"""
Transaction Model - Complete transaction history with cryptographic privacy.

Stores sender/receiver IDX, session IDs, amounts, fees, status progression,
blockchain references, and cryptographic commitments for privacy.
"""

# [DOC] Column types for all the diverse data this table stores
from sqlalchemy import Column, ForeignKey, Integer, String, Numeric, DateTime, Enum, Index, Text, Boolean, LargeBinary
# [DOC] JSON is a PostgreSQL-native type for storing structured data (anomaly_flags, etc.)
from sqlalchemy.dialects.postgresql import JSON
# [DOC] func provides server-side SQL functions like func.now() for automatic timestamps
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
# [DOC] enum defines a closed set of allowed string values for the status column
import enum
from database.connection import Base
from sqlalchemy.orm import relationship


# [DOC] TransactionStatus: every transaction moves through exactly these states in order
# [DOC] Using an enum prevents invalid status strings being written to the database
class TransactionStatus(enum.Enum):
    """Transaction lifecycle states: PENDING -> AWAITING_RECEIVER -> MINING -> COMPLETED."""
    # [DOC] PENDING: transaction object created by sender but not yet confirmed by receiver
    PENDING = "pending"
    # [DOC] AWAITING_RECEIVER: sender has submitted; waiting for receiver to choose their bank account
    AWAITING_RECEIVER = "awaiting_receiver"
    # [DOC] MINING: batch containing this transaction is currently being mined (PoW in progress)
    MINING = "mining"
    # [DOC] PUBLIC_CONFIRMED: block containing this tx has been mined and added to the public chain
    PUBLIC_CONFIRMED = "public_confirmed"
    # [DOC] PRIVATE_CONFIRMED: encrypted private record has been added to the private chain
    PRIVATE_CONFIRMED = "private_confirmed"
    # [DOC] COMPLETED: balances have been updated; fees distributed; nullifier added to accumulator
    COMPLETED = "completed"
    # [DOC] FAILED: an unrecoverable error occurred during processing
    FAILED = "failed"
    # [DOC] REJECTED: receiver explicitly declined this transaction
    REJECTED = "rejected"


class Transaction(Base):
    """Transaction records with cryptographic commitments and anomaly detection."""

    # [DOC] Maps this class to the 'transactions' table in PostgreSQL
    __tablename__ = 'transactions'

    # [DOC] id: internal database primary key — not shown to users; use transaction_hash as the external identifier
    id = Column(Integer, primary_key=True, autoincrement=True)

    # [DOC] sequence_number: global monotonically-increasing counter across all transactions
    # [DOC] Prevents replay attacks: attacker cannot re-submit an old transaction because its sequence number would already exist
    sequence_number = Column(
        Integer,
        unique=True,
        nullable=False,
        autoincrement=True,
        index=True,
        comment="Monotonically increasing sequence (prevents replay attacks)"
    )

    # [DOC] batch_id: groups 100 transactions into one consensus round and one Merkle tree (e.g. "BATCH_101_200")
    # [DOC] nullable=True: set only when the batch is formed in Step 3 of the transaction flow
    batch_id = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Batch identifier for batch processing (100 txs/batch)"
    )

    # [DOC] transaction_hash: SHA-256 of transaction data — the public immutable identifier for this transaction
    # [DOC] unique=True: two different transactions cannot share a hash; index=True for fast O(log n) lookup
    transaction_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique transaction hash (SHA-256)"
    )

    # [DOC] sender_account_id: FK to bank_accounts.id — which of the sender's bank accounts funds are drawn from
    sender_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=False, index=True)

    # [DOC] receiver_account_id: FK to bank_accounts.id — nullable until receiver confirms and picks their account (Step 2)
    receiver_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=True, index=True)

    # [DOC] sender_idx: permanent pseudonym of the sender — used for account-level history lookups
    sender_idx = Column(String(255), nullable=False, index=True)

    # [DOC] receiver_idx: permanent pseudonym of the receiver — used for account-level history lookups
    receiver_idx = Column(String(255), nullable=False, index=True)

    # [DOC] sender_session_id: the 24-hour rotating session ID that appeared on the PUBLIC blockchain for the sender
    # [DOC] Session IDs rotate daily for temporal unlinkability — observers cannot correlate the same user across days
    sender_session_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Sender's session ID (24h rotation)"
    )

    # [DOC] receiver_session_id: the 24-hour rotating session ID that appeared on the PUBLIC blockchain for the receiver
    receiver_session_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Receiver's session ID (24h rotation)"
    )

    # [DOC] amount: transfer value in the local currency unit (e.g. INR); precision=10, scale=2 → up to 99,999,999.99
    amount = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        comment="Transfer amount in INR"
    )

    # [DOC] fee: total fee charged to the sender = miner_fee + bank_fee (1.5% of amount)
    fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total fee (1.5% = 0.5% miner + 1% banks)"
    )

    # [DOC] miner_fee: 0.5% of amount paid to the PoW miner who included this tx in a block
    miner_fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Fee paid to miner (0.5%)"
    )

    # [DOC] bank_fee: 1.0% of amount split equally among all N consortium banks that voted on the batch
    bank_fee = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Fee split among N consortium banks (1%)"
    )

    # [DOC] transaction_type: distinguishes domestic transfers from special travel-account operations
    transaction_type = Column(
        String(20),
        nullable=False,
        default='DOMESTIC',
        index=True,
        comment="Transaction type: DOMESTIC, TRAVEL_DEPOSIT, TRAVEL_WITHDRAWAL, TRAVEL_TRANSFER"
    )

    # ===== CRYPTOGRAPHIC FIELDS (Advanced Privacy) =====

    # [DOC] commitment: a Pedersen commitment C = v*G + r*H on secp256k1 — hides the amount on the public blockchain
    # [DOC] The EC point is serialised as SEC1-compressed 33 bytes → 66 hex chars; verifiers check it without learning the amount
    commitment = Column(
        String(66),  # 0x + 64 hex chars
        nullable=True,
        index=True,
        comment="Cryptographic commitment (hides all transaction data)"
    )

    # [DOC] nullifier: SHA-256(commitment || sender_idx || secret) — a one-time tag that marks this commitment as spent
    # [DOC] unique=True: if the same nullifier appears twice, it is a double-spend attempt; the second is immediately rejected
    nullifier = Column(
        String(66),
        unique=True,
        nullable=True,
        index=True,
        comment="Unique nullifier (prevents double-spend attacks)"
    )

    # [DOC] range_proof: a Bulletproof (Rust dalek, Ristretto255) proving 0 ≤ amount < 2^64 without revealing the amount
    # [DOC] Stored as JSON (~672 bytes for a 64-bit proof); verified by each of the N consortium banks before voting
    range_proof = Column(
        Text,  # ~700 bytes as JSON
        nullable=True,
        comment="Zero-knowledge range proof (balance validation)"
    )

    # [DOC] group_signature: BBS04 group signature from the sender's bank — proves a legitimate consortium bank approved
    # [DOC] The signature is anonymous: verifiers know "a consortium bank signed" but cannot tell which one
    group_signature = Column(
        Text,
        nullable=True,
        comment="Group signature from sender's bank (anonymous)"
    )

    # [DOC] commitment_salt: the blinding factor r used in C = v*G + r*H — needed to open (reveal) the commitment.
    # [DOC] Stored here (bank's private operational DB) and also in the AES-encrypted private chain record.
    # [DOC] Never appears on the public blockchain — only the commitment C is public.
    # [DOC] Knowing r alone does NOT reveal the amount; recovering v from C and r still requires solving ECDLP.
    commitment_salt = Column(
        String(66),
        nullable=True,
        comment="Blinding factor r for C=v*G+r*H. Bank-internal only; never on public chain."
    )

    # ===== ANOMALY DETECTION FIELDS =====

    # [DOC] anomaly_score: rule-based AML score from 0 (clean) to 100 (highly suspicious)
    # [DOC] Composed of: amount risk (40 pts) + velocity risk (30 pts) + structuring risk (30 pts)
    anomaly_score = Column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        index=True,
        comment="Anomaly detection score (0-100)"
    )

    # [DOC] anomaly_flags: JSON array of human-readable rule names that fired, e.g. ["HIGH_VALUE_PMLA", "STRUCTURING_DETECTED"]
    anomaly_flags = Column(
        JSON,
        nullable=True,
        comment="List of anomaly flags detected"
    )

    # [DOC] requires_investigation: True when anomaly_score >= 65 — triggers ZKP proof generation + encrypted detail storage
    # [DOC] CRITICAL: this flag does NOT freeze the account; the transaction still completes normally
    requires_investigation = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Flagged for investigation (score >= 65)"
    )

    # [DOC] zkp_anomaly_proof: Schnorr zero-knowledge proof that the anomaly score meets the threshold
    # [DOC] Proves "score >= 65" without revealing the actual score or the transaction amount (stored as JSON)
    zkp_anomaly_proof = Column(
        Text,
        nullable=True,
        comment="Zero-knowledge proof of anomaly detection (flag hidden)"
    )

    # [DOC] threshold_encrypted_details: AES-256-GCM encrypted JSON containing {sender_idx, receiver_idx, amount, blinding_r}
    # [DOC] The AES key is Shamir-split: outer 2-of-2 (Company + Court_Combined), inner 1-of-N (any one regulatory authority)
    # [DOC] Stored as raw bytes (LargeBinary) because it contains binary ciphertext + nonce + tag
    threshold_encrypted_details = Column(
        LargeBinary,
        nullable=True,
        comment="Threshold-encrypted transaction details (3-party: Company+Court+RBI)"
    )

    # [DOC] investigation_status: tracks the lifecycle of a flagged transaction through the investigation process
    investigation_status = Column(
        String(20),
        nullable=True,
        default=None,
        index=True,
        comment="Investigation status: None, PENDING, UNDER_REVIEW, CLEARED, AUTO_CLEARED, CONFIRMED_SUSPICIOUS"
    )

    # [DOC] flagged_at: timestamp when anomaly detection first set requires_investigation=True on this transaction
    flagged_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When transaction was flagged"
    )

    # [DOC] cleared_at: timestamp when an investigator or auto-clear process set investigation_status = CLEARED
    cleared_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When investigation cleared the transaction"
    )

    # [DOC] status: current position in the transaction lifecycle; transitions are one-directional (no going back)
    status = Column(
        Enum(TransactionStatus),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
        comment="Current transaction status"
    )

    # [DOC] public_block_index: the block number in the PUBLIC blockchain where this tx's hash was included after PoW mining
    public_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in public chain (after mining)"
    )

    # [DOC] private_block_index: the block number in the PRIVATE blockchain where the encrypted record was stored
    private_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in private chain (after consensus)"
    )

    # [DOC] created_at: set by the DB server when the transaction row is first inserted (Step 1 of the flow)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When transaction was created"
    )

    # [DOC] updated_at: automatically refreshed whenever any column in this row changes (status transitions, etc.)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last status update"
    )

    # [DOC] completed_at: set explicitly when status transitions to COMPLETED (Step 7 of the flow)
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When transaction completed"
    )

    # [DOC] Composite and single-column indexes for the query patterns used throughout the codebase
    __table_args__ = (
        Index('idx_tx_sender', 'sender_idx'),                # [DOC] "All txs sent by user X" (history page)
        Index('idx_tx_receiver', 'receiver_idx'),            # [DOC] "All txs received by user X" (history page)
        Index('idx_tx_status', 'status'),                    # [DOC] Mining worker polls for PENDING transactions
        Index('idx_tx_created', 'created_at'),               # [DOC] Date-range queries for statements
        Index('idx_tx_hash', 'transaction_hash'),            # [DOC] Public chain lookup by hash
        Index('idx_tx_sender_session', 'sender_session_id'),    # [DOC] Court order: map session → tx
        Index('idx_tx_receiver_session', 'receiver_session_id'), # [DOC] Court order: map session → tx
        Index('idx_tx_sequence', 'sequence_number'),         # [DOC] Replay-attack prevention check
        Index('idx_tx_batch', 'batch_id'),                   # [DOC] Batch processor: fetch all txs in a batch
        Index('idx_tx_commitment', 'commitment'),            # [DOC] Zero-knowledge proof lookup
        Index('idx_tx_nullifier', 'nullifier'),              # [DOC] Double-spend check: "has this nullifier been seen?"
        Index('idx_tx_flagged_at', 'flagged_at'),            # [DOC] Investigation dashboard: sort by when flagged
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
            # [DOC] str() converts Decimal to string — required for JSON serialisation
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

        # [DOC] Session IDs are private-chain data — only included when the caller has court-order authority
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
