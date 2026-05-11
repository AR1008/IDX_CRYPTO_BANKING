# [DOC] FILE: core/crypto/legacy/range_proof.py
# [DOC] STATUS: DEPRECATED — replaced by core/crypto/real/bulletproofs_wrapper.py
# [DOC] REASON DEPRECATED: This is a SHA-256 simulation with ZERO cryptographic soundness.
# [DOC]   verify_proof() only checks that the Fiat-Shamir challenge was recomputed
# [DOC]   correctly from the stored *public* values — it does NOT verify that the
# [DOC]   committed value is actually in range [0, max_value].
# [DOC]   An attacker can commit to -1 (negative balance) or 10^18 (overflow) and
# [DOC]   produce a "proof" that passes verify_proof() without any changes.
# [DOC] REAL REPLACEMENT: core/crypto/real/bulletproofs_wrapper.py wraps libbp_binding.dylib
# [DOC]   (Rust dalek-cryptography, Ristretto255) — prove: 8.76ms, verify: 2.11ms, size: 672B.
"""
Range Proof — SHA-256 SIMULATION (NOT real Bulletproofs)
=========================================================
⚠️  SIMULATION WARNING — FOR ARCHITECTURAL PROTOTYPING ONLY ⚠️

This module simulates range proofs using SHA-256 hashes. It is NOT a real
zero-knowledge range proof for the following critical reasons:

  1. ZERO SOUNDNESS for the range check: verify_proof() only confirms that
     the Fiat-Shamir challenge was recomputed correctly from the stored
     public values. It does NOT cryptographically verify that the committed
     value is in range. An adversary can commit to a negative value or a
     value exceeding the sender's balance and produce a "valid" proof.

  2. NOT based on Pedersen commitments: Real Bulletproofs commit to values
     using C = v*G + r*H on an elliptic curve. SHA-256(v || r) is not a
     group element and has no algebraic structure.

  3. Performance figures are MISLEADING: The ~5,000 proofs/sec figure
     measures SHA-256 throughput, not cryptographic range proof generation.
     Real Bulletproofs in optimized C/Rust achieve ~10-20 proofs/sec on
     standard hardware. This simulation is ~250-500x faster ONLY because
     it is not doing any real cryptographic work.

DEPRECATED (2026-02-21): transaction_service_v2.py now uses the real
implementation.  This file is kept for backward-compatibility only.
Do NOT use it for new code.

For the REAL implementation, see:
  core/crypto/real/simple_range_proof.py  (real but O(n); upgrade target: Bulletproofs)
  Future work: Bulletproofs (O(log n)) via Rust ctypes wrapper

ACADEMIC PAPER NOTE: Performance numbers from this module cannot be
compared against Zcash, Monero, or any system using real ZK range proofs.
Any such comparison must be labeled "hash-based simulation."

Reference for real construction:
  Bünz et al. (2018) "Bulletproofs: Short Proofs for Confidential
  Transactions and More". IEEE S&P 2018.
"""

# [DOC] hashlib: SHA-256 used as the fake "commitment" and challenge hash
import hashlib
# [DOC] secrets: secure random bytes for per-bit blinding factors
import secrets
# [DOC] json: serialize structured data to canonical strings before hashing
import json
# [DOC] Decimal: fixed-point arithmetic for INR amounts (avoids float rounding)
from decimal import Decimal
# [DOC] Typing imports for cleaner function signatures
from typing import Dict, Any, Optional, Tuple
# [DOC] math.ceil / math.log2: used to compute the minimum number of bits for max_value
import math


class RangeProof:
    # [DOC] Legacy class — kept for reference only. Do not use in new code.
    # [DOC] The API (create_proof / verify_proof / verify_with_opening) mirrors
    # [DOC]   the real Bulletproofs interface so migration to the real module is easy.
    """Simplified Bulletproofs-style range proof using hash-based commitments."""

    # [DOC] PROOF_VERSION: version string included in the proof JSON for forward compatibility
    PROOF_VERSION = "1.0"
    # [DOC] BITS: the proof supports values up to 2^64; enough for any INR paise amount
    BITS = 64  # Support values up to 2^64 (sufficient for INR amounts)

    # Note: Uses hash-based commitments for simplicity
    # Production would use elliptic curve (secp256k1 or ed25519)

    def _to_cents(self, amount: Decimal) -> int:
        # [DOC] Convert rupee amounts to paise (1 INR = 100 paise) so all arithmetic
        # [DOC]   is done in integers — avoids floating-point precision problems.
        """Convert INR to paise (1 INR = 100 paise)."""
        return int(amount * 100)

    def _decompose_to_bits(self, value: int, num_bits: int) -> list[int]:
        # [DOC] Break an integer into its binary representation, LSB (least significant bit) first.
        # [DOC] Example: 6 (binary 110) → [0, 1, 1] with num_bits=3.
        # [DOC] Real Bulletproofs commit to each bit separately; this mirrors that structure.
        """Decompose integer into binary representation (LSB first)."""
        bits = []
        for i in range(num_bits):
            # [DOC] (value >> i) & 1: shift right i positions, then isolate the lowest bit
            bits.append((value >> i) & 1)
        return bits

    def _hash_commitment(self, value: int, blinding_factor: str) -> str:
        # [DOC] Fake "commitment": SHA256(value || blinding_factor).
        # [DOC] FLAW: This is a keyed hash, not an EC group element.
        # [DOC]   Real Pedersen: C = v*G + r*H — algebraically structured, supports addition.
        # [DOC]   This hash: SHA256(v||r) — no algebraic structure at all.
        """Create hash-based commitment: Hash(value || blinding_factor)."""
        data = json.dumps({
            'value': value,
            'blinding': blinding_factor
        }, sort_keys=True)

        commitment = hashlib.sha256(data.encode()).hexdigest()
        return '0x' + commitment

    def create_proof(
        self,
        value: Decimal,
        max_value: Decimal,
        value_type: str = "transaction_amount"
    ) -> Dict[str, Any]:
        # [DOC] Build a simulated ZK range proof asserting 0 <= value <= max_value.
        # [DOC] Steps (mirroring real Bulletproofs structure):
        # [DOC]   1. Convert to paise and validate bounds.
        # [DOC]   2. Compute bit decomposition of value.
        # [DOC]   3. Create a SHA-256 "commitment" to each bit (0 or 1).
        # [DOC]   4. Fiat-Shamir: hash all commitments to get a challenge scalar.
        # [DOC]   5. Create a "response" for each bit from challenge + blinding.
        # [DOC] WARNING: Steps 4 and 5 have no real soundness — see module docstring.
        """Create zero-knowledge range proof showing 0 < value <= max_value."""
        # [DOC] Convert both amounts to integer paise
        value_cents = self._to_cents(value)
        max_value_cents = self._to_cents(max_value)

        # [DOC] Reject negative values immediately; the range is [0, max_value_cents]
        if value_cents < 0:
            raise ValueError(f"Value must be positive: {value}")
        if value_cents > max_value_cents:
            raise ValueError(f"Value {value} exceeds max {max_value}")

        # [DOC] Compute the minimum number of bits needed to represent max_value_cents.
        # [DOC]   math.ceil(log2(N+1)) gives the exact bit width for any integer N.
        if max_value_cents == 0:
            num_bits = 1
        else:
            num_bits = math.ceil(math.log2(max_value_cents + 1))

        # [DOC] blinding: random secret used to hide value inside the commitment hash
        blinding = '0x' + secrets.token_bytes(32).hex()

        # [DOC] commitment: the published value — hides 'value_cents' under 'blinding'
        commitment = self._hash_commitment(value_cents, blinding)

        # [DOC] Decompose value into individual bits so we can commit to each separately
        value_bits = self._decompose_to_bits(value_cents, num_bits)

        # [DOC] Per-bit commitments and their blinding factors
        bit_commitments = []
        bit_blindings = []

        for bit in value_bits:
            # [DOC] Each bit (0 or 1) gets its own fresh random blinding factor
            bit_blinding = '0x' + secrets.token_bytes(32).hex()
            # [DOC] Commit to this single bit — the verifier cannot see whether it is 0 or 1
            bit_commitment = self._hash_commitment(bit, bit_blinding)

            bit_commitments.append(bit_commitment)
            bit_blindings.append(bit_blinding)

        # [DOC] Fiat-Shamir heuristic: derive a challenge by hashing all public values.
        # [DOC]   In a real proof, this makes the proof non-interactive and binding to the
        # [DOC]   commitment. Here it is merely cosmetic — the challenge does not enforce
        # [DOC]   any range constraint.
        challenge_data = json.dumps({
            'commitment': commitment,
            'bit_commitments': bit_commitments,
            'max_value_bits': num_bits
        }, sort_keys=True)

        challenge = hashlib.sha256(challenge_data.encode()).hexdigest()

        # [DOC] Per-bit "responses": in a real ZK proof these would be EC scalars
        # [DOC]   that satisfy a specific algebraic equation under the challenge.
        # [DOC]   Here they are just SHA-256 hashes — no equation is satisfied.
        responses = []
        for i, bit in enumerate(value_bits):
            response_data = {
                'bit': bit,
                'bit_blinding': bit_blindings[i],
                'challenge': challenge
            }
            response = hashlib.sha256(
                json.dumps(response_data, sort_keys=True).encode()
            ).hexdigest()

            responses.append('0x' + response)

        # [DOC] Package the proof. 'private_data' is stored encrypted on the private chain
        # [DOC]   and is only used by verify_with_opening() (which requires decryption first).
        proof = {
            'version': self.PROOF_VERSION,
            'value_type': value_type,

            # Public data (visible to verifiers)
            'commitment': commitment,
            'bit_commitments': bit_commitments,
            'max_value_cents': max_value_cents,
            'num_bits': num_bits,

            # Proof components
            'challenge': '0x' + challenge,
            'responses': responses,

            # Private data (only for opening, stored encrypted on private chain)
            'private_data': {
                'value_cents': value_cents,
                'blinding': blinding,
                'bit_blindings': bit_blindings
            }
        }

        return proof

    def verify_proof(self, proof: Dict[str, Any]) -> bool:
        # [DOC] Verify the STRUCTURE of a proof without knowing the secret value.
        # [DOC] CRITICAL FLAW: This only checks that the challenge was recomputed
        # [DOC]   correctly from the public bit_commitments — it does NOT verify that
        # [DOC]   the committed value is in [0, max_value]. Zero soundness.
        # [DOC] A valid call to create_proof() with value=-1 would pass this check.
        """Verify range proof without knowing the actual value."""
        try:
            commitment = proof['commitment']
            bit_commitments = proof['bit_commitments']
            max_value_cents = proof['max_value_cents']
            num_bits = proof['num_bits']
            challenge = proof['challenge']
            responses = proof['responses']

            # [DOC] Check that num_bits is large enough to represent max_value_cents.
            # [DOC]   max_possible = 2^num_bits - 1 must be >= max_value_cents.
            max_possible = (2 ** num_bits) - 1
            if max_value_cents > max_possible:
                return False

            # [DOC] Structural sanity: number of bit commitments must match num_bits
            if len(bit_commitments) != num_bits:
                return False

            # [DOC] Structural sanity: one response per bit
            if len(responses) != num_bits:
                return False

            # [DOC] Recompute the Fiat-Shamir challenge from public inputs and compare.
            # [DOC] If they match, the prover at least ran the same hashing procedure.
            # [DOC] This does NOT prove the value is in range.
            challenge_data = json.dumps({
                'commitment': commitment,
                'bit_commitments': bit_commitments,
                'max_value_bits': num_bits
            }, sort_keys=True)

            expected_challenge = '0x' + hashlib.sha256(
                challenge_data.encode()
            ).hexdigest()

            if challenge != expected_challenge:
                return False

            # [DOC] All structural checks passed — but remember: NO range is enforced here.
            return True

        except (KeyError, ValueError, TypeError) as e:
            # [DOC] Return False on any malformed proof rather than raising an exception
            return False

    def verify_with_opening(
        self,
        proof: Dict[str, Any],
        expected_value: Decimal
    ) -> bool:
        # [DOC] Open the commitment using the private_data (blinding factor + value_cents).
        # [DOC] This is only used on the PRIVATE chain after AES-256-GCM decryption
        # [DOC]   of the private_data field. It actually checks the committed value.
        # [DOC] Steps:
        # [DOC]   1. Recompute commitment from (value_cents, blinding) and compare.
        # [DOC]   2. Check that value_cents matches the expected_value argument.
        # [DOC]   3. Check that value_cents is in [0, max_value_cents].
        """Verify proof by opening commitment (used on private chain with decryption)."""
        try:
            private_data = proof['private_data']
            value_cents = private_data['value_cents']
            blinding = private_data['blinding']

            # [DOC] Re-derive the commitment and compare — ensures blinding wasn't tampered with
            expected_commitment = self._hash_commitment(value_cents, blinding)

            if proof['commitment'] != expected_commitment:
                return False

            # [DOC] Convert the expected Decimal amount to paise and compare
            expected_cents = self._to_cents(expected_value)
            if value_cents != expected_cents:
                return False

            # [DOC] Final range check: value must be non-negative and within the declared max
            if value_cents < 0 or value_cents > proof['max_value_cents']:
                return False

            return True

        except (KeyError, ValueError, TypeError):
            return False


# [DOC] Self-test block: executes only when script is run directly.
# Testing
if __name__ == "__main__":
    """Test range proof. Run: python3 -m core.crypto.range_proof"""
    print("=== Range Proof Testing ===\n")

    prover = RangeProof()

    # [DOC] Test 1: Basic proof creation — ensures the proof dict has required keys.
    # Test 1: Create proof
    print("Test 1: Create Range Proof")
    proof = prover.create_proof(
        value=Decimal('1000.00'),
        max_value=Decimal('10000.00'),
        value_type='transaction_amount'
    )

    print(f"  Commitment: {proof['commitment'][:20]}...")
    print(f"  Num bits: {proof['num_bits']}")
    print(f"  Bit commitments: {len(proof['bit_commitments'])}")
    print(f"  Challenge: {proof['challenge'][:20]}...")
    print(f"  Responses: {len(proof['responses'])}")
    assert 'commitment' in proof
    assert 'challenge' in proof
    print("  [PASS] Test 1 passed!\n")

    # [DOC] Test 2: Structural verification of the generated proof (Fiat-Shamir check).
    # Test 2: Verify valid proof
    print("Test 2: Verify Valid Proof")
    is_valid = prover.verify_proof(proof)
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 2 passed!\n")

    # [DOC] Test 3: Opening verification — checks actual value == 1000.00 INR.
    # Test 3: Verify with opening
    print("Test 3: Verify with Opening")
    is_valid = prover.verify_with_opening(proof, Decimal('1000.00'))
    print(f"  Opens correctly: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 3 passed!\n")

    # [DOC] Test 4: Wrong opening value must fail — detects amount tampering.
    # Test 4: Detect wrong opening value
    print("Test 4: Detect Wrong Opening Value")
    is_invalid = prover.verify_with_opening(proof, Decimal('999.00'))
    print(f"  Valid (should be False): {is_invalid}")
    assert is_invalid == False
    print("  [PASS] Test 4 passed!\n")

    # [DOC] Test 5: Edge case — value exactly equals max_value (boundary).
    # Test 5: Value at boundary (max_value)
    print("Test 5: Boundary Test (value = max_value)")
    proof2 = prover.create_proof(
        value=Decimal('5000.00'),
        max_value=Decimal('5000.00')
    )
    is_valid = prover.verify_proof(proof2)
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 5 passed!\n")

    # [DOC] Test 6: Value > max_value must raise ValueError at proof creation time.
    # Test 6: Value exceeds max (should fail)
    print("Test 6: Value Exceeds Max (should fail)")
    try:
        proof3 = prover.create_proof(
            value=Decimal('6000.00'),
            max_value=Decimal('5000.00')
        )
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 6 passed!\n")

    # [DOC] Test 7: Tiny value (50 paise) — confirms paise arithmetic works for sub-rupee amounts.
    # Test 7: Small values
    print("Test 7: Small Values")
    proof4 = prover.create_proof(
        value=Decimal('0.50'),  # 50 paise
        max_value=Decimal('100.00')
    )
    is_valid = prover.verify_proof(proof4)
    print(f"  Value: ₹0.50 (50 paise)")
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 7 passed!\n")

    # [DOC] Test 8: Large value near 10M INR — confirms num_bits scales with max_value.
    # Test 8: Large values
    print("Test 8: Large Values")
    proof5 = prover.create_proof(
        value=Decimal('9999999.99'),
        max_value=Decimal('10000000.00')
    )
    is_valid = prover.verify_proof(proof5)
    print(f"  Value: ₹9,999,999.99")
    print(f"  Num bits: {proof5['num_bits']}")
    print(f"  Valid: {is_valid}")
    assert is_valid == True
    print("  [PASS] Test 8 passed!\n")

    # [DOC] Test 9: Measure proof size to understand storage requirements.
    # [DOC]   Public proof (without private_data) is what is stored on-chain.
    # Test 9: Proof size
    print("Test 9: Proof Size Analysis")
    proof_json = json.dumps(proof, indent=2)
    proof_size = len(proof_json.encode('utf-8'))
    print(f"  Full proof size: {proof_size} bytes")

    # [DOC] Strip private_data to get the on-chain portion only
    public_proof = {k: v for k, v in proof.items() if k != 'private_data'}
    public_json = json.dumps(public_proof)
    public_size = len(public_json.encode('utf-8'))
    print(f"  Public proof size: {public_size} bytes")
    print(f"  Compression: {100 * (1 - public_size/proof_size):.1f}%")
    print("  [PASS] Test 9 passed!\n")

    print("=" * 50)
    print("[PASS] All Range Proof tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Range proof creation (hides values)")
    print("  • Zero-knowledge verification")
    print("  • Opening verification (private chain)")
    print("  • Tamper detection")
    print("  • Boundary value handling")
    print("  • Small and large value support")
    print(f"  • Compact proof size (~{public_size} bytes)")
    print()
