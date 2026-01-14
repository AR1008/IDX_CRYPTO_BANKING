"""
Unit Tests for Anomaly Zero-Knowledge Proof Service
Purpose: Test ZKP proof generation, verification, and security properties

Test Coverage:
- ZKP proof generation for flagged and non-flagged transactions
- Proof verification (public proof only)
- Opening verification (private chain with witness)
- Tamper detection
- Transaction hash binding
- Commitment hiding properties
- Proof size and performance
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
import json
from decimal import Decimal

from core.crypto.anomaly_zkp import AnomalyZKPService


class TestAnomalyZKPService(unittest.TestCase):
    """Test Anomaly ZKP Service"""

    def setUp(self):
        """Set up test environment"""
        self.zkp_service = AnomalyZKPService()

    # ===== Test 1: Proof Generation =====

    def test_generate_proof_for_flagged_transaction(self):
        """Test: Generate ZKP proof for flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xabc123def456",
            anomaly_score=75.5,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        # Verify proof structure
        self.assertIn('version', proof)
        self.assertIn('transaction_hash', proof)
        self.assertIn('flag_commitment', proof)
        self.assertIn('timestamp', proof)
        self.assertIn('proof_data', proof)
        self.assertIn('witness', proof)

        # Verify proof data structure
        self.assertIn('nonce_commitment', proof['proof_data'])
        self.assertIn('challenge', proof['proof_data'])
        self.assertIn('response', proof['proof_data'])

        # Verify witness structure
        self.assertEqual(proof['witness']['flag_value'], 1)
        self.assertEqual(proof['witness']['anomaly_score'], 75.5)
        self.assertIn('HIGH_VALUE_TIER_1', proof['witness']['anomaly_flags'])

    def test_generate_proof_for_non_flagged_transaction(self):
        """Test: Generate ZKP proof for non-flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xdef789ghi012",
            anomaly_score=30.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # Verify flag value is 0 (not flagged)
        self.assertEqual(proof['witness']['flag_value'], 0)
        self.assertEqual(proof['witness']['anomaly_score'], 30.0)
        self.assertEqual(proof['witness']['anomaly_flags'], [])

    # ===== Test 2: Proof Verification =====

    def test_verify_valid_proof(self):
        """Test: Verify valid ZKP proof"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xtest123",
            anomaly_score=80.0,
            anomaly_flags=['HIGH_VALUE_TIER_2'],
            requires_investigation=True
        )

        is_valid = self.zkp_service.verify_anomaly_proof(proof)
        self.assertTrue(is_valid, "Valid proof should verify correctly")

    def test_verify_proof_with_transaction_hash(self):
        """Test: Verify proof with transaction hash check"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xspecific_hash",
            anomaly_score=70.0,
            anomaly_flags=['VELOCITY'],
            requires_investigation=True
        )

        # Correct hash should verify
        is_valid = self.zkp_service.verify_anomaly_proof(
            proof,
            expected_transaction_hash="0xspecific_hash"
        )
        self.assertTrue(is_valid, "Proof should verify with correct hash")

        # Wrong hash should fail
        is_invalid = self.zkp_service.verify_anomaly_proof(
            proof,
            expected_transaction_hash="0xwrong_hash"
        )
        self.assertFalse(is_invalid, "Proof should fail with wrong hash")

    def test_verify_tampered_proof(self):
        """Test: Detect tampered proof"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xoriginal",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # Tamper with commitment
        tampered_proof = proof.copy()
        tampered_proof['flag_commitment'] = '0x' + '0' * 64

        is_valid = self.zkp_service.verify_anomaly_proof(tampered_proof)
        self.assertFalse(is_valid, "Tampered proof should not verify")

    def test_verify_invalid_proof_structure(self):
        """Test: Reject proof with invalid structure"""
        invalid_proofs = [
            {},  # Empty
            {'version': '1.0'},  # Missing fields
            {'version': '2.0', 'transaction_hash': '0x123', 'flag_commitment': '0xabc', 'proof_data': {}},  # Wrong version
        ]

        for invalid_proof in invalid_proofs:
            is_valid = self.zkp_service.verify_anomaly_proof(invalid_proof)
            self.assertFalse(is_valid, f"Invalid proof should not verify: {invalid_proof}")

    # ===== Test 3: Opening Verification (Private Chain) =====

    def test_verify_with_opening_flagged(self):
        """Test: Verify proof opens to flag=1 (flagged)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xflagged",
            anomaly_score=85.0,
            anomaly_flags=['STRUCTURING'],
            requires_investigation=True
        )

        # Should open to flag=1
        is_valid = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
        self.assertTrue(is_valid, "Should open to flag=1")

        # Should not open to flag=0
        is_invalid = self.zkp_service.verify_with_opening(proof, expected_flag_value=0)
        self.assertFalse(is_invalid, "Should not open to flag=0")

    def test_verify_with_opening_not_flagged(self):
        """Test: Verify proof opens to flag=0 (not flagged)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnot_flagged",
            anomaly_score=45.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # Should open to flag=0
        is_valid = self.zkp_service.verify_with_opening(proof, expected_flag_value=0)
        self.assertTrue(is_valid, "Should open to flag=0")

        # Should not open to flag=1
        is_invalid = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
        self.assertFalse(is_invalid, "Should not open to flag=1")

    def test_verify_with_opening_tampered_witness(self):
        """Test: Detect tampered witness data"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xtest",
            anomaly_score=70.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # Tamper with witness
        tampered_proof = proof.copy()
        tampered_proof['witness'] = tampered_proof['witness'].copy()
        tampered_proof['witness']['flag_value'] = 0  # Change flag

        is_valid = self.zkp_service.verify_with_opening(tampered_proof, expected_flag_value=0)
        self.assertFalse(is_valid, "Tampered witness should not verify")

    # ===== Test 4: Extract Anomaly Details =====

    def test_extract_anomaly_details(self):
        """Test: Extract anomaly details from proof witness"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xdetails",
            anomaly_score=78.5,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'VELOCITY'],
            requires_investigation=True
        )

        details = self.zkp_service.extract_anomaly_details(proof)

        self.assertEqual(details['flag_value'], 1)
        self.assertEqual(details['anomaly_score'], 78.5)
        self.assertIn('HIGH_VALUE_TIER_1', details['anomaly_flags'])
        self.assertIn('VELOCITY', details['anomaly_flags'])
        self.assertTrue(details['requires_investigation'])

    def test_extract_details_non_flagged(self):
        """Test: Extract details for non-flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnormal",
            anomaly_score=20.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        details = self.zkp_service.extract_anomaly_details(proof)

        self.assertEqual(details['flag_value'], 0)
        self.assertEqual(details['anomaly_score'], 20.0)
        self.assertEqual(details['anomaly_flags'], [])
        self.assertFalse(details['requires_investigation'])

    # ===== Test 5: Commitment Hiding =====

    def test_commitment_hiding_property(self):
        """Test: Different proofs for same transaction have different commitments"""
        # Generate two proofs for same transaction
        proof_a = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xsame",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        proof_b = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xsame",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # Commitments should be different (different blinding factors)
        self.assertNotEqual(
            proof_a['flag_commitment'],
            proof_b['flag_commitment'],
            "Commitments should hide flag value with different randomness"
        )

        # But both should verify correctly
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_a))
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_b))

    def test_same_flag_different_scores_different_commitments(self):
        """Test: Same flag value but different scores produce different commitments"""
        proof_score_70 = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xhash1",
            anomaly_score=70.0,
            anomaly_flags=['FLAG_A'],
            requires_investigation=True
        )

        proof_score_80 = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xhash2",
            anomaly_score=80.0,
            anomaly_flags=['FLAG_B'],
            requires_investigation=True
        )

        # Both have flag=1, but different commitments
        self.assertEqual(proof_score_70['witness']['flag_value'], 1)
        self.assertEqual(proof_score_80['witness']['flag_value'], 1)
        self.assertNotEqual(proof_score_70['flag_commitment'], proof_score_80['flag_commitment'])

    # ===== Test 6: Transaction Hash Binding =====

    def test_proof_binds_to_transaction_hash(self):
        """Test: Proof is cryptographically bound to transaction hash"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xbound_hash",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # Verify transaction hash is embedded in proof
        self.assertEqual(proof['transaction_hash'], "0xbound_hash")

        # Changing transaction hash should fail verification
        proof_modified = proof.copy()
        proof_modified['transaction_hash'] = "0xdifferent_hash"

        is_valid = self.zkp_service.verify_anomaly_proof(proof_modified)
        self.assertFalse(is_valid, "Changing transaction hash should invalidate proof")

    # ===== Test 7: Proof Size =====

    def test_proof_size_is_compact(self):
        """Test: ZKP proof size is reasonable (< 1KB for public proof)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xsize_test",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        # Full proof (with witness)
        full_proof_json = json.dumps(proof)
        full_size = len(full_proof_json.encode('utf-8'))

        # Public proof (without witness - what goes on public chain)
        public_proof = {k: v for k, v in proof.items() if k != 'witness'}
        public_proof_json = json.dumps(public_proof)
        public_size = len(public_proof_json.encode('utf-8'))

        # Public proof should be compact (< 1KB)
        self.assertLess(public_size, 1024, f"Public proof size {public_size} bytes should be < 1KB")

        # Full proof should be < 2KB
        self.assertLess(full_size, 2048, f"Full proof size {full_size} bytes should be < 2KB")

    # ===== Test 8: Edge Cases =====

    def test_proof_for_threshold_score(self):
        """Test: Proof for score exactly at threshold (65.0)"""
        # Score = 65.0 exactly (should be flagged)
        proof_at_threshold = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xthreshold",
            anomaly_score=65.0,
            anomaly_flags=['PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        self.assertEqual(proof_at_threshold['witness']['flag_value'], 1)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_at_threshold))

    def test_proof_for_zero_score(self):
        """Test: Proof for zero anomaly score"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xzero",
            anomaly_score=0.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        self.assertEqual(proof['witness']['flag_value'], 0)
        self.assertEqual(proof['witness']['anomaly_score'], 0.0)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    def test_proof_for_max_score(self):
        """Test: Proof for maximum anomaly score (100.0)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xmax",
            anomaly_score=100.0,
            anomaly_flags=['HIGH_VALUE_TIER_2', 'VELOCITY', 'STRUCTURING'],
            requires_investigation=True
        )

        self.assertEqual(proof['witness']['flag_value'], 1)
        self.assertEqual(proof['witness']['anomaly_score'], 100.0)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    def test_proof_with_empty_flags(self):
        """Test: Proof with empty anomaly flags list"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xno_flags",
            anomaly_score=25.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        self.assertEqual(proof['witness']['anomaly_flags'], [])
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    def test_proof_with_many_flags(self):
        """Test: Proof with many anomaly flags"""
        many_flags = [
            'HIGH_VALUE_TIER_1',
            'HIGH_VALUE_TIER_2',
            'PMLA_MANDATORY_REPORTING',
            'HIGH_VELOCITY_1H_10',
            'STRUCTURING_DETECTED_3_TXS'
        ]

        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xmany_flags",
            anomaly_score=95.0,
            anomaly_flags=many_flags,
            requires_investigation=True
        )

        self.assertEqual(len(proof['witness']['anomaly_flags']), 5)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    # ===== Test 9: Security Properties =====

    def test_cannot_forge_proof_for_non_flagged(self):
        """Test: Cannot create valid proof claiming non-flagged tx is flagged"""
        # Create proof for non-flagged transaction
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnot_flagged",
            anomaly_score=40.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # Try to claim it's flagged by tampering witness
        tampered = proof.copy()
        tampered['witness'] = tampered['witness'].copy()
        tampered['witness']['flag_value'] = 1  # Claim it's flagged

        # Opening verification should fail
        is_valid = self.zkp_service.verify_with_opening(tampered, expected_flag_value=1)
        self.assertFalse(is_valid, "Should not be able to forge flagged proof")

    def test_proof_completeness(self):
        """Test: All valid flagged transactions can generate valid proofs"""
        # Various flagged scenarios
        test_cases = [
            (65.0, ['PMLA_MANDATORY_REPORTING']),
            (70.0, ['HIGH_VALUE_TIER_1']),
            (85.0, ['HIGH_VALUE_TIER_2', 'VELOCITY']),
            (100.0, ['HIGH_VALUE_TIER_2', 'VELOCITY', 'STRUCTURING'])
        ]

        for score, flags in test_cases:
            proof = self.zkp_service.generate_anomaly_proof(
                transaction_hash=f"0xtest_{score}",
                anomaly_score=score,
                anomaly_flags=flags,
                requires_investigation=True
            )

            # All should generate valid proofs
            is_valid = self.zkp_service.verify_anomaly_proof(proof)
            self.assertTrue(is_valid, f"Should generate valid proof for score {score}")

            # All should open correctly
            opens_correctly = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
            self.assertTrue(opens_correctly, f"Should open correctly for score {score}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
