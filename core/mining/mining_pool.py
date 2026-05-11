# [DOC] MiningPool — the coordinator that manages all user mining threads and handles the first-submission race.
# [DOC] Users register as miners via POST /api/mining/start; the pool gives each user a MinerWorker thread.
# [DOC] All workers race to mine the next block; the pool accepts only the first valid submission.
# [DOC] A threading.Lock guards all shared state (active_miners dict) for thread safety.

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
# [DOC] MiningService does the PoW work; MiningPool orchestrates who can submit solutions.
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
        # [DOC] active_miners maps IDX → MinerWorker object for every currently-mining user.
        self.active_miners: Dict[str, 'MinerWorker'] = {}
        # [DOC] lock protects active_miners from concurrent modification by multiple API threads.
        self.lock = threading.Lock()
        # [DOC] current_mining_task could be used to track what block height is being mined (reserved for future use).
        self.current_mining_task = None
        # [DOC] running controls the coordinator loop.
        self.running = False
        self.coordinator_thread = None

    def start(self):
        """Start the mining pool coordinator"""
        if self.running:
            print("⚠️  Mining pool already running")
            return

        self.running = True
        # [DOC] Coordinator thread: periodically logs pending transaction counts; miners run independently.
        self.coordinator_thread = threading.Thread(target=self._coordinate_mining, daemon=True)
        self.coordinator_thread.start()
        print("✅ Mining pool started")

    def stop(self):
        """Stop the mining pool"""
        self.running = False
        if self.coordinator_thread:
            # [DOC] Give the coordinator thread 5 seconds to finish its current sleep cycle.
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
        # [DOC] Acquire the lock before reading or writing active_miners to prevent race conditions.
        with self.lock:
            # [DOC] Idempotency check: reject duplicate registrations.
            if user_idx in self.active_miners:
                print(f"⚠️  Miner {user_idx[:16]}... already registered")
                return False

            # [DOC] Pool capacity check — prevents unbounded thread creation.
            max_miners = getattr(settings, 'MAX_MINERS', 100)
            if len(self.active_miners) >= max_miners:
                print(f"⚠️  Mining pool full ({max_miners} miners)")
                return False

            # [DOC] Upsert a MinerStatistics row so the miner appears in the leaderboard immediately.
            db = SessionLocal()
            try:
                miner_stats = db.query(MinerStatistics).filter(
                    MinerStatistics.user_idx == user_idx
                ).first()

                if not miner_stats:
                    # [DOC] First time mining: create a fresh stats row.
                    miner_stats = MinerStatistics(
                        user_idx=user_idx,
                        is_active=True
                    )
                    db.add(miner_stats)
                else:
                    # [DOC] Returning miner: flip is_active back to True.
                    miner_stats.is_active = True

                db.commit()

            finally:
                db.close()

            # [DOC] Import inside the method to break the circular import:
            # [DOC] mining_pool imports MinerWorker; miner_worker imports MiningPool via pool reference.
            from core.mining.miner_worker import MinerWorker

            # [DOC] Create and immediately start the worker thread for this user.
            worker = MinerWorker(user_idx, self)
            worker.start()

            # [DOC] Register the worker in the dict — now the pool knows this user is mining.
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

            # [DOC] Stop the worker thread before removing it from the dict.
            worker = self.active_miners[user_idx]
            worker.stop()

            del self.active_miners[user_idx]

            # [DOC] Update the DB so the leaderboard shows this miner as inactive.
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
        # [DOC] Acquire the lock because len() on the dict is not atomic in all Python versions.
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
                # [DOC] Open a short-lived DB session just for the count check.
                db = SessionLocal()
                try:
                    pending_count = db.query(Transaction).filter(
                        Transaction.status == TransactionStatus.PENDING
                    ).count()

                    if pending_count > 0 and len(self.active_miners) > 0:
                        # [DOC] Log only — MinerWorker threads pick up pending txs independently.
                        print(f"\n📋 {pending_count} pending transactions, {len(self.active_miners)} active miners")

                finally:
                    db.close()

            except Exception as e:
                print(f"❌ Coordinator error: {e}")

            # [DOC] Sleep 10 seconds before the next status check.
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
        # [DOC] Lock ensures only one submission wins even if two workers finish simultaneously.
        with self.lock:
            # [DOC] Verify the block's hash actually meets the PoW difficulty requirement.
            if not self._verify_block(block):
                print(f"❌ Invalid block from {miner_idx[:16]}...")
                return False

            # [DOC] First valid submission wins — no further checking needed here.
            print(f"🎉 Block #{block.block_index} mined by {miner_idx[:16]}...")

            # [DOC] Update this miner's statistics (blocks_won, last_mined_at).
            self._update_miner_stats(miner_idx, block, won=True)

            return True

    def report_late_solution(self, miner_idx: str):
        """
        Report that miner found a solution but was too late

        Args:
            miner_idx: Miner's IDX
        """
        with self.lock:
            db = SessionLocal()
            try:
                miner_stats = db.query(MinerStatistics).filter(
                    MinerStatistics.user_idx == miner_idx
                ).first()

                if miner_stats:
                    # [DOC] Increment blocks_lost counter — shown on the leaderboard as a performance metric.
                    miner_stats.blocks_lost += 1
                    db.commit()

                    print(f"⏰ Miner {miner_idx[:16]}... was late (blocks lost: {miner_stats.blocks_lost})")

            finally:
                db.close()

    def _verify_block(self, block: BlockPublic) -> bool:
        """Verify block is valid"""
        # [DOC] Basic null check — a None block or missing hash is an obvious invalid submission.
        if not block or not block.block_hash:
            return False

        # [DOC] Check that the hash starts with the required number of zero hex digits.
        # [DOC] e.g. difficulty=4 means the hash must start with "0000".
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

            if won:
                # [DOC] Increment both total_blocks_mined and blocks_won (won ≤ total always).
                miner_stats.total_blocks_mined += 1
                miner_stats.blocks_won += 1
                # [DOC] Actual fee credit happens in MiningService._collect_miner_fees() — we just count here.

            # [DOC] Record when this miner last successfully mined a block (for leaderboard display).
            miner_stats.last_mined_at = datetime.utcnow()
            db.commit()

        finally:
            db.close()


# [DOC] Module-level singleton — one pool per process, shared by all route handlers.
_mining_pool: Optional[MiningPool] = None


def get_mining_pool() -> MiningPool:
    """
    Get global mining pool instance

    Returns:
        MiningPool: Global mining pool
    """
    global _mining_pool

    # [DOC] Lazy initialisation: create and start the pool on first access.
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
