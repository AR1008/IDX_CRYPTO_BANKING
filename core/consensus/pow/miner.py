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

from decimal import Decimal
from datetime import datetime
import time
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models.transaction import Transaction, TransactionStatus
from database.models.block import BlockPublic
from database.models.user import User
from core.blockchain.public_chain.block import Block
from core.blockchain.public_chain.chain import Blockchain
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
        self.db = db
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
        
        # Step 1: Get pending transactions
        pending_txs = self.db.query(Transaction).filter(
            Transaction.status == TransactionStatus.PENDING
        ).limit(batch_size).all()
        
        if not pending_txs:
            return None
        
        print(f"\n⛏️  Mining {len(pending_txs)} transactions...")
        
        # Step 2: Update to MINING status
        tx_hashes = []
        for tx in pending_txs:
            tx.status = TransactionStatus.MINING
            tx_hashes.append(tx.transaction_hash)
        
        self.db.commit()
        
        # Step 3: Get last block from database
        last_block = self.db.query(BlockPublic).order_by(
            BlockPublic.block_index.desc()
        ).first()
        
        if last_block:
            next_index = last_block.block_index + 1
            previous_hash = last_block.block_hash
        else:
            # No blocks yet - create genesis first
            print("No genesis block found, creating one...")
            genesis = self._create_genesis_block()
            next_index = 1
            previous_hash = genesis.block_hash
        
        # Step 4: Create new block
        new_block = Block(
            index=next_index,
            transactions=tx_hashes,
            previous_hash=previous_hash
        )
        
        # Step 5: Mine the block (find valid nonce)
        print(f"Mining block #{next_index}...")
        start_time = time.time()
        
        new_block.mine_block(difficulty=settings.POW_DIFFICULTY)
        
        mining_time = time.time() - start_time
        
        print(f"✅ Block #{next_index} mined!")
        print(f"   Nonce: {new_block.nonce:,}")
        print(f"   Hash: {new_block.hash[:40]}...")
        print(f"   Time: {mining_time:.2f} seconds")
        print(f"   Transactions: {len(tx_hashes)}")
        
        # Step 6: Store in database
        block_public = BlockPublic(
            block_index=new_block.index,
            block_hash=new_block.hash,
            previous_hash=new_block.previous_hash,
            transactions=new_block.transactions,
            nonce=new_block.nonce,
            difficulty=settings.POW_DIFFICULTY,
            timestamp=new_block.timestamp,
            mined_by=self.miner_idx
        )
        
        self.db.add(block_public)
        
        # Step 7: Update transactions to PUBLIC_CONFIRMED
        for tx in pending_txs:
            tx.status = TransactionStatus.PUBLIC_CONFIRMED
            tx.public_block_index = new_block.index
        
        self.db.commit()
        
        # Step 8: Collect miner fees
        total_fees = self._collect_miner_fees(pending_txs)
        
        print(f"💰 Miner earned: ₹{total_fees}")
        
        return block_public
    
    def _create_genesis_block(self) -> BlockPublic:
        """
        Create genesis block (block #0)
        
        Returns:
            BlockPublic: Genesis block
        """
        genesis = Block(index=0, transactions=[], previous_hash="0")
        genesis.mine_block(difficulty=settings.POW_DIFFICULTY)
        
        genesis_db = BlockPublic(
            block_index=0,
            block_hash=genesis.hash,
            previous_hash="0",
            transactions=[],
            nonce=genesis.nonce,
            difficulty=settings.POW_DIFFICULTY,
            timestamp=genesis.timestamp,
            mined_by=None  # Genesis not mined by anyone
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
        miner = self.db.query(User).filter(User.idx == self.miner_idx).first()
        
        if not miner:
            print(f"⚠️  Miner {self.miner_idx} not found, fees not distributed")
            return Decimal('0.00')
        
        total_fees = Decimal('0.00')
        
        for tx in transactions:
            total_fees += tx.miner_fee
        
        # Add fees to miner's balance
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
        total_blocks = self.db.query(BlockPublic).count()
        
        miner_blocks = self.db.query(BlockPublic).filter(
            BlockPublic.mined_by == self.miner_idx
        ).count()
        
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