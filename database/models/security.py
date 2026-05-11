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

# [DOC] SQLAlchemy column types and Index for defining ORM table schemas
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
# [DOC] func provides SQL server-side functions; func.now() generates a NOW() default in the DB
from sqlalchemy.sql import func
# [DOC] datetime and timedelta used for calculating block expiry times
from datetime import datetime, timedelta
# [DOC] Base is the SQLAlchemy declarative base; every ORM model class must inherit from it
from database.connection import Base


# [DOC] ORM model for the blocked_ips table — one row per blocked IP address
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

    # [DOC] __tablename__ tells SQLAlchemy which PostgreSQL table this class maps to
    __tablename__ = "blocked_ips"

    # [DOC] Auto-incrementing surrogate primary key — never exposed to users
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # [DOC] Stores IPv4 (max 15 chars) or IPv6 (max 45 chars) addresses; unique per row
    # IP address (IPv4 or IPv6)
    ip_address = Column(
        String(45),  # IPv6 max length is 45 characters
        nullable=False,
        unique=True,
        index=True,
        comment="Blocked IP address (IPv4 or IPv6)"
    )

    # [DOC] Human-readable explanation of why this IP was blocked (shown to admins)
    # Block details
    reason = Column(
        String(255),
        nullable=True,
        comment="Reason for blocking this IP"
    )

    # [DOC] Records the exact moment the block was created; defaults to server-side NOW()
    blocked_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="When this IP was blocked"
    )

    # [DOC] NULL means the block never expires (permanent); a timestamp means temporary
    expires_at = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="When block expires (NULL = permanent)"
    )

    # [DOC] 'AUTO' for rate-limiter-triggered blocks; admin username for manually imposed blocks
    blocked_by = Column(
        String(100),
        nullable=True,
        comment="Who blocked this IP ('AUTO' for automatic, or admin username)"
    )

    # [DOC] Composite index table args: one index on ip_address for fast lookup,
    # one on expires_at to efficiently find and clean up expired blocks
    # Indexes
    __table_args__ = (
        Index('idx_blocked_ip', 'ip_address'),
        Index('idx_blocked_expiry', 'expires_at'),
    )

    # [DOC] String representation used in logs and debug output — shows key fields briefly
    def __repr__(self):
        return (
            f"<BlockedIP("
            f"ip={self.ip_address}, "
            f"reason={self.reason[:30] if self.reason else None}, "
            f"expires={self.expires_at}"
            f")>"
        )

    # [DOC] Returns True if this block has a finite expiry AND that expiry is in the past
    def is_expired(self):
        """Check if block has expired"""
        if self.expires_at is None:
            # [DOC] No expiry set → permanent block → never consider it expired
            return False  # Permanent block
        return datetime.utcnow() > self.expires_at

    # [DOC] Convenience check: True when expires_at is NULL (meaning no end date)
    def is_permanent(self):
        """Check if this is a permanent block"""
        return self.expires_at is None

    # [DOC] Class method (no instance needed): check the DB for a current active block on an IP
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
        # [DOC] Look up the BlockedIP row for this address; None means not blocked at all
        blocked = db.query(cls).filter(cls.ip_address == ip_address).first()

        if not blocked:
            # [DOC] No row found → IP is not blocked
            return False

        # [DOC] If an expiry time has passed, remove the row and report the IP as unblocked
        # Check if expired
        if blocked.is_expired():
            # Remove expired block
            db.delete(blocked)
            db.commit()
            return False

        # [DOC] Row exists and has not expired → IP is currently blocked
        return True

    # [DOC] Class method: insert or update a block record for the given IP address
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
        # [DOC] Check for a pre-existing block on this IP to decide whether to insert or update
        # Check if already blocked
        existing = db.query(cls).filter(cls.ip_address == ip_address).first()

        if existing:
            # [DOC] Update the existing block in-place so unique constraint on ip_address is not violated
            # Update existing block
            existing.reason = reason
            existing.blocked_at = func.now()
            existing.blocked_by = blocked_by

            # [DOC] Recalculate expiry: if duration given, compute new future timestamp; else make permanent
            if duration_minutes:
                existing.expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            else:
                existing.expires_at = None

            db.commit()
            return existing

        # [DOC] No existing block found — create a brand new BlockedIP row
        # Create new block
        expires_at = None
        if duration_minutes:
            # [DOC] Convert minutes to an absolute timestamp so expiry survives server restarts
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)

        blocked = cls(
            ip_address=ip_address,
            reason=reason,
            blocked_by=blocked_by,
            expires_at=expires_at
        )

        db.add(blocked)
        db.commit()

        # [DOC] Return the new BlockedIP instance so callers can inspect or log it
        return blocked

    # [DOC] Class method: remove a block from the DB so the IP can access the API again
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
        # [DOC] Look up the block row; if it doesn't exist the IP is already unblocked
        blocked = db.query(cls).filter(cls.ip_address == ip_address).first()

        if blocked:
            # [DOC] Delete the row and commit so the change takes effect immediately
            db.delete(blocked)
            db.commit()
            return True

        # [DOC] Return False to indicate no action was needed (IP wasn't blocked)
        return False


# [DOC] ORM model for the rate_limit_violations table — one row per detected violation event
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

    # [DOC] Maps to the rate_limit_violations PostgreSQL table
    __tablename__ = "rate_limit_violations"

    # [DOC] Surrogate primary key — auto-increments per violation event
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # [DOC] The IPv4/IPv6 address that triggered the rate limit; indexed for fast group-by
    # Violation details
    ip_address = Column(
        String(45),
        nullable=False,
        index=True,
        comment="IP address that violated rate limit"
    )

    # [DOC] The API route that was hammered, e.g. '/api/auth/login'; indexed for per-endpoint analysis
    endpoint = Column(
        String(255),
        nullable=False,
        index=True,
        comment="API endpoint that was hit"
    )

    # [DOC] Server-side timestamp of when this violation was detected; indexed for time-window queries
    violated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        index=True,
        comment="When violation occurred"
    )

    # [DOC] How many times the limit was exceeded in this event (usually 1; may be batched)
    violation_count = Column(
        Integer,
        nullable=False,
        default=1,
        comment="How many times rate limit was exceeded"
    )

    # [DOC] Stores the raw User-Agent header for bot fingerprinting analysis
    # Request metadata
    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string from request"
    )

    # [DOC] Full URL path including query string — useful for targeted attack forensics
    request_path = Column(
        Text,
        nullable=True,
        comment="Full request path with query parameters"
    )

    # [DOC] Three indexes speed up the most common queries:
    # by IP (to count violations for a given source),
    # by time (to filter to a recent window),
    # by endpoint (to find which routes are being targeted)
    # Indexes
    __table_args__ = (
        Index('idx_violation_ip', 'ip_address'),
        Index('idx_violation_time', 'violated_at'),
        Index('idx_violation_endpoint', 'endpoint'),
    )

    # [DOC] Compact string representation for logs — shows IP, endpoint, and count
    def __repr__(self):
        return (
            f"<RateLimitViolation("
            f"ip={self.ip_address}, "
            f"endpoint={self.endpoint}, "
            f"count={self.violation_count}"
            f")>"
        )

    # [DOC] Class method: insert one new violation row into the DB and return it
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
        # [DOC] Create a new violation record; violated_at defaults to NOW() in the DB
        violation = cls(
            ip_address=ip_address,
            endpoint=endpoint,
            user_agent=user_agent,
            request_path=request_path,
            violation_count=1
        )

        db.add(violation)
        db.commit()

        # [DOC] Return the saved row so callers can inspect generated fields like id and violated_at
        return violation

    # [DOC] Class method: retrieve all violation rows for a given IP within the last N minutes
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
        # [DOC] Calculate the start of the time window by subtracting minutes from now
        since = datetime.utcnow() - timedelta(minutes=minutes)

        # [DOC] Filter by both ip_address and the time window to get recent events only
        return db.query(cls).filter(
            cls.ip_address == ip_address,
            cls.violated_at >= since
        ).all()

    # [DOC] Class method: return the count of violations for an IP within the last N minutes
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
        # [DOC] Reuse the same time-window logic; .count() issues a COUNT(*) SQL query
        since = datetime.utcnow() - timedelta(minutes=minutes)

        return db.query(cls).filter(
            cls.ip_address == ip_address,
            cls.violated_at >= since
        ).count()

    # [DOC] Class method: decide whether to auto-block this IP based on recent violation count
    # Returns True when the count meets or exceeds the threshold — caller then calls BlockedIP.block_ip()
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
        # [DOC] Delegate counting to get_violation_count for consistent time-window logic
        count = cls.get_violation_count(db, ip_address, minutes)
        # [DOC] Threshold comparison: >= means exactly threshold violations triggers a block
        return count >= threshold


# [DOC] Inline test block — only runs when this file is executed directly (not when imported)
# For testing
if __name__ == "__main__":
    from database.connection import SessionLocal, engine

    # [DOC] Ensure both security tables exist before running tests
    # Create tables
    print("Creating security tables...")
    Base.metadata.create_all(bind=engine)

    # [DOC] Open a fresh DB session for the test operations below
    db = SessionLocal()

    # [DOC] Test the block_ip class method with a 60-minute temporary block
    # Test IP blocking
    print("\nTesting IP blocking...")
    BlockedIP.block_ip(
        db=db,
        ip_address="192.168.1.100",
        reason="Test block",
        duration_minutes=60,
        blocked_by="AUTO"
    )

    # [DOC] Verify is_ip_blocked returns True for the newly blocked IP and False for an unknown one
    print(f"Is 192.168.1.100 blocked? {BlockedIP.is_ip_blocked(db, '192.168.1.100')}")
    print(f"Is 10.0.0.1 blocked? {BlockedIP.is_ip_blocked(db, '10.0.0.1')}")

    # [DOC] Test the log_violation class method and then retrieve the count to verify persistence
    # Test violation logging
    print("\nTesting violation logging...")
    RateLimitViolation.log_violation(
        db=db,
        ip_address="192.168.1.100",
        endpoint="/api/auth/login",
        user_agent="Test Agent"
    )

    # [DOC] get_violation_count should return 1 after the single log_violation call above
    count = RateLimitViolation.get_violation_count(db, "192.168.1.100")
    print(f"Violation count: {count}")

    # [DOC] Close the session to release the connection back to the pool
    db.close()
    print("\n✅ Security models working correctly!")
