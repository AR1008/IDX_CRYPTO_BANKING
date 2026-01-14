"""
Commitment Scheme - Zerocash-style cryptographic commitments for transaction privacy.

Provides hiding and binding properties for transaction data on public blockchain.
Uses SHA-256 hashing with random salt for commitment generation.
"""

import hashlib
import secrets
from decimal import Decimal
from typing import Dict, Any, Optional
import json


class CommitmentScheme:
    """Zerocash-style commitment scheme for transaction privacy."""

    # Configuration
    SALT_LENGTH = 32  # 32 bytes = 256 bits

    def generate_salt(self) -> str:
        """Generate random 32-byte salt for commitment."""
        salt_bytes = secrets.token_bytes(self.SALT_LENGTH)
        return '0x' + salt_bytes.hex()

    def create_commitment(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        salt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create SHA-256 commitment hiding transaction data. Returns commitment, salt, and data_hash."""
        # Generate salt if not provided
        if salt is None:
            salt = self.generate_salt()

        # Create commitment data structure
        commitment_data = {
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount),  # Convert to string for hashing
            'salt': salt
        }

        # Hash the commitment data
        # commitment = SHA256(sender || receiver || amount || salt)
        data_string = json.dumps(commitment_data, sort_keys=True)
        commitment_hash = hashlib.sha256(data_string.encode()).hexdigest()
        commitment = '0x' + commitment_hash

        # Also create a data hash (without salt) for quick validation
        data_only = {
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount)
        }
        data_hash = hashlib.sha256(
            json.dumps(data_only, sort_keys=True).encode()
        ).hexdigest()

        return {
            'commitment': commitment,
            'salt': salt,
            'data_hash': '0x' + data_hash
        }

    def verify_commitment(
        self,
        commitment: str,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        salt: str
    ) -> bool:
        """Verify commitment matches given transaction data."""
        # Recreate commitment with same data
        recomputed = self.create_commitment(
            sender_idx=sender_idx,
            receiver_idx=receiver_idx,
            amount=amount,
            salt=salt
        )

        # Compare commitments
        return recomputed['commitment'] == commitment

    def create_nullifier(
        self,
        commitment: str,
        sender_idx: str,
        secret_key: str
    ) -> str:
        """Create unique nullifier for double-spend prevention. Hash(commitment || sender || secret)."""
        # Create nullifier data
        nullifier_data = {
            'commitment': commitment,
            'sender_idx': sender_idx,
            'secret_key': secret_key
        }

        # Hash to create nullifier
        # nullifier = SHA256(commitment || sender || secret)
        data_string = json.dumps(nullifier_data, sort_keys=True)
        nullifier_hash = hashlib.sha256(data_string.encode()).hexdigest()

        return '0x' + nullifier_hash

    def verify_nullifier(
        self,
        nullifier: str,
        commitment: str,
        sender_idx: str,
        secret_key: str
    ) -> bool:
        """Verify nullifier matches commitment and sender."""
        # Recreate nullifier
        recomputed = self.create_nullifier(
            commitment=commitment,
            sender_idx=sender_idx,
            secret_key=secret_key
        )

        return recomputed == nullifier


# Testing
if __name__ == "__main__":
    """Test commitment scheme. Run: python3 -m core.crypto.commitment_scheme"""
    print("=== Commitment Scheme Testing ===\n")

    scheme = CommitmentScheme()

    # Test 1: Create commitment
    print("Test 1: Create Commitment")
    result = scheme.create_commitment(
        sender_idx="IDX_9ada28aeb123",
        receiver_idx="IDX_1f498a455xyz",
        amount=Decimal('1000.00')
    )

    print(f"  Commitment: {result['commitment'][:20]}...")
    print(f"  Salt: {result['salt'][:20]}...")
    print(f"  Data hash: {result['data_hash'][:20]}...")
    assert len(result['commitment']) == 66  # 0x + 64 hex chars
    assert len(result['salt']) == 66
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Verify commitment
    print("Test 2: Verify Commitment")
    is_valid = scheme.verify_commitment(
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        receiver_idx="IDX_1f498a455xyz",
        amount=Decimal('1000.00'),
        salt=result['salt']
    )
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Tamper detection
    print("Test 3: Tamper Detection")
    is_invalid = scheme.verify_commitment(
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        receiver_idx="IDX_1f498a455xyz",
        amount=Decimal('999.00'),  # Changed amount!
        salt=result['salt']
    )
    print(f"  Valid (should be False): {is_invalid}")
    assert is_invalid == False
    print("  [PASS] Test 3 passed! (Tamper detected)\n")

    # Test 4: Create nullifier
    print("Test 4: Create Nullifier")
    nullifier = scheme.create_nullifier(
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        secret_key="sender_secret_key_abc"
    )
    print(f"  Nullifier: {nullifier[:20]}...")
    assert len(nullifier) == 66
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Verify nullifier
    print("Test 5: Verify Nullifier")
    is_valid = scheme.verify_nullifier(
        nullifier=nullifier,
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        secret_key="sender_secret_key_abc"
    )
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 5 passed!\n")

    # Test 6: Nullifier uniqueness (different secret = different nullifier)
    print("Test 6: Nullifier Uniqueness")
    nullifier2 = scheme.create_nullifier(
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        secret_key="different_secret_key"
    )
    print(f"  Nullifier 1: {nullifier[:20]}...")
    print(f"  Nullifier 2: {nullifier2[:20]}...")
    assert nullifier != nullifier2
    print("  [PASS] Test 6 passed! (Nullifiers are unique)\n")

    # Test 7: Deterministic (same input = same output)
    print("Test 7: Deterministic Behavior")
    result2 = scheme.create_commitment(
        sender_idx="IDX_9ada28aeb123",
        receiver_idx="IDX_1f498a455xyz",
        amount=Decimal('1000.00'),
        salt=result['salt']  # Use same salt
    )
    print(f"  Commitment 1: {result['commitment'][:20]}...")
    print(f"  Commitment 2: {result2['commitment'][:20]}...")
    assert result['commitment'] == result2['commitment']
    print("  [PASS] Test 7 passed! (Deterministic)\n")

    print("=" * 50)
    print("[PASS] All Commitment Scheme tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Commitment creation (hides transaction data)")
    print("  • Commitment verification (proves correctness)")
    print("  • Tamper detection (invalid data rejected)")
    print("  • Nullifier creation (prevents double-spend)")
    print("  • Nullifier verification")
    print("  • Uniqueness (different inputs = different outputs)")
    print("  • Deterministic (same inputs = same outputs)")
    print()
