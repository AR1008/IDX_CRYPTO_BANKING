"""
Court Order Model
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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
"""

from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one court-ordered decryption event targeting exactly one transaction and one party (sender OR receiver)
class CourtOrder(Base):
    """Court order for de-anonymization"""

    # [DOC] Maps this Python class to the 'court_orders' PostgreSQL table
    __tablename__ = 'court_orders'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Order identification
    # [DOC] Unique court-issued reference number, e.g. "ORDER_2025_12345" — printed on freeze notification to account holder
    order_id = Column(String(100), unique=True, nullable=False, index=True)  # ORDER_2025_12345

    # Judge information
    # [DOC] Foreign key to judges.judge_id — only pre-authorized judges in that table can issue orders
    judge_id = Column(String(50), ForeignKey('judges.judge_id'), nullable=False, index=True)

    # Target information
    # [DOC] The permanent IDX pseudonym of the user being investigated (e.g. "IDX_abc123...")
    # [DOC] One court order targets exactly one IDX — the other party in the transaction stays encrypted
    target_idx = Column(String(255), nullable=False, index=True)  # User being investigated
    # [DOC] Optional: narrows the order to a specific 24-hour session ID if the investigator already knows it
    target_session_id = Column(String(255), nullable=True)  # Specific session (optional)

    # Order details
    # [DOC] Free-text legal justification submitted by the judge, e.g. "Money laundering investigation case #2025/FIU/42"
    reason = Column(Text, nullable=False)  # Why de-anonymization needed
    # [DOC] External court docket number for cross-referencing with the judicial system
    case_number = Column(String(100), nullable=True)  # Court case reference

    # Status
    # [DOC] Lifecycle: PENDING (filed) → APPROVED (judge verified) → EXECUTED (keys assembled, decryption done) → EXPIRED
    status = Column(String(50), default='PENDING', nullable=False)  # PENDING, APPROVED, EXECUTED, EXPIRED

    # Access control
    # [DOC] Timestamp when the court order was formally issued by the judge
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # [DOC] Hard deadline: exactly 24 hours after issued_at; keys become invalid and decryption is impossible after this
    expires_at = Column(DateTime, nullable=False)  # 24 hours from issue
    # [DOC] Timestamp when the actual key assembly and decryption happened; NULL until execution
    executed_at = Column(DateTime, nullable=True)  # When decryption happened

    # Keys issued
    # [DOC] True once the company has released its key share (one of two required shares in the 2-of-2 outer Shamir split)
    company_key_issued = Column(Boolean, default=False, nullable=False)
    # [DOC] When the company key share was released; used for audit trail
    company_key_issued_at = Column(DateTime, nullable=True)

    # Results
    # [DOC] True once all required key shares were assembled and the AES-256-GCM decryption succeeded
    access_granted = Column(Boolean, default=False, nullable=False)
    # [DOC] The decrypted transaction details, stored re-encrypted with an audit key (never stored in plaintext)
    # [DOC] Contains: target party's IDX, amount, timestamp — the OTHER party's IDX remains encrypted
    decrypted_data = Column(Text, nullable=True)  # Stored encrypted with audit key

    # Timestamps
    # [DOC] Row creation time; same as issued_at in most cases
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # [DOC] Auto-updated whenever any field changes; used to detect stale records
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    # [DOC] ORM relationship to the Judge row; allows order.judge.full_name lookups without extra queries
    judge = relationship("Judge", back_populates="court_orders")
    
    def __repr__(self):
        return f"<CourtOrder {self.order_id} by {self.judge_id} ({self.status})>"
    
    def is_expired(self):
        """Check if order has expired"""
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at
        # Handle timezone-naive datetime
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return now >= expires_at
    
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