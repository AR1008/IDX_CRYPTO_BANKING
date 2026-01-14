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
from database.connection import Base


class TravelAccount(Base):
    """Temporary foreign bank account for travel"""
    
    __tablename__ = 'travel_accounts'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Owner
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    
    # Source account (Indian bank)
    source_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=False)
    
    # Foreign bank
    foreign_bank_id = Column(Integer, ForeignKey('foreign_banks.id'), nullable=False)
    foreign_account_number = Column(String(50), unique=True, nullable=False, index=True)
    
    # Currency & Balance
    currency = Column(String(3), nullable=False)  # USD, GBP, EUR
    balance = Column(Numeric(precision=15, scale=2), nullable=False, default=Decimal('0.00'))
    
    # Initial conversion
    initial_inr_amount = Column(Numeric(precision=15, scale=2), nullable=False)  # Amount converted from INR
    initial_forex_rate = Column(Numeric(precision=10, scale=6), nullable=False)  # Exchange rate at creation
    initial_foreign_amount = Column(Numeric(precision=15, scale=2), nullable=False)  # Amount in foreign currency
    forex_fee_paid = Column(Numeric(precision=15, scale=2), nullable=False)  # 0.15% fee
    
    # Final conversion (on closure)
    final_foreign_amount = Column(Numeric(precision=15, scale=2), nullable=True)  # Remaining balance
    final_forex_rate = Column(Numeric(precision=10, scale=6), nullable=True)  # Rate at closure
    final_inr_amount = Column(Numeric(precision=15, scale=2), nullable=True)  # Amount returned to INR
    final_forex_fee_paid = Column(Numeric(precision=15, scale=2), nullable=True)  # Fee on return conversion
    
    # Status
    status = Column(String(20), default='ACTIVE', nullable=False)  # ACTIVE, CLOSED
    is_frozen = Column(Boolean, default=False, nullable=False)
    
    # Duration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Auto-close date
    closed_at = Column(DateTime, nullable=True)
    
    # Closure reason
    closure_reason = Column(Text, nullable=True)  # "Trip ended", "Emergency", etc.
    
    # Timestamps
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_idx])
    source_account = relationship("BankAccount", foreign_keys=[source_account_id])
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