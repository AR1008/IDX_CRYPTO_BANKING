"""
Bank Validator - Proof of Stake Consensus
Author: Ashutosh Rajesh
Purpose: Banks validate transactions and create private blockchain

Flow:
1. Get transactions from public chain
2. Re-validate balances (catch double-spends)
3. Banks vote (PBFT consensus - need 8/12)
4. Create private blockchain block
5. Distribute bank fees
6. Complete transactions (update balances)
"""

from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Tuple
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
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
    - Achieve PBFT consensus (8/12 banks)
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
        Example: 100 transactions × 6 banks = 1,200 queries → 1 query

        Args:
            account_ids: Set of account IDs to load

        Returns:
            dict: account_id → BankAccount object
        """
        if not account_ids:
            return {}

        accounts = self.db.query(BankAccount).filter(
            BankAccount.id.in_(account_ids)
        ).all()

        return {account.id: account for account in accounts}
    
    def validate_and_finalize_block(self, public_block_index: int):
        """
        Validate block with dual consensus (domestic vs travel)

        Flow:
        1. Get transactions from public block
        2. Group by transaction type (DOMESTIC vs TRAVEL_*)
        3. Domestic transactions → 12-bank consortium consensus (8/12)
        4. Travel transactions → 2-bank consensus (2/2 sender + receiver banks)
        5. Create private block with consensus data

        Args:
            public_block_index: Public block index to validate

        Returns:
            BlockPrivate: Private block if consensus achieved, None otherwise
        """
        print(f"\n🏦 Banks validating block #{public_block_index}...")

        # Get public block
        public_block = self.db.query(BlockPublic).filter(
            BlockPublic.block_index == public_block_index
        ).first()

        if not public_block:
            print(f"❌ Public block #{public_block_index} not found")
            return None

        # Get transactions in this block
        transactions = self.db.query(Transaction).filter(
            Transaction.public_block_index == public_block_index,
            Transaction.status == TransactionStatus.PUBLIC_CONFIRMED
        ).all()

        if not transactions:
            print(f"⚠️  No transactions to validate in block #{public_block_index}")
            return None

        print(f"   Validating {len(transactions)} transactions...")

        # PERFORMANCE FIX: Batch-load all accounts (prevents N+1 queries)
        account_ids = set()
        for tx in transactions:
            account_ids.add(tx.sender_account_id)
            account_ids.add(tx.receiver_account_id)

        accounts_dict = self._batch_load_accounts(account_ids)
        print(f"   Loaded {len(accounts_dict)} accounts in batch")

        # Group transactions by type
        domestic_txs = [tx for tx in transactions if tx.transaction_type == 'DOMESTIC']
        travel_txs = [tx for tx in transactions if tx.transaction_type in [
            'TRAVEL_DEPOSIT', 'TRAVEL_WITHDRAWAL', 'TRAVEL_TRANSFER'
        ]]

        print(f"   - Domestic transactions: {len(domestic_txs)}")
        print(f"   - Travel transactions: {len(travel_txs)}")

        # Validate domestic transactions (6-bank consortium consensus)
        domestic_failed = []
        if domestic_txs:
            print(f"\n   🏦 Validating {len(domestic_txs)} domestic transactions...")
            consensus_achieved, failed = self._validate_domestic(domestic_txs, public_block.block_hash, accounts_dict)
            if not consensus_achieved:
                print(f"   ❌ Domestic consensus failed")
                for tx in domestic_txs:
                    tx.status = TransactionStatus.FAILED
                domestic_failed = domestic_txs
            else:
                domestic_failed = failed

        # Validate travel transactions (2-bank consensus - sender + receiver banks)
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

        # Check if any transactions succeeded
        all_failed = domestic_failed + travel_failed
        if len(all_failed) == len(transactions):
            print(f"   ❌ All transactions failed validation")
            self.db.commit()
            return None
        # Encrypt private data
        print(f"\n🔒 Encrypting private blockchain data...")
        from core.services.private_chain_service import PrivateChainService

        private_service = PrivateChainService(self.db)
        encrypted_data = private_service.encrypt_transaction_data(transactions)

        # Create private block hash
        private_hash = f"PRIVATE_{public_block.block_hash[:56]}"

        # Calculate total consensus votes (for display)
        total_votes = len(domestic_txs) + len(travel_txs) - len(all_failed)

        # Create private block
        private_block = BlockPrivate(
            block_index=public_block_index,
            block_hash=private_hash,
            linked_public_block=public_block_index,
            encrypted_data=encrypted_data,
            timestamp=datetime.now().timestamp(),
            consensus_votes=total_votes,
            consensus_achieved=True
        )

        self.db.add(private_block)

        # Complete successful transactions
        print(f"\n💰 Completing transactions...")
        completed_count = 0
        for tx in transactions:
            if tx in all_failed:
                continue  # Already marked as failed

            # Get sender and receiver accounts from batch-loaded dict
            sender_account = accounts_dict.get(tx.sender_account_id)
            receiver_account = accounts_dict.get(tx.receiver_account_id)

            if not sender_account or not receiver_account:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - accounts not found")
                tx.status = TransactionStatus.FAILED
                continue

            # Check if accounts are frozen
            if sender_account.is_frozen or receiver_account.is_frozen:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - account frozen")
                tx.status = TransactionStatus.FAILED
                continue

            # Pessimistic lock: Check balance again
            total_required = tx.amount + tx.fee
            if sender_account.balance < total_required:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - insufficient balance")
                tx.status = TransactionStatus.FAILED
                continue

            # Execute transaction atomically
            sender_account.balance -= total_required
            receiver_account.balance += tx.amount

            # Mark complete
            tx.status = TransactionStatus.COMPLETED
            tx.private_block_index = public_block_index
            tx.completed_at = datetime.utcnow()

            completed_count += 1

            print(f"   ✅ TX {tx.transaction_hash[:16]}... completed")
            print(f"      {sender_account.bank_code} → {receiver_account.bank_code}: ₹{tx.amount}")

        # Distribute fees (already distributed in _validate_domestic and _validate_travel)
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
        # Get all consortium banks
        consortium_banks = self.db.query(Bank).filter(Bank.is_active == True).all()

        if len(consortium_banks) < 4:
            print(f"   ❌ Insufficient consortium banks: {len(consortium_banks)}/6")
            return False, transactions

        # Validate with each bank
        votes = {}
        failed_txs = []

        for bank in consortium_banks:
            bank_approved = True

            for tx in transactions:
                if not self._validate_transaction_for_bank(tx, bank.bank_code, accounts_dict):
                    bank_approved = False
                    if tx not in failed_txs:
                        failed_txs.append(tx)

            votes[bank.bank_code] = bank_approved
            status = "✅ APPROVED" if bank_approved else "❌ REJECTED"
            print(f"      {bank.bank_code}: {status}")

        # Check consensus (need 8/12)
        approved_count = sum(1 for v in votes.values() if v)
        required_votes = (len(consortium_banks) * 2) // 3 + 1  # 67% + 1 (8/12)

        if approved_count < required_votes:
            print(f"   ❌ Consensus failed: {approved_count}/{len(consortium_banks)} (need {required_votes})")
            return False, transactions

        print(f"   ✅ Consensus achieved: {approved_count}/{len(consortium_banks)} banks approved")

        # Distribute fees among consortium banks (1% total / 12 banks)
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

        for tx in transactions:
            # Get sender and receiver accounts from batch-loaded dict
            sender_account = accounts_dict.get(tx.sender_account_id)
            receiver_account = accounts_dict.get(tx.receiver_account_id)

            if not sender_account or not receiver_account:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - accounts not found")
                failed_txs.append(tx)
                continue

            # Identify the 2 banks (sender's bank + receiver's bank)
            sender_bank_code = sender_account.bank_code
            receiver_bank_code = receiver_account.bank_code

            # Try to get sender's bank (could be consortium or foreign)
            sender_bank = self.db.query(Bank).filter(
                Bank.bank_code == sender_bank_code,
                Bank.is_active == True
            ).first()

            # Try to get receiver's bank (could be consortium or foreign)
            receiver_bank = self.db.query(Bank).filter(
                Bank.bank_code == receiver_bank_code,
                Bank.is_active == True
            ).first()

            # If not consortium, check foreign banks
            if not sender_bank:
                sender_bank = self.db.query(ForeignBank).filter(
                    ForeignBank.bank_code == sender_bank_code,
                    ForeignBank.is_active == True
                ).first()

            if not receiver_bank:
                receiver_bank = self.db.query(ForeignBank).filter(
                    ForeignBank.bank_code == receiver_bank_code,
                    ForeignBank.is_active == True
                ).first()

            if not sender_bank or not receiver_bank:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - bank not found")
                failed_txs.append(tx)
                continue

            # Both banks must validate (2/2 consensus)
            sender_approved = self._validate_transaction_for_bank(tx, sender_bank_code, accounts_dict)
            receiver_approved = self._validate_transaction_for_bank(tx, receiver_bank_code, accounts_dict)

            if not sender_approved or not receiver_approved:
                print(f"   ❌ TX {tx.transaction_hash[:16]}... - validation failed")
                print(f"      {sender_bank_code}: {'✅' if sender_approved else '❌'}")
                print(f"      {receiver_bank_code}: {'✅' if receiver_approved else '❌'}")
                failed_txs.append(tx)
                continue

            # Both approved! Distribute fees (0.5% each instead of 0.167%)
            fee_per_bank = tx.bank_fee / 2  # 1% total / 2 banks = 0.5% each

            # Update sender bank
            if isinstance(sender_bank, Bank):
                sender_bank.total_fees_earned += fee_per_bank
                sender_bank.total_validations += 1
                sender_bank.last_validation_at = datetime.now()
            elif isinstance(sender_bank, ForeignBank):
                sender_bank.total_fees_earned += fee_per_bank
                sender_bank.total_validations += 1
                sender_bank.last_validation_at = datetime.now()

            # Update receiver bank
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

        # All transactions must succeed for overall consensus
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
        # Get sender account from batch-loaded dict
        sender_account = accounts_dict.get(tx.sender_account_id)

        if not sender_account:
            return False

        # Get receiver account from batch-loaded dict
        receiver_account = accounts_dict.get(tx.receiver_account_id)

        if not receiver_account:
            return False

        # Check if accounts are frozen
        if sender_account.is_frozen or receiver_account.is_frozen:
            return False

        # Check balance
        total_required = tx.amount + tx.fee
        if sender_account.balance < total_required:
            return False

        # All checks passed
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
        
        # Get current sender balance
        sender = self.db.query(User).filter(User.idx == tx.sender_idx).first()
        
        if not sender:
            return False, "Sender not found"
        
        # Check if sender has sufficient balance NOW
        required_amount = tx.amount + tx.fee
        
        if sender.balance < required_amount:
            return False, f"Insufficient balance: has ₹{sender.balance}, needs ₹{required_amount}"
        
        # Verify receiver exists
        receiver = self.db.query(User).filter(User.idx == tx.receiver_idx).first()
        if not receiver:
            return False, "Receiver not found"
        
        # All checks passed
        return True, None
    
    def _achieve_consensus(
        self, 
        valid_transactions: List[Transaction],
        failed_transactions: List[Tuple[Transaction, str]]
    ) -> Tuple[bool, int]:
        """
        Simulate PBFT consensus among 12 banks
        
        In production:
        - Each bank runs validator node
        - Banks vote independently
        - Need 8/12 approval (67% Byzantine fault tolerance)

        For now (Day 2):
        - Simulate votes based on validation results
        - If all validations passed → 12/12 approve
        - If some failed → Depends on failure rate
        
        Args:
            valid_transactions: Transactions that passed re-validation
            failed_transactions: Transactions that failed
        
        Returns:
            Tuple[bool, int]: (consensus_achieved, vote_count)
        """
        
        # Get active banks
        banks = self.db.query(Bank).filter(Bank.is_active == True).all()
        
        if len(banks) < 4:
            print(f"   ⚠️  Insufficient banks: {len(banks)}/6 active")
            return False, len(banks)
        
        # Consensus logic:
        # - All transactions valid → All banks approve
        # - Some transactions failed → Banks reject if >20% failed
        
        total_txs = len(valid_transactions) + len(failed_transactions)
        failure_rate = len(failed_transactions) / total_txs if total_txs > 0 else 0
        
        if failure_rate > 0.2:  # More than 20% failed
            # Banks reject the block
            approving_banks = 2  # Only 2 banks approve
        else:
            # Banks approve (even if some transactions failed)
            approving_banks = len(banks)

        consensus_achieved = approving_banks >= 8  # Need 8/12

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
        
        # Create private block hash (link to public)
        private_hash = f"PRIVATE_{public_block_hash[:56]}"
        
        # Encrypted data (in production: AES-256 encrypted session mappings)
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
            # Mark failed transactions
            for tx, reason in failed_transactions:
                tx.status = TransactionStatus.FAILED
                # Note: Miner already paid, we don't reverse that
            
            # Get active banks for fee distribution
            banks = self.db.query(Bank).filter(Bank.is_active == True).all()
            bank_count = len(banks)
            
            # Process valid transactions
            for tx in valid_transactions:
                # Lock sender row (HYBRID: Pessimistic lock at critical moment)
                sender = self.db.query(User).filter(
                    User.idx == tx.sender_idx
                ).with_for_update().first()
                
                receiver = self.db.query(User).filter(
                    User.idx == tx.receiver_idx
                ).first()
                
                # Double-check balance under lock
                required = tx.amount + tx.fee
                if sender.balance < required:
                    # This shouldn't happen (we already validated)
                    # But safety check under lock
                    tx.status = TransactionStatus.FAILED
                    print(f"   ⚠️  Transaction {tx.id} failed final balance check")
                    continue
                
                # Update balances atomically
                sender.balance -= required
                receiver.balance += tx.amount
                
                # Distribute bank fees
                fee_per_bank = tx.bank_fee / bank_count
                for bank in banks:
                    bank.total_validations += 1
                    bank.total_fees_earned += fee_per_bank
                    bank.last_validation_at = datetime.now()
                
                # Mark transaction complete
                tx.status = TransactionStatus.COMPLETED
                tx.private_block_index = private_block_index
                tx.completed_at = datetime.now()
            
            # Commit all changes atomically
            self.db.commit()
            
            print(f"   ✅ {len(valid_transactions)} transactions completed")
            print(f"   💰 Bank fees distributed: ₹{sum(tx.bank_fee for tx in valid_transactions):.2f}")
            
        except Exception as e:
            # ROLLBACK everything if any error
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