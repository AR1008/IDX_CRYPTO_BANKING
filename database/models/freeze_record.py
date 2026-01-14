"""
Freeze Record Model
Purpose: Track account freeze history for government investigations

Tracks:
- When account was frozen
- Duration (24h or 72h)
- Investigation details
- Auto-unfreeze status
- Manual unfreeze details
"""

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from database.connection import Base


class FreezeRecord(Base):
    """Record of account freeze for government investigation"""

    __tablename__ = 'freeze_records'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # User and transaction
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    transaction_hash = Column(String(66), nullable=True, index=True)  # Transaction being investigated

    # Freeze timing
    freeze_started_at = Column(DateTime, nullable=False, index=True)
    freeze_expires_at = Column(DateTime, nullable=False, index=True)
    freeze_duration_hours = Column(Integer, nullable=False)  # 24 or 72

    # Investigation tracking
    investigation_number_this_month = Column(Integer, nullable=False)
    month = Column(String(7), nullable=False, index=True)  # Format: YYYY-MM
    is_first_this_month = Column(Boolean, nullable=False)

    # Reason and authority
    reason = Column(Text, nullable=False)
    triggered_by = Column(String(100), nullable=True)  # Authority that triggered

    # Status
    is_active = Column(Boolean, default=True, nullable=False)  # True if freeze is still active
    auto_unfreeze_scheduled = Column(Boolean, default=True, nullable=False)
    manually_unfrozen = Column(Boolean, default=False, nullable=False)

    # Manual unfreeze details
    unfrozen_at = Column(DateTime, nullable=True)
    unfrozen_by = Column(String(100), nullable=True)
    unfreeze_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="freeze_records")

    def __repr__(self):
        status = "ACTIVE" if self.is_active else "EXPIRED"
        if self.manually_unfrozen:
            status = "MANUALLY_UNFROZEN"
        return f"<FreezeRecord {self.user_idx} - {status} - {self.freeze_duration_hours}h>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_idx': self.user_idx,
            'transaction_hash': self.transaction_hash,
            'freeze_started_at': self.freeze_started_at.isoformat() if self.freeze_started_at else None,
            'freeze_expires_at': self.freeze_expires_at.isoformat() if self.freeze_expires_at else None,
            'freeze_duration_hours': self.freeze_duration_hours,
            'investigation_number_this_month': self.investigation_number_this_month,
            'month': self.month,
            'is_first_this_month': self.is_first_this_month,
            'reason': self.reason,
            'triggered_by': self.triggered_by,
            'is_active': self.is_active,
            'auto_unfreeze_scheduled': self.auto_unfreeze_scheduled,
            'manually_unfrozen': self.manually_unfrozen,
            'unfrozen_at': self.unfrozen_at.isoformat() if self.unfrozen_at else None,
            'unfrozen_by': self.unfrozen_by,
            'unfreeze_reason': self.unfreeze_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def is_expired(self, now: datetime = None) -> bool:
        """Check if freeze has expired"""
        if now is None:
            from datetime import timezone
            now = datetime.now(timezone.utc)

        # Make freeze_expires_at timezone-aware if it isn't
        expires_at = self.freeze_expires_at
        if expires_at.tzinfo is None:
            from datetime import timezone
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return now >= expires_at

    def should_unfreeze(self, now: datetime = None) -> bool:
        """Check if account should be unfrozen"""
        return self.is_active and not self.manually_unfrozen and self.is_expired(now)
