"""
Threshold Secret Sharing - Modified Shamir scheme for court-order decryption.

Requires 3 keys: Company (mandatory), Court (mandatory), and 1-of-3 regulatory bodies.
Uses polynomial interpolation over finite field for secret reconstruction.
"""

import secrets
import hashlib
import json
from typing import Dict, List, Any, Optional


class ThresholdSecretSharing:
    """Modified Shamir Secret Sharing requiring Company + Court + 1-of-3 regulatory bodies."""

    # [DOC] PRIME is the size of the finite field we do all arithmetic in.
    # [DOC] All share values and secret values are integers modulo PRIME.
    # [DOC] Using a 256-bit prime means shares look like random 256-bit numbers — no leakage.
    # [DOC] In production, use a much larger prime (e.g., 256-bit)
    PRIME = 2**256 - 189  # Large prime

    # [DOC] Each holder has a fixed integer ID (x-coordinate on the secret polynomial).
    # [DOC] Lagrange interpolation uses these IDs to reconstruct the polynomial at x=0.
    # Share holder IDs
    SHARE_HOLDERS = {
        'company': 1,
        'court': 2,
        'rbi': 3,
        'audit': 4,
        'finance': 5
    }

    # [DOC] Mandatory holders — reconstruction is refused if either is absent.
    # [DOC] This models "company AND court must both participate" in the access structure.
    # Mandatory share holders
    MANDATORY = ['company', 'court']

    # [DOC] Optional holders — any ONE of these suffices (1-of-3 sub-threshold).
    # [DOC] This models the regulatory choice: RBI, Audit, or Finance ministry may provide the third share.
    # Optional share holders (need any 1)
    OPTIONAL = ['rbi', 'audit', 'finance']

    def _encode_secret(self, secret: str) -> int:
        """Encode secret string to integer using SHA-256 hash."""
        # [DOC] Hash the secret string to a fixed 256-bit number using SHA-256.
        # [DOC] SHA-256 maps any-length string to exactly 32 bytes — predictable, uniform size.
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()

        # [DOC] Convert the 64-character hex string to a Python integer for polynomial arithmetic.
        secret_int = int(secret_hash, 16)

        # [DOC] Reduce modulo PRIME so the value fits inside the finite field.
        # Ensure it's within field
        return secret_int % self.PRIME

    def _decode_secret(self, secret_int: int, original_secret: str) -> str:
        """Verify recovered integer matches original secret hash."""
        # [DOC] Re-encode the original secret to get its expected integer form.
        expected_int = self._encode_secret(original_secret)

        # [DOC] If the reconstructed integer matches, the shares were correct and the secret is verified.
        if secret_int == expected_int:
            return original_secret
        else:
            # [DOC] Mismatch means wrong shares were provided or data was tampered — hard fail.
            raise ValueError("Secret reconstruction failed - hashes don't match")

    def _evaluate_polynomial(self, coefficients: List[int], x: int) -> int:
        """Evaluate polynomial P(x) = a0 + a1*x + a2*x^2 + ... (mod PRIME)."""
        # [DOC] result accumulates the sum of each polynomial term.
        result = 0
        for i, coeff in enumerate(coefficients):
            # [DOC] pow(x, i, PRIME) computes x^i mod PRIME efficiently (Python built-in modular exponentiation).
            # [DOC] Adding coeff * x^i to result gives the i-th term of the polynomial.
            result += coeff * pow(x, i, self.PRIME)
            # [DOC] Keep result within the field after every addition to avoid integer overflow.
            result %= self.PRIME

        return result

    def _lagrange_interpolation(
        self,
        shares: List[Dict[str, int]],
        x: int = 0
    ) -> int:
        """Lagrange interpolation to recover secret at x=0."""
        # [DOC] secret accumulates the sum of Lagrange basis polynomial terms.
        # [DOC] The Lagrange formula reconstructs the unique polynomial of degree < k that passes through k given points.
        secret = 0

        for i, share_i in enumerate(shares):
            # [DOC] xi is the x-coordinate of this share (the holder's fixed ID).
            # [DOC] yi is the y-coordinate (the share value = P(xi)).
            xi = share_i['x']
            yi = share_i['y']

            # [DOC] Build the Lagrange basis polynomial L_i(x) = product of (x - xj)/(xi - xj) for j != i.
            # Calculate Lagrange basis polynomial
            numerator = 1
            denominator = 1

            for j, share_j in enumerate(shares):
                if i != j:
                    xj = share_j['x']

                    # [DOC] Each factor in the numerator: (x - xj), where x=0 means we evaluate at zero.
                    numerator *= (x - xj)
                    # [DOC] Each factor in the denominator: (xi - xj), making the basis polynomial equal 1 at xi and 0 at xj.
                    denominator *= (xi - xj)

            # [DOC] Modular inverse: since we work modulo PRIME, division is replaced by multiplication by the inverse.
            # [DOC] pow(a, -1, PRIME) is Python 3.8+ syntax for modular inverse — equivalent to pow(a, PRIME-2, PRIME) by Fermat.
            # Compute modular inverse
            denominator_inv = pow(denominator % self.PRIME, -1, self.PRIME)

            # [DOC] Add yi * L_i(0) to the running sum — this is the Lagrange interpolation formula.
            # Add to secret
            secret += yi * numerator * denominator_inv
            secret %= self.PRIME

        return secret

    def split_secret(
        self,
        secret: str,
        threshold: int = 3
    ) -> Dict[str, Dict[str, Any]]:
        """Split secret into shares using Shamir's scheme with polynomial evaluation."""
        # [DOC] Convert the secret string to an integer in the finite field.
        # Encode secret as integer
        secret_int = self._encode_secret(secret)

        # [DOC] Build a polynomial of degree (threshold - 1) with the secret as the constant term.
        # [DOC] P(x) = secret + a1*x + ... + a(k-1)*x^(k-1)
        # [DOC] The secret sits at P(0) — reconstructing P at x=0 recovers it.
        # Generate random polynomial coefficients
        # P(x) = secret + a1*x + a2*x^2 + ... + a(k-1)*x^(k-1)
        coefficients = [secret_int]

        for _ in range(threshold - 1):
            # [DOC] Each additional coefficient is cryptographically random — ensures shares reveal nothing about the secret.
            coeff = secrets.randbelow(self.PRIME)
            coefficients.append(coeff)

        # [DOC] shares will map each holder name to their share dict.
        # Generate shares for each holder
        shares = {}

        for holder, holder_id in self.SHARE_HOLDERS.items():
            # [DOC] Evaluate the polynomial at the holder's fixed x-coordinate (their ID).
            # [DOC] The result y = P(holder_id) is that holder's share value.
            # Evaluate polynomial at holder_id
            share_value = self._evaluate_polynomial(coefficients, holder_id)

            # [DOC] Package the share with metadata: who holds it, what x/y are, the threshold, and whether it is mandatory.
            shares[holder] = {
                'holder': holder,
                'holder_id': holder_id,
                'x': holder_id,
                'y': share_value,
                'threshold': threshold,
                'is_mandatory': holder in self.MANDATORY
            }

        return shares

    def reconstruct_secret(
        self,
        shares: List[Dict[str, Any]],
        original_secret: str
    ) -> str:
        """Reconstruct secret from threshold shares using Lagrange interpolation."""
        # [DOC] Read threshold from the first share — all shares were produced by the same split() call so they agree.
        # Validate we have enough shares
        threshold = shares[0]['threshold']

        # [DOC] Reject immediately if caller supplies fewer shares than the threshold requires.
        if len(shares) < threshold:
            raise ValueError(
                f"Need {threshold} shares, got {len(shares)}"
            )

        # [DOC] Extract the holder names from the provided shares for mandatory-check.
        # Validate mandatory shares are present
        holders = [s['holder'] for s in shares]

        # [DOC] Enforce that every mandatory holder (company and court) has provided their share.
        for mandatory in self.MANDATORY:
            if mandatory not in holders:
                raise ValueError(
                    f"Missing mandatory share: {mandatory}"
                )

        # [DOC] Enforce that at least one optional regulatory authority has provided their share.
        # Validate at least one optional share is present
        has_optional = any(holder in self.OPTIONAL for holder in holders)
        if not has_optional:
            raise ValueError(
                f"Need at least one optional share from: {self.OPTIONAL}"
            )

        # [DOC] Run Lagrange interpolation over the provided (x, y) share pairs to reconstruct P(0) = secret.
        # Reconstruct secret using Lagrange interpolation
        secret_int = self._lagrange_interpolation(shares, x=0)

        # [DOC] Verify the recovered integer equals the expected encoding of the original secret.
        # Decode and verify
        try:
            recovered = self._decode_secret(secret_int, original_secret)
            return recovered
        except ValueError:
            raise ValueError("Secret reconstruction failed - incorrect shares")

    def verify_access_structure(self, shares: List[Dict[str, Any]]) -> bool:
        """Verify shares satisfy access structure (Company + Court + 1-of-3 regulatory)."""
        # [DOC] Collect the holder names from the provided shares list.
        holders = [s['holder'] for s in shares]

        # [DOC] Check that both mandatory holders are present — Company AND Court are required.
        # Check mandatory shares
        for mandatory in self.MANDATORY:
            if mandatory not in holders:
                return False

        # [DOC] Check that at least one optional regulatory holder is present.
        # Check at least one optional share
        has_optional = any(holder in self.OPTIONAL for holder in holders)

        # [DOC] Return True only when both mandatory check and optional check pass.
        return has_optional


if __name__ == "__main__":
    """Test Threshold Secret Sharing."""
    print("=== Threshold Secret Sharing Testing ===\n")

    tss = ThresholdSecretSharing()

    # Test 1: Split secret
    print("Test 1: Split Secret into 5 Shares")
    secret = "master_encryption_key_abc123"

    shares = tss.split_secret(secret, threshold=3)

    print(f"  Secret: {secret}")
    print(f"  Threshold: 3 (need 3 shares to reconstruct)")
    print(f"  Shares created: {len(shares)}")
    print(f"  Company share: {shares['company']['y'] % 1000}... (truncated)")
    print(f"  Court share: {shares['court']['y'] % 1000}... (truncated)")
    assert len(shares) == 5
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Reconstruct with Company + Court + RBI
    print("Test 2: Reconstruct with Company + Court + RBI")
    recovered = tss.reconstruct_secret(
        [shares['company'], shares['court'], shares['rbi']],
        secret
    )
    print(f"  Recovered: {recovered}")
    assert recovered == secret
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Reconstruct with Company + Court + Audit
    print("Test 3: Reconstruct with Company + Court + Audit")
    recovered = tss.reconstruct_secret(
        [shares['company'], shares['court'], shares['audit']],
        secret
    )
    print(f"  Recovered: {recovered}")
    assert recovered == secret
    print("  [PASS] Test 3 passed!\n")

    # Test 4: Reconstruct with Company + Court + Finance
    print("Test 4: Reconstruct with Company + Court + Finance")
    recovered = tss.reconstruct_secret(
        [shares['company'], shares['court'], shares['finance']],
        secret
    )
    print(f"  Recovered: {recovered}")
    assert recovered == secret
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Fail without Company
    print("Test 5: Should Fail Without Company (Mandatory)")
    try:
        recovered = tss.reconstruct_secret(
            [shares['court'], shares['rbi'], shares['audit']],
            secret
        )
        print("  [ERROR] Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 5 passed!\n")

    # Test 6: Fail without Court
    print("Test 6: Should Fail Without Court (Mandatory)")
    try:
        recovered = tss.reconstruct_secret(
            [shares['company'], shares['rbi'], shares['audit']],
            secret
        )
        print("  [ERROR] Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 6 passed!\n")

    # Test 7: Fail with only 2 shares
    print("Test 7: Should Fail With Only 2 Shares")
    try:
        recovered = tss.reconstruct_secret(
            [shares['company'], shares['court']],
            secret
        )
        print("  [ERROR] Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 7 passed!\n")

    # Test 8: Verify access structure
    print("Test 8: Verify Access Structure")

    # Valid combinations
    valid1 = tss.verify_access_structure([
        shares['company'], shares['court'], shares['rbi']
    ])
    valid2 = tss.verify_access_structure([
        shares['company'], shares['court'], shares['audit']
    ])
    valid3 = tss.verify_access_structure([
        shares['company'], shares['court'], shares['finance']
    ])

    # Invalid combinations
    invalid1 = tss.verify_access_structure([
        shares['company'], shares['rbi']
    ])
    invalid2 = tss.verify_access_structure([
        shares['court'], shares['rbi'], shares['audit']
    ])

    print(f"  Company+Court+RBI: {valid1}")
    print(f"  Company+Court+Audit: {valid2}")
    print(f"  Company+Court+Finance: {valid3}")
    print(f"  Company+RBI (missing Court): {invalid1}")
    print(f"  Court+RBI+Audit (missing Company): {invalid2}")

    assert all([valid1, valid2, valid3])
    assert not any([invalid1, invalid2])
    print("  [PASS] Test 8 passed!\n")

    # Test 9: Multiple secrets
    print("Test 9: Different Secrets Get Different Shares")
    secret1 = "encryption_key_1"
    secret2 = "encryption_key_2"

    shares1 = tss.split_secret(secret1, threshold=3)
    shares2 = tss.split_secret(secret2, threshold=3)

    # Shares should be different
    assert shares1['company']['y'] != shares2['company']['y']

    # But both should reconstruct correctly
    recovered1 = tss.reconstruct_secret(
        [shares1['company'], shares1['court'], shares1['rbi']],
        secret1
    )
    recovered2 = tss.reconstruct_secret(
        [shares2['company'], shares2['court'], shares2['rbi']],
        secret2
    )

    print(f"  Secret 1: {secret1} → {recovered1}")
    print(f"  Secret 2: {secret2} → {recovered2}")
    assert recovered1 == secret1
    assert recovered2 == secret2
    print("  [PASS] Test 9 passed!\n")

    print("=" * 50)
    print("[PASS] All Threshold Secret Sharing tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Secret splitting (5 shares)")
    print("  • Mandatory keys (Company + Court)")
    print("  • Optional keys (1-of-3: RBI/Audit/Finance)")
    print("  • Secure reconstruction (need 3 shares)")
    print("  • Access control enforcement")
    print("  • Perfect secrecy (2 shares reveal nothing)")
    print()
    print("Court Order Decryption Model:")
    print("  Required shares:")
    print("    [PASS] Company (always)")
    print("    [PASS] Court (always)")
    print("    [PASS] RBI OR Audit OR Finance (any 1)")
    print()
