"""
Judge Authorization Model
Author: Ashutosh Rajesh
Purpose: Pre-authorized judges for court orders

Only judges in this database can:
- Issue court orders
- Request de-anonymization
- Access private blockchain data

Security:
- Judge ID verified against this list
- Digital signature verification (in production)
- All access logged to audit trail

Example:
    # Add authorized judge
    judge = Judge(
        judge_id="JID_2025_001",
        full_name="Justice Sharma",
        court_name="Delhi High Court",
        jurisdiction="Delhi",
        is_active=True
    )
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database.connection import Base


class Judge(Base):
    """Authorized judge for court orders"""
    
    __tablename__ = 'judges'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Judge identification
    judge_id = Column(String(50), unique=True, nullable=False, index=True)  # JID_2025_001
    full_name = Column(String(255), nullable=False)  # Justice Sharma
    
    # Court information
    court_name = Column(String(255), nullable=False)  # Delhi High Court
    jurisdiction = Column(String(255), nullable=False)  # Delhi, Maharashtra, etc.
    
    # Authorization
    is_active = Column(Boolean, default=True, nullable=False)
    authorized_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    deactivated_at = Column(DateTime, nullable=True)
    
    # Digital signature public key (for production)
    public_key = Column(String(1000), nullable=True)  # For RSA/ECDSA verification
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    court_orders = relationship("CourtOrder", back_populates="judge")
    
    def __repr__(self):
        return f"<Judge {self.judge_id} - {self.full_name} ({self.court_name})>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'judge_id': self.judge_id,
            'full_name': self.full_name,
            'court_name': self.court_name,
            'jurisdiction': self.jurisdiction,
            'is_active': self.is_active,
            'authorized_at': self.authorized_at.isoformat() if self.authorized_at else None
        }