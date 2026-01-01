"""
Recipient Model
Author: Ashutosh Rajesh
Purpose: User's saved recipients (like contact list)

Users can add recipients by their IDX and give them nicknames:
- Add recipient: Save IDX + give nickname "Mom", "Brother", etc.
- 30-minute waiting period before first transaction (fraud prevention)
- System manages session mapping internally (user never sees sessions)
- Session ID refreshes every 24hrs (no tracking possible)

Security Features:
✅ 30-minute waiting period prevents immediate fraudulent transactions
✅ User adds by IDX only (sessions handled internally)
✅ Sessions auto-rotate daily (privacy protection)
"""

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta

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
    # Managed internally - user never sees this
    current_session_id = Column(String(255), index=True)
    session_expires_at = Column(DateTime)

    # 30-minute waiting period (fraud prevention)
    can_transact_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(minutes=30),
        comment="When user can first send money (30 min after adding recipient)"
    )

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

    def can_transact(self):
        """
        Check if 30-minute waiting period has passed

        Returns:
            bool: True if user can send money, False if still waiting

        Example:
            >>> recipient = Recipient(...)
            >>> recipient.can_transact()
            False  # Still within 30 minutes
            >>> # Wait 30 minutes...
            >>> recipient.can_transact()
            True  # Can now send money
        """
        if not self.can_transact_at:
            return True  # Old recipients without this field
        return datetime.utcnow() >= self.can_transact_at

    def time_until_can_transact(self):
        """
        Get remaining time until can transact

        Returns:
            timedelta: Time remaining (or negative if can transact now)
        """
        if not self.can_transact_at:
            return timedelta(0)
        return self.can_transact_at - datetime.utcnow()

    def to_dict(self, include_session=False):
        """
        Convert to dictionary

        Args:
            include_session (bool): Include session ID (only for internal use)

        Returns:
            dict: Recipient data (user never sees session IDs)
        """
        data = {
            'id': self.id,
            'nickname': self.nickname,
            'recipient_idx': self.recipient_idx,
            'can_transact': self.can_transact(),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

        # Add time until can transact if still waiting
        if not self.can_transact():
            remaining = self.time_until_can_transact()
            data['can_transact_in_seconds'] = int(remaining.total_seconds())
            data['can_transact_in_minutes'] = int(remaining.total_seconds() / 60)

        # Only include session for internal operations
        # Users NEVER see session IDs
        if include_session:
            data['current_session_id'] = self.current_session_id
            data['session_expires_at'] = self.session_expires_at.isoformat() if self.session_expires_at else None

        return data