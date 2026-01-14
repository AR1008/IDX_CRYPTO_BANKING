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

from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from database.connection import Base


class BankAccount(Base):
    """User's bank account at a specific bank"""
    
    __tablename__ = 'bank_accounts'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to user
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    
    # Bank information
    bank_code = Column(String(10), nullable=False, index=True)  # HDFC, ICICI, SBI, etc.
    account_number = Column(String(50), unique=True, nullable=False, index=True)  # Generated account number
    
    # Balance
    balance = Column(Numeric(precision=15, scale=2), nullable=False, default=Decimal('0.00'))
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_frozen = Column(Boolean, default=False, nullable=False)  # For court orders
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
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
            'balance': str(self.balance),
            'is_active': self.is_active,
            'is_frozen': self.is_frozen,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }