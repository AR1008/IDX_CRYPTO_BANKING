"""
Miner Worker - Individual Mining Thread
Purpose: Continuously mine blocks for a single user

Features:
- Runs in dedicated thread per miner
- Fetches pending transactions
- Performs PoW mining
- Submits solutions to mining pool
- Tracks performance metrics

Flow:
1. Start worker thread
2. Check for pending transactions
3. Mine block (find valid nonce)
4. Submit solution to pool
5. If accepted: Winner! Get fees
6. If rejected: Too late, someone else won
7. Repeat
"""

import threading
import time
from typing import Optional
from datetime import datetime

from database.connection import SessionLocal
from database.models.transaction import Transaction, TransactionStatus
from database.models.miner import MinerStatistics
from core.consensus.pow.miner import MiningService
from config.settings import settings


class MinerWorker:
    """
    Individual miner worker thread

    Each user who wants to mine gets their own MinerWorker.
    Workers compete to find valid blocks - first to find wins.

    Attributes:
        user_idx: Miner's IDX
        pool: Reference to mining pool
        running: Whether worker is active
        thread: Worker thread
    """

    def __init__(self, user_idx: str, pool):
        """
        Initialize miner worker

        Args:
            user_idx: User's IDX
            pool: Mining pool reference
        """
        self.user_idx = user_idx
        self.pool = pool
        self.running = False
        self.thread = None
        self.hash_attempts = 0
        self.start_time = None

    def start(self):
        """Start mining worker thread"""
        if self.running:
            return

        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._mining_loop, daemon=True)
        self.thread.start()

        print(f"⛏️  Miner worker started: {self.user_idx[:16]}...")

    def stop(self):
        """Stop mining worker"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

        # Update statistics
        self._update_final_stats()

        print(f"⏹️  Miner worker stopped: {self.user_idx[:16]}...")

    def _mining_loop(self):
        """
        Main mining loop

        Continuously:
        1. Check for pending transactions
        2. Try to mine a block
        3. Submit if successful
        4. Repeat
        """
        timeout = getattr(settings, 'MINING_TIMEOUT_SECONDS', 300)

        while self.running:
            try:
                # Mine one block
                success = self._mine_one_block(timeout=timeout)

                if success:
                    # Successfully mined and submitted
                    pass
                else:
                    # No pending transactions or mining failed
                    # Wait a bit before trying again
                    time.sleep(5)

            except Exception as e:
                print(f"❌ Mining error ({self.user_idx[:16]}...): {e}")
                time.sleep(10)

    def _mine_one_block(self, timeout: int = 300) -> bool:
        """
        Attempt to mine one block

        Args:
            timeout: Maximum seconds to spend mining

        Returns:
            True if block mined and submitted, False otherwise
        """
        db = SessionLocal()

        try:
            # Check if there are pending transactions
            pending_count = db.query(Transaction).filter(
                Transaction.status == TransactionStatus.PENDING
            ).count()

            if pending_count == 0:
                return False  # Nothing to mine

            # Create mining service
            miner = MiningService(db, self.user_idx)

            # Track start time for this attempt
            attempt_start = time.time()

            # Mine block (this is the computationally expensive part)
            block = miner.mine_pending_transactions(batch_size=10)

            if not block:
                return False  # Mining failed or no transactions

            # Calculate mining time
            mining_time = time.time() - attempt_start

            # Submit solution to pool
            accepted = self.pool.submit_solution(self.user_idx, block)

            if accepted:
                # Winner! Update statistics
                self._update_stats_after_win(mining_time)
                print(f"🎉 {self.user_idx[:16]}... WON! Mined block #{block.block_index} in {mining_time:.2f}s")
                return True
            else:
                # Too late, someone else won
                self.pool.report_late_solution(self.user_idx)
                print(f"⏰ {self.user_idx[:16]}... lost race (took {mining_time:.2f}s)")
                return False

        finally:
            db.close()

    def _update_stats_after_win(self, mining_time: float):
        """
        Update miner statistics after winning a block

        Args:
            mining_time: Time taken to mine this block (seconds)
        """
        db = SessionLocal()

        try:
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == self.user_idx
            ).first()

            if not miner_stats:
                return

            # Update average mining time
            if miner_stats.avg_mining_time_seconds is None:
                miner_stats.avg_mining_time_seconds = mining_time
            else:
                # Running average
                total_blocks = miner_stats.total_blocks_mined
                current_avg = miner_stats.avg_mining_time_seconds
                new_avg = (current_avg * total_blocks + mining_time) / (total_blocks + 1)
                miner_stats.avg_mining_time_seconds = new_avg

            db.commit()

        finally:
            db.close()

    def _update_final_stats(self):
        """Update statistics when miner stops"""
        if not self.start_time:
            return

        db = SessionLocal()

        try:
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == self.user_idx
            ).first()

            if not miner_stats:
                return

            # Calculate total mining time
            total_time = time.time() - self.start_time

            # Update total hash attempts (approximate)
            miner_stats.total_hash_attempts += self.hash_attempts

            # Calculate hash rate if we have data
            if total_time > 0 and self.hash_attempts > 0:
                hash_rate = self.hash_attempts / total_time
                miner_stats.hash_rate_per_second = hash_rate

            db.commit()

        finally:
            db.close()


# For testing
if __name__ == "__main__":
    print("=== Miner Worker Test ===\n")

    # Create a mock pool
    class MockPool:
        def submit_solution(self, miner_idx, block):
            print(f"📥 Solution submitted by {miner_idx[:16]}...")
            return True  # Accept

        def report_late_solution(self, miner_idx):
            print(f"⏰ Late solution from {miner_idx[:16]}...")

    pool = MockPool()

    # Create worker
    worker = MinerWorker("IDX_TEST_MINER", pool)
    worker.start()

    # Let it run for a bit
    time.sleep(10)

    # Stop worker
    worker.stop()

    print("\n✅ Miner worker test complete")
