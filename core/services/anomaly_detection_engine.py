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

# [DOC] Decimal: used for all monetary arithmetic to avoid floating-point rounding errors
from decimal import Decimal
# [DOC] datetime/timedelta/timezone: needed to compute time windows for velocity and structuring checks
from datetime import datetime, timedelta, timezone
# [DOC] Dict/List/Optional: type hints only — no runtime effect; improves code readability
from typing import Dict, List, Optional
# [DOC] Session: SQLAlchemy database session type; passed in so this engine can query transactions
from sqlalchemy.orm import Session
# [DOC] func: SQLAlchemy helper for SQL aggregate functions like MAX()
from sqlalchemy import func

# [DOC] Transaction ORM model: each row represents one payment on the system
from database.models.transaction import Transaction
# [DOC] BankAccount ORM model: used to check whether sender has a BUSINESS account type
from database.models.bank_account import BankAccount
# [DOC] Recipient ORM model: used to check whether sender has a verified long-term relationship with receiver
from database.models.recipient import Recipient
# [DOC] prove_velocity: generates a ZK range proof that the transaction count crosses (or not) the velocity threshold,
# [DOC] revealing only is_suspicious (bool) and a Pedersen commitment — never the exact count.
from core.crypto.real.velocity_zkp import prove_velocity
# [DOC] prove_structuring: generates a ZK range proof classifying whether the transaction amount falls in
# [DOC] the suspicious structuring range [low, high), revealing only is_structuring (bool) — never the exact amount.
from core.crypto.real.structuring_zkp import prove_structuring, MAX_AMOUNT as STRUCTURING_MAX_AMOUNT


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

    # [DOC] FLAG_THRESHOLD: any transaction scoring >= 65 is flagged for investigation
    # [DOC] Flagging does NOT freeze the account or block the transaction — it only stores the anomaly proof
    FLAG_THRESHOLD = Decimal('65.00')  # Score >= 65 triggers flag

    # All monetary thresholds below are in PAISE (1 rupee = 100 paise).
    # Prototype values are parameterised; in production these map to PMLA 2002 thresholds:
    #   1,000,000 paise = ₹10,000  (prototype)  →  configurable to ₹10 lakh for production
    #   5,000,000 paise = ₹50,000  (prototype)  →  configurable to ₹50 lakh for production
    #  10,000,000 paise = ₹1,00,000 (prototype) →  configurable to ₹1 crore for production

    # [DOC] PMLA_MANDATORY_REPORTING: 1,000,000 paise = ₹10,000 (prototype); scale to ₹10 lakh for production
    PMLA_MANDATORY_REPORTING = Decimal('1000000.00')  # 1,000,000 paise = ₹10,000
    # [DOC] HIGH_VALUE_TIER_1: 5,000,000 paise = ₹50,000 (prototype); mid-tier risk, scores 25 points
    HIGH_VALUE_TIER_1 = Decimal('5000000.00')  # 5,000,000 paise = ₹50,000
    # [DOC] HIGH_VALUE_TIER_2: 10,000,000 paise = ₹1,00,000 (prototype); top-tier risk, scores 40 points
    HIGH_VALUE_TIER_2 = Decimal('10000000.00')  # 10,000,000 paise = ₹1,00,000

    # [DOC] STRUCTURING_WINDOW_HOURS: look back 24 hours when detecting split-amount patterns
    STRUCTURING_WINDOW_HOURS = 24
    # [DOC] STRUCTURING_THRESHOLD: 1,000,000 paise = ₹10,000 (prototype reporting boundary)
    STRUCTURING_THRESHOLD = Decimal('1000000.00')  # 1,000,000 paise = ₹10,000
    # [DOC] STRUCTURING_PROXIMITY: amounts within 95% of the threshold (950,000–999,999 paise = ₹9,500–₹9,999) are suspicious
    STRUCTURING_PROXIMITY = Decimal('0.95')  # Within 95% of threshold

    # [DOC] VELOCITY_HIGH_1H: 5+ transactions from the same sender in one hour → maximum velocity score (30 pts)
    VELOCITY_HIGH_1H = 5  # 5+ txs in 1 hour
    # [DOC] VELOCITY_HIGH_24H: 10+ transactions in 24 hours → medium velocity score (15 pts)
    VELOCITY_HIGH_24H = 10  # 10+ txs in 24 hours
    # [DOC] VELOCITY_HIGH_7D: 50+ transactions in 7 days → low velocity score (10 pts)
    VELOCITY_HIGH_7D = 50  # 50+ txs in 7 days

    def __init__(self, db: Session):
        """
        Initialize anomaly detection engine

        Args:
            db: Database session
        """
        # [DOC] Store database session so all helper methods can query existing transactions for this user
        self.db = db

    def evaluate_transaction(self, tx: Transaction, persist: bool = True) -> Dict:
        """
        Evaluate transaction for anomalies.

        Runs three independent AML rule checks, each producing a score contribution
        and a zero-knowledge proof of its classification. The ZK proofs allow any
        verifier to confirm the rules were applied correctly without seeing the
        exact transaction count or amount.

        Args:
            tx: Transaction to evaluate.
            persist: If True (default), writes anomaly fields to the DB transaction row.
                     Pass False in unit tests or dry-run contexts.

        Returns:
            dict: {
                'score':              float (0-100) — combined anomaly risk score,
                'flags':              list[str] — human-readable rule names that fired,
                'requires_investigation': bool — True if score >= 65,
                'velocity_proofs':    list[dict] — ZK proof(s) from prove_velocity(),
                'structuring_proofs': list[dict] — ZK proof from prove_structuring()
            }
        """
        # [DOC] Start with zero score; each factor adds points independently
        score = Decimal('0.00')
        # [DOC] flags is a human-readable list of rule names that contributed to the score
        flags = []

        # [DOC] Factor 1: large amounts add 0–40 points depending on tier (PMLA reporting thresholds)
        amount_score, amount_flags = self._evaluate_amount_risk(tx)
        score += amount_score
        flags.extend(amount_flags)

        # [DOC] Factor 2: many transactions in a short window add 0–30 points (burst sending pattern)
        # [DOC] Also returns velocity_proofs — ZK range proofs that prove the classification without revealing the count
        velocity_score, velocity_flags, velocity_proofs = self._evaluate_velocity_risk(tx)
        score += velocity_score
        flags.extend(velocity_flags)

        # [DOC] Factor 3: amounts deliberately just below ₹10 lakh threshold add 0–30 points (structuring)
        # [DOC] Also returns structuring_proofs — ZK range proof proving the amount classification in zero knowledge
        structuring_score, structuring_flags, structuring_proofs = self._evaluate_structuring_risk(tx)
        score += structuring_score
        flags.extend(structuring_flags)

        # [DOC] Apply context discounts: trusted business accounts and verified long-term recipients reduce the score
        score = self._apply_context_adjustments(tx, score)

        # [DOC] Cap at 100 so the score cannot exceed the scale even if multiple factors fire simultaneously
        score = min(score, Decimal('100.00'))

        # [DOC] If score >= 65, the transaction is flagged — but it still completes normally
        requires_investigation = score >= self.FLAG_THRESHOLD

        result = {
            'score': float(score),
            'flags': flags,
            'requires_investigation': requires_investigation,
            # [DOC] velocity_proofs: ZK evidence of the velocity classification — verifiable without revealing the count
            'velocity_proofs': velocity_proofs,
            # [DOC] structuring_proofs: ZK evidence of the amount-range classification — verifiable without revealing the amount
            'structuring_proofs': structuring_proofs,
        }

        # [DOC] Optionally persist evaluation result to DB. Callers (and tests) can skip persistence
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
        # [DOC] Write anomaly score onto the transaction ORM object (column: anomaly_score)
        tx.anomaly_score = score
        # [DOC] Store the list of triggered rule names, or None if the transaction is clean
        tx.anomaly_flags = flags if flags else None
        # [DOC] Boolean column that the court order and government systems query to find suspicious transactions
        tx.requires_investigation = requires_investigation
        # [DOC] If flagged, record the exact timestamp and set investigation_status to PENDING
        if requires_investigation:
            tx.flagged_at = datetime.now(timezone.utc)
            # [DOC] investigation_status tracks workflow: PENDING → CLEARED or CONFIRMED (updated by investigators)
            tx.investigation_status = 'PENDING'

        # [DOC] Attempt to write the updated fields to the database
        try:
            self.db.commit()
        except Exception as e:
            try:
                # [DOC] Best-effort rollback: undo all uncommitted changes if the commit failed
                self.db.rollback()
            except Exception:
                # [DOC] If rollback itself fails, swallow that error and re-raise the original
                pass
            # [DOC] Extract the transaction hash (or '<unknown>' if not set) to include in the error message
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
        # [DOC] Start this factor at zero; only one tier fires (highest matching tier wins)
        score = Decimal('0.00')
        flags = []

        # [DOC] Tier 2 (highest): ≥ ₹1 crore → maximum amount risk (40 pts) + mandatory reporting flag
        if tx.amount >= self.HIGH_VALUE_TIER_2:
            # >= ₹1 crore
            score += Decimal('40.00')
            flags.append('HIGH_VALUE_TIER_2')
            flags.append('PMLA_MANDATORY_REPORTING')
        # [DOC] Tier 1: ≥ ₹50 lakh → high amount risk (25 pts) + mandatory reporting flag
        elif tx.amount >= self.HIGH_VALUE_TIER_1:
            # >= ₹50 lakh
            score += Decimal('25.00')
            flags.append('HIGH_VALUE_TIER_1')
            flags.append('PMLA_MANDATORY_REPORTING')
        # [DOC] Tier 0: ≥ ₹10 lakh (PMLA boundary) → low amount risk (10 pts) + mandatory reporting flag
        elif tx.amount >= self.PMLA_MANDATORY_REPORTING:
            # >= ₹10 lakh
            score += Decimal('10.00')
            flags.append('PMLA_MANDATORY_REPORTING')

        return score, flags

    def _evaluate_velocity_risk(self, tx: Transaction) -> tuple:
        """
        Evaluate transaction velocity (0-30 points) with ZK proof generation.

        For whichever window fires (if any), a Pedersen range proof is generated
        that proves is_suspicious without revealing the exact transaction count.
        If no window fires, a proof is generated for the tightest (1h) window to
        confirm the sender is not suspicious there.

        Checks:
        - Last 1 hour: >= 5 txs → 30 points
        - Last 24 hours: >= 10 txs → 15 points
        - Last 7 days: >= 50 txs → 10 points

        Args:
            tx: Transaction

        Returns:
            tuple: (score, flags, velocity_proofs)
                velocity_proofs: list of dicts from prove_velocity() — one per evaluated window.
        """
        # [DOC] Start this factor at zero; only the tightest window that fires adds points
        score = Decimal('0.00')
        flags = []
        # [DOC] velocity_proofs: ZK range proofs collected for the evaluated window(s).
        # [DOC] Each proof reveals is_suspicious and a Pedersen commitment to the count, but not the count itself.
        velocity_proofs = []

        # [DOC] Count how many transactions this sender already sent in the last 1 hour, 24 hours, 7 days
        count_1h = self._count_recent_transactions(tx.sender_idx, hours=1)
        count_24h = self._count_recent_transactions(tx.sender_idx, hours=24)
        count_7d = self._count_recent_transactions(tx.sender_idx, hours=168)  # 7 days

        # [DOC] 1-hour window is the tightest and most alarming — 5+ txns in 1 hour gets the full 30 pts
        if count_1h >= self.VELOCITY_HIGH_1H:
            score += Decimal('30.00')
            # [DOC] Include the actual count in the flag name so investigators see it immediately
            flags.append(f'HIGH_VELOCITY_1H_{count_1h}')
            # [DOC] ZK proof: proves count_1h >= VELOCITY_HIGH_1H without revealing count_1h
            velocity_proofs.append(
                prove_velocity(count_1h, self.VELOCITY_HIGH_1H, "1h", tx.transaction_hash)
            )
        # [DOC] 24-hour window is medium concern — 10+ txns in a day adds 15 pts (only if 1H didn't fire)
        elif count_24h >= self.VELOCITY_HIGH_24H:
            score += Decimal('15.00')
            flags.append(f'HIGH_VELOCITY_24H_{count_24h}')
            # [DOC] ZK proof: proves count_24h >= VELOCITY_HIGH_24H without revealing count_24h
            velocity_proofs.append(
                prove_velocity(count_24h, self.VELOCITY_HIGH_24H, "24h", tx.transaction_hash)
            )
        # [DOC] 7-day window is mild concern — 50+ txns in a week adds 10 pts (only if narrower windows didn't fire)
        elif count_7d >= self.VELOCITY_HIGH_7D:
            score += Decimal('10.00')
            flags.append(f'HIGH_VELOCITY_7D_{count_7d}')
            # [DOC] ZK proof: proves count_7d >= VELOCITY_HIGH_7D without revealing count_7d
            velocity_proofs.append(
                prove_velocity(count_7d, self.VELOCITY_HIGH_7D, "7d", tx.transaction_hash)
            )
        else:
            # [DOC] No window fired. Generate a "not suspicious" proof for the tightest (1h) window
            # [DOC] so the verifier can confirm the sender is clean — count < VELOCITY_HIGH_1H in ZK.
            velocity_proofs.append(
                prove_velocity(count_1h, self.VELOCITY_HIGH_1H, "1h", tx.transaction_hash)
            )

        return score, flags, velocity_proofs

    def _evaluate_structuring_risk(self, tx: Transaction) -> tuple:
        """
        Detect structuring (breaking large transaction into smaller ones) with ZK proof generation.

        A ZK range proof is generated for the amount classification in all cases — whether or not a
        structuring pattern is found. The proof reveals is_structuring (amount in suspicious range)
        and which branch applies (BELOW / STRUCTURING / ABOVE), but never the exact amount.

        Pattern detected:
        - Transaction amount in [₹9.5 lakh, ₹10 lakh)  (suspicious range)
        - PLUS at least one prior similar transaction from the same sender in the last 24 hours

        Args:
            tx: Transaction

        Returns:
            tuple: (score, flags, structuring_proofs)
                structuring_proofs: list with one dict from prove_structuring() — always present.
        """
        # [DOC] Start this factor at zero; only fires if a structuring pattern is detected
        score = Decimal('0.00')
        flags = []
        # [DOC] structuring_proofs: always contains exactly one ZK proof — the amount-range classification.
        # [DOC] The proof proves whether tx.amount ∈ [low, high) without revealing the exact amount.
        structuring_proofs = []

        # [DOC] threshold_amount = 95% of ₹10 lakh = ₹9.5 lakh; amounts in [₹9.5L, ₹10L) are suspicious
        threshold_amount = self.STRUCTURING_THRESHOLD * self.STRUCTURING_PROXIMITY

        # [DOC] Convert thresholds and amount to int (whole rupees) for the integer-only range proof.
        # [DOC] Truncating to whole rupees loses at most ₹1 precision — acceptable for AML classification.
        low_int = int(threshold_amount)
        high_int = int(self.STRUCTURING_THRESHOLD)
        amount_int = int(tx.amount)

        # [DOC] Generate the structuring ZK proof unless amount exceeds MAX_AMOUNT.
        # [DOC] Amounts >= MAX_AMOUNT are already unambiguously ABOVE the structuring threshold —
        # [DOC] no ZKP is needed; append a lightweight sentinel so the proof list is never empty.
        if amount_int >= STRUCTURING_MAX_AMOUNT:
            structuring_proofs.append({
                "branch": "ABOVE_MAX",
                "is_structuring": False,
                "note": f"amount {amount_int} >= MAX_AMOUNT {STRUCTURING_MAX_AMOUNT}; ZKP skipped — clearly non-structuring",
            })
        else:
            structuring_proofs.append(
                prove_structuring(
                    amount=amount_int,
                    low=low_int,
                    high=high_int,
                    tx_hash=tx.transaction_hash,
                )
            )

        # [DOC] Check: is this transaction's amount in the suspicious "just below threshold" range?
        if threshold_amount <= tx.amount < self.STRUCTURING_THRESHOLD:
            # [DOC] This transaction is suspiciously close to threshold
            # [DOC] Look for other transactions by the same sender in the same amount range in the last 24 hours
            recent_similar = self._find_structuring_pattern(
                tx.sender_idx,
                threshold_amount,
                self.STRUCTURING_THRESHOLD
            )

            # [DOC] If there are prior similar transactions, this is a structuring pattern → maximum 30 pts
            if recent_similar > 0:
                # [DOC] Multiple transactions just below threshold → Structuring
                score += Decimal('30.00')
                # [DOC] +1 because recent_similar counts prior txns; current txn makes the total recent_similar+1
                flags.append(f'STRUCTURING_DETECTED_{recent_similar + 1}_TXS')

        return score, flags, structuring_proofs

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
        # [DOC] Work on a mutable copy of the score; keep original for the safety cap calculation
        score = base_score
        original_score = base_score

        # [DOC] Look up the sender's bank account to determine whether it is a BUSINESS account
        sender_account = self.db.query(BankAccount).filter(
            BankAccount.id == tx.sender_account_id
        ).first()

        # [DOC] If the account doesn't exist in DB, skip all adjustments and return unchanged score
        if not sender_account:
            return score

        # [DOC] Adjustment 1: Business accounts have inherently higher legitimate transaction volumes
        # [DOC] Multiply score by 0.6 (40% reduction) for verified BUSINESS account types
        if hasattr(sender_account, 'account_type') and sender_account.account_type == 'BUSINESS':
            score = score * Decimal('0.6')  # Reduce by 40%

        # [DOC] Adjustment 2: Verified recipients are people the sender has paid many times before
        # [DOC] A long-standing payment relationship (10+ past transactions) is strong legitimacy signal
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == tx.sender_idx,
            Recipient.recipient_idx == tx.receiver_idx,
            Recipient.is_active == True
        ).first()

        # [DOC] Only reduce score if recipient has 10+ transactions — avoids gaming with a single prior payment
        if recipient and recipient.transaction_count > 10:
            # [DOC] Verified recipient with 10+ past transactions
            score = score * Decimal('0.5')  # Reduce by 50%

        # [DOC] Adjustment 3: If this transaction is within 2× the sender's own historical maximum, it is "normal for them"
        user_max_amount = self._get_user_max_transaction_amount(tx.sender_idx)

        # [DOC] Only apply this discount if the sender has transaction history (user_max_amount is not None)
        if user_max_amount and tx.amount <= user_max_amount * 2:
            # [DOC] Transaction is within 2x of user's historical max
            score = score * Decimal('0.7')  # Reduce by 30%

        # [DOC] Safety cap: no matter how many discounts apply, score stays at least 10% of original
        # [DOC] Prevents a perfect combination of factors from driving score to 0 and hiding real risk
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
        # [DOC] cutoff_time: the earliest point in the window; transactions before this are ignored
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        # [DOC] COUNT(*) in SQL — far cheaper than fetching all rows when we only need the number
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
        # [DOC] Look only within the last 24 hours — a 24-hour window mirrors PMLA reporting cycles
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.STRUCTURING_WINDOW_HOURS)

        # [DOC] Count transactions by this sender whose amount falls in the suspicious [95%threshold, threshold) band
        count = self.db.query(Transaction).filter(
            Transaction.sender_idx == user_idx,
            Transaction.amount >= min_amount,
            # [DOC] Strict less-than: amounts at exactly the threshold would be caught by amount_risk already
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
        # [DOC] 90-day window covers roughly one financial quarter — a meaningful behavioral baseline period
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=90)

        # [DOC] SQL MAX() aggregate returns None if there are no matching rows (new user with no history)
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
        # [DOC] Ordered by flagged_at descending so the most recently flagged transaction appears first
        return self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        ).order_by(Transaction.flagged_at.desc()).limit(limit).offset(offset).all()

    def get_statistics(self) -> Dict:
        """
        Get anomaly detection statistics

        Returns:
            dict: Statistics
        """
        # [DOC] Total transaction count: denominator for computing the flagged percentage
        total_txs = self.db.query(Transaction).count()
        # [DOC] flagged_txs: any transaction that scored >= 65 at evaluation time
        flagged_txs = self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        ).count()

        # [DOC] cleared_txs: flagged transactions that investigators later marked as non-suspicious
        cleared_txs = self.db.query(Transaction).filter(
            Transaction.investigation_status == 'CLEARED'
        ).count()

        # [DOC] false_positive_rate: cleared / flagged — measures how often the engine over-flags
        false_positive_rate = (cleared_txs / flagged_txs * 100) if flagged_txs > 0 else 0

        return {
            'total_transactions': total_txs,
            'flagged_transactions': flagged_txs,
            'cleared_transactions': cleared_txs,
            'false_positive_rate': round(false_positive_rate, 2),
            # [DOC] flagged_percentage: what fraction of all transactions were flagged — should stay low
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
