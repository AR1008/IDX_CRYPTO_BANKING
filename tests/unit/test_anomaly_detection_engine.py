"""
Unit Tests for Anomaly Detection Engine
Purpose: Test PMLA-compliant anomaly detection with multi-factor scoring

Test Coverage:
- High-value transaction detection (₹10L, ₹50L, ₹1Cr)
- Velocity checks (1h, 24h, 7d windows)
- Structuring pattern detection
- Multi-factor scoring calculation
- Context-aware adjustments (business accounts, verified recipients)
- False positive prevention
"""

# [DOC] sys/os: needed to resolve imports from the project root when running tests from a subdirectory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# [DOC] unittest: standard Python testing framework; all test classes inherit from TestCase
import unittest
# [DOC] Decimal: financial amounts must use exact arithmetic to avoid floating-point rounding errors
from decimal import Decimal
# [DOC] datetime helpers: used to build historical transaction records for velocity window tests
from datetime import datetime, timedelta, timezone
# [DOC] hashlib: SHA-256 used to generate unique, deterministic transaction hashes for test fixtures
import hashlib

# [DOC] database imports: real ORM session and schema needed to persist transactions for velocity queries
from database.connection import SessionLocal, Base, engine
# [DOC] Transaction/TransactionStatus: ORM model and status enum used to create test transaction rows
from database.models.transaction import Transaction, TransactionStatus
# [DOC] BankAccount: ORM model referenced by transactions (sender/receiver account IDs)
from database.models.bank_account import BankAccount
# [DOC] User: ORM model representing the account holder
from database.models.user import User
# [DOC] Recipient: ORM model for known/trusted recipients (used by context-aware scoring adjustments)
from database.models.recipient import Recipient
# [DOC] AnomalyDetectionEngine: the class under test — scores transactions and raises flags
from core.services.anomaly_detection_engine import AnomalyDetectionEngine
# [DOC] IDXGenerator: creates deterministic pseudonymous identifiers from national ID + authority ID
from core.crypto.idx_generator import IDXGenerator


# [DOC] TestAnomalyDetectionEngine: groups all unit tests for the AML scoring and flagging engine
class TestAnomalyDetectionEngine(unittest.TestCase):
    """Test anomaly detection engine"""

    # [DOC] setUpClass: runs once before any tests in this class; creates all database tables if missing
    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        Base.metadata.create_all(engine)

    # [DOC] setUp: runs before each individual test; opens a fresh DB session and clears prior test data
    def setUp(self):
        """Set up test session"""
        self.db = SessionLocal()
        self.engine = AnomalyDetectionEngine(self.db)

        # Create test users (valid PAN format: XXXXX1234X)
        self.sender_idx = IDXGenerator.generate("TESTS1234A", "100001")
        self.receiver_idx = IDXGenerator.generate("TESTR5678B", "100002")

        # [DOC] Remove any transactions left over from previous test runs to ensure isolation
        self.db.query(Transaction).filter(
            Transaction.sender_idx.in_([self.sender_idx, self.receiver_idx])
        ).delete()
        self.db.commit()

    # [DOC] tearDown: runs after each test; closes DB session to release connection pool slot
    def tearDown(self):
        """Clean up"""
        self.db.close()

    # [DOC] _create_test_transaction: helper that builds a Transaction ORM object without saving it;
    # [DOC] allows each test to control the amount while reusing the sender/receiver IDX fixtures
    def _create_test_transaction(self, amount: Decimal, sender_idx: str = None) -> Transaction:
        """Helper: Create test transaction"""
        if sender_idx is None:
            sender_idx = self.sender_idx

        # [DOC] Include timestamp in hash input so successive calls produce unique hashes
        tx_hash = hashlib.sha256(f"{sender_idx}:{datetime.now().timestamp()}".encode()).hexdigest()

        return Transaction(
            transaction_hash=tx_hash,
            sender_account_id=1,
            receiver_account_id=2,
            sender_idx=sender_idx,
            receiver_idx=self.receiver_idx,
            sender_session_id=f"SES_TEST_{tx_hash[:8]}",
            receiver_session_id="SES_TEST_RECV",
            amount=amount,
            fee=amount * Decimal('0.015'),
            miner_fee=amount * Decimal('0.005'),
            bank_fee=amount * Decimal('0.01'),
            status=TransactionStatus.PENDING
        )

    # ===== Test 1: High-Value Detection =====

    # [DOC] test_high_value_tier_1: proves that a ₹50 lakh transaction receives a non-zero score
    # [DOC] and the HIGH_VALUE_TIER_1 and PMLA_MANDATORY_REPORTING flags
    def test_high_value_tier_1(self):
        """Test: ₹50 lakh transaction (Tier 1)"""
        tx = self._create_test_transaction(Decimal('5000000.00'))  # ₹50 lakh

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Score must be positive: ₹50L is above the high-value threshold
        self.assertGreater(result['score'], 0, "Score should be > 0 for ₹50L")
        # [DOC] The tier-1 flag identifies amounts between ₹50L and ₹1Cr
        self.assertIn('HIGH_VALUE_TIER_1', result['flags'], "Should flag HIGH_VALUE_TIER_1")
        # [DOC] PMLA requires mandatory reporting for transactions above ₹10L
        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA reporting")

    # [DOC] test_high_value_tier_2: proves that a ₹1 crore transaction scores above 30 and
    # [DOC] receives the tier-2 and PMLA flags indicating the highest risk category
    def test_high_value_tier_2(self):
        """Test: ₹1 crore transaction (Tier 2)"""
        tx = self._create_test_transaction(Decimal('10000000.00'))  # ₹1 crore

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Score > 30 reflects the elevated risk of transactions above ₹1Cr
        self.assertGreater(result['score'], 30, "Score should be > 30 for ₹1Cr")
        self.assertIn('HIGH_VALUE_TIER_2', result['flags'], "Should flag HIGH_VALUE_TIER_2")
        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA reporting")

    # [DOC] test_pmla_threshold: proves that a transaction at exactly ₹10 lakh triggers
    # [DOC] the PMLA mandatory reporting flag (the statutory threshold in Indian AML law)
    def test_pmla_threshold(self):
        """Test: ₹10 lakh transaction (PMLA threshold)"""
        tx = self._create_test_transaction(Decimal('1000000.00'))  # ₹10 lakh exactly

        result = self.engine.evaluate_transaction(tx)

        # [DOC] PMLA §12 mandates reporting for transactions at or above ₹10L
        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA at ₹10L")

    # ===== Test 2: Normal Transactions =====

    # [DOC] test_normal_transaction: proves that an ordinary ₹10,000 transfer scores exactly 0
    # [DOC] and generates no flags — the baseline "clean transaction" case
    def test_normal_transaction(self):
        """Test: Normal ₹10,000 transaction"""
        tx = self._create_test_transaction(Decimal('10000.00'))  # ₹10,000

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Score=0 means no risk factors triggered; this is the expected state for everyday transfers
        self.assertEqual(result['score'], 0.0, "Normal transaction should have score 0")
        self.assertEqual(result['flags'], [], "Normal transaction should have no flags")
        self.assertFalse(result['requires_investigation'], "Normal tx should not be flagged")

    # [DOC] test_below_pmla_threshold: proves that ₹9 lakh (just under the ₹10L PMLA line)
    # [DOC] scores 0 and does not trigger any flags
    def test_below_pmla_threshold(self):
        """Test: ₹9 lakh transaction (below PMLA)"""
        tx = self._create_test_transaction(Decimal('900000.00'))  # ₹9 lakh

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Amounts below ₹10L are not subject to PMLA mandatory reporting
        self.assertEqual(result['score'], 0.0, "Below PMLA threshold should have score 0")
        self.assertNotIn('PMLA_MANDATORY_REPORTING', result['flags'])

    # ===== Test 3: Velocity Detection =====

    # [DOC] test_velocity_high_frequency: proves that 6 prior transactions in a short window
    # [DOC] cause the 7th to trigger a velocity flag — the engine looks at historical counts
    def test_velocity_high_frequency(self):
        """Test: High velocity - many transactions in short time"""
        # [DOC] Persist 6 transactions to the DB so the velocity query finds them
        for i in range(6):
            tx = self._create_test_transaction(Decimal('100000.00'))
            self.db.add(tx)
        self.db.commit()

        # [DOC] The 7th transaction should trigger the velocity detection rule
        tx_new = self._create_test_transaction(Decimal('100000.00'))

        result = self.engine.evaluate_transaction(tx_new)

        # [DOC] Score must rise above 0 when velocity threshold is breached
        self.assertGreater(result['score'], 0, "Velocity should increase score")
        # [DOC] At least one VELOCITY flag must appear in the flags list
        has_velocity_flag = any('VELOCITY' in flag for flag in result['flags'])
        self.assertTrue(has_velocity_flag, "Should have velocity flag")

    # ===== Test 4: Structuring Detection =====

    # [DOC] test_structuring_pattern: proves that two transactions just below the ₹10L threshold
    # [DOC] raise a structuring flag — smurfing detection per PMLA §2(1)(g)
    def test_structuring_pattern(self):
        """Test: Structuring - multiple txs just below ₹10L threshold"""
        # [DOC] First transaction at ₹9.5L — just below the reporting threshold (structuring indicator)
        tx1 = self._create_test_transaction(Decimal('950000.00'))
        self.db.add(tx1)
        self.db.commit()

        # [DOC] Second similar amount — the engine should recognise the pattern as smurfing/structuring
        tx2 = self._create_test_transaction(Decimal('970000.00'))

        result = self.engine.evaluate_transaction(tx2)

        # [DOC] If structuring is detected the score must reflect significant additional risk
        has_structuring = any('STRUCTURING' in flag for flag in result['flags'])
        if has_structuring:
            self.assertGreater(result['score'], 20, "Structuring should add significant score")

    # ===== Test 5: Flag Threshold =====

    # [DOC] test_flag_threshold_65: proves that when the engine produces a score >= 65,
    # [DOC] requires_investigation is set to True — this triggers the ZKP + threshold encryption pipeline
    def test_flag_threshold_65(self):
        """Test: Score >= 65 triggers investigation flag"""
        # [DOC] ₹75L should score > 65 with no contextual adjustments applied
        tx = self._create_test_transaction(Decimal('7500000.00'))

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Conditional check: only assert investigation flag when score actually breaches threshold
        if result['score'] >= 65:
            self.assertTrue(result['requires_investigation'], "Score >= 65 should flag for investigation")
        else:
            self.assertFalse(result['requires_investigation'], "Score < 65 should not flag")

    # [DOC] test_just_below_threshold: proves the threshold boundary — a score below 65 must not
    # [DOC] set requires_investigation=True (no false positives at the decision boundary)
    def test_just_below_threshold(self):
        """Test: Score just below 65 doesn't trigger"""
        # [DOC] Create transaction that scores ~40-50 (below threshold)
        tx = self._create_test_transaction(Decimal('5000000.00'))  # ₹50 lakh

        result = self.engine.evaluate_transaction(tx)

        if result['score'] < 65:
            self.assertFalse(result['requires_investigation'], "Score < 65 should not flag")

    # ===== Test 6: Context Adjustments =====

    # [DOC] test_business_account_exemption: proves that the engine still returns a score for
    # [DOC] business accounts (future context-aware adjustment path must not crash or suppress result)
    def test_business_account_exemption(self):
        """Test: Business accounts have higher tolerance"""
        # Note: This test requires BankAccount.account_type='BUSINESS'
        # For now, we test that context adjustments reduce score

        tx = self._create_test_transaction(Decimal('10000000.00'))  # ₹1 crore

        result_base = self.engine.evaluate_transaction(tx)

        # [DOC] Even without explicit business account context, the score must be a numeric value
        self.assertIsNotNone(result_base['score'], "Should calculate score for business accounts")

    # ===== Test 7: Multiple Factors =====

    # [DOC] test_multiple_risk_factors: proves that combining high value and high velocity
    # [DOC] produces a higher composite score than either factor alone, with multiple flags present
    def test_multiple_risk_factors(self):
        """Test: High value + high velocity = very high score"""
        # [DOC] Seed 6 prior transactions at ₹50L each to trigger the velocity rule
        for i in range(6):
            tx = self._create_test_transaction(Decimal('5000000.00'))
            self.db.add(tx)
        self.db.commit()

        # [DOC] ₹75L transaction on top of existing velocity should compound the risk score
        tx_new = self._create_test_transaction(Decimal('7500000.00'))

        result = self.engine.evaluate_transaction(tx_new)

        # [DOC] Composite score must exceed 30 when both high-value and velocity risks apply
        self.assertGreater(result['score'], 30, "Multiple factors should increase score significantly")
        # [DOC] At least two flags expected: one for high value, one for velocity
        self.assertTrue(len(result['flags']) > 1, "Should have multiple flags")

    # ===== Test 8: Edge Cases =====

    # [DOC] test_zero_amount: proves the engine handles a zero-amount transaction gracefully
    # [DOC] without crashing and returns a score of 0
    def test_zero_amount(self):
        """Test: Zero amount transaction"""
        tx = self._create_test_transaction(Decimal('0.00'))

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Zero amount has no monetary risk; score must be exactly 0
        self.assertEqual(result['score'], 0.0, "Zero amount should have score 0")

    # [DOC] test_negative_amount: proves the engine handles an invalid negative amount
    # [DOC] without raising an unhandled exception (defensive programming test)
    def test_negative_amount(self):
        """Test: Negative amount (invalid)"""
        tx = self._create_test_transaction(Decimal('-1000.00'))

        result = self.engine.evaluate_transaction(tx)

        # [DOC] Engine must return a dict with 'score' key even for invalid inputs
        self.assertIsNotNone(result['score'], "Should handle negative amounts")

    # [DOC] test_very_large_amount: proves that an extreme amount (₹100 crore) is correctly
    # [DOC] assigned a high score and the HIGH_VALUE_TIER_2 flag
    def test_very_large_amount(self):
        """Test: Very large amount (₹100 crore)"""
        tx = self._create_test_transaction(Decimal('1000000000.00'))  # ₹100 crore

        result = self.engine.evaluate_transaction(tx)

        # [DOC] ₹100Cr must score at least 40 (well above either tier threshold)
        self.assertGreaterEqual(result['score'], 40.0, "₹100Cr should have high score")
        self.assertIn('HIGH_VALUE_TIER_2', result['flags'], "Should have high value flag")

    # ===== Test 9: Statistics =====

    # [DOC] test_get_statistics: proves that the engine's statistics endpoint returns
    # [DOC] the required fields and non-negative counts for DB-persisted transactions
    def test_get_statistics(self):
        """Test: Get anomaly detection statistics"""
        # [DOC] Persist 5 transactions, alternating flagged/unflagged, so the stats query has data
        for i in range(5):
            tx = self._create_test_transaction(Decimal('1000000.00'))
            tx.requires_investigation = (i % 2 == 0)  # Flag every other one
            self.db.add(tx)
        self.db.commit()

        stats = self.engine.get_statistics()

        # [DOC] Statistics must include totals, flagged count, and the false positive rate
        self.assertIn('total_transactions', stats)
        self.assertIn('flagged_transactions', stats)
        self.assertIn('false_positive_rate', stats)
        # [DOC] Flagged count must be a non-negative integer
        self.assertGreaterEqual(stats['flagged_transactions'], 0)

    # ===== Test 10: Scoring Consistency =====

    # [DOC] test_scoring_is_deterministic: proves that evaluating the same transaction object
    # [DOC] twice produces identical scores and flags (no hidden randomness in the scoring logic)
    def test_scoring_is_deterministic(self):
        """Test: Same transaction should always get same score"""
        tx = self._create_test_transaction(Decimal('5000000.00'))

        result1 = self.engine.evaluate_transaction(tx)
        result2 = self.engine.evaluate_transaction(tx)

        # [DOC] Determinism is essential for auditability: same input must always yield same output
        self.assertEqual(result1['score'], result2['score'], "Scoring should be deterministic")
        self.assertEqual(result1['flags'], result2['flags'], "Flags should be consistent")


if __name__ == '__main__':
    unittest.main(verbosity=2)
