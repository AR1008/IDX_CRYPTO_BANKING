# [DOC] PoW Mining Service — finds valid SHA-256 block hashes and records mined blocks in the DB.
# [DOC] Proof-of-Work: the miner must find a nonce such that SHA256(block_data + nonce)
# [DOC] starts with DIFFICULTY leading zero hex characters (default DIFFICULTY=4 → "0000...").
# [DOC] This file is the MiningService class used by both MiningWorker and MinerWorker.

"""
Mining Service - Proof of Work Mining
Purpose: Mine transactions onto public blockchain

This handles:
- Getting pending transactions
- Creating blocks
- Finding valid nonces (PoW)
- Storing blocks in database
- Distributing miner fees
"""

# [DOC] Decimal is used for fee arithmetic to avoid floating-point rounding errors.
from decimal import Decimal
from datetime import datetime
import time
from typing import List, Optional

# [DOC] Session is the SQLAlchemy database session type used for all DB operations.
from sqlalchemy.orm import Session

# [DOC] ORM models for the tables this service reads from and writes to.
from database.models.transaction import Transaction, TransactionStatus
from database.models.block import BlockPublic
from database.models.user import User
# [DOC] Block is the in-memory block object that performs the actual SHA-256 PoW hash search.
from core.blockchain.public_chain.block import Block
# [DOC] Blockchain provides chain-level utilities (genesis validation, chain linking, etc.).
from core.blockchain.public_chain.chain import Blockchain
# [DOC] settings.POW_DIFFICULTY controls how many leading zeros are required.
from config.settings import settings


class MiningService:
    """
    Mining service for public blockchain

    Responsibilities:
    - Batch pending transactions
    - Mine blocks with PoW
    - Store blocks in database
    - Update transaction statuses
    - Distribute miner fees
    """

    def __init__(self, db: Session, miner_idx: str):
        """
        Initialize mining service

        Args:
            db: Database session
            miner_idx: IDX of the miner (who receives fees)
        """
        # [DOC] Store the session so all methods in this instance share one DB connection.
        self.db = db
        # [DOC] miner_idx identifies whose balance to credit with the 0.5% miner fee.
        self.miner_idx = miner_idx

    def mine_pending_transactions(self, batch_size: int = 10) -> Optional[BlockPublic]:
        """
        Mine a batch of pending transactions

        Flow:
        1. Get pending transactions (up to batch_size)
        2. If no transactions, return None
        3. Update transactions to MINING status
        4. Get last block from database
        5. Create new block with transactions
        6. Mine block (find valid nonce)
        7. Store block in database
        8. Update transactions to PUBLIC_CONFIRMED
        9. Collect miner fees
        10. Return mined block

        Args:
            batch_size: Maximum transactions per block

        Returns:
            BlockPublic: Mined block, or None if no pending transactions

        Example:
            >>> miner = MiningService(db, miner_idx="IDX_MINER_001")
            >>> block = miner.mine_pending_transactions(batch_size=10)
            >>> if block:
            ...     print(f"Mined block #{block.block_index}")
        """

        # [DOC] Fetch at most `batch_size` transactions that are in PENDING status.
        # [DOC] PENDING means: receiver confirmed, batch assigned, consensus approved — ready to mine.
        pending_txs = self.db.query(Transaction).filter(
            Transaction.status == TransactionStatus.PENDING
        ).limit(batch_size).all()

        # [DOC] If there are no pending transactions, return None — nothing to mine right now.
        if not pending_txs:
            return None

        print(f"\n⛏️  Mining {len(pending_txs)} transactions...")

        # [DOC] Mark all selected transactions as MINING so other miner threads don't pick them up.
        tx_hashes = []
        for tx in pending_txs:
            tx.status = TransactionStatus.MINING
            tx_hashes.append(tx.transaction_hash)  # [DOC] Collect hashes to embed in the block.

        self.db.commit()  # [DOC] Persist the status change before the computationally expensive mining begins.

        # [DOC] Find the most recently mined block so we know its hash (the new block's previous_hash).
        last_block = self.db.query(BlockPublic).order_by(
            BlockPublic.block_index.desc()
        ).first()

        if last_block:
            next_index = last_block.block_index + 1
            previous_hash = last_block.block_hash
        else:
            # [DOC] No blocks exist yet — create the genesis block (index 0) first.
            print("No genesis block found, creating one...")
            genesis = self._create_genesis_block()
            next_index = 1
            previous_hash = genesis.block_hash

        # [DOC] Construct an in-memory Block object with the list of transaction hashes.
        new_block = Block(
            index=next_index,
            transactions=tx_hashes,
            previous_hash=previous_hash
        )

        # [DOC] mine_block() runs the PoW loop: increments nonce until the hash has DIFFICULTY leading zeros.
        print(f"Mining block #{next_index}...")
        start_time = time.time()

        new_block.mine_block(difficulty=settings.POW_DIFFICULTY)

        mining_time = time.time() - start_time

        print(f"✅ Block #{next_index} mined!")
        print(f"   Nonce: {new_block.nonce:,}")
        print(f"   Hash: {new_block.hash[:40]}...")
        print(f"   Time: {mining_time:.2f} seconds")
        print(f"   Transactions: {len(tx_hashes)}")

        # [DOC] Persist the mined block to the blocks_public table.
        block_public = BlockPublic(
            block_index=new_block.index,
            block_hash=new_block.hash,
            previous_hash=new_block.previous_hash,
            transactions=new_block.transactions,
            nonce=new_block.nonce,
            difficulty=settings.POW_DIFFICULTY,
            timestamp=new_block.timestamp,
            mined_by=self.miner_idx  # [DOC] Record which miner found this block (for fee distribution).
        )

        self.db.add(block_public)

        # [DOC] Advance transaction statuses: MINING → PUBLIC_CONFIRMED.
        # [DOC] PUBLIC_CONFIRMED means the transaction is now part of the immutable public chain.
        for tx in pending_txs:
            tx.status = TransactionStatus.PUBLIC_CONFIRMED
            tx.public_block_index = new_block.index  # [DOC] Link each tx to the block that contains it.

        self.db.commit()

        # [DOC] Credit the miner's balance with the 0.5% fee from every transaction in this block.
        total_fees = self._collect_miner_fees(pending_txs)

        print(f"💰 Miner earned: ₹{total_fees}")

        return block_public

    def _create_genesis_block(self) -> BlockPublic:
        """
        Create genesis block (block #0)

        Returns:
            BlockPublic: Genesis block
        """
        # [DOC] Genesis block: index=0, no transactions, previous_hash="0" (sentinel value).
        genesis = Block(index=0, transactions=[], previous_hash="0")
        # [DOC] Mine the genesis block too — gives the chain a valid starting hash.
        genesis.mine_block(difficulty=settings.POW_DIFFICULTY)

        genesis_db = BlockPublic(
            block_index=0,
            block_hash=genesis.hash,
            previous_hash="0",
            transactions=[],
            nonce=genesis.nonce,
            difficulty=settings.POW_DIFFICULTY,
            timestamp=genesis.timestamp,
            mined_by=None  # [DOC] Genesis was not mined by any user — no fee is distributed.
        )

        self.db.add(genesis_db)
        self.db.commit()

        print(f"✅ Genesis block created: {genesis.hash[:40]}...")

        return genesis_db

    def _collect_miner_fees(self, transactions: List[Transaction]) -> Decimal:
        """
        Collect miner fees from transactions

        Args:
            transactions: List of mined transactions

        Returns:
            Decimal: Total fees collected
        """
        # [DOC] Look up the miner's User row to credit their balance.
        miner = self.db.query(User).filter(User.idx == self.miner_idx).first()

        if not miner:
            # [DOC] Miner IDX doesn't exist in the users table — log and skip (fees are lost).
            print(f"⚠️  Miner {self.miner_idx} not found, fees not distributed")
            return Decimal('0.00')

        total_fees = Decimal('0.00')

        for tx in transactions:
            # [DOC] tx.miner_fee was pre-calculated at transaction creation as 0.5% of the amount.
            total_fees += tx.miner_fee

        # [DOC] Add total fees to the miner's balance in one atomic DB write.
        miner.balance += total_fees
        self.db.commit()

        return total_fees

    def get_mining_stats(self) -> dict:
        """
        Get mining statistics

        Returns:
            dict: Statistics about mining activity

        Example:
            >>> stats = miner.get_mining_stats()
            >>> print(f"Blocks mined: {stats['total_blocks']}")
        """
        # [DOC] Count all blocks in the public chain.
        total_blocks = self.db.query(BlockPublic).count()

        # [DOC] Count only blocks mined by this specific miner IDX.
        miner_blocks = self.db.query(BlockPublic).filter(
            BlockPublic.mined_by == self.miner_idx
        ).count()

        # [DOC] Count confirmed transactions across the entire chain.
        total_txs = self.db.query(Transaction).filter(
            Transaction.status == TransactionStatus.PUBLIC_CONFIRMED
        ).count()

        return {
            'total_blocks': total_blocks,
            'miner_blocks': miner_blocks,
            'total_transactions': total_txs,
            'miner_idx': self.miner_idx
        }


# Testing
if __name__ == "__main__":
    """Test the mining service"""
    from database.connection import SessionLocal
    from core.services.transaction_service import TransactionService
    from core.crypto.idx_generator import IDXGenerator
    from core.crypto.session_id import SessionIDGenerator
    from database.models.session import Session as UserSession

    print("=== Mining Service Testing ===\n")

    db = SessionLocal()

    try:
        # Get or create miner user
        miner_idx = IDXGenerator.generate("MINER1234A", "999999")
        miner = db.query(User).filter(User.idx == miner_idx).first()

        if not miner:
            print("Creating miner user...")
            miner = User(
                idx=miner_idx,
                pan_card="MINER1234A",
                full_name="Miner Node 001",
                balance=Decimal('0.00')
            )
            db.add(miner)
            db.commit()

        print(f"Miner: {miner.full_name}")
        print(f"Initial balance: ₹{miner.balance}\n")

        # Create some test transactions
        rajesh = db.query(User).filter(User.pan_card == "RAJSH1234K").first()
        priya = db.query(User).filter(User.pan_card == "PRIYA5678M").first()

        if rajesh and priya:
            # Get/create session
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
            print("Creating test transaction...")
            tx = tx_service.create_transaction(
                sender_idx=rajesh.idx,
                receiver_idx=priya.idx,
                amount=Decimal('100.00'),
                sender_session_id=rajesh_session.session_id
            )

            print(f"Transaction created: {tx.transaction_hash[:32]}...\n")

        # Initialize mining service
        mining_service = MiningService(db, miner_idx=miner_idx)

        # Mine pending transactions
        block = mining_service.mine_pending_transactions(batch_size=10)

        if block:
            print(f"\n✅ Mining test passed!")
            print(f"Block mined: #{block.block_index}")

            # Check miner balance
            db.refresh(miner)
            print(f"Miner new balance: ₹{miner.balance}")

            # Get stats
            stats = mining_service.get_mining_stats()
            print(f"\nMining Stats:")
            print(f"  Total blocks: {stats['total_blocks']}")
            print(f"  Miner blocks: {stats['miner_blocks']}")
            print(f"  Total transactions: {stats['total_transactions']}")
        else:
            print("No pending transactions to mine")

    finally:
        db.close()
