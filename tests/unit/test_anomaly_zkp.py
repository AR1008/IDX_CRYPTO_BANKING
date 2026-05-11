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

# [DOC] sys/os: needed to make the project root importable from within the tests/ subdirectory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# [DOC] unittest: standard Python test framework used for all unit tests here
import unittest
# [DOC] json: used to serialise proof objects so their byte sizes can be measured
import json
# [DOC] Decimal: financial amounts must be exact; float arithmetic would introduce rounding errors
from decimal import Decimal

# [DOC] AnomalyZKPService: the class under test — generates and verifies Schnorr-based ZKPs
from core.crypto.anomaly_zkp import AnomalyZKPService


# [DOC] TestAnomalyZKPService: groups all unit tests for the zero-knowledge proof subsystem
class TestAnomalyZKPService(unittest.TestCase):
    """Test Anomaly ZKP Service"""

    # [DOC] setUp: runs before each test method; creates a fresh ZKP service instance so tests are isolated
    def setUp(self):
        """Set up test environment"""
        self.zkp_service = AnomalyZKPService()

    # ===== Test 1: Proof Generation =====

    # [DOC] test_generate_proof_for_flagged_transaction: proves that a flagged transaction produces
    # [DOC] a structurally complete proof containing commitment, challenge, response, and witness fields
    def test_generate_proof_for_flagged_transaction(self):
        """Test: Generate ZKP proof for flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xabc123def456",
            anomaly_score=75.5,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        # [DOC] Verify the top-level proof envelope exists with required fields
        self.assertIn('version', proof)
        self.assertIn('transaction_hash', proof)
        self.assertIn('flag_commitment', proof)
        self.assertIn('timestamp', proof)
        self.assertIn('proof_data', proof)
        self.assertIn('witness', proof)

        # [DOC] Verify proof_data contains the three Schnorr sigma-protocol components
        self.assertIn('nonce_commitment', proof['proof_data'])
        self.assertIn('challenge', proof['proof_data'])
        self.assertIn('response', proof['proof_data'])

        # [DOC] Witness stores private data (flag value, score, flags) — lives only on private chain
        self.assertEqual(proof['witness']['flag_value'], 1)
        self.assertEqual(proof['witness']['anomaly_score'], 75.5)
        self.assertIn('HIGH_VALUE_TIER_1', proof['witness']['anomaly_flags'])

    # [DOC] test_generate_proof_for_non_flagged_transaction: proves a normal transaction
    # [DOC] produces flag_value=0 and an empty flags list in the witness
    def test_generate_proof_for_non_flagged_transaction(self):
        """Test: Generate ZKP proof for non-flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xdef789ghi012",
            anomaly_score=30.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # [DOC] flag_value=0 means the commitment encodes "not suspicious"; witness confirms score and empty flags
        self.assertEqual(proof['witness']['flag_value'], 0)
        self.assertEqual(proof['witness']['anomaly_score'], 30.0)
        self.assertEqual(proof['witness']['anomaly_flags'], [])

    # ===== Test 2: Proof Verification =====

    # [DOC] test_verify_valid_proof: proves that an honestly generated proof passes the verifier,
    # [DOC] i.e., completeness property of the Schnorr protocol holds
    def test_verify_valid_proof(self):
        """Test: Verify valid ZKP proof"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xtest123",
            anomaly_score=80.0,
            anomaly_flags=['HIGH_VALUE_TIER_2'],
            requires_investigation=True
        )

        # [DOC] A legitimately generated proof must always verify — completeness invariant
        is_valid = self.zkp_service.verify_anomaly_proof(proof)
        self.assertTrue(is_valid, "Valid proof should verify correctly")

    # [DOC] test_verify_proof_with_transaction_hash: proves that the proof is bound to a specific
    # [DOC] transaction hash; supplying a wrong hash must fail verification (soundness check)
    def test_verify_proof_with_transaction_hash(self):
        """Test: Verify proof with transaction hash check"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xspecific_hash",
            anomaly_score=70.0,
            anomaly_flags=['VELOCITY'],
            requires_investigation=True
        )

        # [DOC] Correct hash matches — proof should verify
        is_valid = self.zkp_service.verify_anomaly_proof(
            proof,
            expected_transaction_hash="0xspecific_hash"
        )
        self.assertTrue(is_valid, "Proof should verify with correct hash")

        # [DOC] Wrong hash breaks the binding — verifier must reject
        is_invalid = self.zkp_service.verify_anomaly_proof(
            proof,
            expected_transaction_hash="0xwrong_hash"
        )
        self.assertFalse(is_invalid, "Proof should fail with wrong hash")

    # [DOC] test_verify_tampered_proof: proves that altering the flag_commitment after proof
    # [DOC] generation invalidates the proof — the verifier detects the tamper (soundness)
    def test_verify_tampered_proof(self):
        """Test: Detect tampered proof"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xoriginal",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # [DOC] Replace commitment with all-zero garbage to simulate an attacker
        tampered_proof = proof.copy()
        tampered_proof['flag_commitment'] = '0x' + '0' * 64

        # [DOC] Verifier must reject: tampered commitment breaks the Schnorr equation
        is_valid = self.zkp_service.verify_anomaly_proof(tampered_proof)
        self.assertFalse(is_valid, "Tampered proof should not verify")

    # [DOC] test_verify_invalid_proof_structure: proves the verifier safely rejects
    # [DOC] incomplete or wrong-version proof objects without crashing
    def test_verify_invalid_proof_structure(self):
        """Test: Reject proof with invalid structure"""
        invalid_proofs = [
            {},  # Empty
            {'version': '1.0'},  # Missing fields
            {'version': '2.0', 'transaction_hash': '0x123', 'flag_commitment': '0xabc', 'proof_data': {}},  # Wrong version
        ]

        # [DOC] Every malformed input must return False, never raise an unhandled exception
        for invalid_proof in invalid_proofs:
            is_valid = self.zkp_service.verify_anomaly_proof(invalid_proof)
            self.assertFalse(is_valid, f"Invalid proof should not verify: {invalid_proof}")

    # ===== Test 3: Opening Verification (Private Chain) =====

    # [DOC] test_verify_with_opening_flagged: proves that a flagged proof opens correctly to flag=1
    # [DOC] and is rejected when opened against flag=0 — soundness of the commitment opening
    def test_verify_with_opening_flagged(self):
        """Test: Verify proof opens to flag=1 (flagged)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xflagged",
            anomaly_score=85.0,
            anomaly_flags=['STRUCTURING'],
            requires_investigation=True
        )

        # [DOC] Opening with the correct flag value must succeed
        is_valid = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
        self.assertTrue(is_valid, "Should open to flag=1")

        # [DOC] Opening with the wrong flag value must fail — binding property of the commitment
        is_invalid = self.zkp_service.verify_with_opening(proof, expected_flag_value=0)
        self.assertFalse(is_invalid, "Should not open to flag=0")

    # [DOC] test_verify_with_opening_not_flagged: mirrors the flagged test for flag=0;
    # [DOC] ensures a clean transaction cannot be falsely opened as flagged
    def test_verify_with_opening_not_flagged(self):
        """Test: Verify proof opens to flag=0 (not flagged)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnot_flagged",
            anomaly_score=45.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # [DOC] Should open to flag=0
        is_valid = self.zkp_service.verify_with_opening(proof, expected_flag_value=0)
        self.assertTrue(is_valid, "Should open to flag=0")

        # [DOC] Should not open to flag=1
        is_invalid = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
        self.assertFalse(is_invalid, "Should not open to flag=1")

    # [DOC] test_verify_with_opening_tampered_witness: proves that overwriting the witness's flag_value
    # [DOC] after proof generation is detected during opening — the commitment is binding
    def test_verify_with_opening_tampered_witness(self):
        """Test: Detect tampered witness data"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xtest",
            anomaly_score=70.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # [DOC] Attacker flips flag_value in the witness hoping the verifier trusts the witness directly
        tampered_proof = proof.copy()
        tampered_proof['witness'] = tampered_proof['witness'].copy()
        tampered_proof['witness']['flag_value'] = 0  # Change flag

        # [DOC] Opening must fail because commitment was made to flag=1, not flag=0
        is_valid = self.zkp_service.verify_with_opening(tampered_proof, expected_flag_value=0)
        self.assertFalse(is_valid, "Tampered witness should not verify")

    # ===== Test 4: Extract Anomaly Details =====

    # [DOC] test_extract_anomaly_details: proves that the service can read back score, flags, and
    # [DOC] investigation status from the witness stored on the private chain
    def test_extract_anomaly_details(self):
        """Test: Extract anomaly details from proof witness"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xdetails",
            anomaly_score=78.5,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'VELOCITY'],
            requires_investigation=True
        )

        # [DOC] extract_anomaly_details reads from the private-chain witness section
        details = self.zkp_service.extract_anomaly_details(proof)

        # [DOC] All fields that were put in must come back out unchanged
        self.assertEqual(details['flag_value'], 1)
        self.assertEqual(details['anomaly_score'], 78.5)
        self.assertIn('HIGH_VALUE_TIER_1', details['anomaly_flags'])
        self.assertIn('VELOCITY', details['anomaly_flags'])
        self.assertTrue(details['requires_investigation'])

    # [DOC] test_extract_details_non_flagged: confirms extraction works for non-flagged transactions
    # [DOC] where flag_value=0 and requires_investigation=False
    def test_extract_details_non_flagged(self):
        """Test: Extract details for non-flagged transaction"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnormal",
            anomaly_score=20.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        details = self.zkp_service.extract_anomaly_details(proof)

        # [DOC] Zero score, empty flags, and False investigation flag must be faithfully preserved
        self.assertEqual(details['flag_value'], 0)
        self.assertEqual(details['anomaly_score'], 20.0)
        self.assertEqual(details['anomaly_flags'], [])
        self.assertFalse(details['requires_investigation'])

    # ===== Test 5: Commitment Hiding =====

    # [DOC] test_commitment_hiding_property: proves the hiding property of the Pedersen-style commitment;
    # [DOC] two proofs for the same transaction must produce different commitments due to fresh randomness
    def test_commitment_hiding_property(self):
        """Test: Different proofs for same transaction have different commitments"""
        # [DOC] Generate two proofs with identical inputs; randomness comes from the blinding factor
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

        # [DOC] Commitments differ due to independent randomness — hiding property holds
        self.assertNotEqual(
            proof_a['flag_commitment'],
            proof_b['flag_commitment'],
            "Commitments should hide flag value with different randomness"
        )

        # [DOC] Both proofs must still verify — completeness holds despite different randomness
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_a))
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_b))

    # [DOC] test_same_flag_different_scores_different_commitments: proves that differing anomaly
    # [DOC] scores produce distinct commitments even when both transactions are flagged (flag=1)
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

        # [DOC] Both are flag=1 but must have different commitments since scores differ
        self.assertEqual(proof_score_70['witness']['flag_value'], 1)
        self.assertEqual(proof_score_80['witness']['flag_value'], 1)
        self.assertNotEqual(proof_score_70['flag_commitment'], proof_score_80['flag_commitment'])

    # ===== Test 6: Transaction Hash Binding =====

    # [DOC] test_proof_binds_to_transaction_hash: proves that modifying the tx_hash field
    # [DOC] after proof generation breaks verification — the hash is baked into the challenge
    def test_proof_binds_to_transaction_hash(self):
        """Test: Proof is cryptographically bound to transaction hash"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xbound_hash",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE'],
            requires_investigation=True
        )

        # [DOC] The proof envelope must record the original tx hash
        self.assertEqual(proof['transaction_hash'], "0xbound_hash")

        # [DOC] Swapping the hash in the envelope must invalidate the proof
        proof_modified = proof.copy()
        proof_modified['transaction_hash'] = "0xdifferent_hash"

        # [DOC] Verifier recomputes the challenge using the embedded hash; mismatch fails
        is_valid = self.zkp_service.verify_anomaly_proof(proof_modified)
        self.assertFalse(is_valid, "Changing transaction hash should invalidate proof")

    # ===== Test 7: Proof Size =====

    # [DOC] test_proof_size_is_compact: verifies that the public proof (without witness) stays
    # [DOC] under 1 KB, making it practical to store on-chain alongside each transaction
    def test_proof_size_is_compact(self):
        """Test: ZKP proof size is reasonable (< 1KB for public proof)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xsize_test",
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE_TIER_1', 'PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        # [DOC] Full proof includes the private witness; public proof strips it before on-chain storage
        full_proof_json = json.dumps(proof)
        full_size = len(full_proof_json.encode('utf-8'))

        # [DOC] Public proof = everything except witness — this goes on the public blockchain
        public_proof = {k: v for k, v in proof.items() if k != 'witness'}
        public_proof_json = json.dumps(public_proof)
        public_size = len(public_proof_json.encode('utf-8'))

        # [DOC] Public proof must fit in 1 KB so block space is not wasted
        self.assertLess(public_size, 1024, f"Public proof size {public_size} bytes should be < 1KB")

        # [DOC] Full proof (with private witness) must fit in 2 KB
        self.assertLess(full_size, 2048, f"Full proof size {full_size} bytes should be < 2KB")

    # ===== Test 8: Edge Cases =====

    # [DOC] test_proof_for_threshold_score: edge-case test for score exactly equal to 65 (flag boundary);
    # [DOC] ensures transactions at the exact threshold are correctly treated as flagged
    def test_proof_for_threshold_score(self):
        """Test: Proof for score exactly at threshold (65.0)"""
        # [DOC] Score = 65.0 exactly (should be flagged)
        proof_at_threshold = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xthreshold",
            anomaly_score=65.0,
            anomaly_flags=['PMLA_MANDATORY_REPORTING'],
            requires_investigation=True
        )

        # [DOC] At-threshold transactions must have flag_value=1 and a valid proof
        self.assertEqual(proof_at_threshold['witness']['flag_value'], 1)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof_at_threshold))

    # [DOC] test_proof_for_zero_score: edge case for the minimum possible anomaly score (0);
    # [DOC] the system must not crash and must mark the transaction as not flagged
    def test_proof_for_zero_score(self):
        """Test: Proof for zero anomaly score"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xzero",
            anomaly_score=0.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # [DOC] Zero score must produce flag_value=0 and still verify correctly
        self.assertEqual(proof['witness']['flag_value'], 0)
        self.assertEqual(proof['witness']['anomaly_score'], 0.0)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    # [DOC] test_proof_for_max_score: edge case for the maximum anomaly score (100);
    # [DOC] ensures proof generation and verification still work at the upper bound
    def test_proof_for_max_score(self):
        """Test: Proof for maximum anomaly score (100.0)"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xmax",
            anomaly_score=100.0,
            anomaly_flags=['HIGH_VALUE_TIER_2', 'VELOCITY', 'STRUCTURING'],
            requires_investigation=True
        )

        # [DOC] Maximum score must produce flag_value=1 and verify correctly
        self.assertEqual(proof['witness']['flag_value'], 1)
        self.assertEqual(proof['witness']['anomaly_score'], 100.0)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    # [DOC] test_proof_with_empty_flags: verifies that a non-zero score with an empty flags list
    # [DOC] is handled gracefully — the service should not error on an empty list
    def test_proof_with_empty_flags(self):
        """Test: Proof with empty anomaly flags list"""
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xno_flags",
            anomaly_score=25.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # [DOC] Empty flags list must round-trip cleanly through the proof
        self.assertEqual(proof['witness']['anomaly_flags'], [])
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    # [DOC] test_proof_with_many_flags: verifies that a large flags list (5 items) is preserved
    # [DOC] completely in the witness without truncation or corruption
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

        # [DOC] All 5 flags must appear in the witness and the proof must verify
        self.assertEqual(len(proof['witness']['anomaly_flags']), 5)
        self.assertTrue(self.zkp_service.verify_anomaly_proof(proof))

    # ===== Test 9: Security Properties =====

    # [DOC] test_cannot_forge_proof_for_non_flagged: proves soundness — an attacker cannot
    # [DOC] take a non-flagged proof and falsely claim it opens to flag=1 by editing the witness
    def test_cannot_forge_proof_for_non_flagged(self):
        """Test: Cannot create valid proof claiming non-flagged tx is flagged"""
        # [DOC] Create a genuine proof for a non-flagged transaction
        proof = self.zkp_service.generate_anomaly_proof(
            transaction_hash="0xnot_flagged",
            anomaly_score=40.0,
            anomaly_flags=[],
            requires_investigation=False
        )

        # [DOC] Attacker modifies the witness to claim flag=1 (pretending transaction is suspicious)
        tampered = proof.copy()
        tampered['witness'] = tampered['witness'].copy()
        tampered['witness']['flag_value'] = 1  # Claim it's flagged

        # [DOC] Opening verification must catch the inconsistency: commitment encodes 0 but witness claims 1
        is_valid = self.zkp_service.verify_with_opening(tampered, expected_flag_value=1)
        self.assertFalse(is_valid, "Should not be able to forge flagged proof")

    # [DOC] test_proof_completeness: proves that all valid flagged scenarios (different scores/flag combos)
    # [DOC] produce proofs that both verify and open correctly — completeness holds universally
    def test_proof_completeness(self):
        """Test: All valid flagged transactions can generate valid proofs"""
        # [DOC] Four representative flagged scenarios covering different score ranges
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

            # [DOC] Verify: does the public proof satisfy the Schnorr equation?
            is_valid = self.zkp_service.verify_anomaly_proof(proof)
            self.assertTrue(is_valid, f"Should generate valid proof for score {score}")

            # [DOC] Open: does the commitment open correctly to flag=1?
            opens_correctly = self.zkp_service.verify_with_opening(proof, expected_flag_value=1)
            self.assertTrue(opens_correctly, f"Should open correctly for score {score}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
