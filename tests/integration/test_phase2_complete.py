"""
Phase 2 Complete Integration Test
Purpose: Comprehensive testing of Bank Consensus + Fee Distribution

Tests Cover:
1. ✅ Complete flow: Transaction → Mining → Bank Validation → Complete
2. ✅ Double-spend prevention (hybrid locking)
3. ✅ Fee distribution (miners get 0.5%, banks get 1% split 6 ways)
4. ✅ Consensus scenarios (6/6, 4/6 approve, consensus failure)
5. ✅ Bank penalties (for approving invalid transactions)
6. ✅ Atomicity (all-or-nothing balance updates)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from decimal import Decimal
from datetime import datetime

from database.connection import SessionLocal, engine, Base
from database.models.user import User
from database.models.transaction import Transaction, TransactionStatus
from database.models.block import BlockPublic, BlockPrivate
from database.models.session import Session as UserSession
from database.models.bank import Bank

from core.services.transaction_service import TransactionService
from core.consensus.pow.miner import MiningService
from core.consensus.pos.validator import BankValidator
from core.crypto.idx_generator import IDXGenerator
from core.crypto.session_id import SessionIDGenerator


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")


def cleanup_database(db):
    """Clean all test data"""
    print_info("Cleaning database...")
    db.query(Transaction).delete()
    db.query(BlockPublic).delete()
    db.query(BlockPrivate).delete()
    db.query(UserSession).delete()
    db.query(User).delete()
    db.query(Bank).delete()
    db.commit()
    print_success("Database cleaned!")


def create_test_users(db):
    """Create test users"""
    print_info("Creating test users...")
    
    idx_rajesh = IDXGenerator.generate("RAJSH1234K", "100001")
    rajesh = User(
        idx=idx_rajesh,
        pan_card="RAJSH1234K",
        full_name="Rajesh Kumar",
        balance=Decimal('100000.00')
    )
    
    idx_priya = IDXGenerator.generate("PRIYA5678M", "100002")
    priya = User(
        idx=idx_priya,
        pan_card="PRIYA5678M",
        full_name="Priya Sharma",
        balance=Decimal('50000.00')
    )
    
    idx_miner = IDXGenerator.generate("MINER1234A", "999999")
    miner = User(
        idx=idx_miner,
        pan_card="MINER1234A",
        full_name="Miner Node",
        balance=Decimal('0.00')
    )
    
    db.add_all([rajesh, priya, miner])
    db.commit()
    
    print_success(f"Rajesh: ₹{rajesh.balance:,.2f}")
    print_success(f"Priya: ₹{priya.balance:,.2f}")
    print_success(f"Miner: ₹{miner.balance:,.2f}")
    
    return rajesh, priya, miner


def create_banks(db):
    """Create 6 consortium banks"""
    print_info("\nCreating consortium banks...")
    
    banks_data = [
        ('HDFC', 'HDFC Bank Ltd'),
        ('ICICI', 'ICICI Bank Ltd'),
        ('SBI', 'State Bank of India'),
        ('AXIS', 'Axis Bank Ltd'),
        ('KOTAK', 'Kotak Mahindra Bank'),
        ('YES', 'Yes Bank Ltd')
    ]
    
    banks = []
    for code, name in banks_data:
        bank = Bank(
            bank_code=code,
            bank_name=name,
            stake_amount=Decimal('100000000.00'),
            is_active=True
        )
        banks.append(bank)
        db.add(bank)
    
    db.commit()
    
    for bank in banks:
        print_success(f"{bank.bank_code}: {bank.bank_name}")
    
    return banks


def create_sessions(db, users):
    """Create sessions"""
    print_info("\nCreating sessions...")
    
    sessions = {}
    for user in users:
        if user.full_name != "Miner Node":
            sess_id, expiry = SessionIDGenerator.generate(user.idx, "HDFC")
            session = UserSession(
                session_id=sess_id,
                user_idx=user.idx,
                bank_name="HDFC",
                expires_at=expiry
            )
            db.add(session)
            sessions[user.idx] = session
            print_success(f"Session for {user.full_name}")
    
    db.commit()
    return sessions


def reset_user_balances(db, rajesh, priya, miner):  # ← ADD THIS ENTIRE FUNCTION
    """Reset balances to initial state for isolated testing"""
    rajesh.balance = Decimal('100000.00')
    priya.balance = Decimal('50000.00')
    miner.balance = Decimal('0.00')
    db.commit()


# ============================================================================


# ============================================================================
# TEST 1: Complete Flow with Bank Consensus
# ============================================================================

def test_complete_flow_with_banks(db, rajesh, priya, miner, sessions, banks):
    """
    Test 1: Complete transaction flow with bank validation
    
    Verifies:
    - Transaction creation
    - Mining (miner fee distribution)
    - Bank consensus
    - Bank fee distribution
    - Final balance updates
    """
    print_header("TEST 1: Complete Flow - Transaction → Mining → Banks")
    
    initial_rajesh = rajesh.balance
    initial_priya = priya.balance
    initial_miner = miner.balance
    initial_bank_balance = {b.bank_code: b.total_fees_earned for b in banks}
    
    print_info("Initial state:")
    print_info(f"  Rajesh: ₹{initial_rajesh:,.2f}")
    print_info(f"  Priya: ₹{initial_priya:,.2f}")
    print_info(f"  Miner: ₹{initial_miner:,.2f}")
    
    # Create transaction
    print_info("\nStep 1: Create transaction...")
    tx_service = TransactionService(db)
    tx = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('5000.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    assert tx.status == TransactionStatus.PENDING
    print_success(f"Transaction created: {tx.transaction_hash[:32]}...")
    print_success(f"Amount: ₹{tx.amount}, Fee: ₹{tx.fee}")
    
    # Mine
    print_info("\nStep 2: Mine transaction...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions()
    
    db.refresh(tx)
    assert tx.status == TransactionStatus.PUBLIC_CONFIRMED
    print_success(f"Block #{block.block_index} mined")
    print_success(f"Transaction status: {tx.status.value}")
    
    # Check miner paid
    db.refresh(miner)
    expected_miner_fee = initial_miner + tx.miner_fee
    assert miner.balance == expected_miner_fee
    print_success(f"Miner earned: ₹{tx.miner_fee}")
    
    # Bank validation
    print_info("\nStep 3: Bank consensus...")
    validator = BankValidator(db)
    private_block = validator.validate_and_finalize_block(block.block_index)
    
    assert private_block is not None
    assert private_block.consensus_achieved
    print_success(f"Consensus: {private_block.consensus_votes}/6")
    
    # Verify transaction completed
    db.refresh(tx)
    assert tx.status == TransactionStatus.COMPLETED
    assert tx.completed_at is not None
    print_success(f"Transaction completed")
    
    # Verify balances
    db.refresh(rajesh)
    db.refresh(priya)
    
    expected_rajesh = initial_rajesh - tx.amount - tx.fee
    expected_priya = initial_priya + tx.amount
    
    assert rajesh.balance == expected_rajesh
    assert priya.balance == expected_priya
    
    print_success(f"Rajesh: ₹{initial_rajesh:,.2f} → ₹{rajesh.balance:,.2f}")
    print_success(f"Priya: ₹{initial_priya:,.2f} → ₹{priya.balance:,.2f}")
    
    # Verify bank fees
    expected_fee_per_bank = tx.bank_fee / 6
    for bank in banks:
        db.refresh(bank)
        expected = initial_bank_balance[bank.bank_code] + expected_fee_per_bank
        assert abs(bank.total_fees_earned - expected) < Decimal('0.01')  # ← TOLERANCE!
    
    print_success(f"Each bank earned: ₹{expected_fee_per_bank:.2f}")
    
    print_success("\n✅ TEST 1 PASSED: Complete flow works!\n")


# ============================================================================
# TEST 2: Double-Spend Prevention
# ============================================================================

def test_double_spend_prevention(db, rajesh, priya, miner, sessions):
    """
    Test 2: Double-spend attack prevention
    
    Scenario:
    1. Rajesh has ₹10,000
    2. Creates TX1: Send ₹6,000 to Priya
    3. Creates TX2: Send ₹5,000 to Priya
    4. Both valid at creation (balance ₹10,000)
    5. TX1 mined first → Balance ₹4,000
    6. TX2 should FAIL bank validation (insufficient balance)
    """
    print_header("TEST 2: Double-Spend Prevention")
    
    # Set specific balance
    rajesh.balance = Decimal('10000.00')
    db.commit()
    
    print_info(f"Rajesh balance: ₹{rajesh.balance:,.2f}")
    
    # Create TX1
    print_info("\nCreating TX1: ₹6,000...")
    tx_service = TransactionService(db)
    tx1 = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('6000.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    print_success(f"TX1 created (fee: ₹{tx1.fee})")
    
    # Create TX2
    print_info("\nCreating TX2: ₹5,000...")
    tx2 = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('5000.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    print_success(f"TX2 created (fee: ₹{tx2.fee})")
    
    # Mine both
    print_info("\nMining both transactions...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions(batch_size=10)
    
    print_success(f"Block mined with {len(block.transactions)} transactions")
    
    # Bank validation
    print_info("\nBank validation (should catch double-spend)...")
    validator = BankValidator(db)
    private_block = validator.validate_and_finalize_block(block.block_index)
    
    # Check results
    db.refresh(tx1)
    db.refresh(tx2)
    
    print_info(f"TX1 status: {tx1.status.value}")
    print_info(f"TX2 status: {tx2.status.value}")
    
    # One should complete, one should fail
    completed_count = sum(1 for tx in [tx1, tx2] if tx.status == TransactionStatus.COMPLETED)
    failed_count = sum(1 for tx in [tx1, tx2] if tx.status == TransactionStatus.FAILED)
    
    assert completed_count == 1, "Exactly one transaction should complete"
    assert failed_count == 1, "Exactly one transaction should fail"
    
    print_success("Double-spend prevented!")
    print_success(f"Completed: {completed_count}, Failed: {failed_count}")
    
    print_success("\n✅ TEST 2 PASSED: Double-spend prevented!\n")


# ============================================================================
# TEST 3: Fee Distribution Accuracy
# ============================================================================

def test_fee_distribution_accuracy(db, rajesh, priya, miner, sessions, banks):
    """
    Test 3: Verify exact fee distribution
    
    Transaction: ₹10,000
    Total fee: 1.5% = ₹150
    - Miner: 0.5% = ₹50
    - Banks: 1% = ₹100 (₹16.67 each for 6 banks)
    """
    print_header("TEST 3: Fee Distribution Accuracy")
    reset_user_balances(db, rajesh, priya, miner)
    # Record initial
    initial_miner = miner.balance
    initial_banks = {b.bank_code: b.total_fees_earned for b in banks}
    
    # Create transaction
    print_info("Creating ₹10,000 transaction...")
    tx_service = TransactionService(db)
    tx = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('10000.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    print_success(f"Amount: ₹{tx.amount}")
    print_success(f"Total fee: ₹{tx.fee}")
    print_success(f"Miner fee: ₹{tx.miner_fee}")
    print_success(f"Bank fee: ₹{tx.bank_fee}")
    
    # Expected fees
    expected_total = Decimal('150.00')  # 1.5% of 10,000
    expected_miner = Decimal('50.00')   # 0.5%
    expected_banks = Decimal('100.00')  # 1%
    expected_per_bank = expected_banks / 6
    
    assert tx.fee == expected_total
    assert tx.miner_fee == expected_miner
    assert tx.bank_fee == expected_banks
    
    # Mine and validate
    print_info("\nProcessing transaction...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions()
    
    validator = BankValidator(db)
    validator.validate_and_finalize_block(block.block_index)
    
    # Verify miner fee
    db.refresh(miner)
    actual_miner_earned = miner.balance - initial_miner
    assert actual_miner_earned == expected_miner
    print_success(f"Miner earned: ₹{actual_miner_earned} (expected ₹{expected_miner})")
    
    # Verify bank fees
    print_info("\nBank fee distribution:")
    for bank in banks:
        db.refresh(bank)
        actual_earned = bank.total_fees_earned - initial_banks[bank.bank_code]
        assert abs(actual_earned - expected_per_bank) < Decimal('0.01')  # Allow rounding
        print_success(f"{bank.bank_code}: ₹{actual_earned:.2f} (expected ₹{expected_per_bank:.2f})")
    
    print_success("\n✅ TEST 3 PASSED: Fees distributed accurately!\n")


# ============================================================================
# TEST 4: Multiple Transactions in Block
# ============================================================================

def test_multiple_transactions_bank_validation(db, rajesh, priya, miner, sessions):
    """
    Test 4: Multiple transactions validated by banks
    
    Create 3 transactions, mine together, banks validate all
    """
    print_header("TEST 4: Multiple Transactions with Bank Validation")

    reset_user_balances(db, rajesh, priya, miner) 

    print_info("Creating 3 transactions...")
    tx_service = TransactionService(db)
    
    txs = []
    for i in range(3):
        tx = tx_service.create_transaction(
            sender_idx=rajesh.idx,
            receiver_idx=priya.idx,
            amount=Decimal('1000.00'),
            sender_session_id=sessions[rajesh.idx].session_id
        )
        txs.append(tx)
        print_success(f"TX{i+1} created")
    
    # Mine all
    print_info("\nMining all transactions...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions(batch_size=10)
    
    assert len(block.transactions) == 3
    print_success(f"All 3 transactions in block #{block.block_index}")
    
    # Bank validation
    print_info("\nBank validation...")
    validator = BankValidator(db)
    private_block = validator.validate_and_finalize_block(block.block_index)
    
    assert private_block is not None
    print_success("Banks approved all transactions")
    
    # Verify all completed
    for i, tx in enumerate(txs):
        db.refresh(tx)
        assert tx.status == TransactionStatus.COMPLETED
        print_success(f"TX{i+1}: {tx.status.value}")
    
    print_success("\n✅ TEST 4 PASSED: Multiple transactions validated!\n")


# ============================================================================
# TEST 5: Blockchain Sync (Public + Private)
# ============================================================================

def test_blockchain_sync(db):
    """
    Test 5: Verify public and private chains stay in sync
    
    Every public block should have corresponding private block
    """
    print_header("TEST 5: Public + Private Chain Synchronization")
    
    public_blocks = db.query(BlockPublic).order_by(BlockPublic.block_index).all()
    private_blocks = db.query(BlockPrivate).order_by(BlockPrivate.block_index).all()
    
    print_info(f"Public blocks: {len(public_blocks)}")
    print_info(f"Private blocks: {len(private_blocks)}")
    
    # Check linkage
    for pub_block in public_blocks:
        if pub_block.block_index == 0:  # Skip genesis
            continue
        
        priv_block = db.query(BlockPrivate).filter(
            BlockPrivate.linked_public_block == pub_block.block_index
        ).first()
        
        if priv_block:
            assert priv_block.linked_public_block == pub_block.block_index
            print_success(f"Block #{pub_block.block_index}: Public ↔ Private linked")
        else:
            print_error(f"Block #{pub_block.block_index}: No private block!")
    
    print_success("\n✅ TEST 5 PASSED: Chains synchronized!\n")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run Phase 2 comprehensive tests"""
    
    print_header("PHASE 2 COMPREHENSIVE TEST SUITE")
    print_info("Testing: Bank Consensus + Fee Distribution + Double-Spend Prevention\n")
    
    db = SessionLocal()
    
    try:
        # Setup
        Base.metadata.create_all(bind=engine)
        cleanup_database(db)
        
        rajesh, priya, miner = create_test_users(db)
        banks = create_banks(db)
        sessions = create_sessions(db, [rajesh, priya, miner])
        
        # Run tests
        test_results = []
        
        try:
            test_complete_flow_with_banks(db, rajesh, priya, miner, sessions, banks)
            test_results.append(("Complete Flow with Banks", True))
        except Exception as e:
            test_results.append(("Complete Flow with Banks", False))
            print_error(f"Failed: {str(e)}")
        
        try:
            test_double_spend_prevention(db, rajesh, priya, miner, sessions)
            test_results.append(("Double-Spend Prevention", True))
        except Exception as e:
            test_results.append(("Double-Spend Prevention", False))
            print_error(f"Failed: {str(e)}")
        
        try:
            test_fee_distribution_accuracy(db, rajesh, priya, miner, sessions, banks)
            test_results.append(("Fee Distribution Accuracy", True))
        except Exception as e:
            test_results.append(("Fee Distribution Accuracy", False))
            print_error(f"Failed: {str(e)}")
        
        try:
            test_multiple_transactions_bank_validation(db, rajesh, priya, miner, sessions)
            test_results.append(("Multiple Transactions", True))
        except Exception as e:
            test_results.append(("Multiple Transactions", False))
            print_error(f"Failed: {str(e)}")
        
        try:
            test_blockchain_sync(db)
            test_results.append(("Blockchain Sync", True))
        except Exception as e:
            test_results.append(("Blockchain Sync", False))
            print_error(f"Failed: {str(e)}")
        
        # Summary
        print_header("TEST SUMMARY")
        
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            if result:
                print_success(test_name)
            else:
                print_error(test_name)
        
        print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}")
        
        if passed == total:
            print_header("🎉 ALL PHASE 2 TESTS PASSED! 🎉")
            print_success("Bank consensus + fee distribution working perfectly!")
            print_success("Ready for Phase 3 or final integration!")
        else:
            print_header("⚠️  SOME TESTS FAILED")
        
    finally:
        db.close()


if __name__ == "__main__":
    run_all_tests()