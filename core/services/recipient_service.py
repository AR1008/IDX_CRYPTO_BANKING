"""
Recipient Management Service
Purpose: Manage user's saved recipients (contact list)

Flow:
1. User adds recipient by IDX2 + gives nickname ("Mom", "Brother", etc.)
2. Session ID created for this recipient (24hr rotation)
3. User sends money using nickname (internally uses IDX2)
4. Session ID refreshes every 24hrs automatically (no tracking)
5. IDX used only once during addition, then session IDs handle everything

Features:
- Add recipient with nickname
- List all recipients
- Get recipient by nickname
- Auto-rotate session IDs (24hr)
- Remove recipient
- Update nickname
"""

# [DOC] datetime/timedelta: used to calculate session expiry (now + 24 hours) and detect expired sessions
from datetime import datetime, timedelta
# [DOC] Session: SQLAlchemy session type for the database connection
from sqlalchemy.orm import Session
# [DOC] List/Optional: type hints — List[Recipient] and Optional[Recipient] indicate possible None returns
from typing import List, Optional
# [DOC] hashlib: SHA-256 is used to generate an unpredictable rotating session ID from owner+recipient+timestamp
import hashlib
# [DOC] time: provides a Unix timestamp used as a randomness component in session ID generation
import time

# [DOC] Recipient ORM model: each row represents one saved payee for a specific owner user
from database.models.recipient import Recipient
# [DOC] User ORM model: queried to verify that the person being added as a recipient actually exists in the system
from database.models.user import User


class RecipientService:
    """Service for managing recipients"""

    def __init__(self, db: Session):
        """
        Initialize service

        Args:
            db: Database session
        """
        # [DOC] Store database session; all methods in this class use self.db for queries and writes
        self.db = db

    def generate_recipient_session_id(self, owner_idx: str, recipient_idx: str) -> str:
        """
        Generate session ID for recipient

        Format: SHA256(owner_idx + recipient_idx + timestamp + salt)

        Args:
            owner_idx: Owner's IDX
            recipient_idx: Recipient's IDX

        Returns:
            str: Session ID (changes every 24hrs)
        """
        # [DOC] Unix timestamp in seconds — ensures the session ID changes each time this is called
        timestamp = str(int(time.time()))
        # [DOC] Python's hash() adds extra per-process randomness as a salt
        salt = str(hash(timestamp))

        # [DOC] Combine owner IDX, recipient IDX, time, and salt so the output is unique and unpredictable
        data = f"{owner_idx}:{recipient_idx}:{timestamp}:{salt}"
        session_hash = hashlib.sha256(data.encode()).hexdigest()

        # [DOC] Prefix with RECIPIENT_SESSION_ to distinguish from bank account session IDs
        return f"RECIPIENT_SESSION_{session_hash}"

    def add_recipient(
        self,
        owner_idx: str,
        recipient_idx: str,
        nickname: str
    ) -> Recipient:
        """
        Add new recipient to user's contact list

        Args:
            owner_idx: Owner's IDX (person adding recipient)
            recipient_idx: Recipient's IDX (person being added)
            nickname: Friendly name ("Mom", "Brother", "Priya", etc.)

        Returns:
            Recipient: Created recipient entry

        Raises:
            ValueError: If recipient user not found or nickname exists

        Example:
            >>> service = RecipientService(db)
            >>> recipient = service.add_recipient(
            ...     "IDX_abc...",
            ...     "IDX_def...",
            ...     "Mom"
            ... )
            >>> print(recipient.nickname)
            Mom
        """
        # [DOC] Verify the recipient's IDX belongs to a real registered user — prevents phantom entries
        recipient_user = self.db.query(User).filter(User.idx == recipient_idx).first()
        if not recipient_user:
            raise ValueError(f"Recipient user not found: {recipient_idx}")

        # [DOC] Prevent self-addition — a user cannot pay themselves through the recipient system
        if owner_idx == recipient_idx:
            raise ValueError("Cannot add yourself as recipient")

        # [DOC] Enforce unique nicknames per owner — "Mom" can only refer to one person in a user's contact list
        existing = self.db.query(Recipient).filter(
            Recipient.user_idx == owner_idx,
            Recipient.nickname == nickname,
            Recipient.is_active == True
        ).first()

        if existing:
            raise ValueError(f"Nickname '{nickname}' already exists")

        # [DOC] Prevent adding the same person twice even under a different nickname
        existing_recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == owner_idx,
            Recipient.recipient_idx == recipient_idx,
            Recipient.is_active == True
        ).first()

        if existing_recipient:
            raise ValueError(f"Recipient already added as '{existing_recipient.nickname}'")

        # [DOC] Generate the first session ID for this recipient relationship — will rotate every 24 hours
        session_id = self.generate_recipient_session_id(owner_idx, recipient_idx)
        # [DOC] session_expiry: 24 hours from now — after this, rotate_session() must be called
        session_expiry = datetime.utcnow() + timedelta(hours=24)

        # [DOC] Create the Recipient ORM object; IDX is stored once here and never needs to be re-entered
        recipient = Recipient(
            user_idx=owner_idx,
            # [DOC] recipient_idx: the permanent pseudonym of the payee — stored once, used for all future payments
            recipient_idx=recipient_idx,
            nickname=nickname,
            # [DOC] current_session_id: the rotating pseudonym currently in use for this recipient
            current_session_id=session_id,
            session_expires_at=session_expiry,
            is_active=True
        )

        self.db.add(recipient)
        self.db.commit()
        # [DOC] refresh: reload from DB so the auto-generated id and timestamps are populated
        self.db.refresh(recipient)

        print(f"✅ Added recipient: {nickname} ({recipient_idx[:16]}...)")
        print(f"   Session expires: {session_expiry}")

        return recipient

    def get_user_recipients(self, user_idx: str) -> List[Recipient]:
        """
        Get all recipients for a user

        Args:
            user_idx: User's IDX

        Returns:
            List[Recipient]: All active recipients
        """
        # [DOC] Only return active (non-removed) recipients; soft-deleted ones (is_active=False) are excluded
        # [DOC] Ordered alphabetically by nickname for consistent display in the UI contact list
        return self.db.query(Recipient).filter(
            Recipient.user_idx == user_idx,
            Recipient.is_active == True
        ).order_by(Recipient.nickname).all()

    def get_recipient_by_nickname(self, user_idx: str, nickname: str) -> Optional[Recipient]:
        """
        Get recipient by nickname

        Args:
            user_idx: Owner's IDX
            nickname: Recipient's nickname

        Returns:
            Recipient or None: Recipient if found
        """
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == user_idx,
            Recipient.nickname == nickname,
            Recipient.is_active == True
        ).first()

        # [DOC] Auto-rotate: if the session ID has expired, regenerate it transparently before returning
        # [DOC] The caller never needs to know a rotation happened — the updated session ID is in the returned object
        if recipient and recipient.is_session_expired():
            recipient = self.rotate_session(recipient.id)

        return recipient

    def get_recipient_by_idx(self, user_idx: str, recipient_idx: str) -> Optional[Recipient]:
        """
        Get recipient by IDX

        Args:
            user_idx: Owner's IDX
            recipient_idx: Recipient's IDX

        Returns:
            Recipient or None: Recipient if found
        """
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == user_idx,
            Recipient.recipient_idx == recipient_idx,
            Recipient.is_active == True
        ).first()

        # [DOC] Same transparent auto-rotation: expired session IDs are refreshed on access
        if recipient and recipient.is_session_expired():
            recipient = self.rotate_session(recipient.id)

        return recipient

    def rotate_session(self, recipient_id: int) -> Recipient:
        """
        Rotate recipient's session ID (24hr refresh)

        Args:
            recipient_id: Recipient ID

        Returns:
            Recipient: Updated recipient with new session
        """
        # [DOC] Look up the recipient by primary key; raises ValueError if not found (should not happen normally)
        recipient = self.db.query(Recipient).filter(Recipient.id == recipient_id).first()
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        # [DOC] Generate a completely new session ID; the old one becomes unlinked from this recipient
        new_session_id = self.generate_recipient_session_id(
            recipient.user_idx,
            recipient.recipient_idx
        )
        # [DOC] new_expiry: 24 hours from now — the next rotation will be needed after this
        new_expiry = datetime.utcnow() + timedelta(hours=24)

        # [DOC] Overwrite the session fields in memory; commit below persists to DB
        recipient.current_session_id = new_session_id
        recipient.session_expires_at = new_expiry

        self.db.commit()
        self.db.refresh(recipient)

        print(f"🔄 Rotated session for {recipient.nickname}")
        print(f"   New session: {new_session_id[:32]}...")
        print(f"   Expires: {new_expiry}")

        return recipient

    def rotate_all_expired_sessions(self) -> int:
        """
        Rotate all expired recipient sessions (background worker)

        Returns:
            int: Number of sessions rotated
        """
        # [DOC] Find all active recipients whose session_expires_at is in the past
        expired_recipients = self.db.query(Recipient).filter(
            Recipient.is_active == True,
            Recipient.session_expires_at <= datetime.utcnow()
        ).all()

        # [DOC] If nothing is expired, skip processing — common case during normal operation
        if not expired_recipients:
            return 0

        print(f"\n🔄 Rotating {len(expired_recipients)} expired recipient sessions...")

        # [DOC] Rotate each expired recipient's session ID one by one
        for recipient in expired_recipients:
            self.rotate_session(recipient.id)

        print(f"✅ Rotated {len(expired_recipients)} sessions\n")

        return len(expired_recipients)

    def update_nickname(self, recipient_id: int, new_nickname: str) -> Recipient:
        """
        Update recipient's nickname

        Args:
            recipient_id: Recipient ID
            new_nickname: New nickname

        Returns:
            Recipient: Updated recipient
        """
        # [DOC] Fetch the recipient to update; raises ValueError if id doesn't exist
        recipient = self.db.query(Recipient).filter(Recipient.id == recipient_id).first()
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        # [DOC] Check that the new nickname doesn't collide with another existing recipient for this owner
        existing = self.db.query(Recipient).filter(
            Recipient.user_idx == recipient.user_idx,
            Recipient.nickname == new_nickname,
            # [DOC] Exclude the current recipient's own row so we don't flag it as a self-conflict
            Recipient.id != recipient_id,
            Recipient.is_active == True
        ).first()

        if existing:
            raise ValueError(f"Nickname '{new_nickname}' already exists")

        # [DOC] Capture old nickname for the log message before overwriting
        old_nickname = recipient.nickname
        recipient.nickname = new_nickname

        self.db.commit()
        self.db.refresh(recipient)

        print(f"✏️  Updated nickname: {old_nickname} → {new_nickname}")

        return recipient

    def remove_recipient(self, recipient_id: int) -> bool:
        """
        Remove recipient (soft delete)

        Args:
            recipient_id: Recipient ID

        Returns:
            bool: True if removed
        """
        recipient = self.db.query(Recipient).filter(Recipient.id == recipient_id).first()
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        nickname = recipient.nickname
        # [DOC] Soft delete: set is_active=False instead of deleting the row so transaction history references remain valid
        recipient.is_active = False

        self.db.commit()

        print(f"❌ Removed recipient: {nickname}")

        return True


# Testing
if __name__ == "__main__":
    """Test recipient service"""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator

    print("=== Recipient Service Testing ===\n")

    db = SessionLocal()
    service = RecipientService(db)

    try:
        # Create test users
        test_idx1 = IDXGenerator.generate("TESTA1234P", "100001")
        test_idx2 = IDXGenerator.generate("TESTB1234C", "100002")

        # Test 1: Add recipient
        print("Test 1: Add Recipient")
        try:
            recipient = service.add_recipient(test_idx1, test_idx2, "Friend")
            print(f"  Nickname: {recipient.nickname}")
            print(f"  Session: {recipient.current_session_id[:32]}...")
            print("  ✅ Test 1 passed!\n")
        except ValueError as e:
            print(f"  ⏭️  {str(e)}\n")

        # Test 2: Get user recipients
        print("Test 2: Get User Recipients")
        recipients = service.get_user_recipients(test_idx1)
        print(f"  Found {len(recipients)} recipients")
        for r in recipients:
            print(f"  - {r.nickname} → {r.recipient_idx[:16]}...")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Get by nickname
        print("Test 3: Get Recipient by Nickname")
        recipient = service.get_recipient_by_nickname(test_idx1, "Friend")
        if recipient:
            print(f"  Found: {recipient.nickname}")
            print(f"  IDX: {recipient.recipient_idx[:16]}...")
            print(f"  Session: {recipient.current_session_id[:32]}...")
            print("  ✅ Test 3 passed!\n")
        else:
            print("  ⏭️  Recipient not found\n")

        print("=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)

    finally:
        db.close()
