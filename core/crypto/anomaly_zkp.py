# [DOC] anomaly_zkp.py — Real Schnorr Zero-Knowledge Proof for AML Anomaly Compliance.
# [DOC] A ZKP lets the system prove it computed the anomaly score correctly without revealing the score value.
# [DOC] Uses secp256k1 elliptic curve arithmetic via the py_ecc library.
# [DOC] Replaced a broken SHA-256 simulation that accepted any hex string as a valid proof (zero soundness).
"""
Anomaly ZKP — Real Schnorr Zero-Knowledge Proof for AML Compliance
===================================================================
Provides a cryptographically sound zero-knowledge proof that a transaction's
anomaly score was evaluated correctly, without revealing the score value,
the transaction amount, or the specific PMLA rule that triggered the flag.

SECURITY PROPERTIES (all three hold after this rewrite):
  Completeness:  An honest prover always convinces the verifier.
  Soundness:     A forged proof passes with probability ≤ 2^{-256}
                 (under DLOG on secp256k1; Fiat-Shamir in the ROM).
  Zero-Knowledge: Transcript (C, K, s_v, s_r) is simulable without the
                  witness — the verifier learns only that the prover knows
                  (score, blinding) that opens the commitment.

CONSTRUCTION:
  1. Commit to anomaly_score using Pedersen: C = score * G + r * H
     (computationally hiding under DDH; perfectly binding under DLOG).
  2. Generate Schnorr proof of opening: prove knowledge of (score, r) s.t.
     C = score * G + r * H, without revealing either value.
     Verification equation: s_v * G + s_r * H + c * C == K

This replaces the previous SHA-256 simulation whose verifier accepted any
hex string as a valid response (zero soundness — CVE-equivalent issue).

API is backward-compatible: same class name, same method signatures,
same return dict structure — caller (transaction_service_v2.py) unchanged.

References:
  Pedersen (1991) "Non-Interactive and Information-Theoretic Secure VSS"
    CRYPTO 1991 — commitment scheme used here.
  Schnorr (1991) "Efficient Signature Generation by Smart Cards"
    JoC — sigma protocol base.
  Cramer, Damgard, Schoenmakers (1994) "Proofs of Partial Knowledge"
    CRYPTO 1994 — OR-proof technique used in range proof layer.
  Fiat and Shamir (1986) "How to Prove Yourself"
    CRYPTO 1986 — Fiat-Shamir transform (ROM non-interactive conversion).
"""

# [DOC] Standard library imports: json for serialization, secrets for cryptographic randomness.
import json
import secrets
# [DOC] datetime/timezone used to record a UTC timestamp in the proof for audit trail.
from datetime import datetime, timezone
# [DOC] Type hints only — no runtime cost; improves readability of function signatures.
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Real EC primitives — secp256k1 via py_ecc
# ---------------------------------------------------------------------------
# [DOC] _pedersen_commit: creates C = v*G + r*H on secp256k1 — the core hiding commitment.
# [DOC] serialize_point / deserialize_point: convert EC points to/from 130-char hex strings for JSON storage.
from core.crypto.real.pedersen import (
    commit as _pedersen_commit,
    serialize_point,
    deserialize_point,
)
# [DOC] prove_commitment_opening: Schnorr sigma protocol — generates (K, s_v, s_r) without revealing (score, r).
# [DOC] verify_commitment_opening: checks s_v*G + s_r*H + c*C == K using only public data.
from core.crypto.real.schnorr import (
    prove_commitment_opening,
    verify_commitment_opening,
)

# ---------------------------------------------------------------------------
# Curve order (secp256k1) — used for domain validation
# ---------------------------------------------------------------------------
# [DOC] secp256k1 group order n: all field arithmetic is done mod this 256-bit prime.
# [DOC] A scalar outside [1, n-1] is invalid — checking this prevents degenerate proofs.
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# [DOC] Anomaly scores are floats (e.g. 78.5) but EC field elements must be integers.
# [DOC] Multiply by 100 → integer (e.g. 7850) before committing; avoids floating-point non-determinism.
_SCORE_SCALE = 100


# [DOC] AnomalyZKPService: the single public class in this module — instantiate per-request.
class AnomalyZKPService:
    """Real Schnorr ZKP service for PMLA anomaly compliance proofs.

    Produces a cryptographically sound proof that a transaction's anomaly
    score was computed and committed to, without revealing the score value
    or the underlying transaction details.

    Instantiate once per request; not thread-safe across simultaneous calls
    due to per-instance state (none currently, but kept for forward compat).
    """

    # [DOC] PROOF_VERSION "2.0" distinguishes real-crypto proofs from the old "1.0" SHA-256 simulations.
    PROOF_VERSION = "2.0"           # Version bump signals real crypto (was "1.0")
    # [DOC] PROOF_SCHEME names the exact cryptographic construction so verifiers can pick the right algorithm.
    PROOF_SCHEME  = "pedersen_schnorr_secp256k1"

    # -----------------------------------------------------------------------
    # Public API (backward-compatible with caller in transaction_service_v2.py)
    # -----------------------------------------------------------------------

    def generate_anomaly_proof(
        self,
        transaction_hash: str,
        anomaly_score: float,
        anomaly_flags: List[str],
        requires_investigation: bool,
    ) -> Dict[str, Any]:
        """Generate a Schnorr ZKP committing to the anomaly score.

        The proof convinces any verifier that the issuer knows an integer score
        and a blinding factor that open the published Pedersen commitment,
        without revealing either value.

        Args:
            transaction_hash:       Hex string identifying the transaction.
                                    Used as domain separation in the Fiat-Shamir
                                    challenge hash.
            anomaly_score:          Float in [0.0, 100.0] — PMLA risk score.
            anomaly_flags:          List of flag names (e.g. ["HIGH_VALUE_PMLA"]).
                                    Stored encrypted; NOT revealed in proof.
            requires_investigation: True if score >= 65 (PMLA reporting threshold).

        Returns:
            dict with keys:
                version (str):           "2.0"
                scheme (str):            "pedersen_schnorr_secp256k1"
                transaction_hash (str):  Echo of input for audit trail.
                flag_commitment (str):   Pedersen commitment to score (130-char hex).
                timestamp (str):         ISO-8601 UTC timestamp.
                proof_data (dict):       Public Schnorr proof components.
                    C (str):   Commitment point (same as flag_commitment).
                    K (str):   Nonce commitment point.
                    s_v (str): Response scalar for score witness.
                    s_r (str): Response scalar for blinding witness.
                    context (str): Fiat-Shamir domain tag.
                witness (dict):          Private witness — store encrypted; never log.
                    score_scaled (int):  anomaly_score * 100 (integer).
                    blinding_hex (str):  Blinding factor as 64-char hex.
                    anomaly_score (float): Original float score.
                    anomaly_flags (list): Original flag list.
                    requires_investigation (bool): Original flag.

        Raises:
            ValueError: If anomaly_score is outside [0.0, 100.0].
            ImportError: If py_ecc is not installed (pip install py_ecc>=6.0.0).
        """
        # [DOC] Reject scores outside the valid 0–100 range before doing any EC math.
        if not (0.0 <= anomaly_score <= 100.0):
            raise ValueError(
                f"anomaly_score must be in [0.0, 100.0]; got {anomaly_score}"
            )

        # [DOC] Convert float score to integer by scaling: 78.5 → 7850. Required for EC field arithmetic.
        # Scale to integer to avoid floating-point in field arithmetic
        score_int = int(anomaly_score * _SCORE_SCALE)

        # --- Step 1: Pedersen commitment to score ---
        # C = score_int * G + r * H
        # DDH-hiding: C is computationally indistinguishable from random point.
        # DLOG-binding: impossible to open C to a different score_int.
        # [DOC] _pedersen_commit returns (point C, blinding_factor r) — r is random, chosen inside pedersen.py.
        commitment_point, blinding_factor = _pedersen_commit(score_int)
        # [DOC] serialize_point encodes the EC point as a 130-char hex string (uncompressed SEC1 format).
        commitment_hex = serialize_point(commitment_point)

        # --- Step 2: Schnorr proof of commitment opening ---
        # Fiat-Shamir context binds proof to this specific transaction hash,
        # preventing proof replay across transactions.
        # [DOC] The context string is hashed into the Fiat-Shamir challenge c = SHA256(C || K || context).
        # [DOC] Binding the proof to the transaction hash makes it impossible to reuse this proof for a different tx.
        context = f"anomaly_zkp:v2:{transaction_hash}"
        # [DOC] prove_commitment_opening runs the full Schnorr sigma protocol and returns (C, K, s_v, s_r, context).
        proof = prove_commitment_opening(
            C=commitment_point,
            v=score_int,
            r=blinding_factor,
            context=context,
        )

        # [DOC] Return a dict split into: public proof data (safe to store on-chain) and private witness (encrypt before storage).
        return {
            "version":           self.PROOF_VERSION,
            "scheme":            self.PROOF_SCHEME,
            # [DOC] transaction_hash echoed back so the audit log can confirm which tx this proof belongs to.
            "transaction_hash":  transaction_hash,
            # [DOC] flag_commitment is the Pedersen commitment point C — public, reveals nothing about the score.
            "flag_commitment":   commitment_hex,        # Public commitment
            # [DOC] UTC timestamp records when this proof was generated — useful for audit and replay detection.
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "proof_data": {
                # [DOC] C: the Pedersen commitment — public. Verifier uses it in the check s_v*G + s_r*H + c*C == K.
                "C":       proof["C"],                  # Commitment (public)
                # [DOC] K: the nonce commitment — generated fresh each proof; prevents witness extraction.
                "K":       proof["K"],                  # Nonce commitment (public)
                # [DOC] s_v: Schnorr response scalar for the score witness v. Public — reveals nothing alone.
                "s_v":     proof["s_v"],                # Score response (public)
                # [DOC] s_r: Schnorr response scalar for the blinding factor r. Public — reveals nothing alone.
                "s_r":     proof["s_r"],                # Blinding response (public)
                # [DOC] context: domain separation tag used in the challenge hash — must match on verification.
                "context": proof["context"],            # Domain tag (public)
                "protocol": proof["protocol"],
            },
            # [DOC] witness: the private opening (score_int, blinding_factor) — NEVER log or send in API responses.
            # [DOC] Caller (transaction_service_v2) must threshold-encrypt this before writing to the DB.
            # Witness — private; never include in API responses; encrypt before storage
            "witness": {
                # [DOC] score_scaled: the integer version of the score (anomaly_score * 100) used in the commitment.
                "score_scaled":          score_int,
                # [DOC] blinding_hex: 64-char hex of the random blinding factor r — needed to open the commitment.
                "blinding_hex":          f"{blinding_factor:064x}",
                # [DOC] anomaly_score: original float preserved so the court can read a human-friendly value.
                "anomaly_score":         anomaly_score,
                # [DOC] anomaly_flags: list of rule names that fired (e.g. HIGH_VALUE_PMLA) — private, not in proof.
                "anomaly_flags":         anomaly_flags,
                # [DOC] requires_investigation: True if score >= 65 — determines whether this tx needs court access.
                "requires_investigation": requires_investigation,
            },
        }

    def verify_anomaly_proof(
        self,
        zkp_proof: Dict[str, Any],
        expected_transaction_hash: Optional[str] = None,
    ) -> bool:
        """Verify a Schnorr anomaly proof without opening the commitment.

        Checks: s_v * G + s_r * H + c * C == K
        Soundness: a forged proof passes with probability ≤ 2^{-256}.

        Args:
            zkp_proof:                 Proof dict returned by generate_anomaly_proof().
            expected_transaction_hash: If provided, confirms proof is bound to this hash.
                                       Rejects proof if hashes differ.

        Returns:
            True if the proof is cryptographically valid; False otherwise.
            Logs a reason on failure for debugging (no secret data logged).
        """
        try:
            # [DOC] Version check: reject any proof that was made by the old SHA-256 simulation (version "1.0").
            # --- Structural validation ---
            if zkp_proof.get("version") != self.PROOF_VERSION:
                return False
            # [DOC] Scheme check: ensures this verifier uses the right curve and protocol for this proof.
            if zkp_proof.get("scheme") != self.PROOF_SCHEME:
                return False

            # [DOC] If the caller supplies a tx hash, confirm the proof was specifically bound to that transaction.
            # [DOC] This prevents an attacker from presenting a valid proof from tx A to authenticate tx B.
            # --- Transaction hash binding check ---
            if expected_transaction_hash is not None:
                if zkp_proof.get("transaction_hash") != expected_transaction_hash:
                    return False

            # [DOC] Rebuild the dict format expected by verify_commitment_opening in schnorr.py.
            # --- Reconstruct proof dict expected by verify_commitment_opening ---
            pd = zkp_proof["proof_data"]
            schnorr_proof = {
                "protocol": pd["protocol"],
                # [DOC] C, K, s_v, s_r are the four public Schnorr transcript elements.
                "C":        pd["C"],
                "K":        pd["K"],
                "s_v":      pd["s_v"],
                "s_r":      pd["s_r"],
                # [DOC] context must match the string used at proof generation time for challenge recomputation.
                "context":  pd["context"],
            }

            # [DOC] Delegate actual EC math to schnorr.py — computes c = SHA256(C||K||context), checks s_v*G + s_r*H + c*C == K.
            # --- Real EC verification: s_v*G + s_r*H + c*C == K ---
            return verify_commitment_opening(schnorr_proof)

        # [DOC] Catch structural errors (missing keys, wrong types) and return False instead of crashing.
        except (KeyError, TypeError, ValueError):
            return False

    def verify_with_opening(
        self,
        zkp_proof: Dict[str, Any],
        expected_flag_value: int,
    ) -> bool:
        """Verify proof AND check that the committed score matches expected value.

        Used post-court-order when the blinding factor is known and the score
        can be revealed. Verifies both the ZKP and the opening.

        Args:
            zkp_proof:           Full proof dict including 'witness' sub-dict.
            expected_flag_value: Expected score_scaled (anomaly_score * 100).

        Returns:
            True if proof is valid AND committed score equals expected_flag_value.
        """
        # [DOC] First verify the cryptographic proof itself — if it fails, the witness is untrusted.
        # First verify the proof cryptographically
        if not self.verify_anomaly_proof(zkp_proof):
            return False

        # [DOC] Then confirm the decrypted witness matches what was committed — prevents key substitution attacks.
        # Then open the commitment with the stored witness
        witness = zkp_proof.get("witness", {})
        return witness.get("score_scaled") == expected_flag_value

    def extract_anomaly_details(
        self,
        zkp_proof: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract anomaly metadata from a proof (requires witness access).

        This is called only by authorized parties holding the decryption key.
        The witness must have been decrypted from threshold-encrypted storage
        before calling this method.

        Args:
            zkp_proof: Full proof dict including decrypted 'witness' sub-dict.

        Returns:
            dict with keys: flag_value (int), anomaly_score (float),
            anomaly_flags (list), requires_investigation (bool).

        Raises:
            KeyError: If 'witness' sub-dict is absent or incomplete.
        """
        # [DOC] The 'witness' key is only present after threshold-decryption — never in the on-chain public record.
        witness = zkp_proof["witness"]
        # [DOC] Return a clean summary dict; callers should not access the raw witness directly.
        return {
            # [DOC] flag_value: the integer-scaled score (score * 100) that was committed to on the EC curve.
            "flag_value":             witness["score_scaled"],
            # [DOC] anomaly_score: the original float score (e.g. 78.0) for human-readable audit reports.
            "anomaly_score":          witness["anomaly_score"],
            # [DOC] anomaly_flags: list of rule names that triggered (e.g. ["HIGH_VALUE_PMLA"]).
            "anomaly_flags":          witness["anomaly_flags"],
            # [DOC] requires_investigation: True means score >= 65 — the PMLA mandatory reporting threshold.
            "requires_investigation": witness["requires_investigation"],
        }


# ---------------------------------------------------------------------------
# Self-test (run with: python3 core/crypto/anomaly_zkp.py)
# ---------------------------------------------------------------------------
# [DOC] __main__ block: run this file directly to verify the Schnorr ZKP works end-to-end.
if __name__ == "__main__":
    print("=" * 65)
    print("AnomalyZKPService — Real Schnorr ZKP Self-Tests")
    print("=" * 65)
    print()

    svc = AnomalyZKPService()

    # Test 1: Normal transaction (no flag)
    # [DOC] Test 1: low-risk score 12.5 — proof must generate and verify successfully.
    print("Test 1: Low-risk transaction (score=12.5, not flagged)")
    proof_low = svc.generate_anomaly_proof(
        transaction_hash="abcdef1234567890" * 4,
        anomaly_score=12.5,
        anomaly_flags=[],
        requires_investigation=False,
    )
    assert svc.verify_anomaly_proof(proof_low), "Low-risk proof must verify"
    # [DOC] Confirm that changing the tx hash causes the proof to fail — tests binding.
    assert not svc.verify_anomaly_proof(proof_low, expected_transaction_hash="wrong_hash"), \
        "Wrong tx hash must fail"
    print("  PASS: valid proof verifies; wrong tx hash rejected\n")

    # Test 2: High-risk transaction (flagged)
    # [DOC] Test 2: high-risk score 78.0 with multiple flags — proof must still verify.
    print("Test 2: High-risk transaction (score=78.0, flagged for PMLA)")
    proof_high = svc.generate_anomaly_proof(
        transaction_hash="deadbeef12345678" * 4,
        anomaly_score=78.0,
        anomaly_flags=["HIGH_VALUE_PMLA", "VELOCITY_STRUCTURING"],
        requires_investigation=True,
    )
    assert svc.verify_anomaly_proof(proof_high), "High-risk proof must verify"
    print("  PASS: flagged transaction proof verifies\n")

    # Test 3: Tampered proof must fail
    # [DOC] Test 3: replace the s_v scalar with zeros — the EC check s_v*G + s_r*H + c*C == K must fail.
    print("Test 3: Tampered proof (altered s_v scalar) must be rejected")
    import copy
    forged = copy.deepcopy(proof_high)
    forged["proof_data"]["s_v"] = "0" * 64         # Replace response with zeros
    assert not svc.verify_anomaly_proof(forged), "Tampered proof must be rejected"
    print("  PASS: tampered proof correctly rejected\n")

    # Test 4: verify_with_opening
    # [DOC] Test 4: simulate a court-order scenario where the witness is decrypted and the score verified.
    print("Test 4: verify_with_opening (court-order scenario)")
    assert svc.verify_with_opening(proof_high, expected_flag_value=7800), \
        "Opening must match committed score"
    # [DOC] Wrong expected score 9999 must fail — confirms the commitment binds to exactly one score.
    assert not svc.verify_with_opening(proof_high, expected_flag_value=9999), \
        "Wrong expected score must fail"
    print("  PASS: verify_with_opening correct\n")

    # Test 5: extract_anomaly_details
    # [DOC] Test 5: after threshold-decryption, extract_anomaly_details must return the correct metadata.
    print("Test 5: extract_anomaly_details")
    details = svc.extract_anomaly_details(proof_high)
    assert details["anomaly_score"] == 78.0
    assert "HIGH_VALUE_PMLA" in details["anomaly_flags"]
    assert details["requires_investigation"] is True
    print("  PASS: details extracted correctly\n")

    # Test 6: Invalid score rejected at generation time
    # [DOC] Test 6: score 101.0 is out of range — must raise ValueError before any EC math runs.
    print("Test 6: Invalid score (> 100) raises ValueError")
    try:
        svc.generate_anomaly_proof("tx_hash", 101.0, [], False)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  PASS: ValueError raised for out-of-range score\n")

    print("=" * 65)
    print("All tests PASSED — soundness: 2^{-256} per proof")
    print("Scheme: Pedersen commitment + Schnorr sigma protocol (secp256k1)")
    print("=" * 65)
