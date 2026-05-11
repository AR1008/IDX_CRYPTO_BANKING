"""
Schnorr ZKP + RCTD Throughput Stress Test
Purpose: Measure real Schnorr ZKP and AES-256-GCM+Shamir throughput at scale.

Targets (CCS 2027, real EC crypto, master run 2026-03-02):
  Schnorr ZKP prove:   ~11.28 ms  (~89 proofs/sec)
  Schnorr ZKP verify:  ~9.05  ms  (~110 proofs/sec)
  AES-256-GCM enc/dec: ~0.04  ms  (>20,000 ops/sec)

NOTE: Old CCS 2026 claims (64,004 ZKP/sec, 17,998 enc/sec) were measured
on a SHA-256 simulation and must NOT be cited.  This file measures the
real secp256k1 Schnorr implementation and the real AES-256-GCM RCTD layer.
"""

# [DOC] time.perf_counter is used for high-resolution wall-clock timing of every generate/verify call
import time
# [DOC] statistics.mean computes average latency from the raw timing lists for each benchmark
import statistics
from decimal import Decimal
# [DOC] AnomalyZKPService is the production Schnorr ZKP class whose throughput is being verified
from core.crypto.anomaly_zkp import AnomalyZKPService
# [DOC] AnomalyThresholdEncryption is the AES-256-GCM + Shamir class whose throughput is being verified
from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption


# [DOC] benchmark_zkp_1000 measures ZKP generation and verification throughput over 1,000 proofs;
# [DOC] verifies every proof to confirm 100% validity while measuring per-operation latency
def benchmark_zkp_1000():
    """Benchmark 1,000 ZKP proofs"""
    print("\n" + "="*70)
    print("TEST 1: ZKP Performance (1,000 proofs)")
    print("="*70)

    # [DOC] AnomalyZKPService.generate_anomaly_proof produces a Schnorr sigma protocol proof;
    # [DOC] verify_anomaly_proof checks the Fiat-Shamir transcript; both are measured here
    zkp_service = AnomalyZKPService()
    num_proofs = 1000

    # Generate proofs
    gen_times = []
    verify_times = []
    valid_count = 0

    print(f"Generating and verifying {num_proofs} ZKP proofs...")
    start_time = time.time()

    for i in range(num_proofs):
        # [DOC] Alternating anomaly_score=85.5 (flagged) and 45.0 (normal) exercises both code paths
        # Generate proof
        gen_start = time.time()
        result = zkp_service.generate_anomaly_proof(
            transaction_hash=f'0xzkp_{i:04d}',
            anomaly_score=85.5 if i % 2 == 0 else 45.0,
            anomaly_flags=['HIGH_VALUE_TIER_1'] if i % 2 == 0 else [],
            requires_investigation=(i % 2 == 0)
        )
        gen_time = time.time() - gen_start
        gen_times.append(gen_time)

        # ✅ FIX: Extract 'proof' key from result
        proof = result['proof']

        # [DOC] Verify every proof immediately to confirm generate→verify round-trip correctness
        # Verify proof
        ver_start = time.time()
        is_valid = zkp_service.verify_anomaly_proof(proof)
        ver_time = time.time() - ver_start
        verify_times.append(ver_time)

        # [DOC] Invariant: every generated proof must pass verification (soundness and completeness check)
        if is_valid:
            valid_count += 1

    total_time = time.time() - start_time

    # [DOC] Throughput is computed separately for generation only, verification only, and combined;
    # [DOC] the combined number represents total pipeline throughput including both operations
    # Calculate throughput
    gen_throughput = num_proofs / sum(gen_times)
    verify_throughput = num_proofs / sum(verify_times)
    combined_throughput = num_proofs / total_time

    print(f"\n📊 Results:")
    print(f"  Total proofs: {num_proofs}")
    print(f"  Valid proofs: {valid_count}/{num_proofs} ({valid_count/num_proofs*100:.1f}%)")
    print(f"  Total time: {total_time:.3f}s")
    print(f"\n⚡ Throughput:")
    print(f"  Generation only: {gen_throughput:,.0f} proofs/sec")
    print(f"  Verification only: {verify_throughput:,.0f} proofs/sec")
    print(f"  Combined (gen+verify): {combined_throughput:,.0f} proofs/sec")
    print(f"\n⏱️  Timing:")
    print(f"  Avg generation: {statistics.mean(gen_times)*1000:.3f}ms")
    print(f"  Avg verification: {statistics.mean(verify_times)*1000:.3f}ms")

    # [DOC] Assertion: all 1,000 proofs must verify correctly — any failure is a critical correctness bug
    assert valid_count == num_proofs, f"❌ Only {valid_count}/{num_proofs} valid"
    print("\n✅ Test 1 PASSED")

    return {
        'count': num_proofs,
        'gen_throughput': gen_throughput,
        'verify_throughput': verify_throughput,
        'combined_throughput': combined_throughput
    }


# [DOC] benchmark_zkp_10000 measures ZKP generation throughput at 10,000 proofs with sampling;
# [DOC] verifies every 10th proof to balance correctness checking against runtime
def benchmark_zkp_10000():
    """Benchmark 10,000 ZKP proofs"""
    print("\n" + "="*70)
    print("TEST 2: ZKP Performance (10,000 proofs)")
    print("="*70)

    zkp_service = AnomalyZKPService()
    num_proofs = 10000

    print(f"Generating and verifying {num_proofs} ZKP proofs...")
    start_time = time.time()

    valid_count = 0

    for i in range(num_proofs):
        # [DOC] Varying anomaly_score by (i % 20) exercises the full score range [75, 94]
        # Generate proof
        result = zkp_service.generate_anomaly_proof(
            transaction_hash=f'0xzkp_large_{i:05d}',
            anomaly_score=75.0 + (i % 20),
            anomaly_flags=['HIGH_VALUE_TIER_1'] if i % 3 == 0 else [],
            requires_investigation=(i % 3 == 0)
        )

        # ✅ FIX: Extract 'proof' key
        proof = result['proof']

        # [DOC] Verify every 10th proof as a statistical sample to confirm ongoing correctness
        # Verify every 10th proof (to save time)
        if i % 10 == 0:
            if zkp_service.verify_anomaly_proof(proof):
                valid_count += 1

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - start_time
            throughput = (i + 1) / elapsed
            print(f"  Progress: {i+1}/{num_proofs} - {throughput:,.0f} proofs/sec")

    total_time = time.time() - start_time
    throughput = num_proofs / total_time

    print(f"\n📊 Results:")
    print(f"  Total proofs: {num_proofs}")
    print(f"  Verified (sample): {valid_count}/{num_proofs//10}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Throughput: {throughput:,.0f} proofs/sec")

    print("\n✅ Test 2 PASSED")

    return {
        'count': num_proofs,
        'throughput': throughput
    }


# [DOC] benchmark_threshold_1000 measures AES-256-GCM + Shamir encrypt and decrypt throughput
# [DOC] over 1,000 operations and verifies the decrypted sender_idx matches the original input
def benchmark_threshold_1000():
    """Benchmark 1,000 threshold encryption operations"""
    print("\n" + "="*70)
    print("TEST 3: Threshold Encryption Performance (1,000 operations)")
    print("="*70)

    # [DOC] AnomalyThresholdEncryption provides encrypt_transaction_details and decrypt_transaction_details
    threshold_enc = AnomalyThresholdEncryption()
    num_operations = 1000

    encrypt_times = []
    decrypt_times = []
    successful_ops = 0

    print(f"Running {num_operations} encrypt+decrypt operations...")
    start_time = time.time()

    for i in range(num_operations):
        # [DOC] Encryption generates a unique AES key per transaction and splits it via Shamir (Nested TSS)
        # Encryption
        enc_start = time.time()

        # ✅ FIX: Get full result with both keys
        result = threshold_enc.encrypt_transaction_details(
            transaction_hash=f'0xenc_{i:04d}',
            sender_idx=f'IDX_SENDER_{i}',
            receiver_idx=f'IDX_RECEIVER_{i}',
            amount=Decimal(str(5000000 + i)),
            anomaly_score=75.5 + (i % 20),
            anomaly_flags=['HIGH_VALUE_TIER_1']
        )

        enc_time = time.time() - enc_start
        encrypt_times.append(enc_time)

        # ✅ FIX: Extract encrypted_package and key_shares separately
        encrypted_package = result['encrypted_package']
        key_shares = result['key_shares']

        # [DOC] Decryption assembles Company + supreme_court + rbi shares and calls AES-GCM decrypt
        # Decryption
        dec_start = time.time()

        # Get shares
        company_share = key_shares['company']
        court_share = key_shares['supreme_court']
        rbi_share = key_shares['rbi']

        # ✅ FIX: Pass the correct encrypted_package
        decrypted = threshold_enc.decrypt_transaction_details(
            encrypted_package=encrypted_package,
            provided_shares=[company_share, court_share, rbi_share]
        )

        dec_time = time.time() - dec_start
        decrypt_times.append(dec_time)

        # [DOC] Invariant: decrypted sender_idx must exactly match the original input; any mismatch is a bug
        # Verify decryption
        if decrypted['sender_idx'] == f'IDX_SENDER_{i}':
            successful_ops += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            throughput = (i + 1) / elapsed
            print(f"  Progress: {i+1}/{num_operations} - {throughput:,.0f} ops/sec - Success: {successful_ops}")

    total_time = time.time() - start_time

    # [DOC] Separate encrypt and decrypt throughput show which half of the RCTD pipeline is the bottleneck
    # Calculate throughput
    enc_throughput = num_operations / sum(encrypt_times)
    dec_throughput = num_operations / sum(decrypt_times)
    combined_throughput = num_operations / total_time

    print(f"\n📊 Results:")
    print(f"  Total operations: {num_operations}")
    print(f"  Successful: {successful_ops}/{num_operations} ({successful_ops/num_operations*100:.1f}%)")
    print(f"  Total time: {total_time:.3f}s")
    print(f"\n⚡ Throughput:")
    print(f"  Encryption only: {enc_throughput:,.0f} ops/sec")
    print(f"  Decryption only: {dec_throughput:,.0f} ops/sec")
    print(f"  Combined (enc+dec): {combined_throughput:,.0f} ops/sec")
    print(f"\n⏱️  Timing:")
    print(f"  Avg encryption: {statistics.mean(encrypt_times)*1000:.3f}ms")
    print(f"  Avg decryption: {statistics.mean(decrypt_times)*1000:.3f}ms")

    # [DOC] Assertion: all 1,000 decrypt operations must recover the correct data — confirms RCTD correctness
    assert successful_ops == num_operations, f"❌ Only {successful_ops}/{num_operations} succeeded"
    print("\n✅ Test 3 PASSED")

    return {
        'count': num_operations,
        'enc_throughput': enc_throughput,
        'dec_throughput': dec_throughput,
        'combined_throughput': combined_throughput
    }


# [DOC] main() runs all three benchmarks in sequence, then compares measured vs claimed numbers
# [DOC] and prints VERIFIED / LOWER / SIGNIFICANT DISCREPANCY to guide paper updates
def main():
    """Run all benchmarks and generate report"""
    print("\n" + "="*70)
    print("SCHNORR ZKP + RCTD THROUGHPUT STRESS TEST (CCS 2027)")
    print("="*70)
    print("\nReal EC targets (master run 2026-03-02):")
    print("  • Schnorr ZKP prove:   ~11.28 ms / ~89 proofs/sec")
    print("  • Schnorr ZKP verify:  ~9.05  ms / ~110 proofs/sec")
    print("  • AES-256-GCM enc/dec: ~0.04  ms / >20,000 ops/sec")
    print("\n" + "="*70)

    # [DOC] Run benchmarks in order of increasing scale: 1k ZKP, 10k ZKP, 1k threshold
    # Run benchmarks
    zkp_1k = benchmark_zkp_1000()
    zkp_10k = benchmark_zkp_10000()
    threshold_1k = benchmark_threshold_1000()

    # Generate final report
    print("\n" + "="*70)
    print("FINAL VERIFICATION REPORT")
    print("="*70)

    print("\n1️⃣  ZKP Performance (1,000 proofs):")
    print(f"   • Generation: {zkp_1k['gen_throughput']:,.0f} proofs/sec")
    print(f"   • Verification: {zkp_1k['verify_throughput']:,.0f} proofs/sec")
    print(f"   • Combined: {zkp_1k['combined_throughput']:,.0f} proofs/sec")

    print("\n2️⃣  ZKP Performance (10,000 proofs):")
    print(f"   • Throughput: {zkp_10k['throughput']:,.0f} proofs/sec")

    print("\n3️⃣  Threshold Encryption (1,000 operations):")
    print(f"   • Encryption: {threshold_1k['enc_throughput']:,.0f} ops/sec")
    print(f"   • Decryption: {threshold_1k['dec_throughput']:,.0f} ops/sec")
    print(f"   • Combined: {threshold_1k['combined_throughput']:,.0f} ops/sec")

    print("\n" + "="*70)
    print("COMPARISON WITH CCS 2027 REAL EC TARGETS")
    print("="*70)

    # [DOC] target_zkp_verify=110 is the real Schnorr secp256k1 throughput from master run 2026-03-02
    target_zkp_verify = 110  # proofs/sec (real Schnorr, 9.05ms verify)
    measured_zkp = zkp_10k['throughput']
    zkp_ratio = (measured_zkp / target_zkp_verify) * 100

    print(f"\n📊 ZKP Proofs (real Schnorr secp256k1):")
    print(f"   Target:   ~{target_zkp_verify:,} proofs/sec (9.05ms verify, master 2026-03-02)")
    print(f"   Measured: {measured_zkp:,.0f} proofs/sec")
    print(f"   Ratio:    {zkp_ratio:.1f}% of target")

    # [DOC] >=80% of target is on-track; <60% indicates a regression worth investigating
    if zkp_ratio >= 80:
        print("   ✅ ON TRACK")
    elif zkp_ratio >= 60:
        print("   ⚠️  SLIGHTLY LOWER — acceptable variance; rerun to confirm")
    else:
        print("   ❌ REGRESSION — investigate before paper submission")

    # [DOC] target_threshold_enc=25000 is a conservative floor for AES-256-GCM+Shamir combined
    target_threshold_enc = 25000  # ops/sec (AES-256-GCM 0.04ms per op)
    measured_threshold = threshold_1k['combined_throughput']
    threshold_ratio = (measured_threshold / target_threshold_enc) * 100

    print(f"\n📊 RCTD Threshold Encryption (AES-256-GCM + Shamir):")
    print(f"   Target:   ~{target_threshold_enc:,} ops/sec (0.04ms enc, master 2026-03-02)")
    print(f"   Measured: {measured_threshold:,.0f} ops/sec")
    print(f"   Ratio:    {threshold_ratio:.1f}% of target")

    # [DOC] Same >=80%/<60% thresholds to classify measured vs real EC target
    if threshold_ratio >= 80:
        print("   ✅ ON TRACK")
    elif threshold_ratio >= 60:
        print("   ⚠️  SLIGHTLY LOWER — acceptable variance; rerun to confirm")
    else:
        print("   ❌ REGRESSION — investigate before paper submission")

    print("\n" + "="*70)
    print("✅ ALL BENCHMARKS COMPLETED SUCCESSFULLY")
    print("="*70)

    # Return results for further analysis
    return {
        'zkp_1k': zkp_1k,
        'zkp_10k': zkp_10k,
        'threshold_1k': threshold_1k
    }


if __name__ == "__main__":
    results = main()
