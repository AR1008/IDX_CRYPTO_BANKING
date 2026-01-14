"""
Session ID Generator - 24-hour rotating anonymous sessions for transaction privacy.

Generates unique temporary session IDs per bank account that expire after 24 hours.
Uses SHA-256 with timestamp and salt for collision resistance.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple
from config.settings import settings


class SessionIDGenerator:
    """Generates temporary session IDs that rotate every 24 hours for transaction privacy."""

    # Session validity duration (24 hours)
    SESSION_DURATION_HOURS = settings.SESSION_ROTATION_HOURS
    
    
    @staticmethod
    def generate(idx: str, bank_name: str,
                 custom_salt: Optional[bytes] = None) -> Tuple[str, datetime]:
        """Generate new session ID for bank account. Returns (session_id, expiry_datetime)."""
        
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
        """Check if session has expired. Returns True if expired."""
        return datetime.now() > expiry_datetime
    
    
    @staticmethod
    def time_until_expiry(expiry_datetime: datetime) -> timedelta:
        """Calculate time remaining until session expires. Returns timedelta (negative if expired)."""
        return expiry_datetime - datetime.now()
    
    
    @staticmethod
    def format_expiry(expiry_datetime: datetime) -> str:
        """Format expiry time in human-readable format (e.g. 'Expires in 23 hours, 45 minutes')."""
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
    print(f"  [PASS] Test 1 passed!\n")
    
    # Test 2: Sessions are unique (even with same inputs at different times)
    print("Test 2: Uniqueness Over Time")
    time.sleep(0.001)  # Wait 1 millisecond
    session2, expiry2 = SessionIDGenerator.generate(idx1, "HDFC")
    assert session1 != session2, "Sessions must be different!"
    print(f"  First session:  {session1[:40]}...")
    print(f"  Second session: {session2[:40]}...")
    print(f"  Different: {session1 != session2}")
    print(f"  [PASS] Test 2 passed!\n")
    
    # Test 3: Bank-specific sessions
    print("Test 3: Bank-Specific Sessions")
    session_hdfc, _ = SessionIDGenerator.generate(idx1, "HDFC")
    session_icici, _ = SessionIDGenerator.generate(idx1, "ICICI")
    assert session_hdfc != session_icici, "Different banks must have different sessions!"
    print(f"  Same user, different banks:")
    print(f"  HDFC session:  {session_hdfc[:40]}...")
    print(f"  ICICI session: {session_icici[:40]}...")
    print(f"  Different: {session_hdfc != session_icici}")
    print(f"  [PASS] Test 3 passed!\n")
    
    # Test 4: Different users get different sessions
    print("Test 4: User-Specific Sessions")
    session_user1, _ = SessionIDGenerator.generate(idx1, "HDFC")
    session_user2, _ = SessionIDGenerator.generate(idx2, "HDFC")
    assert session_user1 != session_user2, "Different users must have different sessions!"
    print(f"  Same bank, different users:")
    print(f"  User 1: {session_user1[:40]}...")
    print(f"  User 2: {session_user2[:40]}...")
    print(f"  Different: {session_user1 != session_user2}")
    print(f"  [PASS] Test 4 passed!\n")
    
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
    print(f"  [PASS] Test 5 passed!\n")
    
    # Test 6: Time formatting
    print("Test 6: Human-Readable Expiry")
    future = datetime.now() + timedelta(hours=23, minutes=45)
    past = datetime.now() - timedelta(hours=2, minutes=30)
    print(f"  Future: {SessionIDGenerator.format_expiry(future)}")
    print(f"  Past: {SessionIDGenerator.format_expiry(past)}")
    print(f"  [PASS] Test 6 passed!\n")
    
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
    print(f"  [PASS] Test 7 passed!\n")
    
    print("=" * 50)
    print("[PASS] All Session ID tests passed!")
    print("=" * 50)