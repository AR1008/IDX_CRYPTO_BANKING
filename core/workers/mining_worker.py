"""
Mining Worker - With Event Emission
"""

import time
import threading

from database.connection import SessionLocal
from core.consensus.pow.miner import MiningService
from core.consensus.pos.validator import BankValidator
from core.events.event_manager import EventManager


class MiningWorker:
    """Background mining worker"""
    
    def __init__(self, miner_idx: str, interval: int = 10):
        self.miner_idx = miner_idx
        self.interval = interval
        self.running = False
        self.thread = None
    
    def start(self):
        """Start worker"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"✅ Mining worker started (every {self.interval}s)")
    
    def stop(self):
        """Stop worker"""
        self.running = False
        if self.thread:
            self.thread.join()
    
    def _loop(self):
        """Main loop"""
        while self.running:
            try:
                self._mine()
            except Exception as e:
                print(f"❌ Mining error: {str(e)}")
            
            time.sleep(self.interval)
    
    def _mine(self):
        """Mine and validate"""
        db = SessionLocal()
        
        try:
            miner = MiningService(db, self.miner_idx)
            validator = BankValidator(db)
            
            # Mine
            block = miner.mine_pending_transactions(batch_size=10)
            
            if block:
                print(f"⛏️  Mined block #{block.block_index}")
                
                # Emit event
                EventManager.emit('block_mined', {
                    'block_index': block.block_index,
                    'transactions_count': len(block.transactions)
                })
                
                # Validate
                private_block = validator.validate_and_finalize_block(block.block_index)
                
                if private_block:
                    print(f"✅ Validated block #{block.block_index}")
                    
                    # Emit consensus event
                    EventManager.emit('consensus', {
                        'block_index': block.block_index,
                        'votes': private_block.consensus_votes
                    })
                    
                    # Emit transaction completed events
                    from database.models.transaction import Transaction, TransactionStatus
                    txs = db.query(Transaction).filter(
                        Transaction.private_block_index == block.block_index,
                        Transaction.status == TransactionStatus.COMPLETED
                    ).all()
                    
                    for tx in txs:
                        EventManager.emit('transaction_completed', {
                            'tx_hash': tx.transaction_hash,
                            'sender_idx': tx.sender_idx,
                            'receiver_idx': tx.receiver_idx,
                            'amount': tx.amount
                        })
            
        finally:
            db.close()


# Singleton
_worker = None


def start_mining_worker(miner_idx: str, interval: int = 10):
    """Start global worker"""
    global _worker
    
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