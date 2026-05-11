# [DOC] FILE: core/crypto/legacy/commitment_scheme.py
# [DOC] STATUS: DEPRECATED — replaced by core/crypto/real/pedersen.py
# [DOC] REASON DEPRECATED: SHA-256 is NOT a real commitment scheme:
# [DOC]   (1) NOT information-theoretically hiding — an attacker who guesses the amount
# [DOC]       can recompute SHA256(sender||receiver||amount||salt) and compare;
# [DOC]   (2) NOT homomorphic — SHA256(a) + SHA256(b) != SHA256(a+b), so range
# [DOC]       proofs cannot be built on top;
# [DOC]   (3) Binding only from SHA-256 collision resistance, not from DDH hardness.
# [DOC] REAL REPLACEMENT: core/crypto/real/pedersen.py uses C = v*G + r*H on secp256k1
# [DOC]   where G and H are EC generators with unknown discrete-log relationship,
# [DOC]   giving PERFECT hiding and COMPUTATIONAL binding under DDH assumption.
"""
Commitment Scheme - SHA-256 SIMULATION (NOT real Pedersen commitments)
=======================================================================
⚠️  SIMULATION WARNING — FOR ARCHITECTURAL PROTOTYPING ONLY ⚠️

This module uses SHA-256(JSON(sender, receiver, amount, salt)) as a
"commitment." It is NOT a real cryptographic commitment scheme because:

  1. NOT homomorphic: SHA-256(a) + SHA-256(b) ≠ SHA-256(a+b)
     Real Pedersen commitments satisfy C(v1)+C(v2) = C(v1+v2).
     This property is required for range proofs to work.

  2. NOT binding under DDH: Binding holds only computationally from
     SHA-256 collision resistance, not from discrete-log hardness.
     A real Pedersen commitment is PERFECTLY binding (unconditional).

  3. NOT compatible with ZK range proofs: Real Bulletproofs require
     Pedersen commitments over an elliptic curve group.

DEPRECATED (2026-02-21): transaction_service_v2.py now uses the real
implementation.  This file is kept for backward-compatibility of any
code paths that import CommitmentScheme directly.  Do NOT use it for
new code.

For the REAL implementation using secp256k1 elliptic curve arithmetic, see:
  core/crypto/real/pedersen.py   (real Pedersen commitments)
  core/crypto/real/schnorr.py    (real ZK proofs of opening)

ACADEMIC PAPER NOTE: Do NOT claim this provides "Zerocash-style" hiding
or binding in a paper without the disclaimer that it is a hash-based
simulation. Use core/crypto/real/pedersen.py for publishable claims.

Reference for the real construction:
  Pedersen (1991) "Non-Interactive and Information-Theoretic Secure
  Verifiable Secret Sharing". CRYPTO 1991.
"""

# [DOC] hashlib: provides SHA-256 used here as the (fake) commitment hash function
import hashlib
# [DOC] secrets: cryptographically secure random bytes for the salt (this part is fine)
import secrets
# [DOC] Decimal: fixed-precision arithmetic so 1000.00 and 1000.000 hash identically
from decimal import Decimal
# [DOC] Standard typing helpers for annotating return types
from typing import Dict, Any, Optional
# [DOC] json: serialize the commitment data dict to a canonical string before hashing
import json


class CommitmentScheme:
    # [DOC] Legacy class kept for import backward-compatibility only.
    # [DOC] Do NOT instantiate this in new code — use core/crypto/real/pedersen.py instead.
    """Zerocash-style commitment scheme for transaction privacy."""

    # [DOC] SALT_LENGTH: 32 bytes = 256 bits of randomness, making brute-force
    # [DOC]   of the salt computationally infeasible (2^256 guesses needed).
    # Configuration
    SALT_LENGTH = 32  # 32 bytes = 256 bits

    def generate_salt(self) -> str:
        # [DOC] Generate a fresh random 256-bit salt for each new commitment.
        # [DOC] Salt prevents two identical transactions producing identical commitments
        # [DOC] (otherwise an observer could detect repeated transfers between the same parties).
        """Generate random 32-byte salt for commitment."""
        salt_bytes = secrets.token_bytes(self.SALT_LENGTH)
        # [DOC] Prepend "0x" to mark this as a hex string (cosmetic convention only)
        return '0x' + salt_bytes.hex()

    def create_commitment(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        salt: Optional[str] = None
    ) -> Dict[str, Any]:
        # [DOC] Build a SHA-256 "commitment" to the transaction fields.
        # [DOC] FLAW: This is NOT zero-knowledge — anyone who knows (sender, receiver, amount)
        # [DOC]   can verify or disprove the commitment by recomputing the hash.
        # [DOC]   Real Pedersen commitments hide the amount unconditionally.
        """Create SHA-256 commitment hiding transaction data. Returns commitment, salt, and data_hash."""
        # [DOC] Generate salt now if the caller did not supply one
        if salt is None:
            salt = self.generate_salt()

        # [DOC] Bundle all secret inputs into a dict for hashing
        commitment_data = {
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount),  # [DOC] Convert Decimal to str so json.dumps is deterministic
            'salt': salt
        }

        # [DOC] json.dumps with sort_keys=True ensures field order is always the same,
        # [DOC]   so SHA-256("amount:100, sender:X") == SHA-256("amount:100, sender:X").
        data_string = json.dumps(commitment_data, sort_keys=True)
        # [DOC] commitment_hash: the "hiding" value published on the public chain
        commitment_hash = hashlib.sha256(data_string.encode()).hexdigest()
        commitment = '0x' + commitment_hash

        # [DOC] data_hash: hash without salt, used for quick lookup/deduplication internally.
        # [DOC]   NOTE: publishing this would break hiding because it lacks the salt.
        data_only = {
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount)
        }
        data_hash = hashlib.sha256(
            json.dumps(data_only, sort_keys=True).encode()
        ).hexdigest()

        return {
            'commitment': commitment,   # [DOC] The value stored on-chain
            'salt': salt,               # [DOC] Secret kept by sender; needed to open the commitment
            'data_hash': '0x' + data_hash  # [DOC] Salt-free hash; internal use only
        }

    def verify_commitment(
        self,
        commitment: str,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        salt: str
    ) -> bool:
        # [DOC] Recompute the commitment from its opening (sender, receiver, amount, salt)
        # [DOC]   and compare with the stored value. Returns True only if they match.
        # [DOC] FLAW: This "verification" reveals the amount to the verifier — not ZK.
        """Verify commitment matches given transaction data."""
        recomputed = self.create_commitment(
            sender_idx=sender_idx,
            receiver_idx=receiver_idx,
            amount=amount,
            salt=salt
        )
        # [DOC] String equality check — both should be "0x<64 hex chars>"
        return recomputed['commitment'] == commitment

    def create_nullifier(
        self,
        commitment: str,
        sender_idx: str,
        secret_key: str
    ) -> str:
        # [DOC] A nullifier is a unique token derived from the commitment and a sender secret.
        # [DOC] It is revealed when the transaction is spent; the system checks that this
        # [DOC]   nullifier has not been seen before — this prevents double-spending.
        # [DOC] Formula: nullifier = SHA256(commitment || sender_idx || secret_key)
        # [DOC] The secret_key is only known to the sender, so others cannot forge nullifiers.
        """Create unique nullifier for double-spend prevention. Hash(commitment || sender || secret)."""
        nullifier_data = {
            'commitment': commitment,
            'sender_idx': sender_idx,
            'secret_key': secret_key
        }

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
        # [DOC] Re-derive the expected nullifier and compare with the provided one.
        # [DOC] Returns True only if the caller knows the matching secret_key.
        """Verify nullifier matches commitment and sender."""
        recomputed = self.create_nullifier(
            commitment=commitment,
            sender_idx=sender_idx,
            secret_key=secret_key
        )
        return recomputed == nullifier


# [DOC] Self-test block: runs only when this script is executed directly, not on import.
# Testing
if __name__ == "__main__":
    """Test commitment scheme. Run: python3 -m core.crypto.commitment_scheme"""
    print("=== Commitment Scheme Testing ===\n")

    scheme = CommitmentScheme()

    # [DOC] Test 1: Basic creation — check that the returned dict has the expected keys and lengths.
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
    # [DOC] "0x" prefix (2 chars) + 64 hex chars from SHA-256 = 66 total
    assert len(result['commitment']) == 66  # 0x + 64 hex chars
    assert len(result['salt']) == 66
    print("  [PASS] Test 1 passed!\n")

    # [DOC] Test 2: Same inputs + same salt must produce the same commitment (determinism).
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

    # [DOC] Test 3: Changing even one field (amount 1000→999) must cause verification to fail.
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

    # [DOC] Test 4: Nullifier creation — result must be 66 chars.
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

    # [DOC] Test 5: Verify the nullifier with correct inputs.
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

    # [DOC] Test 6: Different secret_key must produce a different nullifier.
    # [DOC]   This ensures that one sender cannot reuse another sender's nullifier.
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

    # [DOC] Test 7: Same salt + same inputs must reproduce the same commitment (no randomness leaks in).
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
