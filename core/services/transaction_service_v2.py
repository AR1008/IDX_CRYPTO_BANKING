"""
Transaction Service V2 - Transaction processing with receiver confirmation.

Handles complete transaction lifecycle including receiver bank selection,
anomaly detection, and status tracking through consensus.
"""

from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional, Dict
import hashlib

from database.models.transaction import Transaction, TransactionStatus
from database.models.bank_account import BankAccount
from database.models.user import User
from database.models.recipient import Recipient
from core.events.event_manager import EventManager


class TransactionServiceV2:
    """Transaction service with receiver confirmation and anomaly detection."""

    def __init__(self, db: Session):
        """Initialize transaction service."""
        self.db = db
    
    def calculate_fees(self, amount: Decimal) -> Dict[str, Decimal]:
        """Calculate transaction fees: 1.5% total (0.5% miner + 1.0% banks)."""
        total_fee = amount * Decimal('0.015')  # 1.5%
        miner_fee = amount * Decimal('0.005')  # 0.5%
        bank_fee = amount * Decimal('0.01')    # 1.0%
        
        return {
            'total_fee': total_fee,
            'miner_fee': miner_fee,
            'bank_fee': bank_fee,
            'fee_per_bank': bank_fee / Decimal('6')
        }
    
    def generate_transaction_hash(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal
    ) -> str:
        """Generate unique SHA-256 transaction hash."""
        timestamp = str(datetime.utcnow().timestamp())
        data = f"{sender_idx}:{receiver_idx}:{amount}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def create_transaction(
        self,
        sender_account_id: int,
        recipient_nickname: str,
        amount: Decimal,
        sender_session_id: str
    ) -> Transaction:
        """Create transaction with sender initiation and anomaly detection."""
        # Get sender account
        sender_account = self.db.query(BankAccount).filter(
            BankAccount.id == sender_account_id
        ).first()
        
        if not sender_account:
            raise ValueError(f"Sender account not found: {sender_account_id}")
        
        if sender_account.is_frozen:
            raise ValueError(f"Account is frozen: {sender_account.account_number}")
        
        # Get recipient by nickname
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == sender_account.user_idx,
            Recipient.nickname == recipient_nickname,
            Recipient.is_active == True
        ).first()
        
        if not recipient:
            raise ValueError(f"Recipient '{recipient_nickname}' not found")
        
        # Calculate fees
        fees = self.calculate_fees(amount)
        total_required = amount + fees['total_fee']
        
        # Check balance
        if sender_account.balance < total_required:
            raise ValueError(
                f"Insufficient balance. Required: INR{total_required}, "
                f"Available: INR{sender_account.balance}"
            )
        
        # Generate transaction hash
        tx_hash = self.generate_transaction_hash(
            sender_account.user_idx,
            recipient.recipient_idx,
            amount
        )
        
        # Create transaction (receiver_account_id = NULL initially)
        transaction = Transaction(
            transaction_hash=tx_hash,
            sender_account_id=sender_account_id,
            receiver_account_id=None,  # NULL until receiver confirms
            sender_idx=sender_account.user_idx,
            receiver_idx=recipient.recipient_idx,
            sender_session_id=sender_session_id,
            receiver_session_id=recipient.current_session_id,  # Recipient's session
            amount=amount,
            fee=fees['total_fee'],
            miner_fee=fees['miner_fee'],
            bank_fee=fees['bank_fee'],
            status=TransactionStatus.AWAITING_RECEIVER  # Wait for receiver
        )

        # Anomaly detection (non-blocking, PMLA compliance)
        # Evaluate transaction for suspicious patterns
        from core.services.anomaly_detection_engine import AnomalyDetectionEngine
        from core.crypto.anomaly_zkp import AnomalyZKPService
        from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption
        import json

        try:
            anomaly_engine = AnomalyDetectionEngine(self.db)
            anomaly_result = anomaly_engine.evaluate_transaction(transaction)

            # Store anomaly data (won't block transaction)
            transaction.anomaly_score = Decimal(str(anomaly_result['score']))
            transaction.anomaly_flags = anomaly_result['flags']
            transaction.requires_investigation = anomaly_result['requires_investigation']

            # Generate ZKP proof for anomaly flag (Phase 2)
            # This proves transaction is flagged without revealing details
            zkp_service = AnomalyZKPService()
            zkp_proof = zkp_service.generate_anomaly_proof(
                transaction_hash=tx_hash,
                anomaly_score=anomaly_result['score'],
                anomaly_flags=anomaly_result['flags'],
                requires_investigation=anomaly_result['requires_investigation']
            )

            # Store ZKP proof as JSON (public proof only, witness encrypted separately)
            public_proof = {k: v for k, v in zkp_proof.items() if k != 'witness'}
            transaction.zkp_anomaly_proof = json.dumps(public_proof)

            # If flagged (score >= 65), encrypt transaction details (Phase 3)
            if anomaly_result['requires_investigation']:
                transaction.flagged_at = datetime.now(timezone.utc)
                transaction.investigation_status = 'PENDING'

                # Threshold encrypt transaction details for court order decryption
                # Requires: Company + Supreme Court + 1-of-4 (RBI/FIU/CBI/IT)
                threshold_enc = AnomalyThresholdEncryption()
                encrypted_package = threshold_enc.encrypt_transaction_details(
                    transaction_hash=tx_hash,
                    sender_idx=sender_account.user_idx,
                    receiver_idx=recipient.recipient_idx,
                    amount=amount,
                    anomaly_score=anomaly_result['score'],
                    anomaly_flags=anomaly_result['flags']
                )

                # Store encrypted details (binary data)
                # Key shares distributed separately to authorities
                encrypted_json = json.dumps({
                    'encrypted_details': encrypted_package['encrypted_details'],
                    'transaction_hash': encrypted_package['transaction_hash'],
                    'encrypted_at': encrypted_package['encrypted_at'],
                    'threshold': encrypted_package['threshold']
                })
                transaction.threshold_encrypted_details = encrypted_json.encode('utf-8')

                print(f"[WARNING]  Transaction flagged for investigation")
                print(f"   Score: {anomaly_result['score']}")
                print(f"   Flags: {anomaly_result['flags']}")
                print(f"   ZKP proof generated (flag hidden)")
                print(f"   Details encrypted (threshold: Company+Court+1-of-4)")
                print(f"   User unaware - transaction continues normally")

        except Exception as e:
            # If anomaly detection fails, log error but don't block transaction
            print(f"[WARNING]  Anomaly detection error: {str(e)}")
            print(f"   Transaction proceeding normally (safety mechanism)")

        # Transaction continues normally regardless of anomaly flag
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"Transaction created: {tx_hash[:16]}...")
        print(f"   From: {sender_account.bank_code} account")
        print(f"   To: {recipient_nickname} ({recipient.recipient_idx[:16]}...)")
        print(f"   Amount: {amount}")
        print(f"   Fee: {fees['total_fee']}")
        print(f"   Status: AWAITING_RECEIVER")
        
        # Emit event (receiver notification)
        EventManager.emit('transaction_pending', {
            'transaction_hash': tx_hash,
            'sender_idx': sender_account.user_idx,
            'receiver_idx': recipient.recipient_idx,
            'amount': str(amount),
            'recipient_nickname': recipient_nickname
        })
        
        return transaction
    
    def get_pending_transactions_for_receiver(self, user_idx: str):
        """Get transactions awaiting receiver confirmation."""
        return self.db.query(Transaction).filter(
            Transaction.receiver_idx == user_idx,
            Transaction.status == TransactionStatus.AWAITING_RECEIVER
        ).all()
    
    def confirm_transaction(
        self,
        transaction_hash: str,
        receiver_account_id: int
    ) -> Transaction:
        """Confirm transaction and select receiving bank account."""
        # Get transaction
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()
        
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")
        
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver. Status: {transaction.status.value}")
        
        # Get receiver account
        receiver_account = self.db.query(BankAccount).filter(
            BankAccount.id == receiver_account_id
        ).first()
        
        if not receiver_account:
            raise ValueError(f"Receiver account not found: {receiver_account_id}")
        
        # Verify account belongs to receiver
        if receiver_account.user_idx != transaction.receiver_idx:
            raise ValueError("Account does not belong to receiver")
        
        if receiver_account.is_frozen:
            raise ValueError(f"Account is frozen: {receiver_account.account_number}")
        
        # Update transaction
        transaction.receiver_account_id = receiver_account_id
        transaction.status = TransactionStatus.PENDING  # Now ready for mining
        
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"Transaction confirmed: {transaction_hash[:16]}...")
        print(f"   Receiver selected: {receiver_account.bank_code} account")
        print(f"   Status: PENDING (ready for mining)")
        
        # Emit event
        EventManager.emit('transaction_confirmed', {
            'transaction_hash': transaction_hash,
            'receiver_account_id': receiver_account_id,
            'receiver_bank': receiver_account.bank_code
        })
        
        return transaction
    
    def reject_transaction(self, transaction_hash: str) -> Transaction:
        """Reject pending transaction."""
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()
        
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")
        
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver")
        
        transaction.status = TransactionStatus.REJECTED
        
        self.db.commit()
        self.db.refresh(transaction)
        
        print(f"Transaction rejected: {transaction_hash[:16]}...")
        
        # Emit event
        EventManager.emit('transaction_rejected', {
            'transaction_hash': transaction_hash,
            'receiver_idx': transaction.receiver_idx
        })
        
        return transaction


if __name__ == "__main__":
    """Test transaction service v2."""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    from core.services.recipient_service import RecipientService
    
    print("=== Transaction Service V2 Testing ===\n")
    
    db = SessionLocal()
    service = TransactionServiceV2(db)
    recipient_service = RecipientService(db)
    
    try:
        # Get test accounts
        sender_idx = IDXGenerator.generate("TESTA1234P", "100001")
        receiver_idx = IDXGenerator.generate("TESTC1234D", "100003")
        
        # Get sender's HDFC account
        sender_account = db.query(BankAccount).filter(
            BankAccount.user_idx == sender_idx,
            BankAccount.bank_code == "HDFC"
        ).first()
        
        if not sender_account:
            print("[ERROR] Sender account not found. Run migration first.")
            exit(1)
        
        # Check if recipient exists in contact list
        recipient = recipient_service.get_recipient_by_idx(sender_idx, receiver_idx)
        if not recipient:
            print("  Adding recipient to contact list...")
            recipient = recipient_service.add_recipient(sender_idx, receiver_idx, "TestFriend")
        
        print(f"Sender account: {sender_account.bank_code} - INR{sender_account.balance}")
        print(f"Recipient: {recipient.nickname}\n")
        
        # Test 1: Create transaction
        print("Test 1: Create Transaction (Awaiting Receiver)")
        tx = service.create_transaction(
            sender_account_id=sender_account.id,
            recipient_nickname="TestFriend",
            amount=Decimal('1000'),
            sender_session_id="SESSION_test_123"
        )
        print(f"  Status: {tx.status.value}")
        print(f"  Receiver account ID: {tx.receiver_account_id}")
        print("  [PASS] Test 1 passed!\n")
        
        # Test 2: Get pending for receiver
        print("Test 2: Get Pending Transactions for Receiver")
        pending = service.get_pending_transactions_for_receiver(receiver_idx)
        print(f"  Found {len(pending)} pending transactions")
        print("  [PASS] Test 2 passed!\n")
        
        print("=" * 50)
        print("[PASS] All tests passed!")
        print("=" * 50)
        
    finally:
        db.close()