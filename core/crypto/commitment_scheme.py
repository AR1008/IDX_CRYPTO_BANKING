"""
Commitment Scheme (Zerocash-style)
Author: Ashutosh Rajesh
Purpose: Hide transaction data on public blockchain

How it works:
1. commitment = Hash(sender || receiver || amount || salt)
2. nullifier = Hash(commitment || sender || secret_key)
3. Public chain stores: commitment, nullifier (no real data visible)
4. Private chain stores: opening data (sender, receiver, amount, salt)

Security Properties:
✅ Hiding: Commitment reveals nothing about transaction data
✅ Binding: Cannot change data after commitment
✅ Double-spend prevention: Nullifier ensures uniqueness
✅ Court-order decryption: Private chain has opening data

Example:
    >>> from decimal import Decimal
    >>> scheme = CommitmentScheme()
    >>>
    >>> # Create commitment
    >>> commitment_data = scheme.create_commitment(
    ...     sender_idx="IDX_ABC123",
    ...     receiver_idx="IDX_XYZ789",
    ...     amount=Decimal('1000.00')
    ... )
    >>>
    >>> # Verify commitment
    >>> is_valid = scheme.verify_commitment(
    ...     commitment_data['commitment'],
    ...     sender_idx="IDX_ABC123",
    ...     receiver_idx="IDX_XYZ789",
    ...     amount=Decimal('1000.00'),
    ...     salt=commitment_data['salt']
    ... )
"""

import hashlib
import secrets
from decimal import Decimal
from typing import Dict, Any, Optional
import json


class CommitmentScheme:
    """
    Zerocash-style commitment scheme for transaction privacy

    Public chain sees:
    - commitment: Hash of transaction data
    - nullifier: Unique double-spend prevention

    Private chain stores:
    - Opening data (sender, receiver, amount, salt)
    - Encrypted with threshold keys
    """

    # Configuration
    SALT_LENGTH = 32  # 32 bytes = 256 bits

    def __init__(self):
        """Initialize commitment scheme"""
        pass

    def generate_salt(self) -> str:
        """
        Generate random salt for commitment

        Returns:
            str: Hex-encoded random salt (64 chars)
        """
        salt_bytes = secrets.token_bytes(self.SALT_LENGTH)
        return '0x' + salt_bytes.hex()

    def create_commitment(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        salt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create commitment for transaction

        Args:
            sender_idx: Sender's IDX
            receiver_idx: Receiver's IDX
            amount: Transaction amount
            salt: Optional salt (generates new if not provided)

        Returns:
            dict: {
                'commitment': hex string,
                'salt': hex string,
                'data_hash': hex string (for verification)
            }

        Example:
            >>> scheme = CommitmentScheme()
            >>> result = scheme.create_commitment(
            ...     sender_idx="IDX_ABC123",
            ...     receiver_idx="IDX_XYZ789",
            ...     amount=Decimal('1000.00')
            ... )
            >>> len(result['commitment'])  # 0x + 64 hex chars
            66
        """
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
        """
        Verify that commitment matches the given data

        Args:
            commitment: Commitment to verify
            sender_idx: Sender's IDX
            receiver_idx: Receiver's IDX
            amount: Transaction amount
            salt: Salt used in commitment

        Returns:
            bool: True if commitment is valid

        Example:
            >>> scheme = CommitmentScheme()
            >>> result = scheme.create_commitment(
            ...     sender_idx="IDX_ABC",
            ...     receiver_idx="IDX_XYZ",
            ...     amount=Decimal('100.00')
            ... )
            >>> scheme.verify_commitment(
            ...     result['commitment'],
            ...     "IDX_ABC",
            ...     "IDX_XYZ",
            ...     Decimal('100.00'),
            ...     result['salt']
            ... )
            True
        """
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
        """
        Create nullifier for double-spend prevention

        Nullifier = Hash(commitment || sender_idx || secret_key)

        The secret_key is typically derived from the sender's private key
        or a dedicated nullifier key. This ensures:
        1. Only sender can create valid nullifier
        2. Nullifier is unique for each transaction
        3. Banks can check nullifier without seeing transaction details

        Args:
            commitment: Transaction commitment
            sender_idx: Sender's IDX
            secret_key: Sender's secret nullifier key

        Returns:
            str: Hex-encoded nullifier (0x + 64 chars)

        Example:
            >>> scheme = CommitmentScheme()
            >>> commitment_data = scheme.create_commitment(
            ...     sender_idx="IDX_ABC",
            ...     receiver_idx="IDX_XYZ",
            ...     amount=Decimal('100.00')
            ... )
            >>> nullifier = scheme.create_nullifier(
            ...     commitment_data['commitment'],
            ...     "IDX_ABC",
            ...     "secret_key_xyz"
            ... )
            >>> len(nullifier)
            66
        """
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
        """
        Verify that nullifier matches commitment

        Args:
            nullifier: Nullifier to verify
            commitment: Transaction commitment
            sender_idx: Sender's IDX
            secret_key: Sender's secret key

        Returns:
            bool: True if nullifier is valid

        Example:
            >>> scheme = CommitmentScheme()
            >>> commitment_data = scheme.create_commitment(
            ...     sender_idx="IDX_ABC",
            ...     receiver_idx="IDX_XYZ",
            ...     amount=Decimal('100.00')
            ... )
            >>> nullifier = scheme.create_nullifier(
            ...     commitment_data['commitment'],
            ...     "IDX_ABC",
            ...     "secret123"
            ... )
            >>> scheme.verify_nullifier(
            ...     nullifier,
            ...     commitment_data['commitment'],
            ...     "IDX_ABC",
            ...     "secret123"
            ... )
            True
        """
        # Recreate nullifier
        recomputed = self.create_nullifier(
            commitment=commitment,
            sender_idx=sender_idx,
            secret_key=secret_key
        )

        return recomputed == nullifier


# Example usage / testing
if __name__ == "__main__":
    """
    Test the Commitment Scheme
    Run: python3 -m core.crypto.commitment_scheme
    """
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
    print("  ✅ Test 1 passed!\n")

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
    print("  ✅ Test 2 passed!\n")

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
    print("  ✅ Test 3 passed! (Tamper detected)\n")

    # Test 4: Create nullifier
    print("Test 4: Create Nullifier")
    nullifier = scheme.create_nullifier(
        commitment=result['commitment'],
        sender_idx="IDX_9ada28aeb123",
        secret_key="sender_secret_key_abc"
    )
    print(f"  Nullifier: {nullifier[:20]}...")
    assert len(nullifier) == 66
    print("  ✅ Test 4 passed!\n")

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
    print("  ✅ Test 5 passed!\n")

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
    print("  ✅ Test 6 passed! (Nullifiers are unique)\n")

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
    print("  ✅ Test 7 passed! (Deterministic)\n")

    print("=" * 50)
    print("✅ All Commitment Scheme tests passed!")
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
