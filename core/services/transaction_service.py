"""
Transaction Service - Business Logic for Transaction Processing
Purpose: Handle transaction creation, validation, and state management

This is the "brain" - all transaction logic lives here
APIs call this service, not the database directly
"""

from decimal import Decimal
from datetime import datetime
import hashlib
from typing import Tuple, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.models.user import User
from database.models.transaction import Transaction, TransactionStatus
from database.models.session import Session as UserSession
from config.settings import settings


class InsufficientBalanceError(Exception):
    """Raised when user doesn't have enough balance"""
    pass


class InvalidSessionError(Exception):
    """Raised when session is expired or invalid"""
    pass


class UserNotFoundError(Exception):
    """Raised when user doesn't exist"""
    pass


class TransactionService:
    """
    Core transaction processing service
    
    Responsibilities:
    - Validate transaction requests
    - Check balances
    - Create transactions
    - Calculate fees
    - Manage transaction lifecycle
    """
    
    def __init__(self, db: Session):
        """
        Initialize service with database session
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    def create_transaction(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        sender_session_id: str
    ) -> Transaction:
        """
        Create new transaction
        
        Flow:
        1. Validate sender exists and has session
        2. Validate receiver exists
        3. Check sender has sufficient balance
        4. Calculate fees
        5. Create transaction record
        6. Return transaction (status: PENDING)
        
        Args:
            sender_idx: Sender's permanent IDX
            receiver_idx: Receiver's permanent IDX
            amount: Amount to send (INR)
            sender_session_id: Sender's active session
        
        Returns:
            Transaction: Created transaction object
        
        Raises:
            UserNotFoundError: If sender or receiver doesn't exist
            InvalidSessionError: If session is expired/invalid
            InsufficientBalanceError: If sender lacks funds
        
        Example:
            >>> service = TransactionService(db)
            >>> tx = service.create_transaction(
            ...     sender_idx="IDX_abc...",
            ...     receiver_idx="IDX_def...",
            ...     amount=Decimal('1000.00'),
            ...     sender_session_id="SESSION_xyz..."
            ... )
            >>> print(tx.status)
            TransactionStatus.PENDING
        """
        
        # Step 1: Validate sender
        sender = self.db.query(User).filter(User.idx == sender_idx).first()
        if not sender:
            raise UserNotFoundError(f"Sender with IDX {sender_idx} not found")
        
        # Step 2: Validate sender's session
        sender_session = self.db.query(UserSession).filter(
            UserSession.session_id == sender_session_id,
            UserSession.user_idx == sender_idx
        ).first()
        
        if not sender_session:
            raise InvalidSessionError("Invalid session ID")
        
        if sender_session.is_expired():
            raise InvalidSessionError("Session has expired")
        
        # Step 3: Validate receiver
        receiver = self.db.query(User).filter(User.idx == receiver_idx).first()
        if not receiver:
            raise UserNotFoundError(f"Receiver with IDX {receiver_idx} not found")
        
        # Get or create receiver's session (for transaction record)
        receiver_session = self.db.query(UserSession).filter(
            UserSession.user_idx == receiver_idx,
            UserSession.is_active == True
        ).first()
        
        receiver_session_id = receiver_session.session_id if receiver_session else None
        
        # Step 4: Calculate fees
        total_fee, miner_fee, bank_fee = self._calculate_fees(amount)
        
        # Step 5: Check balance (amount + fees)
        total_deduction = amount + total_fee
        
        if sender.balance < total_deduction:
            raise InsufficientBalanceError(
                f"Insufficient balance. Required: ₹{total_deduction}, Available: ₹{sender.balance}"
            )
        
        # Step 6: Generate transaction hash
        tx_hash = self._generate_transaction_hash(
            sender_idx, receiver_idx, amount, datetime.now()
        )
        
        # Step 7: Create transaction record
        transaction = Transaction(
            transaction_hash=tx_hash,
            sender_idx=sender_idx,
            receiver_idx=receiver_idx,
            sender_session_id=sender_session_id,
            receiver_session_id=receiver_session_id,
            amount=amount,
            fee=total_fee,
            miner_fee=miner_fee,
            bank_fee=bank_fee,
            status=TransactionStatus.PENDING
        )
        
        self.db.add(transaction)
        
        # Update session last used
        sender_session.last_used_at = datetime.now()
        
        try:
            self.db.commit()
            self.db.refresh(transaction)
            
            print(f"✅ Transaction created: {tx_hash[:32]}...")
            print(f"   Amount: ₹{amount}, Fee: ₹{total_fee}")
            print(f"   Status: {transaction.status.value}")
            
            return transaction
            
        except IntegrityError as e:
            self.db.rollback()
            raise Exception(f"Failed to create transaction: {str(e)}")
    
    def get_pending_transactions(self, limit: int = 10) -> list[Transaction]:
        """
        Get pending transactions for mining
        
        Args:
            limit: Maximum number of transactions to return
        
        Returns:
            List of pending transactions
        
        Example:
            >>> pending = service.get_pending_transactions(limit=5)
            >>> print(f"Found {len(pending)} transactions to mine")
        """
        return self.db.query(Transaction).filter(
            Transaction.status == TransactionStatus.PENDING
        ).limit(limit).all()
    
    def mark_as_mining(self, transaction_id: int) -> Transaction:
        """
        Update transaction status to MINING
        
        Args:
            transaction_id: Transaction database ID
        
        Returns:
            Updated transaction
        """
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        
        if transaction:
            transaction.status = TransactionStatus.MINING
            self.db.commit()
            self.db.refresh(transaction)
        
        return transaction
    
    def mark_as_public_confirmed(
        self,
        transaction_id: int,
        block_index: int
    ) -> Transaction:
        """
        Mark transaction as confirmed on public blockchain
        
        Args:
            transaction_id: Transaction database ID
            block_index: Block number in public chain
        
        Returns:
            Updated transaction
        """
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        
        if transaction:
            transaction.status = TransactionStatus.PUBLIC_CONFIRMED
            transaction.public_block_index = block_index
            self.db.commit()
            self.db.refresh(transaction)
            
            print(f"✅ Transaction {transaction.transaction_hash[:16]}... confirmed in block #{block_index}")
        
        return transaction
    
    def complete_transaction(
        self,
        transaction_id: int,
        private_block_index: int
    ) -> Transaction:
        """
        Complete transaction - update balances and finalize
        
        This is called after both public and private blockchain confirmation
        
        Args:
            transaction_id: Transaction database ID
            private_block_index: Block number in private chain
        
        Returns:
            Completed transaction
        """
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        
        if not transaction:
            raise Exception(f"Transaction {transaction_id} not found")
        
        # Get sender and receiver
        sender = self.db.query(User).filter(
            User.idx == transaction.sender_idx
        ).first()
        
        receiver = self.db.query(User).filter(
            User.idx == transaction.receiver_idx
        ).first()
        
        # Update balances
        total_deduction = transaction.amount + transaction.fee
        sender.balance -= total_deduction
        receiver.balance += transaction.amount
        
        # Update transaction status
        transaction.status = TransactionStatus.COMPLETED
        transaction.private_block_index = private_block_index
        transaction.completed_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(transaction)
        self.db.refresh(sender)
        self.db.refresh(receiver)
        
        print(f"✅ Transaction completed!")
        print(f"   Sender balance: ₹{sender.balance}")
        print(f"   Receiver balance: ₹{receiver.balance}")
        
        return transaction
    
    def _calculate_fees(self, amount: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Calculate transaction fees
        
        Args:
            amount: Transaction amount
        
        Returns:
            Tuple of (total_fee, miner_fee, bank_fee)
        """
        miner_fee = amount * Decimal(str(settings.POW_MINER_FEE_RATE))
        bank_fee = amount * Decimal(str(settings.BANK_CONSENSUS_FEE_RATE))
        total_fee = miner_fee + bank_fee
        
        return total_fee, miner_fee, bank_fee
    
    def _generate_transaction_hash(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        timestamp: datetime
    ) -> str:
        """
        Generate unique transaction hash
        
        Args:
            sender_idx: Sender's IDX
            receiver_idx: Receiver's IDX
            amount: Transaction amount
            timestamp: When transaction created
        
        Returns:
            64-character SHA-256 hash
        """
        data = f"{sender_idx}:{receiver_idx}:{amount}:{timestamp.timestamp()}"
        return hashlib.sha256(data.encode()).hexdigest()


# Testing
if __name__ == "__main__":
    """Test the transaction service"""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    from core.crypto.session_id import SessionIDGenerator
    
    print("=== Transaction Service Testing ===\n")
    
    db = SessionLocal()
    service = TransactionService(db)
    
    try:
        # Get existing users from Day 1
        rajesh = db.query(User).filter(User.pan_card == "RAJSH1234K").first()
        priya = db.query(User).filter(User.pan_card == "PRIYA5678M").first()
        
        if not rajesh or not priya:
            print("❌ Users not found. Run Day 1 tests first!")
        else:
            # Get Rajesh's session
            rajesh_session = db.query(UserSession).filter(
                UserSession.user_idx == rajesh.idx
            ).first()
            
            if not rajesh_session:
                print("Creating session for Rajesh...")
                sess_id, expiry = SessionIDGenerator.generate(rajesh.idx, "HDFC")
                rajesh_session = UserSession(
                    session_id=sess_id,
                    user_idx=rajesh.idx,
                    bank_name="HDFC",
                    expires_at=expiry
                )
                db.add(rajesh_session)
                db.commit()
            
            print(f"Rajesh balance: ₹{rajesh.balance}")
            print(f"Priya balance: ₹{priya.balance}\n")
            
            # Create transaction
            print("Creating transaction...")
            tx = service.create_transaction(
                sender_idx=rajesh.idx,
                receiver_idx=priya.idx,
                amount=Decimal('500.00'),
                sender_session_id=rajesh_session.session_id
            )
            
            print(f"\n✅ Transaction service test passed!")
            print(f"Transaction ID: {tx.id}")
            print(f"Status: {tx.status.value}")
            
    finally:
        db.close()