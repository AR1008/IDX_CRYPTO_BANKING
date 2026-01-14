"""
Transaction Model - Complete transaction history with cryptographic privacy.

Stores sender/receiver IDX, session IDs, amounts, fees, status progression,
blockchain references, and cryptographic commitments for privacy.
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Numeric, DateTime, Enum, Index, Text, Boolean, LargeBinary
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
import enum
from database.connection import Base
from sqlalchemy.orm import relationship

class TransactionStatus(enum.Enum):
    """Transaction lifecycle states: PENDING -> AWAITING_RECEIVER -> MINING -> COMPLETED."""
    PENDING = "pending"                          # Transaction created by sender
    AWAITING_RECEIVER = "awaiting_receiver"      # Waiting for receiver to select bank account
    MINING = "mining"                            # Being mined on public chain
    PUBLIC_CONFIRMED = "public_confirmed"        # Added to public blockchain
    PRIVATE_CONFIRMED = "private_confirmed"      # Added to private blockchain
    COMPLETED = "completed"                      # Fully processed, balances updated
    FAILED = "failed"                            # Transaction failed (error occurred)
    REJECTED = "rejected"                    # Transaction failed (error occurred)


class Transaction(Base):
    """Transaction records with cryptographic commitments and anomaly detection."""
    
    __tablename__ = 'transactions'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Sequence number (CRITICAL for replay attack prevention)
    sequence_number = Column(
        Integer,
        unique=True,
        nullable=False,
        autoincrement=True,
        index=True,
        comment="Monotonically increasing sequence (prevents replay attacks)"
    )

    # Batch ID (for batch processing)
    batch_id = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Batch identifier for batch processing (100 txs/batch)"
    )

    # Transaction hash (unique identifier for blockchain)
    # Format: SHA-256 hash of transaction data
    transaction_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique transaction hash (SHA-256)"
    )
    
    # Sender information
    # Bank accounts involved (not just user IDX)
    sender_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=False, index=True)
    receiver_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=True, index=True)  # Nullable until receiver confirms
    sender_idx = Column(String(255), nullable=False, index=True)
    receiver_idx = Column(String(255), nullable=False, index=True)

    sender_session_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Sender's session ID (24h rotation)"
    )
    
    
    receiver_session_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Receiver's session ID (24h rotation)"
    )
    
    # Transaction amounts (in INR)
    amount = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        comment="Transfer amount in INR"
    )
    
    fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total fee (1.5% = 0.5% miner + 1% banks)"
    )
    
    miner_fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Fee paid to miner (0.5%)"
    )
    
    bank_fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Fee split among 6 banks (1%)"
    )

    # Transaction type (for foreign bank consensus)
    transaction_type = Column(
        String(20),
        nullable=False,
        default='DOMESTIC',
        index=True,
        comment="Transaction type: DOMESTIC, TRAVEL_DEPOSIT, TRAVEL_WITHDRAWAL, TRAVEL_TRANSFER"
    )

    # ===== CRYPTOGRAPHIC FIELDS (Advanced Privacy) =====

    # Commitment (Zerocash-style) - hides transaction data on public chain
    commitment = Column(
        String(66),  # 0x + 64 hex chars
        nullable=True,
        index=True,
        comment="Cryptographic commitment (hides all transaction data)"
    )

    # Nullifier (prevents double-spend)
    nullifier = Column(
        String(66),
        unique=True,
        nullable=True,
        index=True,
        comment="Unique nullifier (prevents double-spend attacks)"
    )

    # Range proof (proves balance ≥ amount without revealing either)
    range_proof = Column(
        Text,  # ~700 bytes as JSON
        nullable=True,
        comment="Zero-knowledge range proof (balance validation)"
    )

    # Group signature (anonymous bank voting)
    group_signature = Column(
        Text,
        nullable=True,
        comment="Group signature from sender's bank (anonymous)"
    )

    # Salt for commitment opening (stored encrypted in private chain)
    commitment_salt = Column(
        String(66),
        nullable=True,
        comment="Random salt for commitment opening (private chain only)"
    )

    # ===== ANOMALY DETECTION FIELDS =====

    # Anomaly score (0-100, higher = more suspicious)
    anomaly_score = Column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        index=True,
        comment="Anomaly detection score (0-100)"
    )

    # Anomaly flags (JSON array of flags: ["HIGH_VALUE_PMLA", "STRUCTURING_DETECTED"])
    anomaly_flags = Column(
        JSON,
        nullable=True,
        comment="List of anomaly flags detected"
    )

    # Requires investigation flag (if score >= threshold)
    requires_investigation = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Flagged for investigation (score >= 65)"
    )

    # ZKP anomaly proof (zero-knowledge proof of anomaly flag)
    zkp_anomaly_proof = Column(
        Text,
        nullable=True,
        comment="Zero-knowledge proof of anomaly detection (flag hidden)"
    )

    # Threshold encrypted details (encrypted transaction details for court orders)
    threshold_encrypted_details = Column(
        LargeBinary,
        nullable=True,
        comment="Threshold-encrypted transaction details (3-party: Company+Court+RBI)"
    )

    # Investigation status
    investigation_status = Column(
        String(20),
        nullable=True,
        default=None,
        index=True,
        comment="Investigation status: None, PENDING, UNDER_REVIEW, CLEARED, AUTO_CLEARED, CONFIRMED_SUSPICIOUS"
    )

    # Timestamps for anomaly tracking
    flagged_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When transaction was flagged"
    )

    cleared_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When investigation cleared the transaction"
    )

    # Transaction status
    status = Column(
        Enum(TransactionStatus),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
        comment="Current transaction status"
    )
    
    # Blockchain references
    public_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in public chain (after mining)"
    )
    
    private_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in private chain (after consensus)"
    )
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When transaction was created"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last status update"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When transaction completed"
    )
    
    # Indexes for fast queries
    # Note: anomaly_score, requires_investigation, and investigation_status already have
    # index=True in column definitions, so no need for duplicate explicit indexes
    __table_args__ = (
        Index('idx_tx_sender', 'sender_idx'),           # All transactions by sender
        Index('idx_tx_receiver', 'receiver_idx'),       # All transactions by receiver
        Index('idx_tx_status', 'status'),               # Filter by status
        Index('idx_tx_created', 'created_at'),          # Date range queries
        Index('idx_tx_hash', 'transaction_hash'),       # Lookup by hash
        Index('idx_tx_sender_session', 'sender_session_id'),    # Session queries
        Index('idx_tx_receiver_session', 'receiver_session_id'), # Session queries
        # Indexes for advanced cryptographic features
        Index('idx_tx_sequence', 'sequence_number'),    # Sequence number lookups
        Index('idx_tx_batch', 'batch_id'),              # Batch queries
        Index('idx_tx_commitment', 'commitment'),       # Commitment lookups
        Index('idx_tx_nullifier', 'nullifier'),         # Nullifier checks (double-spend)
        # Indexes for anomaly detection (flagged_at doesn't have index=True in column)
        Index('idx_tx_flagged_at', 'flagged_at'),       # When flagged
    )
    
    def __repr__(self):
        """String representation."""
        return (
            f"<Transaction(id={self.id}, "
            f"hash={self.transaction_hash[:16]}..., "
            f"amount=INR{self.amount}, "
            f"status={self.status.value})>"
        )
    
    def to_dict(self, include_sessions=False):
        """Convert to dictionary for API responses (optionally include session IDs)."""
        data = {
            'id': self.id,
            'transaction_hash': self.transaction_hash,
            'sender_idx': self.sender_idx,
            'receiver_idx': self.receiver_idx,
            'amount': str(self.amount),
            'fee': str(self.fee),
            'miner_fee': str(self.miner_fee),
            'bank_fee': str(self.bank_fee),
            'status': self.status.value,
            'public_block_index': self.public_block_index,
            'private_block_index': self.private_block_index,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        
        # Only include session IDs with court order
        if include_sessions:
            data['sender_session_id'] = self.sender_session_id
            data['receiver_session_id'] = self.receiver_session_id
        
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        
        return data
    # Relationships to bank accounts
    # sender_account = relationship("BankAccount", foreign_keys=[sender_account_id], back_populates="transactions_sent")
    # receiver_account = relationship("BankAccount", foreign_keys=[receiver_account_id], back_populates="transactions_received")


if __name__ == "__main__":
    """Test the Transaction model."""
    from database.connection import engine, SessionLocal
    from database.models.user import User
    from core.crypto.idx_generator import IDXGenerator
    import hashlib
    
    print("=== Transaction Model Testing ===\n")
    
    # Create table
    print("Creating transactions table...")
    Base.metadata.create_all(bind=engine)
    print("[PASS] Table created!\n")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Get or create test users
        print("Test 0: Setup Test Users")
        
        # Check if users exist
        user1 = db.query(User).filter(User.pan_card == "RAJSH1234K").first()
        user2 = db.query(User).filter(User.pan_card == "PRIYA5678M").first()
        
        if not user1:
            idx1 = IDXGenerator.generate("RAJSH1234K", "100001")
            user1 = User(
                idx=idx1,
                pan_card="RAJSH1234K",
                full_name="Rajesh Kumar",
                balance=Decimal('10000.00')
            )
            db.add(user1)
        
        if not user2:
            idx2 = IDXGenerator.generate("PRIYA5678M", "100002")
            user2 = User(
                idx=idx2,
                pan_card="PRIYA5678M",
                full_name="Priya Sharma",
                balance=Decimal('5000.00')
            )
            db.add(user2)
        
        db.commit()
        print(f"  Sender: {user1.full_name} ({user1.idx[:20]}...)")
        print(f"  Receiver: {user2.full_name} ({user2.idx[:20]}...)")
        print("  [PASS] Test 0 passed!\n")
        
        # Test 1: Create transaction
        print("Test 1: Create Transaction")
        
        # Generate transaction hash
        tx_data = f"{user1.idx}:{user2.idx}:{datetime.now().timestamp()}"
        tx_hash = hashlib.sha256(tx_data.encode()).hexdigest()
        
        amount = Decimal('1000.00')
        fee = amount * Decimal('0.015')  # 1.5% total fee
        miner_fee = amount * Decimal('0.005')  # 0.5%
        bank_fee = amount * Decimal('0.01')   # 1%
        
        tx = Transaction(
            transaction_hash=tx_hash,
            sender_idx=user1.idx,
            receiver_idx=user2.idx,
            sender_session_id="SESSION_ABC123",
            receiver_session_id="SESSION_XYZ789",
            amount=amount,
            fee=fee,
            miner_fee=miner_fee,
            bank_fee=bank_fee,
            status=TransactionStatus.PENDING
        )
        
        db.add(tx)
        db.commit()
        
        print(f"  Transaction: {tx}")
        print(f"  Hash: {tx.transaction_hash[:32]}...")
        print(f"  Amount: INR{tx.amount}")
        print(f"  Fee: INR{tx.fee}")
        print("  [PASS] Test 1 passed!\n")
        
        # Test 2: Update status
        print("Test 2: Update Transaction Status")
        
        tx.status = TransactionStatus.MINING
        db.commit()
        print(f"  Status: {tx.status.value}")
        
        tx.status = TransactionStatus.PUBLIC_CONFIRMED
        tx.public_block_index = 1234
        db.commit()
        print(f"  Public block: #{tx.public_block_index}")
        
        tx.status = TransactionStatus.COMPLETED
        tx.private_block_index = 1234
        tx.completed_at = datetime.now()
        db.commit()
        print(f"  Private block: #{tx.private_block_index}")
        print(f"  Status: {tx.status.value}")
        print("  [PASS] Test 2 passed!\n")
        
        # Test 3: Query by sender
        print("Test 3: Query Transactions by Sender")
        sender_txs = db.query(Transaction).filter(
            Transaction.sender_idx == user1.idx
        ).all()
        print(f"  Found {len(sender_txs)} transactions from {user1.full_name}")
        print("  [PASS] Test 3 passed!\n")
        
        # Test 4: Query by status
        print("Test 4: Query by Status")
        completed_txs = db.query(Transaction).filter(
            Transaction.status == TransactionStatus.COMPLETED
        ).all()
        print(f"  Found {len(completed_txs)} completed transactions")
        print("  [PASS] Test 4 passed!\n")
        
        # Test 5: Public dictionary (no sessions)
        print("Test 5: Public Dictionary")
        public_data = tx.to_dict(include_sessions=False)
        print(f"  Public data keys: {list(public_data.keys())}")
        assert 'sender_session_id' not in public_data
        assert 'receiver_session_id' not in public_data
        print("  [PASS] Test 5 passed! (Sessions hidden)\n")
        
        # Test 6: Court order dictionary (with sessions)
        print("Test 6: Court Order Dictionary")
        court_data = tx.to_dict(include_sessions=True)
        print(f"  Sender session: {court_data['sender_session_id']}")
        print(f"  Receiver session: {court_data['receiver_session_id']}")
        assert 'sender_session_id' in court_data
        print("  [PASS] Test 6 passed! (Sessions shown)\n")
        
        print("=" * 50)
        print("[PASS] All Transaction model tests passed!")
        print("=" * 50)
        
    finally:
        db.close()