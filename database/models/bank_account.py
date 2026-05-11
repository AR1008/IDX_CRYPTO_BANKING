"""
Bank Account Model
Purpose: User's bank accounts at different banks

A user can have multiple bank accounts:
- HDFC account
- ICICI account
- SBI account
etc.

Each account has:
- Separate balance
- Separate session IDs (24hr rotation)
- Own transaction history
"""

# [DOC] Column types for defining the table's columns in PostgreSQL
from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, DateTime, Boolean
# [DOC] relationship() creates Python-level ORM links; ForeignKey creates the actual DB foreign key constraint
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

# [DOC] Base is the common parent class all ORM models inherit from
from database.connection import Base


class BankAccount(Base):
    """User's bank account at a specific bank"""

    # [DOC] Maps this Python class to the 'bank_accounts' table in PostgreSQL
    __tablename__ = 'bank_accounts'

    # [DOC] id: auto-incrementing integer primary key — the DB's internal row identifier
    id = Column(Integer, primary_key=True, autoincrement=True)

    # [DOC] user_idx: links this account to its owner via the users.idx column (the user's permanent pseudonym)
    # [DOC] index=True: speeds up "give me all accounts for user X" queries performed on every login
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)

    # [DOC] bank_code: short identifier for the bank this account belongs to (e.g. "HDFC", "SBI", "ICICI")
    # [DOC] index=True: speeds up filtering accounts by bank (used during consensus — sender and receiver bank must both approve)
    bank_code = Column(String(10), nullable=False, index=True)

    # [DOC] account_number: unique account number generated at registration; shown to the user as their account identifier
    # [DOC] unique=True: no two accounts can share the same number; index=True for fast lookups
    account_number = Column(String(50), unique=True, nullable=False, index=True)

    # [DOC] balance: current funds in this specific bank account (a user's total wealth is the sum across all their accounts)
    # [DOC] precision=15, scale=2: supports balances up to 9,999,999,999,999.99 (13 digits before decimal)
    balance = Column(Numeric(precision=15, scale=2), nullable=False, default=Decimal('0.00'))

    # [DOC] is_active: False means the account has been closed; inactive accounts cannot send or receive transactions
    is_active = Column(Boolean, default=True, nullable=False)

    # [DOC] is_frozen: True when a court order has legally frozen the account; frozen accounts cannot transact
    # [DOC] Freezing is triggered only by a court order — never automatically by the anomaly detection system
    is_frozen = Column(Boolean, default=False, nullable=False)

    # [DOC] created_at: when this bank account was opened; set once at insert time
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # [DOC] updated_at: refreshed whenever the balance or status changes
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # [DOC] user: ORM back-reference so account.user gives the full User object without an extra query
    user = relationship("User", back_populates="bank_accounts")
    # sessions = relationship("database.models.session.Session", back_populates="bank_account")
    # transactions_sent = relationship("Transaction",
    #                                 foreign_keys="Transaction.sender_account_id",
    #                                 back_populates="sender_account")
    # transactions_received = relationship("Transaction",
    #                                     foreign_keys="Transaction.receiver_account_id",
    #                                     back_populates="receiver_account")

    def __repr__(self):
        return f"<BankAccount {self.bank_code} - {self.account_number} (Balance: {self.balance})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_idx': self.user_idx,
            'bank_code': self.bank_code,
            'account_number': self.account_number,
            # [DOC] str(self.balance): convert Decimal to string for JSON serialisation (JSON has no Decimal type)
            'balance': str(self.balance),
            'is_active': self.is_active,
            'is_frozen': self.is_frozen,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
