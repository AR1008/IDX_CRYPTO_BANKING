# [DOC] Mining Worker — the primary background daemon that polls for approved batches and mines them.
# [DOC] This is the active mining implementation used in production (started as Terminal 2).
# [DOC] It also emits WebSocket events so connected clients receive real-time block/tx notifications.
# [DOC] Compare with core/mining/miner_worker.py which is the per-user competitive mining thread.

"""
Mining Worker - With Event Emission
"""

import time
import threading

# [DOC] SessionLocal creates a fresh DB connection for each mining cycle.
from database.connection import SessionLocal
# [DOC] MiningService: does the actual PoW hash search and writes the block to blocks_public.
from core.consensus.pow.miner import MiningService
# [DOC] BankValidator: runs consortium consensus and writes the block to blocks_private.
from core.consensus.pos.validator import BankValidator
# [DOC] EventManager: in-process pub/sub — emit() triggers all registered subscribers (e.g., WebSocketManager).
from core.events.event_manager import EventManager


class MiningWorker:
    """Background mining worker"""

    def __init__(self, miner_idx: str, interval: int = 10):
        # [DOC] miner_idx identifies whose balance gets the 0.5% PoW fee for each block mined.
        self.miner_idx = miner_idx
        # [DOC] interval: seconds to sleep between mining attempts (default 10 seconds).
        self.interval = interval
        # [DOC] running: loop-control flag; set to False to gracefully stop the worker.
        self.running = False
        # [DOC] thread: reference to the daemon thread so we can join() it on stop().
        self.thread = None

    def start(self):
        """Start worker"""
        if self.running:
            return

        self.running = True
        # [DOC] daemon=True: Python exits even if this thread is still running.
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"✅ Mining worker started (every {self.interval}s)")

    def stop(self):
        """Stop worker"""
        self.running = False
        if self.thread:
            # [DOC] join() blocks until _loop exits after the current sleep.
            self.thread.join()

    def _loop(self):
        """Main loop"""
        while self.running:
            try:
                self._mine()
            except Exception as e:
                # [DOC] Catch all exceptions so a single bad block doesn't kill the worker.
                print(f"❌ Mining error: {str(e)}")

            # [DOC] Sleep before trying again — prevents busy-looping when there's nothing to mine.
            time.sleep(self.interval)

    def _mine(self):
        """Mine and validate"""
        # [DOC] Open a fresh DB session per mining attempt — avoids stale cached state.
        db = SessionLocal()

        try:
            # [DOC] Instantiate both services with the same session so they share a DB transaction.
            miner = MiningService(db, self.miner_idx)
            validator = BankValidator(db)

            # [DOC] mine_pending_transactions() picks up to 10 PENDING txs, runs PoW, writes the block.
            # [DOC] Returns None if there are no pending transactions to mine.
            block = miner.mine_pending_transactions(batch_size=10)

            if block:
                print(f"⛏️  Mined block #{block.block_index}")

                # [DOC] Emit 'block_mined' to notify all WebSocket clients of the new block.
                EventManager.emit('block_mined', {
                    'block_index': block.block_index,
                    'transactions_count': len(block.transactions)
                })

                # [DOC] Immediately run bank validation on the block we just mined.
                # [DOC] This creates the private block, distributes bank fees, and marks txs COMPLETED.
                private_block = validator.validate_and_finalize_block(block.block_index)

                if private_block:
                    print(f"✅ Validated block #{block.block_index}")

                    # [DOC] Emit 'consensus' event so clients know the block is fully finalised.
                    EventManager.emit('consensus', {
                        'block_index': block.block_index,
                        'votes': private_block.consensus_votes
                    })

                    # [DOC] Query all transactions that were just completed in this block.
                    from database.models.transaction import Transaction, TransactionStatus
                    txs = db.query(Transaction).filter(
                        Transaction.private_block_index == block.block_index,
                        Transaction.status == TransactionStatus.COMPLETED
                    ).all()

                    # [DOC] Emit a 'transaction_completed' event for each tx so sender/receiver get notified.
                    for tx in txs:
                        EventManager.emit('transaction_completed', {
                            'tx_hash': tx.transaction_hash,
                            'sender_idx': tx.sender_idx,
                            'receiver_idx': tx.receiver_idx,
                            'amount': tx.amount
                        })

        finally:
            # [DOC] Always close the DB session whether mining succeeded or failed.
            db.close()


# [DOC] Module-level singleton — only one mining worker should run per process.
_worker = None


def start_mining_worker(miner_idx: str, interval: int = 10):
    """Start global worker"""
    global _worker

    # [DOC] Guard: return the existing worker if it's already running.
    if _worker and _worker.running:
        return _worker

    _worker = MiningWorker(miner_idx, interval)
    _worker.start()
    return _worker


def stop_mining_worker():
    """Stop global worker"""
    global _worker
    if _worker:
        _worker.stop()
        _worker = None
