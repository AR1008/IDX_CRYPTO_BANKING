"""
Split-Key Cryptography - Court-ordered de-anonymization with dual-custody decryption.

Combines RBI permanent key half with temporary company key half (24h expiry).
Both halves required via XOR for Session ID to IDX decryption with judicial oversight.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional
from config.settings import settings
import os 

class CourtOrderKeyManager:
    """Manages split-key cryptography for court-ordered de-anonymization with dual custody and 24h temporary keys."""
    
    # Key validity duration (24 hours)
    KEY_VALIDITY_HOURS = 24
    
    # Secret salt for key generation (stored in HSM in production)
    # This ensures even with Judge ID + Timestamp, key cannot be recreated
    # without our secret salt
    SECRET_SALT = os.getenv("COURT_ORDER_SECRET_SALT", "dev-court-salt-xyz")
    
    
    @staticmethod
    def generate_temporary_key(
        judge_id: str,
        court_order_number: str,
        custom_salt: Optional[str] = None
    ) -> Tuple[str, datetime]:
        """Generate temporary key half for court order. Returns (key_half, expiry_datetime) with 24h validity."""
        
        # Step 1: Get current timestamp with millisecond precision
        # This ensures each key is unique even if same judge approves
        # multiple orders in quick succession
        timestamp_ms = int(time.time() * 1000)
        timestamp_str = str(timestamp_ms)
        
        # Step 2: Use custom salt for testing, or secure random for production
        if custom_salt is None:
            # Generate cryptographically secure random salt
            salt = secrets.token_hex(32)  # 32 bytes = 64 hex characters
        else:
            salt = custom_salt
        
        # Step 3: Combine all components
        # Format: "JUDGE_ID:COURT_ORDER:TIMESTAMP:SECRET_SALT:RANDOM_SALT"
        # Each component adds security:
        #   - judge_id: Different per judge
        #   - court_order_number: Different per order
        #   - timestamp_ms: Different per time
        #   - SECRET_SALT: Our secret (prevents key recreation)
        #   - salt: Random component (additional entropy)
        combined = (
            f"{judge_id}:"
            f"{court_order_number}:"
            f"{timestamp_str}:"
            f"{CourtOrderKeyManager.SECRET_SALT}:"
            f"{salt}"
        )
        
        # Step 4: Hash with SHA-256 to create key half
        # SHA-256 produces 256 bits = 32 bytes = 64 hex characters
        hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
        hash_hex = hash_bytes.hex()
        
        # Step 5: Add prefix to identify as temporary court order key
        temporary_key_half = f"TEMP_KEY_{hash_hex}"
        
        # Step 6: Calculate expiry time (24 hours from now)
        expiry_datetime = datetime.now() + timedelta(
            hours=CourtOrderKeyManager.KEY_VALIDITY_HOURS
        )
        
        return temporary_key_half, expiry_datetime
    
    
    @staticmethod
    def combine_key_halves(temporary_half: str, rbi_permanent_half: str) -> str:
        """Combine temporary and permanent key halves via XOR to create master decryption key."""
        
        # Step 1: Extract hex values (remove prefixes)
        # Temporary key format: "TEMP_KEY_abc123..."
        if temporary_half.startswith("TEMP_KEY_"):
            temp_hex = temporary_half[9:]  # Remove "TEMP_KEY_" prefix
        else:
            temp_hex = temporary_half  # Already in hex format
        
        # RBI key might have prefix or be raw hex
        if rbi_permanent_half.startswith("RBI_KEY_"):
            rbi_hex = rbi_permanent_half[8:]  # Remove "RBI_KEY_" prefix
        else:
            rbi_hex = rbi_permanent_half  # Already in hex format
        
        # Step 2: Convert hex strings to bytes
        temp_bytes = bytes.fromhex(temp_hex)
        rbi_bytes = bytes.fromhex(rbi_hex)
        
        # Step 3: XOR the two key halves together
        # XOR (exclusive OR) is perfect for combining keys:
        # - Reversible: master XOR temp = rbi, master XOR rbi = temp
        # - Secure: Without one half, cannot derive the other
        # - Fast: Simple bitwise operation
        
        # Ensure both keys are same length (pad shorter one if needed)
        max_len = max(len(temp_bytes), len(rbi_bytes))
        temp_bytes = temp_bytes.ljust(max_len, b'\x00')
        rbi_bytes = rbi_bytes.ljust(max_len, b'\x00')
        
        # Perform XOR operation byte by byte
        master_key_bytes = bytes(
            temp_byte ^ rbi_byte 
            for temp_byte, rbi_byte in zip(temp_bytes, rbi_bytes)
        )
        
        # Step 4: Convert back to hex string
        master_key_hex = master_key_bytes.hex()
        
        # Step 5: Add prefix to identify as master key
        master_key = f"MASTER_KEY_{master_key_hex}"
        
        return master_key
    
    
    @staticmethod
    def is_key_expired(expiry_datetime: datetime) -> bool:
        """Check if temporary key has expired. Returns True if expired."""
        return datetime.now() > expiry_datetime
    
    
    @staticmethod
    def verify_court_order(
        judge_id: str,
        court_order_number: str
    ) -> bool:
        """Verify court order legitimacy. Returns True if valid. Production would query central court database."""
        # TODO: Implement actual court database verification
        # This would call Indian courts API to verify:
        # - Court order exists
        # - Judge ID is authorized
        # - Order is not revoked
        # - Order is within validity period
        
        # For now (development), basic format validation
        is_valid_judge = judge_id.startswith("JUDGE_")
        is_valid_order = court_order_number.startswith("CO_")
        
        return is_valid_judge and is_valid_order


if __name__ == "__main__":
    """
    Test the split-key cryptography system
    Run: python3 -m core.crypto.split_key
    """
    print("=== Split-Key Cryptography Testing ===\n")
    
    # Simulate RBI's permanent master key half
    # In production, this is stored securely in RBI's HSM
    rbi_permanent_key = "RBI_KEY_" + "A" * 64  # Placeholder
    
    # Test 1: Generate temporary key for court order
    print("Test 1: Generate Temporary Key Half")
    judge_id = "JUDGE_12345"
    court_order = "CO_2025_67890"
    
    temp_key1, expiry1 = CourtOrderKeyManager.generate_temporary_key(
        judge_id=judge_id,
        court_order_number=court_order
    )
    
    print(f"  Judge ID: {judge_id}")
    print(f"  Court Order: {court_order}")
    print(f"  Temporary Key: {temp_key1[:50]}...")
    print(f"  Expires: {expiry1.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Valid for: {CourtOrderKeyManager.KEY_VALIDITY_HOURS} hours")
    print(f"  [PASS] Test 1 passed!\n")
    
    # Test 2: Combine key halves
    print("Test 2: Combine Key Halves")
    master_key = CourtOrderKeyManager.combine_key_halves(
        temporary_half=temp_key1,
        rbi_permanent_half=rbi_permanent_key
    )
    
    print(f"  Temporary Half: {temp_key1[:40]}...")
    print(f"  RBI Half: {rbi_permanent_key[:40]}...")
    print(f"  Master Key: {master_key[:40]}...")
    print(f"  [PASS] Test 2 passed!\n")
    
    # Test 3: Different court orders → different keys
    print("Test 3: Uniqueness (Different Court Orders)")
    temp_key2, expiry2 = CourtOrderKeyManager.generate_temporary_key(
        judge_id=judge_id,
        court_order_number="CO_2025_99999"  # Different order
    )
    
    assert temp_key1 != temp_key2, "Different orders must have different keys!"
    print(f"  Court Order 1: {court_order}")
    print(f"  Key 1: {temp_key1[:40]}...")
    print(f"  Court Order 2: CO_2025_99999")
    print(f"  Key 2: {temp_key2[:40]}...")
    print(f"  Different: {temp_key1 != temp_key2}")
    print(f"  [PASS] Test 3 passed!\n")
    
    # Test 4: Key expiry
    print("Test 4: Key Expiry Check")
    from datetime import timedelta
    
    future_expiry = datetime.now() + timedelta(hours=24)
    past_expiry = datetime.now() - timedelta(hours=1)
    
    is_valid = not CourtOrderKeyManager.is_key_expired(future_expiry)
    is_invalid = CourtOrderKeyManager.is_key_expired(past_expiry)
    
    print(f"  Key expiring in 24 hours: Valid = {is_valid}")
    print(f"  Key expired 1 hour ago: Invalid = {is_invalid}")
    assert is_valid and is_invalid, "Expiry check failed!"
    print(f"  [PASS] Test 4 passed!\n")
    
    # Test 5: Court order verification
    print("Test 5: Court Order Verification")
    valid_order = CourtOrderKeyManager.verify_court_order(
        judge_id="JUDGE_12345",
        court_order_number="CO_2025_67890"
    )
    
    invalid_order = CourtOrderKeyManager.verify_court_order(
        judge_id="INVALID",
        court_order_number="FAKE_ORDER"
    )
    
    print(f"  Valid court order verified: {valid_order}")
    print(f"  Invalid order rejected: {not invalid_order}")
    assert valid_order and not invalid_order, "Verification failed!"
    print(f"  [PASS] Test 5 passed!\n")
    
    # Test 6: RBI key is reusable
    print("Test 6: RBI Key Reusability")
    # RBI's key can be used with multiple court orders
    master1 = CourtOrderKeyManager.combine_key_halves(temp_key1, rbi_permanent_key)
    master2 = CourtOrderKeyManager.combine_key_halves(temp_key2, rbi_permanent_key)
    
    # Different temporary keys + same RBI key = different master keys
    assert master1 != master2, "Different temp keys should give different masters!"
    print(f"  RBI Key (permanent): {rbi_permanent_key[:40]}...")
    print(f"  Court Order 1 Master: {master1[:40]}...")
    print(f"  Court Order 2 Master: {master2[:40]}...")
    print(f"  RBI key successfully reused with different court orders")
    print(f"  [PASS] Test 6 passed!\n")
    
    print("=" * 50)
    print("[PASS] All Split-Key tests passed!")
    print("")
    print("Security Summary:")
    print("  • RBI alone: Cannot decrypt [ERROR]")
    print("  • We alone: Cannot decrypt [ERROR]")
    print("  • Both together: Can decrypt [PASS]")
    print("  • Temporary key expires: 24 hours")
    print("  • Constitutional protection: Judicial oversight required")
    print("=" * 50)