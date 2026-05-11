"""
Judge Authorization Model
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
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one pre-authorized judge; only judges in this table can issue valid court orders
# [DOC] Acting as an allowlist — any court_order referencing a judge_id NOT in this table is rejected
class Judge(Base):
    """Authorized judge for court orders"""

    # [DOC] Maps this Python class to the 'judges' PostgreSQL table
    __tablename__ = 'judges'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Judge identification
    # [DOC] Unique judge identifier issued by the judiciary, e.g. "JID_2025_001"
    # [DOC] This string is referenced by court_orders.judge_id and anomaly_court_orders.judge_id
    judge_id = Column(String(50), unique=True, nullable=False, index=True)  # JID_2025_001
    # [DOC] Full legal name of the judge, e.g. "Justice Sharma" — displayed on freeze notifications
    full_name = Column(String(255), nullable=False)  # Justice Sharma

    # Court information
    # [DOC] Name of the court this judge belongs to, e.g. "Delhi High Court" — used in audit logs
    court_name = Column(String(255), nullable=False)  # Delhi High Court
    # [DOC] Geographic or legal jurisdiction this judge covers, e.g. "Delhi" or "Maharashtra"
    # [DOC] System does not currently restrict court orders to jurisdiction — stored for audit trail only
    jurisdiction = Column(String(255), nullable=False)  # Delhi, Maharashtra, etc.

    # Authorization
    # [DOC] False means this judge has been removed from the allowlist; their future court orders will be rejected
    is_active = Column(Boolean, default=True, nullable=False)
    # [DOC] When this judge was added to the pre-authorized list by IDX Corp admins
    authorized_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] Set when a judge is deactivated; NULL while still active
    deactivated_at = Column(DateTime, nullable=True)

    # Digital signature public key (for production)
    # [DOC] PEM-encoded RSA or ECDSA public key used to verify the judge's digital signature on court orders
    # [DOC] Signature verification is currently not implemented (raises NotImplementedError) — planned for CCS 2027
    # [DOC] Once implemented, any court order whose judge_signature does not verify against this key is rejected
    public_key = Column(String(1000), nullable=True)  # For RSA/ECDSA verification

    # Timestamps
    # [DOC] UTC datetime when this judge row was inserted
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # [DOC] Auto-updated whenever any field changes
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # [DOC] ORM relationship to all CourtOrder rows filed by this judge; enables judge.court_orders lookups
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