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

# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one account-freeze event; an account can have multiple freeze records over time (one per court order)
class FreezeRecord(Base):
    """Record of account freeze for government investigation"""

    # [DOC] Maps this Python class to the 'freeze_records' PostgreSQL table
    __tablename__ = 'freeze_records'

    # Primary key
    # [DOC] Auto-incrementing integer; referenced by anomaly_court_orders.freeze_record_id
    id = Column(Integer, primary_key=True, autoincrement=True)

    # User and transaction
    # [DOC] IDX pseudonym of the account being frozen; foreign key to users.idx
    # [DOC] The account holder is notified with the court order reference number — no reason is disclosed to them
    user_idx = Column(String(255), ForeignKey('users.idx'), nullable=False, index=True)
    # [DOC] Hash of the specific transaction that triggered this freeze; NULL if the freeze is account-wide
    # [DOC] Linking to a transaction allows the government to read that transaction's decrypted details during the freeze window
    transaction_hash = Column(String(66), nullable=True, index=True)  # Transaction being investigated

    # Freeze timing
    # [DOC] UTC datetime when the freeze was applied; account becomes read-only to the government from this moment
    freeze_started_at = Column(DateTime, nullable=False, index=True)
    # [DOC] UTC datetime when the freeze automatically expires and government access is revoked
    # [DOC] After this time the government loses all visibility — keys are already invalidated (one-time use)
    freeze_expires_at = Column(DateTime, nullable=False, index=True)
    # [DOC] Duration of this freeze in hours; typically 24 (first investigation this month) or 72 (repeat)
    freeze_duration_hours = Column(Integer, nullable=False)  # 24 or 72

    # Investigation tracking
    # [DOC] Sequential count of how many times this account has been investigated in the current calendar month
    # [DOC] Used to determine freeze duration escalation (first = 24h, subsequent = 72h)
    investigation_number_this_month = Column(Integer, nullable=False)
    # [DOC] Calendar month of this freeze in YYYY-MM format, e.g. "2026-03"; used to reset monthly investigation count
    month = Column(String(7), nullable=False, index=True)  # Format: YYYY-MM
    # [DOC] True if this is the first freeze for this account in the current month (determines 24h vs 72h duration)
    is_first_this_month = Column(Boolean, nullable=False)

    # Reason and authority
    # [DOC] Legal justification for the freeze carried over from the court order; stored for audit trail
    reason = Column(Text, nullable=False)
    # [DOC] Which regulatory authority (FFA, FIU, FLEA, NTA) triggered this freeze by providing their key share
    triggered_by = Column(String(100), nullable=True)  # Authority that triggered

    # Status
    # [DOC] True while the freeze is currently in effect; set to False when expired or manually lifted
    is_active = Column(Boolean, default=True, nullable=False)  # True if freeze is still active
    # [DOC] True if a background worker should automatically lift the freeze when freeze_expires_at passes
    auto_unfreeze_scheduled = Column(Boolean, default=True, nullable=False)
    # [DOC] True if a company admin lifted the freeze before its natural expiry (e.g. court order withdrawn)
    manually_unfrozen = Column(Boolean, default=False, nullable=False)

    # Manual unfreeze details
    # [DOC] Timestamp of manual unfreeze; NULL if the freeze expired naturally
    unfrozen_at = Column(DateTime, nullable=True)
    # [DOC] Username of the IDX Corp admin who manually lifted the freeze
    unfrozen_by = Column(String(100), nullable=True)
    # [DOC] Free-text reason for manual early unfreeze, e.g. "Court order withdrawn by judge"
    unfreeze_reason = Column(Text, nullable=True)

    # Timestamps
    # [DOC] UTC datetime when this freeze record row was created (same as freeze_started_at in most cases)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # [DOC] Auto-updated whenever any field changes; tracks the latest state of this freeze lifecycle
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    # [DOC] ORM relationship to the User row being frozen; enables record.user.full_name lookups
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
