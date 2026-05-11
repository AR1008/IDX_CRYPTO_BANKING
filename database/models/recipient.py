"""
Recipient Model
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

# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one saved contact in a sender's address book; eliminates the need to re-enter IDX every time
# [DOC] The sender enters a recipient's IDX ONCE, gives them a nickname, and the system resolves session IDs automatically from then on
class Recipient(Base):
    """Saved recipient in user's contact list"""

    # [DOC] Maps this Python class to the 'recipients' PostgreSQL table
    __tablename__ = 'recipients'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Owner of this recipient entry
    # [DOC] IDX pseudonym of the SENDER who saved this contact; foreign key to users.idx
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)

    # Recipient's IDX (the person you're sending to)
    # [DOC] Permanent IDX pseudonym of the RECEIVER; entered once and stored here permanently
    # [DOC] The sender never needs to enter this again — system auto-resolves to the receiver's current session ID
    recipient_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)

    # Nickname given by user
    # [DOC] Human-readable alias the sender chose, e.g. "Mom", "Landlord", "Priya" — shown in the sender's contact list
    nickname = Column(String(100), nullable=False)  # "Mom", "Brother", "Priya", etc.

    # Current session ID for this recipient (refreshes every 24hrs)
    # Managed internally - user never sees this
    # [DOC] The RECEIVER's current 24-hour rotating session ID; cached here so we do not query the sessions table on every send
    # [DOC] This field is NEVER exposed to the sender — users only ever see IDX pseudonyms, not session IDs
    current_session_id = Column(String(255), index=True)
    # [DOC] Expiry timestamp of the cached session ID above; when this passes, the system fetches a fresh session ID before sending
    session_expires_at = Column(DateTime)

    # 30-minute waiting period (fraud prevention)
    # [DOC] Anti-fraud delay: the sender cannot make any transaction to a newly added recipient for 30 minutes
    # [DOC] Prevents an attacker who has momentary phone access from immediately transferring funds to a new contact
    can_transact_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(minutes=30),
        comment="When user can first send money (30 min after adding recipient)"
    )

    # Status
    # [DOC] False means this contact has been removed from the sender's address book; no new transactions allowed
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    # [DOC] UTC datetime when this contact was first saved; also used to compute can_transact_at (= created_at + 30 min)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] Auto-updated whenever any field changes; primarily changes when current_session_id is refreshed
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # owner = relationship("User", foreign_keys=[user_idx], back_populates="recipients")
    # [DOC] ORM relationship to the RECEIVER's User row; enables contact.recipient_user.idx lookups
    recipient_user = relationship("User", foreign_keys=[recipient_idx])

    # Composite unique constraint: user can't have duplicate nicknames
    # [DOC] Table engine options only; no additional index defined here beyond column-level indexes above
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