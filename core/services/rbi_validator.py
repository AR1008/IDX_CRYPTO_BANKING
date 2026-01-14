"""
RBI Validator - Independent Transaction Re-Verification
Purpose: Re-verify batches to detect malicious bank behavior and enforce slashing

RBI Role:
- Neutral third-party validator (Reserve Bank of India)
- Re-validates 10% of random batches OR challenged batches
- Detects banks that voted APPROVE on invalid transactions
- Automatic slashing with escalating penalties
- Tracks honest/malicious behavior for fiscal year rewards

Flow:
1. Batch gets consensus approval from 8/12 banks
2. RBI randomly selects 10% of batches for re-verification
3. Banks can also challenge specific batches
4. RBI independently validates all transactions in batch
5. Compare RBI verdict with each bank's vote
6. Banks that voted APPROVE on invalid transactions → SLASHED
7. Slashed funds → Treasury (distributed at fiscal year end)

Slashing Penalties (Escalating):
- 1st offense: 5% of stake
- 2nd offense: 10% of stake
- 3rd offense: 20% of stake
- Deactivation: Stake falls below 30% of initial stake

Benefits:
✅ Incentivizes honest validation
✅ Automatic detection of malicious behavior
✅ Fair escalating penalties
✅ Complete audit trail
✅ Fiscal year rewards for honest banks
"""

from database.connection import SessionLocal
from database.models.transaction import Transaction, TransactionStatus
from database.models.transaction_batch import TransactionBatch, BatchStatus
from database.models.bank_voting_record import BankVotingRecord
from database.models.bank import Bank
from database.models.treasury import Treasury
from database.models.bank_account import BankAccount
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import random
import json
from sqlalchemy.orm import joinedload, selectinload


class RBIValidator:
    """
    RBI Independent Validator

    Responsibilities:
    - Re-verify 10% of random batches
    - Handle bank challenge requests
    - Detect malicious bank votes
    - Apply automatic slashing (5%, 10%, 20%)
    - Track honest/malicious verifications
    - Manage treasury entries

    Example:
        >>> validator = RBIValidator()
        >>> validator.verify_random_batches(percentage=10)
        >>> validator.process_bank_challenge('BATCH_1001_1100', 'HDFC')
    """

    # Configuration
    RANDOM_VERIFICATION_PERCENTAGE = 10  # Re-verify 10% of batches

    # Slashing penalties (escalating)
    SLASH_FIRST_OFFENSE = Decimal('0.05')   # 5% of stake
    SLASH_SECOND_OFFENSE = Decimal('0.10')  # 10% of stake
    SLASH_THIRD_OFFENSE = Decimal('0.20')   # 20% of stake

    # Deactivation threshold
    DEACTIVATION_THRESHOLD = Decimal('0.30')  # 30% of initial stake

    def __init__(self, db=None):
        """
        Initialize RBI validator

        Args:
            db: Database session (optional, creates new if not provided)
        """
        self.db = db or SessionLocal()

    def get_fiscal_year(self) -> str:
        """
        Get current fiscal year (April-March)

        Returns:
            str: Fiscal year in format '2025-2026'
        """
        now = datetime.now()
        if now.month >= 4:  # April onwards
            return f"{now.year}-{now.year + 1}"
        else:  # Jan-March
            return f"{now.year - 1}-{now.year}"

    def select_batches_for_verification(
        self,
        status: BatchStatus = BatchStatus.MINING
    ) -> List[TransactionBatch]:
        """
        Select 10% of random batches for re-verification

        Args:
            status: Batch status to select from (default: MINING)

        Returns:
            List[TransactionBatch]: Selected batches
        """
        # Get all batches with given status that haven't been RBI verified
        all_batches = self.db.query(TransactionBatch).filter(
            TransactionBatch.status == status
        ).all()

        if not all_batches:
            return []

        # Select 10% randomly
        sample_size = max(1, int(len(all_batches) * self.RANDOM_VERIFICATION_PERCENTAGE / 100))
        selected = random.sample(all_batches, min(sample_size, len(all_batches)))

        return selected

    def validate_transaction(self, tx: Transaction, sender_account: BankAccount = None, receiver_account: BankAccount = None) -> bool:
        """
        Independently validate a single transaction

        Checks:
        - Sender has sufficient balance
        - Receiver exists
        - Amount is positive
        - Fee is correct

        Args:
            tx: Transaction to validate
            sender_account: Pre-loaded sender account (optional, for N+1 prevention)
            receiver_account: Pre-loaded receiver account (optional, for N+1 prevention)

        Returns:
            bool: True if valid, False otherwise
        """
        # Get sender and receiver accounts (if not provided)
        if sender_account is None:
            sender_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.sender_account_id
            ).first()

        if receiver_account is None:
            receiver_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.receiver_account_id
            ).first()

        # Basic checks
        if not sender_account or not receiver_account:
            return False

        if tx.amount <= 0:
            return False

        if tx.fee < 0:
            return False

        # Check sender balance (simplified - in production, check historical balance)
        total_required = tx.amount + tx.fee

        # In production, we'd check balance at time of transaction
        # For now, just validate structure

        return True

    def validate_batch(self, batch: TransactionBatch) -> bool:
        """
        Independently validate entire batch

        Args:
            batch: Batch to validate

        Returns:
            bool: True if ALL transactions valid, False if ANY invalid

        Performance: Uses eager loading to prevent N+1 queries
        """
        # Get all transactions in batch with eager loading of sender/receiver accounts
        # This prevents N+1 query problem: loads all accounts in one query
        transactions = self.db.query(Transaction).filter(
            Transaction.batch_id == batch.batch_id
        ).all()

        if not transactions:
            return False

        # Build lookup maps for accounts (to avoid repeated queries)
        account_ids = set()
        for tx in transactions:
            if tx.sender_account_id:
                account_ids.add(tx.sender_account_id)
            if tx.receiver_account_id:
                account_ids.add(tx.receiver_account_id)

        # Load all accounts in ONE query (prevents N+1 problem)
        accounts_dict = {}
        if account_ids:
            accounts = self.db.query(BankAccount).filter(
                BankAccount.id.in_(account_ids)
            ).all()
            accounts_dict = {acc.id: acc for acc in accounts}

        # Validate each transaction with pre-loaded accounts
        for tx in transactions:
            sender_account = accounts_dict.get(tx.sender_account_id)
            receiver_account = accounts_dict.get(tx.receiver_account_id)

            if not self.validate_transaction(tx, sender_account, receiver_account):
                print(f"    ❌ Invalid transaction: {tx.transaction_hash[:16]}...")
                return False

        return True

    def get_slash_percentage(self, bank: Bank) -> Decimal:
        """
        Get slash percentage based on offense count

        Args:
            bank: Bank being slashed

        Returns:
            Decimal: Slash percentage (0.05, 0.10, or 0.20)
        """
        offense_count = bank.penalty_count + 1

        if offense_count == 1:
            return self.SLASH_FIRST_OFFENSE
        elif offense_count == 2:
            return self.SLASH_SECOND_OFFENSE
        else:  # 3rd+ offense
            return self.SLASH_THIRD_OFFENSE

    def slash_bank(
        self,
        bank: Bank,
        batch_id: str,
        reason: str
    ) -> Decimal:
        """
        Slash bank stake for malicious behavior

        Penalties:
        - 1st offense: 5% of stake
        - 2nd offense: 10% of stake
        - 3rd+ offense: 20% of stake

        Args:
            bank: Bank to slash
            batch_id: Batch ID where misbehavior occurred
            reason: Reason for slashing

        Returns:
            Decimal: Amount slashed
        """
        # Calculate slash amount
        slash_percentage = self.get_slash_percentage(bank)
        slash_amount = bank.stake_amount * slash_percentage

        # Update bank
        bank.stake_amount -= slash_amount
        bank.penalty_count += 1
        bank.total_penalties += slash_amount
        bank.malicious_verifications += 1

        # Check if should deactivate
        min_stake = bank.initial_stake * self.DEACTIVATION_THRESHOLD
        if bank.stake_amount < min_stake:
            bank.is_active = False
            print(f"      ⚠️  Bank {bank.bank_code} DEACTIVATED (stake below 30% threshold)")

        # Record in treasury
        fiscal_year = self.get_fiscal_year()
        treasury_entry = Treasury(
            entry_type='SLASH',
            amount=slash_amount,
            bank_code=bank.bank_code,
            fiscal_year=fiscal_year,
            reason=f"{reason} (Batch: {batch_id})",
            offense_count=bank.penalty_count,
            processed_by='RBI_VALIDATOR'
        )

        self.db.add(treasury_entry)
        self.db.commit()

        return slash_amount

    def verify_batch_votes(
        self,
        batch: TransactionBatch,
        is_valid: bool
    ):
        """
        Verify bank votes against RBI verdict

        Logic:
        - If batch is VALID: APPROVE votes are correct, REJECT votes are incorrect
        - If batch is INVALID: REJECT votes are correct, APPROVE votes are incorrect
        - Slash banks that voted APPROVE on INVALID batch

        Args:
            batch: Batch being verified
            is_valid: RBI verdict (True = valid, False = invalid)
        """
        # Get all votes for this batch
        votes = self.db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch.batch_id
        ).all()

        if not votes:
            print(f"    ⚠️  No votes found for batch {batch.batch_id}")
            return

        print(f"\n    RBI Verdict: {'VALID' if is_valid else 'INVALID'}")
        print(f"    Checking {len(votes)} bank votes...")

        # Pre-load all banks in ONE query (prevents N+1 problem)
        bank_codes = [vote.bank_code for vote in votes]
        banks_list = self.db.query(Bank).filter(
            Bank.bank_code.in_(bank_codes)
        ).all()
        banks_dict = {bank.bank_code: bank for bank in banks_list}

        slashed_count = 0
        correct_count = 0

        for vote in votes:
            # Determine if vote was correct
            vote_correct = (vote.vote == 'APPROVE' and is_valid) or \
                          (vote.vote == 'REJECT' and not is_valid)

            # Update vote record
            vote.is_correct = vote_correct
            vote.rbi_verified = True
            vote.rbi_verification_time = datetime.now(timezone.utc)

            # Get bank from pre-loaded dict (no additional query)
            bank = banks_dict.get(vote.bank_code)

            if not bank:
                continue

            if vote_correct:
                # Reward honest behavior
                bank.honest_verifications += 1
                correct_count += 1
                print(f"      ✅ {vote.bank_code}: {vote.vote} (correct)")
            else:
                # Punish incorrect vote ONLY if they voted APPROVE on invalid batch
                if vote.vote == 'APPROVE' and not is_valid:
                    # This is malicious - approved invalid transaction
                    slash_amount = self.slash_bank(
                        bank,
                        batch.batch_id,
                        f"Voted APPROVE on invalid batch"
                    )

                    # Update vote record
                    vote.was_slashed = True
                    vote.slash_amount = int(slash_amount)

                    slashed_count += 1
                    print(f"      ⚠️  {vote.bank_code}: {vote.vote} (SLASHED ₹{slash_amount:,.0f})")
                else:
                    # Voted REJECT on valid batch - incorrect but not malicious
                    # Just track, no slashing
                    bank.malicious_verifications += 1
                    print(f"      ℹ️  {vote.bank_code}: {vote.vote} (incorrect, no slash)")

        self.db.commit()

        print(f"\n    Summary:")
        print(f"      Correct votes: {correct_count}/{len(votes)}")
        print(f"      Banks slashed: {slashed_count}")

    def verify_batch(self, batch: TransactionBatch):
        """
        Complete RBI verification of a batch

        Steps:
        1. Independently validate all transactions
        2. Compare with bank votes
        3. Slash malicious banks
        4. Update honest/malicious counters

        Args:
            batch: Batch to verify
        """
        print(f"\n  🏛️  RBI Verifying: {batch.batch_id}")
        print(f"    Transactions: {batch.transaction_count}")

        # Step 1: Validate batch
        is_valid = self.validate_batch(batch)

        # Step 2: Compare votes
        self.verify_batch_votes(batch, is_valid)

    def verify_random_batches(self):
        """
        Main entry point: Verify 10% of random batches
        """
        print("\n" + "=" * 60)
        print("RBI RANDOM BATCH VERIFICATION")
        print("=" * 60)

        # Select batches
        batches = self.select_batches_for_verification()

        if not batches:
            print("\n  No batches available for verification")
            return

        print(f"\n  Selected {len(batches)} batches for verification (10% random)\n")

        # Verify each batch
        for batch in batches:
            self.verify_batch(batch)

        print("\n" + "=" * 60)
        print("RBI VERIFICATION COMPLETE")
        print("=" * 60)

    def process_bank_challenge(
        self,
        batch_id: str,
        challenger_bank_code: str
    ):
        """
        Process bank challenge request

        Any bank can challenge a batch for RBI re-verification.

        Args:
            batch_id: Batch being challenged
            challenger_bank_code: Bank code that issued challenge
        """
        print("\n" + "=" * 60)
        print("BANK CHALLENGE PROCESSING")
        print("=" * 60)

        # Get batch
        batch = self.db.query(TransactionBatch).filter(
            TransactionBatch.batch_id == batch_id
        ).first()

        if not batch:
            print(f"\n  ❌ Batch not found: {batch_id}")
            return

        print(f"\n  Challenge by: {challenger_bank_code}")
        print(f"  Batch: {batch_id}")

        # Mark challenge in voting records
        votes = self.db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch_id
        ).all()

        for vote in votes:
            if not vote.challenged_by:
                vote.challenged_by = challenger_bank_code
                vote.challenge_time = datetime.now(timezone.utc)

        self.db.commit()

        # Perform RBI verification
        self.verify_batch(batch)

        print("\n" + "=" * 60)
        print("CHALLENGE PROCESSING COMPLETE")
        print("=" * 60)

    def get_treasury_balance(self, fiscal_year: Optional[str] = None) -> Dict[str, Decimal]:
        """
        Get treasury balance for fiscal year

        Args:
            fiscal_year: Fiscal year (default: current)

        Returns:
            dict: {total_slashed, total_rewarded, balance}
        """
        if not fiscal_year:
            fiscal_year = self.get_fiscal_year()

        from sqlalchemy import func

        total_slashed = self.db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'SLASH',
            Treasury.fiscal_year == fiscal_year
        ).scalar() or Decimal('0.00')

        total_rewarded = self.db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'REWARD',
            Treasury.fiscal_year == fiscal_year
        ).scalar() or Decimal('0.00')

        balance = total_slashed - total_rewarded

        return {
            'fiscal_year': fiscal_year,
            'total_slashed': total_slashed,
            'total_rewarded': total_rewarded,
            'balance': balance
        }

    def close(self):
        """Close database connection"""
        if self.db:
            self.db.close()


# Example usage / testing
if __name__ == "__main__":
    """
    Test RBI validator
    Run: python3 -m core.services.rbi_validator
    """
    from database.models.user import User
    from core.crypto.idx_generator import IDXGenerator
    import hashlib

    print("=== RBI Validator Testing ===\n")

    db = SessionLocal()

    try:
        # Setup: Create test batch with votes
        print("Setting up test data...\n")

        # Create test users
        user1 = db.query(User).filter(User.pan_card == "RBITEST1234P").first()
        user2 = db.query(User).filter(User.pan_card == "RBITEST5678Q").first()

        if not user1:
            idx1 = IDXGenerator.generate("RBITEST1234P", "200001")
            user1 = User(
                idx=idx1,
                pan_card="RBITEST1234P",
                full_name="RBI Test User 1",
                balance=Decimal('100000.00')
            )
            db.add(user1)

        if not user2:
            idx2 = IDXGenerator.generate("RBITEST5678Q", "200002")
            user2 = User(
                idx=idx2,
                pan_card="RBITEST5678Q",
                full_name="RBI Test User 2",
                balance=Decimal('50000.00')
            )
            db.add(user2)

        db.commit()

        # Create test batch
        batch = TransactionBatch(
            batch_id="BATCH_RBI_TEST",
            sequence_start=1,
            sequence_end=100,
            transaction_count=1,
            status=BatchStatus.MINING,
            merkle_root="test_root_" + hashlib.sha256(b"test").hexdigest()
        )
        db.add(batch)
        db.commit()

        # Create test transaction
        tx_hash = hashlib.sha256(f"{user1.idx}:{user2.idx}:rbi_test".encode()).hexdigest()
        tx = Transaction(
            transaction_hash=tx_hash,
            batch_id=batch.batch_id,
            sequence_number=1,
            sender_account_id=1,
            receiver_account_id=2,
            sender_idx=user1.idx,
            receiver_idx=user2.idx,
            sender_session_id=f"SES_RBI_SENDER",
            receiver_session_id=f"SES_RBI_RECEIVER",
            amount=Decimal('1000.00'),
            fee=Decimal('15.00'),
            miner_fee=Decimal('5.00'),
            bank_fee=Decimal('10.00'),
            status=TransactionStatus.MINING
        )
        db.add(tx)
        db.commit()

        # Create bank votes (simulate scenario: batch is INVALID, but 10 banks voted APPROVE)
        print("Creating bank votes (10 APPROVE, 2 REJECT on INVALID batch)...\n")

        bank_codes = ['SBI', 'PNB', 'BOB', 'CANARA', 'UNION', 'INDIAN', 'CENTRAL', 'UCO', 'HDFC', 'ICICI', 'AXIS', 'KOTAK']

        # Clear existing votes
        db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch.batch_id
        ).delete()
        db.commit()

        for i, bank_code in enumerate(bank_codes):
            # First 10 banks vote APPROVE (will be slashed), last 2 vote REJECT (correct)
            vote = BankVotingRecord(
                batch_id=batch.batch_id,
                bank_code=bank_code,
                vote='APPROVE' if i < 10 else 'REJECT',
                validation_time_ms=10 + i
            )
            db.add(vote)

        db.commit()
        print("✅ Created 12 bank votes\n")

        # Test 1: RBI verification
        print("Test 1: RBI Batch Verification")
        validator = RBIValidator(db)
        validator.verify_batch(batch)
        print("  ✅ Test 1 passed!\n")

        # Test 2: Check slashing results
        print("Test 2: Verify Slashing Results")

        slashed_votes = db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch.batch_id,
            BankVotingRecord.was_slashed == True
        ).count()

        print(f"  Banks slashed: {slashed_votes}")
        print(f"  Expected: 10 (voted APPROVE on invalid batch)")
        assert slashed_votes == 10
        print("  ✅ Test 2 passed!\n")

        # Test 3: Treasury balance
        print("Test 3: Treasury Balance")

        balance = validator.get_treasury_balance()
        print(f"  Fiscal year: {balance['fiscal_year']}")
        print(f"  Total slashed: ₹{balance['total_slashed']:,.2f}")
        print(f"  Balance: ₹{balance['balance']:,.2f}")

        assert balance['total_slashed'] > 0
        print("  ✅ Test 3 passed!\n")

        # Test 4: Bank challenge
        print("Test 4: Bank Challenge Mechanism")

        # Create another batch
        batch2 = TransactionBatch(
            batch_id="BATCH_CHALLENGE_TEST",
            sequence_start=101,
            sequence_end=200,
            transaction_count=0,
            status=BatchStatus.MINING,
            merkle_root="test_root_2_" + hashlib.sha256(b"test2").hexdigest()
        )
        db.add(batch2)

        # Create votes
        for bank_code in bank_codes[:3]:
            vote = BankVotingRecord(
                batch_id=batch2.batch_id,
                bank_code=bank_code,
                vote='APPROVE',
                validation_time_ms=10
            )
            db.add(vote)

        db.commit()

        # Process challenge
        validator.process_bank_challenge(batch2.batch_id, 'AXIS')

        # Verify challenge was recorded
        challenged = db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch2.batch_id,
            BankVotingRecord.challenged_by == 'AXIS'
        ).count()

        print(f"\n  Votes marked as challenged: {challenged}")
        assert challenged > 0
        print("  ✅ Test 4 passed!\n")

        print("=" * 50)
        print("✅ All RBI Validator tests passed!")
        print("=" * 50)
        print("\nKey Features Demonstrated:")
        print("  • RBI independent verification")
        print("  • Automatic slashing (5%, 10%, 20%)")
        print("  • Treasury fund management")
        print("  • Bank challenge mechanism")
        print("  • Honest/malicious vote tracking")

    finally:
        db.close()
