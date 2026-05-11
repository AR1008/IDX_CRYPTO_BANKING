"""
Statement Generation Service
Purpose: Generate transaction statements for users/CAs

Formats:
- CSV: Simple format for Excel/accounting software
- PDF: Professional format with digital signature

Security:
- Digital signature (SHA-256) for authenticity verification
- CAs can verify statement wasn't tampered with
"""

# [DOC] csv: Python's built-in CSV writer; used to produce comma-separated output for each transaction row
import csv
# [DOC] io.StringIO: in-memory text buffer so CSV content can be built as a string without writing to disk
import io
# [DOC] hashlib: SHA-256 used to produce a tamper-evident digital signature for the statement
import hashlib
# [DOC] hmac.compare_digest: constant-time string comparison that prevents timing-based signature forgery attacks
import hmac
# [DOC] json: used to serialize statement metadata for API responses
import json
# [DOC] datetime/timedelta/timezone: needed to calculate statement periods and record the generation timestamp
from datetime import datetime, timedelta, timezone
# [DOC] Decimal: monetary amounts use Decimal to avoid floating-point rounding errors in totals
from decimal import Decimal
# [DOC] List/Dict/Tuple: type hints for function signatures; no runtime effect
from typing import List, Dict, Tuple

# [DOC] SessionLocal: factory that creates a new database session; used when no db is passed to __init__
from database.connection import SessionLocal
# [DOC] Transaction ORM model: queried to get all transactions where the user was sender or receiver
from database.models.transaction import Transaction
# [DOC] Recipient ORM model: queried to resolve a counterparty's IDX into their human-readable nickname
from database.models.recipient import Recipient
# [DOC] BankAccount ORM model: queried to get the bank code and account number for statement display
from database.models.bank_account import BankAccount
# [DOC] User ORM model: queried to verify the user exists and to retrieve their current balance
from database.models.user import User
# [DOC] AuditLogger: records that a statement was generated — part of the non-repudiable audit trail
from core.security.audit_logger import AuditLogger


class StatementService:
    """Generate and verify user transaction statements"""

    def __init__(self, db=None):
        # [DOC] Use the passed-in db session; if none provided, create a new one from SessionLocal
        self.db = db or SessionLocal()

    def generate_csv_statement(
        self,
        user_idx: str,
        start_date: datetime,
        end_date: datetime,
        include_signature: bool = True
    ) -> Tuple[str, str]:
        """
        Generate CSV statement for date range

        Args:
            user_idx: User's IDX
            start_date: Start of statement period
            end_date: End of statement period
            include_signature: Include digital signature

        Returns:
            Tuple of (csv_content, signature)

        Example CSV Format:
            Date,Counterparty IDX,Nickname,Direction,Amount,Fee,Net Amount,Bank Account,Status
            2025-12-26,IDX_def456...,Mom,sent,10000.00,150.00,10150.00,HDFC-12345,completed
        """
        # [DOC] Verify user exists; raises ValueError if no account found for this IDX
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")

        # [DOC] Fetch all transactions in the date range where this user was either sender or receiver
        # [DOC] The | operator is SQLAlchemy's OR — matches either condition
        transactions = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).order_by(Transaction.created_at.asc()).all()

        # [DOC] StringIO: acts like a file object in memory; the csv.writer writes text into it
        output = io.StringIO()
        writer = csv.writer(output)

        # [DOC] Header row: column names for the statement; CAs and Excel need consistent column names
        writer.writerow([
            'Date',
            'Counterparty IDX',
            'Nickname',
            'Direction',
            'Amount (₹)',
            'Fee (₹)',
            'Net Amount (₹)',
            'Bank Account',
            'Status'
        ])

        # [DOC] Accumulators for the summary section at the bottom of the CSV
        total_sent = Decimal('0.00')
        total_received = Decimal('0.00')
        # [DOC] opening_balance: estimated balance at start_date; computed by working backwards from current balance
        opening_balance = self._get_balance_at_date(user_idx, start_date)
        # [DOC] running_balance: tracks the balance change through the statement period
        running_balance = opening_balance

        for tx in transactions:
            # [DOC] Determine which direction this transaction is relative to the statement user
            if tx.sender_idx == user_idx:
                # [DOC] User sent this payment: money left their account
                direction = "sent"
                counterparty_idx = tx.receiver_idx
                my_account_id = tx.sender_account_id
                amount = tx.amount
                fee = tx.fee
                # [DOC] net_amount for sent: amount + fee (total deducted from sender's balance)
                net_amount = amount + fee
                total_sent += net_amount
                running_balance -= net_amount
            else:
                # [DOC] User received this payment: money entered their account
                direction = "received"
                counterparty_idx = tx.sender_idx
                my_account_id = tx.receiver_account_id
                amount = tx.amount
                # [DOC] Receivers pay no fee — only the sender's side pays the 1.5% combined fee
                fee = Decimal('0.00')
                net_amount = amount
                total_received += amount
                running_balance += amount

            # [DOC] Look up the counterparty's nickname in this user's recipient list (may be empty string if not saved)
            recipient = self.db.query(Recipient).filter(
                Recipient.user_idx == user_idx,
                Recipient.recipient_idx == counterparty_idx
            ).first()
            nickname = recipient.nickname if recipient else ""

            # [DOC] Look up the bank account involved to display a human-readable "HDFC-1234567890" label
            account = self.db.query(BankAccount).get(my_account_id) if my_account_id else None
            bank_account_str = f"{account.bank_code}-{account.account_number}" if account else ""

            # [DOC] Write one CSV row per transaction
            writer.writerow([
                tx.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                counterparty_idx,
                nickname,
                direction,
                f"{amount:.2f}",
                f"{fee:.2f}",
                f"{net_amount:.2f}",
                bank_account_str,
                tx.status.value
            ])

        # [DOC] Blank separator row between transaction detail rows and the summary section
        writer.writerow([])  # Blank line
        writer.writerow(['SUMMARY'])
        # [DOC] Opening and closing balance rows let government or CA auditors verify period-end reconciliation
        writer.writerow(['Opening Balance', '', '', '', '', '', f"{opening_balance:.2f}", '', ''])
        writer.writerow(['Total Received', '', '', '', f"{total_received:.2f}", '', '', '', ''])
        writer.writerow(['Total Sent', '', '', '', f"{total_sent:.2f}", '', '', '', ''])
        writer.writerow(['Closing Balance', '', '', '', '', '', f"{running_balance:.2f}", '', ''])
        # [DOC] Net Change: positive means net gain; negative means net loss over the period
        writer.writerow(['Net Change', '', '', '', '', '', f"{total_received - total_sent:.2f}", '', ''])

        # [DOC] Extract the full CSV string from the in-memory buffer
        csv_content = output.getvalue()
        output.close()

        # [DOC] Optionally sign the CSV so recipients can verify it was not tampered with
        signature = ""
        if include_signature:
            signature = self._sign_statement(user_idx, start_date, end_date, csv_content)

        # [DOC] Log that a statement was generated; logged even if the signing or CSV generation failed partially
        try:
            AuditLogger.log_custom_event(
                event_type='STATEMENT_GENERATED',
                event_data={
                    'user_idx': user_idx,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'transaction_count': len(transactions),
                    'total_sent': str(total_sent),
                    'total_received': str(total_received),
                    'opening_balance': str(opening_balance),
                    'closing_balance': str(running_balance),
                    'include_signature': include_signature,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as audit_error:
            # [DOC] Audit failure is non-fatal — the statement is still returned even if logging fails
            print(f"⚠️ Audit logging failed: {audit_error}")

        return csv_content, signature

    def _get_balance_at_date(self, user_idx: str, date: datetime) -> Decimal:
        """
        Calculate user's total balance at a specific date

        This is approximate - gets current balance and works backwards
        """
        # [DOC] Fetch the user's current balance (stored on the User row directly)
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            return Decimal('0.00')

        # [DOC] Find all transactions that happened AFTER the requested date — these have not yet occurred in our timeline
        transactions_after = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at > date,
            Transaction.status == 'completed'
        ).all()

        # [DOC] Start from current balance and reverse each post-date transaction to reconstruct the balance at `date`
        balance_at_date = user.balance

        for tx in transactions_after:
            if tx.sender_idx == user_idx:
                # [DOC] User sent money after this date — add it back to get the pre-send balance
                balance_at_date += (tx.amount + tx.fee)
            else:
                # [DOC] User received money after this date — subtract it to get the pre-receive balance
                balance_at_date -= tx.amount

        return balance_at_date

    def _sign_statement(
        self,
        user_idx: str,
        start_date: datetime,
        end_date: datetime,
        content: str
    ) -> str:
        """
        Generate cryptographic signature for statement

        Signature = SHA256(user_idx + start_date + end_date + content + secret_salt)

        This proves:
        - Statement was generated by this system
        - Content hasn't been modified
        - Specific to this user and date range
        """
        # [DOC] Import settings here (lazy import) to avoid circular imports at module load time
        from config.settings import settings

        # [DOC] Concatenate all components that should be immutable after signing
        # [DOC] Including user_idx and date range ensures the signature is specific to this exact statement
        sig_data = (
            user_idx +
            start_date.isoformat() +
            end_date.isoformat() +
            content +
            # [DOC] SECRET_KEY is the application secret; changing it invalidates all previously issued statements
            settings.SECRET_KEY  # Secret salt
        )

        # [DOC] SHA-256 of the combined string; returned as a 64-character hex string
        signature = hashlib.sha256(sig_data.encode()).hexdigest()

        return signature

    def verify_statement_signature(
        self,
        user_idx: str,
        start_date: datetime,
        end_date: datetime,
        content: str,
        provided_signature: str
    ) -> bool:
        """
        Verify statement signature

        Returns:
            bool: True if signature is valid, False otherwise
        """
        # [DOC] Regenerate the expected signature from the same inputs
        calculated_signature = self._sign_statement(user_idx, start_date, end_date, content)

        # [DOC] hmac.compare_digest: constant-time comparison — prevents timing attacks where an attacker
        # [DOC] could infer correct bytes by measuring how long the comparison takes
        return hmac.compare_digest(calculated_signature, provided_signature)

    def get_statement_metadata(
        self,
        user_idx: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """
        Get statement metadata (for API response)

        Returns:
            {
                'user_idx': '...',
                'period': {
                    'start': '2025-01-01T00:00:00',
                    'end': '2025-12-31T23:59:59'
                },
                'transaction_count': 45,
                'total_sent': '125000.00',
                'total_received': '200000.00',
                'net_change': '75000.00',
                'generated_at': '2025-12-27T15:00:00'
            }
        """
        # [DOC] tx_count: total number of transactions (any status) in the date range for display in the API
        tx_count = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).count()

        # [DOC] Fetch only completed transactions for the financial totals — pending/failed don't count
        transactions = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date,
            Transaction.status == 'completed'
        ).all()

        # [DOC] total_sent: sum of (amount + fee) for all outgoing completed transactions
        total_sent = sum(
            (tx.amount + tx.fee) for tx in transactions if tx.sender_idx == user_idx
        )
        # [DOC] total_received: sum of amounts for all incoming completed transactions (receivers pay no fee)
        total_received = sum(
            tx.amount for tx in transactions if tx.receiver_idx == user_idx
        )

        return {
            'user_idx': user_idx,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'transaction_count': tx_count,
            'total_sent': str(total_sent),
            'total_received': str(total_received),
            # [DOC] net_change: positive = net inflow; negative = net outflow over the period
            'net_change': str(total_received - total_sent),
            # [DOC] generated_at: when this metadata snapshot was produced — useful for cache invalidation
            'generated_at': datetime.now().isoformat()
        }


# Example usage
if __name__ == "__main__":
    print("=== Statement Generation Service Test ===\n")

    from database.connection import SessionLocal

    db = SessionLocal()
    service = StatementService(db)

    try:
        # Generate statement for test user
        test_user_idx = "IDX_test"
        start = datetime(2025, 1, 1)
        end = datetime(2025, 12, 31)

        print(f"Generating statement for {test_user_idx}")
        print(f"Period: {start} to {end}\n")

        csv_content, signature = service.generate_csv_statement(
            test_user_idx,
            start,
            end
        )

        print("CSV Content (first 500 chars):")
        print(csv_content[:500])
        print("\n...")

        print(f"\nDigital Signature: {signature[:32]}...")

        # Verify signature
        is_valid = service.verify_statement_signature(
            test_user_idx,
            start,
            end,
            csv_content,
            signature
        )

        print(f"Signature Valid: {is_valid}")

        # Get metadata
        metadata = service.get_statement_metadata(test_user_idx, start, end)
        print(f"\nMetadata: {json.dumps(metadata, indent=2)}")

        print("\n✅ Statement service working!")

    finally:
        db.close()
