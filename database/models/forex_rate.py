"""
Forex Rate Model
Author: Ashutosh Rajesh
Purpose: Exchange rates for currency conversion

Rates updated daily (in production: via API like exchangerate-api.com)
For demo: Manual updates or fixed rates

Example:
    # INR to USD
    rate = ForexRate(
        from_currency="INR",
        to_currency="USD",
        rate=0.012,  # 1 INR = 0.012 USD (1 USD = ₹83.33)
        forex_fee_percentage=0.15
    )
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean
from datetime import datetime
from decimal import Decimal
from database.connection import Base


class ForexRate(Base):
    """Forex exchange rate"""
    
    __tablename__ = 'forex_rates'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Currency pair
    from_currency = Column(String(3), nullable=False, index=True)  # INR
    to_currency = Column(String(3), nullable=False, index=True)  # USD
    
    # Rate (1 from_currency = X to_currency)
    rate = Column(Numeric(precision=10, scale=6), nullable=False)  # 0.012000
    
    # Fee
    forex_fee_percentage = Column(Numeric(precision=5, scale=2), default=Decimal('0.15'))  # 0.15%
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    effective_from = Column(DateTime, default=datetime.utcnow, nullable=False)
    effective_to = Column(DateTime, nullable=True)  # When rate expires
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<ForexRate {self.from_currency}/{self.to_currency}: {self.rate}>"
    
    def convert(self, amount: Decimal, apply_fee: bool = True) -> Decimal:
        """
        Convert amount using this rate
        
        Args:
            amount: Amount in from_currency
            apply_fee: Apply forex fee?
            
        Returns:
            Decimal: Amount in to_currency
            
        Example:
            >>> rate = ForexRate(from_currency="INR", to_currency="USD", rate=0.012)
            >>> rate.convert(Decimal('10000'))  # ₹10,000
            Decimal('119.82')  # $119.82 (after 0.15% fee)
        """
        converted = amount * self.rate
        
        if apply_fee:
            fee = converted * (self.forex_fee_percentage / Decimal('100'))
            converted -= fee
        
        return converted.quantize(Decimal('0.01'))
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'from_currency': self.from_currency,
            'to_currency': self.to_currency,
            'rate': str(self.rate),
            'forex_fee_percentage': str(self.forex_fee_percentage),
            'is_active': self.is_active,
            'effective_from': self.effective_from.isoformat() if self.effective_from else None
        }