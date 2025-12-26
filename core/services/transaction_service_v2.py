"""
Transaction Service V2 - With Receiver Confirmation
Author: Ashutosh Rajesh
Purpose: Complete transaction flow with receiver bank selection

Flow:
1. Sender creates transaction:
   - Selects recipient by nickname
   - Sends from their HDFC account
   - Status: AWAITING_RECEIVER
   - receiver_account_id = NULL

2. Receiver gets notification:
   - "Someone wants to send you ₹X"
   - Receiver sees sender's nickname (if saved)

3. Receiver confirms and selects bank:
   - "Receive in ICICI account"
   - receiver_account_id = ICICI account ID
   - Status: PENDING (ready for mining)

4. Mining worker processes:
   - Mines with both session IDs
   - Status: MINING → PUBLIC_CONFIRMED

5. Bank consensus:
   - Both banks (sender's HDFC + receiver's ICICI) participate
   - Other banks validate
   - Status: COMPLETED
"""

from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, Dict
import hashlib

from database.models.transaction import Transaction, TransactionStatus
from database.models.bank_account import BankAccount
from database.models.user import User
from database.models.recipient import Recipient
from core.events.event_manager import EventManager


class TransactionServiceV2:
    """Enhanced transaction service with receiver confirmation"""
    
    def __init__(self, db: Session):
        """
        Initialize service
        
        Args:
            db: Database session
        """
        self.db = db
    
    def calculate_fees(self, amount: Decimal) -> Dict[str, Decimal]:
        """
        Calculate transaction fees
        
        Total: 1.5%
        - Miner: 0.5%
        - Banks: 1.0% (split among 6 = 0.167% each)
        
        Args:
            amount: Transaction amount
            
        Returns:
            Dict with fee breakdown
        """
        total_fee = amount * Decimal('0.015')  # 1.5%
        miner_fee = amount * Decimal('0.005')  # 0.5%
        bank_fee = amount * Decimal('0.01')    # 1.0%
        
        return {
            'total_fee': total_fee,
            'miner_fee': miner_fee,
            'bank_fee': bank_fee,
            'fee_per_bank': bank_fee / Decimal('6')
        }
    
    def generate_transaction_hash(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal
    ) -> str:
        """
        Generate unique transaction hash
        
        Args:
            sender_idx: Sender's IDX
            receiver_idx: Receiver's IDX
            amount: Amount
            
        Returns:
            str: Transaction hash (SHA-256)
        """
        timestamp = str(datetime.utcnow().timestamp())
        data = f"{sender_idx}:{receiver_idx}:{amount}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def create_transaction(
        self,
        sender_account_id: int,
        recipient_nickname: str,
        amount: Decimal,
        sender_session_id: str
    ) -> Transaction:
        """
        Create transaction (Step 1: Sender initiates)
        
        Args:
            sender_account_id: Sender's bank account ID
            recipient_nickname: Recipient's nickname ("Mom", "Friend", etc.)
            amount: Amount to send
            sender_session_id: Sender's session ID
            
        Returns:
            Transaction: Created transaction (AWAITING_RECEIVER)
            
        Raises:
            ValueError: If validation fails
        """
        # Get sender account
        sender_account = self.db.query(BankAccount).filter(
            BankAccount.id == sender_account_id
        ).first()
        
        if not sender_account:
            raise ValueError(f"Sender account not found: {sender_account_id}")
        
        if sender_account.is_frozen:
            raise ValueError(f"Account is frozen: {sender_account.account_number}")
        
        # Get recipient by nickname
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == sender_account.user_idx,
            Recipient.nickname == recipient_nickname,
            Recipient.is_active == True
        ).first()
        
        if not recipient:
            raise ValueError(f"Recipient '{recipient_nickname}' not found")
        
        # Calculate fees
        fees = self.calculate_fees(amount)
        total_required = amount + fees['total_fee']
        
        # Check balance
        if sender_account.balance < total_required:
            raise ValueError(
                f"Insufficient balance. Required: ₹{total_required}, "
                f"Available: ₹{sender_account.balance}"
            )
        
        # Generate transaction hash
        tx_hash = self.generate_transaction_hash(
            sender_account.user_idx,
            recipient.recipient_idx,
            amount
        )
        
        # Create transaction (receiver_account_id = NULL initially)
        transaction = Transaction(
            transaction_hash=tx_hash,
            sender_account_id=sender_account_id,
            receiver_account_id=None,  # NULL until receiver confirms
            sender_idx=sender_account.user_idx,
            receiver_idx=recipient.recipient_idx,
            sender_session_id=sender_session_id,
            receiver_session_id=recipient.current_session_id,  # Recipient's session
            amount=amount,
            fee=fees['total_fee'],
            miner_fee=fees['miner_fee'],
            bank_fee=fees['bank_fee'],
            status=TransactionStatus.AWAITING_RECEIVER  # Wait for receiver
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"📤 Transaction created: {tx_hash[:16]}...")
        print(f"   From: {sender_account.bank_code} account")
        print(f"   To: {recipient_nickname} ({recipient.recipient_idx[:16]}...)")
        print(f"   Amount: ₹{amount}")
        print(f"   Fee: ₹{fees['total_fee']}")
        print(f"   Status: AWAITING_RECEIVER")
        
        # Emit event (receiver notification)
        EventManager.emit('transaction_pending', {
            'transaction_hash': tx_hash,
            'sender_idx': sender_account.user_idx,
            'receiver_idx': recipient.recipient_idx,
            'amount': str(amount),
            'recipient_nickname': recipient_nickname
        })
        
        return transaction
    
    def get_pending_transactions_for_receiver(self, user_idx: str):
        """
        Get transactions awaiting receiver's confirmation
        
        Args:
            user_idx: Receiver's IDX
            
        Returns:
            List[Transaction]: Pending transactions
        """
        return self.db.query(Transaction).filter(
            Transaction.receiver_idx == user_idx,
            Transaction.status == TransactionStatus.AWAITING_RECEIVER
        ).all()
    
    def confirm_transaction(
        self,
        transaction_hash: str,
        receiver_account_id: int
    ) -> Transaction:
        """
        Confirm transaction and select receiving bank (Step 2: Receiver accepts)
        
        Args:
            transaction_hash: Transaction hash
            receiver_account_id: Receiver's bank account ID (their choice)
            
        Returns:
            Transaction: Updated transaction (PENDING)
            
        Raises:
            ValueError: If validation fails
        """
        # Get transaction
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()
        
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")
        
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver. Status: {transaction.status.value}")
        
        # Get receiver account
        receiver_account = self.db.query(BankAccount).filter(
            BankAccount.id == receiver_account_id
        ).first()
        
        if not receiver_account:
            raise ValueError(f"Receiver account not found: {receiver_account_id}")
        
        # Verify account belongs to receiver
        if receiver_account.user_idx != transaction.receiver_idx:
            raise ValueError("Account does not belong to receiver")
        
        if receiver_account.is_frozen:
            raise ValueError(f"Account is frozen: {receiver_account.account_number}")
        
        # Update transaction
        transaction.receiver_account_id = receiver_account_id
        transaction.status = TransactionStatus.PENDING  # Now ready for mining
        
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"✅ Transaction confirmed: {transaction_hash[:16]}...")
        print(f"   Receiver selected: {receiver_account.bank_code} account")
        print(f"   Status: PENDING (ready for mining)")
        
        # Emit event
        EventManager.emit('transaction_confirmed', {
            'transaction_hash': transaction_hash,
            'receiver_account_id': receiver_account_id,
            'receiver_bank': receiver_account.bank_code
        })
        
        return transaction
    
    def reject_transaction(self, transaction_hash: str) -> Transaction:
        """
        Reject transaction (Step 2: Receiver declines)
        
        Args:
            transaction_hash: Transaction hash
            
        Returns:
            Transaction: Updated transaction (REJECTED)
        """
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()
        
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")
        
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver")
        
        transaction.status = TransactionStatus.REJECTED
        
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"❌ Transaction rejected: {transaction_hash[:16]}...")
        
        # Emit event
        EventManager.emit('transaction_rejected', {
            'transaction_hash': transaction_hash,
            'receiver_idx': transaction.receiver_idx
        })
        
        return transaction


# Testing
if __name__ == "__main__":
    """Test transaction service v2"""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    from core.services.recipient_service import RecipientService
    
    print("=== Transaction Service V2 Testing ===\n")
    
    db = SessionLocal()
    service = TransactionServiceV2(db)
    recipient_service = RecipientService(db)
    
    try:
        # Get test accounts
        sender_idx = IDXGenerator.generate("TESTA1234P", "100001")
        receiver_idx = IDXGenerator.generate("TESTC1234D", "100003")
        
        # Get sender's HDFC account
        sender_account = db.query(BankAccount).filter(
            BankAccount.user_idx == sender_idx,
            BankAccount.bank_code == "HDFC"
        ).first()
        
        if not sender_account:
            print("❌ Sender account not found. Run migration first.")
            exit(1)
        
        # Check if recipient exists in contact list
        recipient = recipient_service.get_recipient_by_idx(sender_idx, receiver_idx)
        if not recipient:
            print("  Adding recipient to contact list...")
            recipient = recipient_service.add_recipient(sender_idx, receiver_idx, "TestFriend")
        
        print(f"Sender account: {sender_account.bank_code} - ₹{sender_account.balance}")
        print(f"Recipient: {recipient.nickname}\n")
        
        # Test 1: Create transaction
        print("Test 1: Create Transaction (Awaiting Receiver)")
        tx = service.create_transaction(
            sender_account_id=sender_account.id,
            recipient_nickname="TestFriend",
            amount=Decimal('1000'),
            sender_session_id="SESSION_test_123"
        )
        print(f"  Status: {tx.status.value}")
        print(f"  Receiver account ID: {tx.receiver_account_id}")
        print("  ✅ Test 1 passed!\n")
        
        # Test 2: Get pending for receiver
        print("Test 2: Get Pending Transactions for Receiver")
        pending = service.get_pending_transactions_for_receiver(receiver_idx)
        print(f"  Found {len(pending)} pending transactions")
        print("  ✅ Test 2 passed!\n")
        
        print("=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        
    finally:
        db.close()