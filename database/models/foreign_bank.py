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
from database.connection import Base


class ForeignBank(Base):
    """Foreign bank for international transactions"""
    
    __tablename__ = 'foreign_banks'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Bank identification
    bank_code = Column(String(20), unique=True, nullable=False, index=True)  # CITI_USA, HSBC_UK
    bank_name = Column(String(255), nullable=False)  # Citibank USA
    
    # Location
    country = Column(String(100), nullable=False)  # United States
    country_code = Column(String(3), nullable=False, index=True)  # USA, GBR, DEU
    currency = Column(String(3), nullable=False)  # USD, GBP, EUR
    
    # Partnership
    partner_indian_banks = Column(String(500), nullable=True)  # "HDFC,ICICI,SBI" (comma-separated)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Stake (for consensus - like Indian banks)
    stake_amount = Column(Numeric(precision=15, scale=2), default=Decimal('100000000.00'))
    
    # Fees
    total_fees_earned = Column(Numeric(precision=15, scale=2), default=Decimal('0.00'))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
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