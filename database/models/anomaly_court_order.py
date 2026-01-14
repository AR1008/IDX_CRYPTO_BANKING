"""
Anomaly Court Order Model
Purpose: Track court orders for anomaly-flagged transaction investigations

Flow:
1. Judge signs court order for anomaly investigation
2. System verifies judge signature
3. System auto-generates decryption keys (48h validity)
4. Keys distributed to: Company + Supreme Court + 1 regulatory authority
5. When keys used → triggers account freeze
6. All operations logged for audit trail

Key Properties:
- 48-hour key validity
- One-time use keys
- Judge signature required
- Automatic key distribution
- Freeze triggered on key usage
"""

from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from database.connection import Base


class AnomalyCourtOrder(Base):
    """Court order for anomaly-flagged transaction investigation"""

    __tablename__ = 'anomaly_court_orders'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Transaction being investigated
    transaction_hash = Column(String(66), nullable=False, index=True, unique=True)

    # Judge information
    judge_id = Column(String(50), nullable=False, index=True)
    judge_signature = Column(Text, nullable=False)  # Digital signature

    # Regulatory authority (which one gets the 3rd key)
    regulatory_authority = Column(String(50), nullable=False)  # rbi, fiu, cbi, income_tax

    # Court order metadata
    court_order_details = Column(JSON, nullable=True)  # Additional court order info

    # Key generation
    keys_generated_at = Column(DateTime, nullable=False, index=True)
    keys_expire_at = Column(DateTime, nullable=False, index=True)
    key_id = Column(String(66), nullable=False, unique=True)  # Unique key identifier

    # Key usage tracking
    keys_used = Column(Boolean, default=False, nullable=False)
    keys_used_at = Column(DateTime, nullable=True)
    keys_used_by = Column(String(100), nullable=True)  # Which authority used the keys

    # Account freeze tracking
    freeze_triggered = Column(Boolean, default=False, nullable=False)
    freeze_record_id = Column(Integer, nullable=True)  # Link to FreezeRecord

    # Audit trail
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        status = "KEYS_USED" if self.keys_used else "KEYS_ACTIVE"
        return f"<AnomalyCourtOrder {self.transaction_hash} - {status}>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'transaction_hash': self.transaction_hash,
            'judge_id': self.judge_id,
            'regulatory_authority': self.regulatory_authority,
            'keys_generated_at': self.keys_generated_at.isoformat() if self.keys_generated_at else None,
            'keys_expire_at': self.keys_expire_at.isoformat() if self.keys_expire_at else None,
            'key_id': self.key_id,
            'keys_used': self.keys_used,
            'keys_used_at': self.keys_used_at.isoformat() if self.keys_used_at else None,
            'keys_used_by': self.keys_used_by,
            'freeze_triggered': self.freeze_triggered,
            'freeze_record_id': self.freeze_record_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def is_expired(self, now: datetime = None) -> bool:
        """Check if keys have expired"""
        if now is None:
            from datetime import timezone
            now = datetime.now(timezone.utc)

        # Make keys_expire_at timezone-aware if it isn't
        expires_at = self.keys_expire_at
        if expires_at.tzinfo is None:
            from datetime import timezone
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return now >= expires_at

    def can_use_keys(self, now: datetime = None) -> bool:
        """Check if keys can still be used"""
        return not self.keys_used and not self.is_expired(now)
