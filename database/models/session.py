"""
Session Model - Manage 24-Hour Rotating Sessions

Purpose: Track active session IDs with expiry times

Session Lifecycle:
1. User logs in → Create session → Store with 24h expiry
2. User makes transaction → Validate session still active
3. After 24 hours → Session expires
4. Background job → Delete expired sessions from database

Privacy Protection:
- Session IDs are temporary (rotate every 24h)
- Cannot link sessions across days without database
- Database mapping is encrypted in private blockchain
"""

# [DOC] Column types and ForeignKey for linking sessions to bank accounts
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Boolean, Index
# [DOC] func gives server-side SQL functions; used for server_default=func.now()
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from database.connection import Base
# [DOC] settings holds SESSION_ROTATION_HOURS and other configurable values
from config.settings import settings
from sqlalchemy.orm import relationship


class Session(Base):
    """
    Active session tracking table

    Each session represents:
    - One user's access to one bank account
    - Valid for 24 hours (configurable)
    - Automatically expires after timeout
    - Used to map session_id → IDX (encrypted)

    Example:
        >>> from database.connection import SessionLocal
        >>> from core.crypto.session_id import SessionIDGenerator
        >>>
        >>> db = SessionLocal()
        >>>
        >>> # Create new session
        >>> session_id, expiry = SessionIDGenerator.generate(
        ...     idx="IDX_9ada28aeb...",
        ...     bank_name="HDFC"
        ... )
        >>>
        >>> session = Session(
        ...     session_id=session_id,
        ...     user_idx="IDX_9ada28aeb...",
        ...     bank_name="HDFC",
        ...     expires_at=expiry
        ... )
        >>>
        >>> db.add(session)
        >>> db.commit()
    """

    # [DOC] Maps this Python class to the 'sessions' table in PostgreSQL
    __tablename__ = 'sessions'

    # [DOC] id: internal auto-increment primary key — not the session ID shown on the blockchain
    id = Column(Integer, primary_key=True, autoincrement=True)

    # [DOC] session_id: the public 24-hour rotating pseudonym, format "SESSION_{bank}_{hash}_{date}"
    # [DOC] This is what appears on the public blockchain in place of the user's real IDX
    # [DOC] unique=True: no two active sessions can share the same token; index=True for O(log n) lookup on every transaction
    session_id = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Temporary session ID (rotates every 24h)"
    )

    # [DOC] user_idx: the PERMANENT pseudonym of the user who owns this session
    # [DOC] This mapping (session_id → user_idx) is the sensitive link that the system protects
    # [DOC] index=True: speeds up "find all sessions for user X" queries (used during transaction initiation)
    user_idx = Column(
        String(100),
        nullable=False,
        index=True,
        comment="User's permanent IDX"
    )

    # [DOC] bank_name: identifies which bank this session belongs to (one session per bank account per 24h window)
    # [DOC] A user with accounts at HDFC and ICICI has two simultaneous sessions — one per bank
    bank_name = Column(
        String(50),
        nullable=False,
        comment="Bank account identifier (HDFC, ICICI, etc.)"
    )

    # [DOC] bank_account_id: FK to bank_accounts.id — links this session to a specific numbered account
    # [DOC] nullable=True because sessions created before migration may not have a direct account link
    bank_account_id = Column(
        Integer,
        ForeignKey('bank_accounts.id'),
        nullable=True,
        index=True)
    # bank_account =relationship("BankAccount",
    #                             back_populates="sessions")

    # [DOC] expires_at: the exact UTC datetime when this session ID stops being valid
    # [DOC] Background worker (core/session/rotation.py) deactivates sessions past this timestamp
    # [DOC] index=True: background job queries "WHERE expires_at < NOW()" every hour — needs to be fast
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When this session expires (24h from creation)"
    )

    # [DOC] is_active: False after the user logs out OR after the background worker deactivates expired sessions
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether session is currently active"
    )

    # [DOC] created_at: set by the DB server when the session row is first inserted (on login)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When session was created"
    )

    # [DOC] last_used_at: automatically updated by the DB whenever this row is touched (e.g. a tx uses this session)
    last_used_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last transaction using this session"
    )

    # [DOC] Named indexes complement the inline index=True flags with explicit names for DB query plan readability
    __table_args__ = (
        Index('idx_session_id', 'session_id'),      # [DOC] Primary lookup: "find session by session_id" on every tx
        Index('idx_session_user', 'user_idx'),      # [DOC] "Find all active sessions for user X" (transaction routing)
        Index('idx_session_expiry', 'expires_at'),  # [DOC] Background cleanup: "WHERE expires_at < NOW()"
        Index('idx_session_active', 'is_active'),   # [DOC] Filter only active sessions quickly
    )

    def is_expired(self) -> bool:
        """
        Check if session has expired

        Returns:
            bool: True if expired, False if still valid

        Example:
            >>> session = db.query(Session).first()
            >>> if session.is_expired():
            ...     print("Session expired, generate new one")
            ... else:
            ...     print("Session still valid")
        """
        # [DOC] Compare current UTC time to expires_at; pass tzinfo to avoid naive/aware mismatch error
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    def time_remaining(self) -> timedelta:
        """
        Get time remaining until expiry

        Returns:
            timedelta: Time remaining (negative if expired)

        Example:
            >>> session = db.query(Session).first()
            >>> remaining = session.time_remaining()
            >>> print(f"Session expires in {remaining.total_seconds()/3600:.1f} hours")
        """
        # [DOC] Subtract current time from expiry; result is negative if the session is already expired
        return self.expires_at - datetime.now(self.expires_at.tzinfo)

    def deactivate(self):
        """
        Manually deactivate session (e.g., user logs out)

        Example:
            >>> # User logs out
            >>> session.deactivate()
            >>> db.commit()
        """
        # [DOC] Set is_active=False; caller must call db.commit() to persist this change to PostgreSQL
        self.is_active = False

    def __repr__(self):
        """String representation"""
        status = "active" if self.is_active and not self.is_expired() else "inactive"
        return (
            f"<Session(id={self.id}, "
            f"session={self.session_id[:20]}..., "
            f"bank={self.bank_name}, "
            f"status={status})>"
        )

    def to_dict(self):
        """
        Convert to dictionary for API responses

        Returns:
            dict: Session data
        """
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_idx': self.user_idx,
            'bank_name': self.bank_name,
            'expires_at': self.expires_at.isoformat(),
            'is_active': self.is_active,
            # [DOC] is_expired() is computed at call time — not stored — so it always reflects the current clock
            'is_expired': self.is_expired(),
            # [DOC] time_remaining_seconds: handy for UIs to display a countdown without client-side date math
            'time_remaining_seconds': self.time_remaining().total_seconds(),
            'created_at': self.created_at.isoformat(),
            'last_used_at': self.last_used_at.isoformat()
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test the Session model
    Run: python3 -m database.models.session
    """
    from database.connection import engine, SessionLocal
    from database.models.user import User
    from core.crypto.idx_generator import IDXGenerator
    from core.crypto.session_id import SessionIDGenerator
    from decimal import Decimal

    print("=== Session Model Testing ===\n")

    # Create table
    print("Creating sessions table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")

    # Create session
    db = SessionLocal()

    try:
        # Cleanup old test data
        print("Test 0: Cleanup")
        db.query(Session).delete()
        db.commit()
        print("✅ Cleanup complete!\n")

        # Get or create test user
        print("Test 1: Setup Test User")
        user = db.query(User).filter(User.pan_card == "RAJSH1234K").first()

        if not user:
            idx = IDXGenerator.generate("RAJSH1234K", "100001")
            user = User(
                idx=idx,
                pan_card="RAJSH1234K",
                full_name="Rajesh Kumar",
                balance=Decimal('10000.00')
            )
            db.add(user)
            db.commit()

        print(f"  User: {user.full_name} ({user.idx[:20]}...)")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Create session
        print("Test 2: Create Session for HDFC Account")

        session_id, expiry = SessionIDGenerator.generate(
            idx=user.idx,
            bank_name="HDFC"
        )

        session = Session(
            session_id=session_id,
            user_idx=user.idx,
            bank_name="HDFC",
            expires_at=expiry
        )

        db.add(session)
        db.commit()

        print(f"  Session: {session}")
        print(f"  Session ID: {session.session_id[:40]}...")
        print(f"  Expires: {session.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Active: {session.is_active}")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Create session for different bank
        print("Test 3: Create Session for ICICI Account (Same User)")

        session_id2, expiry2 = SessionIDGenerator.generate(
            idx=user.idx,
            bank_name="ICICI"
        )

        session2 = Session(
            session_id=session_id2,
            user_idx=user.idx,
            bank_name="ICICI",
            expires_at=expiry2
        )

        db.add(session2)
        db.commit()

        print(f"  Session: {session2}")
        print(f"  Different session ID: {session.session_id != session2.session_id}")
        print("  ✅ Test 3 passed!\n")

        # Test 4: Check expiry
        print("Test 4: Check Session Validity")

        is_expired = session.is_expired()
        time_left = session.time_remaining()

        print(f"  Is expired: {is_expired}")
        print(f"  Time remaining: {time_left.total_seconds()/3600:.1f} hours")
        assert not is_expired, "New session should not be expired!"
        print("  ✅ Test 4 passed!\n")

        # Test 5: Query by user
        print("Test 5: Get All Sessions for User")

        user_sessions = db.query(Session).filter(
            Session.user_idx == user.idx,
            Session.is_active == True
        ).all()

        print(f"  Active sessions: {len(user_sessions)}")
        for s in user_sessions:
            print(f"    - {s.bank_name}: {s.session_id[:30]}...")

        assert len(user_sessions) == 2  # HDFC + ICICI
        print("  ✅ Test 5 passed!\n")

        # Test 6: Deactivate session
        print("Test 6: Deactivate Session (User Logout)")

        session.deactivate()
        db.commit()

        db.refresh(session)
        print(f"  Session active: {session.is_active}")
        assert not session.is_active
        print("  ✅ Test 6 passed!\n")

        # Test 7: to_dict
        print("Test 7: Session Dictionary")

        data = session2.to_dict()
        print(f"  Dictionary keys: {list(data.keys())}")
        print(f"  Time remaining: {data['time_remaining_seconds']/3600:.1f} hours")
        print("  ✅ Test 7 passed!\n")

        # Test 8: Find expired sessions (simulate)
        print("Test 8: Find Expired Sessions")

        # Create a session that's already expired (for testing)
        past_expiry = datetime.now() - timedelta(hours=1)
        expired_session = Session(
            session_id="SESSION_EXPIRED_TEST",
            user_idx=user.idx,
            bank_name="SBI",
            expires_at=past_expiry,
            is_active=True
        )

        db.add(expired_session)
        db.commit()

        # Find expired sessions
        expired = db.query(Session).filter(
            Session.expires_at < datetime.now()
        ).all()

        print(f"  Expired sessions found: {len(expired)}")
        for s in expired:
            print(f"    - {s.bank_name}: Expired {abs(s.time_remaining().total_seconds()/3600):.1f} hours ago")

        assert len(expired) >= 1
        print("  ✅ Test 8 passed!\n")

        print("=" * 50)
        print("✅ All Session model tests passed!")
        print("")
        print("Session Summary:")
        total = db.query(Session).count()
        active = db.query(Session).filter(Session.is_active == True).count()
        expired = db.query(Session).filter(Session.expires_at < datetime.now()).count()
        print(f"  Total sessions: {total}")
        print(f"  Active: {active}")
        print(f"  Expired: {expired}")
        print("=" * 50)

    finally:
        db.close()
