"""
Block Model - Store Blockchain Blocks in Database

Purpose: Persistent storage for public and private blockchain blocks

Two Separate Tables:
1. blocks_public: Public chain (session IDs, transaction hashes only)
2. blocks_private: Private chain (encrypted IDX mappings)

Why Database Storage:
- Blockchain objects exist in memory (lost on restart)
- Database persists blocks permanently
- Fast queries by index, hash, or transaction
- Easy chain validation and statistics
"""

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, Index, JSON
from sqlalchemy.sql import func
from datetime import datetime
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one mined block on the PUBLIC blockchain; contains NO real identities, only hashes
class BlockPublic(Base):
    """
    Public blockchain blocks

    Stores:
    - Block metadata (index, hash, nonce, timestamp)
    - Transaction hashes (NOT actual transaction data)
    - Previous block hash (chain linkage)
    - Mining proof (difficulty, nonce)

    Privacy: Only transaction hashes visible, no identities

    Example:
        >>> block = BlockPublic(
        ...     block_index=1,
        ...     block_hash="0000abc123...",
        ...     previous_hash="0000xyz789...",
        ...     transactions=["TX_ABC123", "TX_DEF456"],
        ...     nonce=47234,
        ...     difficulty=4
        ... )
    """

    # [DOC] Maps this Python class to the 'blocks_public' PostgreSQL table
    __tablename__ = 'blocks_public'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID, separate from block_index
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Block identification
    # [DOC] Sequential block number starting from 0 (genesis); publicly browsable; used to identify blocks in the chain
    block_index = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Block number in chain (0 = genesis)"
    )

    # [DOC] SHA-256 hash of this block's header; must start with 'difficulty' leading zero nibbles (PoW proof)
    # [DOC] Stored as 64-character hex string; links this block to the next block via next_block.previous_hash
    block_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Block's SHA-256 hash (starts with zeros)"
    )

    # [DOC] SHA-256 hash of the immediately preceding block; forms the tamper-evident chain
    # [DOC] Genesis block uses "0" as previous_hash (no parent)
    previous_hash = Column(
        String(64),
        nullable=False,
        comment="Hash of previous block (chain linkage)"
    )

    # Block content
    # [DOC] JSON array of transaction hash strings included in this block, e.g. ["TX_ABC123", "TX_DEF456"]
    # [DOC] Only hashes are stored here — actual transaction data lives in the private block
    # [DOC] Public observers can see which transactions exist but cannot link them to real identities
    transactions = Column(
        JSON,  # Store list of transaction hashes as JSON
        nullable=False,
        default=[],
        comment="List of transaction hashes in this block"
    )

    # Mining proof
    # [DOC] The integer value found by the miner such that SHA256(block_header || nonce) starts with 'difficulty' zeros
    # [DOC] Proves the miner expended computational work; validated by all nodes in O(1) time
    nonce = Column(
        Integer,
        nullable=False,
        comment="Proof of work nonce (number found by mining)"
    )

    # [DOC] Number of leading zero hex digits required in block_hash; currently 4 (configurable via POW_DIFFICULTY)
    difficulty = Column(
        Integer,
        nullable=False,
        comment="Mining difficulty (number of leading zeros)"
    )

    # Metadata
    # [DOC] Unix epoch timestamp (float) when the miner found the valid nonce and sealed the block
    timestamp = Column(
        Float,
        nullable=False,
        comment="Unix timestamp when block was created"
    )

    # [DOC] IDX pseudonym of the miner who found this block's nonce; they receive 0.5% of fees in this block
    # [DOC] NULL for the genesis block (no miner)
    mined_by = Column(
        String(100),
        nullable=True,
        comment="Miner's IDX (who mined this block)"
    )

    # Database timestamps
    # [DOC] Set automatically by the DB when the block row is inserted; distinct from the blockchain timestamp field
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Indexes
    # [DOC] Three indexes: by block_index (chain traversal), by block_hash (integrity checks), by timestamp (time queries)
    __table_args__ = (
        Index('idx_block_public_index', 'block_index'),
        Index('idx_block_public_hash', 'block_hash'),
        Index('idx_block_public_timestamp', 'timestamp'),
    )

    def __repr__(self):
        return (
            f"<BlockPublic(index={self.block_index}, "
            f"hash={self.block_hash[:16]}..., "
            f"txs={len(self.transactions)})>"
        )


# [DOC] One row = one block on the PRIVATE blockchain; contains AES-256-GCM encrypted identity records
# [DOC] Mirrors the public chain block-for-block; linked via linked_public_block
class BlockPrivate(Base):
    """
    Private blockchain blocks

    Stores:
    - Encrypted session ID → IDX mappings
    - Complete transaction details
    - Bank consensus information

    Privacy: AES-256 encrypted, only accessible with split-key

    Access Control:
    - Banks: Can decrypt (for validation)
    - RBI + Court Order: Can decrypt (for investigations)
    - Public: Cannot decrypt

    Example:
        >>> block = BlockPrivate(
        ...     block_index=1,
        ...     block_hash="PRIVATE_0000abc...",
        ...     encrypted_data="U2FsdGVkX1+vupppZks...",
        ...     linked_public_block=1
        ... )
    """

    # [DOC] Maps this Python class to the 'blocks_private' PostgreSQL table
    __tablename__ = 'blocks_private'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Block identification
    # [DOC] Sequential block number on the PRIVATE chain; should always equal the corresponding public chain block_index
    block_index = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Block number in private chain"
    )

    # [DOC] Hash of this private block's header; used to verify integrity of the private chain independently
    block_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Private block hash"
    )

    # Linkage to public chain
    # [DOC] block_index of the corresponding public block; ties the two chains together at every height
    linked_public_block = Column(
        Integer,
        nullable=False,
        comment="Corresponding public block index"
    )

    # Encrypted data (AES-256)
    # [DOC] AES-256-GCM ciphertext containing: sender_idx, receiver_idx, amount, blinding_r, timestamp for each transaction
    # [DOC] Each transaction uses its OWN unique AES key — so decrypting one transaction does not reveal others
    # [DOC] The per-transaction AES key is split via Nested Shamir: requires Company share + ONE regulatory authority share
    encrypted_data = Column(
        Text,
        nullable=False,
        comment="AES-256 encrypted session→IDX mappings"
    )

    # Encryption metadata
    # [DOC] SHA-256 hash of the encryption key (NOT the key itself); used to verify key integrity after assembly
    encryption_key_hash = Column(
        String(64),
        nullable=True,
        comment="Hash of encryption key (for verification)"
    )

    # Consensus information
    # [DOC] Count of BBS04 bank signatures collected approving this block's private records
    consensus_votes = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Number of banks that validated"
    )

    # [DOC] True once T-of-N approvals were received and the private block was officially sealed
    consensus_achieved = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether T-of-N banks approved"
    )

    # Timestamps
    # [DOC] Unix epoch timestamp when this private block was sealed by the consensus process
    timestamp = Column(
        Float,
        nullable=False,
        comment="Unix timestamp"
    )

    # [DOC] Set automatically by the DB when the row is inserted
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Indexes
    # [DOC] Three indexes: by block_index, by block_hash, and by linked_public_block (join with public chain)
    __table_args__ = (
        Index('idx_block_private_index', 'block_index'),
        Index('idx_block_private_hash', 'block_hash'),
        Index('idx_block_private_public_link', 'linked_public_block'),
    )
    
    def __repr__(self):
        return (
            f"<BlockPrivate(index={self.block_index}, "
            f"public_block={self.linked_public_block}, "
            f"consensus={self.consensus_achieved})>"
        )


# Example usage / testing
if __name__ == "__main__":
    """
    Test the Block models
    Run: python3 -m database.models.block
    """
    from database.connection import engine, SessionLocal
    import time
    
    print("=== Block Model Testing ===\n")
    
    # Create tables
    print("Creating block tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created!\n")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Cleanup: Delete old test data
        print("Cleaning up old test data...")
        db.query(BlockPublic).delete()
        db.query(BlockPrivate).delete()
        db.commit()
        print("✅ Cleanup complete!\n")
        
        # Test 1: Create public genesis block
        print("Test 1: Create Public Genesis Block")
        
        genesis_public = BlockPublic(
            block_index=0,
            block_hash="0000" + "a" * 60,  # Genesis hash
            previous_hash="0",
            transactions=[],
            nonce=0,
            difficulty=4,
            timestamp=time.time(),
            mined_by=None  # Genesis not mined by anyone
        )
        
        db.add(genesis_public)
        db.commit()
        
        print(f"  Genesis: {genesis_public}")
        print(f"  Hash: {genesis_public.block_hash[:40]}...")
        print("  ✅ Test 1 passed!\n")
        
        # Test 2: Create public block with transactions
        print("Test 2: Create Public Block with Transactions")
        
        block1_public = BlockPublic(
            block_index=1,
            block_hash="0000" + "b" * 60,
            previous_hash=genesis_public.block_hash,
            transactions=["TX_ABC123", "TX_DEF456", "TX_GHI789"],
            nonce=47234,
            difficulty=4,
            timestamp=time.time(),
            mined_by="IDX_MINER_123"
        )
        
        db.add(block1_public)
        db.commit()
        
        print(f"  Block 1: {block1_public}")
        print(f"  Transactions: {len(block1_public.transactions)}")
        print(f"  Mined by: {block1_public.mined_by}")
        print("  ✅ Test 2 passed!\n")
        
        # Test 3: Create private genesis block
        print("Test 3: Create Private Genesis Block")
        
        genesis_private = BlockPrivate(
            block_index=0,
            block_hash="PRIVATE_0000" + "a" * 52,
            linked_public_block=0,
            encrypted_data="",  # Genesis has no transactions
            timestamp=time.time(),
            consensus_votes=6,
            consensus_achieved=True
        )
        
        db.add(genesis_private)
        db.commit()
        
        print(f"  Private Genesis: {genesis_private}")
        print(f"  Linked to public block: #{genesis_private.linked_public_block}")
        print("  ✅ Test 3 passed!\n")
        
        # Test 4: Create private block with encrypted data
        print("Test 4: Create Private Block with Encrypted Data")
        
        # Simulate encrypted data (in production, this is AES-256 encrypted)
        encrypted_mapping = "U2FsdGVkX1+vupppZksvRf8NOp7Jz4rRZqw5L5FDCLY="
        
        block1_private = BlockPrivate(
            block_index=1,
            block_hash="PRIVATE_0000" + "b" * 52,
            linked_public_block=1,
            encrypted_data=encrypted_mapping,
            encryption_key_hash="abc123def456...",
            timestamp=time.time(),
            consensus_votes=6,
            consensus_achieved=True
        )
        
        db.add(block1_private)
        db.commit()
        
        print(f"  Block 1 Private: {block1_private}")
        print(f"  Encrypted data: {block1_private.encrypted_data[:40]}...")
        print(f"  Consensus: {block1_private.consensus_votes}/6 votes")
        print("  ✅ Test 4 passed!\n")
        
        # Test 5: Query blocks
        print("Test 5: Query Blocks")
        
        # Get all public blocks
        public_blocks = db.query(BlockPublic).order_by(BlockPublic.block_index).all()
        print(f"  Public chain length: {len(public_blocks)}")
        
        # Get all private blocks
        private_blocks = db.query(BlockPrivate).order_by(BlockPrivate.block_index).all()
        print(f"  Private chain length: {len(private_blocks)}")
        
        assert len(public_blocks) == len(private_blocks)
        print("  ✅ Test 5 passed! (Chains same length)\n")
        
        # Test 6: Verify chain linkage
        print("Test 6: Verify Chain Linkage")
        
        genesis = db.query(BlockPublic).filter(BlockPublic.block_index == 0).first()
        block1 = db.query(BlockPublic).filter(BlockPublic.block_index == 1).first()
        
        print(f"  Genesis hash: {genesis.block_hash[:40]}...")
        print(f"  Block 1 previous: {block1.previous_hash[:40]}...")
        print(f"  Match: {genesis.block_hash == block1.previous_hash}")
        
        assert genesis.block_hash == block1.previous_hash
        print("  ✅ Test 6 passed! (Chain properly linked)\n")
        
        # Test 7: Count transactions
        print("Test 7: Transaction Statistics")
        
        total_txs = sum(len(block.transactions) for block in public_blocks)
        print(f"  Total transactions in chain: {total_txs}")
        print(f"  Blocks with transactions: {sum(1 for b in public_blocks if b.transactions)}")
        print("  ✅ Test 7 passed!\n")
        
        print("=" * 50)
        print("✅ All Block model tests passed!")
        print("")
        print("Database Storage Summary:")
        print(f"  Public blocks: {len(public_blocks)}")
        print(f"  Private blocks: {len(private_blocks)}")
        print(f"  Total transactions: {total_txs}")
        print("=" * 50)
        
    finally:
        db.close()