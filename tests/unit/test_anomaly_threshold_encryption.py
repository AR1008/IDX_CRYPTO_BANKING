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

# [DOC] sys/os: needed to insert the project root into the Python path before any local imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# [DOC] unittest: standard Python test framework; all tests live in a TestCase subclass
import unittest
# [DOC] Decimal: financial amounts require exact representation; float would introduce rounding errors
from decimal import Decimal

# [DOC] AnomalyThresholdEncryption: the class under test — encrypts flagged tx details with AES-256-GCM
# [DOC] and splits the symmetric key using a 3-of-6 Shamir threshold scheme
from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption


# [DOC] TestAnomalyThresholdEncryption: groups all unit tests for the threshold encryption subsystem
class TestAnomalyThresholdEncryption(unittest.TestCase):
    """Test Anomaly Threshold Encryption Service"""

    # [DOC] setUp: instantiates a fresh AnomalyThresholdEncryption object before each test method
    def setUp(self):
        """Set up test environment"""
        self.enc = AnomalyThresholdEncryption()

    # [DOC] _normalize_encrypted: helper that accommodates two API shapes; newer API returns a wrapper
    # [DOC] dict with 'encrypted_package' and 'key_shares' keys — older tests receive the raw dict
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

    # [DOC] test_encrypt_transaction_details: proves that encrypting a flagged transaction produces
    # [DOC] a valid package with version, ciphertext, tx hash, threshold=3, and exactly 6 key shares
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

        # [DOC] Normalise the return value to unpack package and key shares regardless of API version
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)

        # [DOC] The encrypted package must contain metadata and the AES-GCM ciphertext
        self.assertIn('version', encrypted_package)
        self.assertIn('encrypted_details', encrypted_package)
        self.assertIn('transaction_hash', encrypted_package)
        # [DOC] threshold=3 means Company + Supreme Court + 1-of-4 regulatory authority required
        self.assertEqual(encrypted_package['threshold'], 3)

        # [DOC] All 6 key share holders must be present: company, supreme_court, and 4 regulatory bodies
        self.assertEqual(len(key_shares), 6)
        self.assertIn('company', key_shares)
        self.assertIn('supreme_court', key_shares)
        self.assertIn('rbi', key_shares)
        self.assertIn('fiu', key_shares)
        self.assertIn('cbi', key_shares)
        self.assertIn('income_tax', key_shares)

    # ===== Test 2: Decryption with Valid Shares =====

    # [DOC] test_decrypt_with_company_court_rbi: proves that Company + Supreme Court + RBI (one of the
    # [DOC] four optional regulators) is a valid combination that successfully decrypts the package
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

        # [DOC] POST to decryption endpoint with the three required shares
        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['rbi']
            ]
        )

        # [DOC] All original plaintext fields must survive the encrypt-decrypt round-trip unchanged
        self.assertEqual(decrypted['transaction_hash'], "0xabc123")
        self.assertEqual(decrypted['sender_idx'], "IDX_SENDER_1")
        self.assertEqual(decrypted['receiver_idx'], "IDX_RECEIVER_1")
        self.assertEqual(decrypted['amount'], '5000000.00')
        self.assertEqual(decrypted['anomaly_score'], 70.0)
        self.assertIn('HIGH_VALUE_TIER_1', decrypted['anomaly_flags'])

    # [DOC] test_decrypt_with_company_court_fiu: proves FIU (Financial Intelligence Unit) can be the
    # [DOC] optional third share — covers the FIU-triggered court order scenario
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

        # [DOC] FIU is authorised under PMLA §48 to request financial data — test that path
        decrypted = self.enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['supreme_court'],
                key_shares['fiu']
            ]
        )

        # [DOC] Verify that transaction hash and score survive the round-trip with FIU share
        self.assertEqual(decrypted['transaction_hash'], "0xdef456")
        self.assertEqual(decrypted['anomaly_score'], 80.0)

    # [DOC] test_decrypt_with_company_court_cbi: proves CBI (Central Bureau of Investigation) can be
    # [DOC] the optional third share — covers criminal investigation court order scenario
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

        # [DOC] CBI covers serious financial crime cases — verify decryption succeeds with their share
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

    # [DOC] test_decrypt_with_company_court_income_tax: proves the Income Tax authority can be the
    # [DOC] optional third share — covers tax evasion investigation scenario
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

        # [DOC] Income Tax authority has standing under I-T Act §133 — verify their share works
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

    # [DOC] test_fail_without_company: proves that omitting the Company share (mandatory) raises
    # [DOC] ValueError — the Company key is always required to prevent unilateral government access
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
        # [DOC] Attempt decryption with Supreme Court + RBI + FIU but NO Company share
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['supreme_court'],
                    key_shares['rbi'],
                    key_shares['fiu']
                ]
            )

        # [DOC] Error message must mention "Company" so the caller knows what is missing
        self.assertIn("Company", str(context.exception))

    # [DOC] test_fail_without_supreme_court: proves that omitting the Supreme Court share raises
    # [DOC] ValueError — the court's authorisation is mandatory to prevent executive overreach
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
        # [DOC] Attempt with Company + RBI + FIU but NO Supreme Court share
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['rbi'],
                    key_shares['fiu']
                ]
            )

        # [DOC] Error must identify the missing Supreme Court share
        self.assertIn("Supreme Court", str(context.exception))

    # [DOC] test_fail_without_optional_share: proves that providing only the two mandatory shares
    # [DOC] (Company + Supreme Court) is insufficient — the 1-of-4 optional regulator is also required
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

        # [DOC] Normalize API shape
        encrypted_package, key_shares = self._normalize_encrypted(encrypted)
        # [DOC] Only 2 of the 3 required shares are provided; should raise "Invalid access structure"
        with self.assertRaises(ValueError) as context:
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['supreme_court']
                ]
            )

        # [DOC] Error must indicate the access structure is not satisfied
        self.assertIn("Invalid access structure", str(context.exception))

    # [DOC] test_fail_with_only_2_shares: proves that any two-share combination (e.g. Company + RBI)
    # [DOC] that misses one mandatory share is rejected — threshold is strictly 3
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
        # [DOC] Company + RBI misses the Supreme Court — this combination must be rejected
        with self.assertRaises(ValueError):
            self.enc.decrypt_transaction_details(
                encrypted_package,
                [
                    key_shares['company'],
                    key_shares['rbi']
                ]
            )

    # ===== Test 4: Share Management =====

    # [DOC] test_get_share_for_authority: proves that individual authority shares can be retrieved
    # [DOC] and carry correct metadata: holder name, ID, and mandatory/optional flag
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
        # [DOC] Retrieve and verify the RBI share metadata
        _, key_shares = self._normalize_encrypted(encrypted)
        rbi_share = self.enc.get_share_for_authority(key_shares, 'rbi')
        self.assertEqual(rbi_share['holder'], 'rbi')
        # [DOC] RBI is holder_id=3 in the authority ordering; is_mandatory=False (optional share)
        self.assertEqual(rbi_share['holder_id'], 3)
        self.assertFalse(rbi_share['is_mandatory'])

        # [DOC] Retrieve and verify the Company share metadata
        company_share = self.enc.get_share_for_authority(key_shares, 'company')
        self.assertEqual(company_share['holder'], 'company')
        # [DOC] Company share is always mandatory — is_mandatory must be True
        self.assertTrue(company_share['is_mandatory'])

    # [DOC] test_list_required_authorities: proves the service can enumerate both mandatory
    # [DOC] and optional authority classes without requiring an encrypted package
    def test_list_required_authorities(self):
        """Test: List required authorities for decryption"""
        authorities = self.enc.list_required_authorities()

        # [DOC] Company and Supreme Court must always appear in the mandatory list
        self.assertIn('company', authorities['mandatory'])
        self.assertIn('supreme_court', authorities['mandatory'])
        # [DOC] All four regulatory bodies must appear in the optional list
        self.assertIn('rbi', authorities['optional'])
        self.assertIn('fiu', authorities['optional'])
        self.assertIn('cbi', authorities['optional'])
        self.assertIn('income_tax', authorities['optional'])

    # ===== Test 5: Security Properties =====

    # [DOC] test_encryption_produces_different_ciphertext: proves IND-CPA (randomised encryption);
    # [DOC] encrypting the same plaintext twice must produce different ciphertexts due to random AES nonce
    def test_encryption_produces_different_ciphertext(self):
        """Test: Same data produces different ciphertext (randomized)"""
        # [DOC] Encrypt identical plaintext twice to check for ciphertext diversity
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

        # [DOC] Ciphertexts must differ: AES-GCM uses a fresh random nonce each time (IND-CPA)
        ep1, ks1 = self._normalize_encrypted(encrypted1)
        ep2, ks2 = self._normalize_encrypted(encrypted2)
        self.assertNotEqual(
            ep1['encrypted_details'],
            ep2['encrypted_details']
        )

        # [DOC] Despite different ciphertexts, both packages must decrypt to the same plaintext
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

        # [DOC] Plaintexts must match even though ciphertexts differ — correctness invariant
        self.assertEqual(decrypted1['transaction_hash'], decrypted2['transaction_hash'])
        self.assertEqual(decrypted1['amount'], decrypted2['amount'])

    # [DOC] test_perfect_secrecy_2_shares_reveal_nothing: proves that only 2 of the 3 required shares
    # [DOC] are insufficient to decrypt — Shamir's information-theoretic security holds
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

        # [DOC] Company + Supreme Court is 2-of-3 required shares; must not decrypt (threshold not met)
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

    # [DOC] test_encrypt_large_amount: proves the encryption handles ₹100 crore (very large Decimal)
    # [DOC] without truncation or serialization errors
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

        # [DOC] The large decimal must round-trip as a string without scientific notation
        self.assertEqual(decrypted['amount'], '1000000000.00')
        self.assertEqual(decrypted['anomaly_score'], 100.0)

    # [DOC] test_encrypt_small_amount: proves the encryption handles a ₹10 lakh amount
    # [DOC] (the PMLA threshold) and that a score of exactly 65 is preserved
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

        # [DOC] Boundary score of 65.0 must be preserved exactly — no float precision loss
        self.assertEqual(decrypted['amount'], '1000000.00')
        self.assertEqual(decrypted['anomaly_score'], 65.0)

    # [DOC] test_encrypt_with_many_flags: proves that a list of 4 anomaly flags is serialised and
    # [DOC] deserialised completely without any flags being dropped or duplicated
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

        # [DOC] All 4 flags must survive the round-trip intact
        self.assertEqual(len(decrypted['anomaly_flags']), 4)
        for flag in many_flags:
            self.assertIn(flag, decrypted['anomaly_flags'])

    # ===== Test 7: Share Metadata =====

    # [DOC] test_share_has_correct_metadata: proves that each authority share carries
    # [DOC] the correct holder name, threshold value, and mandatory/optional classification
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

        # [DOC] Company share metadata check: threshold=3, is_mandatory=True
        _, key_shares = self._normalize_encrypted(encrypted)
        company = key_shares['company']
        self.assertEqual(company['holder'], 'company')
        self.assertEqual(company['threshold'], 3)
        self.assertTrue(company['is_mandatory'])

        # [DOC] RBI share metadata check: threshold=3, is_mandatory=False (optional regulator)
        rbi = key_shares['rbi']
        self.assertEqual(rbi['holder'], 'rbi')
        self.assertEqual(rbi['threshold'], 3)
        self.assertFalse(rbi['is_mandatory'])

    # ===== Test 8: Different Authority Combinations =====

    # [DOC] test_all_valid_combinations: proves that all four valid access combinations
    # [DOC] (Company + Court + each of the 4 optional regulators) successfully decrypt the package
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

        # [DOC] The RCTD access structure defines exactly 4 valid 3-party combinations
        valid_combinations = [
            ['company', 'supreme_court', 'rbi'],
            ['company', 'supreme_court', 'fiu'],
            ['company', 'supreme_court', 'cbi'],
            ['company', 'supreme_court', 'income_tax']
        ]

        # [DOC] Each combination must successfully decrypt and return the correct tx hash and score
        for combo in valid_combinations:
            ep, ks = self._normalize_encrypted(encrypted)
            shares = [ks[authority] for authority in combo]
            decrypted = self.enc.decrypt_transaction_details(ep, shares)

            self.assertEqual(decrypted['transaction_hash'], "0xcombos")
            self.assertEqual(decrypted['anomaly_score'], 80.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
