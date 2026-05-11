# [DOC] IPBlocker — the service layer that controls which IP addresses are banned from the API.
# [DOC] Two mechanisms work together:
# [DOC]   1. Rate-limit violations are logged (rate_limit_violations table).
# [DOC]   2. When an IP accumulates enough violations, it is added to blocked_ips and rejected at request time.
# [DOC] This class is called by the rate_limiter middleware (on_rate_limit_breach) and by admin tools.

"""
IP Blocker Service
Purpose: Manage IP blocking for DDoS protection and security

Features:
- Check if IP is blocked
- Block/unblock IPs
- Automatic blocking based on violation threshold
- Query violation history
"""

from database.connection import SessionLocal
# [DOC] BlockedIP: ORM model for the blocked_ips table; RateLimitViolation: ORM model for violation history.
from database.models.security import BlockedIP, RateLimitViolation
# [DOC] settings provides DDOS_THRESHOLD and DDOS_BLOCK_DURATION_MINUTES.
from config.settings import settings


class IPBlocker:
    """
    IP blocking service for DDoS protection

    Usage:
        >>> # Check if IP is blocked
        >>> if IPBlocker.is_blocked("192.168.1.100"):
        ...     return "Access denied", 403
        >>>
        >>> # Auto-block based on violations
        >>> IPBlocker.check_and_auto_block("192.168.1.100")
        >>>
        >>> # Manual block
        >>> IPBlocker.block("10.0.0.50", "Malicious activity", permanent=True, admin="admin@example.com")
    """

    @staticmethod
    def is_blocked(ip_address: str) -> bool:
        """
        Check if an IP address is currently blocked

        Args:
            ip_address: IP address to check

        Returns:
            True if blocked, False otherwise
        """
        # [DOC] Open a DB session for this single query; always close it in the finally block.
        db = SessionLocal()
        try:
            # [DOC] BlockedIP.is_ip_blocked() checks for a row with this IP whose unblock_at is in the future
            # [DOC] (or is NULL for permanent blocks).
            return BlockedIP.is_ip_blocked(db, ip_address)
        finally:
            db.close()

    @staticmethod
    def block(ip_address: str, reason: str, duration_minutes: int = None, admin: str = "AUTO"):
        """
        Block an IP address

        Args:
            ip_address: IP to block
            reason: Reason for blocking
            duration_minutes: Block duration (None = permanent)
            admin: Who is blocking (default: "AUTO")

        Returns:
            BlockedIP instance
        """
        db = SessionLocal()
        try:
            # [DOC] BlockedIP.block_ip() inserts a new row (or updates an existing one) in blocked_ips.
            # [DOC] duration_minutes=None means the block has no expiry (permanent ban).
            return BlockedIP.block_ip(
                db=db,
                ip_address=ip_address,
                reason=reason,
                duration_minutes=duration_minutes,
                blocked_by=admin  # [DOC] Records whether this was an automatic or human-triggered block.
            )
        finally:
            db.close()

    @staticmethod
    def unblock(ip_address: str) -> bool:
        """
        Unblock an IP address

        Args:
            ip_address: IP to unblock

        Returns:
            True if unblocked, False if not found
        """
        db = SessionLocal()
        try:
            # [DOC] BlockedIP.unblock_ip() deletes the row (or sets unblock_at = now) for this IP.
            return BlockedIP.unblock_ip(db, ip_address)
        finally:
            db.close()

    @staticmethod
    def log_violation(ip_address: str, endpoint: str, user_agent: str = None, request_path: str = None):
        """
        Log a rate limit violation

        Args:
            ip_address: IP that violated limit
            endpoint: Endpoint that was hit
            user_agent: User agent string (optional)
            request_path: Full request path (optional)
        """
        db = SessionLocal()
        try:
            # [DOC] Inserts one row into rate_limit_violations; cumulative count is used by check_and_auto_block().
            RateLimitViolation.log_violation(
                db=db,
                ip_address=ip_address,
                endpoint=endpoint,
                user_agent=user_agent,
                request_path=request_path
            )
        finally:
            db.close()

    @staticmethod
    def check_and_auto_block(ip_address: str, threshold: int = None, window_minutes: int = 60) -> bool:
        """
        Check if IP should be auto-blocked based on violations

        Uses DDOS_THRESHOLD from settings if threshold not specified.

        Args:
            ip_address: IP to check
            threshold: Number of violations before block (default: from settings)
            window_minutes: Time window for counting violations

        Returns:
            True if IP was auto-blocked, False otherwise
        """
        # [DOC] Use the settings-configured threshold if the caller didn't pass one explicitly.
        if threshold is None:
            threshold = getattr(settings, 'DDOS_THRESHOLD', 10)

        db = SessionLocal()
        try:
            # [DOC] should_auto_block() counts violations in the last window_minutes and compares to threshold.
            if RateLimitViolation.should_auto_block(db, ip_address, threshold, window_minutes):
                # [DOC] Read the block duration from settings (default: 60 minutes).
                duration = getattr(settings, 'DDOS_BLOCK_DURATION_MINUTES', 60)

                # [DOC] Insert the blocked_ips row — subsequent requests from this IP will be rejected by check_ip_blocked().
                BlockedIP.block_ip(
                    db=db,
                    ip_address=ip_address,
                    reason=f"Automatic block: Exceeded {threshold} violations in {window_minutes} minutes",
                    duration_minutes=duration,
                    blocked_by="AUTO"
                )

                print(f"🚫 Auto-blocked IP: {ip_address} (threshold: {threshold} violations)")
                return True

            return False  # [DOC] Violation count is below threshold — no block applied.

        finally:
            db.close()

    @staticmethod
    def get_violation_count(ip_address: str, minutes: int = 60) -> int:
        """
        Get violation count for an IP

        Args:
            ip_address: IP to check
            minutes: Time window

        Returns:
            Number of violations
        """
        db = SessionLocal()
        try:
            # [DOC] Counts rows in rate_limit_violations WHERE ip = ? AND created_at >= now - minutes.
            return RateLimitViolation.get_violation_count(db, ip_address, minutes)
        finally:
            db.close()

    @staticmethod
    def get_blocked_ips():
        """
        Get all currently blocked IPs

        Returns:
            List of BlockedIP instances
        """
        db = SessionLocal()
        try:
            # [DOC] Returns all rows from blocked_ips — includes expired blocks (admin use; filter by unblock_at if needed).
            return db.query(BlockedIP).all()
        finally:
            db.close()


# For testing
if __name__ == "__main__":
    print("=== IP Blocker Service Test ===\n")

    # Test blocking
    print("1. Testing IP blocking...")
    IPBlocker.block(
        ip_address="192.168.1.100",
        reason="Test block",
        duration_minutes=60
    )
    print(f"   Is 192.168.1.100 blocked? {IPBlocker.is_blocked('192.168.1.100')}")

    # Test violation logging
    print("\n2. Testing violation logging...")
    for i in range(5):
        IPBlocker.log_violation(
            ip_address="10.0.0.50",
            endpoint="/api/auth/login",
            user_agent="Test Agent"
        )
    print(f"   Violations for 10.0.0.50: {IPBlocker.get_violation_count('10.0.0.50')}")

    # Test auto-blocking
    print("\n3. Testing auto-blocking (threshold: 3)...")
    for i in range(5):
        IPBlocker.log_violation(
            ip_address="172.16.0.1",
            endpoint="/api/transactions/send"
        )

    if IPBlocker.check_and_auto_block("172.16.0.1", threshold=3):
        print("   ✅ IP auto-blocked after exceeding threshold")
    else:
        print("   ❌ IP not auto-blocked")

    print(f"   Is 172.16.0.1 blocked? {IPBlocker.is_blocked('172.16.0.1')}")

    # Test unblocking
    print("\n4. Testing unblocking...")
    IPBlocker.unblock("192.168.1.100")
    print(f"   Is 192.168.1.100 blocked? {IPBlocker.is_blocked('192.168.1.100')}")

    print("\n✅ IP Blocker service working correctly!")
