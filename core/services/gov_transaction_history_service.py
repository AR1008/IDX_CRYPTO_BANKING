"""
Government Transaction History Service (Restricted Access)
Purpose: Provide restricted transaction history view for government investigations

CRITICAL USER REQUIREMENT:
Government can ONLY see:
✅ Date/time
✅ Amount
✅ Direction (sent or received)
✅ Transaction ID

Government CANNOT see:
❌ Sender session ID
❌ Receiver session ID
❌ Sender IDX
❌ Receiver IDX
❌ Counterparty information

User's Own History (NOT government):
✅ User CAN see session ID/IDX in their own history
✅ User CAN generate PDF statements for CA/tax filing
✅ PDF shows full details (for tax compliance)

Example:
    >>> service = GovTransactionHistoryService(db)
    >>>
    >>> # Government views flagged transactions (restricted)
    >>> history = service.get_flagged_transactions_for_gov(
    ...     limit=100,
    ...     min_score=65.0
    ... )
    >>> # Returns: date/time, amount, direction, tx ID only
    >>>
    >>> # User views their own history (full access)
    >>> user_history = service.get_user_transaction_history(
    ...     user_idx="IDX_USER123"
    ... )
    >>> # Returns: all fields including session IDs, counterparty info
"""

from typing import Dict, List, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from database.models.transaction import Transaction
from database.models.bank_account import BankAccount


class GovTransactionHistoryService:
    """
    Transaction history service with government access restrictions

    Two access levels:
    1. Government: Restricted view (date/time, amount, direction, tx ID only)
    2. User: Full view (all fields including session IDs, counterparty info)
    """

    def __init__(self, db: Session):
        """
        Initialize government transaction history service

        Args:
            db: Database session
        """
        self.db = db

    def get_flagged_transactions_for_gov(
        self,
        limit: int = 100,
        offset: int = 0,
        min_score: Optional[float] = 65.0,
        investigation_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get flagged transactions for government (RESTRICTED ACCESS)

        Government can ONLY see:
        - Date/time
        - Amount
        - Transaction ID
        - Investigation status

        Args:
            limit: Maximum results
            offset: Results offset
            min_score: Minimum anomaly score (default: 65.0)
            investigation_status: Filter by status

        Returns:
            dict: Restricted transaction list

        Example:
            >>> service = GovTransactionHistoryService(db)
            >>> result = service.get_flagged_transactions_for_gov(
            ...     limit=50,
            ...     min_score=70.0
            ... )
            >>> len(result['transactions'])
            15  # 15 transactions with score >= 70
        """
        # Build query
        query = self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        )

        if min_score is not None:
            query = query.filter(Transaction.anomaly_score >= min_score)

        if investigation_status:
            query = query.filter(
                Transaction.investigation_status == investigation_status
            )

        # Order by flagged_at (most recent first)
        query = query.order_by(desc(Transaction.flagged_at))

        # Get total count
        total_count = query.count()

        # Apply pagination
        transactions = query.limit(limit).offset(offset).all()

        # Return ONLY restricted fields
        restricted_transactions = []
        for tx in transactions:
            restricted_transactions.append({
                'transaction_id': tx.transaction_hash,
                'timestamp': tx.created_at.isoformat(),
                'amount': str(tx.amount),
                'anomaly_score': float(tx.anomaly_score) if tx.anomaly_score else 0.0,
                'requires_investigation': tx.requires_investigation,
                'investigation_status': tx.investigation_status,
                'flagged_at': tx.flagged_at.isoformat() if tx.flagged_at else None,
                # NO sender_idx, NO receiver_idx, NO session IDs
            })

        return {
            'total_count': total_count,
            'returned_count': len(restricted_transactions),
            'limit': limit,
            'offset': offset,
            'transactions': restricted_transactions,
            'access_level': 'GOVERNMENT_RESTRICTED',
            'fields_exposed': [
                'transaction_id',
                'timestamp',
                'amount',
                'anomaly_score',
                'investigation_status'
            ]
        }

    def get_transaction_for_gov(
        self,
        transaction_hash: str
    ) -> Dict[str, Any]:
        """
        Get single transaction for government (RESTRICTED ACCESS)

        Args:
            transaction_hash: Transaction hash

        Returns:
            dict: Restricted transaction information

        Example:
            >>> service = GovTransactionHistoryService(db)
            >>> tx = service.get_transaction_for_gov("0xabc123")
            >>> 'sender_idx' in tx
            False  # Sender IDX is NOT exposed
        """
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()

        if not transaction:
            raise ValueError(f"Transaction {transaction_hash} not found")

        # Return ONLY allowed fields
        return {
            'transaction_id': transaction.transaction_hash,
            'timestamp': transaction.created_at.isoformat(),
            'amount': str(transaction.amount),
            'fee': str(transaction.fee),
            'anomaly_score': float(transaction.anomaly_score) if transaction.anomaly_score else 0.0,
            'requires_investigation': transaction.requires_investigation,
            'investigation_status': transaction.investigation_status,
            'flagged_at': transaction.flagged_at.isoformat() if transaction.flagged_at else None,
            'cleared_at': transaction.cleared_at.isoformat() if transaction.cleared_at else None,
            # NO sender_idx, NO receiver_idx, NO session IDs
            'access_level': 'GOVERNMENT_RESTRICTED'
        }

    def get_user_transaction_history(
        self,
        user_idx: str,
        requesting_user_idx: str,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get user's own transaction history (FULL ACCESS)

        Users can see ALL fields in their own history:
        - Session IDs
        - Counterparty IDX
        - All transaction details

        This is for user's own access, NOT for government.

        Args:
            user_idx: User IDX to query
            requesting_user_idx: IDX of the user making the request
            limit: Maximum results
            offset: Results offset

        Returns:
            dict: Full transaction history

        Raises:
            PermissionError: If requesting user is not authorized

        Example:
            >>> service = GovTransactionHistoryService(db)
            >>> history = service.get_user_transaction_history(
            ...     user_idx="IDX_USER123",
            ...     requesting_user_idx="IDX_USER123"
            ... )
            >>> history['transactions'][0].keys()
            dict_keys(['transaction_id', 'timestamp', 'amount', 'sender_idx',
                      'receiver_idx', 'sender_session_id', 'receiver_session_id', ...])
        """
        # CRITICAL: Authorization check
        if requesting_user_idx != user_idx:
            raise PermissionError(
                f"User {requesting_user_idx} not authorized to access "
                f"transaction history for {user_idx}"
            )

        # Get transactions where user is sender or receiver
        query = self.db.query(Transaction).filter(
            or_(
                Transaction.sender_idx == user_idx,
                Transaction.receiver_idx == user_idx
            )
        ).order_by(desc(Transaction.created_at))

        total_count = query.count()
        transactions = query.limit(limit).offset(offset).all()

        # Return FULL details (for user's own access)
        full_transactions = []
        for tx in transactions:
            direction = 'SENT' if tx.sender_idx == user_idx else 'RECEIVED'

            full_transactions.append({
                'transaction_id': tx.transaction_hash,
                'timestamp': tx.created_at.isoformat(),
                'direction': direction,
                'amount': str(tx.amount),
                'fee': str(tx.fee),
                # User CAN see session IDs in their own history
                'sender_session_id': tx.sender_session_id,
                'receiver_session_id': tx.receiver_session_id,
                # User CAN see counterparty IDX
                'sender_idx': tx.sender_idx,
                'receiver_idx': tx.receiver_idx,
                'status': tx.status.value if hasattr(tx.status, 'value') else tx.status,
                # Full details available
            })

        return {
            'user_idx': user_idx,
            'total_count': total_count,
            'returned_count': len(full_transactions),
            'limit': limit,
            'offset': offset,
            'transactions': full_transactions,
            'access_level': 'USER_FULL_ACCESS',
            'can_generate_pdf': True,  # For CA/tax filing
        }

    def generate_pdf_statement_for_user(
        self,
        user_idx: str,
        requesting_user_idx: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate PDF statement for user (for CA/tax filing)

        PDF includes FULL transaction details:
        - All session IDs
        - All IDXs
        - Counterparty information
        - Full amounts and fees

        This is for tax compliance and can be shared with CA/auditors.

        Args:
            user_idx: User IDX to generate statement for
            requesting_user_idx: IDX of the user making the request
            start_date: Statement start date
            end_date: Statement end date

        Returns:
            dict: Statement data for PDF generation

        Raises:
            PermissionError: If requesting user is not authorized

        Example:
            >>> service = GovTransactionHistoryService(db)
            >>> statement = service.generate_pdf_statement_for_user(
            ...     user_idx="IDX_USER123",
            ...     requesting_user_idx="IDX_USER123",
            ...     start_date=datetime(2026, 1, 1),
            ...     end_date=datetime(2026, 1, 31)
            ... )
            >>> statement['purpose']
            'TAX_FILING_CA_AUDITOR'
        """
        # CRITICAL: Authorization check
        if requesting_user_idx != user_idx:
            raise PermissionError(
                f"User {requesting_user_idx} not authorized to generate "
                f"PDF statement for {user_idx}"
            )

        # Set default dates if not provided
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=365)  # Last 1 year

        # Get all transactions in date range
        transactions = self.db.query(Transaction).filter(
            or_(
                Transaction.sender_idx == user_idx,
                Transaction.receiver_idx == user_idx
            ),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).order_by(Transaction.created_at).all()

        # Prepare full statement data
        statement_data = {
            'user_idx': user_idx,
            'statement_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'purpose': 'TAX_FILING_CA_AUDITOR',
            'access_level': 'USER_FULL_ACCESS',
            'transaction_count': len(transactions),
            'transactions': []
        }

        # Include FULL transaction details for tax purposes
        for tx in transactions:
            direction = 'SENT' if tx.sender_idx == user_idx else 'RECEIVED'

            statement_data['transactions'].append({
                'date': tx.created_at.date().isoformat(),
                'time': tx.created_at.time().isoformat(),
                'transaction_id': tx.transaction_hash,
                'direction': direction,
                'amount': str(tx.amount),
                'fee': str(tx.fee),
                # FULL details for tax compliance
                'sender_session_id': tx.sender_session_id,
                'receiver_session_id': tx.receiver_session_id,
                'sender_idx': tx.sender_idx,
                'receiver_idx': tx.receiver_idx,
                'status': tx.status.value if hasattr(tx.status, 'value') else tx.status,
            })

        return statement_data


# Testing
if __name__ == "__main__":
    """
    Test Government Transaction History Service
    Run: python3 -m core.services.gov_transaction_history_service
    """
    print("=== Government Transaction History Service Testing ===\n")

    # Mock database
    class MockTransaction:
        def __init__(self, idx):
            self.transaction_hash = f"0xtx{idx}"
            self.created_at = datetime.now(timezone.utc) - timedelta(days=idx)
            self.amount = Decimal('5000000.00')
            self.fee = Decimal('75000.00')
            self.anomaly_score = Decimal('75.0')
            self.requires_investigation = True
            self.investigation_status = 'PENDING'
            self.flagged_at = datetime.now(timezone.utc) - timedelta(days=idx)
            self.cleared_at = None
            self.sender_idx = "IDX_SENDER_abc123"
            self.receiver_idx = "IDX_RECEIVER_xyz789"
            self.sender_session_id = "SES_SENDER_001"
            self.receiver_session_id = "SES_RECEIVER_002"
            self.status = "COMPLETED"

    class MockQuery:
        def __init__(self, data):
            self.data = data

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def count(self):
            return len(self.data)

        def limit(self, n):
            self.data = self.data[:n]
            return self

        def offset(self, n):
            self.data = self.data[n:]
            return self

        def all(self):
            return self.data

        def first(self):
            return self.data[0] if self.data else None

    class MockDB:
        def query(self, model):
            # Return mock transactions
            return MockQuery([MockTransaction(i) for i in range(5)])

    db = MockDB()
    service = GovTransactionHistoryService(db)

    # Test 1: Get flagged transactions for government (RESTRICTED)
    print("Test 1: Get Flagged Transactions for Government (RESTRICTED)")
    result = service.get_flagged_transactions_for_gov(limit=10, min_score=65.0)

    print(f"  Total count: {result['total_count']}")
    print(f"  Returned: {result['returned_count']}")
    print(f"  Access level: {result['access_level']}")
    print(f"  Fields exposed: {result['fields_exposed']}")

    if result['transactions']:
        tx = result['transactions'][0]
        print(f"\n  Sample transaction:")
        print(f"    Transaction ID: {tx['transaction_id']}")
        print(f"    Timestamp: {tx['timestamp']}")
        print(f"    Amount: ₹{tx['amount']}")
        print(f"    Anomaly score: {tx['anomaly_score']}")

        # Verify NO sensitive data
        assert 'sender_idx' not in tx
        assert 'receiver_idx' not in tx
        assert 'sender_session_id' not in tx
        assert 'receiver_session_id' not in tx
        print(f"\n  ✅ NO sensitive data exposed (sender/receiver IDX, session IDs)")

    print("  ✅ Test 1 passed!\n")

    # Test 2: Get single transaction for government (RESTRICTED)
    print("Test 2: Get Single Transaction for Government (RESTRICTED)")
    tx_info = service.get_transaction_for_gov("0xtx0")

    print(f"  Transaction ID: {tx_info['transaction_id']}")
    print(f"  Amount: ₹{tx_info['amount']}")
    print(f"  Access level: {tx_info['access_level']}")

    # Verify NO sensitive data
    assert 'sender_idx' not in tx_info
    assert 'receiver_idx' not in tx_info
    assert 'sender_session_id' not in tx_info
    assert 'receiver_session_id' not in tx_info
    print(f"  ✅ NO sensitive data exposed")
    print("  ✅ Test 2 passed!\n")

    # Test 3: Get user's own transaction history (FULL ACCESS)
    print("Test 3: Get User's Own Transaction History (FULL ACCESS)")
    user_history = service.get_user_transaction_history(
        user_idx="IDX_USER123",
        requesting_user_idx="IDX_USER123",
        limit=10
    )

    print(f"  User: {user_history['user_idx']}")
    print(f"  Total count: {user_history['total_count']}")
    print(f"  Access level: {user_history['access_level']}")
    print(f"  Can generate PDF: {user_history['can_generate_pdf']}")

    if user_history['transactions']:
        user_tx = user_history['transactions'][0]
        print(f"\n  Sample transaction:")
        print(f"    Transaction ID: {user_tx['transaction_id']}")
        print(f"    Direction: {user_tx['direction']}")
        print(f"    Amount: ₹{user_tx['amount']}")

        # Verify FULL data available for user
        assert 'sender_idx' in user_tx
        assert 'receiver_idx' in user_tx
        assert 'sender_session_id' in user_tx
        assert 'receiver_session_id' in user_tx
        print(f"\n  ✅ FULL data available (session IDs, IDXs, counterparty info)")

    print("  ✅ Test 3 passed!\n")

    # Test 4: Generate PDF statement for user (TAX FILING)
    print("Test 4: Generate PDF Statement for User (TAX FILING)")
    statement = service.generate_pdf_statement_for_user(
        user_idx="IDX_USER123",
        requesting_user_idx="IDX_USER123",
        start_date=datetime.now(timezone.utc) - timedelta(days=30)
    )

    print(f"  User: {statement['user_idx']}")
    print(f"  Purpose: {statement['purpose']}")
    print(f"  Transaction count: {statement['transaction_count']}")
    print(f"  Access level: {statement['access_level']}")

    if statement['transactions']:
        stmt_tx = statement['transactions'][0]
        print(f"\n  Sample transaction in statement:")
        print(f"    Date: {stmt_tx['date']}")
        print(f"    Direction: {stmt_tx['direction']}")
        print(f"    Amount: ₹{stmt_tx['amount']}")

        # Verify FULL data for tax purposes
        assert 'sender_session_id' in stmt_tx
        assert 'receiver_session_id' in stmt_tx
        print(f"\n  ✅ FULL details for CA/tax filing")

    print("  ✅ Test 4 passed!\n")

    print("=" * 50)
    print("✅ All Government Transaction History tests passed!")
    print("=" * 50)
    print()
    print("Access Levels Summary:")
    print()
    print("1. GOVERNMENT (RESTRICTED):")
    print("   ✅ Can see: date/time, amount, tx ID, investigation status")
    print("   ❌ CANNOT see: sender/receiver IDX, session IDs")
    print()
    print("2. USER (FULL ACCESS):")
    print("   ✅ Can see: ALL fields including session IDs, IDXs")
    print("   ✅ Can generate PDF statements for CA/tax filing")
    print("   ✅ PDF includes full transaction details")
    print()
    print("Privacy Protection:")
    print("  • Government has limited view (investigation only)")
    print("  • User maintains full access to their own data")
    print("  • Tax compliance preserved (PDF with full details)")
    print()
