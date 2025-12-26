"""
Security Models - IP Blocking and Rate Limit Violations
Purpose: Track blocked IPs and rate limit violations for DDoS protection

Tables:
- blocked_ips: IP addresses blocked from accessing the system
- rate_limit_violations: Log of all rate limit violations

Security Features:
- Automatic IP blocking after threshold violations
- Manual IP blocking by administrators
- Temporary and permanent blocks
- Violation history for analysis
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from database.connection import Base


class BlockedIP(Base):
    """
    Blocked IP addresses table

    Tracks IP addresses that have been blocked from accessing the system.
    Supports both automatic blocking (DDoS protection) and manual blocking (admin action).

    Example:
        >>> from database.connection import SessionLocal
        >>>
        >>> # Block an IP automatically (DDoS)
        >>> db = SessionLocal()
        >>> blocked = BlockedIP(
        ...     ip_address="192.168.1.100",
        ...     reason="Exceeded rate limit threshold (1000+ requests/min)",
        ...     blocked_by="AUTO",
        ...     expires_at=datetime.utcnow() + timedelta(hours=1)
        ... )
        >>> db.add(blocked)
        >>> db.commit()
        >>>
        >>> # Block an IP permanently (manual)
        >>> blocked = BlockedIP(
        ...     ip_address="10.0.0.50",
        ...     reason="Malicious activity detected",
        ...     blocked_by="admin@example.com",
        ...     expires_at=None  # Permanent
        ... )
    """

    __tablename__ = "blocked_ips"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # IP address (IPv4 or IPv6)
    ip_address = Column(
        String(45),  # IPv6 max length is 45 characters
        nullable=False,
        unique=True,
        index=True,
        comment="Blocked IP address (IPv4 or IPv6)"
    )

    # Block details
    reason = Column(
        String(255),
        nullable=True,
        comment="Reason for blocking this IP"
    )

    blocked_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="When this IP was blocked"
    )

    expires_at = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="When block expires (NULL = permanent)"
    )

    blocked_by = Column(
        String(100),
        nullable=True,
        comment="Who blocked this IP ('AUTO' for automatic, or admin username)"
    )

    # Indexes
    __table_args__ = (
        Index('idx_blocked_ip', 'ip_address'),
        Index('idx_blocked_expiry', 'expires_at'),
    )

    def __repr__(self):
        return (
            f"<BlockedIP("
            f"ip={self.ip_address}, "
            f"reason={self.reason[:30] if self.reason else None}, "
            f"expires={self.expires_at}"
            f")>"
        )

    def is_expired(self):
        """Check if block has expired"""
        if self.expires_at is None:
            return False  # Permanent block
        return datetime.utcnow() > self.expires_at

    def is_permanent(self):
        """Check if this is a permanent block"""
        return self.expires_at is None

    @classmethod
    def is_ip_blocked(cls, db, ip_address: str) -> bool:
        """
        Check if an IP is currently blocked

        Args:
            db: Database session
            ip_address: IP address to check

        Returns:
            True if IP is blocked and block hasn't expired, False otherwise
        """
        blocked = db.query(cls).filter(cls.ip_address == ip_address).first()

        if not blocked:
            return False

        # Check if expired
        if blocked.is_expired():
            # Remove expired block
            db.delete(blocked)
            db.commit()
            return False

        return True

    @classmethod
    def block_ip(cls, db, ip_address: str, reason: str, duration_minutes: int = None, blocked_by: str = "AUTO"):
        """
        Block an IP address

        Args:
            db: Database session
            ip_address: IP to block
            reason: Reason for blocking
            duration_minutes: Block duration in minutes (None = permanent)
            blocked_by: Who is blocking ("AUTO" or admin username)

        Returns:
            BlockedIP instance
        """
        # Check if already blocked
        existing = db.query(cls).filter(cls.ip_address == ip_address).first()

        if existing:
            # Update existing block
            existing.reason = reason
            existing.blocked_at = func.now()
            existing.blocked_by = blocked_by

            if duration_minutes:
                existing.expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            else:
                existing.expires_at = None

            db.commit()
            return existing

        # Create new block
        expires_at = None
        if duration_minutes:
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)

        blocked = cls(
            ip_address=ip_address,
            reason=reason,
            blocked_by=blocked_by,
            expires_at=expires_at
        )

        db.add(blocked)
        db.commit()

        return blocked

    @classmethod
    def unblock_ip(cls, db, ip_address: str):
        """
        Unblock an IP address

        Args:
            db: Database session
            ip_address: IP to unblock

        Returns:
            True if IP was unblocked, False if not found
        """
        blocked = db.query(cls).filter(cls.ip_address == ip_address).first()

        if blocked:
            db.delete(blocked)
            db.commit()
            return True

        return False


class RateLimitViolation(Base):
    """
    Rate limit violations table

    Logs all instances where a user/IP exceeded the rate limit.
    Used for security analysis and automatic IP blocking.

    Example:
        >>> from database.connection import SessionLocal
        >>>
        >>> # Log a violation
        >>> db = SessionLocal()
        >>> violation = RateLimitViolation(
        ...     ip_address="192.168.1.100",
        ...     endpoint="/api/auth/login",
        ...     violation_count=5,
        ...     user_agent="Mozilla/5.0..."
        ... )
        >>> db.add(violation)
        >>> db.commit()
    """

    __tablename__ = "rate_limit_violations"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Violation details
    ip_address = Column(
        String(45),
        nullable=False,
        index=True,
        comment="IP address that violated rate limit"
    )

    endpoint = Column(
        String(255),
        nullable=False,
        index=True,
        comment="API endpoint that was hit"
    )

    violated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        index=True,
        comment="When violation occurred"
    )

    violation_count = Column(
        Integer,
        nullable=False,
        default=1,
        comment="How many times rate limit was exceeded"
    )

    # Request metadata
    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string from request"
    )

    request_path = Column(
        Text,
        nullable=True,
        comment="Full request path with query parameters"
    )

    # Indexes
    __table_args__ = (
        Index('idx_violation_ip', 'ip_address'),
        Index('idx_violation_time', 'violated_at'),
        Index('idx_violation_endpoint', 'endpoint'),
    )

    def __repr__(self):
        return (
            f"<RateLimitViolation("
            f"ip={self.ip_address}, "
            f"endpoint={self.endpoint}, "
            f"count={self.violation_count}"
            f")>"
        )

    @classmethod
    def log_violation(cls, db, ip_address: str, endpoint: str, user_agent: str = None, request_path: str = None):
        """
        Log a rate limit violation

        Args:
            db: Database session
            ip_address: IP that violated limit
            endpoint: Endpoint that was hit
            user_agent: User agent string (optional)
            request_path: Full request path (optional)

        Returns:
            RateLimitViolation instance
        """
        violation = cls(
            ip_address=ip_address,
            endpoint=endpoint,
            user_agent=user_agent,
            request_path=request_path,
            violation_count=1
        )

        db.add(violation)
        db.commit()

        return violation

    @classmethod
    def get_recent_violations(cls, db, ip_address: str, minutes: int = 60):
        """
        Get recent violations for an IP

        Args:
            db: Database session
            ip_address: IP to check
            minutes: Time window in minutes

        Returns:
            List of recent violations
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)

        return db.query(cls).filter(
            cls.ip_address == ip_address,
            cls.violated_at >= since
        ).all()

    @classmethod
    def get_violation_count(cls, db, ip_address: str, minutes: int = 60) -> int:
        """
        Get total violation count for an IP in time window

        Args:
            db: Database session
            ip_address: IP to check
            minutes: Time window in minutes

        Returns:
            Total number of violations
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)

        return db.query(cls).filter(
            cls.ip_address == ip_address,
            cls.violated_at >= since
        ).count()

    @classmethod
    def should_auto_block(cls, db, ip_address: str, threshold: int = 10, minutes: int = 60) -> bool:
        """
        Check if IP should be auto-blocked based on violation count

        Args:
            db: Database session
            ip_address: IP to check
            threshold: Number of violations before auto-block
            minutes: Time window in minutes

        Returns:
            True if IP should be blocked, False otherwise
        """
        count = cls.get_violation_count(db, ip_address, minutes)
        return count >= threshold


# For testing
if __name__ == "__main__":
    from database.connection import SessionLocal, engine

    # Create tables
    print("Creating security tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Test IP blocking
    print("\nTesting IP blocking...")
    BlockedIP.block_ip(
        db=db,
        ip_address="192.168.1.100",
        reason="Test block",
        duration_minutes=60,
        blocked_by="AUTO"
    )

    print(f"Is 192.168.1.100 blocked? {BlockedIP.is_ip_blocked(db, '192.168.1.100')}")
    print(f"Is 10.0.0.1 blocked? {BlockedIP.is_ip_blocked(db, '10.0.0.1')}")

    # Test violation logging
    print("\nTesting violation logging...")
    RateLimitViolation.log_violation(
        db=db,
        ip_address="192.168.1.100",
        endpoint="/api/auth/login",
        user_agent="Test Agent"
    )

    count = RateLimitViolation.get_violation_count(db, "192.168.1.100")
    print(f"Violation count: {count}")

    db.close()
    print("\n✅ Security models working correctly!")
