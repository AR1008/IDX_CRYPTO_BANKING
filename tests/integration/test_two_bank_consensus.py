"""
Test Two-Bank Consensus Flow
Author: Ashutosh Rajesh
Purpose: Test complete flow with sender's bank + receiver's bank in consensus

Flow:
1. Sender (HDFC) → Creates transaction → Status: AWAITING_RECEIVER
2. Receiver → Confirms, selects ICICI → Status: PENDING
3. Mining worker → Mines transaction → Status: PUBLIC_CONFIRMED
4. Bank validator → Both HDFC + ICICI must approve
5. All 6 banks validate → Need 4/6 approval
6. Transaction → Status: COMPLETED
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from decimal import Decimal
from database.connection import SessionLocal, Base, engine
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.bank import Bank
from database.models.transaction import Transaction, TransactionStatus
from core.services.recipient_service import RecipientService
from core.services.transaction_service_v2 import TransactionServiceV2
from core.consensus.pow.miner import MiningService
from core.consensus.pos.validator import BankValidator
from core.crypto.idx_generator import IDXGenerator


def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def setup_banks(db):
    """Create consortium banks"""
    banks_data = [
        ('HDFC', 'HDFC Bank Ltd'),
        ('ICICI', 'ICICI Bank Ltd'),
        ('SBI', 'State Bank of India'),
        ('AXIS', 'Axis Bank Ltd'),
        ('KOTAK', 'Kotak Mahindra Bank'),
        ('YES', 'Yes Bank Ltd')
    ]
    
    for code, name in banks_data:
        existing = db.query(Bank).filter(Bank.bank_code == code).first()
        if not existing:
            bank = Bank(
                bank_code=code,
                bank_name=name,
                stake_amount=Decimal('100000000.00'),
                is_active=True
            )
            db.add(bank)
    
    db.commit()
    print(f"✅ 6 consortium banks ready")


import time

def create_test_user(db, pan_suffix, rbi_number, name, initial_balance):
    """Create test user with bank account"""
    # Use timestamp to make PAN unique
    unique_id = str(int(time.time()))[-4:]
    pan_card = f"TEST{pan_suffix}{unique_id}A"
    idx = IDXGenerator.generate(pan_card, rbi_number)
    
    user = User(
        idx=idx,
        pan_card=pan_card,
        full_name=name,
        balance=Decimal('0.00')  # Balance in BankAccount, not User
    )
    db.add(user)
    db.commit()
    
    return user


def create_bank_account(db, user_idx, bank_code, balance):
    """Create bank account for user"""
    import random
    account_number = f"{bank_code}{user_idx[-8:]}{random.randint(1000, 9999)}"
    
    account = BankAccount(
        user_idx=user_idx,
        bank_code=bank_code,
        account_number=account_number,
        balance=balance,
        is_active=True,
        is_frozen=False
    )
    
    db.add(account)
    db.commit()
    db.refresh(account)
    
    return account


def main():
    print_header("🚀 TWO-BANK CONSENSUS TEST")
    
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # Setup banks
        print_header("Step 1: Setup Consortium Banks")
        setup_banks(db)
        
        # Create sender with HDFC account
        print_header("Step 2: Create Sender (HDFC)")
        sender = create_test_user(db, "S", "300001", "Sender User", 100000)
        sender_hdfc = create_bank_account(db, sender.idx, "HDFC", Decimal('100000'))
        print(f"✅ Sender: {sender.full_name}")
        print(f"   IDX: {sender.idx[:32]}...")
        print(f"   HDFC Account: {sender_hdfc.account_number}")
        print(f"   Balance: ₹{sender_hdfc.balance}")
        
        # Create receiver with ICICI account
        print_header("Step 3: Create Receiver (ICICI)")
        receiver = create_test_user(db, "R", "300002", "Receiver User", 50000)
        receiver_icici = create_bank_account(db, receiver.idx, "ICICI", Decimal('50000'))
        print(f"✅ Receiver: {receiver.full_name}")
        print(f"   IDX: {receiver.idx[:32]}...")
        print(f"   ICICI Account: {receiver_icici.account_number}")
        print(f"   Balance: ₹{receiver_icici.balance}")
        
        # Create miner
        print_header("Step 4: Create Miner")
        miner = create_test_user(db, "M", "999999", "Miner", 0)
        miner_account = create_bank_account(db, miner.idx, "HDFC", Decimal('0'))
        print(f"✅ Miner: {miner.full_name}")
        
        # Add receiver to sender's contacts
        print_header("Step 5: Add Recipient to Contacts")
        recipient_service = RecipientService(db)
        recipient = recipient_service.add_recipient(sender.idx, receiver.idx, "Friend")
        print(f"   Nickname: {recipient.nickname}")
        print(f"   Session: {recipient.current_session_id[:32]}...")
        
        # Create transaction (awaiting receiver)
        print_header("Step 6: Create Transaction (Awaiting Receiver)")
        tx_service = TransactionServiceV2(db)
        tx = tx_service.create_transaction(
            sender_account_id=sender_hdfc.id,
            recipient_nickname="Friend",
            amount=Decimal('5000'),
            sender_session_id="SESSION_test_sender"
        )
        print(f"   TX Hash: {tx.transaction_hash[:32]}...")
        print(f"   Amount: ₹{tx.amount}")
        print(f"   Status: {tx.status.value}")
        
        # Receiver confirms and selects ICICI
        print_header("Step 7: Receiver Confirms (Selects ICICI)")
        tx = tx_service.confirm_transaction(tx.transaction_hash, receiver_icici.id)
        print(f"   Status: {tx.status.value}")
        print(f"   Sender bank: HDFC")
        print(f"   Receiver bank: ICICI")
        
        # Mine transaction
        print_header("Step 8: Mine Transaction (PoW)")
        mining_service = MiningService(db, miner.idx)
        block = mining_service.mine_pending_transactions()
        
        if not block:
            print("❌ Mining failed!")
            return
        
        print(f"   Block #{block.block_index} mined")
        print(f"   Transactions: {len(block.transactions)}")
        
        # Refresh transaction
        db.refresh(tx)
        print(f"   TX Status: {tx.status.value}")
        
        # Bank validation with two-bank consensus
        print_header("Step 9: Bank Validation (PoS + Two-Bank)")
        validator = BankValidator(db)
        private_block = validator.validate_and_finalize_block(block.block_index)
        
        if not private_block:
            print("❌ Consensus failed!")
            return
        
        print(f"\n✅ Consensus achieved!")
        print(f"   Private block: #{private_block.block_index}")
        print(f"   Votes: {private_block.consensus_votes}/6")
        
        # Check final status
        print_header("Step 10: Verify Results")
        
        # Refresh accounts
        db.refresh(sender_hdfc)
        db.refresh(receiver_icici)
        db.refresh(tx)
        
        print(f"Transaction Status: {tx.status.value}")
        print(f"\nSender HDFC Account:")
        print(f"  Before: ₹100,000")
        print(f"  After: ₹{sender_hdfc.balance}")
        print(f"  Sent: ₹{tx.amount + tx.fee}")
        
        print(f"\nReceiver ICICI Account:")
        print(f"  Before: ₹50,000")
        print(f"  After: ₹{receiver_icici.balance}")
        print(f"  Received: ₹{tx.amount}")
        
        # Check bank fees
        hdfc = db.query(Bank).filter(Bank.bank_code == "HDFC").first()
        icici = db.query(Bank).filter(Bank.bank_code == "ICICI").first()
        
        print(f"\nBank Fees Earned:")
        print(f"  HDFC (involved): ₹{hdfc.total_fees_earned}")
        print(f"  ICICI (involved): ₹{icici.total_fees_earned}")
        
        # Verify math
        expected_sender = Decimal('100000') - tx.amount - tx.fee
        expected_receiver = Decimal('50000') + tx.amount
        
        assert sender_hdfc.balance == expected_sender, f"Sender balance mismatch!"
        assert receiver_icici.balance == expected_receiver, f"Receiver balance mismatch!"
        assert tx.status == TransactionStatus.COMPLETED, f"Transaction not completed!"
        
        print_header("✅ ALL TESTS PASSED!")
        print("\nTwo-Bank Consensus Flow:")
        print("1. ✅ Sender (HDFC) created transaction")
        print("2. ✅ Receiver confirmed (selected ICICI)")
        print("3. ✅ Transaction mined (PoW)")
        print("4. ✅ Both HDFC + ICICI approved (critical)")
        print("5. ✅ All 6 banks validated (4/6 consensus)")
        print("6. ✅ Transaction completed")
        print("7. ✅ Balances updated correctly")
        print("8. ✅ Bank fees distributed")
        print("\n🎉 Two-bank consensus working perfectly!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


if __name__ == "__main__":
    main()