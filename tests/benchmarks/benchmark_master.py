"""
ZK-AML Master Benchmark Suite
===============================
Single script that benchmarks EVERY crypto primitive, ZK circuit, and anomaly
detection scenario — then saves a timestamped JSON and prints a paper-ready
summary table.

Sections
--------
 0. System information
 1. Bulletproofs (Rust dalek v4, Ristretto255)   — prove/verify/batch
 2. Pedersen Commitments (py_ecc secp256k1)
 3. Schnorr ZKP (anomaly proof, Fiat-Shamir)
 4. BBS04 Group Signatures (BN254, Charm-Crypto)
 5. Simple Range Proof (Schnorr OR-proofs, CDS 1994)  ← NEW
 6. R_velocity ZK Circuit (Gap 2)                     ← NEW
 7. R_structuring ZK Circuit (Gap 3)                  ← NEW
 8. Anomaly Detection Engine (end-to-end, mock DB)    ← NEW
 9. Consensus N-X Policy Sweep
10. TPS Estimate (Config A / A2 / A2+batch)
11. Breaking Point Analysis (concurrent ZK load)      ← NEW
12. Paper Comparison Table

Methodology
-----------
- Crypto primitives: N_TRIALS=100, first 5 discarded (warm-up).
- Anomaly engine: N_TRIALS_ENGINE=20 (each call generates ZK proofs).
- Breaking point: ThreadPoolExecutor with load=[1,5,10,25,50] concurrent workers.
  Note: pure-Python OR-proofs are GIL-bound — threads serialise, showing honest
  single-process throughput ceiling rather than false parallel speedup.
- Results saved: tests/benchmarks/results/master_<YYYYMMDD_HHMMSS>.json
"""

# [DOC] Standard library imports used throughout the benchmark harness.
import sys
import os
import time
import json
import statistics
import datetime
import multiprocessing
import concurrent.futures
import platform

# [DOC] Path setup so project modules resolve when running as python3 -m tests.benchmarks.benchmark_master.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

# [DOC] Inject venv310 site-packages so charm-crypto and py_ecc resolve without activating the venv manually.
VENV_SITE = os.path.join(ROOT, "venv310", "lib", "python3.10", "site-packages")
if os.path.isdir(VENV_SITE) and VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

# ── Constants ──────────────────────────────────────────────────────────────────
# [DOC] N_TRIALS=100 gives statistically stable estimates; N_WARMUP=5 discards JIT/cache warm-up noise.
N_TRIALS        = 100
N_WARMUP        = 5
# [DOC] N_TRIALS_ENGINE=20: anomaly engine is slower (generates ZK proofs per call).
N_TRIALS_ENGINE = 20
BATCH_SIZES     = [1, 10, 25, 50, 100]
N_WORKERS       = min(8, multiprocessing.cpu_count())
# [DOC] BP_SIZES: concurrent load levels for the breaking-point analysis.
BP_SIZES        = [1, 5, 10, 25, 50]
# [DOC] TX_HASH: fixed 64-char hex string used as the binding context in all ZK proofs.
TX_HASH         = "0xdeadbeef" * 8

# [DOC] Reference benchmark data from published papers — used in the comparison table.
PLATYPUS_REF = {
    "hardware": "Intel Core i7-7700 @ 3.60 GHz, 4 cores, 16 GB",
    "proof_gen_ms": 110, "verify_ms": 0.89, "proof_size_bytes": 418,
    "tps_server": 922, "trusted_setup": True,
    "aml_in_zk": "Balance limits only",
}
ZEROCASH_REF = {
    "hardware": "Intel Core i7 (2014)",
    "proof_gen_ms": 87000, "verify_ms": 6,
    "proof_size_bytes": 288, "trusted_setup": True, "aml_in_zk": "None",
}
BP_PAPER_REF = {
    "hardware": "secp256k1, 2018 hardware",
    "proof_gen_ms": 36, "verify_ms": 11,
    "proof_size_bytes": 674, "batch_marginal_ms": 0.25, "trusted_setup": False,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hardware_info():
    """Collect hardware and software metadata for the JSON header."""
    return {
        "model":        platform.machine(),
        "processor":    platform.processor() or platform.machine(),
        "cpu_count":    multiprocessing.cpu_count(),
        "os":           f"{platform.system()} {platform.release()}",
        "python":       f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


# [DOC] measure() runs fn() (n+warmup) times, discards the first warmup results,
# [DOC] and returns a dict with mean/median/stdev/p95/p99/min/max in milliseconds.
def measure(fn, n=N_TRIALS, warmup=N_WARMUP):
    """Time fn() n+warmup times; discard warmup; return stats dict (ms)."""
    times = []
    result = None
    for i in range(n + warmup):
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
        "p95_ms":    round(sorted_t[int(0.95 * n)], 3),
        "p99_ms":    round(sorted_t[int(0.99 * n)], 3),
        "min_ms":    round(sorted_t[0], 3),
        "max_ms":    round(sorted_t[-1], 3),
        "n_trials":  n,
        "_last":     result,
    }


def section(n, title):
    print(f"\n{'='*70}")
    print(f"  SECTION {n}: {title}")
    print('='*70)


def row(label, val, note=""):
    note_str = f"  [{note}]" if note else ""
    print(f"  {label:<50} {val}{note_str}")


# ── Section 1: Bulletproofs ────────────────────────────────────────────────────

def bench_bulletproofs():
    section(1, "Bulletproofs — Rust dalek v4, Ristretto255")
    from core.crypto.real.bulletproofs_wrapper import (
        create_range_proof, verify_range_proof,
        verify_batch_parallel, verify_batch_native, proof_size_bytes,
    )
    results = {}

    # 1a: Prove 64-bit
    print("\n  [1a] Prove 64-bit")
    s = measure(lambda: create_range_proof(1_000_000, bit_length=64))
    last_proof = s.pop("_last")
    results["prove_64bit"] = s
    row("prove mean",   f"{s['mean_ms']:.2f} ms")
    row("prove p95",    f"{s['p95_ms']:.2f} ms")
    row("prove stdev",  f"{s['stdev_ms']:.2f} ms")

    # 1b: Verify 64-bit
    print("\n  [1b] Verify 64-bit")
    s = measure(lambda: verify_range_proof(last_proof))
    s.pop("_last")
    results["verify_64bit"] = s
    row("verify mean",   f"{s['mean_ms']:.2f} ms")
    row("verify p95",    f"{s['p95_ms']:.2f} ms")

    # 1c: Proof sizes (hardware-independent)
    print("\n  [1c] Proof sizes (bytes, hardware-independent)")
    results["proof_sizes"] = {}
    for bits in [8, 16, 32, 64]:
        pf = create_range_proof((1 << bits) - 1, bit_length=bits)
        actual = len(bytes.fromhex(pf["proof"]))
        results["proof_sizes"][f"{bits}bit"] = actual
        row(f"  {bits}-bit", f"{actual} bytes", f"formula={proof_size_bytes(bits)} B")

    # 1d: Batch speedup (3 strategies)
    print(f"\n  [1d] Batch verify speedup (N_WORKERS={N_WORKERS})")
    results["batch"] = {}
    max_b = max(BATCH_SIZES)
    print(f"       Generating {max_b} proofs...", end="", flush=True)
    pool_proofs = [create_range_proof(i * 100 + 1, bit_length=64) for i in range(max_b)]
    print(" done")

    import multiprocessing as _mp
    _ctx = _mp.get_context("fork")
    _pool = _ctx.Pool(processes=N_WORKERS)
    _pool.map(verify_range_proof, pool_proofs[:N_WORKERS])  # pre-warm
    print(f"  {'B':>4}  {'seq_ms':>8}  {'native_ms':>10}  {'par_ms':>8}  {'nat_x':>6}  {'par_x':>6}")
    print("  " + "-" * 55)
    for B in BATCH_SIZES:
        bp = pool_proofs[:B]
        t0 = time.perf_counter(); [verify_range_proof(p) for p in bp]; seq_ms = (time.perf_counter()-t0)*1000
        ok_n, nat_ms = verify_batch_native(bp, bit_length=64)
        t0 = time.perf_counter(); par_ok = _pool.map(verify_range_proof, bp); par_ms = (time.perf_counter()-t0)*1000
        nx = seq_ms / nat_ms if nat_ms > 0 else 0
        px = seq_ms / par_ms if par_ms > 0 else 0
        results["batch"][f"B{B}"] = {
            "sequential_ms": round(seq_ms, 2), "native_ms": round(nat_ms, 2),
            "parallel_ms": round(par_ms, 2), "native_speedup": round(nx, 2),
            "parallel_speedup": round(px, 2), "per_proof_native_ms": round(nat_ms/B, 3),
            "all_valid": ok_n and all(par_ok),
            "speedup_x": round(nx, 2), "per_proof_ms": round(nat_ms/B, 3),
        }
        print(f"  {B:>4}  {seq_ms:>8.1f}  {nat_ms:>10.1f}  {par_ms:>8.1f}  {nx:>5.1f}×  {px:>5.1f}×")
    _pool.terminate(); _pool.join()
    return results


# ── Section 2: Pedersen ────────────────────────────────────────────────────────

def bench_pedersen():
    section(2, "Pedersen Commitments — py_ecc secp256k1")
    from core.crypto.real.pedersen import commit, verify_opening, point_to_bytes
    results = {}
    s = measure(lambda: commit(1_000_000))
    C, r = s.pop("_last")
    results["commit"] = s
    row("commit mean",  f"{s['mean_ms']:.2f} ms"); row("commit p95", f"{s['p95_ms']:.2f} ms")
    s = measure(lambda: verify_opening(C, 1_000_000, r))
    s.pop("_last")
    results["verify_opening"] = s
    row("verify_opening mean", f"{s['mean_ms']:.2f} ms")
    C2, _ = commit(42)
    sz = len(point_to_bytes(C2))
    results["commitment_size_compressed_bytes"] = sz
    results["commitment_size_uncompressed_bytes"] = 65
    row("compressed size", f"{sz} bytes"); row("uncompressed size", "65 bytes")
    return results


# ── Section 3: Schnorr ZKP ────────────────────────────────────────────────────

def bench_schnorr_zkp():
    section(3, "Schnorr ZKP — anomaly proof (Fiat-Shamir, secp256k1)")
    from core.crypto.anomaly_zkp import AnomalyZKPService
    zkp = AnomalyZKPService()
    results = {}
    s = measure(lambda: zkp.generate_anomaly_proof(
        transaction_hash="abc123deadbeef", anomaly_score=75.0,
        anomaly_flags=["HIGH_VALUE_PMLA", "VELOCITY"], requires_investigation=True,
    ))
    last_proof = s.pop("_last")
    results["prove"] = s
    row("prove mean", f"{s['mean_ms']:.2f} ms"); row("prove p95", f"{s['p95_ms']:.2f} ms")
    s = measure(lambda: zkp.verify_anomaly_proof(last_proof))
    s.pop("_last")
    results["verify"] = s
    tps = round(1000.0 / s["mean_ms"], 1)
    results["verify_tps"] = tps
    row("verify mean", f"{s['mean_ms']:.2f} ms"); row("verify TPS (1 core)", f"~{tps}/sec")
    return results


# ── Section 4: BBS04 ──────────────────────────────────────────────────────────

def bench_bbs():
    section(4, "BBS04 Group Signatures — BN254 (Charm-Crypto)")
    results = {}
    try:
        from core.crypto.real.bbs_group_signature import BBSGroupSignature
        bbs = BBSGroupSignature()
        params = bbs.setup(n_banks=12)
        gpk = params["group_pk"]; open_key = params["open_key"]
        sk0 = params["bank_keys"][0]["signing_key"]
        certs = params["bank_certificates"]
        MSG = "BATCH_001_100"
        s = measure(lambda: bbs.sign(gpk, sk0, MSG))
        sig = s.pop("_last")
        results["sign"] = s
        row("sign mean", f"{s['mean_ms']:.2f} ms"); row("sign p95", f"{s['p95_ms']:.2f} ms")
        s = measure(lambda: bbs.verify(gpk, sig, MSG))
        s.pop("_last")
        results["verify"] = s
        row("verify mean", f"{s['mean_ms']:.2f} ms")
        s = measure(lambda: bbs.open(gpk, open_key, sig, MSG, certs))
        s.pop("_last")
        results["open"] = s
        row("open mean", f"{s['mean_ms']:.2f} ms")
        sz = len(sig.encode())
        results["sig_size_bytes"] = sz; results["available"] = True
        row("signature size", f"{sz} bytes")
    except Exception as e:
        results["available"] = False; results["error"] = str(e)
        row("BBS+ status", f"UNAVAILABLE — {e}")
    return results


# ── Section 5: Simple Range Proof (OR-proofs) ─────────────────────────────────

def bench_simple_range_proof():
    section(5, "Simple Range Proof — Schnorr OR-proofs (CDS 1994), secp256k1")
    from core.crypto.real.simple_range_proof import create_range_proof, verify_range_proof
    results = {}
    # [DOC] Bit widths chosen to cover every range used in velocity_zkp and structuring_zkp:
    # [DOC]   3-bit  → velocity not-suspicious (T=5, 3-bit internal)
    # [DOC]   14-bit → velocity suspicious (MAX_COUNT-T+1 ≈ 9996, 14-bit)
    # [DOC]   16-bit → structuring STRUCTURING branch (width=50,000, 16-bit)
    # [DOC]   20-bit → structuring BELOW branch (low=950,000, 20-bit)
    # [DOC]   24-bit → structuring ABOVE branch (9,000,001, 24-bit)
    # Using slightly rounded values for cleaner display:
    configs = [
        ("8bit",  100,        256,       "baseline"),
        ("14bit", 100,        10_000,    "velocity suspicious branch"),
        ("16bit", 49_999,     50_000,    "structuring STRUCTURING branch"),
        ("20bit", 500_000,    950_001,   "structuring BELOW branch"),
        ("24bit", 500_000,    9_000_001, "structuring ABOVE branch"),
    ]
    ctx = "bench_context_" + "a" * 16
    print(f"\n  {'Width':<8} {'prove_mean':>11} {'prove_p95':>10} {'verify_mean':>12} {'verify_p95':>10}")
    print("  " + "-" * 58)
    for key, val, mx, note in configs:
        sp = measure(lambda v=val, m=mx: create_range_proof(v, m, ctx))
        proof = sp.pop("_last")
        sv = measure(lambda p=proof: verify_range_proof(p))
        sv.pop("_last")
        results[key] = {"prove": sp, "verify": sv, "note": note}
        print(f"  {key:<8} {sp['mean_ms']:>10.1f}ms {sp['p95_ms']:>9.1f}ms "
              f"{sv['mean_ms']:>11.1f}ms {sv['p95_ms']:>9.1f}ms   [{note}]")
    return results


# ── Section 6: R_velocity ZK Circuit ─────────────────────────────────────────

def bench_velocity_zkp():
    section(6, "R_velocity ZK Circuit — Pedersen range proof over tx count (Gap 2)")
    from core.crypto.real.velocity_zkp import prove_velocity, verify_velocity
    results = {}
    # [DOC] Four scenarios covering both classification branches and all three AML windows.
    scenarios = [
        ("not_suspicious_1h",  3,  5,  "1h",  False, "count=3 < T=5"),
        ("suspicious_1h",      7,  5,  "1h",  True,  "count=7 ≥ T=5"),
        ("not_suspicious_24h", 9,  10, "24h", False, "count=9 < T=10"),
        ("suspicious_7d",      60, 50, "7d",  True,  "count=60 ≥ T=50"),
    ]
    print(f"\n  {'Scenario':<22} {'is_susp':>8} {'prove_mean':>11} {'verify_mean':>12}")
    print("  " + "-" * 60)
    for key, count, thresh, window, expected, note in scenarios:
        sp = measure(lambda c=count, t=thresh, w=window:
                     prove_velocity(c, t, w, TX_HASH))
        proof = sp.pop("_last")
        # correctness check
        assert proof["is_suspicious"] == expected, \
            f"Correctness fail: {key} expected {expected}"
        assert verify_velocity(proof), f"Verification fail: {key}"
        sv = measure(lambda p=proof: verify_velocity(p))
        sv.pop("_last")
        results[key] = {
            "prove": sp, "verify": sv,
            "is_suspicious": expected, "note": note,
        }
        print(f"  {key:<22} {str(expected):>8} {sp['mean_ms']:>10.1f}ms {sv['mean_ms']:>11.1f}ms   [{note}]")
    print("\n  All 4 velocity proofs verified correctly.")
    return results


# ── Section 7: R_structuring ZK Circuit ──────────────────────────────────────

def bench_structuring_zkp():
    section(7, "R_structuring ZK Circuit — 3-branch Pedersen range proof (Gap 3)")
    from core.crypto.real.structuring_zkp import prove_structuring, verify_structuring
    # Structuring range in paise: LOW=950,000 paise (₹9,500) | HIGH=1,000,000 paise (₹10,000)
    # These are prototype values; production scales to actual PMLA range (₹9.5L–₹10L = 95M–100M paise)
    LOW, HIGH = 950_000, 1_000_000
    results = {}
    scenarios = [
        ("BELOW",       500_000,   False, "amount=₹5,000 (500,000 paise) < LOW=₹9,500"),
        ("STRUCTURING", 960_000,   True,  "₹9,500 ≤ amount=₹9,600 (960,000 paise) < ₹10,000"),
        ("ABOVE",       1_500_000, False, "amount=₹15,000 (1,500,000 paise) ≥ HIGH=₹10,000"),
    ]
    print(f"\n  {'Branch':<14} {'is_struct':>10} {'prove_mean':>11} {'prove_p95':>10} {'verify_mean':>12}")
    print("  " + "-" * 65)
    for branch, amount, expected, note in scenarios:
        sp = measure(lambda a=amount: prove_structuring(a, LOW, HIGH, TX_HASH))
        proof = sp.pop("_last")
        assert proof["is_structuring"] == expected, f"Correctness fail: {branch}"
        assert proof["branch"] == branch, f"Branch mismatch: {branch}"
        assert verify_structuring(proof), f"Verification fail: {branch}"
        sv = measure(lambda p=proof: verify_structuring(p))
        sv.pop("_last")
        results[branch] = {
            "prove": sp, "verify": sv,
            "is_structuring": expected, "branch": branch, "note": note,
        }
        print(f"  {branch:<14} {str(expected):>10} {sp['mean_ms']:>10.1f}ms "
              f"{sp['p95_ms']:>9.1f}ms {sv['mean_ms']:>11.1f}ms   [{note}]")
    print("\n  All 3 structuring branches verified correctly.")
    return results


# ── Section 8: Anomaly Detection Engine ───────────────────────────────────────

def bench_anomaly_engine():
    section(8, "Anomaly Detection Engine — end-to-end (mock DB, persist=False)")
    from unittest.mock import MagicMock, PropertyMock
    from decimal import Decimal
    from core.services.anomaly_detection_engine import AnomalyDetectionEngine

    results = {}

    def make_engine(velocity_count: int):
        """Build an engine backed by a mock DB that returns velocity_count for all count() calls."""
        mock_db = MagicMock()
        # [DOC] Chain: db.query().filter().count() → velocity_count
        mock_db.query.return_value.filter.return_value.count.return_value = velocity_count
        # [DOC] Chain: db.query().filter().first() → None (no structuring history)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = None
        return AnomalyDetectionEngine(mock_db)

    def make_tx(amount_paise: int, tx_hash: str = TX_HASH):
        """Build a minimal mock Transaction object. Amounts are in paise (100 paise = ₹1)."""
        tx = MagicMock()
        tx.amount = Decimal(amount_paise)
        tx.sender_idx = "IDX_BENCH_SENDER_" + "a" * 20
        tx.receiver_idx = "IDX_BENCH_RECV_" + "b" * 20
        tx.sender_account_id = 1
        tx.transaction_hash = tx_hash
        from datetime import datetime, timezone
        tx.created_at = datetime.now(timezone.utc)
        return tx

    scenarios = [
        # (name,           amount_paise,  velocity_count, desc)
        # Prototype thresholds (paise): PMLA=1,000,000(₹10,000) | T1=5,000,000(₹50,000) | T2=10,000,000(₹1,00,000)
        ("clean_tx",      100_000,        0,  "₹1,000 (100,000 paise) — no flags expected"),
        ("high_value",    7_000_000,      0,  "₹70,000 (7,000,000 paise) — >= T1 threshold, score=25"),
        ("high_velocity", 100_000,        12, "₹1,000 + 12 txns/1h — VELOCITY, score=30"),
        # full_flag: ₹1,10,000 (>= T2=₹1,00,000) → 40pts + VELOCITY 12/1h → 30pts = 70 >= 65 → requires_investigation=True
        ("full_flag",     11_000_000,     12, "₹1,10,000 (11,000,000 paise) + velocity — T2+VELOCITY, score=70"),
    ]

    print(f"\n  {'Scenario':<18} {'mean_ms':>9} {'p95_ms':>8} {'v_proofs':>9} {'s_proofs':>9}  flags")
    print("  " + "-" * 80)

    for name, amount, vel_count, desc in scenarios:
        engine = make_engine(vel_count)
        tx = make_tx(amount)
        s = measure(
            lambda e=engine, t=tx: e.evaluate_transaction(t, persist=False),
            n=N_TRIALS_ENGINE, warmup=2,
        )
        last = s.pop("_last")
        vp = len(last.get("velocity_proofs", []))
        sp2 = len(last.get("structuring_proofs", []))
        flags = last.get("flags", [])
        results[name] = {
            "mean_ms": s["mean_ms"], "median_ms": s["median_ms"],
            "p95_ms": s["p95_ms"], "stdev_ms": s["stdev_ms"],
            "n_trials": N_TRIALS_ENGINE,
            "velocity_proofs": vp, "structuring_proofs": sp2,
            "flags": flags,
            "requires_investigation": last.get("requires_investigation", False),
            "score": last.get("score", 0),
            "note": desc,
        }
        flag_str = ",".join(flags[:2]) + ("..." if len(flags) > 2 else "")
        print(f"  {name:<18} {s['mean_ms']:>8.1f}ms {s['p95_ms']:>7.1f}ms "
              f"{vp:>9} {sp2:>9}  {flag_str}")

    return results


# ── Section 9: Consensus N-X Sweep ───────────────────────────────────────────

def bench_consensus_sweep():
    section(9, "Consensus Policy — (N, X) BFT parameter sweep")
    configs = [
        {"N": 4,  "X": 1,  "label": "Small consortium"},
        {"N": 12, "X": 2,  "label": "Indian consortium (default)"},
        {"N": 12, "X": 3,  "label": "Indian consortium (max BFT tolerance)"},
        {"N": 50, "X": 16, "label": "Large network (BFT limit)"},
    ]
    results = {}
    print(f"\n  {'Label':<38} {'N':>4} {'X':>4} {'T':>4} {'T%':>6} {'BFT':>5}")
    print("  " + "-" * 65)
    for c in configs:
        N, X = c["N"], c["X"]
        T = N - X; pct = T / N; ok = X < N / 3
        print(f"  {c['label']:<38} {N:>4} {X:>4} {T:>4} {pct:>5.1%} {'✓' if ok else '✗':>5}")
        results[c["label"]] = {"N": N, "X": X, "T": T,
                                "threshold_pct": round(pct * 100, 1), "bft_safe": ok}
    return results


# ── Section 10: TPS Estimate ──────────────────────────────────────────────────

def bench_tps_estimate(bp, ped, schn):
    section(10, "TPS Estimate — Config A / A2 / A2+batch")
    prove_ms  = bp["prove_64bit"]["mean_ms"]
    verify_ms = bp["verify_64bit"]["mean_ms"]
    commit_ms = ped["commit"]["mean_ms"]
    zkp_ms    = schn["verify"]["mean_ms"]
    a_ms   = commit_ms * 2 + zkp_ms
    a2_ms  = prove_ms + verify_ms + commit_ms
    nat_ms = bp["batch"].get("B100", {}).get("native_ms", verify_ms * 100)
    a2b_ms = prove_ms * 100 + nat_ms + commit_ms * 100
    tps_a   = 1000.0 / a_ms
    tps_a2  = 1000.0 / a2_ms
    tps_a2b = 100_000.0 / a2b_ms
    print(f"\n  Config A  (Python EC only):           {a_ms:.1f} ms/tx  → {tps_a:.1f} TPS")
    print(f"  Config A2 (Python + Rust BP):         {a2_ms:.1f} ms/tx  → {tps_a2:.1f} TPS")
    print(f"  Config A2+batch (100 tx native batch):{a2b_ms:.0f} ms/100tx → {tps_a2b:.1f} TPS")
    print(f"\n  ZK-AML prove speedup vs Platypus:     {110/prove_ms:.1f}× (claimed 12.6×)")
    print(f"  ZK-AML prove speedup vs Zerocash:     {87000/prove_ms:.0f}×")
    return {
        "config_a_tps":   round(tps_a, 2),
        "config_a2_tps":  round(tps_a2, 2),
        "config_a2b_tps": round(tps_a2b, 2),
        "prove_speedup_vs_platypus": round(110 / prove_ms, 1),
        "prove_speedup_vs_zerocash": round(87000 / prove_ms, 0),
    }


# ── Section 11: Breaking Point Analysis ──────────────────────────────────────

def bench_breaking_point():
    section(11, "Breaking Point Analysis — concurrent ZK proof load")
    from core.crypto.real.velocity_zkp import prove_velocity
    from core.crypto.real.structuring_zkp import prove_structuring

    print("""
  Note: Python OR-proofs (simple_range_proof.py) are GIL-bound.
  Threads serialise on EC arithmetic — this test shows the honest
  single-process throughput ceiling under concurrent requests.
  True parallelism would require multiprocessing (like batch verify).
""")

    results = {"velocity_zkp_concurrent": [], "structuring_zkp_concurrent": [],
               "detected_breaking_points": []}

    def _run_concurrent(fn, load: int) -> dict:
        """Submit `load` copies of fn() to a thread pool; return timing stats."""
        t_wall = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=load) as pool:
            futs = [pool.submit(fn) for _ in range(load)]
            times_ms = []
            for f in concurrent.futures.as_completed(futs):
                f.result()  # ensure no exception
            # We can't get per-task times easily from as_completed without wrapping
        wall_ms = (time.perf_counter() - t_wall) * 1000
        # Measure serial time for per-proof baseline
        t_serial = time.perf_counter()
        fn()
        serial_ms = (time.perf_counter() - t_serial) * 1000
        return {
            "load": load,
            "wall_ms": round(wall_ms, 1),
            "throughput_proofs_per_sec": round(load / (wall_ms / 1000), 2),
            "serial_single_ms": round(serial_ms, 1),
        }

    # ── 11a: velocity ZK ──
    print("  [11a] Concurrent R_velocity prove (count=7, T=5, window=1h)")
    vel_fn = lambda: prove_velocity(7, 5, "1h", TX_HASH)
    # baseline at load=1
    b1 = _run_concurrent(vel_fn, 1)
    baseline_v = b1["throughput_proofs_per_sec"]
    print(f"  {'load':>6} {'wall_ms':>9} {'proofs/s':>10} {'serial_ms':>10}")
    print("  " + "-" * 40)
    for load in BP_SIZES:
        r = _run_concurrent(vel_fn, load)
        degraded = r["throughput_proofs_per_sec"] < baseline_v * 0.5
        if degraded:
            results["detected_breaking_points"].append({
                "test": "velocity_zkp_concurrent",
                "load": load,
                "throughput": r["throughput_proofs_per_sec"],
                "reason": "50% throughput degradation vs baseline",
            })
        results["velocity_zkp_concurrent"].append(r)
        marker = " ← DEGRADATION" if degraded else ""
        print(f"  {load:>6} {r['wall_ms']:>9.1f} {r['throughput_proofs_per_sec']:>10.2f} "
              f"{r['serial_single_ms']:>10.1f}{marker}")

    # ── 11b: structuring ZK ──
    print(f"\n  [11b] Concurrent R_structuring prove (STRUCTURING branch)")
    str_fn = lambda: prove_structuring(960_000, 950_000, 1_000_000, TX_HASH)
    b1s = _run_concurrent(str_fn, 1)
    baseline_s = b1s["throughput_proofs_per_sec"]
    print(f"  {'load':>6} {'wall_ms':>9} {'proofs/s':>10} {'serial_ms':>10}")
    print("  " + "-" * 40)
    for load in BP_SIZES:
        r = _run_concurrent(str_fn, load)
        degraded = r["throughput_proofs_per_sec"] < baseline_s * 0.5
        if degraded:
            results["detected_breaking_points"].append({
                "test": "structuring_zkp_concurrent",
                "load": load,
                "throughput": r["throughput_proofs_per_sec"],
                "reason": "50% throughput degradation vs baseline",
            })
        results["structuring_zkp_concurrent"].append(r)
        marker = " ← DEGRADATION" if degraded else ""
        print(f"  {load:>6} {r['wall_ms']:>9.1f} {r['throughput_proofs_per_sec']:>10.2f} "
              f"{r['serial_single_ms']:>10.1f}{marker}")

    if results["detected_breaking_points"]:
        print(f"\n  Breaking points detected: {len(results['detected_breaking_points'])}")
        for bp in results["detected_breaking_points"]:
            print(f"    - {bp['test']}: load={bp['load']}, {bp['reason']}")
    else:
        print("\n  No breaking points detected — system is GIL-serialised (expected).")
        print("  Throughput scales sublinearly with load due to Python GIL on EC arithmetic.")

    return results


# ── Section 12: Paper Comparison Table ───────────────────────────────────────

def print_paper_table(bp, bbs, tps):
    section(12, "Paper Comparison Table")
    prove  = bp["prove_64bit"]["mean_ms"]
    verify = bp["verify_64bit"]["mean_ms"]
    psize  = bp["proof_sizes"]["64bit"]
    print(f"""
  ┌─────────────────────┬─────────────┬─────────────┬─────────┬───────────┬──────────────────────┐
  │ System              │ Prove (ms)  │ Verify (ms) │ Size(B) │ Trusted   │ AML in ZK            │
  ├─────────────────────┼─────────────┼─────────────┼─────────┼───────────┼──────────────────────┤
  │ Zerocash S&P'14     │ ~87,000     │ <6          │ 288     │ YES       │ None                 │
  │ Platypus CCS'22     │ 110–730     │ 0.89–1.5    │ 418–1122│ YES       │ Balance limits only  │
  │ Bulletproofs S&P'18 │ ~36         │ ~11         │ ~674    │ NO        │ None                 │
  ├─────────────────────┼─────────────┼─────────────┼─────────┼───────────┼──────────────────────┤
  │ ZK-AML (this work)  │ {prove:<11.2f}│ {verify:<11.2f}│ {psize:<7} │ NO        │ PMLA: high-value,    │
  │ Apple M1 Pro ARM64  │ (Rust dalek │ (Rust dalek │(Rist255)│ (DLOG)    │ velocity, structuring │
  │                     │  Rist255)   │  Rist255)   │         │           │ (CBC primitive, novel)│
  └─────────────────────┴─────────────┴─────────────┴─────────┴───────────┴──────────────────────┘

  ZK-AML prove speedup vs Platypus:  {110/prove:.1f}× faster  (hardware-adjusted note: M1 Pro vs i7-7700)
  ZK-AML prove speedup vs Zerocash:  {87000/prove:.0f}× faster
  Batch verify B=100: {bp['batch'].get('B100',{}).get('native_speedup','N/A')}× native Rust speedup, {bp['batch'].get('B100',{}).get('parallel_speedup','N/A')}× fork-pool speedup
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    hw = _hardware_info()
    ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 70)
    print("  ZK-AML MASTER BENCHMARK SUITE")
    print(f"  {ts_str}")
    print(f"  CPU: {hw['processor']}  ({hw['cpu_count']} cores)  OS: {hw['os']}")
    print(f"  Python {hw['python']}  N_TRIALS={N_TRIALS}  N_WORKERS={N_WORKERS}")
    print("=" * 70)

    all_results = {
        "run_id":       f"master_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "hardware":     hw,
        "timestamp":    datetime.datetime.now().isoformat(),
        "n_trials":     N_TRIALS,
        "n_warmup":     N_WARMUP,
        "n_trials_engine": N_TRIALS_ENGINE,
        "platypus_ref": PLATYPUS_REF,
        "zerocash_ref": ZEROCASH_REF,
        "bp_paper_ref": BP_PAPER_REF,
    }

    bp_res   = bench_bulletproofs()
    ped_res  = bench_pedersen()
    schn_res = bench_schnorr_zkp()
    bbs_res  = bench_bbs()
    srp_res  = bench_simple_range_proof()
    vel_res  = bench_velocity_zkp()
    str_res  = bench_structuring_zkp()
    eng_res  = bench_anomaly_engine()
    con_res  = bench_consensus_sweep()
    tps_res  = bench_tps_estimate(bp_res, ped_res, schn_res)
    brk_res  = bench_breaking_point()
    print_paper_table(bp_res, bbs_res, tps_res)

    all_results.update({
        "bulletproofs":        bp_res,
        "pedersen":            ped_res,
        "schnorr_zkp":         schn_res,
        "bbs_group_sig":       bbs_res,
        "simple_range_proof":  srp_res,
        "velocity_zkp":        vel_res,
        "structuring_zkp":     str_res,
        "anomaly_engine":      eng_res,
        "consensus":           con_res,
        "tps_estimate":        tps_res,
        "breaking_points":     brk_res,
    })

    # Save JSON
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"master_{ts}.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*70}")
    print(f"  Results saved → {out_path}")
    print(f"  Run: python3 -m tests.benchmarks.benchmark_master")
    print(f"  All numbers on {hw['processor']} / {hw['os']}.")
    print(f"  Hardware-independent claims: proof sizes, batch speedup ratios,")
    print(f"  no trusted setup, AML rules in ZK (CBC primitive).")
    print(f"{'='*70}\n")

    return all_results, out_path


if __name__ == "__main__":
    main()
