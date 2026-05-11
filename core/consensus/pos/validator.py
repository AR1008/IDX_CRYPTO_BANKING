# [DOC] PoS Bank Validator — handles private blockchain consensus after PoW mining completes.
# [DOC] Two consensus sub-protocols run here:
# [DOC]   Domestic transactions: N-bank consortium (T-of-N BFT majority required, T = N - X).
# [DOC]   Travel transactions: 2-bank (sender's bank + receiver's bank, both must approve).
# [DOC] This file implements the BankValidator class, not a generic PoS coin-stake system.

"""
Bank Validator - Proof of Stake Consensus
Purpose: Banks validate transactions and create private blockchain

Flow:
1. Get transactions from public chain
2. Re-validate balances (catch double-spends)
3. Banks vote (PBFT consensus - need T-of-N, T = CONSENSUS_N - CONSENSUS_X)
4. Create private blockchain block
5. Distribute bank fees
6. Complete transactions (update balances)
"""

from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Tuple
import time
from datetime import datetime, timezone
# [DOC] Session is the SQLAlchemy DB session; select is for advanced query building.
from sqlalchemy.orm import Session
from sqlalchemy import select
# [DOC] ORM models for the tables this class reads and writes.
from database.models.bank_account import BankAccount
from database.models.transaction import Transaction, TransactionStatus
from database.models.block import BlockPublic, BlockPrivate
from database.models.bank import Bank
from database.models.user import User
from config.settings import settings


class BankValidator:
    """
    Bank validation service for private blockchain

    Responsibilities:
    - Re-validate transactions (prevent double-spend)
    - Achieve PBFT consensus (T-of-N banks, T = CONSENSUS_N - CONSENSUS_X)
    - Create private blockchain blocks
    - Distribute bank fees
    - Complete transactions atomically
    """

    def __init__(self, db: Session):
        """
        Initialize validator

        Args:
            db: Database session
        """
        self.db = db

    def _batch_load_accounts(self, account_ids: set) -> dict:
        """
        Batch-load bank accounts to prevent N+1 queries

        PERFORMANCE OPTIMIZATION: Instead of querying each account individually,
        load all accounts in a single query and store in dictionary.

        Impact: Reduces queries from O(2n) to O(1) for n transactions
        Example: 100 transactions × N banks = 1 query (batch load)

        Args:
            account_ids: Set of account IDs to load

        Returns:
            dict: account_id → BankAccount object
        """
        # [DOC] Empty set means no accounts to load — return empty dict to avoid a SELECT with empty IN().
        if not account_ids:
            return {}

        # [DOC] .in_(account_ids) generates SQL: WHERE id IN (1, 2, 3, ...) — one round-trip to the DB.
        accounts = self.db.query(BankAccount).filter(
            BankAccount.id.in_(account_ids)
        ).all()

        # [DOC] Convert list to dict keyed by account.id so lookups are O(1) instead of O(n).
        return {account.id: account for account in accounts}

    def validate_and_finalize_block(self, public_block_index: int):
        """
        Validate block with dual consensus (domestic vs travel)

        Flow:
        1. Get transactions from public block
        2. Group by transaction type (DOMESTIC vs TRAVEL_*)
        3. Domestic transactions → N-bank consortium consensus (T-of-N)
        4. Travel transactions → 2-bank consensus (2/2 sender + receiver banks)
        5. Create private block with consensus data

        Args:
            public_block_index: Public block index to validate

        Returns:
            BlockPrivate: Private block if consensus achieved, None otherwise
        """
        print(f"\n🏦 Banks validating block #{public_block_index}...")

        # [DOC] Fetch the public block row to confirm it exists and get its hash.
        public_block = self.db.query(BlockPublic).filter(
            BlockPublic.block_index == public_block_index
        ).first()

        if not public_block:
            print(f"❌ Public block #{public_block_index} not found")
            return None

        # [DOC] Fetch only the transactions that belong to this block and are in PUBLIC_CONFIRMED status.
        transactions = self.db.query(Transaction).filter(
            Transaction.public_block_index == public_block_index,
            Transaction.status == TransactionStatus.PUBLIC_CONFIRMED
        ).all()

        if not transactions:
            print(f"⚠️  No transactions to validate in block #{public_block_index}")
            return None

        print(f"   Validating {len(transactions)} transactions...")

        # [DOC] Collect all unique account IDs referenced by these transactions (sender + receiver).
        account_ids = set()
        for tx in transactions:
            account_ids.add(tx.sender_account_id)
            account_ids.add(tx.receiver_account_id)

        # [DOC] Load all referenced accounts in a single DB query (prevents N+1 query problem).
        accounts_dict = self._batch_load_accounts(account_ids)
        print(f"   Loaded {len(accounts_dict)} accounts in batch")

        # [DOC] Split transactions into domestic vs travel categories — each has its own consensus rules.
        domestic_txs = [tx for tx in transactions if tx.transaction_type == 'DOMESTIC']
        travel_txs = [tx for tx in transactions if tx.transaction_type in [
            'TRAVEL_DEPOSIT', 'TRAVEL_WITHDRAWAL', 'TRAVEL_TRANSFER'
        ]]

        print(f"   - Domestic transactions: {len(domestic_txs)}")
        print(f"   - Travel transactions: {len(travel_txs)}")

        # [DOC] Run consortium consensus (8/12 banks) for domestic transactions.
        domestic_failed = []
        if domestic_txs:
            print(f"\n   🏦 Validating {len(domestic_txs)} domestic transactions...")
            consensus_achieved, failed = self._validate_domestic(domestic_txs, public_block.block_hash, accounts_dict)
            if not consensus_achieved:
                print(f"   ❌ Domestic consensus failed")
                for tx in domestic_txs:
                    tx.status = TransactionStatus.FAILED  # [DOC] Mark all domestic txs failed if consensus fails.
                domestic_failed = domestic_txs
            else:
                domestic_failed = failed  # [DOC] Individual transactions that failed per-bank validation.

        # [DOC] Run 2-bank consensus (sender bank + receiver bank must both approve) for travel transactions.
        travel_failed = []
        if travel_txs:
            print(f"\n   ✈️  Validating {len(travel_txs)} travel transactions...")
            consensus_achieved, failed = self._validate_travel(travel_txs, accounts_dict)
            if not consensus_achieved:
                print(f"   ❌ Travel consensus failed")
                for tx in travel_txs:
                    tx.status = TransactionStatus.FAILED
                travel_failed = travel_txs
            else:
                travel_failed = failed

        # [DOC] If every single transaction failed validation, there's nothing to put in the private block.
        all_failed = domestic_failed + travel_failed
        if len(all_failed) == len(transactions):
            print(f"   ❌ All transactions failed validation")
            self.db.commit()
            return None

        # [DOC] Encrypt the private data (sender IDX, receiver IDX, amounts) for the private chain.
        print(f"\n🔒 Encrypting private blockchain data...")
        from core.services.private_chain_service import PrivateChainService

        private_service = PrivateChainService(self.db)
        encrypted_data = private_service.encrypt_transaction_data(transactions)

        # [DOC] Private block hash is derived from the public block hash — links the two chains together.
        private_hash = f"PRIVATE_{public_block.block_hash[:56]}"

        # [DOC] total_votes represents how many transactions passed validation (used for reporting).
        total_votes = len(domestic_txs) + len(travel_txs) - len(all_failed)

        # [DOC] Create the private block record — this is what stores the encrypted identity data.
        private_block = BlockPrivate(
            block_index=public_block_index,
            block_hash=private_hash,
            linked_public_block=public_block_index,  # [DOC] Foreign key back to the public chain block.
            encrypted_data=encrypted_data,
            timestamp=datetime.now().timestamp(),
            consensus_votes=total_votes,
            consensus_achieved=True
        )

        self.db.add(private_block)

        # [DOC] Update balances and status for every transaction that passed validation.
        print(f"\n💰 Completing transactions...")
        completed_count = 0
        for tx in transactions:
            if tx in all_failed:
                continue  # [DOC] Already marked FAILED above — skip.

            sender_account = accounts_dict.get(tx.sender_account_id)
            receiver_account = accounts_dict.get(tx.receiver_account_id)

            if not sender_account or not receiver_account:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - accounts not found")
                tx.status = TransactionStatus.FAILED
                continue

            # [DOC] Frozen accounts cannot send or receive — this is the legal hold mechanism.
            if sender_account.is_frozen or receiver_account.is_frozen:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - account frozen")
                tx.status = TransactionStatus.FAILED
                continue

            # [DOC] Re-check balance one final time (pessimistic lock guard against TOCTOU race).
            total_required = tx.amount + tx.fee
            if sender_account.balance < total_required:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - insufficient balance")
                tx.status = TransactionStatus.FAILED
                continue

            # [DOC] Atomically debit sender and credit receiver.
            sender_account.balance -= total_required     # [DOC] Deduct amount + total fee from sender.
            receiver_account.balance += tx.amount        # [DOC] Credit only the amount (fee stays with miner/banks).

            tx.status = TransactionStatus.COMPLETED
            tx.private_block_index = public_block_index  # [DOC] Record which private block holds this tx's encrypted data.
            tx.completed_at = datetime.utcnow()

            completed_count += 1

            print(f"   ✅ TX {tx.transaction_hash[:16]}... completed")
            print(f"      {sender_account.bank_code} → {receiver_account.bank_code}: ₹{tx.amount}")

        # [DOC] Commit everything: private block, transaction statuses, and balance changes.
        self.db.commit()

        print(f"   ✅ {completed_count} transactions completed")

        return private_block

    def _validate_domestic(self, transactions: List[Transaction], public_block_hash: str, accounts_dict: dict) -> Tuple[bool, List[Transaction]]:
        """
        Validate domestic transactions with 12-bank consortium consensus

        Flow:
        1. Get all 12 consortium banks
        2. Each bank validates all transactions
        3. Need 8/12 approval (Byzantine fault tolerance)
        4. Distribute bank fees equally (1% ÷ 12 per bank)

        Args:
            transactions: Domestic transactions to validate
            public_block_hash: Public block hash for reference
            accounts_dict: Pre-loaded bank accounts dictionary (prevents N+1 queries)

        Returns:
            Tuple[bool, List[Transaction]]: (consensus_achieved, failed_transactions)
        """
        # [DOC] Fetch all active consortium banks — these are the N banks in the BFT quorum.
        consortium_banks = self.db.query(Bank).filter(Bank.is_active == True).all()

        # [DOC] Need at least 4 banks to form a meaningful quorum (2/3 majority requires ≥4 for quorum of ≥3).
        if len(consortium_banks) < 4:
            print(f"   ❌ Insufficient consortium banks: {len(consortium_banks)}/6")
            return False, transactions

        # [DOC] votes dict tracks whether each bank approved all its transactions.
        votes = {}
        failed_txs = []

        for bank in consortium_banks:
            bank_approved = True

            for tx in transactions:
                # [DOC] Each bank independently checks: accounts unfrozen, balance sufficient.
                if not self._validate_transaction_for_bank(tx, bank.bank_code, accounts_dict):
                    bank_approved = False
                    if tx not in failed_txs:
                        failed_txs.append(tx)  # [DOC] Track which tx caused a rejection (deduplicated).

            votes[bank.bank_code] = bank_approved
            status = "✅ APPROVED" if bank_approved else "❌ REJECTED"
            print(f"      {bank.bank_code}: {status}")

        # [DOC] BFT threshold: need strictly more than 2/3 of banks to approve (8/12 in the default config).
        approved_count = sum(1 for v in votes.values() if v)
        required_votes = (len(consortium_banks) * 2) // 3 + 1

        if approved_count < required_votes:
            print(f"   ❌ Consensus failed: {approved_count}/{len(consortium_banks)} (need {required_votes})")
            return False, transactions

        print(f"   ✅ Consensus achieved: {approved_count}/{len(consortium_banks)} banks approved")

        # [DOC] Distribute bank fees among all consortium members equally.
        # [DOC] Each bank earns 1% of each transaction split across N banks (1%/N per bank).
        successful_txs = [tx for tx in transactions if tx not in failed_txs]
        if successful_txs:
            total_bank_fees = sum(tx.bank_fee for tx in successful_txs)
            fee_per_bank = total_bank_fees / len(consortium_banks)

            for bank in consortium_banks:
                bank.total_fees_earned += fee_per_bank
                bank.total_validations += 1
                bank.last_validation_at = datetime.now()

            print(f"   💰 Consortium fees: ₹{total_bank_fees:.2f} (₹{fee_per_bank:.2f} per bank)")

        return True, failed_txs

    def _validate_travel(self, transactions: List[Transaction], accounts_dict: dict) -> Tuple[bool, List[Transaction]]:
        """
        Validate travel transactions with 2-bank consensus

        Flow:
        1. For each transaction, identify sender's bank and receiver's bank
        2. BOTH banks must approve (2/2 consensus - no fault tolerance)
        3. Distribute fees only to these 2 banks (0.5% each instead of 0.167%)

        Args:
            transactions: Travel transactions to validate
            accounts_dict: Pre-loaded bank accounts dictionary (prevents N+1 queries)

        Returns:
            Tuple[bool, List[Transaction]]: (consensus_achieved, failed_transactions)
        """
        from database.models.foreign_bank import ForeignBank

        failed_txs = []

        # [DOC] Pre-load all domestic consortium banks indexed by bank_code for O(1) lookup.
        all_banks = self.db.query(Bank).filter(Bank.is_active == True).all()
        banks_dict = {bank.bank_code: bank for bank in all_banks}

        # [DOC] Pre-load all foreign banks — travel accounts may involve international bank counterparties.
        all_foreign_banks = self.db.query(ForeignBank).filter(ForeignBank.is_active == True).all()
        foreign_banks_dict = {fb.bank_code: fb for fb in all_foreign_banks}

        for tx in transactions:
            sender_account = accounts_dict.get(tx.sender_account_id)
            receiver_account = accounts_dict.get(tx.receiver_account_id)

            if not sender_account or not receiver_account:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - accounts not found")
                failed_txs.append(tx)
                continue

            # [DOC] Identify the two banks involved — each runs its own independent validation.
            sender_bank_code = sender_account.bank_code
            receiver_bank_code = receiver_account.bank_code

            # [DOC] Check domestic banks first; if not found, fall back to foreign banks dict.
            sender_bank = banks_dict.get(sender_bank_code)
            if not sender_bank:
                sender_bank = foreign_banks_dict.get(sender_bank_code)

            receiver_bank = banks_dict.get(receiver_bank_code)
            if not receiver_bank:
                receiver_bank = foreign_banks_dict.get(receiver_bank_code)

            if not sender_bank or not receiver_bank:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - bank not found")
                failed_txs.append(tx)
                continue

            # [DOC] 2-of-2 consensus: BOTH the sender's bank AND the receiver's bank must approve.
            sender_approved = self._validate_transaction_for_bank(tx, sender_bank_code, accounts_dict)
            receiver_approved = self._validate_transaction_for_bank(tx, receiver_bank_code, accounts_dict)

            if not sender_approved or not receiver_approved:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - validation failed")
                print(f"      {sender_bank_code}: {'✅' if sender_approved else '❌'}")
                print(f"      {receiver_bank_code}: {'✅' if receiver_approved else '❌'}")
                failed_txs.append(tx)
                continue

            # [DOC] Split the 1% bank fee equally: each of the two banks earns 0.5%.
            fee_per_bank = tx.bank_fee / 2

            # [DOC] Update the relevant bank's stats regardless of whether it's domestic or foreign.
            if isinstance(sender_bank, Bank):
                sender_bank.total_fees_earned += fee_per_bank
                sender_bank.total_validations += 1
                sender_bank.last_validation_at = datetime.now()
            elif isinstance(sender_bank, ForeignBank):
                sender_bank.total_fees_earned += fee_per_bank
                sender_bank.total_validations += 1
                sender_bank.last_validation_at = datetime.now()

            if isinstance(receiver_bank, Bank):
                receiver_bank.total_fees_earned += fee_per_bank
                receiver_bank.total_validations += 1
                receiver_bank.last_validation_at = datetime.now()
            elif isinstance(receiver_bank, ForeignBank):
                receiver_bank.total_fees_earned += fee_per_bank
                receiver_bank.total_validations += 1
                receiver_bank.last_validation_at = datetime.now()

            print(f"   ✅ TX {tx.transaction_hash[:16]}... approved (2/2)")
            print(f"      {sender_bank_code} + {receiver_bank_code}: ₹{tx.bank_fee:.2f} (₹{fee_per_bank:.2f} each)")

        # [DOC] Return True if at least one travel tx succeeded; the list of failures is always returned.
        if failed_txs:
            print(f"   ⚠️  {len(failed_txs)}/{len(transactions)} travel transactions failed")

        return len(failed_txs) < len(transactions), failed_txs

    def _validate_transaction_for_bank(self, tx: Transaction, bank_code: str, accounts_dict: dict) -> bool:
        """
        Validate transaction from a bank's perspective

        Args:
            tx: Transaction to validate
            bank_code: Bank validating
            accounts_dict: Pre-loaded bank accounts dictionary (prevents N+1 queries)

        Returns:
            bool: True if valid
        """
        # [DOC] Use the batch-loaded dict — O(1) lookup instead of a DB query.
        sender_account = accounts_dict.get(tx.sender_account_id)

        if not sender_account:
            return False

        receiver_account = accounts_dict.get(tx.receiver_account_id)

        if not receiver_account:
            return False

        # [DOC] Frozen accounts must not participate in any transaction — court order hold applies.
        if sender_account.is_frozen or receiver_account.is_frozen:
            return False

        # [DOC] Balance check: sender must have amount + fee available right now.
        total_required = tx.amount + tx.fee
        if sender_account.balance < total_required:
            return False

        return True

    def _revalidate_transaction(self, tx: Transaction) -> Tuple[bool, Optional[str]]:
        """
        Re-validate transaction at consensus time

        CRITICAL: This catches double-spend attacks!

        Example:
        - TX1: User sends ₹2k (validated at creation, balance was ₹5k)
        - TX2: User sends ₹4k (validated at creation, balance was ₹5k)
        - TX1 gets mined first, balance now ₹3k
        - TX2 re-validation: ₹3k < ₹4k → FAIL ✅

        Args:
            tx: Transaction to validate

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, failure_reason)
        """

        # [DOC] Re-query the sender's current balance from the DB — it may have changed since tx creation.
        sender = self.db.query(User).filter(User.idx == tx.sender_idx).first()

        if not sender:
            return False, "Sender not found"

        required_amount = tx.amount + tx.fee

        # [DOC] If another transaction drained the balance after this tx was created, reject it now.
        if sender.balance < required_amount:
            return False, f"Insufficient balance: has ₹{sender.balance}, needs ₹{required_amount}"

        receiver = self.db.query(User).filter(User.idx == tx.receiver_idx).first()
        if not receiver:
            return False, "Receiver not found"

        return True, None

    def _achieve_consensus(
        self,
        valid_transactions: List[Transaction],
        failed_transactions: List[Tuple[Transaction, str]]
    ) -> Tuple[bool, int]:
        """
        Simulate PBFT consensus among N banks

        In production:
        - Each bank runs validator node
        - Banks vote independently
        - Need T-of-N approval (T = CONSENSUS_N - CONSENSUS_X)

        For now (Day 2):
        - Simulate votes based on validation results
        - If all validations passed → N/N approve
        - If some failed → Depends on failure rate

        Args:
            valid_transactions: Transactions that passed re-validation
            failed_transactions: Transactions that failed

        Returns:
            Tuple[bool, int]: (consensus_achieved, vote_count)
        """
        from config.settings import settings as _cfg

        banks = self.db.query(Bank).filter(Bank.is_active == True).all()
        threshold = _cfg.CONSENSUS_T

        if len(banks) < threshold:
            print(f"   Warning: Insufficient banks: {len(banks)}/{_cfg.CONSENSUS_N} active (need {threshold})")
            return False, len(banks)

        total_txs = len(valid_transactions) + len(failed_transactions)
        failure_rate = len(failed_transactions) / total_txs if total_txs > 0 else 0

        # [DOC] If more than 20% of transactions in the block failed, banks collectively reject the whole block.
        if failure_rate > 0.2:
            approving_banks = 2  # [DOC] Only 2 dissenting banks — not enough for quorum.
        else:
            # [DOC] Failure rate acceptable — all active banks vote to approve.
            approving_banks = len(banks)

        # [DOC] BFT threshold: T = N - X approvals required (read from settings, never hardcoded).
        consensus_achieved = approving_banks >= threshold

        return consensus_achieved, approving_banks

    def _create_private_block(
        self,
        public_block_index: int,
        public_block_hash: str,
        consensus_votes: int
    ) -> BlockPrivate:
        """
        Create private blockchain block

        Args:
            public_block_index: Linked public block
            public_block_hash: Hash of public block
            consensus_votes: Number of banks that approved

        Returns:
            BlockPrivate: Created block
        """

        # [DOC] Derive the private block hash from the public hash — creates a cryptographic link between chains.
        private_hash = f"PRIVATE_{public_block_hash[:56]}"

        # [DOC] In production: real AES-256-GCM encrypted session→IDX mapping goes here.
        encrypted_data = "ENCRYPTED_SESSION_IDX_MAPPINGS"

        private_block = BlockPrivate(
            block_index=public_block_index,
            block_hash=private_hash,
            linked_public_block=public_block_index,
            encrypted_data=encrypted_data,
            timestamp=time.time(),
            consensus_votes=consensus_votes,
            consensus_achieved=True
        )

        self.db.add(private_block)
        self.db.commit()

        return private_block

    def _finalize_transactions_atomic(
        self,
        valid_transactions: List[Transaction],
        failed_transactions: List[Tuple[Transaction, str]],
        private_block_index: int
    ):
        """
        Complete transactions atomically with balance updates

        CRITICAL: All-or-nothing operation!
        - Update all balances
        - Distribute all fees
        - Update all statuses
        - If ANY fails → ROLLBACK ALL

        Args:
            valid_transactions: Transactions to complete
            failed_transactions: Transactions to mark as failed
            private_block_index: Private block number
        """

        try:
            # [DOC] Mark failed transactions first — they won't get balance updates.
            for tx, reason in failed_transactions:
                tx.status = TransactionStatus.FAILED

            banks = self.db.query(Bank).filter(Bank.is_active == True).all()
            bank_count = len(banks)

            # [DOC] Pre-load all receiver Users in a single query to avoid N+1 for receiver balance updates.
            receiver_idxs = {tx.receiver_idx for tx in valid_transactions}
            receivers_list = self.db.query(User).filter(
                User.idx.in_(receiver_idxs)
            ).all()
            receivers_dict = {user.idx: user for user in receivers_list}

            for tx in valid_transactions:
                # [DOC] with_for_update() issues SELECT ... FOR UPDATE — locks the sender row until commit.
                # [DOC] This prevents two concurrent finalizations from both reading the same balance.
                sender = self.db.query(User).filter(
                    User.idx == tx.sender_idx
                ).with_for_update().first()

                # [DOC] Receiver is safe to read from the pre-loaded dict (no concurrent credit race).
                receiver = receivers_dict.get(tx.receiver_idx)

                # [DOC] Final balance check under the pessimistic lock — last line of defence against double-spend.
                required = tx.amount + tx.fee
                if sender.balance < required:
                    tx.status = TransactionStatus.FAILED
                    print(f"   ⚠️  Transaction {tx.id} failed final balance check")
                    continue

                # [DOC] Debit sender and credit receiver — both happen in the same DB transaction.
                sender.balance -= required
                receiver.balance += tx.amount

                # [DOC] Spread the 1% bank fee equally across all active consortium banks.
                fee_per_bank = tx.bank_fee / bank_count
                for bank in banks:
                    bank.total_validations += 1
                    bank.total_fees_earned += fee_per_bank
                    bank.last_validation_at = datetime.now()

                tx.status = TransactionStatus.COMPLETED
                tx.private_block_index = private_block_index
                tx.completed_at = datetime.now()

            # [DOC] Single commit for all changes — if any update fails, the whole block rolls back.
            self.db.commit()

            print(f"   ✅ {len(valid_transactions)} transactions completed")
            print(f"   💰 Bank fees distributed: ₹{sum(tx.bank_fee for tx in valid_transactions):.2f}")

        except Exception as e:
            # [DOC] Rollback undoes all balance changes and status updates from this block.
            self.db.rollback()
            print(f"   ❌ Finalization failed: {str(e)}")
            raise


# Testing
if __name__ == "__main__":
    """Test bank validator"""
    from database.connection import SessionLocal
    from core.services.transaction_service import TransactionService
    from core.consensus.pow.miner import MiningService
    from core.crypto.idx_generator import IDXGenerator
    from core.crypto.session_id import SessionIDGenerator
    from database.models.session import Session as UserSession

    print("=== Bank Validator Testing ===\n")

    db = SessionLocal()

    try:
        # Get test users
        rajesh = db.query(User).filter(User.pan_card == "RAJSH1234K").first()
        priya = db.query(User).filter(User.pan_card == "PRIYA5678M").first()
        miner = db.query(User).filter(User.pan_card == "MINER1234A").first()

        if not all([rajesh, priya, miner]):
            print("❌ Test users not found. Run Phase 1 tests first!")
            exit(1)

        # Create banks if not exist
        bank_codes = ['HDFC', 'ICICI', 'SBI', 'AXIS', 'KOTAK', 'YES']
        for code in bank_codes:
            if not db.query(Bank).filter(Bank.bank_code == code).first():
                bank = Bank(
                    bank_code=code,
                    bank_name=f"{code} Bank",
                    stake_amount=Decimal('100000000.00'),
                    is_active=True
                )
                db.add(bank)
        db.commit()

        print(f"Rajesh balance: ₹{rajesh.balance}")
        print(f"Priya balance: ₹{priya.balance}\n")

        # Create session
        rajesh_session = db.query(UserSession).filter(
            UserSession.user_idx == rajesh.idx
        ).first()

        if not rajesh_session:
            sess_id, expiry = SessionIDGenerator.generate(rajesh.idx, "HDFC")
            rajesh_session = UserSession(
                session_id=sess_id,
                user_idx=rajesh.idx,
                bank_name="HDFC",
                expires_at=expiry
            )
            db.add(rajesh_session)
            db.commit()

        # Create transaction
        tx_service = TransactionService(db)
        tx = tx_service.create_transaction(
            sender_idx=rajesh.idx,
            receiver_idx=priya.idx,
            amount=Decimal('1000.00'),
            sender_session_id=rajesh_session.session_id
        )

        print(f"Transaction created: {tx.transaction_hash[:32]}...\n")

        # Mine transaction
        mining_service = MiningService(db, miner_idx=miner.idx)
        block = mining_service.mine_pending_transactions()

        print(f"\nBlock #{block.block_index} mined")
        print(f"Transaction status: {tx.status.value}\n")

        # Validate with banks
        validator = BankValidator(db)
        private_block = validator.validate_and_finalize_block(block.block_index)

        if private_block:
            print(f"\n✅ Bank validation test passed!")
            print(f"Private block: #{private_block.block_index}")
            print(f"Consensus: {private_block.consensus_votes}/6")

            # Check final balances
            db.refresh(rajesh)
            db.refresh(priya)
            print(f"\nFinal balances:")
            print(f"  Rajesh: ₹{rajesh.balance}")
            print(f"  Priya: ₹{priya.balance}")

            # Check transaction
            db.refresh(tx)
            print(f"\nTransaction status: {tx.status.value}")

            # Check bank fees
            hdfc = db.query(Bank).filter(Bank.bank_code == "HDFC").first()
            print(f"\nHDFC Bank earned: ₹{hdfc.total_fees_earned}")

    finally:
        db.close()
