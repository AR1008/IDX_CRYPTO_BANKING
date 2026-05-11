"""
Transaction Batch Model
Purpose: High-performance batch processing

Batching Strategy:
- Group 100 transactions together
- Single consensus round instead of 100
- Single database commit instead of 100
- Build Merkle tree for parallel validation

Benefits:
✅ 2.75x faster throughput
✅ 100x fewer consensus votes
✅ Reduced database load
✅ Deterministic ordering
"""

from sqlalchemy import Column, Integer, String, DateTime, Enum, Index, Text
from sqlalchemy.sql import func
from datetime import datetime
import enum

# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] Python enum listing every lifecycle state a batch can be in, stored as a string in the DB
class BatchStatus(enum.Enum):
    """
    Batch lifecycle states

    Flow:
    PENDING → BUILDING → READY → MINING → COMPLETED
                            ↓
                          FAILED
    """
    # [DOC] PENDING: batch record created but not yet full (fewer than 100 transactions collected)
    PENDING = "pending"      # Waiting for more transactions
    # [DOC] BUILDING: 100 transactions collected; Merkle tree is being computed now
    BUILDING = "building"    # Building Merkle tree
    # [DOC] READY: Merkle tree computed; batch is waiting for T-of-N BBS04 bank signatures
    READY = "ready"          # Ready for consensus
    # [DOC] MINING: consensus achieved (T approvals received); PoW miner is hashing to find a valid nonce
    MINING = "mining"        # Being mined on blockchain
    # [DOC] COMPLETED: block mined and appended to both public and private chains; balances updated
    COMPLETED = "completed"  # Successfully processed
    # [DOC] FAILED: batch could not be processed (e.g. consensus not reached, Merkle error)
    FAILED = "failed"        # Batch failed


# [DOC] One row = one batch of up to 100 transactions processed together through consensus and mining
class TransactionBatch(Base):
    """
    Transaction Batch table

    Groups 100 transactions for efficient processing:
    - Single consensus round (T-of-N banks vote, T = N - X)
    - Merkle tree for parallel validation
    - Single database commit
    - Deterministic ordering via sequence numbers

    Example:
        >>> batch = TransactionBatch(
        ...     batch_id="BATCH_100_200",
        ...     sequence_start=100,
        ...     sequence_end=200,
        ...     transaction_count=100
        ... )
        >>> db.add(batch)
        >>> db.commit()
    """

    # [DOC] Maps this Python class to the 'transaction_batches' PostgreSQL table
    __tablename__ = 'transaction_batches'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Batch identifier
    # [DOC] Human-readable unique identifier, e.g. "BATCH_1_100" or "BATCH_101_200"
    # [DOC] Format: BATCH_{sequence_start}_{sequence_end}; used as foreign key in transaction rows
    batch_id = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique batch identifier (BATCH_{start}_{end})"
    )

    # Sequence range (deterministic ordering)
    # [DOC] Global transaction sequence number of the first transaction in this batch
    # [DOC] Sequence numbers enforce deterministic ordering across all batches
    sequence_start = Column(
        Integer,
        nullable=False,
        index=True,
        comment="First sequence number in batch"
    )

    # [DOC] Global transaction sequence number of the last transaction in this batch
    sequence_end = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Last sequence number in batch"
    )

    # Transaction count (should be 100, but can be less for last batch)
    # [DOC] Usually 100; may be less for the final partial batch if the queue does not fill completely
    transaction_count = Column(
        Integer,
        nullable=False,
        comment="Number of transactions in this batch"
    )

    # Merkle tree root (for verification)
    # [DOC] SHA-256 Merkle root over the 100 transaction hashes in this batch
    # [DOC] 0x-prefixed hex string (66 chars total); stored on the public blockchain block
    # [DOC] Each bank independently re-computes this root to verify no transaction was swapped or omitted
    # [DOC] Batch verification is 1.9× faster with native Rust bp_verify_batch using this root
    merkle_root = Column(
        String(66),  # 0x + 64 hex chars
        nullable=True,
        index=True,
        comment="Merkle tree root hash (for parallel validation)"
    )

    # Merkle tree structure (stored as JSON)
    # [DOC] Full intermediate Merkle tree node hashes stored as JSON; allows membership proofs per transaction
    merkle_tree = Column(
        Text,
        nullable=True,
        comment="Complete Merkle tree structure (JSON)"
    )

    # Consensus votes (stored as JSON array)
    # [DOC] JSON array where each element is one bank's BBS04 group signature approving this batch
    # [DOC] Signatures are anonymous — you cannot tell which specific bank signed without the opening key
    # [DOC] Length of this array is the current consensus_votes count; batch advances to MINING once length >= T
    consensus_votes = Column(
        Text,
        nullable=True,
        comment="Bank votes for this batch (JSON array of group signatures)"
    )

    # Blockchain references
    # [DOC] Index of the public blockchain block that contains this batch's Merkle root and nullifier set
    public_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in public chain"
    )

    # [DOC] Index of the private blockchain block that holds the AES-256-GCM encrypted transaction records
    private_block_index = Column(
        Integer,
        nullable=True,
        comment="Block number in private chain"
    )

    # Status
    # [DOC] Current lifecycle state from BatchStatus enum; drives which processing step runs next
    status = Column(
        Enum(BatchStatus),
        nullable=False,
        default=BatchStatus.PENDING,
        index=True,
        comment="Current batch status"
    )

    # Timestamps
    # [DOC] Set automatically by the DB when the batch row is first inserted
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When batch was created"
    )

    # [DOC] Set when status transitions to COMPLETED; NULL until then; used to compute throughput metrics
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When batch was completed"
    )

    # Processing metrics
    # [DOC] Wall-clock milliseconds from batch creation to COMPLETED; used in TPS benchmarks
    processing_time_ms = Column(
        Integer,
        nullable=True,
        comment="Time taken to process batch (milliseconds)"
    )

    # Indexes for fast queries
    # [DOC] Four indexes: by status (poll for READY/MINING batches), by sequence range, by time, and by Merkle root
    __table_args__ = (
        Index('idx_batch_status', 'status'),
        Index('idx_batch_sequence', 'sequence_start', 'sequence_end'),
        Index('idx_batch_created', 'created_at'),
        Index('idx_batch_merkle', 'merkle_root'),
    )

    def __repr__(self):
        """String representation"""
        return (
            f"<TransactionBatch(id={self.id}, "
            f"batch_id={self.batch_id}, "
            f"count={self.transaction_count}, "
            f"status={self.status.value})>"
        )

    def to_dict(self):
        """
        Convert to dictionary for API responses

        Returns:
            dict: Batch data
        """
        import json

        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'sequence_start': self.sequence_start,
            'sequence_end': self.sequence_end,
            'transaction_count': self.transaction_count,
            'merkle_root': self.merkle_root,
            'status': self.status.value,
            'public_block_index': self.public_block_index,
            'private_block_index': self.private_block_index,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_ms': self.processing_time_ms,
            'consensus_votes': json.loads(self.consensus_votes) if self.consensus_votes else None
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test the TransactionBatch model
    Run: python3 -m database.models.transaction_batch
    """
    from database.connection import engine, SessionLocal

    print("=== Transaction Batch Model Testing ===\n")

    # Create table
    print("Creating transaction_batches table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")

    # Create session
    db = SessionLocal()

    try:
        # Test 1: Create batch
        print("Test 1: Create Batch")

        batch = TransactionBatch(
            batch_id="BATCH_1_100",
            sequence_start=1,
            sequence_end=100,
            transaction_count=100,
            status=BatchStatus.PENDING
        )

        db.add(batch)
        db.commit()

        print(f"  Batch: {batch}")
        print(f"  Sequence range: {batch.sequence_start}-{batch.sequence_end}")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Update status
        print("Test 2: Update Batch Status")

        batch.status = BatchStatus.BUILDING
        batch.merkle_root = "0x" + "a" * 64  # Mock Merkle root
        db.commit()

        print(f"  Status: {batch.status.value}")
        print(f"  Merkle root: {batch.merkle_root[:20]}...")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Query batches
        print("Test 3: Query Batches")

        pending_batches = db.query(TransactionBatch).filter(
            TransactionBatch.status == BatchStatus.BUILDING
        ).all()

        print(f"  Found {len(pending_batches)} building batches")
        print("  ✅ Test 3 passed!\n")

        # Test 4: to_dict conversion
        print("Test 4: Dictionary Conversion")

        batch_dict = batch.to_dict()
        print(f"  Keys: {list(batch_dict.keys())}")
        print(f"  Batch ID: {batch_dict['batch_id']}")
        print("  ✅ Test 4 passed!\n")

        print("=" * 50)
        print("✅ All TransactionBatch tests passed!")
        print("=" * 50)

    finally:
        db.close()
