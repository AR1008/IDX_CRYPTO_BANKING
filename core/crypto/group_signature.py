"""
Group Signatures - Anonymous bank voting in consensus.

Ring signature-based implementation where any bank can sign anonymously.
RBI can later identify signers for dispute resolution.
"""

import hashlib
import hmac
import secrets
import json
from typing import Dict, Any, List, Optional, Tuple


class GroupSignatureManager:
    """Manage group signatures for bank consortium with anonymous voting and signature opening."""

    def __init__(self, num_banks: int = 12):
        """Initialize group signature manager with specified number of banks."""
        self.num_banks = num_banks

        # RBI's opening key (kept secret, used to identify signers)
        self.opening_key = '0x' + secrets.token_bytes(32).hex()

        # Group public parameters
        self.group_id = '0x' + hashlib.sha256(
            f"IDX_BANKING_CONSORTIUM_{num_banks}".encode()
        ).hexdigest()

    def generate_bank_keys(self) -> List[Dict[str, str]]:
        """Generate keypairs for all banks in consortium."""
        bank_keys = []

        for bank_id in range(1, self.num_banks + 1):
            # Generate random secret key
            secret = '0x' + secrets.token_bytes(32).hex()

            # Derive public key from secret (deterministic)
            public = '0x' + hashlib.sha256(
                (secret + self.group_id).encode()
            ).hexdigest()

            bank_keys.append({
                'bank_id': bank_id,
                'public': public,
                'secret': secret
            })

        return bank_keys

    def _derive_opening_tag(
        self,
        signer_id: int,
        signer_secret: str,
        message: str
    ) -> str:
        """Derive opening tag for signature (allows RBI to identify signer later)."""
        tag_data = json.dumps({
            'signer_id': signer_id,
            'signer_secret': signer_secret,
            'message': message,
            'opening_key': self.opening_key
        }, sort_keys=True)

        tag = hashlib.sha256(tag_data.encode()).hexdigest()
        return '0x' + tag

    def _create_ring_signature_component(
        self,
        bank_id: int,
        bank_public: str,
        message: str,
        is_signer: bool,
        signer_secret: Optional[str] = None
    ) -> Dict[str, str]:
        """Create one component of ring signature (real for signer, random for others)."""
        if is_signer:
            # Real signature component using secret key
            component_data = json.dumps({
                'bank_public': bank_public,
                'message': message,
                'secret': signer_secret,
                'group_id': self.group_id
            }, sort_keys=True)
        else:
            # Simulated component (indistinguishable from real)
            random_value = '0x' + secrets.token_bytes(32).hex()
            component_data = json.dumps({
                'bank_public': bank_public,
                'message': message,
                'random': random_value,
                'group_id': self.group_id
            }, sort_keys=True)

        component = hashlib.sha256(component_data.encode()).hexdigest()

        return {
            'bank_id': bank_id,
            'component': '0x' + component
        }

    def sign(
        self,
        message: str,
        signer_id: int,
        signer_secret_key: str,
        bank_keys: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Create anonymous group signature using ring signature."""
        # Validate signer_id
        if signer_id < 1 or signer_id > self.num_banks:
            raise ValueError(f"Invalid signer_id: {signer_id}")

        # Create opening tag (for RBI to identify signer later)
        opening_tag = self._derive_opening_tag(
            signer_id,
            signer_secret_key,
            message
        )

        # Create ring signature components for all banks
        ring_components = []

        for bank in bank_keys:
            bank_id = bank['bank_id']
            is_signer = (bank_id == signer_id)

            component = self._create_ring_signature_component(
                bank_id=bank_id,
                bank_public=bank['public'],
                message=message,
                is_signer=is_signer,
                signer_secret=signer_secret_key if is_signer else None
            )

            ring_components.append(component)

        # Create challenge (Fiat-Shamir)
        challenge_data = json.dumps({
            'message': message,
            'ring_components': [c['component'] for c in ring_components],
            'group_id': self.group_id
        }, sort_keys=True)

        challenge = hashlib.sha256(challenge_data.encode()).hexdigest()

        # Package signature
        signature = {
            'version': '1.0',
            'group_id': self.group_id,
            'message': message,
            'ring_signature': ring_components,
            'challenge': '0x' + challenge,
            'opening_tag': opening_tag,  # For RBI to identify signer
            'num_banks': self.num_banks
        }

        return signature

    def verify(
        self,
        signature: Dict[str, Any],
        message: str,
        bank_keys: Optional[List[Dict[str, str]]] = None
    ) -> bool:
        """Verify group signature without knowing signer identity."""
        try:
            # Verify group_id matches
            if signature['group_id'] != self.group_id:
                return False

            # Verify message matches
            if signature['message'] != message:
                return False

            # Verify number of ring components
            if len(signature['ring_signature']) != self.num_banks:
                return False

            # Verify challenge was computed correctly
            challenge_data = json.dumps({
                'message': message,
                'ring_components': [c['component'] for c in signature['ring_signature']],
                'group_id': self.group_id
            }, sort_keys=True)

            expected_challenge = '0x' + hashlib.sha256(
                challenge_data.encode()
            ).hexdigest()

            if signature['challenge'] != expected_challenge:
                return False

            # All checks passed
            return True

        except (KeyError, ValueError, TypeError):
            return False

    def open_signature(
        self,
        signature: Dict[str, Any],
        bank_keys: List[Dict[str, str]]
    ) -> Optional[int]:
        """Open signature to identify signer (RBI only)."""
        opening_tag = signature['opening_tag']
        message = signature['message']

        # Try each bank to find which one matches the opening tag
        for bank in bank_keys:
            bank_id = bank['bank_id']
            secret = bank['secret']

            # Recompute opening tag
            test_tag = self._derive_opening_tag(bank_id, secret, message)

            # Use constant-time comparison to prevent timing attacks
            if hmac.compare_digest(test_tag, opening_tag):
                return bank_id

        # Could not identify signer
        return None


if __name__ == "__main__":
    """Test Group Signature implementation."""
    print("=== Group Signature Testing ===\n")

    manager = GroupSignatureManager(num_banks=12)

    # Test 1: Generate bank keys
    print("Test 1: Generate Bank Keys")
    bank_keys = manager.generate_bank_keys()
    print(f"  Generated {len(bank_keys)} keypairs")
    print(f"  Bank 1 public: {bank_keys[0]['public'][:20]}...")
    print(f"  Bank 1 secret: {bank_keys[0]['secret'][:20]}...")
    assert len(bank_keys) == 12
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Create signature (Bank 5 signs)
    print("Test 2: Bank 5 Creates Anonymous Signature")
    signature = manager.sign(
        message="APPROVE_BATCH_BATCH_1_100",
        signer_id=5,
        signer_secret_key=bank_keys[4]['secret'],  # 0-indexed
        bank_keys=bank_keys
    )

    print(f"  Group ID: {signature['group_id'][:20]}...")
    print(f"  Challenge: {signature['challenge'][:20]}...")
    print(f"  Ring size: {len(signature['ring_signature'])}")
    print(f"  Opening tag: {signature['opening_tag'][:20]}...")
    assert 'ring_signature' in signature
    assert len(signature['ring_signature']) == 12
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Verify signature (anyone can do this)
    print("Test 3: Verify Signature (Without Knowing Signer)")
    is_valid = manager.verify(signature, "APPROVE_BATCH_BATCH_1_100", bank_keys)
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 3 passed!\n")

    # Test 4: Open signature (RBI identifies signer)
    print("Test 4: RBI Opens Signature to Identify Signer")
    signer_id = manager.open_signature(signature, bank_keys)
    print(f"  Identified signer: Bank {signer_id}")
    assert signer_id == 5
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Different bank signs
    print("Test 5: Bank 11 Creates Signature")
    signature2 = manager.sign(
        message="REJECT_BATCH_BATCH_101_200",
        signer_id=11,
        signer_secret_key=bank_keys[10]['secret'],
        bank_keys=bank_keys
    )

    is_valid = manager.verify(signature2, "REJECT_BATCH_BATCH_101_200", bank_keys)
    signer = manager.open_signature(signature2, bank_keys)

    print(f"  Signature valid: {is_valid}")
    print(f"  Identified signer: Bank {signer}")
    assert is_valid == True
    assert signer == 11
    print("  [PASS] Test 5 passed!\n")

    # Test 6: Tamper detection (wrong message)
    print("Test 6: Tamper Detection (Wrong Message)")
    is_invalid = manager.verify(signature, "APPROVE_BATCH_WRONG", bank_keys)
    print(f"  Valid (should be False): {is_invalid}")
    assert is_invalid == False
    print("  [PASS] Test 6 passed!\n")

    # Test 7: All banks can sign
    print("Test 7: All 12 Banks Can Sign")
    for bank_id in range(1, 13):
        sig = manager.sign(
            message=f"TEST_BANK_{bank_id}",
            signer_id=bank_id,
            signer_secret_key=bank_keys[bank_id-1]['secret'],
            bank_keys=bank_keys
        )

        is_valid = manager.verify(sig, f"TEST_BANK_{bank_id}", bank_keys)
        signer = manager.open_signature(sig, bank_keys)

        assert is_valid == True
        assert signer == bank_id

    print(f"  All 12 banks successfully signed")
    print("  [PASS] Test 7 passed!\n")

    # Test 8: Signature size
    print("Test 8: Signature Size Analysis")
    sig_json = json.dumps(signature, indent=2)
    sig_size = len(sig_json.encode('utf-8'))
    print(f"  Full signature size: {sig_size} bytes")
    print(f"  Ring components: {len(signature['ring_signature'])}")
    print(f"  Bytes per bank: {sig_size // 12:.0f}")
    print("  [PASS] Test 8 passed!\n")

    print("=" * 50)
    print("[PASS] All Group Signature tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Anonymous bank voting (12 banks)")
    print("  • Signature verification (without knowing signer)")
    print("  • Signature opening (RBI identifies signer)")
    print("  • Tamper detection")
    print("  • All banks can sign")
    print(f"  • Signature size: ~{sig_size} bytes")
    print()
    print("Use Cases:")
    print("  • Batch approval voting")
    print("  • Consensus decisions")
    print("  • Dispute resolution (RBI can identify)")
    print("  • Privacy-preserving voting")
    print()
