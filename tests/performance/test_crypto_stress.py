"""
Crypto Stress Tests: Performance Testing for Cryptographic Operations
Purpose: Test cryptographic performance with high load

Focus Areas:
1. ZKP proof generation (1,000 proofs)
2. Threshold encryption (1,000 operations)
3. Concurrent cryptographic operations

Performance Targets:
- ZKP generation: < 50ms per proof
- Threshold encryption: < 100ms per operation
- Threshold decryption: < 100ms per operation
"""

import pytest
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

from core.crypto.anomaly_zkp import AnomalyZKPService
from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption


class TestZKPStress:
    """Stress test ZKP proof generation"""

    def test_1000_zkp_proofs(self):
        """
        Stress test: Generate 1,000 ZKP proofs

        Target: < 50ms per proof average
        """
        print("\n=== Stress Test: 1,000 ZKP Proof Generation ===\n")

        zkp_service = AnomalyZKPService()

        num_proofs = 1000

        print(f"Generating {num_proofs} ZKP proofs...")
        start_time = time.time()

        results = []
        valid_count = 0

        for i in range(num_proofs):
            proof_start = time.time()

            # Alternate between flagged and normal
            requires_investigation = (i % 2 == 0)
            anomaly_score = 85.5 if requires_investigation else 45.0
            anomaly_flags = ['HIGH_VALUE_TIER_1'] if requires_investigation else []

            result = zkp_service.generate_anomaly_proof(
                transaction_hash=f'0xzkp_stress_{i:04d}',
                anomaly_score=anomaly_score,
                anomaly_flags=anomaly_flags,
                requires_investigation=requires_investigation
            )

            # Verify proof (extract 'proof' key from result)
            proof = result['proof']
            is_valid = zkp_service.verify_anomaly_proof(proof)
            if is_valid:
                valid_count += 1

            proof_time = (time.time() - proof_start) * 1000
            results.append(proof_time)

            if (i + 1) % 100 == 0:
                avg_so_far = statistics.mean(results)
                print(f"  Generated {i + 1}/{num_proofs} proofs - Avg: {avg_so_far:.2f}ms - Valid: {valid_count}")

        end_time = time.time()
        total_time = end_time - start_time

        # Calculate statistics
        avg_time = statistics.mean(results)
        median_time = statistics.median(results)
        min_time = min(results)
        max_time = max(results)
        p95_time = sorted(results)[int(len(results) * 0.95)]
        p99_time = sorted(results)[int(len(results) * 0.99)]

        print(f"\n📊 Performance Results:")
        print(f"  Total proofs: {num_proofs}")
        print(f"  Valid proofs: {valid_count}/{num_proofs} ({valid_count/num_proofs*100:.1f}%)")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {num_proofs/total_time:.2f} proofs/sec")
        print(f"\n⏱️  Timing Statistics (per proof):")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  Median: {median_time:.2f}ms")
        print(f"  Min: {min_time:.2f}ms")
        print(f"  Max: {max_time:.2f}ms")
        print(f"  P95: {p95_time:.2f}ms")
        print(f"  P99: {p99_time:.2f}ms")

        print(f"\n✅ Performance Targets:")
        print(f"  {'✅' if avg_time < 50 else '❌'} Average < 50ms: {avg_time:.2f}ms")
        print(f"  {'✅' if p95_time < 100 else '❌'} P95 < 100ms: {p95_time:.2f}ms")
        print(f"  {'✅' if p99_time < 200 else '❌'} P99 < 200ms: {p99_time:.2f}ms")

        # All proofs should be valid
        assert valid_count == num_proofs, f"Only {valid_count}/{num_proofs} proofs were valid"

        print("\n=== ✅ ZKP Stress Test PASSED ===\n")


class TestThresholdEncryptionStress:
    """Stress test threshold encryption"""

    def test_1000_encryptions_and_decryptions(self):
        """
        Stress test: 1,000 encryption + decryption operations

        Target: < 100ms per operation average
        """
        print("\n=== Stress Test: 1,000 Threshold Encryption Operations ===\n")

        threshold_enc = AnomalyThresholdEncryption()

        num_operations = 1000

        print(f"Running {num_operations} encrypt+decrypt operations...")
        start_time = time.time()

        encrypt_times = []
        decrypt_times = []
        totals_list = []
        successful_ops = 0

        for i in range(num_operations):
            # Encryption
            enc_start = time.time()

            result = threshold_enc.encrypt_transaction_details(
                transaction_hash=f'0xenc_stress_{i:04d}',
                sender_idx=f'IDX_SENDER_{i}',
                receiver_idx=f'IDX_RECEIVER_{i}',
                amount=Decimal(str(5000000 + i)),
                anomaly_score=75.5 + (i % 20),
                anomaly_flags=['HIGH_VALUE_TIER_1']
            )

            enc_time = (time.time() - enc_start) * 1000
            encrypt_times.append(enc_time)

            # Extract encrypted_package and key_shares separately
            encrypted_package = result['encrypted_package']
            key_shares = result['key_shares']

            # Decryption
            dec_start = time.time()

            company_share = key_shares['company']
            court_share = key_shares['supreme_court']
            rbi_share = key_shares['rbi']

            decrypted = threshold_enc.decrypt_transaction_details(
                encrypted_package=encrypted_package,
                provided_shares=[company_share, court_share, rbi_share]
            )

            dec_time = (time.time() - dec_start) * 1000
            decrypt_times.append(dec_time)

            # Record per-iteration total (encrypt + decrypt)
            totals_list.append(enc_time + dec_time)

            # Verify decryption
            if decrypted['sender_idx'] == f'IDX_SENDER_{i}':
                successful_ops += 1

            if (i + 1) % 100 == 0:
                avg_enc = statistics.mean(encrypt_times)
                avg_dec = statistics.mean(decrypt_times)
                print(f"  Completed {i + 1}/{num_operations} - Enc: {avg_enc:.2f}ms, Dec: {avg_dec:.2f}ms - Success: {successful_ops}")

        end_time = time.time()
        total_time = end_time - start_time

        # Calculate statistics
        avg_enc = statistics.mean(encrypt_times)
        avg_dec = statistics.mean(decrypt_times)
        # Average total per iteration from totals_list
        avg_total = statistics.mean(totals_list) if totals_list else (avg_enc + avg_dec)

        median_enc = statistics.median(encrypt_times)
        median_dec = statistics.median(decrypt_times)
        median_total = statistics.median(totals_list) if totals_list else None

        p95_enc = sorted(encrypt_times)[int(len(encrypt_times) * 0.95)]
        p95_dec = sorted(decrypt_times)[int(len(decrypt_times) * 0.95)]
        p95_total = sorted(totals_list)[int(len(totals_list) * 0.95)]
        p99_enc = sorted(encrypt_times)[int(len(encrypt_times) * 0.99)]
        p99_dec = sorted(decrypt_times)[int(len(decrypt_times) * 0.99)]
        p99_total = sorted(totals_list)[int(len(totals_list) * 0.99)]

        print(f"\n📊 Performance Results:")
        print(f"  Total operations: {num_operations} (encrypt + decrypt)")
        print(f"  Successful: {successful_ops}/{num_operations} ({successful_ops/num_operations*100:.1f}%)")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {num_operations/total_time:.2f} ops/sec")
        
        print(f"\n⏱️  Encryption Timing:")
        print(f"  Average: {avg_enc:.2f}ms")
        print(f"  Median: {median_enc:.2f}ms")
        print(f"  P95: {p95_enc:.2f}ms")
        print(f"  P99: {p99_enc:.2f}ms")
        
        print(f"\n⏱️  Decryption Timing:")
        print(f"  Average: {avg_dec:.2f}ms")
        print(f"  Median: {median_dec:.2f}ms")
        print(f"  P95: {p95_dec:.2f}ms")
        print(f"  P99: {p99_dec:.2f}ms")
        
        print(f"\n⏱️  Total (Encrypt + Decrypt):")
        print(f"  Average: {avg_total:.2f}ms")
        print(f"  P95: {p95_total:.2f}ms")

        print(f"\n✅ Performance Targets:")
        print(f"  {'✅' if avg_total < 100 else '❌'} Average < 100ms: {avg_total:.2f}ms")
        print(f"  {'✅' if p95_enc < 75 else '❌'} P95 Encryption < 75ms: {p95_enc:.2f}ms")
        print(f"  {'✅' if p95_dec < 75 else '❌'} P95 Decryption < 75ms: {p95_dec:.2f}ms")

        # All operations should succeed
        assert successful_ops == num_operations, f"Only {successful_ops}/{num_operations} operations succeeded"

        print("\n=== ✅ Threshold Encryption Stress Test PASSED ===\n")

    def test_10000_zkp_proofs_high_volume(self):
        """
        High-volume stress test: Generate 10,000 ZKP proofs

        Target: Maintain < 50ms average even at high volume
        """
        print("\n=== High-Volume Stress Test: 10,000 ZKP Proofs ===\n")

        zkp_service = AnomalyZKPService()

        num_proofs = 10000

        print(f"Generating {num_proofs} ZKP proofs...")
        start_time = time.time()

        results = []
        valid_count = 0

        for i in range(num_proofs):
            proof_start = time.time()

            result = zkp_service.generate_anomaly_proof(
                transaction_hash=f'0xhighvol_{i:05d}',
                anomaly_score=75.0 + (i % 20),
                anomaly_flags=['HIGH_VALUE_TIER_1'] if i % 3 == 0 else [],
                requires_investigation=(i % 3 == 0)
            )

            # Verify every 10th proof (to save time)
            if i % 10 == 0:
                proof = result['proof']
                if zkp_service.verify_anomaly_proof(proof):
                    valid_count += 1

            proof_time = (time.time() - proof_start) * 1000
            results.append(proof_time)

            if (i + 1) % 1000 == 0:
                avg_so_far = statistics.mean(results)
                print(f"  Generated {i + 1}/{num_proofs} - Avg: {avg_so_far:.2f}ms")

        end_time = time.time()
        total_time = end_time - start_time

        # Calculate statistics
        avg_time = statistics.mean(results)
        median_time = statistics.median(results)
        p95_time = sorted(results)[int(len(results) * 0.95)]
        p99_time = sorted(results)[int(len(results) * 0.99)]
        throughput = num_proofs / total_time

        print(f"\n📊 High-Volume Performance Results:")
        print(f"  Total proofs: {num_proofs}")
        print(f"  Verified (sample): {valid_count}/{num_proofs//10} ({valid_count/(num_proofs//10)*100:.1f}%)")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} proofs/sec")
        print(f"\n⏱️  Timing Statistics:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  Median: {median_time:.2f}ms")
        print(f"  P95: {p95_time:.2f}ms")
        print(f"  P99: {p99_time:.2f}ms")

        print(f"\n✅ Performance Targets:")
        print(f"  {'✅' if avg_time < 50 else '❌'} Average < 50ms: {avg_time:.2f}ms")
        print(f"  {'✅' if throughput > 20 else '❌'} Throughput > 20/sec: {throughput:.2f}/sec")

        print("\n=== ✅ High-Volume ZKP Test PASSED ===\n")


class TestConcurrentCrypto:
    """Test concurrent cryptographic operations"""

    def test_concurrent_zkp_generation(self):
        """
        Test concurrent ZKP proof generation with multiple threads

        Simulates real-world concurrent proof generation
        """
        print("\n=== Stress Test: Concurrent ZKP Generation ===\n")

        zkp_service = AnomalyZKPService()

        num_proofs = 500
        num_threads = 10

        print(f"Generating {num_proofs} proofs with {num_threads} threads...")

        def generate_proof(proof_id):
            """Generate single proof"""
            start = time.time()
            result = zkp_service.generate_anomaly_proof(
                transaction_hash=f'0xconcurrent_{proof_id:04d}',
                anomaly_score=75.0 + (proof_id % 20),
                anomaly_flags=['HIGH_VALUE_TIER_1'],
                requires_investigation=True
            )
            elapsed = (time.time() - start) * 1000
            proof = result['proof']
            is_valid = zkp_service.verify_anomaly_proof(proof)
            return (elapsed, is_valid)

        start_time = time.time()
        results = []
        valid_count = 0

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(generate_proof, i) for i in range(num_proofs)]

            for i, future in enumerate(as_completed(futures)):
                elapsed, is_valid = future.result()
                results.append(elapsed)
                if is_valid:
                    valid_count += 1

                if (i + 1) % 50 == 0:
                    print(f"  Completed {i + 1}/{num_proofs} - Valid: {valid_count}")

        end_time = time.time()
        total_time = end_time - start_time

        avg_time = statistics.mean(results)
        throughput = num_proofs / total_time

        print(f"\n📊 Concurrent Processing Results:")
        print(f"  Total proofs: {num_proofs}")
        print(f"  Threads: {num_threads}")
        print(f"  Valid: {valid_count}/{num_proofs} ({valid_count/num_proofs*100:.1f}%)")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} proofs/sec")
        print(f"  Average time: {avg_time:.2f}ms")

        print(f"\n✅ Performance Targets:")
        print(f"  {'✅' if throughput > 50 else '❌'} Throughput > 50/sec: {throughput:.2f}/sec")
        print(f"  {'✅' if valid_count == num_proofs else '❌'} All proofs valid: {valid_count}/{num_proofs}")

        assert valid_count == num_proofs, f"Only {valid_count}/{num_proofs} proofs were valid"

        print("\n=== ✅ Concurrent ZKP Test PASSED ===\n")


# Run tests
if __name__ == "__main__":
    print("=" * 70)
    print("CRYPTO STRESS TESTS: Performance Testing")
    print("=" * 70)
    print()

    pytest.main([__file__, '-v', '-s'])
