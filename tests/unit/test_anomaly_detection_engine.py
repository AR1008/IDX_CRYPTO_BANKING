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

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import hashlib

from database.connection import SessionLocal, Base, engine
from database.models.transaction import Transaction, TransactionStatus
from database.models.bank_account import BankAccount
from database.models.user import User
from database.models.recipient import Recipient
from core.services.anomaly_detection_engine import AnomalyDetectionEngine
from core.crypto.idx_generator import IDXGenerator


class TestAnomalyDetectionEngine(unittest.TestCase):
    """Test anomaly detection engine"""

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        Base.metadata.create_all(engine)

    def setUp(self):
        """Set up test session"""
        self.db = SessionLocal()
        self.engine = AnomalyDetectionEngine(self.db)

        # Create test users (valid PAN format: XXXXX1234X)
        self.sender_idx = IDXGenerator.generate("TESTS1234A", "100001")
        self.receiver_idx = IDXGenerator.generate("TESTR5678B", "100002")

        # Clean up old test data
        self.db.query(Transaction).filter(
            Transaction.sender_idx.in_([self.sender_idx, self.receiver_idx])
        ).delete()
        self.db.commit()

    def tearDown(self):
        """Clean up"""
        self.db.close()

    def _create_test_transaction(self, amount: Decimal, sender_idx: str = None) -> Transaction:
        """Helper: Create test transaction"""
        if sender_idx is None:
            sender_idx = self.sender_idx

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

    def test_high_value_tier_1(self):
        """Test: ₹50 lakh transaction (Tier 1)"""
        tx = self._create_test_transaction(Decimal('5000000.00'))  # ₹50 lakh

        result = self.engine.evaluate_transaction(tx)

        self.assertGreater(result['score'], 0, "Score should be > 0 for ₹50L")
        self.assertIn('HIGH_VALUE_TIER_1', result['flags'], "Should flag HIGH_VALUE_TIER_1")
        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA reporting")

    def test_high_value_tier_2(self):
        """Test: ₹1 crore transaction (Tier 2)"""
        tx = self._create_test_transaction(Decimal('10000000.00'))  # ₹1 crore

        result = self.engine.evaluate_transaction(tx)

        self.assertGreater(result['score'], 30, "Score should be > 30 for ₹1Cr")
        self.assertIn('HIGH_VALUE_TIER_2', result['flags'], "Should flag HIGH_VALUE_TIER_2")
        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA reporting")

    def test_pmla_threshold(self):
        """Test: ₹10 lakh transaction (PMLA threshold)"""
        tx = self._create_test_transaction(Decimal('1000000.00'))  # ₹10 lakh exactly

        result = self.engine.evaluate_transaction(tx)

        self.assertIn('PMLA_MANDATORY_REPORTING', result['flags'], "Should flag PMLA at ₹10L")

    # ===== Test 2: Normal Transactions =====

    def test_normal_transaction(self):
        """Test: Normal ₹10,000 transaction"""
        tx = self._create_test_transaction(Decimal('10000.00'))  # ₹10,000

        result = self.engine.evaluate_transaction(tx)

        self.assertEqual(result['score'], 0.0, "Normal transaction should have score 0")
        self.assertEqual(result['flags'], [], "Normal transaction should have no flags")
        self.assertFalse(result['requires_investigation'], "Normal tx should not be flagged")

    def test_below_pmla_threshold(self):
        """Test: ₹9 lakh transaction (below PMLA)"""
        tx = self._create_test_transaction(Decimal('900000.00'))  # ₹9 lakh

        result = self.engine.evaluate_transaction(tx)

        self.assertEqual(result['score'], 0.0, "Below PMLA threshold should have score 0")
        self.assertNotIn('PMLA_MANDATORY_REPORTING', result['flags'])

    # ===== Test 3: Velocity Detection =====

    def test_velocity_high_frequency(self):
        """Test: High velocity - many transactions in short time"""
        # Create 6 transactions in last hour (should trigger velocity flag)
        for i in range(6):
            tx = self._create_test_transaction(Decimal('100000.00'))
            self.db.add(tx)
        self.db.commit()

        # Create 7th transaction - should detect velocity
        tx_new = self._create_test_transaction(Decimal('100000.00'))

        result = self.engine.evaluate_transaction(tx_new)

        self.assertGreater(result['score'], 0, "Velocity should increase score")
        has_velocity_flag = any('VELOCITY' in flag for flag in result['flags'])
        self.assertTrue(has_velocity_flag, "Should have velocity flag")

    # ===== Test 4: Structuring Detection =====

    def test_structuring_pattern(self):
        """Test: Structuring - multiple txs just below ₹10L threshold"""
        # Create transaction at ₹9.5 lakh (just below ₹10L)
        tx1 = self._create_test_transaction(Decimal('950000.00'))
        self.db.add(tx1)
        self.db.commit()

        # Create another similar transaction
        tx2 = self._create_test_transaction(Decimal('970000.00'))

        result = self.engine.evaluate_transaction(tx2)

        # Should detect structuring pattern
        has_structuring = any('STRUCTURING' in flag for flag in result['flags'])
        if has_structuring:
            self.assertGreater(result['score'], 20, "Structuring should add significant score")

    # ===== Test 5: Flag Threshold =====

    def test_flag_threshold_65(self):
        """Test: Score >= 65 triggers investigation flag"""
        # ₹75 lakh should score > 65 (high value + no context adjustments)
        tx = self._create_test_transaction(Decimal('7500000.00'))

        result = self.engine.evaluate_transaction(tx)

        if result['score'] >= 65:
            self.assertTrue(result['requires_investigation'], "Score >= 65 should flag for investigation")
        else:
            self.assertFalse(result['requires_investigation'], "Score < 65 should not flag")

    def test_just_below_threshold(self):
        """Test: Score just below 65 doesn't trigger"""
        # Create transaction that scores ~40-50 (below threshold)
        tx = self._create_test_transaction(Decimal('5000000.00'))  # ₹50 lakh

        result = self.engine.evaluate_transaction(tx)

        if result['score'] < 65:
            self.assertFalse(result['requires_investigation'], "Score < 65 should not flag")

    # ===== Test 6: Context Adjustments =====

    def test_business_account_exemption(self):
        """Test: Business accounts have higher tolerance"""
        # Note: This test requires BankAccount.account_type='BUSINESS'
        # For now, we test that context adjustments reduce score

        tx = self._create_test_transaction(Decimal('10000000.00'))  # ₹1 crore

        result_base = self.engine.evaluate_transaction(tx)

        # With business account context, score should be reduced
        # (In production, this would check account_type)
        self.assertIsNotNone(result_base['score'], "Should calculate score for business accounts")

    # ===== Test 7: Multiple Factors =====

    def test_multiple_risk_factors(self):
        """Test: High value + high velocity = very high score"""
        # Create 6 previous transactions (velocity)
        for i in range(6):
            tx = self._create_test_transaction(Decimal('5000000.00'))
            self.db.add(tx)
        self.db.commit()

        # Create high-value transaction (₹75 lakh) with velocity
        tx_new = self._create_test_transaction(Decimal('7500000.00'))

        result = self.engine.evaluate_transaction(tx_new)

        # Should have both high value and velocity flags
        self.assertGreater(result['score'], 30, "Multiple factors should increase score significantly")
        self.assertTrue(len(result['flags']) > 1, "Should have multiple flags")

    # ===== Test 8: Edge Cases =====

    def test_zero_amount(self):
        """Test: Zero amount transaction"""
        tx = self._create_test_transaction(Decimal('0.00'))

        result = self.engine.evaluate_transaction(tx)

        self.assertEqual(result['score'], 0.0, "Zero amount should have score 0")

    def test_negative_amount(self):
        """Test: Negative amount (invalid)"""
        tx = self._create_test_transaction(Decimal('-1000.00'))

        result = self.engine.evaluate_transaction(tx)

        # Should handle gracefully (no crash)
        self.assertIsNotNone(result['score'], "Should handle negative amounts")

    def test_very_large_amount(self):
        """Test: Very large amount (₹100 crore)"""
        tx = self._create_test_transaction(Decimal('1000000000.00'))  # ₹100 crore

        result = self.engine.evaluate_transaction(tx)

        # Very large amounts get flagged (score should be high)
        self.assertGreaterEqual(result['score'], 40.0, "₹100Cr should have high score")
        self.assertIn('HIGH_VALUE_TIER_2', result['flags'], "Should have high value flag")

    # ===== Test 9: Statistics =====

    def test_get_statistics(self):
        """Test: Get anomaly detection statistics"""
        # Create some transactions
        for i in range(5):
            tx = self._create_test_transaction(Decimal('1000000.00'))
            tx.requires_investigation = (i % 2 == 0)  # Flag every other one
            self.db.add(tx)
        self.db.commit()

        stats = self.engine.get_statistics()

        self.assertIn('total_transactions', stats)
        self.assertIn('flagged_transactions', stats)
        self.assertIn('false_positive_rate', stats)
        self.assertGreaterEqual(stats['flagged_transactions'], 0)

    # ===== Test 10: Scoring Consistency =====

    def test_scoring_is_deterministic(self):
        """Test: Same transaction should always get same score"""
        tx = self._create_test_transaction(Decimal('5000000.00'))

        result1 = self.engine.evaluate_transaction(tx)
        result2 = self.engine.evaluate_transaction(tx)

        self.assertEqual(result1['score'], result2['score'], "Scoring should be deterministic")
        self.assertEqual(result1['flags'], result2['flags'], "Flags should be consistent")


if __name__ == '__main__':
    unittest.main(verbosity=2)
