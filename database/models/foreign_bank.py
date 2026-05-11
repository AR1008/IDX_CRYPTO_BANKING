"""
Foreign Bank Model
Purpose: International partner banks for travel accounts

Foreign banks:
- Located in different countries
- Partner with Indian consortium banks
- Support temporary travel accounts
- Handle forex conversions

Example Foreign Banks:
- Citibank (USA)
- HSBC (UK)
- Deutsche Bank (Germany)
- DBS Bank (Singapore)
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one foreign correspondent bank that hosts travel accounts for cross-border transactions
class ForeignBank(Base):
    """Foreign bank for international transactions"""

    # [DOC] Maps this Python class to the 'foreign_banks' PostgreSQL table
    __tablename__ = 'foreign_banks'

    # Primary key
    # [DOC] Auto-incrementing integer; referenced by travel_accounts.foreign_bank_id
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Bank identification
    # [DOC] Short unique code combining bank and country, e.g. "CITI_USA" or "HSBC_UK"
    # [DOC] Used in travel account creation to select the destination bank
    bank_code = Column(String(20), unique=True, nullable=False, index=True)  # CITI_USA, HSBC_UK
    # [DOC] Full legal name of the foreign bank, e.g. "Citibank N.A." — shown in API responses and receipts
    bank_name = Column(String(255), nullable=False)  # Citibank USA

    # Location
    # [DOC] Full country name, e.g. "United States" — used for display and jurisdiction checks
    country = Column(String(100), nullable=False)  # United States
    # [DOC] ISO 3166-1 alpha-3 country code, e.g. "USA", "GBR", "DEU" — used for forex rate lookups
    country_code = Column(String(3), nullable=False, index=True)  # USA, GBR, DEU
    # [DOC] ISO 4217 3-letter currency code, e.g. "USD", "GBP", "EUR" — determines which forex_rate row to use
    currency = Column(String(3), nullable=False)  # USD, GBP, EUR

    # Partnership
    # [DOC] Comma-separated list of consortium bank codes that have a correspondent relationship with this foreign bank
    # [DOC] Example: "HDFC,ICICI,SBI" — only these banks can route travel account transactions through this foreign bank
    partner_indian_banks = Column(String(500), nullable=True)  # "HDFC,ICICI,SBI" (comma-separated)
    # [DOC] False means this bank is temporarily suspended and cannot accept new travel accounts
    is_active = Column(Boolean, default=True, nullable=False)

    # Stake (for consensus - like Indian banks)
    # [DOC] Stake posted by this foreign bank as a security deposit; can be slashed for misbehavior during cross-border consensus
    stake_amount = Column(Numeric(precision=15, scale=2), default=Decimal('100000000.00'))

    # Fees
    # [DOC] Cumulative fees earned by this bank from forex conversions (0.15% per travel account open/close)
    total_fees_earned = Column(Numeric(precision=15, scale=2), default=Decimal('0.00'))

    # Timestamps
    # [DOC] UTC datetime when this bank was registered in the system
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] Auto-updated whenever any field changes; used to detect stale or recently modified records
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # [DOC] ORM relationship to all TravelAccount rows that use this foreign bank; enables bank.travel_accounts lookups
    travel_accounts = relationship("TravelAccount", back_populates="foreign_bank")
    
    def __repr__(self):
        return f"<ForeignBank {self.bank_code} - {self.bank_name} ({self.currency})>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'country': self.country,
            'country_code': self.country_code,
            'currency': self.currency,
            'is_active': self.is_active,
            'stake_amount': str(self.stake_amount),
            'total_fees_earned': str(self.total_fees_earned)
        }