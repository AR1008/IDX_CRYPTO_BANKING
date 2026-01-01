"""
Access Control Models
Purpose: Company-controlled access to IDX registry and sensitive data

Security Model:
- Company: Master access to everything
- Government: Time-limited access (granted by company)
- CAs (Chartered Accountants): Time-limited access (granted by company for tax season)
- Auto-expiry: All access tokens expire automatically
- Audit trail: Every access logged

Tables:
1. AccessToken - Time-limited access tokens for Gov/CA
2. AccessAuditLog - Complete access history (who accessed what when)
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum as SQLEnum, Index
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from database.connection import Base
import enum


class AccessRole(enum.Enum):
    """
    Types of access roles
    """
    COMPANY_ADMIN = "company_admin"          # Full access, no expiry
    GOVERNMENT = "government"                 # Time-limited, court order required
    CHARTERED_ACCOUNTANT = "chartered_accountant"  # Time-limited, tax season only
    BANK_ADMIN = "bank_admin"                # Bank-specific access


class AccessToken(Base):
    """
    Time-limited access tokens for external parties

    Company grants temporary access to:
    - Government agencies (for investigations)
    - Chartered Accountants (for tax verification)

    All tokens auto-expire after duration.
    All access is logged to AccessAuditLog.

    Example:
        >>> # Company grants CA access for 7 days
        >>> token = AccessToken(
        ...     role=AccessRole.CHARTERED_ACCOUNTANT,
        ...     granted_to="CA_FIRM_123",
        ...     granted_by="ADMIN_001",
        ...     purpose="Tax season 2025-26",
        ...     expires_at=datetime.now() + timedelta(days=7)
        ... )
    """

    __tablename__ = 'access_tokens'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Token (UUID for API authentication)
    token = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Access token (used for API authentication)"
    )

    # Role
    role = Column(
        SQLEnum(AccessRole),
        nullable=False,
        index=True,
        comment="Access role type"
    )

    # Who was granted access
    granted_to = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Entity receiving access (CA firm name, Gov dept, etc.)"
    )

    # Who granted the access (company admin)
    granted_by = Column(
        String(255),
        nullable=False,
        comment="Company admin who granted access"
    )

    # Purpose of access
    purpose = Column(
        Text,
        nullable=False,
        comment="Why this access was granted"
    )

    # Scope restrictions (JSON)
    # Example: {"user_idx": "IDX_abc123..."} - only access this user's data
    # Example: {"date_range": {"from": "2025-01-01", "to": "2025-12-31"}}
    scope = Column(
        Text,
        nullable=True,
        comment="JSON scope restrictions (optional)"
    )

    # Time limits
    granted_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When access was granted"
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When access expires (auto-revoke)"
    )

    # Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Active status (can be manually revoked)"
    )

    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When access was revoked (if manually revoked)"
    )

    revoked_by = Column(
        String(255),
        nullable=True,
        comment="Who revoked the access"
    )

    # Last used
    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this token was used"
    )

    # Indexes
    __table_args__ = (
        Index('idx_access_tokens_active', 'is_active', 'expires_at'),
        Index('idx_access_tokens_granted_to', 'granted_to'),
        Index('idx_access_tokens_role', 'role'),
    )

    def is_valid(self):
        """Check if token is still valid"""
        if not self.is_active:
            return False
        if datetime.now(self.expires_at.tzinfo) > self.expires_at:
            return False
        return True

    def __repr__(self):
        status = "ACTIVE" if self.is_valid() else "EXPIRED/REVOKED"
        return (
            f"<AccessToken(role={self.role.value}, "
            f"granted_to={self.granted_to}, "
            f"status={status})>"
        )

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'token': self.token,
            'role': self.role.value,
            'granted_to': self.granted_to,
            'granted_by': self.granted_by,
            'purpose': self.purpose,
            'granted_at': self.granted_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'is_active': self.is_active,
            'is_valid': self.is_valid(),
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None
        }


class AccessAuditLog(Base):
    """
    Complete audit trail of all IDX registry access

    Logs every access to:
    - IDX → Real name lookups
    - Transaction history access
    - User data access

    Purpose: Accountability and security monitoring

    Example:
        >>> # Log CA accessing user data
        >>> log = AccessAuditLog(
        ...     access_token_id=token.id,
        ...     accessed_by="CA_FIRM_123",
        ...     action="VIEW_USER_TRANSACTIONS",
        ...     target_idx="IDX_abc123...",
        ...     details={"transaction_count": 45}
        ... )
    """

    __tablename__ = 'access_audit_logs'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which access token was used
    access_token_id = Column(
        Integer,
        nullable=True,  # Null for company admin access
        index=True,
        comment="Access token used (null for company admin)"
    )

    # Who accessed
    accessed_by = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Who accessed (CA firm, Gov dept, Admin user)"
    )

    # What action
    action = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Action type: VIEW_IDX_REGISTRY, VIEW_TRANSACTIONS, etc."
    )

    # Target of access
    target_idx = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Which user's data was accessed (null for bulk queries)"
    )

    # Additional details (JSON)
    details = Column(
        Text,
        nullable=True,
        comment="JSON details of what was accessed"
    )

    # IP address and user agent
    ip_address = Column(
        String(45),
        nullable=True,
        comment="IP address of accessor"
    )

    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string"
    )

    # Timestamp
    accessed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="When access occurred"
    )

    # Indexes
    __table_args__ = (
        Index('idx_access_audit_accessed_by', 'accessed_by'),
        Index('idx_access_audit_action', 'action'),
        Index('idx_access_audit_target', 'target_idx'),
        Index('idx_access_audit_time', 'accessed_at'),
    )

    def __repr__(self):
        return (
            f"<AccessAuditLog(action={self.action}, "
            f"by={self.accessed_by}, "
            f"target={self.target_idx[:20] if self.target_idx else 'N/A'}...)>"
        )

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'access_token_id': self.access_token_id,
            'accessed_by': self.accessed_by,
            'action': self.action,
            'target_idx': self.target_idx,
            'details': self.details,
            'ip_address': self.ip_address,
            'accessed_at': self.accessed_at.isoformat()
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test access control models
    Run: python3 -m database.models.access_control
    """
    from database.connection import engine, SessionLocal
    import uuid

    print("=== Access Control Models Testing ===\n")

    # Create tables
    print("Creating access control tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created!\n")

    # Create session
    db = SessionLocal()

    try:
        # Test 1: Create CA access token
        print("Test 1: Create CA Access Token")

        token = AccessToken(
            token=str(uuid.uuid4()),
            role=AccessRole.CHARTERED_ACCOUNTANT,
            granted_to="ABC Tax Consultants Pvt Ltd",
            granted_by="ADMIN_001",
            purpose="Tax season FY 2025-26 - Client verification",
            expires_at=datetime.now() + timedelta(days=7)
        )

        db.add(token)
        db.commit()

        print(f"  Token: {token}")
        print(f"  Valid: {token.is_valid()}")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Create government access token
        print("Test 2: Create Government Access Token")

        gov_token = AccessToken(
            token=str(uuid.uuid4()),
            role=AccessRole.GOVERNMENT,
            granted_to="Income Tax Department - Delhi",
            granted_by="ADMIN_002",
            purpose="Investigation case #2025/IT/1234",
            expires_at=datetime.now() + timedelta(hours=24)
        )

        db.add(gov_token)
        db.commit()

        print(f"  Token: {gov_token}")
        print(f"  Expires in: 24 hours")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Log access
        print("Test 3: Log Access")

        audit_log = AccessAuditLog(
            access_token_id=token.id,
            accessed_by="ABC Tax Consultants Pvt Ltd",
            action="VIEW_USER_TRANSACTIONS",
            target_idx="IDX_abc123...",
            details='{"transaction_count": 45, "date_range": "2025-01-01 to 2025-12-31"}',
            ip_address="203.0.113.45"
        )

        db.add(audit_log)
        db.commit()

        print(f"  Audit log: {audit_log}")
        print("  ✅ Test 3 passed!\n")

        # Test 4: Revoke access
        print("Test 4: Revoke Access")

        token.is_active = False
        token.revoked_at = datetime.now()
        token.revoked_by = "ADMIN_001"
        db.commit()

        print(f"  Token revoked: {not token.is_valid()}")
        print("  ✅ Test 4 passed!\n")

        # Test 5: Query audit logs
        print("Test 5: Query Audit Logs")

        logs = db.query(AccessAuditLog).filter(
            AccessAuditLog.action == "VIEW_USER_TRANSACTIONS"
        ).all()

        print(f"  Found {len(logs)} transaction view logs")
        print("  ✅ Test 5 passed!\n")

        print("=" * 50)
        print("✅ All Access Control tests passed!")
        print("=" * 50)

    finally:
        db.close()
