"""
Session Management Service
Purpose: Create and manage bank-specific sessions

Session Flow:
1. User logs in → Homepage (no session yet)
2. User clicks "HDFC" → Session created for HDFC account (24hr)
3. User clicks "ICICI" → Different session created for ICICI (24hr)
4. Each bank account has its own independent session
5. Sessions auto-rotate every 24hrs

Session Format:
SESSION_IDX_BANKCODE_TIMESTAMP_HASH
Example: SESSION_abc123_HDFC_1735000000_xyz789
"""

# [DOC] datetime: used to compute session expiry times and compare against current UTC time
from datetime import datetime, timedelta
# [DOC] Session: SQLAlchemy session type annotation for the database connection
from sqlalchemy.orm import Session
# [DOC] Optional: type hint indicating a function may return None (e.g., no active session found)
from typing import Optional
# [DOC] hashlib: SHA-256 is used to generate an unpredictable session ID from user/bank/time data
import hashlib
# [DOC] time: provides millisecond-precision timestamps used as salt in session ID generation
import time

# [DOC] UserSession alias: the ORM model for the "sessions" table; aliased to avoid conflict with SQLAlchemy's Session
from database.models.session import Session as UserSession
# [DOC] BankAccount: queried to find which bank account a user has at the requested bank code
from database.models.bank_account import BankAccount
# [DOC] User: queried to confirm the user exists before creating a session
from database.models.user import User


class SessionService:
    """Service for managing user sessions"""

    def __init__(self, db: Session):
        """
        Initialize service

        Args:
            db: Database session
        """
        # [DOC] Store the SQLAlchemy database session; all DB queries in this class use self.db
        self.db = db

    def generate_session_id(
        self,
        user_idx: str,
        bank_code: str,
        account_id: int
    ) -> str:
        """
        Generate bank-specific session ID

        Format: SESSION_{idx_part}_{bank_code}_{timestamp}_{hash}

        Args:
            user_idx: User's IDX
            bank_code: Bank code (HDFC, ICICI, etc.)
            account_id: Bank account ID

        Returns:
            str: Session ID
        """
        # [DOC] Millisecond timestamp: used as a time component so two calls within the same second are still different
        timestamp = str(int(time.time() * 1000))  # millisecond precision
        # [DOC] salt: Python's hash() adds extra randomness so collisions are practically impossible
        salt = str(hash(timestamp))

        # [DOC] Combine all identifying components; SHA-256 of this string is the unique fingerprint
        data = f"{user_idx}:{bank_code}:{account_id}:{timestamp}:{salt}"
        session_hash = hashlib.sha256(data.encode()).hexdigest()

        # [DOC] idx_part: last 8 chars of IDX — enough to make the session visually traceable without leaking full IDX
        idx_part = user_idx[-8:]

        # [DOC] Final format: SESSION_{idx_tail}_{bank}_{timestamp_tail}_{hash_prefix}
        # [DOC] timestamp[-6:] keeps only the last 6 digits — enough granularity, short enough to be readable
        return f"SESSION_{idx_part}_{bank_code}_{timestamp[-6:]}_{session_hash[:16]}"

    def create_session(
        self,
        user_idx: str,
        bank_code: str,
        duration_hours: int = 24
    ) -> UserSession:
        """
        Create new session for specific bank account

        Args:
            user_idx: User's IDX
            bank_code: Bank code
            duration_hours: Session duration (default: 24)

        Returns:
            UserSession: Created session

        Raises:
            ValueError: If user or bank account not found
        """
        # [DOC] Verify the user actually exists in the system before issuing a session
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")

        # [DOC] Find the specific bank account for this user at the requested bank
        # [DOC] is_active=True: skip closed or deactivated accounts
        account = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code,
            BankAccount.is_active == True
        ).first()

        if not account:
            raise ValueError(f"No {bank_code} account found for user")

        # [DOC] Check for an existing active, non-expired session — avoid creating duplicates
        existing = self.db.query(UserSession).filter(
            UserSession.user_idx == user_idx,
            UserSession.bank_account_id == account.id,
            UserSession.is_active == True,
            # [DOC] expires_at > now: only reuse sessions that haven't expired yet
            UserSession.expires_at > datetime.utcnow()
        ).first()

        # [DOC] If a valid session already exists, return it immediately — no new row needed
        if existing:
            print(f"♻️  Reusing active session for {bank_code}")
            return existing

        # [DOC] Generate a unique session ID combining the user's IDX, bank code, account ID, and timestamp
        session_id = self.generate_session_id(user_idx, bank_code, account.id)
        # [DOC] expires_at: current UTC time + 24 hours; after this the session must be rotated
        expires_at = datetime.utcnow() + timedelta(hours=duration_hours)

        # [DOC] Build the new session ORM object with all required fields
        session = UserSession(
            session_id=session_id,
            user_idx=user_idx,
            # [DOC] bank_name stores the bank_code string (e.g. "HDFC") for easy filtering
            bank_name=bank_code,
            bank_account_id=account.id,
            expires_at=expires_at,
            is_active=True
        )

        # [DOC] Persist the new session row to the database
        self.db.add(session)
        self.db.commit()
        # [DOC] refresh: reload the object from DB to populate server-generated fields (e.g. id, created_at)
        self.db.refresh(session)

        print(f"✅ Created session for {bank_code}")
        print(f"   Session: {session_id[:40]}...")
        print(f"   Expires: {expires_at}")

        return session

    def get_active_session(
        self,
        user_idx: str,
        bank_code: str
    ) -> Optional[UserSession]:
        """
        Get active session for bank account

        Args:
            user_idx: User's IDX
            bank_code: Bank code

        Returns:
            UserSession or None: Active session if exists
        """
        # [DOC] First find the bank account row; we need its id to look up the session
        account = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code,
            BankAccount.is_active == True
        ).first()

        # [DOC] If the user has no account at this bank, there can be no session — return None
        if not account:
            return None

        # [DOC] Query for a session tied to this exact account that is both active and unexpired
        session = self.db.query(UserSession).filter(
            UserSession.user_idx == user_idx,
            UserSession.bank_account_id == account.id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        ).first()

        return session

    def get_or_create_session(
        self,
        user_idx: str,
        bank_code: str
    ) -> UserSession:
        """
        Get existing session or create new one

        Args:
            user_idx: User's IDX
            bank_code: Bank code

        Returns:
            UserSession: Active session
        """
        # [DOC] Try to reuse an existing active session first — avoids unnecessary session churn
        session = self.get_active_session(user_idx, bank_code)

        # [DOC] If no active session found (e.g., first login or session expired), create a fresh one
        if session:
            return session

        return self.create_session(user_idx, bank_code)

    def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate session (logout)

        Args:
            session_id: Session ID

        Returns:
            bool: True if invalidated
        """
        # [DOC] Look up the specific session row by its session_id string
        session = self.db.query(UserSession).filter(
            UserSession.session_id == session_id
        ).first()

        # [DOC] If session doesn't exist (already deleted or never created), return False
        if not session:
            return False

        # [DOC] Soft-deactivate: set is_active=False instead of deleting so audit trail is preserved
        session.is_active = False
        self.db.commit()

        print(f"🚪 Session invalidated: {session_id[:40]}...")

        return True

    def invalidate_all_user_sessions(self, user_idx: str) -> int:
        """
        Invalidate all sessions for user (logout all devices)

        Args:
            user_idx: User's IDX

        Returns:
            int: Number of sessions invalidated
        """
        # [DOC] Fetch all currently active sessions for this user across all their bank accounts
        sessions = self.db.query(UserSession).filter(
            UserSession.user_idx == user_idx,
            UserSession.is_active == True
        ).all()

        # [DOC] Deactivate each session in memory; a single commit below persists all changes at once
        for session in sessions:
            session.is_active = False

        # [DOC] Single commit for all deactivations — more efficient than committing inside the loop
        self.db.commit()

        print(f"🚪 Invalidated {len(sessions)} sessions for user")

        return len(sessions)


# Testing
if __name__ == "__main__":
    """Test session service"""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator

    print("=== Session Service Testing ===\n")

    db = SessionLocal()
    service = SessionService(db)

    try:
        test_idx = IDXGenerator.generate("TESTA1234P", "100001")

        # Test 1: Create HDFC session
        print("Test 1: Create HDFC Session")
        hdfc_session = service.create_session(test_idx, "HDFC")
        print(f"  Session: {hdfc_session.session_id[:40]}...")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Create ICICI session
        print("Test 2: Create ICICI Session")
        icici_session = service.create_session(test_idx, "ICICI")
        print(f"  Session: {icici_session.session_id[:40]}...")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Get or create (should reuse)
        print("Test 3: Get or Create (Reuse)")
        reused = service.get_or_create_session(test_idx, "HDFC")
        assert reused.id == hdfc_session.id
        print("  ✅ Reused existing session")
        print("  ✅ Test 3 passed!\n")

        print("=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)

    finally:
        db.close()
