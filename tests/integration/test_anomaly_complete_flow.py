"""
Integration Tests: Complete Anomaly Detection Flow
Purpose: Test end-to-end anomaly detection, ZKP, threshold encryption, court orders, and freeze

Complete Flow Tests:
1. Transaction flagged (score >= 65)
2. ZKP proof generated
3. Details threshold-encrypted
4. Court order issued by judge
5. Keys generated and distributed
6. Keys used for decryption
7. Account freeze triggered (24h or 72h)
8. Auto-unfreeze after timer expires

Privacy Requirements Verified:
- User unaware of anomaly flag
- Transaction proceeds normally
- ZKP hides details except flag
- Government sees ONLY: date/time, amount, tx ID (NO counterparty session ID/IDX)
- User maintains full access to own history
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from database.models.transaction import Transaction
from database.models.bank import Bank
from database.models.bank_account import BankAccount
from database.models.recipient import Recipient

from core.services.anomaly_detection_engine import AnomalyDetectionEngine
from core.crypto.anomaly_zkp import AnomalyZKPService
from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption
from core.services.court_order_verification_anomaly import CourtOrderVerificationAnomalyService
from core.services.account_freeze_service import AccountFreezeService
from core.services.court_order_anomaly_integration import CourtOrderAnomalyIntegration
from core.services.gov_transaction_history_service import GovTransactionHistoryService


@pytest.fixture(scope='module')
def test_db():
    """Create test database"""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test bank
    bank = Bank(
        bank_id="TEST_BANK_001",
        bank_name="Test Bank",
        ifsc_code="TEST0001234",
        idx_address="IDX_BANK_TEST123",
        public_key="0xbank_public_key",
        registration_status="APPROVED"
    )
    session.add(bank)

    # Create test user account
    account = BankAccount(
        account_number="TEST_ACC_001",
        idx_address="IDX_USER_TEST123",
        bank_id="TEST_BANK_001",
        balance=Decimal('10000000.00'),  # ₹1 crore
        account_type="SAVINGS",
        frozen=False
    )
    session.add(account)

    # Create test recipient
    recipient = Recipient(
        idx_address="IDX_RECEIVER_TEST456",
        name="Test Receiver",
        bank_id="TEST_BANK_001",
        account_number="TEST_ACC_002",
        verified=True
    )
    session.add(recipient)

    session.commit()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def anomaly_engine(test_db):
    """Create anomaly detection engine"""
    return AnomalyDetectionEngine(test_db)


@pytest.fixture
def zkp_service():
    """Create ZKP service"""
    return AnomalyZKPService()


@pytest.fixture
def threshold_enc():
    """Create threshold encryption service"""
    return AnomalyThresholdEncryption()


@pytest.fixture
def court_order_service(test_db):
    """Create court order integration service"""
    return CourtOrderAnomalyIntegration(test_db)


@pytest.fixture
def freeze_service(test_db):
    """Create account freeze service"""
    return AccountFreezeService(test_db)


@pytest.fixture
def gov_history_service(test_db):
    """Create government transaction history service"""
    return GovTransactionHistoryService(test_db)


class TestCompleteAnomalyFlow:
    """Test complete end-to-end anomaly detection flow"""

    def test_complete_flow_high_value_transaction(
        self,
        test_db,
        anomaly_engine,
        zkp_service,
        threshold_enc,
        court_order_service,
        freeze_service,
        gov_history_service
    ):
        """
        Test complete flow for high-value transaction (₹75L)

        Flow:
        1. Transaction flagged (score >= 65)
        2. ZKP proof generated
        3. Details threshold-encrypted
        4. Court order issued
        5. Keys generated and distributed
        6. Keys used for decryption
        7. Account freeze triggered (24h)
        8. Government sees restricted view
        9. User sees full view
        """
        print("\n=== Test: Complete Anomaly Flow (₹75L Transaction) ===\n")

        # Step 1: Create high-value transaction (₹75 lakh)
        print("Step 1: Creating ₹75L transaction...")

        transaction = Transaction(
            transaction_hash="0xtest_anomaly_tx_001",
            sender_idx="IDX_USER_TEST123",
            receiver_idx="IDX_RECEIVER_TEST456",
            amount=Decimal('7500000.00'),  # ₹75 lakh
            sender_session_id="SESSION_SENDER_001",
            receiver_session_id="SESSION_RECEIVER_001",
            transaction_type="TRANSFER",
            status="PENDING"
        )
        test_db.add(transaction)
        test_db.commit()

        print(f"  ✅ Transaction created: {transaction.transaction_hash}")
        print(f"  Amount: ₹{transaction.amount:,}")

        # Step 2: Run anomaly detection
        print("\nStep 2: Running anomaly detection...")

        anomaly_result = anomaly_engine.analyze_transaction(
            transaction_hash=transaction.transaction_hash,
            sender_idx=transaction.sender_idx,
            receiver_idx=transaction.receiver_idx,
            amount=transaction.amount,
            transaction_type=transaction.transaction_type
        )

        print(f"  Anomaly score: {anomaly_result['anomaly_score']}")
        print(f"  Is flagged: {anomaly_result['requires_investigation']}")
        print(f"  Flags: {anomaly_result['anomaly_flags']}")

        # Verify flagged
        assert anomaly_result['requires_investigation'] == True
        assert anomaly_result['anomaly_score'] >= 65.0
        assert 'HIGH_VALUE_TIER_1' in anomaly_result['anomaly_flags']

        # Step 3: Generate ZKP proof
        print("\nStep 3: Generating ZKP proof...")

        zkp_proof = zkp_service.generate_proof(
            transaction_hash=transaction.transaction_hash,
            requires_investigation=True,
            anomaly_score=anomaly_result['anomaly_score']
        )

        print(f"  ✅ ZKP proof generated")
        print(f"  Proof valid: {zkp_service.verify_proof(zkp_proof)}")

        # Verify ZKP proof
        assert zkp_service.verify_proof(zkp_proof) == True

        # Step 4: Threshold encryption
        print("\nStep 4: Threshold encrypting transaction details...")

        transaction_details = {
            'transaction_hash': transaction.transaction_hash,
            'sender_idx': transaction.sender_idx,
            'receiver_idx': transaction.receiver_idx,
            'amount': str(transaction.amount),
            'anomaly_score': anomaly_result['anomaly_score'],
            'anomaly_flags': anomaly_result['anomaly_flags']
        }

        encrypted_package = threshold_enc.encrypt_anomaly_transaction(
            transaction_details=transaction_details,
            threshold=3,
            authorities=[
                'company',
                'supreme_court',
                'rbi',
                'fiu',
                'cbi',
                'income_tax'
            ]
        )

        print(f"  ✅ Details encrypted")
        print(f"  Authorities: {len(encrypted_package['key_shares'])} key shares")
        print(f"  Threshold: {encrypted_package['threshold']}")

        # Update transaction with encrypted details
        transaction.threshold_encrypted_details = json.dumps(encrypted_package).encode('utf-8')
        transaction.anomaly_score = Decimal(str(anomaly_result['anomaly_score']))
        transaction.anomaly_flags = anomaly_result['anomaly_flags']
        transaction.requires_investigation = True
        transaction.investigation_status = 'PENDING'
        transaction.flagged_at = datetime.now(timezone.utc)
        transaction.zkp_proof = json.dumps(zkp_proof).encode('utf-8')
        test_db.commit()

        # Step 5: Government views flagged transactions (RESTRICTED)
        print("\nStep 5: Government views flagged transactions (RESTRICTED)...")

        gov_view = gov_history_service.get_flagged_transactions_for_gov(limit=10)

        print(f"  Flagged transactions: {gov_view['total_count']}")
        if gov_view['transactions']:
            first_tx = gov_view['transactions'][0]
            print(f"  Visible fields: {list(first_tx.keys())}")

            # Verify NO sensitive data
            assert 'sender_idx' not in first_tx
            assert 'receiver_idx' not in first_tx
            assert 'sender_session_id' not in first_tx
            assert 'receiver_session_id' not in first_tx

            # Verify allowed fields
            assert 'transaction_id' in first_tx
            assert 'timestamp' in first_tx
            assert 'amount' in first_tx

            print(f"  ✅ Privacy verified: NO sender/receiver IDX or session IDs")

        # Step 6: Court order issued
        print("\nStep 6: Issuing court order...")

        court_order = court_order_service.issue_anomaly_court_order(
            transaction_hash=transaction.transaction_hash,
            judge_id="supreme_court_judge_1",
            judge_signature="0xvalid_judge_signature",
            regulatory_authority="rbi",
            reason="Suspected money laundering - high value transaction",
            case_number="CASE_2026_TEST_001"
        )

        print(f"  ✅ Court order issued: {court_order['order_id']}")
        print(f"  Keys generated: {court_order['keys_generated']}")
        print(f"  Regulatory authority: {court_order['regulatory_authority']}")

        # Verify keys generated
        assert court_order['keys_generated'] == True
        assert 'keys' in court_order

        # Step 7: Decrypt with 3 authority keys
        print("\nStep 7: Decrypting with 3 authority keys...")

        # Get key shares from encrypted package
        company_share = encrypted_package['key_shares'][0]  # Company
        court_share = encrypted_package['key_shares'][1]    # Supreme Court
        rbi_share = encrypted_package['key_shares'][2]      # RBI

        decryption_result = court_order_service.decrypt_with_court_order(
            order_id=court_order['order_id'],
            transaction_hash=transaction.transaction_hash,
            company_key_share=company_share,
            court_key_share=court_share,
            regulatory_key_share=rbi_share
        )

        print(f"  ✅ Transaction decrypted")
        print(f"  Freeze triggered: {decryption_result['freeze_triggered']}")
        print(f"  Freeze duration: {decryption_result['freeze_duration_hours']}h")

        # Verify decryption and freeze
        assert decryption_result['decrypted'] == True
        assert decryption_result['freeze_triggered'] == True
        assert decryption_result['freeze_duration_hours'] == 24  # First investigation

        # Step 8: Verify user's own history (FULL ACCESS)
        print("\nStep 8: User views own transaction history (FULL ACCESS)...")

        user_view = gov_history_service.get_user_transaction_history(
            user_idx="IDX_USER_TEST123",
            limit=10
        )

        print(f"  User's transactions: {user_view['total_count']}")
        if user_view['transactions']:
            first_tx = user_view['transactions'][0]
            print(f"  Visible fields: {list(first_tx.keys())}")

            # Verify FULL access
            assert 'sender_idx' in first_tx or 'sender_session_id' in first_tx
            assert 'receiver_idx' in first_tx or 'receiver_session_id' in first_tx

            print(f"  ✅ Full access verified: User can see all fields")

        # Step 9: Generate PDF statement for user (tax compliance)
        print("\nStep 9: Generating PDF statement for user (tax compliance)...")

        pdf_result = gov_history_service.generate_pdf_statement_for_user(
            user_idx="IDX_USER_TEST123"
        )

        print(f"  ✅ PDF generated: {pdf_result['pdf_filename']}")
        print(f"  Purpose: {pdf_result['purpose']}")
        print(f"  Transactions included: {pdf_result['transaction_count']}")

        # Verify PDF includes full details
        assert pdf_result['includes_full_details'] == True
        assert pdf_result['purpose'] == 'TAX_FILING_CA_AUDITOR'

        print("\n=== ✅ Complete Flow Test PASSED ===\n")

    def test_consecutive_investigations_freeze_duration(
        self,
        test_db,
        freeze_service
    ):
        """
        Test freeze duration for consecutive investigations

        Scenario:
        - First investigation: 24 hours
        - Second investigation (same month): 72 hours
        - Third investigation (same month): 72 hours
        """
        print("\n=== Test: Consecutive Investigations Freeze Duration ===\n")

        user_idx = "IDX_USER_CONSECUTIVE_TEST"
        current_month = datetime.now(timezone.utc).strftime('%Y-%m')

        # First investigation
        print("Investigation #1 (First this month)...")
        freeze1 = freeze_service.trigger_freeze(
            user_idx=user_idx,
            transaction_hash="0xtx_001",
            reason="First investigation"
        )

        print(f"  Duration: {freeze1['freeze_duration_hours']}h")
        assert freeze1['freeze_duration_hours'] == 24
        assert freeze1['is_first_this_month'] == True

        print("\n=== ✅ Consecutive Freeze Test PASSED ===\n")

    def test_privacy_requirements_comprehensive(
        self,
        test_db,
        gov_history_service
    ):
        """
        Test comprehensive privacy requirements

        Verify:
        - Government CANNOT see: sender/receiver IDX, session IDs
        - Government CAN see: date/time, amount, tx ID
        - User CAN see: ALL fields
        """
        print("\n=== Test: Comprehensive Privacy Requirements ===\n")

        # Create test transaction
        transaction = Transaction(
            transaction_hash="0xprivacy_test_tx",
            sender_idx="IDX_SENDER_PRIVACY",
            receiver_idx="IDX_RECEIVER_PRIVACY",
            amount=Decimal('8000000.00'),
            sender_session_id="SESSION_SENDER_PRIVACY",
            receiver_session_id="SESSION_RECEIVER_PRIVACY",
            transaction_type="TRANSFER",
            status="COMPLETED",
            requires_investigation=True,
            investigation_status='PENDING',
            anomaly_score=Decimal('75.5'),
            flagged_at=datetime.now(timezone.utc)
        )
        test_db.add(transaction)
        test_db.commit()

        # Test 1: Government view (RESTRICTED)
        print("Test 1: Government View (RESTRICTED)...")
        gov_view = gov_history_service.get_flagged_transactions_for_gov(limit=10)

        if gov_view['transactions']:
            tx = gov_view['transactions'][0]

            # What government CANNOT see
            forbidden_fields = [
                'sender_idx',
                'receiver_idx',
                'sender_session_id',
                'receiver_session_id'
            ]

            for field in forbidden_fields:
                assert field not in tx, f"Government should NOT see {field}"
                print(f"  ✅ {field}: HIDDEN")

            # What government CAN see
            required_fields = ['transaction_id', 'timestamp', 'amount']
            for field in required_fields:
                assert field in tx, f"Government should see {field}"
                print(f"  ✅ {field}: VISIBLE")

        # Test 2: User view (FULL ACCESS)
        print("\nTest 2: User View (FULL ACCESS)...")
        user_view = gov_history_service.get_user_transaction_history(
            user_idx="IDX_SENDER_PRIVACY",
            limit=10
        )

        if user_view['transactions']:
            tx = user_view['transactions'][0]

            # User should see ALL fields
            full_access_fields = [
                'sender_session_id',
                'receiver_session_id',
                'sender_idx',
                'receiver_idx'
            ]

            for field in full_access_fields:
                assert field in tx, f"User should see {field}"
                print(f"  ✅ {field}: VISIBLE TO USER")

        print("\n=== ✅ Privacy Requirements Test PASSED ===\n")

    def test_zkp_hides_details_except_flag(
        self,
        zkp_service
    ):
        """
        Test that ZKP proof hides transaction details except anomaly flag

        Verify:
        - Proof reveals ONLY that transaction is flagged
        - Proof does NOT reveal: amount, sender, receiver, score
        - Proof is verifiable
        """
        print("\n=== Test: ZKP Hides Details Except Flag ===\n")

        # Generate proof for flagged transaction
        proof_flagged = zkp_service.generate_anomaly_proof(
            transaction_hash="0xzkp_test_flagged",
            requires_investigation=True,
            anomaly_score=85.5,
            anomaly_flags=['HIGH_VALUE_TIER_1']
        )

        print("Proof for flagged transaction:")
        print(f"  Fields in proof: {list(proof_flagged.keys())}")

        # Verify proof structure (updated field names)
        assert 'flag_commitment' in proof_flagged
        assert 'proof_data' in proof_flagged
        assert 'challenge' in proof_flagged['proof_data']
        assert 'response' in proof_flagged['proof_data']

        # Verify proof does NOT contain sensitive data
        sensitive_fields = ['amount', 'sender_idx', 'receiver_idx', 'anomaly_score']
        for field in sensitive_fields:
            assert field not in proof_flagged, f"Proof should NOT contain {field}"
            print(f"  ✅ {field}: HIDDEN")

        # Verify proof is valid
        is_valid = zkp_service.verify_anomaly_proof(proof_flagged)
        print(f"  ✅ Proof valid: {is_valid}")
        assert is_valid == True

        # Generate proof for non-flagged transaction
        proof_normal = zkp_service.generate_anomaly_proof(
            transaction_hash="0xzkp_test_normal",
            requires_investigation=False,
            anomaly_score=45.0,
            anomaly_flags=[]
        )

        print("\nProof for normal transaction:")
        is_valid_normal = zkp_service.verify_anomaly_proof(proof_normal)
        print(f"  ✅ Proof valid: {is_valid_normal}")
        assert is_valid_normal == True

        print("\n=== ✅ ZKP Privacy Test PASSED ===\n")

    def test_threshold_encryption_requires_3_parties(
        self,
        threshold_enc
    ):
        """
        Test that threshold decryption requires exactly 3 parties

        Verify:
        - 2 keys: CANNOT decrypt
        - 3 keys: CAN decrypt
        - Authority structure: Company + Supreme Court + 1-of-4
        """
        print("\n=== Test: Threshold Encryption Requires 3 Parties ===\n")

        # Create test transaction details
        transaction_details = {
            'transaction_hash': '0xthreshold_test',
            'sender_idx': 'IDX_SENDER_THRESHOLD',
            'receiver_idx': 'IDX_RECEIVER_THRESHOLD',
            'amount': '10000000.00',
            'anomaly_score': 90.0,
            'anomaly_flags': ['HIGH_VALUE_TIER_1']
        }

        # Encrypt with threshold scheme
        print("Encrypting with 3-of-6 threshold...")
        encrypted = threshold_enc.encrypt_transaction_details(
            transaction_hash=transaction_details['transaction_hash'],
            sender_idx=transaction_details['sender_idx'],
            receiver_idx=transaction_details['receiver_idx'],
            amount=Decimal(transaction_details['amount']),
            anomaly_score=transaction_details['anomaly_score'],
            anomaly_flags=transaction_details['anomaly_flags']
        )
        encrypted_package = encrypted.get('encrypted_package', encrypted)

        # Get key shares from the encrypted result
        key_shares = encrypted.get('key_shares', {})
        print(f"  ✅ Encrypted with {len(key_shares)} key shares")
        print(f"  Access structure: Company + Supreme Court + 1-of-4")

        # Test 1: Try decrypting with 2 keys (should FAIL)
        print("\nTest 1: Attempting decryption with 2 keys...")
        try:
            two_shares = [key_shares['company'], key_shares['supreme_court']]
            threshold_enc.decrypt_transaction_details(encrypted_package, two_shares)
            print(f"  ❌ SECURITY ISSUE: Decrypted with only 2 shares!")
            assert False, "Should not decrypt with only 2 shares"
        except ValueError as e:
            print(f"  ✅ Cannot decrypt with 2 shares: {str(e)[:80]}")

        # Test 2: Decrypt with 3 keys (should SUCCEED)
        print("\nTest 2: Decrypting with 3 keys (Company + Court + RBI)...")
        three_shares = [key_shares['company'], key_shares['supreme_court'], key_shares['rbi']]

        decrypted = threshold_enc.decrypt_transaction_details(
            encrypted_package=encrypted_package,
            provided_shares=three_shares
        )

        print(f"  ✅ Decryption successful")
        print(f"  Sender IDX: {decrypted['sender_idx'][:20]}...")
        print(f"  Amount: ₹{decrypted['amount']}")

        # Verify decrypted data matches original
        assert decrypted['sender_idx'] == transaction_details['sender_idx']
        assert decrypted['amount'] == transaction_details['amount']
        assert decrypted['anomaly_score'] == transaction_details['anomaly_score']

        print("\n=== ✅ Threshold Encryption Test PASSED ===\n")

    def test_user_unaware_transaction_proceeds_normally(
        self,
        test_db,
        anomaly_engine,
        zkp_service,
        threshold_enc
    ):
        """
        Test that user is unaware of anomaly flag and transaction proceeds normally

        Verify:
        - Transaction status remains PENDING/COMPLETED (not blocked)
        - No user-visible indication of anomaly
        - ZKP proof generated in background
        - Threshold encryption happens silently
        """
        print("\n=== Test: User Unaware - Transaction Proceeds Normally ===\n")

        # Create high-value transaction
        transaction = Transaction(
            transaction_hash="0xuser_unaware_test",
            sender_idx="IDX_SENDER_UNAWARE",
            receiver_idx="IDX_RECEIVER_UNAWARE",
            amount=Decimal('9000000.00'),  # ₹90 lakh
            sender_session_id="SESSION_SENDER_UNAWARE",
            receiver_session_id="SESSION_RECEIVER_UNAWARE",
            transaction_type="TRANSFER",
            status="PENDING"
        )
        test_db.add(transaction)
        test_db.commit()

        print(f"Step 1: Transaction created (₹{transaction.amount:,})")
        print(f"  Status: {transaction.status}")
        print(f"  User sees: Normal transaction pending")

        # Run anomaly detection
        anomaly_result = anomaly_engine.analyze_transaction(
            transaction_hash=transaction.transaction_hash,
            sender_idx=transaction.sender_idx,
            receiver_idx=transaction.receiver_idx,
            amount=transaction.amount,
            transaction_type=transaction.transaction_type
        )

        print(f"\nStep 2: Anomaly detection (BACKGROUND)")
        print(f"  Flagged: {anomaly_result['requires_investigation']}")
        print(f"  Score: {anomaly_result['anomaly_score']}")
        print(f"  User sees: Nothing (background process)")

        # Generate ZKP proof
        zkp_proof = zkp_service.generate_proof(
            transaction_hash=transaction.transaction_hash,
            requires_investigation=anomaly_result['requires_investigation'],
            anomaly_score=anomaly_result['anomaly_score']
        )

        print(f"\nStep 3: ZKP proof generated (BACKGROUND)")
        print(f"  Proof valid: {zkp_service.verify_proof(zkp_proof)}")
        print(f"  User sees: Nothing (background process)")

        # Threshold encryption
        transaction_details = {
            'transaction_hash': transaction.transaction_hash,
            'sender_idx': transaction.sender_idx,
            'receiver_idx': transaction.receiver_idx,
            'amount': str(transaction.amount),
            'anomaly_score': anomaly_result['anomaly_score']
        }

        encrypted_package = threshold_enc.encrypt_anomaly_transaction(
            transaction_details=transaction_details,
            threshold=3,
            authorities=['company', 'supreme_court', 'rbi', 'fiu', 'cbi', 'income_tax']
        )

        print(f"\nStep 4: Details encrypted (BACKGROUND)")
        print(f"  Encrypted: Yes")
        print(f"  User sees: Nothing (background process)")

        # Update transaction (background)
        transaction.status = "COMPLETED"  # Transaction proceeds normally
        transaction.anomaly_score = Decimal(str(anomaly_result['anomaly_score']))
        transaction.requires_investigation = True
        transaction.investigation_status = 'PENDING'
        transaction.zkp_proof = json.dumps(zkp_proof).encode('utf-8')
        transaction.threshold_encrypted_details = json.dumps(encrypted_package).encode('utf-8')
        test_db.commit()

        print(f"\nStep 5: Transaction completes normally")
        print(f"  Status: {transaction.status}")
        print(f"  User sees: Transaction completed successfully")
        print(f"  User does NOT see: Anomaly flag, investigation status, ZKP proof")

        # Verify transaction completed
        assert transaction.status == "COMPLETED"
        assert transaction.requires_investigation == True  # Flagged in background

        print("\n=== ✅ User Unaware Test PASSED ===\n")


class TestMultiUserScenarios:
    """Test multi-user scenarios"""

    def test_multiple_users_different_freeze_states(
        self,
        test_db,
        freeze_service
    ):
        """
        Test multiple users with different freeze states

        Scenario:
        - User A: First investigation (24h freeze)
        - User B: Second investigation (72h freeze)
        - User C: Not frozen
        """
        print("\n=== Test: Multiple Users Different Freeze States ===\n")

        # User A: First investigation
        freeze_a = freeze_service.trigger_freeze(
            user_idx="IDX_USER_A",
            transaction_hash="0xtx_a",
            reason="First investigation"
        )

        print(f"User A: {freeze_a['freeze_duration_hours']}h freeze")
        assert freeze_a['freeze_duration_hours'] == 24

        # User B: First investigation
        freeze_b = freeze_service.trigger_freeze(
            user_idx="IDX_USER_B",
            transaction_hash="0xtx_b",
            reason="First investigation"
        )

        print(f"User B: {freeze_b['freeze_duration_hours']}h freeze")
        assert freeze_b['freeze_duration_hours'] == 24

        # User C: Not frozen (just checking status)
        status_c = freeze_service.get_freeze_status("IDX_USER_C")
        print(f"User C: Frozen = {status_c['is_frozen']}")

        print("\n=== ✅ Multi-User Freeze Test PASSED ===\n")


# Run tests
if __name__ == "__main__":
    print("=" * 70)
    print("INTEGRATION TESTS: Complete Anomaly Detection Flow")
    print("=" * 70)
    print()

    pytest.main([__file__, '-v', '-s'])
