"""
Travel Account Model
Purpose: Temporary foreign bank accounts for international travel

Travel Account Lifecycle:
1. User creates travel account before trip
2. Money converted from INR → Foreign currency (0.15% forex fee)
3. Account active for trip duration (30-90 days)
4. User makes transactions in foreign currency
5. User closes account after trip
6. Remaining balance converted back to INR
7. Account status = CLOSED, history preserved

Example:
    # Before USA trip
    travel_account = create_travel_account(
        user_idx="IDX_abc123...",
        source_account=hdfc_account,
        foreign_bank="CITI_USA",
        amount=100000,  # ₹1 lakh
        duration_days=30
    )
    # Converts ₹100,000 → $1,200 USD (minus 0.15% fee)
    
    # After trip
    close_travel_account(travel_account.id)
    # Converts remaining $200 → ₹16,500 back to HDFC
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from decimal import Decimal
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one temporary foreign-currency account opened for an international trip
# [DOC] Lifecycle: user converts INR → foreign currency at open; spends abroad; remaining balance converts back at close
class TravelAccount(Base):
    """Temporary foreign bank account for travel"""

    # [DOC] Maps this Python class to the 'travel_accounts' PostgreSQL table
    __tablename__ = 'travel_accounts'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Owner
    # [DOC] IDX pseudonym of the user who owns this travel account; foreign key to users.idx
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)

    # Source account (Indian bank)
    # [DOC] The user's domestic bank_accounts.id from which INR was debited to fund this travel account
    source_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=False)

    # Foreign bank
    # [DOC] Which foreign correspondent bank hosts this account; foreign key to foreign_banks.id
    foreign_bank_id = Column(Integer, ForeignKey('foreign_banks.id'), nullable=False)
    # [DOC] Account number at the foreign bank, e.g. "CITI_USA_20260301_abc123"; globally unique
    foreign_account_number = Column(String(50), unique=True, nullable=False, index=True)

    # Currency & Balance
    # [DOC] ISO 4217 3-letter currency code for this account, e.g. "USD", "GBP", "EUR"; set at creation and never changes
    currency = Column(String(3), nullable=False)  # USD, GBP, EUR
    # [DOC] Current balance in the foreign currency; decremented on each spending transaction, never goes negative
    balance = Column(Numeric(precision=15, scale=2), nullable=False, default=Decimal('0.00'))

    # Initial conversion
    # [DOC] Amount of INR debited from the user's domestic account to fund this travel account (before fee)
    initial_inr_amount = Column(Numeric(precision=15, scale=2), nullable=False)  # Amount converted from INR
    # [DOC] Exchange rate (INR per 1 unit of foreign currency) at the moment the account was opened; locked for audit
    initial_forex_rate = Column(Numeric(precision=10, scale=6), nullable=False)  # Exchange rate at creation
    # [DOC] Amount in foreign currency credited to the account = (initial_inr_amount - forex_fee_paid) / initial_forex_rate
    initial_foreign_amount = Column(Numeric(precision=15, scale=2), nullable=False)  # Amount in foreign currency
    # [DOC] Forex conversion fee charged at account opening = 0.15% of initial_inr_amount; recorded for transparency
    forex_fee_paid = Column(Numeric(precision=15, scale=2), nullable=False)  # 0.15% fee

    # Final conversion (on closure)
    # [DOC] The foreign currency balance remaining when the account was closed; NULL until closure
    final_foreign_amount = Column(Numeric(precision=15, scale=2), nullable=True)  # Remaining balance
    # [DOC] Exchange rate at time of closure; may differ from initial_forex_rate due to market movement
    final_forex_rate = Column(Numeric(precision=10, scale=6), nullable=True)  # Rate at closure
    # [DOC] INR credited back to source_account = final_foreign_amount × final_forex_rate - final_forex_fee_paid
    final_inr_amount = Column(Numeric(precision=15, scale=2), nullable=True)  # Amount returned to INR
    # [DOC] Forex conversion fee charged at closure = 0.15% of the INR equivalent of the remaining balance
    final_forex_fee_paid = Column(Numeric(precision=15, scale=2), nullable=True)  # Fee on return conversion

    # Status
    # [DOC] "ACTIVE": account is open and the user can spend from it; "CLOSED": account has been closed and balance returned
    status = Column(String(20), default='ACTIVE', nullable=False)  # ACTIVE, CLOSED
    # [DOC] True if this travel account has been frozen by a court order; spending is blocked while frozen
    is_frozen = Column(Boolean, default=False, nullable=False)

    # Duration
    # [DOC] UTC datetime when the account was created and the initial INR→foreign conversion was executed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] UTC datetime when the account will auto-close; set to created_at + trip duration (30–90 days)
    # [DOC] If still active at this timestamp, a background worker closes the account and returns remaining balance
    expires_at = Column(DateTime, nullable=False)  # Auto-close date
    # [DOC] UTC datetime when the account was actually closed (manual or auto); NULL until closure
    closed_at = Column(DateTime, nullable=True)

    # Closure reason
    # [DOC] Human-readable reason for closure, e.g. "Trip ended", "Emergency closure", "Expired"; stored for audit trail
    closure_reason = Column(Text, nullable=True)  # "Trip ended", "Emergency", etc.

    # Timestamps
    # [DOC] Auto-updated by the DB whenever any field changes; mainly updates when balance changes on spending
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # [DOC] ORM relationship to the User row that owns this account
    user = relationship("User", foreign_keys=[user_idx])
    # [DOC] ORM relationship to the domestic BankAccount that funded this travel account
    source_account = relationship("BankAccount", foreign_keys=[source_account_id])
    # [DOC] ORM relationship to the ForeignBank row hosting this account; enables account.foreign_bank.currency lookups
    foreign_bank = relationship("ForeignBank", back_populates="travel_accounts")
    
    def __repr__(self):
        return f"<TravelAccount {self.foreign_account_number} ({self.currency} {self.balance}) - {self.status}>"
    
    def is_expired(self):
        """Check if account expired"""
        return datetime.utcnow() >= self.expires_at
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_idx': self.user_idx,
            'foreign_account_number': self.foreign_account_number,
            'currency': self.currency,
            'balance': str(self.balance),
            'status': self.status,
            'is_frozen': self.is_frozen,
            'initial_inr_amount': str(self.initial_inr_amount),
            'initial_forex_rate': str(self.initial_forex_rate),
            'forex_fee_paid': str(self.forex_fee_paid),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'is_expired': self.is_expired()
        }