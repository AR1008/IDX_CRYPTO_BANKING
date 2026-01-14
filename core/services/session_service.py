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

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional
import hashlib
import time

from database.models.session import Session as UserSession
from database.models.bank_account import BankAccount
from database.models.user import User


class SessionService:
    """Service for managing user sessions"""
    
    def __init__(self, db: Session):
        """
        Initialize service
        
        Args:
            db: Database session
        """
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
        timestamp = str(int(time.time() * 1000))  # millisecond precision
        salt = str(hash(timestamp))
        
        data = f"{user_idx}:{bank_code}:{account_id}:{timestamp}:{salt}"
        session_hash = hashlib.sha256(data.encode()).hexdigest()
        
        idx_part = user_idx[-8:]  # Last 8 chars of IDX
        
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
        # Get user
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")
        
        # Get bank account
        account = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code,
            BankAccount.is_active == True
        ).first()
        
        if not account:
            raise ValueError(f"No {bank_code} account found for user")
        
        # Check for existing active session
        existing = self.db.query(UserSession).filter(
            UserSession.user_idx == user_idx,
            UserSession.bank_account_id == account.id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        ).first()
        
        if existing:
            print(f"♻️  Reusing active session for {bank_code}")
            return existing
        
        # Generate session ID
        session_id = self.generate_session_id(user_idx, bank_code, account.id)
        expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        
        # Create session
        session = UserSession(
            session_id=session_id,
            user_idx=user_idx,
            bank_name=bank_code,
            bank_account_id=account.id,
            expires_at=expires_at,
            is_active=True
        )
        
        self.db.add(session)
        self.db.commit()
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
        # Get bank account
        account = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code,
            BankAccount.is_active == True
        ).first()
        
        if not account:
            return None
        
        # Get active session
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
        session = self.get_active_session(user_idx, bank_code)
        
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
        session = self.db.query(UserSession).filter(
            UserSession.session_id == session_id
        ).first()
        
        if not session:
            return False
        
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
        sessions = self.db.query(UserSession).filter(
            UserSession.user_idx == user_idx,
            UserSession.is_active == True
        ).all()
        
        for session in sessions:
            session.is_active = False
        
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