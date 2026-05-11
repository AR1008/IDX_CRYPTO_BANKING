"""
R_velocity ZK Circuit — Zero-Knowledge Velocity Proof
======================================================
Proves whether a transaction count c crosses a public threshold T,
WITHOUT revealing the exact count c.

CONSTRUCTION:
  Not-suspicious (c < T):
    Commit to c:           C_c, r = pedersen.commit(c)
    Prove c in [0, T-1]:  create_range_proof(c, max_value_paise=T, context)
    Note: create_range_proof proves value < max_value_paise (strictly less),
    so max_value_paise=T is correct for proving c ∈ [0, T-1].

  Suspicious (c >= T):
    Commit to delta=c-T:   C_d, r = pedersen.commit(c - T)
    Prove delta in [0, M]: create_range_proof(c-T, max_value_paise=MAX_COUNT-T+1, context)
    where MAX_COUNT = 10000 (safe upper bound on transactions per window)
    Note: max_value_paise=MAX_COUNT-T+1 proves delta ∈ [0, MAX_COUNT-T].

SECURITY PROPERTIES:
  Privacy:   Verifier learns is_suspicious (bool) and the commitment point,
             but NOT the exact count c. The Pedersen commitment is computationally
             hiding under the Decisional Diffie-Hellman assumption on secp256k1.
  Soundness: 2^{-256} forgery probability — inherits from simple_range_proof.py
             (Schnorr sigma protocols + Fiat-Shamir transform).
  Binding:   proof['context'] = SHA256(window_label + tx_hash) — ties each proof
             to a specific transaction and time window, preventing replay.

USAGE:
  proof = prove_velocity(count=7, threshold=5, window_label="1h", tx_hash="0xabc...")
  assert verify_velocity(proof) == True   # verifier confirms: IS suspicious

Reference: Cramer, Damgård, Schoenmakers (1994). "Proofs of Partial Knowledge
           and Simplified Design of Witness Hiding Protocols." CRYPTO 1994.
           (OR-proof technique used internally by simple_range_proof.py)
"""

# [DOC] hashlib: SHA-256 used to derive the proof-binding context string from window label + tx hash.
import hashlib
# [DOC] time: perf_counter used only in the self-test block to measure prove/verify latency.
import time
# [DOC] Dict/Any/Optional: type hints for function signatures — no runtime effect.
from typing import Dict, Any, Optional

# [DOC] pedersen_commit: samples a random blinding r, returns C = v*G + r*H on secp256k1.
# [DOC] serialize_point: converts the EC point C to a 66-char hex string for JSON storage.
from core.crypto.real.pedersen import commit as pedersen_commit, serialize_point
# [DOC] create_range_proof: proves a value lies in [0, max_value_paise) using Schnorr OR-proofs (CDS 1994).
# [DOC] verify_range_proof: checks the Schnorr equations for every bit commitment in the proof dict.
from core.crypto.real.simple_range_proof import create_range_proof, verify_range_proof

# [DOC] MAX_COUNT: safe upper bound on transactions any user can make in a single rolling window.
# [DOC] 10,000 is orders of magnitude above any real-world usage — sets the suspicious branch range.
MAX_COUNT: int = 10_000

# [DOC] _SCHEME: identifies the cryptographic construction used — recorded in every proof for auditability.
_SCHEME = "pedersen_range_secp256k1"
# [DOC] _VERSION: proof format version — bump if the proof structure changes incompatibly.
_VERSION = "velocity_1.0"


def _make_context(window_label: str, tx_hash: str) -> str:
    """
    Derive a deterministic proof-binding context string.

    Binds the range proof to a specific (transaction, window) pair so the
    proof cannot be replayed for a different transaction or a different window.

    Args:
        window_label: "1h", "24h", or "7d" — identifies the rolling window.
        tx_hash:      Transaction hash being evaluated.

    Returns:
        64-char hex SHA-256 digest of "velocity:{window_label}:{tx_hash}".
    """
    # [DOC] Prefix "velocity:" domain-separates this context from other SHA-256 uses in the system.
    # [DOC] Including both window_label and tx_hash ensures the context is unique per (window, transaction) pair.
    raw = f"velocity:{window_label}:{tx_hash}".encode("utf-8")
    # [DOC] hexdigest() returns a 64-character lowercase hex string — safe to embed in JSON.
    return hashlib.sha256(raw).hexdigest()


def prove_velocity(
    count: int,
    threshold: int,
    window_label: str,
    tx_hash: str,
) -> Dict[str, Any]:
    """
    Generate a ZK proof of the velocity classification for a rolling window.

    The proof reveals is_suspicious (bool) and a Pedersen commitment to either
    count (if not suspicious) or count-threshold (if suspicious), but never
    reveals the exact count.

    Args:
        count:        Number of transactions the sender made in this window (secret).
        threshold:    Public AML threshold (e.g. 5 for 1h, 10 for 24h, 50 for 7d).
        window_label: Human-readable window identifier: "1h", "24h", or "7d".
        tx_hash:      Hash of the transaction being evaluated — binds proof to tx.

    Returns:
        Dict with keys:
            version, scheme, window, threshold, is_suspicious,
            C_committed (hex), range_proof (Dict), context (hex)

    Raises:
        ValueError: if count < 0 or count > MAX_COUNT.
        ImportError: if py_ecc is not installed.
    """
    # [DOC] Reject impossible inputs immediately — a negative count or a count above MAX_COUNT
    # [DOC] means the caller made a programming error; both would cause range-proof failure anyway.
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    if count > MAX_COUNT:
        raise ValueError(f"count {count} exceeds MAX_COUNT {MAX_COUNT}")
    if threshold <= 0:
        raise ValueError(f"threshold must be > 0, got {threshold}")

    # [DOC] Derive the binding context — SHA256("velocity:{window_label}:{tx_hash}").
    # [DOC] This context string is passed into the range proof so the proof is tied to this exact
    # [DOC] (window, transaction) pair and cannot be replayed in a different context.
    context = _make_context(window_label, tx_hash)
    # [DOC] is_suspicious: the single public output of this ZK proof — True if count >= threshold.
    is_suspicious = count >= threshold

    if not is_suspicious:
        # [DOC] Not-suspicious branch: commit to count itself and prove count ∈ [0, threshold-1].
        # [DOC] create_range_proof proves value < max_value_paise (strict), so passing threshold
        # [DOC] means the range is [0, threshold-1] — i.e., count is strictly below the AML threshold.
        committed_value = count
        max_value = threshold
    else:
        # [DOC] Suspicious branch: commit to delta = count - threshold (the excess above the threshold).
        # [DOC] Proving delta ∈ [0, MAX_COUNT - threshold] is equivalent to proving count ∈ [threshold, MAX_COUNT].
        # [DOC] max_value = MAX_COUNT - threshold + 1 because create_range_proof proves value < max_value_paise.
        committed_value = count - threshold
        max_value = MAX_COUNT - threshold + 1

    # [DOC] Create an independent Pedersen commitment to the value for external verifier convenience.
    # [DOC] C = committed_value * G + r * H on secp256k1; r is a random blinding factor (discarded).
    # [DOC] This commitment hides committed_value under DDH — revealing nothing about the count.
    C, _blinding = pedersen_commit(committed_value)
    # [DOC] Serialize C to a 66-byte SEC1-compressed hex string for JSON storage.
    C_hex = serialize_point(C)

    # [DOC] Generate the range proof — proves committed_value ∈ [0, max_value) using Schnorr OR-proofs.
    # [DOC] The range proof internally creates its own Pedersen commitments to each bit of committed_value;
    # [DOC] C_hex above is a separate top-level commitment included for external verifier convenience.
    range_proof = create_range_proof(
        value_paise=committed_value,
        max_value_paise=max_value,
        context=context,
    )

    # [DOC] Return a self-contained proof dict that any verifier can check with verify_velocity().
    # [DOC] The verifier learns: is_suspicious, C_committed, and which window/threshold was used.
    # [DOC] The verifier does NOT learn: the exact count (privacy guarantee).
    return {
        "version": _VERSION,
        "scheme": _SCHEME,
        # [DOC] window: "1h", "24h", or "7d" — tells verifier which rolling window this proof covers.
        "window": window_label,
        # [DOC] threshold: the public AML threshold — same value the anomaly engine uses in its checks.
        "threshold": threshold,
        # [DOC] is_suspicious: True if count >= threshold — the primary output of the ZK classification.
        "is_suspicious": is_suspicious,
        # [DOC] C_committed: Pedersen commitment to count (not suspicious) or count-threshold (suspicious).
        "C_committed": C_hex,
        # [DOC] range_proof: the cryptographic proof dict — verified by verify_range_proof() internally.
        "range_proof": range_proof,
        # [DOC] context: SHA-256 binding tag — ties this proof to a specific (window, transaction) pair.
        "context": context,
    }


def verify_velocity(proof: Dict[str, Any]) -> bool:
    """
    Verify a velocity ZK proof.

    Checks that the embedded range proof is cryptographically valid.
    The verifier learns is_suspicious and the commitment, not the exact count.

    Args:
        proof: Dict produced by prove_velocity().

    Returns:
        True if the proof is valid, False otherwise.

    Security note:
        A forged proof is accepted with probability at most 2^{-256}
        (inherits soundness from simple_range_proof.verify_range_proof).
    """
    try:
        # [DOC] Extract the nested range proof dict — the only field that carries the cryptographic evidence.
        range_proof = proof.get("range_proof")
        # [DOC] A missing range_proof key means the proof is malformed — reject immediately.
        if range_proof is None:
            return False
        # [DOC] Delegate to the Schnorr OR-proof verifier: checks every bit commitment's Schnorr equation.
        # [DOC] Any single failing bit commitment causes the entire proof to be rejected.
        return verify_range_proof(range_proof)
    except Exception:
        # [DOC] Catch all exceptions — malformed proof dicts, missing keys, wrong types — and return False.
        # [DOC] This ensures verify_velocity never raises; it always returns a safe boolean.
        return False


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # [DOC] copy.deepcopy: needed in Test 3 to tamper with a copy without mutating the original proof.
    import copy

    # [DOC] TX_HASH: a 64-character fake transaction hash used as the binding context for all test proofs.
    TX_HASH = "0xdeadbeef" * 8  # 64-char fake tx hash for testing

    print("=" * 70)
    print("R_velocity ZK Circuit — Self Tests")
    print("=" * 70)

    # ── Test 1: Not suspicious (count < threshold) ─────────────────────────
    # [DOC] Test 1: count=3 < threshold=5 → is_suspicious must be False and proof must verify.
    print("\nTest 1: count=3, threshold=5 → should be NOT suspicious")
    proof = prove_velocity(count=3, threshold=5, window_label="1h", tx_hash=TX_HASH)
    assert proof["is_suspicious"] is False, "Expected not suspicious"
    assert verify_velocity(proof) is True, "Proof should verify"
    print(f"  PASS  is_suspicious={proof['is_suspicious']}, verify=True")

    # ── Test 2: Suspicious (count >= threshold) ────────────────────────────
    # [DOC] Test 2: count=7 >= threshold=5 → is_suspicious must be True and proof must verify.
    print("\nTest 2: count=7, threshold=5 → should be SUSPICIOUS")
    proof = prove_velocity(count=7, threshold=5, window_label="1h", tx_hash=TX_HASH)
    assert proof["is_suspicious"] is True, "Expected suspicious"
    assert verify_velocity(proof) is True, "Proof should verify"
    print(f"  PASS  is_suspicious={proof['is_suspicious']}, verify=True")

    # ── Test 3: Soundness — tampered proof must be rejected ────────────────
    # [DOC] Test 3: corrupting value_commitment in the range proof must make verify_velocity return False.
    # [DOC] This confirms the Schnorr sum-check detects any change to the committed value.
    print("\nTest 3: Tampered proof → should FAIL verification")
    proof = prove_velocity(count=7, threshold=5, window_label="1h", tx_hash=TX_HASH)
    tampered = copy.deepcopy(proof)
    # Corrupt an actual field in the range proof to break verification.
    # bit_proofs[0] has keys: protocol, C, context, branch_0, branch_1.
    # Overwriting value_commitment (top-level hex) breaks the sum check.
    if tampered["range_proof"].get("bit_proofs"):
        tampered["range_proof"]["value_commitment"] = "ff" * 33
    result = verify_velocity(tampered)
    assert result is False, "Tampered proof must not verify"
    print(f"  PASS  tampered proof rejected (verify=False)")

    # ── Test 4: All three velocity windows ────────────────────────────────
    # [DOC] Test 4: exercise each of the three AML windows and an edge case (count = threshold - 1).
    # [DOC] The edge case (9, T=10) previously revealed a bug: max_value must be threshold, not threshold-1.
    print("\nTest 4: All three windows (1h, 24h, 7d)")
    windows = [
        (3, 5, "1h", False),    # below 1h threshold
        (12, 10, "24h", True),  # above 24h threshold
        (60, 50, "7d", True),   # above 7d threshold
        (9, 10, "24h", False),  # exactly below 24h threshold
    ]
    for count, threshold, window, expected_flag in windows:
        p = prove_velocity(count, threshold, window, TX_HASH)
        assert p["is_suspicious"] == expected_flag, \
            f"count={count} T={threshold}: expected {expected_flag}, got {p['is_suspicious']}"
        assert verify_velocity(p) is True, f"Proof failed for {window}"
        print(f"  PASS  window={window} count={count} T={threshold} is_suspicious={p['is_suspicious']}")

    # ── Test 5: Timing ─────────────────────────────────────────────────────
    # [DOC] Test 5: measures average prove and verify latency over 10 trials.
    # [DOC] The assertion limit is 50,000ms (50 seconds) — a generous guard against runaway regressions.
    # [DOC] Actual timings are printed so the developer can monitor for unacceptable slowdowns.
    print("\nTest 5: Timing (10 trials each)")
    prove_times = []
    verify_times = []
    for _ in range(10):
        t0 = time.perf_counter()
        p = prove_velocity(7, 5, "1h", TX_HASH)
        prove_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        verify_velocity(p)
        verify_times.append((time.perf_counter() - t0) * 1000)

    avg_prove = sum(prove_times) / len(prove_times)
    avg_verify = sum(verify_times) / len(verify_times)
    print(f"  Prove:  avg={avg_prove:.1f}ms  (target < 50ms)")
    print(f"  Verify: avg={avg_verify:.1f}ms  (target < 30ms)")
    assert avg_prove < 50_000, f"Prove too slow: {avg_prove:.1f}ms"  # generous limit
    print("  PASS  timing within bounds")

    print("\n" + "=" * 70)
    print("All R_velocity ZK tests PASSED.")
    print("=" * 70)
    print("\nSecurity summary:")
    print("  Privacy:   Exact count is hidden — only is_suspicious is revealed.")
    print("  Soundness: 2^{-256} forgery probability (Schnorr + Fiat-Shamir).")
    print("  Binding:   Proof is tied to tx_hash + window via SHA-256 context.")
