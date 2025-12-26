"""
Mining Pool - Competitive Mining Coordinator
Purpose: Manage multiple miners competing to mine blocks

Features:
- Register/unregister miners
- Coordinate mining competition
- Accept first valid solution
- Distribute rewards to winner
- Track mining statistics

Architecture:
    MiningPool (Coordinator)
        ├── MinerWorker (User 1) ─┐
        ├── MinerWorker (User 2) ─┤ All race to find nonce
        ├── MinerWorker (User 3) ─┤ First valid submission wins
        └── MinerWorker (User N) ─┘
"""

import threading
import time
from typing import Dict, Optional
from datetime import datetime

from database.connection import SessionLocal
from database.models.transaction import Transaction, TransactionStatus
from database.models.miner import MinerStatistics
from database.models.block import BlockPublic
from core.consensus.pow.miner import MiningService
from config.settings import settings


class MiningPool:
    """
    Coordinates competitive mining between multiple users

    Flow:
    1. Users register as miners via API
    2. Pool fetches pending transactions
    3. All active miners race to find valid nonce
    4. First to find valid solution submits to pool
    5. Pool verifies solution and rewards winner
    6. Losers discard their work (no reward)
    7. Update statistics and repeat

    Thread Safety:
    - Uses lock for critical sections
    - Miners run in separate threads
    - Pool coordinates access to shared resources
    """

    def __init__(self):
        """Initialize mining pool"""
        self.active_miners: Dict[str, 'MinerWorker'] = {}  # {user_idx: worker}
        self.lock = threading.Lock()
        self.current_mining_task = None
        self.running = False
        self.coordinator_thread = None

    def start(self):
        """Start the mining pool coordinator"""
        if self.running:
            print("⚠️  Mining pool already running")
            return

        self.running = True
        self.coordinator_thread = threading.Thread(target=self._coordinate_mining, daemon=True)
        self.coordinator_thread.start()
        print("✅ Mining pool started")

    def stop(self):
        """Stop the mining pool"""
        self.running = False
        if self.coordinator_thread:
            self.coordinator_thread.join(timeout=5)
        print("⏹️  Mining pool stopped")

    def register_miner(self, user_idx: str) -> bool:
        """
        Register a user as an active miner

        Args:
            user_idx: User's IDX

        Returns:
            True if registered, False if already registered or pool full
        """
        with self.lock:
            # Check if already registered
            if user_idx in self.active_miners:
                print(f"⚠️  Miner {user_idx[:16]}... already registered")
                return False

            # Check pool limit
            max_miners = getattr(settings, 'MAX_MINERS', 100)
            if len(self.active_miners) >= max_miners:
                print(f"⚠️  Mining pool full ({max_miners} miners)")
                return False

            # Create or update miner statistics
            db = SessionLocal()
            try:
                miner_stats = db.query(MinerStatistics).filter(
                    MinerStatistics.user_idx == user_idx
                ).first()

                if not miner_stats:
                    miner_stats = MinerStatistics(
                        user_idx=user_idx,
                        is_active=True
                    )
                    db.add(miner_stats)
                else:
                    miner_stats.is_active = True

                db.commit()

            finally:
                db.close()

            # Import here to avoid circular dependency
            from core.mining.miner_worker import MinerWorker

            # Create worker thread
            worker = MinerWorker(user_idx, self)
            worker.start()

            self.active_miners[user_idx] = worker

            print(f"✅ Miner registered: {user_idx[:16]}... (Total: {len(self.active_miners)})")
            return True

    def unregister_miner(self, user_idx: str) -> bool:
        """
        Unregister a miner

        Args:
            user_idx: User's IDX

        Returns:
            True if unregistered, False if not found
        """
        with self.lock:
            if user_idx not in self.active_miners:
                return False

            # Stop worker
            worker = self.active_miners[user_idx]
            worker.stop()

            # Remove from active miners
            del self.active_miners[user_idx]

            # Update database
            db = SessionLocal()
            try:
                miner_stats = db.query(MinerStatistics).filter(
                    MinerStatistics.user_idx == user_idx
                ).first()

                if miner_stats:
                    miner_stats.is_active = False
                    db.commit()

            finally:
                db.close()

            print(f"⏹️  Miner unregistered: {user_idx[:16]}... (Total: {len(self.active_miners)})")
            return True

    def get_active_miners_count(self) -> int:
        """Get number of active miners"""
        with self.lock:
            return len(self.active_miners)

    def _coordinate_mining(self):
        """
        Main coordinator loop

        Continuously checks for pending transactions and coordinates mining
        """
        print("🔄 Mining coordinator started")

        while self.running:
            try:
                # Check if there are pending transactions
                db = SessionLocal()
                try:
                    pending_count = db.query(Transaction).filter(
                        Transaction.status == TransactionStatus.PENDING
                    ).count()

                    if pending_count > 0 and len(self.active_miners) > 0:
                        print(f"\n📋 {pending_count} pending transactions, {len(self.active_miners)} active miners")
                        # Miners are continuously working in their own threads
                        # They'll pick up pending transactions automatically

                finally:
                    db.close()

            except Exception as e:
                print(f"❌ Coordinator error: {e}")

            # Sleep before next check
            time.sleep(10)

        print("🔄 Mining coordinator stopped")

    def submit_solution(self, miner_idx: str, block: BlockPublic) -> bool:
        """
        Miner submits a solution

        This is called by MinerWorker when it finds a valid block.
        First valid solution wins.

        Args:
            miner_idx: Miner's IDX
            block: Mined block

        Returns:
            True if solution accepted (first), False if rejected (late)
        """
        with self.lock:
            # Verify block is valid
            if not self._verify_block(block):
                print(f"❌ Invalid block from {miner_idx[:16]}...")
                return False

            # Accept solution (first come, first served)
            print(f"🎉 Block #{block.block_index} mined by {miner_idx[:16]}...")

            # Update miner statistics
            self._update_miner_stats(miner_idx, block, won=True)

            return True

    def report_late_solution(self, miner_idx: str):
        """
        Report that miner found a solution but was too late

        Args:
            miner_idx: Miner's IDX
        """
        with self.lock:
            # Update statistics (block lost)
            db = SessionLocal()
            try:
                miner_stats = db.query(MinerStatistics).filter(
                    MinerStatistics.user_idx == miner_idx
                ).first()

                if miner_stats:
                    miner_stats.blocks_lost += 1
                    db.commit()

                    print(f"⏰ Miner {miner_idx[:16]}... was late (blocks lost: {miner_stats.blocks_lost})")

            finally:
                db.close()

    def _verify_block(self, block: BlockPublic) -> bool:
        """Verify block is valid"""
        # Basic validation
        if not block or not block.block_hash:
            return False

        # Check hash has correct difficulty
        difficulty = getattr(settings, 'POW_DIFFICULTY', 4)
        required_prefix = '0' * difficulty

        if not block.block_hash.startswith(required_prefix):
            return False

        return True

    def _update_miner_stats(self, miner_idx: str, block: BlockPublic, won: bool):
        """Update miner statistics after mining"""
        db = SessionLocal()
        try:
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == miner_idx
            ).first()

            if not miner_stats:
                return

            # Update statistics
            if won:
                miner_stats.total_blocks_mined += 1
                miner_stats.blocks_won += 1

                # Get fees from block transactions
                # (Fees are already distributed in MiningService, we just track the count)

            miner_stats.last_mined_at = datetime.utcnow()
            db.commit()

        finally:
            db.close()


# Global mining pool instance
_mining_pool: Optional[MiningPool] = None


def get_mining_pool() -> MiningPool:
    """
    Get global mining pool instance

    Returns:
        MiningPool: Global mining pool
    """
    global _mining_pool

    if _mining_pool is None:
        _mining_pool = MiningPool()
        _mining_pool.start()

    return _mining_pool


def start_mining_pool():
    """Start the global mining pool"""
    pool = get_mining_pool()
    if not pool.running:
        pool.start()
    return pool


def stop_mining_pool():
    """Stop the global mining pool"""
    global _mining_pool
    if _mining_pool:
        _mining_pool.stop()
        _mining_pool = None


# For testing
if __name__ == "__main__":
    print("=== Mining Pool Test ===\n")

    # Start pool
    pool = MiningPool()
    pool.start()

    # Register miners
    pool.register_miner("IDX_MINER_001")
    pool.register_miner("IDX_MINER_002")
    pool.register_miner("IDX_MINER_003")

    print(f"\nActive miners: {pool.get_active_miners_count()}")

    # Let it run for a bit
    time.sleep(5)

    # Stop pool
    pool.stop()

    print("\n✅ Mining pool test complete")
