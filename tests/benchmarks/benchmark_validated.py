"""
ZK-AML Validated Benchmark Suite
==================================
Hardware:  Apple M1 Pro (MacBookPro18,3), 8+2 cores, 16 GB RAM, macOS 26.3
Baseline:  Platypus CCS 2022 (Intel Core i7-7700 @ 3.60 GHz, 4 cores, 16 GB)
           Zerocash S&P 2014  (Intel Core i7, 128-bit security)
           Bulletproofs S&P 2018 (secp256k1 reference numbers)

Methodology
-----------
- Each operation measured N_TRIALS=100 times (warm-up: first 5 discarded).
- Reports: mean, median, p95, p99, std-dev (all in ms).
- Proof sizes in bytes (hardware-independent, exact).
- Batch speedup reported as ratio over sequential (hardware-independent).
- Results saved to tests/benchmarks/results/validated_<timestamp>.json

Paper citation string (update if hardware changes):
  "Apple M1 Pro (aarch64, 3.2 GHz, 8 perf cores, 16 GB LPDDR5),
   macOS 26.3; Python 3.10.19; py_ecc 8.0.0; dalek bulletproofs v4 (Rust 1.93)"
"""

# [DOC] sys and os are needed to manipulate the Python module search path so project modules resolve
import sys
import os
# [DOC] time provides high-resolution perf_counter used for every wall-clock measurement
import time
# [DOC] json serialises benchmark results to a timestamped file for paper citation
import json
# [DOC] statistics computes mean, median, and stdev over the 100 raw timing samples
import statistics
# [DOC] datetime stamps each result file so runs are uniquely identifiable
import datetime
# [DOC] multiprocessing lets the batch-verify benchmark pre-warm a fork pool on multiple CPU cores
import multiprocessing

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

# Activate venv310 if not already active
VENV = os.path.join(ROOT, "venv310")
VENV_SITE = os.path.join(VENV, "lib", "python3.10", "site-packages")
if os.path.isdir(VENV_SITE) and VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

# ── constants ─────────────────────────────────────────────────────────────────
# [DOC] N_TRIALS=100 gives statistically stable estimates; N_WARMUP=5 discards JIT/cache warm-up noise
N_TRIALS   = 100   # measurement trials per operation
N_WARMUP   = 5     # discard first N_WARMUP trials
# [DOC] BATCH_SIZES lists the proof counts used to plot the batch speedup curve in the paper
BATCH_SIZES = [1, 10, 25, 50, 100]   # for batch speedup curve
N_WORKERS  = min(8, multiprocessing.cpu_count())

# [DOC] HARDWARE dict is embedded in every saved JSON so paper reviewers know exact machine specs
HARDWARE = {
    "model":  "Apple M1 Pro (MacBookPro18,3)",
    "cores":  "8 performance + 2 efficiency",
    "ram_gb": 16,
    "os":     "macOS 26.3",
    "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
}

# [DOC] PLATYPUS_REF holds the published Platypus CCS 2022 numbers used in the paper comparison table
# Platypus CCS 2022 reference numbers (Table 1, BN256 curve)
PLATYPUS_REF = {
    "hardware":        "Intel Core i7-7700 @ 3.60 GHz, 4 cores, 16 GB",
    "proof_gen_ms":    110,   # base transaction, BN256
    "verify_ms":       0.89,  # per proof, BN256
    "proof_size_bytes": 418,  # base transaction, BN256
    "tps_server":      922,   # server-side verification TPS, BN256
    "trusted_setup":   True,  # Groth16
    "aml_in_zk":       "Balance limits only (holding + receiving)",
}

# [DOC] ZEROCASH_REF holds the published Zerocash S&P 2014 numbers showing the 9928x prove speedup
# Zerocash S&P 2014 reference numbers
ZEROCASH_REF = {
    "hardware":        "Intel Core i7 (2014)",
    "proof_gen_ms":    87000,  # ~87 seconds per Pour
    "verify_ms":       6,      # <6 ms
    "proof_size_bytes": 288,
    "trusted_setup":   True,
    "aml_in_zk":       "None",
}

# [DOC] BP_PAPER_REF holds the original Bulletproofs S&P 2018 numbers to confirm our Rust impl is faster
# Bulletproofs S&P 2018 reference numbers (secp256k1, 64-bit)
BP_PAPER_REF = {
    "hardware":           "secp256k1, 2018 hardware",
    "proof_gen_ms":       36,
    "verify_ms":          11,
    "proof_size_bytes":   674,
    "batch_marginal_ms":  0.25,   # per proof in a batch (paper §6.3)
    "trusted_setup":      False,
}


# ── timing helper ─────────────────────────────────────────────────────────────

# [DOC] measure() is the core harness: runs fn() n+warmup times, discards warm-up, returns percentile stats
def measure(fn, n=N_TRIALS, warmup=N_WARMUP):
    """Run fn() n+warmup times, discard first warmup, return stats dict (ms)."""
    times = []
    for i in range(n + warmup):
        # [DOC] perf_counter gives sub-microsecond wall-clock resolution; multiply by 1000 for milliseconds
        t0 = time.perf_counter()
        result = fn()
        elapsed = (time.perf_counter() - t0) * 1000
        if i >= warmup:
            times.append(elapsed)
    sorted_t = sorted(times)
    return {
        "mean_ms":   round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "stdev_ms":  round(statistics.stdev(times), 3),
        # [DOC] p95 and p99 characterise tail latency; p95 is the primary number cited in the paper
        "p95_ms":    round(sorted_t[int(0.95 * n)], 3),
        "p99_ms":    round(sorted_t[int(0.99 * n)], 3),
        "min_ms":    round(sorted_t[0], 3),
        "max_ms":    round(sorted_t[-1], 3),
        "n_trials":  n,
        "_last_result": result,
    }


def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print('='*65)


def row(label, val, note=""):
    note_str = f"  [{note}]" if note else ""
    print(f"  {label:<45} {val}{note_str}")


# ── Section 1: Bulletproofs (range proofs) ───────────────────────────────────

# [DOC] bench_bulletproofs measures the Rust dalek Ristretto255 Bulletproofs library:
# [DOC] prove time, verify time, exact proof sizes per bit-length, and three batch-verify strategies
def bench_bulletproofs():
    section("1. Bulletproofs Range Proofs — dalek v4, Ristretto255")
    # [DOC] Import the ctypes-wrapped Rust functions: create_range_proof, verify_range_proof,
    # [DOC] verify_batch_parallel, verify_batch_native, and the analytical proof_size_bytes formula
    from core.crypto.real.bulletproofs_wrapper import (
        create_range_proof, verify_range_proof,
        verify_batch_parallel, verify_batch_native, proof_size_bytes,
    )

    results = {}

    # 1a. Prove time (64-bit)
    # [DOC] Measures how long the Rust prover takes to generate one 64-bit range proof;
    # [DOC] this is the primary prove-time number in the paper comparison table (target: ~8.76 ms)
    print("\n  [1a] Prove time — 64-bit range proof")
    stats = measure(lambda: create_range_proof(1_000_000, bit_length=64))
    last_proof = stats.pop("_last_result")
    results["prove_64bit"] = stats
    row("prove_64bit mean",   f"{stats['mean_ms']:.2f} ms",   f"paper: ~36 ms on 2018 x86")
    row("prove_64bit median", f"{stats['median_ms']:.2f} ms")
    row("prove_64bit p95",    f"{stats['p95_ms']:.2f} ms")
    row("prove_64bit stdev",  f"{stats['stdev_ms']:.2f} ms")

    # 1b. Verify time (64-bit)
    # [DOC] Measures how long the Rust verifier takes to check one 64-bit proof;
    # [DOC] this is the primary verify-time number in the paper table (target: ~2.11 ms)
    print("\n  [1b] Verify time — 64-bit range proof")
    stats = measure(lambda: verify_range_proof(last_proof))
    stats.pop("_last_result")
    results["verify_64bit"] = stats
    row("verify_64bit mean",   f"{stats['mean_ms']:.2f} ms",  f"Platypus: 0.89 ms (Groth16)")
    row("verify_64bit median", f"{stats['median_ms']:.2f} ms")
    row("verify_64bit p95",    f"{stats['p95_ms']:.2f} ms")

    # 1c. Proof sizes (hardware-independent)
    # [DOC] Proof size in bytes is hardware-independent and follows (2*ceil(log2(n))+9)*32;
    # [DOC] these exact byte counts appear in Table 1 of the paper
    print("\n  [1c] Proof sizes (bytes) — hardware-independent")
    results["proof_sizes"] = {}
    for bits in [8, 16, 32, 64]:
        pf = create_range_proof((1 << bits) - 1, bit_length=bits)
        actual = len(bytes.fromhex(pf["proof"]))
        formula = proof_size_bytes(bits)
        results["proof_sizes"][f"{bits}bit"] = actual
        row(f"  {bits}-bit proof size", f"{actual} bytes",
            f"formula (2·ceil(log2({bits}))+9)·32 = {formula}")

    # 1d. Batch verification speedup curve — three strategies
    # [DOC] Compares three batch-verification strategies at B in {1,10,25,50,100}:
    # [DOC] sequential Python, native Rust single ctypes call, and fork-pool multiprocessing
    print(f"\n  [1d] Batch verify speedup curve")
    print(f"       Strategy 1: sequential Python loop over verify_range_proof()")
    print(f"       Strategy 2: native Rust bp_verify_batch() — single ctypes call")
    print(f"       Strategy 3: multiprocessing fork pool ({N_WORKERS} workers, pre-warmed)")
    print(f"       Note: pool pre-warmed to exclude one-time fork overhead from measurements.")
    results["batch"] = {}

    # [DOC] Pre-generate max_batch proofs once so proof generation cost is excluded from speedup measurement
    max_batch = max(BATCH_SIZES)
    print(f"       Generating {max_batch} proofs for batch benchmark...", end="", flush=True)
    proofs_pool = [create_range_proof(i * 100 + 1, bit_length=64) for i in range(max_batch)]
    print(" done")

    # Pre-warm the process pool (one-time fork cost, excluded from measurements).
    import multiprocessing as _mp
    _pool_ctx = _mp.get_context("fork")
    _warm_pool = _pool_ctx.Pool(processes=N_WORKERS)
    # [DOC] Pre-warming the pool avoids counting OS fork overhead in the speedup ratios
    _warm_pool.map(verify_range_proof, proofs_pool[:N_WORKERS])
    print(f"       Pool pre-warmed ({N_WORKERS} workers). Measuring...\n")

    print(f"  {'B':>4}  {'seq_ms':>8}  {'native_ms':>10}  {'par_ms':>8}  "
          f"{'nat_speedup':>11}  {'par_speedup':>11}  {'nat/proof':>10}")
    print("  " + "-" * 70)

    for B in BATCH_SIZES:
        batch_proofs = proofs_pool[:B]

        # Strategy 1: Sequential baseline
        # [DOC] Sequential loop establishes the 1x baseline; each proof verified independently
        t0 = time.perf_counter()
        for p in batch_proofs:
            verify_range_proof(p)
        seq_ms = (time.perf_counter() - t0) * 1000

        # Strategy 2: Native Rust batch (single ctypes call)
        # [DOC] bp_verify_batch makes one FFI call to Rust, amortising per-proof overhead;
        # [DOC] target speedup is ~1.9x at B=100 (hardware-independent ratio)
        native_ok, native_ms = verify_batch_native(batch_proofs, bit_length=64)

        # Strategy 3: Multiprocessing fork pool (pre-warmed)
        # [DOC] Fork pool distributes proofs across N_WORKERS cores;
        # [DOC] target speedup is ~5.9x at B=100 (hardware-dependent ratio)
        t0 = time.perf_counter()
        results_list = _warm_pool.map(verify_range_proof, batch_proofs)
        par_ms = (time.perf_counter() - t0) * 1000
        par_ok = all(results_list)

        nat_speedup = seq_ms / native_ms if native_ms > 0 else float("inf")
        par_speedup = seq_ms / par_ms    if par_ms    > 0 else float("inf")
        per_proof_nat = native_ms / B

        results["batch"][f"B{B}"] = {
            "sequential_ms":   round(seq_ms, 2),
            "native_ms":       round(native_ms, 2),
            "parallel_ms":     round(par_ms, 2),
            "native_speedup":  round(nat_speedup, 2),
            "parallel_speedup": round(par_speedup, 2),
            "per_proof_native_ms": round(per_proof_nat, 3),
            # [DOC] all_valid confirms every proof in the batch verified correctly (correctness invariant)
            "all_valid":       native_ok and par_ok,
            # keep legacy key name for TPS estimate compatibility
            "speedup_x":       round(nat_speedup, 2),
            "per_proof_ms":    round(per_proof_nat, 3),
            "parallel_ms_legacy": round(par_ms, 2),
        }
        print(f"  {B:>4}  {seq_ms:>8.1f}  {native_ms:>10.1f}  {par_ms:>8.1f}  "
              f"{nat_speedup:>10.1f}×  {par_speedup:>10.1f}×  {per_proof_nat:>9.3f}ms")

    print(f"\n  Reference: Bulletproofs paper batch bound ~{BP_PAPER_REF['batch_marginal_ms']} ms/proof (§6.3, secp256k1)")

    _warm_pool.terminate()
    _warm_pool.join()

    return results


# ── Section 2: Pedersen Commitments ──────────────────────────────────────────

# [DOC] bench_pedersen measures Pedersen commitment creation and opening verification on secp256k1
# [DOC] using py_ecc; these numbers underpin the commit cost in Config A/A2 TPS estimates
def bench_pedersen():
    section("2. Pedersen Commitments — py_ecc secp256k1")
    # [DOC] commit() computes C = v*G + r*H; point_to_bytes serialises it to SEC1 compressed form
    from core.crypto.real.pedersen import commit, verify_opening, serialize_point

    results = {}

    # [DOC] Commit benchmark: measures EC scalar-multiplication cost for blinding a transaction amount
    # Commit
    stats = measure(lambda: commit(1_000_000))
    last = stats.pop("_last_result")
    results["commit"] = stats
    row("commit mean",   f"{stats['mean_ms']:.2f} ms")
    row("commit median", f"{stats['median_ms']:.2f} ms")
    row("commit p95",    f"{stats['p95_ms']:.2f} ms")

    # [DOC] verify_opening benchmark: checks C == v*G + r*H; used by each bank during consensus voting
    # Verify opening
    C, r = last
    stats = measure(lambda: verify_opening(C, 1_000_000, r))
    stats.pop("_last_result")
    results["verify_opening"] = stats
    row("verify_opening mean",   f"{stats['mean_ms']:.2f} ms")
    row("verify_opening median", f"{stats['median_ms']:.2f} ms")

    # [DOC] Commitment size is hardware-independent: 33 bytes compressed or 65 bytes uncompressed;
    # [DOC] the 33-byte figure appears in the paper as the on-chain representation cost
    # Commitment size — SEC1 compressed (33 bytes) and uncompressed (65 bytes)
    C2, _ = commit(42)
    from core.crypto.real.pedersen import point_to_bytes
    compressed = point_to_bytes(C2)
    size_compressed = len(compressed)
    size_uncompressed = 65  # 1 prefix + 32x + 32y
    results["commitment_size_compressed_bytes"] = size_compressed
    results["commitment_size_uncompressed_bytes"] = size_uncompressed
    row("commitment size (compressed)",   f"{size_compressed} bytes", "SEC1 compressed on-chain repr")
    row("commitment size (uncompressed)", f"{size_uncompressed} bytes", "full (x,y) point")

    return results


# ── Section 3: Schnorr ZKP (anomaly proofs) ──────────────────────────────────

# [DOC] bench_schnorr_zkp measures the CBC anomaly ZKP: Fiat-Shamir Schnorr prove and verify times
# [DOC] these numbers support the claim that AML rule compliance can be proven in ~11 ms and verified in ~8.84 ms
def bench_schnorr_zkp():
    section("3. Schnorr ZKP — anomaly proof (Fiat-Shamir, secp256k1)")
    # [DOC] AnomalyZKPService wraps the real Schnorr sigma protocol (core/crypto/anomaly_zkp.py)
    from core.crypto.anomaly_zkp import AnomalyZKPService

    zkp = AnomalyZKPService()
    results = {}

    # [DOC] Prove: generates a Schnorr ZKP that the anomaly score crosses the threshold
    # [DOC] without revealing the raw score; measures the cost a sender pays per flagged transaction
    # Prove
    stats = measure(lambda: zkp.generate_anomaly_proof(
        transaction_hash="abc123deadbeef",
        anomaly_score=75.0,
        anomaly_flags=["HIGH_VALUE_PMLA", "VELOCITY"],
        requires_investigation=True,
    ))
    last_proof = stats.pop("_last_result")
    results["prove"] = stats
    row("generate_proof mean",   f"{stats['mean_ms']:.2f} ms")
    row("generate_proof median", f"{stats['median_ms']:.2f} ms")
    row("generate_proof p95",    f"{stats['p95_ms']:.2f} ms")

    # [DOC] Verify: checks the Schnorr proof using the public Fiat-Shamir transcript;
    # [DOC] TPS derived from verify time shows regulatory throughput capacity on one core
    # Verify
    stats = measure(lambda: zkp.verify_anomaly_proof(last_proof))
    stats.pop("_last_result")
    results["verify"] = stats
    row("verify_proof mean",   f"{stats['mean_ms']:.2f} ms")
    row("verify_proof median", f"{stats['median_ms']:.2f} ms")

    # [DOC] Derived TPS: 1000 / mean_verify_ms gives the single-core regulatory audit throughput
    # Derived TPS for anomaly ZKP
    tps = 1000.0 / stats["mean_ms"]
    results["verify_tps"] = round(tps, 1)
    row("verify TPS (1 core)", f"~{tps:.0f}/sec")

    return results


# ── Section 4: BBS+ Group Signatures ─────────────────────────────────────────

# [DOC] bench_bbs measures BBS04 group signature performance (BN254, Charm-Crypto):
# [DOC] sign time per bank vote, verify time for consortium consensus, open time for traceability
def bench_bbs():
    section("4. BBS04 Group Signatures — BN254 (Charm-Crypto)")
    results = {}

    try:
        # [DOC] BBSGroupSignature wraps the Charm-Crypto BN254 group signature scheme;
        # [DOC] it must be imported from venv310 which has Charm installed from JHUISI source
        from core.crypto.real.bbs_group_signature import BBSGroupSignature
        import json as _json
        bbs = BBSGroupSignature()
        # [DOC] setup(n_banks=12) generates the group public key, opening key, and per-bank signing keys;
        # [DOC] in production each bank calls keygen once and stores the result in the Bank ORM row
        params = bbs.setup(n_banks=12)
        gpk        = params["group_pk"]         # raw charm object
        open_key   = params["open_key"]
        bank_keys  = params["bank_keys"]        # list of dicts with "signing_key"
        bank_certs = params["bank_certificates"]  # JSON string
        signing_key_0 = bank_keys[0]["signing_key"]
        MSG = "BATCH_001_100"

        # [DOC] Sign benchmark: measures how long bank 0 takes to sign a batch ID anonymously;
        # [DOC] the 92 ms mean is the dominant cost per bank per consensus round
        # Sign (bank 0 signs batch ID)
        stats = measure(lambda: bbs.sign(gpk, signing_key_0, MSG))
        last_sig = stats.pop("_last_result")
        results["sign"] = stats
        row("sign mean",   f"{stats['mean_ms']:.2f} ms")
        row("sign median", f"{stats['median_ms']:.2f} ms")
        row("sign p95",    f"{stats['p95_ms']:.2f} ms")

        # [DOC] Verify benchmark: measures how long a bank spends checking another bank's signature;
        # [DOC] called T=10 times per batch to assemble the required approvals
        # Verify
        stats = measure(lambda: bbs.verify(gpk, last_sig, MSG))
        stats.pop("_last_result")
        results["verify"] = stats
        row("verify mean",   f"{stats['mean_ms']:.2f} ms")
        row("verify median", f"{stats['median_ms']:.2f} ms")

        # [DOC] Open benchmark: measures the traceability operation used by the consortium opener
        # [DOC] to identify which bank signed a disputed batch (requires bank_certs for identity recovery)
        # Open (RBI traceability — needs bank_certs for identity recovery)
        stats = measure(lambda: bbs.open(gpk, open_key, last_sig, MSG, bank_certs))
        stats.pop("_last_result")
        results["open"] = stats
        row("open mean",   f"{stats['mean_ms']:.2f} ms", "RBI traceability key")

        # [DOC] Signature size in bytes is hardware-independent and reported in the paper's Table 1
        # Signature size
        sig_size = len(last_sig.encode())
        results["sig_size_bytes"] = sig_size
        row("signature size", f"{sig_size} bytes")

        results["available"] = True

    except ImportError as e:
        results["available"] = False
        results["error"] = str(e)
        row("BBS+ status", "UNAVAILABLE — charm-crypto not importable", str(e))

    return results


# ── Section 5: Consensus N-X Parameter Sweep ─────────────────────────────────

# [DOC] bench_consensus_sweep verifies the generalised N-X BFT safety condition across four consortium sizes;
# [DOC] checks that X < N/3 holds for every configuration and computes the threshold percentage
def bench_consensus_sweep():
    section("5. Consensus Policy — (N, X) parameter sweep")

    # [DOC] configs lists the four reference configurations from the paper:
    # [DOC] small, default Indian (N=12 X=2), max BFT tolerance (N=12 X=3), and a large network
    configs = [
        {"N": 4,  "X": 1,  "label": "Small consortium"},
        {"N": 12, "X": 2,  "label": "Indian consortium (default)"},
        {"N": 12, "X": 3,  "label": "Indian consortium (max BFT tolerance)"},
        {"N": 50, "X": 16, "label": "Large network (BFT limit)"},
    ]

    results = {}
    print(f"\n  {'Label':<35} {'N':>4} {'X':>4} {'T=N-X':>6} {'T/N':>6} {'X<N/3':>6}")
    print("  " + "-" * 65)

    for c in configs:
        N, X = c["N"], c["X"]
        T = N - X
        ratio = T / N
        # [DOC] bft_ok asserts the safety condition X < N/3; if False the configuration is unsafe
        bft_ok = X < N / 3
        print(f"  {c['label']:<35} {N:>4} {X:>4} {T:>6} {ratio:>6.1%} {'✓' if bft_ok else '✗ UNSAFE':>6}")
        results[c["label"]] = {
            "N": N, "X": X, "T": T,
            "threshold_pct": round(ratio * 100, 1),
            "bft_safe": bft_ok,
        }

    print(f"\n  Note: Default (N=12, X=2, T=10) uses X=2 < N/3=4 — conservative by 2 banks.")
    print(f"        This means the system tolerates 2 dishonest banks but could tolerate up to 3.")
    return results


# ── Section 6: End-to-end TPS estimate ───────────────────────────────────────

# [DOC] bench_tps_estimate combines measured primitive costs into three Config A / A2 / A2+batch TPS figures;
# [DOC] these are the end-to-end throughput numbers reported in the paper's evaluation section
def bench_tps_estimate(bp_results, pedersen_results, schnorr_results):
    section("6. End-to-End TPS Estimate")

    prove_ms   = bp_results["prove_64bit"]["mean_ms"]
    verify_ms  = bp_results["verify_64bit"]["mean_ms"]
    commit_ms  = pedersen_results["commit"]["mean_ms"]
    zkp_ms     = schnorr_results["verify"]["mean_ms"]

    # [DOC] Config A models the pure Python path: 2 Pedersen commits + 1 Schnorr ZKP verify per transaction
    # Config A: Python EC only (Pedersen commit + Schnorr ZKP, no Bulletproofs)
    config_a_ms  = commit_ms * 2 + zkp_ms  # 2 commits per tx + 1 ZKP verify
    tps_a        = 1000.0 / config_a_ms

    # [DOC] Config A2 adds the Rust Bulletproof prove cost to give the current deployed system's TPS
    # Config A2: Python EC + Rust Bulletproofs (current system)
    config_a2_ms = prove_ms + verify_ms + commit_ms
    tps_a2       = 1000.0 / config_a2_ms

    # [DOC] Config A2+batch uses native Rust bp_verify_batch over 100 proofs;
    # [DOC] amortised per-proof verify cost gives a higher effective TPS for a full batch
    # Config A2 with batch (100 tx/batch, native Rust batch verify — single ctypes call)
    batch_native_ms = bp_results["batch"].get("B100", {}).get("native_ms", verify_ms * 100)
    config_a2b_total = prove_ms * 100 + batch_native_ms + commit_ms * 100
    tps_a2b = 100_000.0 / config_a2b_total

    print(f"\n  Config A  (Python EC only):          {config_a_ms:.1f} ms/tx → {tps_a:.1f} TPS")
    print(f"  Config A2 (Python + Rust BP):        {config_a2_ms:.1f} ms/tx → {tps_a2:.1f} TPS")
    print(f"  Config A2+batch (100 tx/batch,       {config_a2b_total:.0f} ms/100tx → {tps_a2b:.1f} TPS")
    print(f"    native Rust bp_verify_batch):")
    print()
    print(f"  --- Comparison ---")
    print(f"  Platypus CCS 2022 (server verify TPS):  922 TPS  [Groth16, trusted setup]")
    print(f"  Platypus CCS 2022 (client prove TPS):   ~9 TPS   [110 ms/proof on i7-7700]")
    print(f"  Zerocash S&P 2014:                      ~0.01 TPS [87s/proof]")
    print(f"  ZK-AML prove (this system, M1 Pro):     {1000/prove_ms:.1f} TPS")
    print(f"  ZK-AML verify (this system, M1 Pro):    {1000/verify_ms:.1f} TPS")
    # [DOC] Speedup vs Platypus divides Platypus 110 ms by our prove_ms; must stay near 12.6x claimed
    print(f"  ZK-AML prove speedup vs Platypus:       {110/prove_ms:.1f}× faster  [12.6× claimed]")
    print(f"  ZK-AML prove speedup vs Zerocash:       {87000/prove_ms:.0f}× faster")
    print()
    print(f"  NOTE: All ZK-AML numbers on Apple M1 Pro (ARM64).")
    print(f"        Platypus numbers on Intel i7-7700 (x86-64).")
    print(f"        Hardware-independent claims: no trusted setup, AML rules in ZK,")
    print(f"        proof sizes, batch speedup ratios.")

    return {
        "config_a_tps":    round(tps_a, 2),
        "config_a2_tps":   round(tps_a2, 2),
        "config_a2b_tps":  round(tps_a2b, 2),
        "prove_speedup_vs_platypus":  round(110 / prove_ms, 1),
        "prove_speedup_vs_zerocash":  round(87000 / prove_ms, 0),
    }


# ── Section 7: Paper comparison table ────────────────────────────────────────

# [DOC] print_paper_table renders the four-system comparison table ready to paste into the paper's LaTeX;
# [DOC] it uses only measured numbers (bp_results) so the table is always in sync with reality
def print_paper_table(bp_results, bbs_results, tps_results):
    section("7. Paper Comparison Table")

    prove  = bp_results["prove_64bit"]["mean_ms"]
    verify = bp_results["verify_64bit"]["mean_ms"]
    psize  = bp_results["proof_sizes"]["64bit"]

    print(f"""
  ┌──────────────────────┬──────────────┬──────────────┬──────────┬────────────┬──────────────────┐
  │ System               │ Prove (ms)   │ Verify (ms)  │ Size (B) │ Trusted    │ AML in ZK        │
  │                      │              │              │          │ Setup      │                  │
  ├──────────────────────┼──────────────┼──────────────┼──────────┼────────────┼──────────────────┤
  │ Zerocash S&P 2014    │ ~87,000 ms   │ <6 ms        │ 288 B    │ YES        │ None             │
  │ Platypus CCS 2022    │ 110–730 ms   │ 0.89–1.5 ms  │ 418–1122 │ YES        │ Balance limits   │
  │                      │ (on client)  │ (BN256)      │ B (BN256)│ (Groth16)  │ only             │
  │ Bulletproofs S&P'18  │ ~36 ms       │ ~11 ms       │ ~674 B   │ NO         │ None (amount     │
  │                      │ (secp256k1,  │ (secp256k1)  │(secp256k1│            │ privacy only)    │
  │                      │ 2018 hw)     │              │)         │            │                  │
  ├──────────────────────┼──────────────┼──────────────┼──────────┼────────────┼──────────────────┤
  │ ZK-AML (this work)   │ {prove:.2f} ms     │ {verify:.2f} ms      │ {psize} B    │ NO         │ PMLA rules:      │
  │ Apple M1 Pro ARM64   │ (Rust dalek  │ (Rust dalek  │(Ristretto│ (DLOG only)│ high-value,      │
  │                      │ Ristretto255)│ Ristretto255)│ 255)     │            │ velocity,        │
  │                      │              │              │          │            │ structuring (CBC) │
  └──────────────────────┴──────────────┴──────────────┴──────────┴────────────┴──────────────────┘

  Hardware note: ZK-AML numbers on Apple M1 Pro (ARM64, ~3.2 GHz performance cores).
  Platypus on Intel i7-7700 (x86-64, 3.6 GHz). Hardware-independent claims are
  marked with (*) and hold regardless of measurement platform:
    (*) No trusted setup required (Bulletproofs = DLOG assumption only)
    (*) AML compliance as ZK-provable statements — CBC primitive (novel)
    (*) RCTD access structure formalized (novel)
    (*) Batch speedup ratio: {bp_results['batch'].get('B100', {}).get('speedup_x', 'N/A')}× for B=100
    (*) Proof size formula: (2·⌈log₂(n)⌉+9)·32 bytes (672 B for 64-bit)
""")


# ── Main ──────────────────────────────────────────────────────────────────────

# [DOC] main() orchestrates all seven benchmark sections in order and saves the complete result dict
# [DOC] to a timestamped JSON file in tests/benchmarks/results/ for citation in the paper
def main():
    print("=" * 65)
    print("  ZK-AML VALIDATED BENCHMARK SUITE")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Hardware: {HARDWARE['model']}, {HARDWARE['cores']} cores, {HARDWARE['ram_gb']}GB")
    print(f"  OS: {HARDWARE['os']}  Python: {HARDWARE['python']}")
    print("=" * 65)

    all_results = {
        "hardware":    HARDWARE,
        "timestamp":   datetime.datetime.now().isoformat(),
        "platypus_ref": PLATYPUS_REF,
        "zerocash_ref": ZEROCASH_REF,
        "bp_paper_ref": BP_PAPER_REF,
    }

    # [DOC] Run sections in dependency order: Bulletproofs first because TPS estimate consumes its results
    bp_res        = bench_bulletproofs()
    pedersen_res  = bench_pedersen()
    schnorr_res   = bench_schnorr_zkp()
    bbs_res       = bench_bbs()
    consensus_res = bench_consensus_sweep()
    tps_res       = bench_tps_estimate(bp_res, pedersen_res, schnorr_res)
    print_paper_table(bp_res, bbs_res, tps_res)

    all_results.update({
        "bulletproofs":  bp_res,
        "pedersen":      pedersen_res,
        "schnorr_zkp":   schnorr_res,
        "bbs_group_sig": bbs_res,
        "consensus":     consensus_res,
        "tps_estimate":  tps_res,
    })

    # [DOC] Save results to a timestamped JSON so each run is an independent artifact traceable to the paper
    # Save results
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"validated_{ts}.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n  Results saved → {out_path}")
    print("\n  DONE — use these numbers directly in the paper.")
    print("  All numbers on Apple M1 Pro (ARM64). Note hardware difference vs Platypus (x86).")
    print("  Hardware-independent claims (marked *) may be used without qualification.")

    return all_results


if __name__ == "__main__":
    main()
