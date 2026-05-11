# [DOC] FILE: core/services/gov_transaction_history_service.py
# [DOC] PURPOSE: Provide two access tiers to transaction history:
# [DOC]   1. GOVERNMENT (restricted): only date/time, amount, tx_id, investigation status.
# [DOC]      No identity fields are returned — sender and receiver remain anonymous.
# [DOC]   2. USER (full): all fields including session IDs and counterparty IDX.
# [DOC]      Users can generate PDF statements for CA / tax filing.
# [DOC]
# [DOC] WHY TWO TIERS?
# [DOC]   The privacy model: the government may observe that a flagged transaction
# [DOC]   EXISTS and SEE its amount, but cannot identify the parties without a
# [DOC]   court order. This service enforces that boundary in code.
# [DOC]
# [DOC] GOVERNMENT ACCESS SCOPE:
# [DOC]   - get_flagged_transactions_for_gov(): list of anomaly-flagged txns (restricted view)
# [DOC]   - get_transaction_for_gov(hash): single txn restricted view
# [DOC]
# [DOC] USER ACCESS SCOPE:
# [DOC]   - get_user_transaction_history(idx): own txns, full details
# [DOC]   - generate_pdf_statement_for_user(idx): date-range statement for CA
# [DOC]
# [DOC] AUTHORIZATION: get_user_transaction_history() and generate_pdf_statement_for_user()
# [DOC]   check that requesting_user_idx == user_idx; mismatches raise PermissionError.
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

# [DOC] Typing helpers for annotated return types
from typing import Dict, List, Any, Optional
# [DOC] Decimal: monetary amounts for statement totals
from decimal import Decimal
# [DOC] datetime/timedelta/timezone: default date ranges and timestamp formatting
from datetime import datetime, timedelta, timezone
# [DOC] Session: SQLAlchemy session type
from sqlalchemy.orm import Session
# [DOC] and_/or_/desc: SQLAlchemy query operators
# [DOC]   or_: "WHERE sender_idx = X OR receiver_idx = X"
# [DOC]   desc: ORDER BY created_at DESC (newest first)
from sqlalchemy import and_, or_, desc

# [DOC] ORM models used in queries
from database.models.transaction import Transaction
from database.models.bank_account import BankAccount


class GovTransactionHistoryService:
    # [DOC] Stateful service — holds a DB session injected at construction time.
    """
    Transaction history service with government access restrictions

    Two access levels:
    1. Government: Restricted view (date/time, amount, direction, tx ID only)
    2. User: Full view (all fields including session IDs, counterparty info)
    """

    def __init__(self, db: Session):
        # [DOC] db: SQLAlchemy session; shared with the caller's unit-of-work
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
        # [DOC] Returns a paginated list of anomaly-flagged transactions with RESTRICTED fields only.
        # [DOC]
        # [DOC] QUERY LOGIC:
        # [DOC]   WHERE requires_investigation = True
        # [DOC]     AND anomaly_score >= min_score (default 65 — the flag threshold)
        # [DOC]     [AND investigation_status = ... (optional filter)]
        # [DOC]   ORDER BY flagged_at DESC
        # [DOC]   LIMIT limit OFFSET offset
        # [DOC]
        # [DOC] PRIVACY: only allowed fields are added to the response dict.
        # [DOC]   sender_idx, receiver_idx, and session IDs are deliberately NOT included.
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
        # [DOC] Base filter: only flagged transactions
        query = self.db.query(Transaction).filter(
            Transaction.requires_investigation == True
        )

        # [DOC] Optional score filter: government can narrow to high-confidence anomalies
        if min_score is not None:
            query = query.filter(Transaction.anomaly_score >= min_score)

        # [DOC] Optional status filter: e.g., show only 'PENDING' investigations
        if investigation_status:
            query = query.filter(
                Transaction.investigation_status == investigation_status
            )

        # [DOC] Order newest-flagged-first so the most recent alerts appear at the top
        query = query.order_by(desc(Transaction.flagged_at))

        # [DOC] Get total count BEFORE pagination for the response metadata
        total_count = query.count()

        # [DOC] Apply pagination: limit + offset for page-based navigation
        transactions = query.limit(limit).offset(offset).all()

        # [DOC] Construct restricted dicts — deliberately enumerate only allowed fields
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
            'access_level': 'GOVERNMENT_RESTRICTED',    # [DOC] Explicit access level for logging
            'fields_exposed': [                          # [DOC] Machine-readable list for audit
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
        # [DOC] Single-transaction view for government — same restricted field set as above.
        # [DOC]   Also returns fee and cleared_at for a slightly richer but still safe view.
        # [DOC] Raises ValueError if the transaction is not found.
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

        # [DOC] Return only allowed fields; identity fields are deliberately excluded
        return {
            'transaction_id': transaction.transaction_hash,
            'timestamp': transaction.created_at.isoformat(),
            'amount': str(transaction.amount),
            'fee': str(transaction.fee),               # [DOC] Total fee (miner + bank) is public
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
        # [DOC] Full transaction history for a user viewing THEIR OWN account.
        # [DOC]
        # [DOC] AUTHORIZATION: requesting_user_idx must exactly match user_idx.
        # [DOC]   This prevents one user from reading another's history.
        # [DOC]   Raises PermissionError on mismatch.
        # [DOC]
        # [DOC] QUERY: WHERE sender_idx = user_idx OR receiver_idx = user_idx
        # [DOC]   ORDER BY created_at DESC  (newest first)
        # [DOC]
        # [DOC] FULL FIELDS RETURNED:
        # [DOC]   sender_session_id, receiver_session_id, sender_idx, receiver_idx, direction, etc.
        # [DOC]   This is for the user's own portal — they are entitled to see their own data.
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
        # [DOC] CRITICAL authorization gate — must come before any DB query
        if requesting_user_idx != user_idx:
            raise PermissionError(
                f"User {requesting_user_idx} not authorized to access "
                f"transaction history for {user_idx}"
            )

        # [DOC] or_() generates: WHERE sender_idx = ? OR receiver_idx = ?
        # [DOC]   This captures both sent and received transactions in one query.
        query = self.db.query(Transaction).filter(
            or_(
                Transaction.sender_idx == user_idx,
                Transaction.receiver_idx == user_idx
            )
        ).order_by(desc(Transaction.created_at))

        total_count = query.count()
        transactions = query.limit(limit).offset(offset).all()

        full_transactions = []
        for tx in transactions:
            # [DOC] direction: SENT if this user initiated the transaction; RECEIVED otherwise
            direction = 'SENT' if tx.sender_idx == user_idx else 'RECEIVED'

            full_transactions.append({
                'transaction_id': tx.transaction_hash,
                'timestamp': tx.created_at.isoformat(),
                'direction': direction,
                'amount': str(tx.amount),
                'fee': str(tx.fee),
                # [DOC] Session IDs: publicly rotating identifiers on the blockchain
                'sender_session_id': tx.sender_session_id,
                'receiver_session_id': tx.receiver_session_id,
                # [DOC] IDX values: semi-public permanent pseudonyms
                'sender_idx': tx.sender_idx,
                'receiver_idx': tx.receiver_idx,
                # [DOC] .value: TransactionStatus is an Enum; .value gives the string representation
                'status': tx.status.value if hasattr(tx.status, 'value') else tx.status,
            })

        return {
            'user_idx': user_idx,
            'total_count': total_count,
            'returned_count': len(full_transactions),
            'limit': limit,
            'offset': offset,
            'transactions': full_transactions,
            'access_level': 'USER_FULL_ACCESS',     # [DOC] Distinguish from gov restricted access
            'can_generate_pdf': True,               # [DOC] User can request a PDF statement
        }

    def generate_pdf_statement_for_user(
        self,
        user_idx: str,
        requesting_user_idx: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        # [DOC] Generate a complete statement suitable for sharing with a CA or tax authority.
        # [DOC]
        # [DOC] AUTHORIZATION: same check as get_user_transaction_history().
        # [DOC]
        # [DOC] DATE DEFAULTS:
        # [DOC]   end_date defaults to now; start_date defaults to end_date - 365 days.
        # [DOC]   This gives a one-year statement by default.
        # [DOC]
        # [DOC] FULL FIELDS: The PDF includes session IDs and IDX values because
        # [DOC]   a CA needs to verify that claimed transfers actually occurred
        # [DOC]   on the IDX blockchain system.
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
        # [DOC] Authorization check — same pattern as get_user_transaction_history()
        if requesting_user_idx != user_idx:
            raise PermissionError(
                f"User {requesting_user_idx} not authorized to generate "
                f"PDF statement for {user_idx}"
            )

        # [DOC] Set default date range: last 365 days if not specified
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        # [DOC] Query: all transactions in the date range where user is sender or receiver.
        # [DOC]   ORDER BY created_at ASC (oldest first) for a chronological statement.
        transactions = self.db.query(Transaction).filter(
            or_(
                Transaction.sender_idx == user_idx,
                Transaction.receiver_idx == user_idx
            ),
            Transaction.created_at >= start_date,    # [DOC] Inclusive lower bound
            Transaction.created_at <= end_date       # [DOC] Inclusive upper bound
        ).order_by(Transaction.created_at).all()

        # [DOC] Build the statement envelope with metadata for the PDF renderer
        statement_data = {
            'user_idx': user_idx,
            'statement_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'purpose': 'TAX_FILING_CA_AUDITOR',      # [DOC] Machine-readable purpose tag
            'access_level': 'USER_FULL_ACCESS',
            'transaction_count': len(transactions),
            'transactions': []
        }

        # [DOC] Include FULL details for each transaction so the CA can cross-reference
        for tx in transactions:
            direction = 'SENT' if tx.sender_idx == user_idx else 'RECEIVED'

            statement_data['transactions'].append({
                'date': tx.created_at.date().isoformat(),   # [DOC] Date part only (YYYY-MM-DD)
                'time': tx.created_at.time().isoformat(),   # [DOC] Time part only (HH:MM:SS)
                'transaction_id': tx.transaction_hash,
                'direction': direction,
                'amount': str(tx.amount),
                'fee': str(tx.fee),
                # [DOC] Full session IDs and IDX values for CA verification
                'sender_session_id': tx.sender_session_id,
                'receiver_session_id': tx.receiver_session_id,
                'sender_idx': tx.sender_idx,
                'receiver_idx': tx.receiver_idx,
                'status': tx.status.value if hasattr(tx.status, 'value') else tx.status,
            })

        return statement_data


# [DOC] Self-test block — runs only when script is executed directly.
# Testing
if __name__ == "__main__":
    """
    Test Government Transaction History Service
    Run: python3 -m core.services.gov_transaction_history_service
    """
    print("=== Government Transaction History Service Testing ===\n")

    # [DOC] MockTransaction: in-memory stub mimicking the Transaction ORM model fields
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

    # [DOC] MockQuery: chainable stub that simulates SQLAlchemy query builder
    class MockQuery:
        def __init__(self, data):
            self.data = data

        def filter(self, *args):
            return self   # [DOC] Return self for method chaining

        def order_by(self, *args):
            return self

        def count(self):
            return len(self.data)

        def limit(self, n):
            self.data = self.data[:n]   # [DOC] Simulate SQL LIMIT
            return self

        def offset(self, n):
            self.data = self.data[n:]   # [DOC] Simulate SQL OFFSET
            return self

        def all(self):
            return self.data

        def first(self):
            return self.data[0] if self.data else None

    # [DOC] MockDB: returns a MockQuery pre-loaded with 5 MockTransaction objects
    class MockDB:
        def query(self, model):
            return MockQuery([MockTransaction(i) for i in range(5)])

    db = MockDB()
    service = GovTransactionHistoryService(db)

    # [DOC] Test 1: Government restricted view — assert NO identity fields in response
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

        # [DOC] Critical assertions: identity fields must NOT be present
        assert 'sender_idx' not in tx
        assert 'receiver_idx' not in tx
        assert 'sender_session_id' not in tx
        assert 'receiver_session_id' not in tx
        print(f"\n  ✅ NO sensitive data exposed (sender/receiver IDX, session IDs)")

    print("  ✅ Test 1 passed!\n")

    # [DOC] Test 2: Single-transaction government view — same restricted fields
    print("Test 2: Get Single Transaction for Government (RESTRICTED)")
    tx_info = service.get_transaction_for_gov("0xtx0")

    print(f"  Transaction ID: {tx_info['transaction_id']}")
    print(f"  Amount: ₹{tx_info['amount']}")
    print(f"  Access level: {tx_info['access_level']}")

    assert 'sender_idx' not in tx_info
    assert 'receiver_idx' not in tx_info
    assert 'sender_session_id' not in tx_info
    assert 'receiver_session_id' not in tx_info
    print(f"  ✅ NO sensitive data exposed")
    print("  ✅ Test 2 passed!\n")

    # [DOC] Test 3: User full access — assert ALL identity fields ARE present
    print("Test 3: Get User's Own Transaction History (FULL ACCESS)")
    user_history = service.get_user_transaction_history(
        user_idx="IDX_USER123",
        requesting_user_idx="IDX_USER123",  # [DOC] Must match user_idx
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

        # [DOC] Full access: identity fields MUST be present
        assert 'sender_idx' in user_tx
        assert 'receiver_idx' in user_tx
        assert 'sender_session_id' in user_tx
        assert 'receiver_session_id' in user_tx
        print(f"\n  ✅ FULL data available (session IDs, IDXs, counterparty info)")

    print("  ✅ Test 3 passed!\n")

    # [DOC] Test 4: PDF statement — assert full fields present for CA use
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

        # [DOC] Full fields must be present for CA verification
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
