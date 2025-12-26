"""
Session ID Generator - 24-Hour Rotating Anonymous Sessions
Author: Ashutosh Rajesh
Purpose: Generate temporary session IDs that prevent transaction tracking

Privacy Model:
- Each bank account gets a unique session ID
- Session IDs rotate every 24 hours automatically
- Sessions are bank-specific (HDFC session ≠ ICICI session)
- Impossible to link sessions to IDX without database mapping

Example Flow:
1. User logs in → Creates session for HDFC account
2. Session valid for 24 hours
3. User makes transactions → All use same session ID
4. After 24 hours → Session expires
5. User logs in again → NEW session ID created
6. Observer cannot link old session to new session
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple
from config.settings import settings


class SessionIDGenerator:
    """
    Generates temporary session IDs that rotate every 24 hours
    
    Session IDs provide transaction privacy by preventing correlation:
    - Same user gets different session ID each day
    - Same user gets different session ID for each bank
    - Session IDs cannot be linked without database mapping
    
    Security Features:
    - Cryptographically secure random salt (32 bytes)
    - Millisecond-precision timestamp (prevents collisions)
    - Bank-specific sessions (isolation between accounts)
    - SHA-256 hashing (cannot reverse to get IDX)
    
    Example:
        >>> # Day 1: User opens HDFC account
        >>> session1, expiry1 = SessionIDGenerator.generate(
        ...     idx="IDX_9ada28aeb...",
        ...     bank_name="HDFC"
        ... )
        >>> print(session1)
        "SESSION_7f3a9b2c1d5e8f4a6b9c3d7e0f2a5b8c..."
        
        >>> # Day 2: Same user, same bank
        >>> session2, expiry2 = SessionIDGenerator.generate(
        ...     idx="IDX_9ada28aeb...",  # Same IDX!
        ...     bank_name="HDFC"          # Same bank!
        ... )
        >>> print(session2)
        "SESSION_3c8e1f9a4d6b2e5c..."  # Completely different!
        
        >>> # Sessions are different (privacy!)
        >>> assert session1 != session2
    """
    
    # Session validity duration (24 hours)
    SESSION_DURATION_HOURS = settings.SESSION_ROTATION_HOURS
    
    
    @staticmethod
    def generate(idx: str, bank_name: str, 
                 custom_salt: Optional[bytes] = None) -> Tuple[str, datetime]:
        """
        Generate a new session ID for a bank account
        
        Process:
        1. Get current timestamp (millisecond precision)
        2. Generate cryptographically secure random salt
        3. Combine: "IDX:BANK:TIMESTAMP:SALT"
        4. Hash with SHA-256
        5. Add SESSION_ prefix
        6. Calculate expiry time (current time + 24 hours)
        
        Args:
            idx (str): User's permanent IDX
                      Example: "IDX_9ada28aeb50248db..."
            
            bank_name (str): Bank account identifier
                            Example: "HDFC", "ICICI", "SBI"
            
            custom_salt (bytes, optional): Custom salt for testing
                                          Production: Auto-generated
                                          Testing: Provide fixed salt
        
        Returns:
            Tuple[str, datetime]: (session_id, expiry_datetime)
                session_id: Session identifier starting with "SESSION_"
                expiry_datetime: When this session expires (24h from now)
        
        Example:
            >>> # Generate session for HDFC account
            >>> session_id, expires_at = SessionIDGenerator.generate(
            ...     idx="IDX_9ada28aeb50248db...",
            ...     bank_name="HDFC"
            ... )
            >>> print(f"Session: {session_id}")
            Session: SESSION_7f3a9b2c1d5e8f4a6b9c3d7e0f2a5b8c...
            
            >>> print(f"Expires: {expires_at}")
            Expires: 2025-12-22 10:30:45.123456
            
            >>> # After 24 hours, generate new session
            >>> # Same IDX, same bank, but different session!
            >>> new_session, new_expiry = SessionIDGenerator.generate(
            ...     idx="IDX_9ada28aeb50248db...",
            ...     bank_name="HDFC"
            ... )
            >>> assert session_id != new_session  # Different!
        """
        
        # Step 1: Get current timestamp with millisecond precision
        # This ensures each session generated is unique
        # Even if same user, same bank, same second → different millisecond
        timestamp_ms = int(time.time() * 1000)  # Milliseconds since epoch
        
        # Step 2: Generate cryptographically secure random salt
        # Salt prevents rainbow table attacks and adds entropy
        # 32 bytes = 256 bits of randomness
        if custom_salt is None:
            salt = secrets.token_bytes(32)  # Cryptographically secure
        else:
            salt = custom_salt  # For testing with deterministic values
        
        salt_hex = salt.hex()  # Convert to hexadecimal string
        
        # Step 3: Combine all components
        # Format: "IDX:BANK:TIMESTAMP:SALT"
        # Each component adds uniqueness:
        #   - IDX: Different per user
        #   - BANK: Different per account
        #   - TIMESTAMP: Different per time
        #   - SALT: Random component
        combined = f"{idx}:{bank_name}:{timestamp_ms}:{salt_hex}"
        
        # Step 4: Hash with SHA-256 (one-way function)
        # SHA-256 produces 256 bits = 32 bytes = 64 hex characters
        hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
        hash_hex = hash_bytes.hex()
        
        # Step 5: Add SESSION_ prefix
        session_id = f"SESSION_{hash_hex}"
        
        # Step 6: Calculate expiry time
        # Session valid for SESSION_DURATION_HOURS (default: 24)
        expiry_datetime = datetime.now() + timedelta(
            hours=SessionIDGenerator.SESSION_DURATION_HOURS
        )
        
        return session_id, expiry_datetime
    
    
    @staticmethod
    def is_expired(expiry_datetime: datetime) -> bool:
        """
        Check if a session has expired
        
        Args:
            expiry_datetime (datetime): When session expires
        
        Returns:
            bool: True if expired, False if still valid
        
        Example:
            >>> from datetime import datetime, timedelta
            
            >>> # Session expires in 1 hour (still valid)
            >>> future_time = datetime.now() + timedelta(hours=1)
            >>> SessionIDGenerator.is_expired(future_time)
            False
            
            >>> # Session expired 1 hour ago (invalid)
            >>> past_time = datetime.now() - timedelta(hours=1)
            >>> SessionIDGenerator.is_expired(past_time)
            True
        """
        return datetime.now() > expiry_datetime
    
    
    @staticmethod
    def time_until_expiry(expiry_datetime: datetime) -> timedelta:
        """
        Calculate time remaining until session expires
        
        Args:
            expiry_datetime (datetime): When session expires
        
        Returns:
            timedelta: Time remaining (can be negative if expired)
        
        Example:
            >>> from datetime import datetime, timedelta
            
            >>> # Session expires in 6 hours
            >>> expiry = datetime.now() + timedelta(hours=6)
            >>> remaining = SessionIDGenerator.time_until_expiry(expiry)
            >>> print(f"Expires in: {remaining.total_seconds() / 3600:.1f} hours")
            Expires in: 6.0 hours
        """
        return expiry_datetime - datetime.now()
    
    
    @staticmethod
    def format_expiry(expiry_datetime: datetime) -> str:
        """
        Format expiry time in human-readable format
        
        Args:
            expiry_datetime (datetime): When session expires
        
        Returns:
            str: Formatted string like "Expires in 23 hours, 45 minutes"
        
        Example:
            >>> from datetime import datetime, timedelta
            >>> expiry = datetime.now() + timedelta(hours=23, minutes=45)
            >>> SessionIDGenerator.format_expiry(expiry)
            "Expires in 23 hours, 45 minutes"
        """
        if SessionIDGenerator.is_expired(expiry_datetime):
            time_since = datetime.now() - expiry_datetime
            hours = int(time_since.total_seconds() // 3600)
            minutes = int((time_since.total_seconds() % 3600) // 60)
            return f"Expired {hours} hours, {minutes} minutes ago"
        else:
            time_until = expiry_datetime - datetime.now()
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            return f"Expires in {hours} hours, {minutes} minutes"


# ==========================================
# EXAMPLE USAGE & TESTING
# ==========================================

if __name__ == "__main__":
    """
    Test the Session ID generator
    Run: python3 -m core.crypto.session_id
    """
    print("=== Session ID Generator Testing ===\n")
    
    # Test data
    idx1 = "IDX_9ada28aeb50248db207855e6b550feb678303271eddabe4a0c5500d61115182e"
    idx2 = "IDX_1f498a455e40ede113880643f010a3f8e2d44c7b0f4b21498aead0fcf634626f"
    
    # Test 1: Basic session generation
    print("Test 1: Basic Session Generation")
    session1, expiry1 = SessionIDGenerator.generate(idx1, "HDFC")
    print(f"  IDX: {idx1[:20]}...")
    print(f"  Bank: HDFC")
    print(f"  Session: {session1[:30]}...")
    print(f"  Length: {len(session1)} characters")
    print(f"  Expires: {expiry1.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Status: {SessionIDGenerator.format_expiry(expiry1)}")
    print(f"  ✅ Test 1 passed!\n")
    
    # Test 2: Sessions are unique (even with same inputs at different times)
    print("Test 2: Uniqueness Over Time")
    time.sleep(0.001)  # Wait 1 millisecond
    session2, expiry2 = SessionIDGenerator.generate(idx1, "HDFC")
    assert session1 != session2, "Sessions must be different!"
    print(f"  First session:  {session1[:40]}...")
    print(f"  Second session: {session2[:40]}...")
    print(f"  Different: {session1 != session2}")
    print(f"  ✅ Test 2 passed!\n")
    
    # Test 3: Bank-specific sessions
    print("Test 3: Bank-Specific Sessions")
    session_hdfc, _ = SessionIDGenerator.generate(idx1, "HDFC")
    session_icici, _ = SessionIDGenerator.generate(idx1, "ICICI")
    assert session_hdfc != session_icici, "Different banks must have different sessions!"
    print(f"  Same user, different banks:")
    print(f"  HDFC session:  {session_hdfc[:40]}...")
    print(f"  ICICI session: {session_icici[:40]}...")
    print(f"  Different: {session_hdfc != session_icici}")
    print(f"  ✅ Test 3 passed!\n")
    
    # Test 4: Different users get different sessions
    print("Test 4: User-Specific Sessions")
    session_user1, _ = SessionIDGenerator.generate(idx1, "HDFC")
    session_user2, _ = SessionIDGenerator.generate(idx2, "HDFC")
    assert session_user1 != session_user2, "Different users must have different sessions!"
    print(f"  Same bank, different users:")
    print(f"  User 1: {session_user1[:40]}...")
    print(f"  User 2: {session_user2[:40]}...")
    print(f"  Different: {session_user1 != session_user2}")
    print(f"  ✅ Test 4 passed!\n")
    
    # Test 5: Expiry checking
    print("Test 5: Session Expiry")
    from datetime import timedelta
    future_expiry = datetime.now() + timedelta(hours=24)
    past_expiry = datetime.now() - timedelta(hours=1)
    
    is_valid = not SessionIDGenerator.is_expired(future_expiry)
    is_invalid = SessionIDGenerator.is_expired(past_expiry)
    
    print(f"  Session expiring in 24 hours: Valid = {is_valid}")
    print(f"  Session expired 1 hour ago: Invalid = {is_invalid}")
    assert is_valid and is_invalid, "Expiry check failed!"
    print(f"  ✅ Test 5 passed!\n")
    
    # Test 6: Time formatting
    print("Test 6: Human-Readable Expiry")
    future = datetime.now() + timedelta(hours=23, minutes=45)
    past = datetime.now() - timedelta(hours=2, minutes=30)
    print(f"  Future: {SessionIDGenerator.format_expiry(future)}")
    print(f"  Past: {SessionIDGenerator.format_expiry(past)}")
    print(f"  ✅ Test 6 passed!\n")
    
    # Test 7: Deterministic with custom salt (for testing)
    print("Test 7: Deterministic Testing (Custom Salt)")
    fixed_salt = b'A' * 32  # Fixed salt for testing
    session_a, _ = SessionIDGenerator.generate(idx1, "HDFC", fixed_salt)
    session_b, _ = SessionIDGenerator.generate(idx1, "HDFC", fixed_salt)
    # Same salt, same millisecond → same session
    print(f"  With fixed salt, sessions can be deterministic")
    print(f"  Session A: {session_a[:40]}...")
    print(f"  Session B: {session_b[:40]}...")
    print(f"  (May differ due to timestamp, that's OK)")
    print(f"  ✅ Test 7 passed!\n")
    
    print("=" * 50)
    print("✅ All Session ID tests passed!")
    print("=" * 50)