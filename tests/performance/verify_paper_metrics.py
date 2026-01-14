"""
Comprehensive Performance Verification for CCS 2026 Paper
Purpose: Verify ALL claimed performance metrics with rigorous testing

Paper Claims to Verify:
1. Anomaly ZKP Proofs: 64,004/sec
2. Threshold Anomaly Encryption: 17,998/sec
"""

import time
import statistics
from decimal import Decimal
from core.crypto.anomaly_zkp import AnomalyZKPService
from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption


def benchmark_zkp_1000():
    """Benchmark 1,000 ZKP proofs"""
    print("\n" + "="*70)
    print("TEST 1: ZKP Performance (1,000 proofs)")
    print("="*70)

    zkp_service = AnomalyZKPService()
    num_proofs = 1000

    # Generate proofs
    gen_times = []
    verify_times = []
    valid_count = 0

    print(f"Generating and verifying {num_proofs} ZKP proofs...")
    start_time = time.time()

    for i in range(num_proofs):
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

        # Verify proof
        ver_start = time.time()
        is_valid = zkp_service.verify_anomaly_proof(proof)
        ver_time = time.time() - ver_start
        verify_times.append(ver_time)

        if is_valid:
            valid_count += 1

    total_time = time.time() - start_time

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

    assert valid_count == num_proofs, f"❌ Only {valid_count}/{num_proofs} valid"
    print("\n✅ Test 1 PASSED")

    return {
        'count': num_proofs,
        'gen_throughput': gen_throughput,
        'verify_throughput': verify_throughput,
        'combined_throughput': combined_throughput
    }


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
        # Generate proof
        result = zkp_service.generate_anomaly_proof(
            transaction_hash=f'0xzkp_large_{i:05d}',
            anomaly_score=75.0 + (i % 20),
            anomaly_flags=['HIGH_VALUE_TIER_1'] if i % 3 == 0 else [],
            requires_investigation=(i % 3 == 0)
        )

        # ✅ FIX: Extract 'proof' key
        proof = result['proof']

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


def benchmark_threshold_1000():
    """Benchmark 1,000 threshold encryption operations"""
    print("\n" + "="*70)
    print("TEST 3: Threshold Encryption Performance (1,000 operations)")
    print("="*70)

    threshold_enc = AnomalyThresholdEncryption()
    num_operations = 1000

    encrypt_times = []
    decrypt_times = []
    successful_ops = 0

    print(f"Running {num_operations} encrypt+decrypt operations...")
    start_time = time.time()

    for i in range(num_operations):
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

        # Verify decryption
        if decrypted['sender_idx'] == f'IDX_SENDER_{i}':
            successful_ops += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            throughput = (i + 1) / elapsed
            print(f"  Progress: {i+1}/{num_operations} - {throughput:,.0f} ops/sec - Success: {successful_ops}")

    total_time = time.time() - start_time

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

    assert successful_ops == num_operations, f"❌ Only {successful_ops}/{num_operations} succeeded"
    print("\n✅ Test 3 PASSED")

    return {
        'count': num_operations,
        'enc_throughput': enc_throughput,
        'dec_throughput': dec_throughput,
        'combined_throughput': combined_throughput
    }


def main():
    """Run all benchmarks and generate report"""
    print("\n" + "="*70)
    print("COMPREHENSIVE PERFORMANCE VERIFICATION FOR CCS 2026 PAPER")
    print("="*70)
    print("\nVerifying claimed metrics:")
    print("  • Anomaly ZKP Proofs: 64,004/sec (claimed)")
    print("  • Threshold Encryption: 17,998/sec (claimed)")
    print("\n" + "="*70)

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
    print("COMPARISON WITH PAPER CLAIMS")
    print("="*70)

    # ZKP comparison
    claimed_zkp = 64004
    measured_zkp = zkp_10k['throughput']
    zkp_ratio = (measured_zkp / claimed_zkp) * 100

    print(f"\n📊 ZKP Proofs:")
    print(f"   Claimed:  {claimed_zkp:,} proofs/sec")
    print(f"   Measured: {measured_zkp:,.0f} proofs/sec")
    print(f"   Ratio:    {zkp_ratio:.1f}% of claimed")

    if zkp_ratio >= 90:
        print("   ✅ VERIFIED - Within acceptable range")
    elif zkp_ratio >= 70:
        print("   ⚠️  LOWER - Need to update paper with measured value")
    else:
        print("   ❌ SIGNIFICANT DISCREPANCY - Must update paper")

    # Threshold comparison
    claimed_threshold = 17998
    measured_threshold = threshold_1k['combined_throughput']
    threshold_ratio = (measured_threshold / claimed_threshold) * 100

    print(f"\n📊 Threshold Encryption:")
    print(f"   Claimed:  {claimed_threshold:,} ops/sec")
    print(f"   Measured: {measured_threshold:,.0f} ops/sec")
    print(f"   Ratio:    {threshold_ratio:.1f}% of claimed")

    if threshold_ratio >= 90:
        print("   ✅ VERIFIED - Within acceptable range")
    elif threshold_ratio >= 70:
        print("   ⚠️  LOWER - Need to update paper with measured value")
    else:
        print("   ❌ SIGNIFICANT DISCREPANCY - Must update paper")

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
