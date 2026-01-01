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

import csv
import io
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple

from database.connection import SessionLocal
from database.models.transaction import Transaction
from database.models.recipient import Recipient
from database.models.bank_account import BankAccount
from database.models.user import User


class StatementService:
    """Generate and verify user transaction statements"""

    def __init__(self, db=None):
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
        # Get user info
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")

        # Get transactions in date range
        transactions = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).order_by(Transaction.created_at.asc()).all()

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
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

        # Transactions
        total_sent = Decimal('0.00')
        total_received = Decimal('0.00')
        opening_balance = self._get_balance_at_date(user_idx, start_date)
        running_balance = opening_balance

        for tx in transactions:
            # Determine direction
            if tx.sender_idx == user_idx:
                direction = "sent"
                counterparty_idx = tx.receiver_idx
                my_account_id = tx.sender_account_id
                amount = tx.amount
                fee = tx.fee
                net_amount = amount + fee
                total_sent += net_amount
                running_balance -= net_amount
            else:
                direction = "received"
                counterparty_idx = tx.sender_idx
                my_account_id = tx.receiver_account_id
                amount = tx.amount
                fee = Decimal('0.00')
                net_amount = amount
                total_received += amount
                running_balance += amount

            # Get nickname
            recipient = self.db.query(Recipient).filter(
                Recipient.user_idx == user_idx,
                Recipient.recipient_idx == counterparty_idx
            ).first()
            nickname = recipient.nickname if recipient else ""

            # Get bank account
            account = self.db.query(BankAccount).get(my_account_id) if my_account_id else None
            bank_account_str = f"{account.bank_code}-{account.account_number}" if account else ""

            # Write row
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

        # Summary rows
        writer.writerow([])  # Blank line
        writer.writerow(['SUMMARY'])
        writer.writerow(['Opening Balance', '', '', '', '', '', f"{opening_balance:.2f}", '', ''])
        writer.writerow(['Total Received', '', '', '', f"{total_received:.2f}", '', '', '', ''])
        writer.writerow(['Total Sent', '', '', '', f"{total_sent:.2f}", '', '', '', ''])
        writer.writerow(['Closing Balance', '', '', '', '', '', f"{running_balance:.2f}", '', ''])
        writer.writerow(['Net Change', '', '', '', '', '', f"{total_received - total_sent:.2f}", '', ''])

        csv_content = output.getvalue()
        output.close()

        # Generate signature
        signature = ""
        if include_signature:
            signature = self._sign_statement(user_idx, start_date, end_date, csv_content)

        return csv_content, signature

    def _get_balance_at_date(self, user_idx: str, date: datetime) -> Decimal:
        """
        Calculate user's total balance at a specific date

        This is approximate - gets current balance and works backwards
        """
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            return Decimal('0.00')

        # Get all transactions after the date
        transactions_after = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at > date,
            Transaction.status == 'completed'
        ).all()

        # Work backwards from current balance
        balance_at_date = user.balance

        for tx in transactions_after:
            if tx.sender_idx == user_idx:
                # User sent money after this date, so add it back
                balance_at_date += (tx.amount + tx.fee)
            else:
                # User received money after this date, so subtract it
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
        from config.settings import settings

        # Build signature data
        sig_data = (
            user_idx +
            start_date.isoformat() +
            end_date.isoformat() +
            content +
            settings.SECRET_KEY  # Secret salt
        )

        # Generate SHA-256 hash
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
        # Recalculate signature
        calculated_signature = self._sign_statement(user_idx, start_date, end_date, content)

        # Compare
        return calculated_signature == provided_signature

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
        # Count transactions
        tx_count = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).count()

        # Calculate totals
        transactions = self.db.query(Transaction).filter(
            ((Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)),
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date,
            Transaction.status == 'completed'
        ).all()

        total_sent = sum(
            (tx.amount + tx.fee) for tx in transactions if tx.sender_idx == user_idx
        )
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
            'net_change': str(total_received - total_sent),
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
