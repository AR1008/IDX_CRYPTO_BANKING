"""
Cryptographic Primitive Benchmarks — For Paper Table Generation
================================================================
Measures wall-clock time for every real cryptographic operation in ZK-AML.
Run this to produce the numbers for Section 6 (Evaluation) of the paper.

Usage:
    python3 tests/benchmarks/benchmark_crypto_primitives.py

Output:
    Prints a Markdown table ready to paste into the paper.
    Also writes results to tests/benchmarks/results/benchmark_YYYYMMDD.json

Hardware context MUST be reported in the paper alongside these numbers.
Run on the same hardware class as your comparison targets:
    - Platypus/PayOff use: Intel i7 / AWS c5.xlarge
    - Androulaki (2023) uses: AWS t3.medium

What this measures:
    1.  Pedersen commit            (secp256k1, py_ecc)
    2.  Pedersen open/verify
    3.  Schnorr DLOG proof         (secp256k1, Fiat-Shamir)
    4.  Schnorr DLOG verify
    5.  Schnorr commitment-opening proof
    6.  Schnorr commitment-opening verify
    7.  Range proof create         (O(n) Schnorr OR-proof, 32-bit)
    8.  Range proof verify         (O(n) Schnorr OR-proof, 32-bit)
    9.  Bulletproofs create        (O(log n), 64-bit) [if installed]
    10. Bulletproofs verify        (O(log n), 64-bit) [if installed]
    11. AES-256-GCM encrypt        (1KB payload)
    12. AES-256-GCM decrypt        (1KB payload)
    13. BBS04 sign                 (BN254, Charm-Crypto)
    14. BBS04 verify               (BN254, Charm-Crypto)
    15. BBS04 open                 (BN254, Charm-Crypto)
    16. Anomaly ZKP generate       (full AnomalyZKPService call)
    17. Anomaly ZKP verify
    18. Full transaction commit    (Pedersen + range proof combined)

Each operation is run N_TRIALS = 50 times. Report: mean, median, p95, p99.
"""

# [DOC] sys and os are used to inject the project root into sys.path so all core modules resolve
import sys
import os
# [DOC] time.perf_counter is used for high-resolution wall-clock timing of each operation
import time
# [DOC] json serialises the results dict to disk for paper traceability
import json
# [DOC] statistics computes mean, median, p95, p99 over raw timing arrays
import statistics
# [DOC] platform.processor() records the CPU model alongside every result for hardware transparency
import platform
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# [DOC] N_TRIALS=50 balances statistical accuracy against total runtime (~15 min for slow BBS04)
N_TRIALS = 50   # Number of repetitions per operation

# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------
# [DOC] bench() is the generic harness: runs fn() n times, records ms per call, returns percentile stats
def bench(name: str, fn, n: int = N_TRIALS):
    """Run fn() n times and return timing stats in milliseconds."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        result = fn()
        t1 = time.perf_counter()
        # [DOC] Convert seconds to milliseconds so all printed values share a consistent unit
        times.append((t1 - t0) * 1000)   # convert to ms
    return {
        "name":   name,
        "n":      n,
        "mean_ms":   round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        # [DOC] p95 and p99 reveal tail-latency; p95 is the primary number cited in the paper table
        "p95_ms":    round(sorted(times)[int(0.95 * n)], 3),
        "p99_ms":    round(sorted(times)[int(0.99 * n)], 3),
        "min_ms":    round(min(times), 3),
        "max_ms":    round(max(times), 3),
    }


results = []

print("=" * 70)
print("ZK-AML Cryptographic Primitive Benchmarks")
print(f"Date:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Platform: {platform.processor()}")
print(f"Python:   {sys.version.split()[0]}")
print(f"Trials:   {N_TRIALS} per operation")
print("=" * 70)


# ---------------------------------------------------------------------------
# 1-2. Pedersen Commitments
# ---------------------------------------------------------------------------
# [DOC] Pedersen commit (C = v*G + r*H) hides the transaction amount under DDH on secp256k1;
# [DOC] this measures the EC scalar-multiplication cost paid once per transaction on the sender side
print("\n[1/18] Pedersen commitments (secp256k1, py_ecc)...")
try:
    # [DOC] commit() and verify_opening() are from core/crypto/real/pedersen.py using py_ecc
    from core.crypto.real.pedersen import commit as pedersen_commit, verify_opening

    # [DOC] VALUE = 50000_00 paise (₹50,000) represents a high-value transaction near the PMLA threshold
    VALUE = 50000_00   # ₹50,000 in paise

    # [DOC] Benchmark 1: commit — measures cost of hiding the amount in a Pedersen commitment
    results.append(bench("Pedersen commit", lambda: pedersen_commit(VALUE)))

    C, r = pedersen_commit(VALUE)
    # [DOC] Benchmark 2: open/verify — measures cost of checking C == v*G + r*H during consensus
    results.append(bench("Pedersen open/verify", lambda: verify_opening(C, VALUE, r)))
    print(f"  commit: {results[-2]['mean_ms']:.2f}ms  |  open: {results[-1]['mean_ms']:.2f}ms")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "Pedersen commit", "error": str(e)})
    results.append({"name": "Pedersen open/verify", "error": str(e)})


# ---------------------------------------------------------------------------
# 3-4. Schnorr DLOG proof
# ---------------------------------------------------------------------------
# [DOC] Schnorr DLOG proof demonstrates knowledge of a discrete logarithm x such that P = x*G;
# [DOC] this is the building block for CBC commitment-opening proofs and the anomaly ZKP
print("\n[3/18] Schnorr DLOG proof (secp256k1)...")
try:
    # [DOC] prove_dlog and verify_dlog are from core/crypto/real/schnorr.py (Fiat-Shamir heuristic)
    from core.crypto.real.schnorr import prove_dlog, verify_dlog
    # [DOC] secrets provides cryptographically secure random integers for the DLOG witness
    import secrets as _secrets
    from py_ecc.secp256k1 import secp256k1 as _secp

    # [DOC] x_scalar is a random 256-bit DLOG witness; P_point = x*G is the corresponding public element
    x_scalar = _secrets.randbelow(
        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    )
    P_point = _secp.multiply(_secp.G, x_scalar)

    # [DOC] Benchmark 3: prove — measures cost of generating one Schnorr sigma protocol transcript
    results.append(bench("Schnorr DLOG prove", lambda: prove_dlog(x_scalar, P_point)))
    proof = prove_dlog(x_scalar, P_point)
    # [DOC] Benchmark 4: verify — measures cost of checking the Fiat-Shamir challenge equation
    results.append(bench("Schnorr DLOG verify", lambda: verify_dlog(proof)))
    print(f"  prove: {results[-2]['mean_ms']:.2f}ms  |  verify: {results[-1]['mean_ms']:.2f}ms")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "Schnorr DLOG prove", "error": str(e)})
    results.append({"name": "Schnorr DLOG verify", "error": str(e)})


# ---------------------------------------------------------------------------
# 5-6. Schnorr commitment-opening proof
# ---------------------------------------------------------------------------
# [DOC] Schnorr commitment-opening proof proves knowledge of (v, r) such that C = v*G + r*H;
# [DOC] this is the CBC primitive used to prove AML rule compliance without revealing the amount
print("\n[5/18] Schnorr commitment-opening proof (secp256k1)...")
try:
    # [DOC] prove_commitment_opening and verify_commitment_opening extend the DLOG proof to two witnesses
    from core.crypto.real.schnorr import prove_commitment_opening, verify_commitment_opening
    from core.crypto.real.pedersen import commit as pedersen_commit_2

    VALUE2 = 100000_00
    C2, r2 = pedersen_commit_2(VALUE2)
    # [DOC] Benchmark 5: proves (value, blinding) knowledge for a commitment — the CBC prove step
    results.append(bench("Schnorr commit-open prove",
                         lambda: prove_commitment_opening(C2, VALUE2, r2, context="BENCH")))
    proof2 = prove_commitment_opening(C2, VALUE2, r2, context="BENCH")
    # [DOC] Benchmark 6: verifies the commitment-opening proof — the CBC verify step for regulators
    results.append(bench("Schnorr commit-open verify",
                         lambda: verify_commitment_opening(proof2)))
    print(f"  prove: {results[-2]['mean_ms']:.2f}ms  |  verify: {results[-1]['mean_ms']:.2f}ms")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "Schnorr commit-open prove", "error": str(e)})
    results.append({"name": "Schnorr commit-open verify", "error": str(e)})


# ---------------------------------------------------------------------------
# 7-8. O(n) Range proofs (Schnorr OR-proofs, current Python impl)
# ---------------------------------------------------------------------------
# [DOC] O(n) range proof uses n Schnorr OR-proofs, one per bit; this is the Python fallback path
# [DOC] when the Rust Bulletproofs dylib is unavailable; note: NOT the number used in the paper
print("\n[7/18] Range proof — O(n) Schnorr OR-proofs (32-bit)...")
try:
    # [DOC] simple_range_proof.py is the fallback O(n) implementation in core/crypto/real/
    from core.crypto.real.simple_range_proof import create_range_proof, verify_range_proof

    RP_VALUE = 50000_00
    RP_MAX   = 100000_00
    # [DOC] Benchmark 7: create O(n) range proof — expected to be slow (~hundreds of ms per proof)
    results.append(bench("Range proof create (O(n), 32-bit)",
                         lambda: create_range_proof(RP_VALUE, RP_MAX, context="BENCH"),
                         n=min(N_TRIALS, 10)))   # O(n) is slow — use fewer trials
    rp = create_range_proof(RP_VALUE, RP_MAX, context="BENCH")
    # [DOC] Benchmark 8: verify O(n) range proof — also slow; compare to Bulletproofs O(log n) in §9-10
    results.append(bench("Range proof verify (O(n), 32-bit)",
                         lambda: verify_range_proof(rp),
                         n=min(N_TRIALS, 10)))
    print(f"  create: {results[-2]['mean_ms']:.1f}ms  |  verify: {results[-1]['mean_ms']:.1f}ms")
    print(f"  NOTE: O(n) — this is slow by design; Bulletproofs needed for paper numbers")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "Range proof create (O(n), 32-bit)", "error": str(e)})
    results.append({"name": "Range proof verify (O(n), 32-bit)", "error": str(e)})


# ---------------------------------------------------------------------------
# 9-10. Bulletproofs (if py_bulletproofs installed)
# ---------------------------------------------------------------------------
# [DOC] Bulletproofs use O(log n) communication and no trusted setup; this section measures
# [DOC] the native Rust dalek library (libbp_binding.dylib) wrapped via ctypes
print("\n[9/18] Bulletproofs (O(log n), 64-bit) — native Rust dylib ...")
try:
    # [DOC] bulletproofs_wrapper.py calls into libbp_binding.dylib (compiled Rust, aarch64 Ristretto255)
    from core.crypto.real.bulletproofs_wrapper import (
        create_range_proof,
        verify_range_proof,
        proof_size_bytes,
    )
    # [DOC] BP_VALUE is a large paise amount (₹50 lakh) used to exercise the full 64-bit range
    BP_VALUE = 500000_00

    # [DOC] Benchmark 9: Bulletproofs create — the primary prove-time number in Table 1 of the paper
    results.append(bench("Bulletproofs create (64-bit)",
                         lambda: create_range_proof(BP_VALUE, bit_length=64)))
    bp = create_range_proof(BP_VALUE, bit_length=64)
    # [DOC] Benchmark 10: Bulletproofs verify — the primary verify-time number in Table 1 of the paper
    results.append(bench("Bulletproofs verify (64-bit)",
                         lambda: verify_range_proof(bp)))
    print(f"  create: {results[-2]['mean_ms']:.2f}ms  |  verify: {results[-1]['mean_ms']:.2f}ms")
    print(f"  Proof size: {proof_size_bytes(64)} bytes  (O(log 64), Ristretto255)")

except Exception as e:
    print(f"  ERROR: {e}")
    results.append({"name": "Bulletproofs create (64-bit)", "error": str(e)})
    results.append({"name": "Bulletproofs verify (64-bit)", "error": str(e)})


# ---------------------------------------------------------------------------
# 11-12. AES-256-GCM
# ---------------------------------------------------------------------------
# [DOC] AES-256-GCM encrypts the per-transaction private record (sender IDX, receiver IDX, amount);
# [DOC] this is the RCTD symmetric layer; expected cost is negligible (<0.1 ms) vs ZK operations
print("\n[11/18] AES-256-GCM (1KB payload)...")
try:
    # [DOC] AES from pycryptodome (MODE_GCM) provides authenticated encryption with associated data
    from Crypto.Cipher import AES
    # [DOC] get_random_bytes generates a fresh nonce per encryption call — mandatory for GCM security
    from Crypto.Random import get_random_bytes
    import json as _json

    KEY_HEX  = get_random_bytes(32).hex()
    # [DOC] 1KB payload represents the encrypted transaction detail record (sender IDX, receiver IDX, amount)
    PAYLOAD  = "x" * 1024   # 1KB plaintext

    # [DOC] _aes_enc encrypts with a fresh 16-byte nonce each call; includes the JSON serialisation overhead
    def _aes_enc():
        key   = bytes.fromhex(KEY_HEX)
        nonce = get_random_bytes(16)
        c     = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ct, t = c.encrypt_and_digest(PAYLOAD.encode())
        return _json.dumps({"nonce": nonce.hex(), "tag": t.hex(), "ciphertext": ct.hex()})

    enc_out = _aes_enc()

    # [DOC] _aes_dec decrypts and verifies the GCM authentication tag; tag failure raises ValueError
    def _aes_dec():
        d   = _json.loads(enc_out)
        key = bytes.fromhex(KEY_HEX)
        c   = AES.new(key, AES.MODE_GCM, nonce=bytes.fromhex(d["nonce"]))
        return c.decrypt_and_verify(bytes.fromhex(d["ciphertext"]), bytes.fromhex(d["tag"]))

    # [DOC] Benchmark 11: encrypt — cost of sealing the private transaction record at STEP 6 of the flow
    results.append(bench("AES-256-GCM encrypt (1KB)", _aes_enc))
    # [DOC] Benchmark 12: decrypt — cost of opening the private record during a court-ordered decryption
    results.append(bench("AES-256-GCM decrypt (1KB)", _aes_dec))
    print(f"  encrypt: {results[-2]['mean_ms']:.3f}ms  |  decrypt: {results[-1]['mean_ms']:.3f}ms")

except Exception as e:
    print(f"  SKIP: {e}")


# ---------------------------------------------------------------------------
# 13-15. BBS04 Group Signatures
# ---------------------------------------------------------------------------
# [DOC] BBS04 group signatures on BN254 allow each bank to vote anonymously in consensus;
# [DOC] the opener (FFA) can later trace which bank signed a disputed batch
print("\n[13/18] BBS04 group signatures (BN254, Charm-Crypto)...")
try:
    # [DOC] BBSGroupSignature is in core/crypto/real/bbs_group_signature.py using Charm-Crypto BN254
    from core.crypto.real.bbs_group_signature import BBSGroupSignature

    bbs = BBSGroupSignature()
    print("  Running setup(12)... (this takes ~5-10 seconds)")
    # [DOC] setup(n_banks=12) generates group keys for all 12 consortium banks;
    # [DOC] in production this is done once and keys are stored in the Bank ORM row
    params   = bbs.setup(n_banks=12)
    gpk      = params["group_pk"]
    sk_b1    = params["bank_keys"][0]["signing_key"]
    ok       = params["open_key"]
    certs    = params["bank_certificates"]
    MSG      = "BATCH_BENCHMARK_001"

    # [DOC] Benchmark 13: sign — cost of one bank casting an anonymous vote on a batch;
    # [DOC] expected ~92 ms in Python (charm-crypto BN254 pairing); would be ~10 ms in native C
    results.append(bench("BBS04 sign (BN254)",
                         lambda: bbs.sign(gpk, sk_b1, MSG),
                         n=min(N_TRIALS, 10)))

    sig = bbs.sign(gpk, sk_b1, MSG)

    # [DOC] Benchmark 14: verify — cost of a bank checking another bank's vote signature;
    # [DOC] called T=10 times per batch to assemble the required approval count
    results.append(bench("BBS04 verify (BN254)",
                         lambda: bbs.verify(gpk, sig, MSG),
                         n=min(N_TRIALS, 10)))

    # [DOC] Benchmark 15: open/trace — cost of the opener identifying which bank signed a disputed batch;
    # [DOC] requires bank_certs to map the recovered key back to a bank identity
    results.append(bench("BBS04 open/trace (BN254)",
                         lambda: bbs.open(gpk, ok, sig, MSG, certs),
                         n=min(N_TRIALS, 10)))

    import json as _json2
    sig_bytes = len(_json2.dumps(_json2.loads(sig)).encode())
    print(f"  sign: {results[-3]['mean_ms']:.0f}ms  |  verify: {results[-2]['mean_ms']:.0f}ms  |  open: {results[-1]['mean_ms']:.0f}ms")
    print(f"  Signature size (JSON): ~{sig_bytes} bytes (9 group elements)")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "BBS04 sign (BN254)", "error": str(e)})
    results.append({"name": "BBS04 verify (BN254)", "error": str(e)})
    results.append({"name": "BBS04 open/trace (BN254)", "error": str(e)})


# ---------------------------------------------------------------------------
# 16-17. Anomaly ZKP (full AnomalyZKPService)
# ---------------------------------------------------------------------------
# [DOC] AnomalyZKPService wraps the full CBC anomaly proof pipeline (Schnorr + Fiat-Shamir);
# [DOC] benchmarks 16-17 measure end-to-end generate+verify times as used in the transaction flow
print("\n[16/18] Anomaly ZKP (full service call)...")
try:
    # [DOC] AnomalyZKPService is the production class in core/crypto/anomaly_zkp.py (Schnorr ZKP v2.0)
    from core.crypto.anomaly_zkp import AnomalyZKPService

    zkp = AnomalyZKPService()
    TX_HASH = "a" * 64
    SCORE   = 75.5
    FLAGS   = ["high_value", "velocity"]

    # [DOC] Benchmark 16: generate — cost of proving anomaly score >= threshold without revealing the score
    results.append(bench("Anomaly ZKP generate",
                         lambda: zkp.generate_anomaly_proof(TX_HASH, SCORE, FLAGS, True),
                         n=min(N_TRIALS, 20)))

    proof = zkp.generate_anomaly_proof(TX_HASH, SCORE, FLAGS, True)

    # [DOC] Benchmark 17: verify — cost of checking the anomaly proof; determines regulatory audit throughput
    results.append(bench("Anomaly ZKP verify",
                         lambda: zkp.verify_anomaly_proof(proof, TX_HASH),
                         n=min(N_TRIALS, 20)))

    import json as _json3
    proof_bytes = len(_json3.dumps(proof).encode())
    print(f"  generate: {results[-2]['mean_ms']:.1f}ms  |  verify: {results[-1]['mean_ms']:.1f}ms")
    print(f"  Proof size: ~{proof_bytes} bytes")

except Exception as e:
    print(f"  SKIP: {e}")
    results.append({"name": "Anomaly ZKP generate", "error": str(e)})
    results.append({"name": "Anomaly ZKP verify", "error": str(e)})


# ---------------------------------------------------------------------------
# 18. Full transaction commitment pipeline
# ---------------------------------------------------------------------------
# [DOC] Benchmark 18 chains Pedersen commit and O(n) range proof together to measure
# [DOC] the total sender-side cryptographic cost per transaction in the Python-only Config A path
print("\n[18/18] Full transaction commitment pipeline...")
try:
    # [DOC] Uses Python-only primitives (pedersen + simple_range_proof) so the result reflects Config A TPS
    from core.crypto.real.pedersen import commit as _pc, serialize_point
    from core.crypto.real.simple_range_proof import create_range_proof as _crp

    AMOUNT  = 100000_00
    BALANCE = 500000_00

    # [DOC] _full_pipeline simulates steps 1-2 of the transaction flow: commit amount then create range proof
    def _full_pipeline():
        C, r   = _pc(AMOUNT)
        comm   = serialize_point(C)
        proof  = _crp(AMOUNT, BALANCE, context="BENCH_TX")
        return comm, proof

    # [DOC] Only 5 trials because O(n) range proof is slow; sufficient to estimate Config A TPS ceiling
    results.append(bench("Full tx pipeline (commit + range proof)",
                         _full_pipeline, n=5))
    print(f"  mean: {results[-1]['mean_ms']:.0f}ms  → max TPS ≈ {1000/results[-1]['mean_ms']:.0f}")
    print(f"  NOTE: This is py_ecc Python; native Rust would be ~100x faster")

except Exception as e:
    print(f"  SKIP: {e}")


# ---------------------------------------------------------------------------
# Print results table
# ---------------------------------------------------------------------------
# [DOC] The results table is formatted as Markdown for direct copy-paste into the paper's Section 6
print("\n\n")
print("=" * 70)
print("RESULTS TABLE (paste into paper Section 6)")
print("=" * 70)
print(f"\nHardware: {platform.processor()}")
print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
print(f"Trials per operation: {N_TRIALS}\n")

header = f"{'Operation':<45} {'Mean':>8} {'Median':>8} {'p95':>8} {'p99':>8}"
print(header)
print("-" * 79)

for r in results:
    name = r.get("name", "?")
    if "error" in r:
        print(f"  {name:<43} {'SKIP (import error)':>38}")
    elif "note" in r:
        print(f"  {name:<43} {r['note']:>38}")
    elif "mean_ms" in r:
        print(f"  {name:<43} {r['mean_ms']:>7.2f}ms {r['median_ms']:>7.2f}ms "
              f"{r['p95_ms']:>7.2f}ms {r['p99_ms']:>7.2f}ms")

print("-" * 79)
print("All times in milliseconds. p95/p99 = 95th/99th percentile latency.")
print("Run on dedicated hardware for paper submission numbers.")

# ---------------------------------------------------------------------------
# Save results to JSON
# ---------------------------------------------------------------------------
# [DOC] Saves the full results list (including errors) to a timestamped JSON file
# [DOC] so benchmark runs are reproducible and traceable to a specific date and machine
os.makedirs("tests/benchmarks/results", exist_ok=True)
out_path = f"tests/benchmarks/results/benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(out_path, "w") as f:
    json.dump({
        "date":     datetime.now().isoformat(),
        "platform": platform.processor(),
        "python":   sys.version,
        "n_trials": N_TRIALS,
        "results":  results,
    }, f, indent=2)

print(f"\nFull results saved to: {out_path}")
print("=" * 70)
