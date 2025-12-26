"""
Court Order Model
Author: Ashutosh Rajesh
Purpose: Track court orders for de-anonymization

Each court order:
- Has unique order ID
- Issued by authorized judge
- Targets specific user (by IDX)
- Valid for 24 hours
- All access logged

Flow:
1. Judge submits court order
2. System verifies judge authorization
3. RBI provides master key
4. Company provides 24hr key
5. Private data decrypted
6. Access expires after 24hrs
7. All logged permanently

Example:
    order = CourtOrder(
        order_id="ORDER_2025_12345",
        judge_id="JID_2025_001",
        target_idx="IDX_abc123...",
        reason="Money laundering investigation",
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
"""

from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from database.connection import Base


class CourtOrder(Base):
    """Court order for de-anonymization"""
    
    __tablename__ = 'court_orders'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Order identification
    order_id = Column(String(100), unique=True, nullable=False, index=True)  # ORDER_2025_12345
    
    # Judge information
    judge_id = Column(String(50), ForeignKey('judges.judge_id'), nullable=False, index=True)
    
    # Target information
    target_idx = Column(String(255), nullable=False, index=True)  # User being investigated
    target_session_id = Column(String(255), nullable=True)  # Specific session (optional)
    
    # Order details
    reason = Column(Text, nullable=False)  # Why de-anonymization needed
    case_number = Column(String(100), nullable=True)  # Court case reference
    
    # Status
    status = Column(String(50), default='PENDING', nullable=False)  # PENDING, APPROVED, EXECUTED, EXPIRED
    
    # Access control
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # 24 hours from issue
    executed_at = Column(DateTime, nullable=True)  # When decryption happened
    
    # Keys issued
    company_key_issued = Column(Boolean, default=False, nullable=False)
    company_key_issued_at = Column(DateTime, nullable=True)
    
    # Results
    access_granted = Column(Boolean, default=False, nullable=False)
    decrypted_data = Column(Text, nullable=True)  # Stored encrypted with audit key
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    judge = relationship("Judge", back_populates="court_orders")
    
    def __repr__(self):
        return f"<CourtOrder {self.order_id} by {self.judge_id} ({self.status})>"
    
    def is_expired(self):
        """Check if order has expired"""
        return datetime.utcnow() >= self.expires_at
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'judge_id': self.judge_id,
            'target_idx': self.target_idx,
            'reason': self.reason,
            'case_number': self.case_number,
            'status': self.status,
            'issued_at': self.issued_at.isoformat() if self.issued_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'access_granted': self.access_granted,
            'is_expired': self.is_expired()
        }