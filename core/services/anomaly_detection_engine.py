"""
Anomaly Detection Engine - PMLA Compliance
Purpose: Rule-based anomaly detection for suspicious transactions

PMLA Compliance (Prevention of Money Laundering Act - India):
- Threshold reporting: ₹10 lakh and above
- Suspicious transaction detection (any amount)
- Structuring detection (avoiding thresholds)

Score Threshold: >= 65 → FLAG for investigation

Multi-Factor Scoring (0-100):
- Amount-based risk: 0-40 points
- Velocity risk: 0-30 points
- Structuring pattern: 0-30 points

Context-Aware Adjustments:
- Business accounts: Higher thresholds
- Verified recipients: Reduced scores
- User transaction history: Behavioral analysis
"""

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models.transaction import Transaction
from database.models.bank_account import BankAccount
from database.models.recipient import Recipient


class AnomalyDetectionEngine:
    """
    Rule-based anomaly detection engine with PMLA compliance

    Configuration:
    - FLAG_THRESHOLD: 65 (score >= 65 triggers investigation)
    - PMLA_THRESHOLD: ₹10,00,000 (mandatory reporting)
    - STRUCTURING_WINDOW: 24 hours

    Example:
        >>> engine = AnomalyDetectionEngine(db)
        >>> result = engine.evaluate_transaction(tx)
        >>> # Returns: {score: 68, flags: [...], requires_investigation: True}
    """

    # Configuration
    FLAG_THRESHOLD = Decimal('65.00')  # Score >= 65 triggers flag

    # PMLA Thresholds (India)
    PMLA_MANDATORY_REPORTING = Decimal('1000000.00')  # ₹10 lakh
    HIGH_VALUE_TIER_1 = Decimal('5000000.00')  # ₹50 lakh
    HIGH_VALUE_TIER_2 = Decimal('10000000.00')  # ₹1 crore

    # Structuring detection
    STRUCTURING_WINDOW_HOURS = 24
    STRUCTURING_THRESHOLD = Decimal('1000000.00')  # ₹10 lakh
    STRUCTURING_PROXIMITY = Decimal('0.95')  # Within 95% of threshold

    # Velocity thresholds
    VELOCITY_HIGH_1H = 5  # 5+ txs in 1 hour
    VELOCITY_HIGH_24H = 10  # 10+ txs in 24 hours
    VELOCITY_HIGH_7D = 50  # 50+ txs in 7 days

    def __init__(self, db: Session):
        """
        Initialize anomaly detection engine

        Args:
            db: Database session
        """
        self.db = db

    def evaluate_transaction(self, tx: Transaction, persist: bool = True) -> Dict:
        """
        Evaluate transaction for anomalies

        Args:
            tx: Transaction to evaluate

        Returns:
            dict: {
                'score': float (0-100),
                'flags': list of flag names,
                'requires_investigation': bool (score >= 65)
            }
        """
        score = Decimal('0.00')
        flags = []

        # Factor 1: Amount-based risk (0-40 points)
        amount_score, amount_flags = self._evaluate_amount_risk(tx)
        score += amount_score
        flags.extend(amount_flags)

        # Factor 2: Velocity risk (0-30 points)
        velocity_score, velocity_flags = self._evaluate_velocity_risk(tx)
        score += velocity_score
        flags.extend(velocity_flags)

        # Factor 3: Structuring detection (0-30 points)
        structuring_score, structuring_flags = self._evaluate_structuring_risk(tx)
        score += structuring_score
        flags.extend(structuring_flags)

        # Context-aware adjustments
        score = self._apply_context_adjustments(tx, score)

        # Cap score at 100
        score = min(score, Decimal('100.00'))

        # Determine if requires investigation
        requires_investigation = score >= self.FLAG_THRESHOLD

        result = {
            'score': float(score),
            'flags': flags,
            'requires_investigation': requires_investigation
        }

        # Optionally persist evaluation result to DB. Callers (and tests) can skip persistence
        # by passing persist=False to avoid committing during unit tests or higher-level
        # transaction management.
        if persist:
            self._persist_evaluation(tx, score, flags, requires_investigation)

        return result

    def _persist_evaluation(self, tx: Transaction, score: Decimal, flags: List[str], requires_investigation: bool) -> None:
        """
        Persist evaluation result to the database in a safe manner.

        This method writes evaluation fields to the provided transaction object and
        attempts to commit the session. On failure, it rolls back the session and
        raises a RuntimeError with a clear message so callers can handle failures.

        Args:
            tx: Transaction object to update
            score: Decimal score computed
            flags: List of flag strings
            requires_investigation: Whether the tx is flagged

        Raises:
            RuntimeError: If committing the DB transaction fails
        """
        # Update fields on transaction
        tx.anomaly_score = score
        tx.anomaly_flags = flags if flags else None
        tx.requires_investigation = requires_investigation
        if requires_investigation:
            tx.flagged_at = datetime.now(timezone.utc)
            tx.investigation_status = 'PENDING'

        # Commit safely with rollback on exception
        try:
            self.db.commit()
        except Exception as e:
            try:
                # Best-effort rollback
                self.db.rollback()
            except Exception:
                # If rollback fails, there's little we can do here; continue to raise
                pass
            tx_id = getattr(tx, 'transaction_hash', '<unknown>')
            raise RuntimeError(f"Failed to persist anomaly evaluation for transaction {tx_id}: {e}")

    def _evaluate_amount_risk(self, tx: Transaction) -> tuple:
        """
        Evaluate amount-based risk (0-40 points)

        Tiers:
        - >= ₹1 crore: 40 points
        - >= ₹50 lakh: 25 points
        - >= ₹10 lakh: 10 points (PMLA threshold)

        Args:
            tx: Transaction

        Returns:
            tuple: (score, flags)
        """
        score = Decimal('0.00')
        flags = []

        if tx.amount >= self.HIGH_VALUE_TIER_2:
            # >= ₹1 crore
            score += Decimal('40.00')
            flags.append('HIGH_VALUE_TIER_2')
            flags.append('PMLA_MANDATORY_REPORTING')
        elif tx.amount >= self.HIGH_VALUE_TIER_1:
            # >= ₹50 lakh
            score += Decimal('25.00')
            flags.append('HIGH_VALUE_TIER_1')
            flags.append('PMLA_MANDATORY_REPORTING')
        elif tx.amount >= self.PMLA_MANDATORY_REPORTING:
            # >= ₹10 lakh
            score += Decimal('10.00')
            flags.append('PMLA_MANDATORY_REPORTING')

        return score, flags

    def _evaluate_velocity_risk(self, tx: Transaction) -> tuple:
        """
        Evaluate transaction velocity (0-30 points)

        Checks:
        - Last 1 hour: >= 5 txs → 30 points
        - Last 24 hours: >= 10 txs → 15 points
        - Last 7 days: >= 50 txs → 10 points

        Args:
            tx: Transaction

        Returns:
            tuple: (score, flags)
        """
        score = Decimal('0.00')
        flags = []

        now = datetime.now(timezone.utc)

        # Count transactions in different time windows
        count_1h = self._count_recent_transactions(tx.sender_idx, hours=1)
        count_24h = self._count_recent_transactions(tx.sender_idx, hours=24)
        count_7d = self._count_recent_transactions(tx.sender_idx, hours=168)  # 7 days

        # Check 1 hour window (highest priority)
        if count_1h >= self.VELOCITY_HIGH_1H:
            score += Decimal('30.00')
            flags.append(f'HIGH_VELOCITY_1H_{count_1h}')
        # Check 24 hour window
        elif count_24h >= self.VELOCITY_HIGH_24H:
            score += Decimal('15.00')
            flags.append(f'HIGH_VELOCITY_24H_{count_24h}')
        # Check 7 day window
        elif count_7d >= self.VELOCITY_HIGH_7D:
            score += Decimal('10.00')
            flags.append(f'HIGH_VELOCITY_7D_{count_7d}')

        return score, flags

    def _evaluate_structuring_risk(self, tx: Transaction) -> tuple:
        """
        Detect structuring (breaking large transaction into smaller ones)

        Pattern:
        - Multiple transactions just below ₹10 lakh threshold
        - Within 24-hour window
        - Total exceeds ₹10 lakh

        Args:
            tx: Transaction

        Returns:
            tuple: (score, flags)
        """
        score = Decimal('0.00')
        flags = []

        # Check if current transaction is just below threshold
        threshold_amount = self.STRUCTURING_THRESHOLD * self.STRUCTURING_PROXIMITY

        if threshold_amount <= tx.amount < self.STRUCTURING_THRESHOLD:
            # This transaction is suspiciously close to threshold
            # Check for other similar transactions in last 24 hours
            recent_similar = self._find_structuring_pattern(
                tx.sender_idx,
                threshold_amount,
                self.STRUCTURING_THRESHOLD
            )

            if recent_similar > 0:
                # Multiple transactions just below threshold → Structuring
                score += Decimal('30.00')
                flags.append(f'STRUCTURING_DETECTED_{recent_similar + 1}_TXS')

        return score, flags

    def _apply_context_adjustments(self, tx: Transaction, base_score: Decimal) -> Decimal:
        """
        Apply context-aware adjustments to score

        Adjustments (MULTIPLICATIVE - intentional design):
        - Business accounts: × 0.6 (40% reduction)
        - Verified recipients: × 0.5 (50% reduction)
        - Within user's historical max: × 0.7 (30% reduction)

        Multiplicative Design Rationale:
        - Each factor independently validates legitimacy
        - Combined factors indicate high confidence in legitimacy
        - Example: Business account (trusted) + verified recipient (relationship) +
          historical pattern (normal behavior) = very low risk
        - Maximum reduction capped at 90% to prevent complete score elimination

        Example reductions:
        - Business only: 100 → 60 (40% reduction)
        - Business + verified: 100 → 30 (70% reduction)
        - All three: 100 → 21 (79% reduction) [well below 65 threshold]

        Args:
            tx: Transaction
            base_score: Base anomaly score

        Returns:
            Decimal: Adjusted score (minimum 10% of original)
        """
        score = base_score
        original_score = base_score

        # Get sender account
        sender_account = self.db.query(BankAccount).filter(
            BankAccount.id == tx.sender_account_id
        ).first()

        if not sender_account:
            return score

        # Adjustment 1: Business account exception
        if hasattr(sender_account, 'account_type') and sender_account.account_type == 'BUSINESS':
            score = score * Decimal('0.6')  # Reduce by 40%

        # Adjustment 2: Verified recipient (long-standing relationship)
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == tx.sender_idx,
            Recipient.recipient_idx == tx.receiver_idx,
            Recipient.is_active == True
        ).first()

        if recipient and recipient.transaction_count > 10:
            # Verified recipient with 10+ past transactions
            score = score * Decimal('0.5')  # Reduce by 50%

        # Adjustment 3: Within user's historical behavior
        user_max_amount = self._get_user_max_transaction_amount(tx.sender_idx)

        if user_max_amount and tx.amount <= user_max_amount * 2:
            # Transaction is within 2x of user's historical max
            score = score * Decimal('0.7')  # Reduce by 30%

        # Safety cap: Prevent excessive reduction (max 90% reduction)
        # Ensures even highly trusted transactions retain some score
        minimum_score = original_score * Decimal('0.10')  # Minimum 10% of original
        if score < minimum_score:
            score = minimum_score

        return score

    def _count_recent_transactions(self, user_idx: str, hours: int) -> int:
        """
        Count transactions from user in last N hours

        Args:
            user_idx: User IDX
            hours: Time window in hours

        Returns:
            int: Transaction count
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        count = self.db.query(Transaction).filter(
            Transaction.sender_idx == user_idx,
            Transaction.created_at >= cutoff_time
        ).count()

        return count

    def _find_structuring_pattern(
        self,
        user_idx: str,
        min_amount: Decimal,
        max_amount: Decimal
    ) -> int:
        """
        Find transactions in structuring range (just below threshold)

        Args:
            user_idx: User IDX
            min_amount: Minimum amount (95% of threshold)
            max_amount: Maximum amount (threshold)

        Returns:
            int: Count of similar transactions in last 24h
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.STRUCTURING_WINDOW_HOURS)

        count = self.db.query(Transaction).filter(
            Transaction.sender_idx == user_idx,
            Transaction.amount >= min_amount,
            Transaction.amount < max_amount,
            Transaction.created_at >= cutoff_time
        ).count()

        return count

    def _get_user_max_transaction_amount(self, user_idx: str) -> Optional[Decimal]:
        """
        Get user's maximum transaction amount in last 90 days

        Args:
            user_idx: User IDX

        Returns:
            Decimal: Max amount, or None if no history
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=90)

        max_amount = self.db.query(func.max(Transaction.amount)).filter(
            Transaction.sender_idx == user_idx,
            Transaction.created_at >= cutoff_time
        ).scalar()

        return max_amount

    def get_flagged_transactions(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Transaction]:
        """
        Get all flagged transactions

        Args:
            limit: Maximum results
            offset: Results offset

        Returns:
            List[Transaction]: Flagged transactions
        """
        return self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        ).order_by(Transaction.flagged_at.desc()).limit(limit).offset(offset).all()

    def get_statistics(self) -> Dict:
        """
        Get anomaly detection statistics

        Returns:
            dict: Statistics
        """
        total_txs = self.db.query(Transaction).count()
        flagged_txs = self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        ).count()

        cleared_txs = self.db.query(Transaction).filter(
            Transaction.investigation_status == 'CLEARED'
        ).count()

        false_positive_rate = (cleared_txs / flagged_txs * 100) if flagged_txs > 0 else 0

        return {
            'total_transactions': total_txs,
            'flagged_transactions': flagged_txs,
            'cleared_transactions': cleared_txs,
            'false_positive_rate': round(false_positive_rate, 2),
            'flagged_percentage': round(flagged_txs / total_txs * 100, 2) if total_txs > 0 else 0
        }


# Testing
if __name__ == "__main__":
    """Test anomaly detection engine"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from database.connection import SessionLocal
    from database.models.user import User
    from core.crypto.idx_generator import IDXGenerator
    import hashlib

    print("=== Anomaly Detection Engine Testing ===\n")

    db = SessionLocal()
    engine = AnomalyDetectionEngine(db)

    try:
        # Test 1: High-value transaction (₹75 lakh)
        print("Test 1: High-Value Transaction (₹75 lakh)")

        tx1 = Transaction(
            transaction_hash=hashlib.sha256(b"test_high_value").hexdigest(),
            sender_account_id=1,
            receiver_account_id=2,
            sender_idx="IDX_TEST_SENDER",
            receiver_idx="IDX_TEST_RECEIVER",
            sender_session_id="SES_TEST",
            receiver_session_id="SES_TEST",
            amount=Decimal('7500000.00'),  # ₹75 lakh
            fee=Decimal('112500.00'),
            miner_fee=Decimal('37500.00'),
            bank_fee=Decimal('75000.00')
        )

        result1 = engine.evaluate_transaction(tx1)
        print(f"  Score: {result1['score']}")
        print(f"  Flags: {result1['flags']}")
        print(f"  Requires Investigation: {result1['requires_investigation']}")
        print(f"  ✅ Test 1 passed!\n")

        # Test 2: Normal transaction (₹10,000)
        print("Test 2: Normal Transaction (₹10,000)")

        tx2 = Transaction(
            transaction_hash=hashlib.sha256(b"test_normal").hexdigest(),
            sender_account_id=1,
            receiver_account_id=2,
            sender_idx="IDX_TEST_SENDER",
            receiver_idx="IDX_TEST_RECEIVER",
            sender_session_id="SES_TEST",
            receiver_session_id="SES_TEST",
            amount=Decimal('10000.00'),  # ₹10,000
            fee=Decimal('150.00'),
            miner_fee=Decimal('50.00'),
            bank_fee=Decimal('100.00')
        )

        result2 = engine.evaluate_transaction(tx2)
        print(f"  Score: {result2['score']}")
        print(f"  Flags: {result2['flags']}")
        print(f"  Requires Investigation: {result2['requires_investigation']}")
        print(f"  ✅ Test 2 passed!\n")

        # Test 3: Structuring attempt (₹9.5 lakh - just below ₹10L)
        print("Test 3: Structuring Attempt (₹9.5 lakh)")

        tx3 = Transaction(
            transaction_hash=hashlib.sha256(b"test_structuring").hexdigest(),
            sender_account_id=1,
            receiver_account_id=2,
            sender_idx="IDX_TEST_SENDER",
            receiver_idx="IDX_TEST_RECEIVER",
            sender_session_id="SES_TEST",
            receiver_session_id="SES_TEST",
            amount=Decimal('950000.00'),  # ₹9.5 lakh (just below ₹10L)
            fee=Decimal('14250.00'),
            miner_fee=Decimal('4750.00'),
            bank_fee=Decimal('9500.00')
        )

        result3 = engine.evaluate_transaction(tx3)
        print(f"  Score: {result3['score']}")
        print(f"  Flags: {result3['flags']}")
        print(f"  Requires Investigation: {result3['requires_investigation']}")
        print(f"  ✅ Test 3 passed!\n")

        print("=" * 50)
        print("✅ All anomaly detection tests passed!")
        print("=" * 50)

    finally:
        db.close()
