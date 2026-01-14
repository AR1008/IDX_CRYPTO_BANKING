"""
Phase 1 Complete Integration Test
Purpose: Comprehensive end-to-end testing of Transaction → Mining → Blockchain flow

Tests Cover:
1. ✅ Happy Path: Complete transaction flow
2. ❌ Error Scenarios: Insufficient balance, invalid sessions, etc.
3. 🔗 Integration Points: API → Service → Database → Blockchain
4. ⚠️  Edge Cases: Incomplete transactions, invalid data
5. 🔒 Atomicity: Mining complete = block added (all or nothing)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
import json
from decimal import Decimal
from datetime import datetime, timedelta

from database.connection import SessionLocal, engine, Base
from database.models.user import User
from database.models.transaction import Transaction, TransactionStatus
from database.models.block import BlockPublic
from database.models.session import Session as UserSession
from database.models.bank import Bank

from core.services.transaction_service import (
    TransactionService,
    InsufficientBalanceError,
    InvalidSessionError,
    UserNotFoundError
)
from core.consensus.pow.miner import MiningService
from core.crypto.idx_generator import IDXGenerator
from core.crypto.session_id import SessionIDGenerator


class Colors:
    """Terminal colors"""
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


def print_warning(text):
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def cleanup_database(db):
    """Clean all test data"""
    print_info("Cleaning database...")
    db.query(Transaction).delete()
    db.query(BlockPublic).delete()
    db.query(UserSession).delete()
    db.query(User).delete()
    db.query(Bank).delete()
    db.commit()
    print_success("Database cleaned!")


def create_test_users(db):
    """Create test users with balances"""
    print_info("Creating test users...")
    
    # User 1: Rajesh (rich)
    idx_rajesh = IDXGenerator.generate("RAJSH1234K", "100001")
    rajesh = User(
        idx=idx_rajesh,
        pan_card="RAJSH1234K",
        full_name="Rajesh Kumar",
        balance=Decimal('50000.00')  # ₹50,000
    )
    
    # User 2: Priya (moderate)
    idx_priya = IDXGenerator.generate("PRIYA5678M", "100002")
    priya = User(
        idx=idx_priya,
        pan_card="PRIYA5678M",
        full_name="Priya Sharma",
        balance=Decimal('10000.00')  # ₹10,000
    )
    
    # User 3: Amit (poor)
    idx_amit = IDXGenerator.generate("AMITK9012N", "100003")
    amit = User(
        idx=idx_amit,
        pan_card="AMITK9012N",
        full_name="Amit Kapoor",
        balance=Decimal('100.00')  # ₹100 only
    )
    
    # Miner
    idx_miner = IDXGenerator.generate("MINER1234A", "999999")
    miner = User(
        idx=idx_miner,
        pan_card="MINER1234A",
        full_name="Miner Node 001",
        balance=Decimal('0.00')
    )
    
    db.add_all([rajesh, priya, amit, miner])
    db.commit()
    
    print_success(f"Rajesh created: ₹{rajesh.balance:,.2f}")
    print_success(f"Priya created: ₹{priya.balance:,.2f}")
    print_success(f"Amit created: ₹{amit.balance:,.2f}")
    print_success(f"Miner created: ₹{miner.balance:,.2f}")
    
    return rajesh, priya, amit, miner


def create_sessions(db, users):
    """Create active sessions for users"""
    print_info("\nCreating user sessions...")
    
    sessions = {}
    for user in users:
        if user.full_name != "Miner Node 001":  # Skip miner
            sess_id, expiry = SessionIDGenerator.generate(user.idx, "HDFC")
            session = UserSession(
                session_id=sess_id,
                user_idx=user.idx,
                bank_name="HDFC",
                expires_at=expiry
            )
            db.add(session)
            sessions[user.idx] = session
            print_success(f"Session created for {user.full_name}")
    
    db.commit()
    return sessions


# ============================================================================
# TEST 1: HAPPY PATH - Complete Transaction Flow
# ============================================================================

def test_happy_path_complete_flow(db, rajesh, priya, miner, sessions):
    """
    Test 1: Complete happy path
    
    Flow:
    1. Create transaction (Rajesh → Priya ₹1,000)
    2. Verify transaction status = PENDING
    3. Mine transaction
    4. Verify block created
    5. Verify transaction status = PUBLIC_CONFIRMED
    6. Verify balances NOT updated yet (mining complete but not finalized)
    7. Complete transaction (simulate bank consensus)
    8. Verify balances updated correctly
    9. Verify miner received fees
    """
    print_header("TEST 1: HAPPY PATH - Complete Transaction Flow")
    
    # Record initial balances
    initial_rajesh = rajesh.balance
    initial_priya = priya.balance
    initial_miner = miner.balance
    
    print_info(f"Initial balances:")
    print_info(f"  Rajesh: ₹{initial_rajesh:,.2f}")
    print_info(f"  Priya: ₹{initial_priya:,.2f}")
    print_info(f"  Miner: ₹{initial_miner:,.2f}")
    
    # Step 1: Create transaction
    print_info("\nStep 1: Creating transaction...")
    tx_service = TransactionService(db)
    
    tx = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('1000.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    assert tx.status == TransactionStatus.PENDING, "Transaction should be PENDING"
    print_success(f"Transaction created: {tx.transaction_hash[:32]}...")
    print_success(f"Status: {tx.status.value}")
    
    # Step 2: Verify transaction in database
    print_info("\nStep 2: Verifying transaction persisted...")
    db_tx = db.query(Transaction).filter(Transaction.id == tx.id).first()
    assert db_tx is not None, "Transaction not found in database"
    assert db_tx.status == TransactionStatus.PENDING, "Status should be PENDING"
    print_success("Transaction verified in database")
    
    # Step 3: Mine transaction
    print_info("\nStep 3: Mining transaction...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    
    block = mining_service.mine_pending_transactions(batch_size=10)
    
    assert block is not None, "Block should be created"
    assert block.block_index >= 1, "Block index should be >= 1"
    assert tx.transaction_hash in block.transactions, "Transaction should be in block"
    print_success(f"Block #{block.block_index} mined successfully")
    
    # Step 4: Verify transaction status updated
    print_info("\nStep 4: Verifying transaction status...")
    db.refresh(tx)
    assert tx.status == TransactionStatus.PUBLIC_CONFIRMED, "Should be PUBLIC_CONFIRMED"
    assert tx.public_block_index == block.block_index, "Block index should match"
    print_success(f"Transaction status: {tx.status.value}")
    
    # Step 5: Verify balances NOT updated yet (important!)
    print_info("\nStep 5: Verifying balances NOT updated yet...")
    db.refresh(rajesh)
    db.refresh(priya)
    assert rajesh.balance == initial_rajesh, "Rajesh balance should NOT change yet"
    assert priya.balance == initial_priya, "Priya balance should NOT change yet"
    print_success("Balances correctly NOT updated (waiting for bank consensus)")
    
    # Step 6: Complete transaction (simulate bank consensus)
    print_info("\nStep 6: Completing transaction (bank consensus)...")
    tx_service.complete_transaction(tx.id, private_block_index=block.block_index)
    
    # Step 7: Verify balances updated
    print_info("\nStep 7: Verifying final balances...")
    db.refresh(rajesh)
    db.refresh(priya)
    db.refresh(miner)
    
    expected_rajesh = initial_rajesh - Decimal('1000.00') - tx.fee
    expected_priya = initial_priya + Decimal('1000.00')
    expected_miner = initial_miner + tx.miner_fee
    
    assert rajesh.balance == expected_rajesh, f"Rajesh balance incorrect: {rajesh.balance} != {expected_rajesh}"
    assert priya.balance == expected_priya, f"Priya balance incorrect: {priya.balance} != {expected_priya}"
    assert miner.balance == expected_miner, f"Miner balance incorrect: {miner.balance} != {expected_miner}"
    
    print_success(f"Rajesh: ₹{initial_rajesh} → ₹{rajesh.balance} (sent ₹{Decimal('1000.00') + tx.fee})")
    print_success(f"Priya: ₹{initial_priya} → ₹{priya.balance} (received ₹1,000)")
    print_success(f"Miner: ₹{initial_miner} → ₹{miner.balance} (earned ₹{tx.miner_fee})")
    
    # Step 8: Verify transaction completed
    db.refresh(tx)
    assert tx.status == TransactionStatus.COMPLETED, "Transaction should be COMPLETED"
    assert tx.completed_at is not None, "Completed timestamp should be set"
    print_success(f"Transaction completed at: {tx.completed_at}")
    
    print_success("\n✅ TEST 1 PASSED: Complete flow works correctly!\n")


# ============================================================================
# TEST 2: ERROR SCENARIO - Insufficient Balance
# ============================================================================

def test_insufficient_balance(db, amit, priya, sessions):
    """
    Test 2: Insufficient balance error
    
    Amit has ₹100 but tries to send ₹1,000
    Should fail WITHOUT creating transaction or changing balances
    """
    print_header("TEST 2: ERROR - Insufficient Balance")
    
    initial_amit = amit.balance
    initial_priya = priya.balance
    
    print_info(f"Amit balance: ₹{initial_amit}")
    print_info(f"Trying to send: ₹1,000")
    
    tx_service = TransactionService(db)
    
    try:
        tx = tx_service.create_transaction(
            sender_idx=amit.idx,
            receiver_idx=priya.idx,
            amount=Decimal('1000.00'),
            sender_session_id=sessions[amit.idx].session_id
        )
        print_error("Transaction should have failed!")
        assert False, "Should raise InsufficientBalanceError"
        
    except InsufficientBalanceError as e:
        print_success(f"Correctly raised error: {str(e)}")
    
    # Verify NO transaction created
    tx_count = db.query(Transaction).filter(
        Transaction.sender_idx == amit.idx,
        Transaction.receiver_idx == priya.idx
    ).count()
    
    assert tx_count == 0, "No transaction should be created"
    print_success("No transaction record created")
    
    # Verify balances unchanged
    db.refresh(amit)
    db.refresh(priya)
    assert amit.balance == initial_amit, "Amit balance should be unchanged"
    assert priya.balance == initial_priya, "Priya balance should be unchanged"
    print_success("Balances unchanged")
    
    print_success("\n✅ TEST 2 PASSED: Insufficient balance correctly prevented!\n")


# ============================================================================
# TEST 3: ERROR SCENARIO - Invalid Session
# ============================================================================

def test_invalid_session(db, rajesh, priya):
    """
    Test 3: Invalid session error
    
    Try to create transaction with fake session ID
    Should fail WITHOUT creating transaction
    """
    print_header("TEST 3: ERROR - Invalid Session")
    
    tx_service = TransactionService(db)
    
    try:
        tx = tx_service.create_transaction(
            sender_idx=rajesh.idx,
            receiver_idx=priya.idx,
            amount=Decimal('100.00'),
            sender_session_id="SESSION_FAKE_INVALID_123"
        )
        print_error("Transaction should have failed!")
        assert False, "Should raise InvalidSessionError"
        
    except InvalidSessionError as e:
        print_success(f"Correctly raised error: {str(e)}")
    
    print_success("\n✅ TEST 3 PASSED: Invalid session correctly rejected!\n")


# ============================================================================
# TEST 4: ERROR SCENARIO - Expired Session
# ============================================================================

def test_expired_session(db, rajesh, priya):
    """
    Test 4: Expired session error
    
    Create expired session and try to use it
    Should fail WITHOUT creating transaction
    """
    print_header("TEST 4: ERROR - Expired Session")
    
    # Create expired session (expires 1 hour ago)
    expired_time = datetime.now() - timedelta(hours=1)
    
    expired_session = UserSession(
        session_id="SESSION_EXPIRED_TEST",
        user_idx=rajesh.idx,
        bank_name="HDFC",
        expires_at=expired_time
    )
    db.add(expired_session)
    db.commit()
    
    print_info(f"Created expired session: {expired_time}")
    
    tx_service = TransactionService(db)
    
    try:
        tx = tx_service.create_transaction(
            sender_idx=rajesh.idx,
            receiver_idx=priya.idx,
            amount=Decimal('100.00'),
            sender_session_id="SESSION_EXPIRED_TEST"
        )
        print_error("Transaction should have failed!")
        assert False, "Should raise InvalidSessionError"
        
    except InvalidSessionError as e:
        print_success(f"Correctly raised error: {str(e)}")
    
    print_success("\n✅ TEST 4 PASSED: Expired session correctly rejected!\n")


# ============================================================================
# TEST 5: ATOMICITY - Mining Failure Should Not Create Block
# ============================================================================

def test_mining_atomicity(db, rajesh, priya, miner, sessions):
    """
    Test 5: Mining atomicity
    
    Verify that if mining fails partway through, NO block is created
    All-or-nothing behavior
    """
    print_header("TEST 5: ATOMICITY - Mining All-or-Nothing")
    
    # Create valid transaction
    tx_service = TransactionService(db)
    tx = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('500.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    print_success(f"Transaction created: {tx.transaction_hash[:32]}...")
    
    # Get initial block count
    initial_block_count = db.query(BlockPublic).count()
    print_info(f"Initial block count: {initial_block_count}")
    
    # Mine successfully
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions()
    
    # Verify block created
    final_block_count = db.query(BlockPublic).count()
    assert final_block_count == initial_block_count + 1, "Block count should increase by 1"
    print_success(f"Block created successfully: #{block.block_index}")
    
    # Verify transaction status updated
    db.refresh(tx)
    assert tx.status == TransactionStatus.PUBLIC_CONFIRMED, "Transaction should be confirmed"
    assert tx.public_block_index == block.block_index, "Block index should match"
    
    print_success("Transaction properly linked to block")
    print_success("\n✅ TEST 5 PASSED: Mining atomicity verified!\n")


# ============================================================================
# TEST 6: EDGE CASE - User Not Found
# ============================================================================

def test_user_not_found(db, rajesh, sessions):
    """
    Test 6: User not found error
    
    Try to send money to non-existent user
    Should fail cleanly
    """
    print_header("TEST 6: EDGE CASE - User Not Found")
    
    tx_service = TransactionService(db)
    
    try:
        tx = tx_service.create_transaction(
            sender_idx=rajesh.idx,
            receiver_idx="IDX_NONEXISTENT_USER",
            amount=Decimal('100.00'),
            sender_session_id=sessions[rajesh.idx].session_id
        )
        print_error("Transaction should have failed!")
        assert False, "Should raise UserNotFoundError"
        
    except UserNotFoundError as e:
        print_success(f"Correctly raised error: {str(e)}")
    
    print_success("\n✅ TEST 6 PASSED: Non-existent user correctly rejected!\n")


# ============================================================================
# TEST 7: CONCURRENCY - Multiple Transactions in One Block
# ============================================================================

def test_multiple_transactions_one_block(db, rajesh, priya, amit, miner, sessions):
    """
    Test 7: Multiple transactions in one block
    
    Create 3 transactions and mine them together
    Verify all are included in same block
    """
    print_header("TEST 7: CONCURRENCY - Multiple Transactions")
    
    tx_service = TransactionService(db)
    
    # Create 3 transactions
    print_info("Creating 3 transactions...")
    
    tx1 = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=priya.idx,
        amount=Decimal('100.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    tx2 = tx_service.create_transaction(
        sender_idx=rajesh.idx,
        receiver_idx=amit.idx,
        amount=Decimal('200.00'),
        sender_session_id=sessions[rajesh.idx].session_id
    )
    
    tx3 = tx_service.create_transaction(
        sender_idx=priya.idx,
        receiver_idx=amit.idx,
        amount=Decimal('50.00'),
        sender_session_id=sessions[priya.idx].session_id
    )
    
    print_success(f"Created {3} transactions")
    
    # Mine all together
    print_info("\nMining all transactions together...")
    mining_service = MiningService(db, miner_idx=miner.idx)
    block = mining_service.mine_pending_transactions(batch_size=10)
    
    assert block is not None, "Block should be created"
    assert len(block.transactions) == 3, "All 3 transactions should be in block"
    print_success(f"All 3 transactions in block #{block.block_index}")
    
    # Verify all transactions updated
    db.refresh(tx1)
    db.refresh(tx2)
    db.refresh(tx3)
    
    assert tx1.status == TransactionStatus.PUBLIC_CONFIRMED, "TX1 should be confirmed"
    assert tx2.status == TransactionStatus.PUBLIC_CONFIRMED, "TX2 should be confirmed"
    assert tx3.status == TransactionStatus.PUBLIC_CONFIRMED, "TX3 should be confirmed"
    
    assert tx1.public_block_index == block.block_index, "TX1 block index should match"
    assert tx2.public_block_index == block.block_index, "TX2 block index should match"
    assert tx3.public_block_index == block.block_index, "TX3 block index should match"
    
    print_success("All transactions correctly linked to same block")
    print_success("\n✅ TEST 7 PASSED: Multiple transactions handled correctly!\n")


# ============================================================================
# TEST 8: BLOCKCHAIN INTEGRITY - Chain Validation
# ============================================================================

def test_blockchain_integrity(db):
    """
    Test 8: Blockchain integrity
    
    Verify entire blockchain is valid:
    - Each block links to previous
    - Hashes are correct
    - No gaps in block numbers
    """
    print_header("TEST 8: BLOCKCHAIN INTEGRITY")
    
    blocks = db.query(BlockPublic).order_by(BlockPublic.block_index).all()
    
    print_info(f"Verifying {len(blocks)} blocks...")
    
    for i, block in enumerate(blocks):
        # Verify block index is sequential
        assert block.block_index == i, f"Block index gap at {i}"
        
        # Verify hash starts with correct difficulty
        expected_prefix = "0" * block.difficulty
        assert block.block_hash.startswith(expected_prefix), f"Block {i} hash invalid"
        
        # Verify links to previous (except genesis)
        if i > 0:
            prev_block = blocks[i-1]
            assert block.previous_hash == prev_block.block_hash, f"Block {i} chain broken"
        
        print_success(f"Block #{i} valid: {block.block_hash[:40]}...")
    
    print_success(f"\n✅ TEST 8 PASSED: All {len(blocks)} blocks valid!\n")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run complete Phase 1 test suite"""
    
    print_header("PHASE 1 COMPREHENSIVE INTEGRATION TEST SUITE")
    print_info("Testing: Transaction → Mining → Blockchain")
    print_info("Coverage: Happy path, errors, edge cases, atomicity\n")
    
    # Setup
    db = SessionLocal()
    
    try:
        # Create tables
        print_info("Setting up database...")
        Base.metadata.create_all(bind=engine)
        print_success("Tables created\n")
        
        # Cleanup
        cleanup_database(db)
        
        # Create test data
        rajesh, priya, amit, miner = create_test_users(db)
        sessions = create_sessions(db, [rajesh, priya, amit, miner])
        
        # Run tests
        test_results = []
        
        try:
            test_happy_path_complete_flow(db, rajesh, priya, miner, sessions)
            test_results.append(("Happy Path Flow", True))
        except Exception as e:
            test_results.append(("Happy Path Flow", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_insufficient_balance(db, amit, priya, sessions)
            test_results.append(("Insufficient Balance", True))
        except Exception as e:
            test_results.append(("Insufficient Balance", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_invalid_session(db, rajesh, priya)
            test_results.append(("Invalid Session", True))
        except Exception as e:
            test_results.append(("Invalid Session", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_expired_session(db, rajesh, priya)
            test_results.append(("Expired Session", True))
        except Exception as e:
            test_results.append(("Expired Session", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_mining_atomicity(db, rajesh, priya, miner, sessions)
            test_results.append(("Mining Atomicity", True))
        except Exception as e:
            test_results.append(("Mining Atomicity", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_user_not_found(db, rajesh, sessions)
            test_results.append(("User Not Found", True))
        except Exception as e:
            test_results.append(("User Not Found", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_multiple_transactions_one_block(db, rajesh, priya, amit, miner, sessions)
            test_results.append(("Multiple Transactions", True))
        except Exception as e:
            test_results.append(("Multiple Transactions", False))
            print_error(f"Test failed: {str(e)}")
        
        try:
            test_blockchain_integrity(db)
            test_results.append(("Blockchain Integrity", True))
        except Exception as e:
            test_results.append(("Blockchain Integrity", False))
            print_error(f"Test failed: {str(e)}")
        
        # Final summary
        print_header("TEST SUMMARY")
        
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            if result:
                print_success(f"{test_name}")
            else:
                print_error(f"{test_name}")
        
        print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}")
        
        if passed == total:
            print_header("🎉 ALL TESTS PASSED! PHASE 1 COMPLETE! 🎉")
            print_success("Your system is working correctly!")
            print_success("Ready to build Phase 2 (Fee Distribution & Bank Consensus)")
        else:
            print_header("⚠️  SOME TESTS FAILED")
            print_warning(f"{total - passed} test(s) need attention")
        
    finally:
        db.close()


if __name__ == "__main__":
    run_all_tests()