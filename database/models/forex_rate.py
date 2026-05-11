"""
Forex Rate Model
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

# [DOC] SQLAlchemy column types for the forex_rates table schema.
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean
# [DOC] datetime for auto-populating created_at / effective_from on insert.
from datetime import datetime
# [DOC] Decimal is Python's exact fixed-point arithmetic — critical for financial amounts (no float rounding errors).
from decimal import Decimal
# [DOC] Base is the SQLAlchemy declarative base that all ORM models inherit from.
from database.connection import Base


# [DOC] ForexRate stores the exchange rate for one currency pair (e.g., INR → USD).
# [DOC] Travel account forex conversions and cross-border transactions use rows from this table.
class ForexRate(Base):
    """Forex exchange rate"""

    __tablename__ = 'forex_rates'

    # Primary key
    # [DOC] Auto-incrementing integer PK — simpler than UUID here since rates are internal reference data.
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Currency pair
    # [DOC] ISO 4217 3-letter currency code for the source currency (e.g., "INR"). Indexed for fast lookup.
    from_currency = Column(String(3), nullable=False, index=True)  # INR
    # [DOC] ISO 4217 3-letter currency code for the target currency (e.g., "USD"). Indexed for fast lookup.
    to_currency = Column(String(3), nullable=False, index=True)  # USD

    # Rate (1 from_currency = X to_currency)
    # [DOC] Exchange rate: 1 unit of from_currency = `rate` units of to_currency. 6 decimal places for precision.
    rate = Column(Numeric(precision=10, scale=6), nullable=False)  # 0.012000

    # Fee
    # [DOC] Bank's forex fee as a percentage (default 0.15%). Deducted from the converted amount before settlement.
    forex_fee_percentage = Column(Numeric(precision=5, scale=2), default=Decimal('0.15'))  # 0.15%

    # Status
    # [DOC] Only active rates are used for conversions; old rates are deactivated (not deleted) for audit history.
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    # [DOC] When this rate became effective — allows time-series lookup of historical rates.
    effective_from = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] When this rate expires; NULL means the rate is still current.
    effective_to = Column(DateTime, nullable=True)  # When rate expires
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ForexRate {self.from_currency}/{self.to_currency}: {self.rate}>"

    # [DOC] Converts an amount from from_currency to to_currency using this row's rate and fee.
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
        # [DOC] Apply the exchange rate: multiply the source amount by the rate to get the target-currency amount.
        converted = amount * self.rate

        if apply_fee:
            # [DOC] Calculate the bank's forex fee and subtract it — the user receives the net amount.
            fee = converted * (self.forex_fee_percentage / Decimal('100'))
            converted -= fee

        # [DOC] Round to 2 decimal places (cents/paise) to avoid fractional currency units.
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