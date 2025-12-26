"""
Recipient Model
Author: Ashutosh Rajesh
Purpose: User's saved recipients (like contact list)

Users can add recipients by their IDX and give them nicknames:
- Add recipient: Save IDX2 + give nickname "Mom", "Brother", etc.
- Session created for this recipient (24hr rotation)
- Send money using nickname (internally uses IDX2)
- Session ID refreshes every 24hrs (no tracking possible)
"""

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from database.connection import Base


class Recipient(Base):
    """Saved recipient in user's contact list"""
    
    __tablename__ = 'recipients'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Owner of this recipient entry
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    
    # Recipient's IDX (the person you're sending to)
    recipient_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    
    # Nickname given by user
    nickname = Column(String(100), nullable=False)  # "Mom", "Brother", "Priya", etc.
    
    # Current session ID for this recipient (refreshes every 24hrs)
    current_session_id = Column(String(255), index=True)
    session_expires_at = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # owner = relationship("User", foreign_keys=[user_idx], back_populates="recipients")
    recipient_user = relationship("User", foreign_keys=[recipient_idx])
    
    # Composite unique constraint: user can't have duplicate nicknames
    __table_args__ = (
        # Index for faster lookups
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )
    
    def __repr__(self):
        return f"<Recipient {self.nickname} (IDX: {self.recipient_idx[:16]}...)>"
    
    def is_session_expired(self):
        """Check if session needs rotation"""
        if not self.session_expires_at:
            return True
        return datetime.utcnow() >= self.session_expires_at
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'nickname': self.nickname,
            'recipient_idx': self.recipient_idx,
            'current_session_id': self.current_session_id,
            'session_expires_at': self.session_expires_at.isoformat() if self.session_expires_at else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }