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

# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] Separate from regular court_order: targets anomaly-flagged transactions specifically
# [DOC] Regular court_order targets a user's IDX; this one targets a specific transaction_hash
# [DOC] One row = one anomaly investigation order; unique per transaction (you cannot open two orders for the same tx)
class AnomalyCourtOrder(Base):
    """Court order for anomaly-flagged transaction investigation"""

    # [DOC] Maps this Python class to the 'anomaly_court_orders' PostgreSQL table
    __tablename__ = 'anomaly_court_orders'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Transaction being investigated
    # [DOC] SHA-256 hash of the transaction (0x-prefixed, 66 chars); links to the transactions table
    # [DOC] The transaction must have zkp_anomaly_proof set (anomaly score >= 65) for this order to be valid
    transaction_hash = Column(String(66), nullable=False, index=True, unique=True)

    # Judge information
    # [DOC] ID of the judge issuing this order; must exist in the judges table (only pre-authorized judges are accepted)
    judge_id = Column(String(50), nullable=False, index=True)
    # [DOC] The judge's digital signature over the court order payload; verifies the order was not forged
    # [DOC] Signature verification currently raises NotImplementedError in court_order_verification_anomaly.py (known limitation)
    judge_signature = Column(Text, nullable=False)  # Digital signature

    # Regulatory authority (which one gets the 3rd key)
    # [DOC] Which authority provides their key share for decryption: "ffa", "fiu", "flea", or "nta"
    # [DOC] This is the 1-of-N inner Shamir share holder that participates in this specific decryption
    regulatory_authority = Column(String(50), nullable=False)  # rbi, fiu, cbi, income_tax

    # Court order metadata
    # [DOC] Optional JSON blob for additional court order fields (case number, date, court name, etc.)
    court_order_details = Column(JSON, nullable=True)  # Additional court order info

    # Key generation
    # [DOC] Timestamp when the system generated the one-time AES decryption keys for this order
    keys_generated_at = Column(DateTime, nullable=False, index=True)
    # [DOC] Hard deadline for key use: currently 48 hours after keys_generated_at (stricter than regular court orders)
    keys_expire_at = Column(DateTime, nullable=False, index=True)
    # [DOC] Unique hex identifier for this key set; used to look up the correct Shamir shares during assembly
    key_id = Column(String(66), nullable=False, unique=True)  # Unique key identifier

    # Key usage tracking
    # [DOC] True once all required shares were assembled and decryption was performed; keys cannot be reused after this
    keys_used = Column(Boolean, default=False, nullable=False)
    # [DOC] Timestamp of the decryption event; NULL until the keys are actually used
    keys_used_at = Column(DateTime, nullable=True)
    # [DOC] Name of the authority that assembled the keys and performed the decryption (audit trail)
    keys_used_by = Column(String(100), nullable=True)  # Which authority used the keys

    # Account freeze tracking
    # [DOC] True once the decrypted IDX was looked up and the account was frozen as a result
    freeze_triggered = Column(Boolean, default=False, nullable=False)
    # [DOC] Foreign reference to freeze_records.id for the freeze that resulted from this court order
    freeze_record_id = Column(Integer, nullable=True)  # Link to FreezeRecord

    # Audit trail
    # [DOC] Row creation time (UTC); set automatically at INSERT
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # [DOC] Auto-updated whenever any field changes; tracks the latest state of the order lifecycle
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
