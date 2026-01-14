"""
Unit Tests for Anomaly Threshold Encryption Service
Purpose: Test threshold encryption for anomaly-flagged transaction details

Test Coverage:
- Transaction details encryption
- Key splitting (6 authorities)
- Decryption with valid key combinations
- Access structure enforcement (Company + Supreme Court + 1-of-4)
- Security properties (perfect secrecy, threshold security)
- Edge cases and error handling
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from decimal import Decimal

from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption


class TestAnomalyThresholdEncryption(unittest.TestCase):
    """Test Anomaly Threshold Encryption Service"""

    def setUp(self):
        """Set up test environment"""
        self.enc = AnomalyThresholdEncryption()

    def _normalize_encrypted(self, encrypted):
        """Normalize return value from encrypt_transaction_details.

        Newer API returns {'encrypted_package': {...}, 'key_shares': {...}}.
        This helper returns (encrypted_package, key_shares) for tests.
        """
        if isinstance(encrypted, dict) and 'encrypted_package' in encrypted:
            return encrypted['encrypted_package'], encrypted.get('key_shares', {})
        # Backward-compat: return as-is
        return encrypted, encrypted.get('key_shares', {})

    # ===== Test 1: Encryption =====

    def test_encrypt_transaction_details(self):
        """Test: Encrypt transaction details"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest123",
            sender_idx="IDX_SENDER",
            receiver_idx="IDX_RECEIVER",
            amount=Decimal('10000000.00'),
            anomaly_score=85.5,
            anomaly_flags=['HIGH_VALUE_TIER_2']
        )

        # Normalize API (encrypted_package, key_shares)
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        # Verify structure
        self.assertIn('version', encrypted_package)
        self.assertIn('encrypted_details', encrypted_package)
        self.assertIn('transaction_hash', encrypted_package)
        self.assertEqual(encrypted_package['threshold'], 3)

        # Verify all 6 key shares created (out-of-band)
        self.assertEqual(len(key_shares), 6)
        self.assertIn('company', key_shares)
        self.assertIn('supreme_court', key_shares)
        self.assertIn('rbi', key_shares)
        self.assertIn('fiu', key_shares)
        self.assertIn('cbi', key_shares)
        self.assertIn('income_tax', key_shares)

    # ===== Test 2: Decryption with Valid Shares =====

    def test_decrypt_with_company_court_rbi(self):
        """Test: Decrypt with Company + Supreme Court + RBI"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xabc123",
            sender_idx="IDX_SENDER_1",
            receiver_idx="IDX_RECEIVER_1",
            amount=Decimal('5000000.00'),
            anomaly_score=70.0,
            anomaly_flags=['HIGH_VALUE_TIER_1']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['rbi']
            ]
        )

        # Verify decrypted data
        self.assertEqual(decrypted['transaction_hash'], "0xabc123")
        self.assertEqual(decrypted['sender_idx'], "IDX_SENDER_1")
        self.assertEqual(decrypted['receiver_idx'], "IDX_RECEIVER_1")
        self.assertEqual(decrypted['amount'], '5000000.00')
        self.assertEqual(decrypted['anomaly_score'], 70.0)
        self.assertIn('HIGH_VALUE_TIER_1', decrypted['anomaly_flags'])

    def test_decrypt_with_company_court_fiu(self):
        """Test: Decrypt with Company + Supreme Court + FIU"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xdef456",
            sender_idx="IDX_S2",
            receiver_idx="IDX_R2",
            amount=Decimal('7500000.00'),
            anomaly_score=80.0,
            anomaly_flags=['VELOCITY']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['fiu']
            ]
        )

        self.assertEqual(decrypted['transaction_hash'], "0xdef456")
        self.assertEqual(decrypted['anomaly_score'], 80.0)

    def test_decrypt_with_company_court_cbi(self):
        """Test: Decrypt with Company + Supreme Court + CBI"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xghi789",
            sender_idx="IDX_S3",
            receiver_idx="IDX_R3",
            amount=Decimal('9000000.00'),
            anomaly_score=90.0,
            anomaly_flags=['STRUCTURING']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['cbi']
            ]
        )

        self.assertEqual(decrypted['transaction_hash'], "0xghi789")
        self.assertEqual(decrypted['anomaly_score'], 90.0)

    def test_decrypt_with_company_court_income_tax(self):
        """Test: Decrypt with Company + Supreme Court + Income Tax"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xjkl012",
            sender_idx="IDX_S4",
            receiver_idx="IDX_R4",
            amount=Decimal('12000000.00'),
            anomaly_score=95.0,
            anomaly_flags=['HIGH_VALUE_TIER_2', 'VELOCITY']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['income_tax']
            ]
        )

        self.assertEqual(decrypted['transaction_hash'], "0xjkl012")
        self.assertEqual(decrypted['anomaly_score'], 95.0)

    # ===== Test 3: Access Control =====

    def test_fail_without_company(self):
        """Test: Decryption fails without Company (mandatory)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest",
            sender_idx="IDX_S",
            receiver_idx="IDX_R",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['supreme_court'],
                    key_shares['rbi'],
                    key_shares['fiu']
                ]
            )

        self.assertIn("Company", str(context.exception))

    def test_fail_without_supreme_court(self):
        """Test: Decryption fails without Supreme Court (mandatory)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest",
            sender_idx="IDX_S",
            receiver_idx="IDX_R",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['rbi'],
                    key_shares['fiu']
                ]
            )

        self.assertIn("Supreme Court", str(context.exception))

    def test_fail_without_optional_share(self):
        """Test: Decryption fails with only mandatory shares (no optional)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest",
            sender_idx="IDX_S",
            receiver_idx="IDX_R",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        # Normalize API shape
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['supreme_court']
                ]
            )

        self.assertIn("Invalid access structure", str(context.exception))

    def test_fail_with_only_2_shares(self):
        """Test: Decryption fails with only 2 shares"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest",
            sender_idx="IDX_S",
            receiver_idx="IDX_R",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        with self.assertRaises(ValueError):
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['rbi']
                ]
            )

    # ===== Test 4: Share Management =====

    def test_get_share_for_authority(self):
        """Test: Get share for specific authority"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xtest",
            sender_idx="IDX_S",
            receiver_idx="IDX_R",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )
        # Get RBI share
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        rbi_share = self.enc.get_share_for_authority(key_shares, 'rbi')
        self.assertEqual(rbi_share['holder'], 'rbi')
        self.assertEqual(rbi_share['holder_id'], 3)
        self.assertFalse(rbi_share['is_mandatory'])

        # Get company share
        company_share = self.enc.get_share_for_authority(key_shares, 'company')
        self.assertEqual(company_share['holder'], 'company')
        self.assertTrue(company_share['is_mandatory'])

    def test_list_required_authorities(self):
        """Test: List required authorities for decryption"""
        authorities = self.enc.list_required_authorities()

        self.assertIn('company', authorities['mandatory'])
        self.assertIn('supreme_court', authorities['mandatory'])
        self.assertIn('rbi', authorities['optional'])
        self.assertIn('fiu', authorities['optional'])
        self.assertIn('cbi', authorities['optional'])
        self.assertIn('income_tax', authorities['optional'])

    # ===== Test 5: Security Properties =====

    def test_encryption_produces_different_ciphertext(self):
        """Test: Same data produces different ciphertext (randomized)"""
        # Encrypt same data twice
        encrypted1 = self.enc.encrypt_transaction_details(
            transaction_hash="0xsame",
            sender_idx="IDX_SAME",
            receiver_idx="IDX_SAME",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        encrypted2 = self.enc.encrypt_transaction_details(
            transaction_hash="0xsame",
            sender_idx="IDX_SAME",
            receiver_idx="IDX_SAME",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        # Ciphertext should be different (due to random encryption key)
        ep1, ks1 = self._normalize_encrypted(encrypted1)
        ep2, ks2 = self._normalize_encrypted(encrypted2)
        self.assertNotEqual(
            ep1['encrypted_details'],
            ep2['encrypted_details']
        )

        # But both should decrypt correctly
        ep1, ks1 = self._normalize_encrypted(encrypted1)
        ep2, ks2 = self._normalize_encrypted(encrypted2)

        decrypted1 = self.enc.decrypt_transaction_details(
            ep1,
            [
                ks1['company'],
                ks1['supreme_court'],
                ks1['rbi']
            ]
        )

        decrypted2 = self.enc.decrypt_transaction_details(
            ep2,
            [
                ks2['company'],
                ks2['supreme_court'],
                ks2['rbi']
            ]
        )

        # Both should have same plaintext
        self.assertEqual(decrypted1['transaction_hash'], decrypted2['transaction_hash'])
        self.assertEqual(decrypted1['amount'], decrypted2['amount'])

    def test_perfect_secrecy_2_shares_reveal_nothing(self):
        """Test: 2 shares alone cannot decrypt (perfect secrecy)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xsecret",
            sender_idx="IDX_SECRET",
            receiver_idx="IDX_SECRET",
            amount=Decimal('10000000.00'),
            anomaly_score=85.0,
            anomaly_flags=['HIGH_VALUE']
        )

        # Try with only 2 shares - should fail
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        with self.assertRaises(ValueError):
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['supreme_court']
                ]
            )

    # ===== Test 6: Edge Cases =====

    def test_encrypt_large_amount(self):
        """Test: Encrypt very large amount (₹100 crore)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xlarge",
            sender_idx="IDX_LARGE",
            receiver_idx="IDX_RCV",
            amount=Decimal('1000000000.00'),  # ₹100 crore
            anomaly_score=100.0,
            anomaly_flags=['HIGH_VALUE_TIER_2', 'PMLA_MANDATORY_REPORTING']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['rbi']
            ]
        )

        self.assertEqual(decrypted['amount'], '1000000000.00')
        self.assertEqual(decrypted['anomaly_score'], 100.0)

    def test_encrypt_small_amount(self):
        """Test: Encrypt small amount (₹10 lakh - threshold)"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xsmall",
            sender_idx="IDX_SMALL",
            receiver_idx="IDX_RCV",
            amount=Decimal('1000000.00'),  # ₹10 lakh
            anomaly_score=65.0,  # Exactly at threshold
            anomaly_flags=['PMLA_MANDATORY_REPORTING']
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['fiu']
            ]
        )

        self.assertEqual(decrypted['amount'], '1000000.00')
        self.assertEqual(decrypted['anomaly_score'], 65.0)

    def test_encrypt_with_many_flags(self):
        """Test: Encrypt transaction with multiple anomaly flags"""
        many_flags = [
            'HIGH_VALUE_TIER_2',
            'PMLA_MANDATORY_REPORTING',
            'HIGH_VELOCITY_1H_10',
            'STRUCTURING_DETECTED_3_TXS'
        ]

        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xmany",
            sender_idx="IDX_MANY",
            receiver_idx="IDX_RCV",
            amount=Decimal('15000000.00'),
            anomaly_score=95.0,
            anomaly_flags=many_flags
        )

        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['cbi']
            ]
        )

        self.assertEqual(len(decrypted['anomaly_flags']), 4)
        for flag in many_flags:
            self.assertIn(flag, decrypted['anomaly_flags'])

    # ===== Test 7: Share Metadata =====

    def test_share_has_correct_metadata(self):
        """Test: Each share has correct metadata"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xmeta",
            sender_idx="IDX_META",
            receiver_idx="IDX_RCV",
            amount=Decimal('5000000.00'),
            anomaly_score=75.0,
            anomaly_flags=['HIGH_VALUE']
        )

        # Check company share (mandatory)
        _, key_shares = self._normalize_encrypted(encrypted)
        company = key_shares['company']
        self.assertEqual(company['holder'], 'company')
        self.assertEqual(company['threshold'], 3)
        self.assertTrue(company['is_mandatory'])

        # Check RBI share (optional)
        rbi = key_shares['rbi']
        self.assertEqual(rbi['holder'], 'rbi')
        self.assertEqual(rbi['threshold'], 3)
        self.assertFalse(rbi['is_mandatory'])

    # ===== Test 8: Different Authority Combinations =====

    def test_all_valid_combinations(self):
        """Test: All valid authority combinations can decrypt"""
        encrypted = self.enc.encrypt_transaction_details(
            transaction_hash="0xcombos",
            sender_idx="IDX_COMBO",
            receiver_idx="IDX_RCV",
            amount=Decimal('8000000.00'),
            anomaly_score=80.0,
            anomaly_flags=['HIGH_VALUE']
        )

        # Valid combinations: Company + Supreme Court + any 1 of 4 optional
        valid_combinations = [
            ['company', 'supreme_court', 'rbi'],
            ['company', 'supreme_court', 'fiu'],
            ['company', 'supreme_court', 'cbi'],
            ['company', 'supreme_court', 'income_tax']
        ]

        for combo in valid_combinations:
            ep, ks = self._normalize_encrypted(encrypted)
            shares = [ks[authority] for authority in combo]
            decrypted = self.enc.decrypt_transaction_details(ep, shares)

            self.assertEqual(decrypted['transaction_hash'], "0xcombos")
            self.assertEqual(decrypted['anomaly_score'], 80.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
