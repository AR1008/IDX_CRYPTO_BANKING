# [DOC] FILE: core/crypto/legacy/group_signature.py
# [DOC] STATUS: DEPRECATED — replaced by core/crypto/real/bbs_group_signature.py
# [DOC] REASON DEPRECATED: Contains NO real cryptography.
# [DOC]   sign() returns a dict of SHA-256 hashes, not EC ring-signature components.
# [DOC]   verify() checks only that the challenge hash matches — ANY non-member can
# [DOC]   forge a "valid" signature by running the same hashing procedure.
# [DOC]   open_signature() identifies the signer by brute-forcing all 12 bank keys
# [DOC]   instead of using a cryptographic linking tag.
# [DOC] REAL REPLACEMENT: core/crypto/real/bbs_group_signature.py uses BBS04 group
# [DOC]   signatures on BN254 pairing curve (Charm-Crypto) — 92ms sign, 142ms verify,
# [DOC]   939-byte signatures, with provable anonymity and unforgeability.
"""
Group Signatures — SHA-256 SIMULATION (NOT real ring signatures)
=================================================================
⚠️  SIMULATION WARNING — FOR ARCHITECTURAL PROTOTYPING ONLY ⚠️

This module simulates ring/group signatures using SHA-256 hashes. It does
NOT provide real cryptographic anonymity or unforgeability because:

  1. NO algebraic ring structure: Real ring signatures (e.g., Monero's LSAG)
     use EC key pairs where the signer's component satisfies an algebraic
     equation that links all ring members' public keys. Here, each component
     is an independent SHA-256 hash — there is no mathematical relationship
     that binds the "ring" together.

  2. NO real anonymity: In a real ring signature, all n bank components are
     mathematically indistinguishable. Here, the real and simulated components
     are both SHA-256 outputs of different JSON objects — any verifier with
     knowledge of the inputs can distinguish them.

  3. NO real unforgeability: A real ring signature scheme (under DLOG) prevents
     non-members from forging. Here, anyone knowing the challenge construction
     can forge a "valid" signature for any bank.

  4. Opening mechanism is brute-force, not cryptographic: open_signature()
     tries all 12 bank keys. A real traceable ring signature uses a cryptographic
     linking tag derived from the signer's key and the message.

What IS correctly modeled:
  - The ARCHITECTURE of having 12 banks vote anonymously with an opening key
  - The API contract (sign / verify / open) for system design purposes

For a real implementation, use LSAG (Monero) or BBS+ group signatures.

Reference for real construction:
  Liu, Wei, Wong (2004) "Linkable Spontaneous Anonymous Group Signature
  for Ad Hoc Groups". ACISP 2004.
"""

# [DOC] hashlib: SHA-256 used throughout as the fake signing/hashing primitive
import hashlib
# [DOC] hmac.compare_digest: constant-time string comparison prevents timing-based
# [DOC]   identification of the signer during open_signature()
import hmac
# [DOC] secrets: generate cryptographically random values for "secret" keys and ring components
import secrets
# [DOC] json: serialize dicts to canonical strings before hashing
import json
# [DOC] Typing helpers for annotated signatures
from typing import Dict, Any, List, Optional, Tuple


class GroupSignatureManager:
    # [DOC] Legacy class kept for architectural reference only.
    # [DOC] The correct implementation is core/crypto/real/bbs_group_signature.py.
    """Manage group signatures for bank consortium with anonymous voting and signature opening."""

    def __init__(self, num_banks: int = 12):
        # [DOC] num_banks: size of the consortium ring (default 12 for the Indian consortium)
        """Initialize group signature manager with specified number of banks."""
        self.num_banks = num_banks

        # [DOC] opening_key: secret held by the regulator (RBI) — allows them to open (de-anonymize)
        # [DOC]   a signature and identify which bank signed. Random per process startup.
        self.opening_key = '0x' + secrets.token_bytes(32).hex()

        # [DOC] group_id: a deterministic identifier for this consortium configuration.
        # [DOC]   Included in every signature so cross-group replay is rejected by verify().
        self.group_id = '0x' + hashlib.sha256(
            f"IDX_BANKING_CONSORTIUM_{num_banks}".encode()
        ).hexdigest()

    def generate_bank_keys(self) -> List[Dict[str, str]]:
        # [DOC] Generate one (secret, public) keypair for each of the num_banks banks.
        # [DOC] FLAW: "public" is just SHA256(secret || group_id) — this is a keyed hash,
        # [DOC]   NOT a real EC public key. Real BBS04 uses G1 group elements on BN254.
        """Generate keypairs for all banks in consortium."""
        bank_keys = []

        for bank_id in range(1, self.num_banks + 1):
            # [DOC] secret: 256-bit random value — this would be an EC scalar in a real scheme
            secret = '0x' + secrets.token_bytes(32).hex()

            # [DOC] public: SHA256(secret || group_id) — deterministic but NOT a group element
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
        # [DOC] Compute an opening tag = SHA256(signer_id || signer_secret || message || opening_key).
        # [DOC] This tag is embedded in every signature so the regulator can identify the signer.
        # [DOC] FLAW: In a real traceable group signature, the tag is a deterministic EC point
        # [DOC]   derived from the signer's key — different from brute-forcing all keys.
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
        # [DOC] Create one component of the ring for a given bank.
        # [DOC] If is_signer=True, uses the real secret_key — otherwise uses fresh random bytes.
        # [DOC] FLAW: Both paths produce a SHA-256 hash. In a real ring signature the real
        # [DOC]   component satisfies a hard algebraic equation; simulated ones are random.
        # [DOC]   Here, real and simulated components are computationally indistinguishable
        # [DOC]   ONLY because SHA-256 is a pseudorandom function — no ring equation holds.
        """Create one component of ring signature (real for signer, random for others)."""
        if is_signer:
            # [DOC] Real component: uses the signer's secret_key as the "witness"
            component_data = json.dumps({
                'bank_public': bank_public,
                'message': message,
                'secret': signer_secret,
                'group_id': self.group_id
            }, sort_keys=True)
        else:
            # [DOC] Simulated component: fresh random value instead of a secret key
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
            'component': '0x' + component  # [DOC] The per-bank ring element
        }

    def sign(
        self,
        message: str,
        signer_id: int,
        signer_secret_key: str,
        bank_keys: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        # [DOC] Create an "anonymous" group signature on `message` by bank `signer_id`.
        # [DOC] Steps:
        # [DOC]   1. Derive an opening_tag so the regulator can later identify the signer.
        # [DOC]   2. Create one ring component per bank (real for signer, random for others).
        # [DOC]   3. Compute Fiat-Shamir challenge by hashing all components together.
        # [DOC]   4. Package the signature (ring_components, challenge, opening_tag).
        """Create anonymous group signature using ring signature."""
        if signer_id < 1 or signer_id > self.num_banks:
            raise ValueError(f"Invalid signer_id: {signer_id}")

        # [DOC] Opening tag embedded in signature — only computable by the actual signer
        opening_tag = self._derive_opening_tag(
            signer_id,
            signer_secret_key,
            message
        )

        # [DOC] Build ring components for ALL banks; the real signer uses their secret
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

        # [DOC] Fiat-Shamir challenge: hash of all ring components — makes signature non-interactive
        challenge_data = json.dumps({
            'message': message,
            'ring_components': [c['component'] for c in ring_components],
            'group_id': self.group_id
        }, sort_keys=True)

        challenge = hashlib.sha256(challenge_data.encode()).hexdigest()

        signature = {
            'version': '1.0',
            'group_id': self.group_id,       # [DOC] Consortium identifier (prevents cross-group replay)
            'message': message,              # [DOC] The payload that was signed (e.g., batch hash)
            'ring_signature': ring_components,  # [DOC] One component per consortium bank
            'challenge': '0x' + challenge,   # [DOC] Fiat-Shamir challenge binding all components
            'opening_tag': opening_tag,      # [DOC] Regulator token — identifies signer when opened
            'num_banks': self.num_banks
        }

        return signature

    def verify(
        self,
        signature: Dict[str, Any],
        message: str,
        bank_keys: Optional[List[Dict[str, str]]] = None
    ) -> bool:
        # [DOC] Verify a group signature without learning which bank signed.
        # [DOC] Checks: group_id matches, message matches, ring has correct size,
        # [DOC]   and the Fiat-Shamir challenge recomputes correctly.
        # [DOC] FLAW: These checks only confirm structural consistency; they do NOT
        # [DOC]   prove the signer knew a secret — anyone can fabricate all components.
        """Verify group signature without knowing signer identity."""
        try:
            # [DOC] group_id mismatch means the signature was generated for a different consortium
            if signature['group_id'] != self.group_id:
                return False

            # [DOC] message mismatch means the signature was for a different payload
            if signature['message'] != message:
                return False

            # [DOC] Ring must have exactly num_banks components (one per consortium member)
            if len(signature['ring_signature']) != self.num_banks:
                return False

            # [DOC] Recompute the Fiat-Shamir challenge from the public ring components
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

            return True

        except (KeyError, ValueError, TypeError):
            return False

    def open_signature(
        self,
        signature: Dict[str, Any],
        bank_keys: List[Dict[str, str]]
    ) -> Optional[int]:
        # [DOC] Identify the signer by brute-force: try every bank's secret key,
        # [DOC]   recompute their opening_tag, and compare with the one in the signature.
        # [DOC] FLAW: In a real traceable group signature, the tracing key allows O(1)
        # [DOC]   identification without trying every bank.
        # [DOC] This is O(num_banks) — fine for 12 banks, not for large consortia.
        # [DOC] hmac.compare_digest: constant-time comparison to avoid timing side-channels
        # [DOC]   (prevents an attacker from using response time to identify which bank matched).
        """Open signature to identify signer (RBI only)."""
        opening_tag = signature['opening_tag']
        message = signature['message']

        for bank in bank_keys:
            bank_id = bank['bank_id']
            secret = bank['secret']

            # [DOC] Recompute this bank's opening tag — matches only for the actual signer
            test_tag = self._derive_opening_tag(bank_id, secret, message)

            # [DOC] Constant-time comparison prevents timing attacks
            if hmac.compare_digest(test_tag, opening_tag):
                return bank_id

        # [DOC] None means no bank matched — possible if keys were regenerated
        return None


# [DOC] Self-test block — runs only when script is executed directly, not on import.
if __name__ == "__main__":
    """Test Group Signature implementation."""
    print("=== Group Signature Testing ===\n")

    manager = GroupSignatureManager(num_banks=12)

    # [DOC] Test 1: Key generation — 12 banks, each with secret + public
    # Test 1: Generate bank keys
    print("Test 1: Generate Bank Keys")
    bank_keys = manager.generate_bank_keys()
    print(f"  Generated {len(bank_keys)} keypairs")
    print(f"  Bank 1 public: {bank_keys[0]['public'][:20]}...")
    print(f"  Bank 1 secret: {bank_keys[0]['secret'][:20]}...")
    assert len(bank_keys) == 12
    print("  [PASS] Test 1 passed!\n")

    # [DOC] Test 2: Bank 5 signs — signature must have 12 ring components
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

    # [DOC] Test 3: verify() returns True — structural check only (no identity revealed)
    # Test 3: Verify signature (anyone can do this)
    print("Test 3: Verify Signature (Without Knowing Signer)")
    is_valid = manager.verify(signature, "APPROVE_BATCH_BATCH_1_100", bank_keys)
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 3 passed!\n")

    # [DOC] Test 4: open_signature() must correctly identify bank 5 as the signer
    # Test 4: RBI Opens Signature to Identify Signer
    print("Test 4: RBI Opens Signature to Identify Signer")
    signer_id = manager.open_signature(signature, bank_keys)
    print(f"  Identified signer: Bank {signer_id}")
    assert signer_id == 5
    print("  [PASS] Test 4 passed!\n")

    # [DOC] Test 5: Different bank (11) signs a different message — verify + open both work
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

    # [DOC] Test 6: verify() must return False if message argument doesn't match
    # Test 6: Tamper detection (wrong message)
    print("Test 6: Tamper Detection (Wrong Message)")
    is_invalid = manager.verify(signature, "APPROVE_BATCH_WRONG", bank_keys)
    print(f"  Valid (should be False): {is_invalid}")
    assert is_invalid == False
    print("  [PASS] Test 6 passed!\n")

    # [DOC] Test 7: Every bank must be able to sign and be correctly identified
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

    # [DOC] Test 8: Measure signature size — ring grows linearly with num_banks
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
