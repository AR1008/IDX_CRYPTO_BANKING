# [DOC] Session Rotation Worker — background thread that replaces expired 24-hour session IDs.
# [DOC] Session IDs are the public pseudonyms on the blockchain; rotating them every 24 hours
# [DOC] prevents observers from linking transactions across days (temporal unlinkability).
# [DOC] Users and senders never notice the rotation — the system resolves IDX → current session automatically.

"""
Session Auto-Rotation Worker
Purpose: Automatically rotate expired sessions every 24 hours

Flow:
1. Check for sessions older than 24 hours
2. Mark old session as inactive
3. Create new session for user
4. User seamlessly continues with new session
"""

import time
import threading
# [DOC] datetime and timedelta are used to compare session expiry timestamps against the current time.
from datetime import datetime, timedelta

# [DOC] SessionLocal opens a new DB connection for each rotation cycle.
from database.connection import SessionLocal
# [DOC] UserSession ORM model represents one row in the sessions table.
from database.models.session import Session as UserSession
# [DOC] SessionIDGenerator creates new SESSION_{bank}_{hash}_{date} identifiers.
from core.crypto.session_id import SessionIDGenerator


class SessionRotationWorker:
    """Background worker for session rotation"""

    def __init__(self, interval: int = 3600):
        """
        Initialize rotation worker

        Args:
            interval: Check interval in seconds (default: 1 hour)
        """
        # [DOC] How often to wake up and check for expired sessions (default: every 3600 seconds = 1 hour).
        self.interval = interval
        # [DOC] Flag that controls the while loop in _worker_loop(); set to False to stop gracefully.
        self.running = False
        # [DOC] Reference to the daemon thread so we can join() it on stop().
        self.thread = None

    def start(self):
        """Start the rotation worker"""
        if self.running:
            print("⚠️  Session rotation worker already running")
            return

        self.running = True
        # [DOC] daemon=True means Python won't wait for this thread when the main process exits.
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        print(f"✅ Session rotation worker started (checking every {self.interval}s)")

    def stop(self):
        """Stop the rotation worker"""
        # [DOC] Setting running=False causes _worker_loop to exit after the current sleep completes.
        self.running = False
        if self.thread:
            # [DOC] join() blocks until the thread finishes — ensures a clean shutdown.
            self.thread.join()
        print("⛔ Session rotation worker stopped")

    def _worker_loop(self):
        """Main worker loop"""
        print(f"🔄 Session rotation worker running...")

        while self.running:
            try:
                self._rotate_expired_sessions()
            except Exception as e:
                # [DOC] Log errors but don't crash the loop — session rotation must keep running.
                print(f"❌ Session rotation error: {str(e)}")

            # [DOC] Sleep between rotations — wakes up every `interval` seconds to check again.
            time.sleep(self.interval)

    def _rotate_expired_sessions(self):
        """Find and rotate expired sessions"""
        # [DOC] Open a fresh DB session per rotation cycle (not per request, to avoid long-lived connections).
        db = SessionLocal()

        try:
            # [DOC] "Now" in UTC — all session expiry timestamps are stored in UTC.
            now = datetime.utcnow()

            # [DOC] Find sessions that are still marked active but whose expires_at is in the past.
            expired_sessions = db.query(UserSession).filter(
                UserSession.is_active == True,
                UserSession.expires_at <= now
            ).all()

            # [DOC] No expired sessions found — nothing to do this cycle.
            if not expired_sessions:
                return

            print(f"\n🔄 Found {len(expired_sessions)} expired sessions")

            rotated_count = 0

            for old_session in expired_sessions:
                try:
                    # [DOC] Mark the old session inactive — it will no longer be resolved when someone pays this IDX.
                    old_session.is_active = False

                    # [DOC] Generate a fresh SESSION_{bank}_{hash}_{date} identifier and a new 24-hour expiry.
                    new_session_id, new_expiry = SessionIDGenerator.generate(
                        old_session.user_idx,
                        old_session.bank_name
                    )

                    # [DOC] Insert the new session row — senders will start resolving to this new ID.
                    new_session = UserSession(
                        session_id=new_session_id,
                        user_idx=old_session.user_idx,
                        bank_name=old_session.bank_name,  # [DOC] Same bank as the old session.
                        expires_at=new_expiry,
                        is_active=True
                    )

                    db.add(new_session)
                    db.commit()  # [DOC] Commit each rotation individually so one failure doesn't block the rest.

                    rotated_count += 1

                    print(f"  ✅ Rotated session for user: {old_session.user_idx[:32]}...")
                    print(f"     Old: {old_session.session_id[:32]}...")
                    print(f"     New: {new_session_id[:32]}...")

                except Exception as e:
                    print(f"  ❌ Failed to rotate session: {str(e)}")
                    # [DOC] Rollback only this session's changes; continue with the next one.
                    db.rollback()

            print(f"✅ Rotated {rotated_count}/{len(expired_sessions)} sessions\n")

        finally:
            # [DOC] Always close the DB connection when the rotation cycle finishes.
            db.close()


# [DOC] Module-level singleton — only one rotation worker should run per process.
_rotation_worker = None


def start_session_rotation(interval: int = 3600):
    """
    Start global session rotation worker

    Args:
        interval: Check interval in seconds (default: 1 hour)
    """
    global _rotation_worker

    # [DOC] Guard against starting a second worker if one is already running.
    if _rotation_worker and _rotation_worker.running:
        print("⚠️  Session rotation worker already running")
        return _rotation_worker

    _rotation_worker = SessionRotationWorker(interval)
    _rotation_worker.start()
    return _rotation_worker


def stop_session_rotation():
    """Stop global session rotation worker"""
    global _rotation_worker

    if _rotation_worker:
        _rotation_worker.stop()
        _rotation_worker = None


# Testing
if __name__ == "__main__":
    from database.models.user import User
    from decimal import Decimal
    from core.crypto.idx_generator import IDXGenerator

    print("=== Session Rotation Worker Testing ===\n")

    db = SessionLocal()

    try:
        # Create test user
        test_idx = IDXGenerator.generate("TEST1234A", "100001")
        user = db.query(User).filter(User.idx == test_idx).first()

        if not user:
            user = User(
                idx=test_idx,
                pan_card="TEST1234A",
                full_name="Test User",
                balance=Decimal('10000.00')
            )
            db.add(user)
            db.commit()

        # Create expired session (for testing)
        expired_time = datetime.utcnow() - timedelta(hours=25)

        test_session = UserSession(
            session_id="SESSION_test_expired_123",
            user_idx=user.idx,
            bank_name="HDFC",
            expires_at=expired_time,
            is_active=True
        )
        db.add(test_session)
        db.commit()

        print(f"Created expired test session for: {user.full_name}")
        print(f"Session ID: {test_session.session_id}")
        print(f"Expired at: {expired_time}\n")

        # Start worker (check every 5 seconds for testing)
        worker = start_session_rotation(interval=5)

        print("Worker running... It will rotate the expired session in 5 seconds")
        print("Press Ctrl+C to stop\n")

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping worker...")
            stop_session_rotation()

    finally:
        db.close()
