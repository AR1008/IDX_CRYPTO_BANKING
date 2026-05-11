"""
TPS (Transactions Per Second) Benchmark — For Paper Section 6
==============================================================
Measures end-to-end transaction throughput at the cryptographic layer.
This is NOT a database/network benchmark — it measures the pure crypto cost.

Three configurations:
  Config A: Python py_ecc (current, honest, slow)
  Config B: Native libs estimate (Rust Bulletproofs + libsecp256k1)
  Config C: SHA-256 simulation (OLD — shown only for comparison, NOT for paper claims)

Usage:
    python3 tests/benchmarks/benchmark_tps.py

What "one transaction" costs cryptographically:
    1. Pedersen commit to amount        (~5ms py_ecc / ~0.05ms native)
    2. Range proof create (64-bit)      (~500ms py_ecc / ~20ms Bulletproofs)
    3. Schnorr anomaly ZKP              (~15ms py_ecc / ~0.5ms native)
    4. AES-256-GCM encrypt details      (~0.1ms / ~0.1ms)
    -----------------------------------------------------------------
    Total per-tx crypto cost:   ~520ms py_ecc | ~21ms native | ~0.01ms SHA-256 sim

Maximum honest TPS:
    py_ecc Python (single core):       ~2 TPS
    Native Rust (single core):         ~50 TPS
    Native Rust (12 cores):            ~500 TPS
    Platypus/PayOff (Groth16, Rust):   ~5,000-80,000 TPS (different proof system)

IMPORTANT FOR PAPER:
    Never report the SHA-256 simulation TPS (~4,000) as your system's throughput.
    Report Config A (honest) and Config B (projected with native libs).
    State clearly: "Config A is our reference Python implementation.
    Config B projects performance with Rust native libraries (Bulletproofs crate,
    libsecp256k1) which are direct drop-in replacements on the same algorithm."
"""

# [DOC] sys and os are used to add the project root to sys.path so all core modules resolve
import sys
import os
# [DOC] time.perf_counter provides the high-resolution wall-clock used for all tx timing
import time
# [DOC] json serialises benchmark results to disk for paper traceability
import json
# [DOC] statistics.mean summarises per-transaction timing samples into a single TPS figure
import statistics
# [DOC] platform.processor() records the CPU name alongside every result for hardware transparency
import platform
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# [DOC] measure_tps_config_a runs n_tx complete transactions through the Python-only path:
# [DOC] Pedersen commit + O(n) Schnorr range proof + anomaly ZKP + AES-256-GCM;
# [DOC] this is the honest Config A TPS reported in the paper (no simulation, real crypto)
def measure_tps_config_a(n_tx: int = 20) -> dict:
    """Config A: Python py_ecc — honest, current implementation."""
    # [DOC] All four crypto modules needed for one complete transaction
    from core.crypto.real.pedersen import commit as pedersen_commit, serialize_point
    from core.crypto.real.simple_range_proof import create_range_proof
    from core.crypto.anomaly_zkp import AnomalyZKPService
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    import hashlib

    zkp     = AnomalyZKPService()
    key_hex = get_random_bytes(32).hex()
    tx_times = []

    print(f"  Running {n_tx} transactions (Config A: Python py_ecc)...")
    for i in range(n_tx):
        t0 = time.perf_counter()

        # [DOC] Step 1: Pedersen commit hides the paise amount under DDH — STEP 1 of the tx flow
        # Step 1: Pedersen commit
        amount_paise = 50000_00 + i * 100
        C, r         = pedersen_commit(amount_paise)
        commitment   = serialize_point(C)

        # [DOC] Step 2: O(n) Schnorr range proof proves amount is in [0, max_balance] without revealing it
        # Step 2: Range proof (O(n) Schnorr — honest current impl)
        rp = create_range_proof(amount_paise, 100000_00, context=commitment[:16])

        # [DOC] Step 3: Schnorr anomaly ZKP proves the anomaly score without revealing the score value
        # Step 3: Anomaly ZKP
        tx_hash = hashlib.sha256(f"tx_{i}".encode()).hexdigest()
        proof   = zkp.generate_anomaly_proof(tx_hash, 45.0, ["velocity"], False)

        # [DOC] Step 4: AES-256-GCM encrypts the private record (sender IDX, receiver IDX, amount) — STEP 6
        # Step 4: AES-256-GCM encrypt
        key    = bytes.fromhex(key_hex)
        nonce  = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(f"sender=IDX_001,receiver=IDX_002,amount={amount_paise}".encode())

        t1 = time.perf_counter()
        tx_times.append((t1 - t0) * 1000)
        if (i + 1) % 5 == 0:
            print(f"    {i+1}/{n_tx} done  ({tx_times[-1]:.0f}ms/tx)")

    mean_ms = statistics.mean(tx_times)
    tps     = 1000 / mean_ms
    return {
        "config":   "A — Python py_ecc (honest)",
        "n_tx":     n_tx,
        "mean_ms":  round(mean_ms, 1),
        "tps":      round(tps, 1),
        "min_ms":   round(min(tx_times), 1),
        "max_ms":   round(max(tx_times), 1),
        "note":     "Reference implementation. Correct but slow.",
    }


# [DOC] measure_tps_config_a_bulletproofs runs n_tx transactions with Python Pedersen/Schnorr
# [DOC] but replaces the slow O(n) range proof with the Rust dalek Bulletproofs dylib;
# [DOC] this is the best measured single-machine TPS and the primary Config A2 number in the paper
def measure_tps_config_a_bulletproofs(n_tx: int = 20) -> dict:
    """Config A2: Python py_ecc + native Rust Bulletproofs (best honest single-machine)."""
    # [DOC] bp_prove calls into libbp_binding.dylib (Rust, aarch64) via the ctypes wrapper
    from core.crypto.real.pedersen import commit as pedersen_commit, serialize_point
    from core.crypto.real.bulletproofs_wrapper import create_range_proof as bp_prove
    from core.crypto.anomaly_zkp import AnomalyZKPService
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    import hashlib

    zkp     = AnomalyZKPService()
    key_hex = get_random_bytes(32).hex()
    tx_times = []

    print(f"  Running {n_tx} transactions (Config A2: py_ecc + Rust Bulletproofs)...")
    for i in range(n_tx):
        t0 = time.perf_counter()
        amount_paise = 50000_00 + i * 100
        C, r         = pedersen_commit(amount_paise)
        commitment   = serialize_point(C)
        # [DOC] bp_prove calls Rust bp_create (Ristretto255, 64-bit) — replaces O(n) Python range proof
        rp           = bp_prove(amount_paise, bit_length=64)
        tx_hash      = hashlib.sha256(f"tx_{i}".encode()).hexdigest()
        proof        = zkp.generate_anomaly_proof(tx_hash, 45.0, ["velocity"], False)
        key    = bytes.fromhex(key_hex)
        nonce  = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(f"sender=IDX_001,receiver=IDX_002,amount={amount_paise}".encode())
        t1 = time.perf_counter()
        tx_times.append((t1 - t0) * 1000)
        if (i + 1) % 5 == 0:
            print(f"    {i+1}/{n_tx} done  ({tx_times[-1]:.0f}ms/tx)")

    mean_ms = statistics.mean(tx_times)
    tps     = 1000 / mean_ms
    return {
        "config":  "A2 — py_ecc Pedersen + Rust Bulletproofs (measured)",
        "n_tx":    n_tx,
        "mean_ms": round(mean_ms, 1),
        "tps":     round(tps, 1),
        "note":    "Hybrid: Schnorr/Pedersen in Python, range proof in Rust.",
    }


# [DOC] measure_tps_config_b_estimated computes a projected TPS using published component benchmarks;
# [DOC] this is NOT a live measurement — it projects what fully native Rust/C libraries would achieve
def measure_tps_config_b_estimated() -> dict:
    """Config B: Projected TPS with fully native Rust libraries.

    These numbers are computed from published benchmarks of each component:
      - libsecp256k1 (C): ~0.05ms per scalar multiplication
      - Bulletproofs (Rust, dalek): ~20ms prove, ~15ms verify (Bünz et al. 2018)
      - Schnorr ZKP (libsecp256k1): ~0.5ms (2 scalar mults)
      - AES-256-GCM (AES-NI): ~0.01ms for 1KB

    Sources:
      Pedersen/Schnorr: bitcoin/secp256k1 bench, ~50K ops/sec → ~0.02ms
      Bulletproofs: https://github.com/dalek-cryptography/bulletproofs#benchmarks
      AES-GCM: ~10GB/s on AES-NI hardware → negligible
    """
    # [DOC] Component latencies are sourced from published library benchmarks, not measured here
    pedersen_ms   = 0.05     # libsecp256k1, scalar mult
    range_ms      = 20.0     # Bulletproofs prove, 64-bit (Bünz et al. 2018)
    schnorr_ms    = 0.5      # Schnorr ZKP, 2 scalar mults
    aes_ms        = 0.01     # AES-256-GCM, negligible

    total_ms      = pedersen_ms + range_ms + schnorr_ms + aes_ms
    tps_single    = 1000 / total_ms
    # [DOC] tps_12cores assumes linear scaling (embarrassingly parallel crypto, no shared state)
    tps_12cores   = tps_single * 12   # linear scaling for embarrassingly parallel crypto

    return {
        "config":           "B — Estimated (native Rust/C libs)",
        "breakdown": {
            "pedersen_ms":  pedersen_ms,
            "range_ms":     range_ms,
            "schnorr_ms":   schnorr_ms,
            "aes_ms":       aes_ms,
            "total_ms":     total_ms,
        },
        "tps_single_core":  round(tps_single, 0),
        "tps_12_cores":     round(tps_12cores, 0),
        "sources": {
            "pedersen":     "bitcoin/secp256k1 benchmarks",
            "bulletproofs": "Bünz et al. 2018 (S&P), Table 4",
            "schnorr":      "libsecp256k1, ~50K ops/s",
            "aes":          "AES-NI hardware, negligible",
        },
        "note": "Projection — install Rust + py_bulletproofs to measure directly.",
    }


# [DOC] measure_tps_config_c_simulation runs the OLD SHA-256 fake-commitment path for historical comparison;
# [DOC] these numbers must NEVER be reported in the paper as system TPS — they measure Python/hash speed only
def measure_tps_config_c_simulation(n_tx: int = 1000) -> dict:
    """Config C: SHA-256 simulation (OLD) — shown ONLY for historical comparison.

    WARNING: Do NOT report this as your system's TPS in the paper.
    This measures database/Python overhead, not cryptographic security.
    """
    import hashlib
    import secrets
    import json

    tx_times = []
    for i in range(n_tx):
        t0 = time.perf_counter()

        # [DOC] OLD SHA-256 "commitment" — not hiding, not binding in the EC sense; purely illustrative
        # OLD SHA-256 "commitment"
        salt = secrets.token_hex(16)
        commitment = "0x" + hashlib.sha256(
            json.dumps({"sender": "IDX_001", "receiver": "IDX_002",
                        "amount": 50000, "salt": salt}).encode()
        ).hexdigest()

        # [DOC] OLD SHA-256 "range proof" — just a hash, provides no cryptographic range guarantee
        # OLD SHA-256 "range proof"
        range_proof = {"proof": hashlib.sha256(f"range_{i}".encode()).hexdigest()}

        # [DOC] OLD group signature string — just a string literal, provides no anonymity or traceability
        # OLD group signature string
        group_sig = f"GROUP_SIG_SBI_BATCH{i:08d}"

        t1 = time.perf_counter()
        tx_times.append((t1 - t0) * 1000)

    mean_ms = statistics.mean(tx_times)
    tps     = 1000 / mean_ms
    return {
        "config":   "C — SHA-256 simulation (OLD, do not cite in paper)",
        "n_tx":     n_tx,
        "mean_ms":  round(mean_ms, 4),
        "tps":      round(tps, 0),
        "warning":  "This is measuring Python/SHA-256 speed, NOT cryptographic security. NEVER report as system TPS.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# [DOC] main() runs all three configs in sequence and prints the TPS summary table for the paper
if __name__ == "__main__":
    print("=" * 70)
    print("ZK-AML TPS Benchmark")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.processor()}")
    print("=" * 70)

    all_results = {}

    # [DOC] Config A: real EC crypto but slow O(n) range proof; establishes the honest lower bound on TPS
    # Config A — py_ecc + O(n) range proof
    print("\n--- Config A: Real crypto (Python py_ecc, O(n) Schnorr range proof) ---")
    try:
        all_results["config_a"] = measure_tps_config_a(n_tx=10)
        a = all_results["config_a"]
        print(f"\n  RESULT: {a['mean_ms']:.0f}ms/tx → {a['tps']} TPS (single core)")
    except Exception as e:
        print(f"  ERROR: {e}")
        all_results["config_a"] = {"error": str(e)}

    # [DOC] Config A2: real EC crypto + Rust Bulletproofs — the best measured single-machine TPS figure
    # Config A2 — py_ecc Pedersen + Rust Bulletproofs (BEST HONEST CURRENT)
    print("\n--- Config A2: py_ecc Pedersen + Rust Bulletproofs (BEST MEASURED) ---")
    try:
        all_results["config_a2"] = measure_tps_config_a_bulletproofs(n_tx=20)
        a2 = all_results["config_a2"]
        print(f"\n  RESULT: {a2['mean_ms']:.0f}ms/tx → {a2['tps']} TPS (single core)")
    except Exception as e:
        print(f"  ERROR: {e}")
        all_results["config_a2"] = {"error": str(e)}

    # [DOC] Config B: purely projected, not measured; shows what production native-Rust deployment would achieve
    # Config B
    print("\n--- Config B: Fully native Rust/C estimate ---")
    all_results["config_b"] = measure_tps_config_b_estimated()
    b = all_results["config_b"]
    print(f"  Breakdown:")
    for k, v in b["breakdown"].items():
        print(f"    {k:<20} {v:.2f}ms")
    print(f"  RESULT: {b['tps_single_core']:.0f} TPS (1 core) / "
          f"{b['tps_12_cores']:.0f} TPS (12 cores, embarrassingly parallel)")

    # [DOC] Config C: shown for historical context only; must never be cited in the paper as system TPS
    # Config C
    print("\n--- Config C: SHA-256 simulation (for historical comparison ONLY) ---")
    all_results["config_c"] = measure_tps_config_c_simulation(n_tx=500)
    c = all_results["config_c"]
    print(f"  RESULT: {c['mean_ms']:.3f}ms/tx → {c['tps']:.0f} TPS")
    print(f"  ⚠  WARNING: {c['warning']}")

    # [DOC] Summary table formats all configs side-by-side for direct copy into the paper's evaluation table
    # Summary table
    print("\n\n")
    print("=" * 70)
    print("TPS SUMMARY TABLE (for paper)")
    print("=" * 70)
    a2_ms  = all_results.get('config_a2', {}).get('mean_ms', 'N/A')
    a2_tps = all_results.get('config_a2', {}).get('tps', 'N/A')
    print(f"""
| Configuration                                    | Latency/tx | TPS (1 core)  |
|--------------------------------------------------|-----------|---------------|
| Config A:  Python py_ecc + O(n) range proof      | {all_results['config_a'].get('mean_ms', 'N/A'):>8}ms | {all_results['config_a'].get('tps', 'N/A'):>13} |
| Config A2: py_ecc + Rust Bulletproofs (measured) | {a2_ms:>8}ms | {a2_tps:>13} |
| Config B:  Fully native Rust (projected)         | ~{b['breakdown']['total_ms']:.1f}ms    | ~{b['tps_single_core']:.0f} (1 core)  |
| Config B:  Fully native Rust (12 cores)          | ~{b['breakdown']['total_ms']:.1f}ms    | ~{b['tps_12_cores']:.0f} (12 cores) |
| Platypus   (CCS 2022, Groth16, Rust)             |  ~0.012ms  |  80K–150K     |
| PayOff     (2024, Groth16)                       |  ~0.2ms    |  ~5,000       |
| Androulaki (2023, Hyperledger Fabric, 12 nodes)  |  ~1ms      |  ~1,000       |
| SHA-256 simulation (OLD — do NOT cite)           | {all_results['config_c'].get('mean_ms', 'N/A'):>8}ms | {all_results['config_c'].get('tps', 'N/A'):>13} |
""")

    print("""HOW TO CITE THIS IN THE PAPER:
  "We implement ZK-AML in Python using py_ecc for elliptic curve operations
   (Config A). On a [your hardware] machine, this achieves approximately
   [Config A TPS] TPS. We project [Config B TPS] TPS (single core) using
   production-grade Rust implementations (dalek bulletproofs [CITE],
   libsecp256k1 [CITE]), which implement identical algorithms with optimised
   field arithmetic. This compares to Platypus [80K-150K TPS] which uses
   Groth16 SNARKs requiring a trusted setup; our construction uses only
   standard assumptions (DDH, DLOG) with no trusted setup."
""")

    # [DOC] Save all four config results to a timestamped JSON for paper citation and run traceability
    # Save
    os.makedirs("tests/benchmarks/results", exist_ok=True)
    out = f"tests/benchmarks/results/tps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w") as f:
        json.dump({"date": datetime.now().isoformat(),
                   "platform": platform.processor(),
                   "results": all_results}, f, indent=2)
    print(f"Full results saved to: {out}")
    print("=" * 70)
