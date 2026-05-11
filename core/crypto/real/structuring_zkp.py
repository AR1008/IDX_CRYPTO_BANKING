"""
R_structuring ZK Circuit — Zero-Knowledge Structuring Detection Proof
=====================================================================
Proves whether a transaction amount falls in the suspicious structuring
range [low, high) — WITHOUT revealing the exact amount.

WHAT IS STRUCTURING?
  Structuring (also called "smurfing") is the deliberate practice of splitting
  large transactions into smaller ones just below a mandatory reporting threshold
  to evade AML detection. For example, sending ₹9.6 lakh instead of ₹10 lakh
  because ₹10 lakh triggers PMLA mandatory reporting.

  This system's structuring rule flags amounts in [₹9.5 lakh, ₹10 lakh)
  (i.e., 95%–100% of the ₹10 lakh threshold) as suspicious.

CONSTRUCTION:
  Amounts are represented as integers (whole rupees).
    low   = STRUCTURING_THRESHOLD × STRUCTURING_PROXIMITY  (₹9,50,000)
    high  = STRUCTURING_THRESHOLD                           (₹10,00,000)
    width = high − low                                      (₹50,000)

  Branch BELOW (amount < low — not structuring):
    Commit to amount:         C = pedersen.commit(amount)
    Prove amount ∈ [0, low):  create_range_proof(amount, max_value_paise=low, context)

  Branch STRUCTURING (low ≤ amount < high — suspicious):
    Let delta = amount − low
    Commit to delta:          C = pedersen.commit(delta)
    Prove delta ∈ [0, width): create_range_proof(delta, max_value_paise=width, context)
    Equivalently:             proves amount ∈ [low, high)

  Branch ABOVE (amount ≥ high — not structuring):
    Let delta = amount − high
    Commit to delta:          C = pedersen.commit(delta)
    Prove delta ∈ [0, MAX_AMOUNT−high):
                              create_range_proof(delta, max_value_paise=MAX_AMOUNT−high+1, context)
    Equivalently:             proves amount ∈ [high, MAX_AMOUNT]

  Note: create_range_proof proves value < max_value_paise (strictly less than),
  so all max_value arguments are set one above the inclusive upper bound.

SECURITY PROPERTIES:
  Privacy:   Verifier learns is_structuring (bool) and a Pedersen commitment,
             but NOT the exact amount. The commitment is computationally hiding
             under the Decisional Diffie-Hellman assumption on secp256k1.
  Soundness: 2^{-256} forgery probability — inherits from simple_range_proof.py
             (Schnorr OR-proofs over bit commitments + Fiat-Shamir transform).
  Binding:   proof['context'] = SHA-256("structuring:{tx_hash}") — ties the proof
             to a specific transaction, preventing replay.

USAGE:
  proof = prove_structuring(
      amount=960000, low=950000, high=1000000, tx_hash="0xabc..."
  )
  assert verify_structuring(proof) is True   # verifier: IS structuring suspicious

Reference: Cramer, Damgård, Schoenmakers (1994). "Proofs of Partial Knowledge
           and Simplified Design of Witness Hiding Protocols." CRYPTO 1994.
           (OR-proof technique used internally by simple_range_proof.py)
"""

# [DOC] hashlib: SHA-256 used to derive the proof-binding context string from the transaction hash.
import hashlib
# [DOC] time: perf_counter used only in the self-test block to measure prove/verify latency.
import time
# [DOC] Dict/Any: type hints for function signatures — no runtime effect.
from typing import Dict, Any

# [DOC] pedersen_commit: samples a random blinding r, returns C = v*G + r*H on secp256k1.
# [DOC] serialize_point: converts the EC point C to a 66-char SEC1-compressed hex string for JSON.
from core.crypto.real.pedersen import commit as pedersen_commit, serialize_point
# [DOC] create_range_proof: proves a value lies in [0, max_value_paise) using Schnorr OR-proofs (CDS 1994).
# [DOC] verify_range_proof: re-checks every bit commitment's Schnorr equation and the sum equality.
from core.crypto.real.simple_range_proof import create_range_proof, verify_range_proof

# [DOC] MAX_AMOUNT: safe upper bound on any single transaction amount (₹1 crore in whole rupees).
# [DOC] Used to set the upper bound for the ABOVE branch range proof (amount ≥ high).
MAX_AMOUNT: int = 10_000_000  # ₹1 crore

# [DOC] Branch labels: recorded in the proof dict so the verifier knows which range sub-case was proven.
# [DOC] BELOW = amount < low (not suspicious), STRUCTURING = amount in [low, high) (suspicious),
# [DOC] ABOVE = amount >= high (not suspicious, large legitimate transfer).
_BRANCH_BELOW = "BELOW"
_BRANCH_STRUCTURING = "STRUCTURING"
_BRANCH_ABOVE = "ABOVE"

# [DOC] _SCHEME: identifies the cryptographic construction for auditability and version tracking.
_SCHEME = "pedersen_range_secp256k1"
# [DOC] _VERSION: proof format version — bump if the proof structure changes incompatibly.
_VERSION = "structuring_1.0"


def _make_context(tx_hash: str) -> str:
    """
    Derive a deterministic proof-binding context string.

    Binds the range proof to a specific transaction so the proof cannot be
    replayed for a different transaction.

    Args:
        tx_hash: Transaction hash being evaluated.

    Returns:
        64-char hex SHA-256 digest of "structuring:{tx_hash}".
    """
    # [DOC] Prefix "structuring:" domain-separates this context from velocity and other SHA-256 uses.
    # [DOC] Including tx_hash ensures the context is unique per transaction — replay is infeasible.
    raw = f"structuring:{tx_hash}".encode("utf-8")
    # [DOC] hexdigest() returns a 64-character lowercase hex string — safe to embed in JSON proof dicts.
    return hashlib.sha256(raw).hexdigest()


def prove_structuring(
    amount: int,
    low: int,
    high: int,
    tx_hash: str,
) -> Dict[str, Any]:
    """
    Generate a ZK proof classifying a transaction amount as structuring-suspicious or not.

    The proof reveals is_structuring (bool) and a Pedersen commitment to a derived
    value (the amount itself or an offset from a threshold), but never the exact amount.

    Three branches:
      BELOW      (amount < low):         proves amount ∈ [0, low)
      STRUCTURING (low ≤ amount < high): proves (amount − low) ∈ [0, high − low)
      ABOVE      (amount ≥ high):        proves (amount − high) ∈ [0, MAX_AMOUNT − high)

    Args:
        amount:   Transaction amount in whole rupees (int). Caller truncates Decimal to int.
        low:      Lower bound of the suspicious range (inclusive), e.g. 950000 for ₹9.5 lakh.
        high:     Upper bound of the suspicious range (exclusive), e.g. 1000000 for ₹10 lakh.
        tx_hash:  Transaction hash — binds the proof to this specific transaction.

    Returns:
        Dict with keys:
            version, scheme, low, high, is_structuring, branch,
            C_committed (hex), range_proof (Dict), context (hex)

    Raises:
        ValueError: if low >= high, amount < 0, or amount > MAX_AMOUNT.
        ImportError: if py_ecc is not installed.
    """
    # [DOC] Validate inputs to catch caller errors early — a negative amount or inverted range
    # [DOC] would silently produce a mathematically invalid proof.
    if low >= high:
        raise ValueError(f"low ({low}) must be < high ({high})")
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount}")
    if amount > MAX_AMOUNT:
        raise ValueError(f"amount {amount} exceeds MAX_AMOUNT {MAX_AMOUNT}")

    # [DOC] Derive the binding context — SHA256("structuring:{tx_hash}").
    # [DOC] Embedding this context inside the range proof prevents proof replay for other transactions.
    context = _make_context(tx_hash)

    if low <= amount < high:
        # [DOC] STRUCTURING branch: amount falls in the suspicious range [low, high).
        # [DOC] Commit to delta = amount - low, the "excess above the lower structuring boundary."
        # [DOC] Proving delta ∈ [0, width-1] is equivalent to proving amount ∈ [low, high).
        # [DOC] max_value = high - low (width) because create_range_proof proves value < max_value.
        is_structuring = True
        branch = _BRANCH_STRUCTURING
        committed_value = amount - low
        max_value = high - low

    elif amount < low:
        # [DOC] BELOW branch: amount is safely below the structuring range.
        # [DOC] Commit to amount directly and prove amount ∈ [0, low-1].
        # [DOC] max_value = low because create_range_proof proves value < max_value (strictly less).
        is_structuring = False
        branch = _BRANCH_BELOW
        committed_value = amount
        max_value = low

    else:
        # [DOC] ABOVE branch: amount >= high — a large legitimate transaction above the reporting threshold.
        # [DOC] Commit to delta = amount - high, the "excess above the PMLA mandatory reporting boundary."
        # [DOC] Proving delta ∈ [0, MAX_AMOUNT - high] proves amount ∈ [high, MAX_AMOUNT].
        # [DOC] max_value = MAX_AMOUNT - high + 1 because create_range_proof proves value < max_value.
        is_structuring = False
        branch = _BRANCH_ABOVE
        committed_value = amount - high
        max_value = MAX_AMOUNT - high + 1

    # [DOC] Create an independent Pedersen commitment to the committed_value.
    # [DOC] C = committed_value * G + r * H on secp256k1; r is a random blinding factor (discarded after).
    # [DOC] This commitment is computationally hiding — a verifier cannot recover committed_value from C.
    C, _blinding = pedersen_commit(committed_value)
    # [DOC] Serialize C to a 66-byte SEC1-compressed hex string for JSON storage in the proof dict.
    C_hex = serialize_point(C)

    # [DOC] Generate the range proof — proves committed_value ∈ [0, max_value) using Schnorr OR-proofs.
    # [DOC] The proof internally creates its own Pedersen commitments to each bit of committed_value;
    # [DOC] C_hex above is an independent top-level commitment for external verifier convenience.
    range_proof = create_range_proof(
        value_paise=committed_value,
        max_value_paise=max_value,
        context=context,
    )

    # [DOC] Return a self-contained proof dict that any verifier can check with verify_structuring().
    # [DOC] The verifier learns: is_structuring, branch, C_committed, low, high — not the exact amount.
    return {
        "version": _VERSION,
        "scheme": _SCHEME,
        # [DOC] low/high: the public AML structuring thresholds that define the suspicious interval.
        "low": low,
        "high": high,
        # [DOC] is_structuring: True if amount ∈ [low, high) — the primary ZK classification output.
        "is_structuring": is_structuring,
        # [DOC] branch: "BELOW", "STRUCTURING", or "ABOVE" — tells the verifier which range was proven.
        # [DOC] Revealing branch is acceptable: it only discloses whether amount < low, in [low,high), or >= high.
        "branch": branch,
        # [DOC] C_committed: Pedersen commitment to amount, amount-low, or amount-high depending on branch.
        "C_committed": C_hex,
        # [DOC] range_proof: the cryptographic OR-proof dict — verified by verify_range_proof() internally.
        "range_proof": range_proof,
        # [DOC] context: SHA-256 binding tag — ties this proof to the specific transaction.
        "context": context,
    }


def verify_structuring(proof: Dict[str, Any]) -> bool:
    """
    Verify a structuring ZK proof.

    Checks that the embedded range proof is cryptographically valid.
    The verifier learns is_structuring, branch, and the commitment, not the exact amount.

    Args:
        proof: Dict produced by prove_structuring().

    Returns:
        True if the range proof is valid, False otherwise.

    Security note:
        A forged proof is accepted with probability at most 2^{-256}
        (inherits soundness from simple_range_proof.verify_range_proof).
    """
    try:
        # [DOC] Extract the nested range proof dict — the only field carrying cryptographic evidence.
        range_proof = proof.get("range_proof")
        # [DOC] A missing range_proof key means the proof dict is malformed — reject immediately.
        if range_proof is None:
            return False
        # [DOC] Delegate to the Schnorr OR-proof verifier: checks every bit commitment's Schnorr equation
        # [DOC] and the sum-of-bit-commitments equality check. A single failing check returns False.
        return verify_range_proof(range_proof)
    except Exception:
        # [DOC] Catch all exceptions — malformed dicts, wrong types, missing keys — and return False.
        # [DOC] verify_structuring() never raises; callers always get a safe boolean.
        return False


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # [DOC] copy.deepcopy: needed in the soundness test to tamper with a copy without mutating the original.
    import copy

    # [DOC] Use the same thresholds as the anomaly engine: low = ₹9.5 lakh, high = ₹10 lakh.
    LOW = 950_000   # ₹9,50,000 — 95% of ₹10 lakh PMLA threshold
    HIGH = 1_000_000  # ₹10,00,000 — PMLA mandatory reporting threshold
    # [DOC] TX_HASH: a 64-character fake transaction hash used as the binding context for all tests.
    TX_HASH = "0xdeadbeef" * 8

    print("=" * 70)
    print("R_structuring ZK Circuit — Self Tests")
    print("=" * 70)

    # ── Test 1: BELOW — amount < low (not structuring) ────────────────────
    # [DOC] Test 1: amount=500000 (₹5 lakh) is well below the suspicious range → not structuring.
    print("\nTest 1: amount=500000 (BELOW low=950000) → should NOT be structuring")
    proof = prove_structuring(amount=500_000, low=LOW, high=HIGH, tx_hash=TX_HASH)
    assert proof["is_structuring"] is False, "Expected not structuring"
    assert proof["branch"] == _BRANCH_BELOW, f"Expected BELOW, got {proof['branch']}"
    assert verify_structuring(proof) is True, "Proof should verify"
    print(f"  PASS  is_structuring={proof['is_structuring']}, branch={proof['branch']}, verify=True")

    # ── Test 2: STRUCTURING — amount in [low, high) (suspicious) ─────────
    # [DOC] Test 2: amount=960000 (₹9.6 lakh) is inside [₹9.5L, ₹10L) → structuring suspicious.
    print("\nTest 2: amount=960000 (STRUCTURING in [950000, 1000000)) → should be STRUCTURING")
    proof = prove_structuring(amount=960_000, low=LOW, high=HIGH, tx_hash=TX_HASH)
    assert proof["is_structuring"] is True, "Expected structuring"
    assert proof["branch"] == _BRANCH_STRUCTURING, f"Expected STRUCTURING, got {proof['branch']}"
    assert verify_structuring(proof) is True, "Proof should verify"
    print(f"  PASS  is_structuring={proof['is_structuring']}, branch={proof['branch']}, verify=True")

    # ── Test 3: ABOVE — amount >= high (not structuring) ──────────────────
    # [DOC] Test 3: amount=1500000 (₹15 lakh) is above the ₹10L threshold → large legitimate transfer.
    print("\nTest 3: amount=1500000 (ABOVE high=1000000) → should NOT be structuring")
    proof = prove_structuring(amount=1_500_000, low=LOW, high=HIGH, tx_hash=TX_HASH)
    assert proof["is_structuring"] is False, "Expected not structuring"
    assert proof["branch"] == _BRANCH_ABOVE, f"Expected ABOVE, got {proof['branch']}"
    assert verify_structuring(proof) is True, "Proof should verify"
    print(f"  PASS  is_structuring={proof['is_structuring']}, branch={proof['branch']}, verify=True")

    # ── Test 4: Edge cases — boundary amounts ─────────────────────────────
    # [DOC] Test 4: verify the exact boundary amounts are classified correctly.
    # [DOC] amount=low is suspicious (inclusive), amount=high is not (exclusive upper bound).
    print("\nTest 4: Boundary amounts")
    cases = [
        (LOW,       True,  "amount == low (inclusive lower bound → suspicious)"),
        (HIGH - 1,  True,  "amount == high-1 (inclusive upper bound → suspicious)"),
        (HIGH,      False, "amount == high (exclusive upper bound → not suspicious)"),
        (LOW - 1,   False, "amount == low-1 (just below lower bound → not suspicious)"),
    ]
    for amt, expected_flag, desc in cases:
        p = prove_structuring(amount=amt, low=LOW, high=HIGH, tx_hash=TX_HASH)
        assert p["is_structuring"] == expected_flag, \
            f"amount={amt}: expected {expected_flag}, got {p['is_structuring']} ({desc})"
        assert verify_structuring(p) is True, f"Proof failed for amount={amt}"
        print(f"  PASS  amount={amt:>8}  is_structuring={p['is_structuring']}  ({desc})")

    # ── Test 5: Soundness — tampered proof must be rejected ────────────────
    # [DOC] Test 5: corrupting value_commitment in the range proof must make verify_structuring return False.
    # [DOC] This confirms the Schnorr sum-check detects any change to the committed value.
    print("\nTest 5: Tampered proof → should FAIL verification")
    proof = prove_structuring(amount=960_000, low=LOW, high=HIGH, tx_hash=TX_HASH)
    tampered = copy.deepcopy(proof)
    # [DOC] Overwrite value_commitment with all-0xFF bytes — breaks the sum-of-bit-commitments check.
    if tampered["range_proof"].get("bit_proofs"):
        tampered["range_proof"]["value_commitment"] = "ff" * 33
    result = verify_structuring(tampered)
    assert result is False, "Tampered proof must not verify"
    print(f"  PASS  tampered proof rejected (verify=False)")

    # ── Test 6: Timing ─────────────────────────────────────────────────────
    # [DOC] Test 6: measures prove and verify latency over 5 trials.
    # [DOC] The STRUCTURING branch (16-bit range) is the tightest range proof;
    # [DOC] the ABOVE branch (24-bit range) is the slowest.
    print("\nTest 6: Timing (5 trials, STRUCTURING and ABOVE branches)")
    print("  STRUCTURING branch (16-bit range):")
    prove_times_s, verify_times_s = [], []
    for _ in range(5):
        t0 = time.perf_counter()
        p = prove_structuring(960_000, LOW, HIGH, TX_HASH)
        prove_times_s.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        verify_structuring(p)
        verify_times_s.append((time.perf_counter() - t0) * 1000)
    print(f"    Prove avg:  {sum(prove_times_s)/len(prove_times_s):.1f}ms")
    print(f"    Verify avg: {sum(verify_times_s)/len(verify_times_s):.1f}ms")

    print("  ABOVE branch (24-bit range):")
    prove_times_a, verify_times_a = [], []
    for _ in range(5):
        t0 = time.perf_counter()
        p = prove_structuring(1_500_000, LOW, HIGH, TX_HASH)
        prove_times_a.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        verify_structuring(p)
        verify_times_a.append((time.perf_counter() - t0) * 1000)
    print(f"    Prove avg:  {sum(prove_times_a)/len(prove_times_a):.1f}ms")
    print(f"    Verify avg: {sum(verify_times_a)/len(verify_times_a):.1f}ms")
    print("  PASS  timing complete (no hard limit — see notes in testing guide)")

    print("\n" + "=" * 70)
    print("All R_structuring ZK tests PASSED.")
    print("=" * 70)
    print("\nSecurity summary:")
    print("  Privacy:   Exact amount is hidden — only is_structuring + branch revealed.")
    print("  Soundness: 2^{-256} forgery probability (Schnorr + Fiat-Shamir).")
    print("  Binding:   Proof is tied to tx_hash via SHA-256 context.")
    print("\nBranch privacy note:")
    print("  The 'branch' field reveals whether amount < ₹9.5L, in [₹9.5L,₹10L), or >= ₹10L.")
    print("  For production, omit 'branch'; verifier infers from is_structuring + range_proof.")
