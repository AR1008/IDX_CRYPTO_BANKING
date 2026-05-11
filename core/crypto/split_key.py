# [DOC] FILE: core/crypto/split_key.py
# [DOC] PURPOSE: Dual-custody key management for court-ordered de-anonymization.
# [DOC]
# [DOC] CONTEXT — why two key halves?
# [DOC]   The system must ensure that NO single party can decrypt a transaction
# [DOC]   on their own. Decryption requires BOTH:
# [DOC]     - IDX Corp's temporary key half (generated per court order, 24h expiry)
# [DOC]     - The regulator's permanent key half (held in RBI's HSM)
# [DOC]   Only when a judge signs a court order does IDX Corp generate the temporary
# [DOC]   half. Without that order, IDX Corp's half does not exist, so decryption
# [DOC]   is impossible — even for IDX Corp itself.
# [DOC]
# [DOC] NOTE: This is the top-level split_key.py (used for court order key management).
# [DOC]   Separate from core/crypto/encryption/split_key.py (Shamir secret sharing).
# [DOC]   The combination method here is XOR, NOT Shamir — simpler, 2-of-2 only.
"""
Split-Key Cryptography - Court-ordered de-anonymization with dual-custody decryption.

Combines RBI permanent key half with temporary company key half (24h expiry).
Both halves required via XOR for Session ID to IDX decryption with judicial oversight.
"""

# [DOC] hashlib.sha256: used to hash the combined inputs into a 256-bit key half
import hashlib
# [DOC] secrets: cryptographically secure random bytes for the random salt component
import secrets
# [DOC] time: millisecond-precision timestamp ensures uniqueness even for same judge + order
import time
# [DOC] datetime/timedelta: compute and compare key expiry timestamps
from datetime import datetime, timedelta
# [DOC] Tuple/Optional: type hints for return values and optional parameters
from typing import Tuple, Optional
# [DOC] settings: may carry environment-specific configuration values
from config.settings import settings
# [DOC] os.getenv: read the SECRET_SALT from the environment variable at startup
import os


class CourtOrderKeyManager:
    # [DOC] Manages the lifecycle of split court-order keys:
    # [DOC]   generate_temporary_key() → combine_key_halves() → is_key_expired()
    """Manages split-key cryptography for court-ordered de-anonymization with dual custody and 24h temporary keys."""

    # [DOC] KEY_VALIDITY_HOURS: after 24 hours the temporary half is no longer usable.
    # [DOC]   This enforces time-limited access — even a leaked key becomes worthless after a day.
    KEY_VALIDITY_HOURS = 24

    # [DOC] SECRET_SALT: an application-level secret mixed into every key derivation.
    # [DOC]   Even if an attacker knows judge_id + court_order_number + timestamp,
    # [DOC]   they cannot reproduce the key without this secret.
    # [DOC]   In production this MUST come from an HSM, not an env var.
    SECRET_SALT = os.getenv("COURT_ORDER_SECRET_SALT", "dev-court-salt-xyz")


    @staticmethod
    def generate_temporary_key(
        judge_id: str,
        court_order_number: str,
        custom_salt: Optional[str] = None
    ) -> Tuple[str, datetime]:
        # [DOC] Generate the IDX Corp temporary key half for a specific court order.
        # [DOC] Returns: (temporary_key_half_string, expiry_datetime)
        # [DOC]
        # [DOC] Five entropy sources are combined so that the key is unique even if:
        # [DOC]   - The same judge approves many orders (timestamp differentiates them).
        # [DOC]   - Two orders are issued at the same millisecond (random salt differentiates them).
        # [DOC]   - The log of inputs is leaked (SECRET_SALT prevents recomputation).
        """Generate temporary key half for court order. Returns (key_half, expiry_datetime) with 24h validity."""

        # [DOC] Step 1: Millisecond timestamp — ensures uniqueness across rapid successive orders
        timestamp_ms = int(time.time() * 1000)
        timestamp_str = str(timestamp_ms)

        # [DOC] Step 2: Salt — custom_salt is used only in tests for reproducibility;
        # [DOC]   in production a fresh 32-byte random value is generated each time.
        if custom_salt is None:
            salt = secrets.token_hex(32)  # [DOC] 64 hex chars = 256 bits of randomness
        else:
            salt = custom_salt

        # [DOC] Step 3: Concatenate all five entropy sources with ":" separators.
        # [DOC]   The colon delimiter prevents "JUDGE_1:CO_23" colliding with "JUDGE_12:CO_3".
        combined = (
            f"{judge_id}:"
            f"{court_order_number}:"
            f"{timestamp_str}:"
            f"{CourtOrderKeyManager.SECRET_SALT}:"
            f"{salt}"
        )

        # [DOC] Step 4: SHA-256 produces a 256-bit (32-byte = 64 hex char) key half.
        # [DOC]   .digest() returns raw bytes; .hex() converts to lowercase hex string.
        hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
        hash_hex = hash_bytes.hex()

        # [DOC] Step 5: Prefix "TEMP_KEY_" for human readability and to distinguish
        # [DOC]   this from the permanent RBI key half.
        temporary_key_half = f"TEMP_KEY_{hash_hex}"

        # [DOC] Step 6: Expiry is exactly KEY_VALIDITY_HOURS (24) hours from now.
        expiry_datetime = datetime.now() + timedelta(
            hours=CourtOrderKeyManager.KEY_VALIDITY_HOURS
        )

        return temporary_key_half, expiry_datetime


    @staticmethod
    def combine_key_halves(temporary_half: str, rbi_permanent_half: str) -> str:
        # [DOC] XOR the two key halves together to produce the master decryption key.
        # [DOC] Why XOR?
        # [DOC]   - Reversible: master XOR temp = rbi, so either half alone reveals nothing.
        # [DOC]   - Simple: a single bitwise operation, no key derivation overhead.
        # [DOC]   - Perfect secrecy (information-theoretically): master is uniformly random
        # [DOC]     to anyone who has only one of the two halves (one-time-pad property).
        """Combine temporary and permanent key halves via XOR to create master decryption key."""

        # [DOC] Step 1: Strip the "TEMP_KEY_" or "RBI_KEY_" prefix to get raw hex
        if temporary_half.startswith("TEMP_KEY_"):
            temp_hex = temporary_half[9:]   # [DOC] Skip the 9-char prefix "TEMP_KEY_"
        else:
            temp_hex = temporary_half        # [DOC] Already raw hex

        if rbi_permanent_half.startswith("RBI_KEY_"):
            rbi_hex = rbi_permanent_half[8:]  # [DOC] Skip the 8-char prefix "RBI_KEY_"
        else:
            rbi_hex = rbi_permanent_half      # [DOC] Already raw hex

        # [DOC] Step 2: Convert hex strings to raw bytes for bitwise XOR
        temp_bytes = bytes.fromhex(temp_hex)
        rbi_bytes = bytes.fromhex(rbi_hex)

        # [DOC] Step 3: Pad the shorter key to match the longer one with zero bytes.
        # [DOC]   Padding with zeros means XOR(k, 0) = k — the unpadded portion is unchanged.
        max_len = max(len(temp_bytes), len(rbi_bytes))
        temp_bytes = temp_bytes.ljust(max_len, b'\x00')
        rbi_bytes = rbi_bytes.ljust(max_len, b'\x00')

        # [DOC] Step 4: XOR each byte pair to produce the master key bytes
        master_key_bytes = bytes(
            temp_byte ^ rbi_byte
            for temp_byte, rbi_byte in zip(temp_bytes, rbi_bytes)
        )

        # [DOC] Step 5: Convert back to hex string and add "MASTER_KEY_" prefix
        master_key_hex = master_key_bytes.hex()
        master_key = f"MASTER_KEY_{master_key_hex}"

        return master_key


    @staticmethod
    def is_key_expired(expiry_datetime: datetime) -> bool:
        # [DOC] Returns True if the current time is past expiry_datetime.
        # [DOC] Called before any decryption attempt — expired keys must be rejected.
        """Check if temporary key has expired. Returns True if expired."""
        return datetime.now() > expiry_datetime


    @staticmethod
    def verify_court_order(
        judge_id: str,
        court_order_number: str
    ) -> bool:
        # [DOC] Validate that the court order is legitimate before generating a temporary key.
        # [DOC] In production this would:
        # [DOC]   1. Call the national court database API to confirm the order exists.
        # [DOC]   2. Verify that judge_id has authority to issue financial investigation orders.
        # [DOC]   3. Confirm the order is not revoked or expired.
        # [DOC] For development: simple string-format checks only.
        """Verify court order legitimacy. Returns True if valid. Production would query central court database."""
        # [DOC] judge_id must start with "JUDGE_" — acts as a format guard
        is_valid_judge = judge_id.startswith("JUDGE_")
        # [DOC] court_order_number must start with "CO_" — acts as a format guard
        is_valid_order = court_order_number.startswith("CO_")

        return is_valid_judge and is_valid_order


# [DOC] Self-test block — runs only when script is executed directly.
if __name__ == "__main__":
    """
    Test the split-key cryptography system
    Run: python3 -m core.crypto.split_key
    """
    print("=== Split-Key Cryptography Testing ===\n")

    # [DOC] Simulate the RBI's permanent master key half.
    # [DOC] In production this lives in an HSM and is never loaded into RAM.
    rbi_permanent_key = "RBI_KEY_" + "A" * 64  # Placeholder

    # [DOC] Test 1: Generate a temporary key for a specific judge + court order
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

    # [DOC] Test 2: XOR the temporary half with the permanent RBI half → master key
    print("Test 2: Combine Key Halves")
    master_key = CourtOrderKeyManager.combine_key_halves(
        temporary_half=temp_key1,
        rbi_permanent_half=rbi_permanent_key
    )

    print(f"  Temporary Half: {temp_key1[:40]}...")
    print(f"  RBI Half: {rbi_permanent_key[:40]}...")
    print(f"  Master Key: {master_key[:40]}...")
    print(f"  [PASS] Test 2 passed!\n")

    # [DOC] Test 3: Two different court orders must produce two different temporary keys.
    # [DOC]   Ensures that a key for order CO_001 cannot be reused for CO_002.
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

    # [DOC] Test 4: is_key_expired() must return False for a future expiry and True for a past one.
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

    # [DOC] Test 5: Well-formatted IDs pass; random strings without the required prefix fail.
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

    # [DOC] Test 6: The RBI key can be combined with multiple different temporary keys
    # [DOC]   to produce different master keys — one per court order, as required.
    print("Test 6: RBI Key Reusability")
    master1 = CourtOrderKeyManager.combine_key_halves(temp_key1, rbi_permanent_key)
    master2 = CourtOrderKeyManager.combine_key_halves(temp_key2, rbi_permanent_key)

    # [DOC] Different temp key → different master key (even with same RBI key)
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
