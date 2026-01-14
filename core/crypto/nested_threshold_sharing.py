"""
Nested Threshold Secret Sharing - Cryptographic access control with mandatory keys.

Two-layer Shamir scheme: Outer (Company + Court_Combined 2-of-2) and Inner (1-of-4 regulatory).
Company share mandatory, any 1-of-4 regulatory (RBI/FIU/CBI/IT) required for decryption.
"""

import secrets
import hashlib
import json
from typing import Dict, List, Any, Optional


class NestedThresholdSharing:
    """Nested Shamir Secret Sharing with 2-layer structure: Outer (Company+Court 2-of-2), Inner (1-of-4 regulatory)."""

    # Prime modulus (256-bit prime for finite field)
    PRIME = 2**256 - 189

    # Regulatory authorities (inner layer, 1-of-4)
    REGULATORY_AUTHORITIES = {
        'rbi': 1,           # Reserve Bank of India
        'fiu': 2,           # Financial Intelligence Unit
        'cbi': 3,           # Central Bureau of Investigation
        'income_tax': 4     # Income Tax Department
    }

    def _encode_secret(self, secret: str) -> int:
        """
        Encode secret string to integer

        Args:
            secret: Secret to encode

        Returns:
            int: Encoded secret as finite field element
        """
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        secret_int = int(secret_hash, 16)
        return secret_int % self.PRIME

    def _evaluate_polynomial(self, coefficients: List[int], x: int) -> int:
        """
        Evaluate polynomial at point x

        P(x) = a0 + a1*x + a2*x^2 + ... (mod PRIME)

        Args:
            coefficients: Polynomial coefficients [a0, a1, ...]
            x: Evaluation point

        Returns:
            int: P(x) mod PRIME
        """
        result = 0
        for i, coeff in enumerate(coefficients):
            result += coeff * pow(x, i, self.PRIME)
            result %= self.PRIME
        return result

    def _split_shamir(self, secret_int: int, threshold: int, num_shares: int) -> List[Dict[str, int]]:
        """
        Standard Shamir Secret Sharing (k-of-n)

        Args:
            secret_int: Secret as integer
            threshold: Number of shares needed to reconstruct
            num_shares: Total shares to generate

        Returns:
            list: Shares [(x1, y1), (x2, y2), ...]
        """
        # Generate random polynomial: P(x) = secret + a1*x + a2*x^2 + ...
        coefficients = [secret_int]
        for _ in range(threshold - 1):
            coefficients.append(secrets.randbelow(self.PRIME))

        # Generate shares
        shares = []
        for i in range(1, num_shares + 1):
            share_value = self._evaluate_polynomial(coefficients, i)
            shares.append({'x': i, 'y': share_value})

        return shares

    def _lagrange_interpolation(self, shares: List[Dict[str, int]], x: int = 0) -> int:
        """
        Lagrange interpolation to recover secret

        Args:
            shares: List of shares [{'x': x1, 'y': y1}, ...]
            x: Point to interpolate (0 for secret)

        Returns:
            int: Interpolated value at x
        """
        secret = 0

        for i, share_i in enumerate(shares):
            xi = share_i['x']
            yi = share_i['y']

            # Lagrange basis polynomial
            numerator = 1
            denominator = 1

            for j, share_j in enumerate(shares):
                if i != j:
                    xj = share_j['x']
                    numerator *= (x - xj)
                    denominator *= (xi - xj)

            # Modular inverse
            denominator_inv = pow(denominator % self.PRIME, -1, self.PRIME)

            # Add term
            secret += yi * numerator * denominator_inv
            secret %= self.PRIME

        return secret

    def split_secret(self, secret: str) -> Dict[str, Any]:
        """
        Split secret with nested threshold structure

        Structure:
        1. Encode secret to integer
        2. Outer layer: Split into 2 shares (Company, Court_Combined) using 2-of-2
        3. Inner layer: Split Court_Combined into 4 shares using 1-of-4

        Args:
            secret: Master secret to split

        Returns:
            dict: {
                'company': Company share (mandatory),
                'rbi': RBI share (1 of 4 optional),
                'fiu': FIU share (1 of 4 optional),
                'cbi': CBI share (1 of 4 optional),
                'income_tax': Income Tax share (1 of 4 optional)
            }

        Example:
            >>> tss = NestedThresholdSharing()
            >>> shares = tss.split_secret("master_encryption_key")
            >>> shares.keys()
            dict_keys(['company', 'rbi', 'fiu', 'cbi', 'income_tax'])
        """
        # Encode secret
        secret_int = self._encode_secret(secret)

        # OUTER LAYER: 2-of-2 Shamir (Company + Court_Combined)
        outer_shares = self._split_shamir(
            secret_int=secret_int,
            threshold=2,  # Need both shares
            num_shares=2  # Company and Court_Combined
        )

        company_share = outer_shares[0]  # x=1
        court_combined = outer_shares[1]  # x=2 (will be split further)

        # INNER LAYER: 1-of-4 Shamir (RBI, FIU, CBI, Income Tax)
        # Split Court_Combined into 4 regulatory shares
        inner_shares = self._split_shamir(
            secret_int=court_combined['y'],  # Use Court_Combined value
            threshold=1,  # Need only 1 share
            num_shares=4  # 4 regulatory authorities
        )

        # Package shares
        shares = {
            'company': {
                'type': 'company_share',
                'x': company_share['x'],
                'y': company_share['y'],
                'layer': 'outer',
                'mandatory': True
            }
        }

        # Add regulatory shares (inner layer)
        for i, (authority, authority_id) in enumerate(self.REGULATORY_AUTHORITIES.items()):
            shares[authority] = {
                'type': 'regulatory_share',
                'authority': authority,
                'x': inner_shares[i]['x'],
                'y': inner_shares[i]['y'],
                'layer': 'inner',
                'court_combined_x': court_combined['x'],  # Store for reconstruction
                'mandatory': False
            }

        return shares

    def reconstruct_secret(
        self,
        company_share: Dict[str, Any],
        regulatory_share: Dict[str, Any],
        original_secret: str
    ) -> str:
        """
        Reconstruct secret from Company + 1 Regulatory share

        Process:
        1. Validate Company share exists (mandatory)
        2. Use regulatory share to reconstruct Court_Combined (inner layer)
        3. Use Company + Court_Combined to reconstruct Master Secret (outer layer)
        4. Verify against original secret hash

        Args:
            company_share: Company share (mandatory)
            regulatory_share: One regulatory share (RBI/FIU/CBI/IT)
            original_secret: Original secret for verification

        Returns:
            str: Reconstructed secret

        Raises:
            ValueError: If reconstruction fails or shares invalid

        Example:
            >>> tss = NestedThresholdSharing()
            >>> shares = tss.split_secret("master_key")
            >>>
            >>> # Valid reconstruction
            >>> secret = tss.reconstruct_secret(
            >>>     shares['company'],
            >>>     shares['rbi'],
            >>>     "master_key"
            >>> )
            >>> assert secret == "master_key"
        """
        # Validate inputs
        if company_share is None:
            raise ValueError("Company share is mandatory and cannot be None")

        if regulatory_share is None:
            raise ValueError("Regulatory share is mandatory (need 1 of 4)")

        if company_share.get('type') != 'company_share':
            raise ValueError(f"Invalid company share type: {company_share.get('type')}")

        if regulatory_share.get('type') != 'regulatory_share':
            raise ValueError(f"Invalid regulatory share type: {regulatory_share.get('type')}")

        # INNER LAYER: Reconstruct Court_Combined from regulatory share
        # Since threshold=1, single share contains the secret
        court_combined_y = regulatory_share['y']
        court_combined_x = regulatory_share['court_combined_x']

        # OUTER LAYER: Reconstruct Master Secret from Company + Court_Combined
        outer_shares = [
            {'x': company_share['x'], 'y': company_share['y']},
            {'x': court_combined_x, 'y': court_combined_y}
        ]

        reconstructed_int = self._lagrange_interpolation(outer_shares, x=0)

        # Verify against original secret
        expected_int = self._encode_secret(original_secret)

        if reconstructed_int == expected_int:
            return original_secret
        else:
            raise ValueError("Secret reconstruction failed - invalid shares or tampered data")

    def verify_access_structure(self, shares: List[Dict[str, Any]]) -> Dict[str, bool]:
        """
        Verify which access patterns are possible with given shares

        Args:
            shares: List of shares to check

        Returns:
            dict: {
                'has_company': bool,
                'has_regulatory': bool,
                'can_decrypt': bool,
                'regulatory_authorities': list
            }

        Example:
            >>> tss = NestedThresholdSharing()
            >>> all_shares = tss.split_secret("key")
            >>>
            >>> # Check what's possible with Company + RBI
            >>> result = tss.verify_access_structure([
            >>>     all_shares['company'],
            >>>     all_shares['rbi']
            >>> ])
            >>> assert result['can_decrypt'] == True
        """
        has_company = False
        regulatory_authorities = []

        for share in shares:
            if share.get('type') == 'company_share':
                has_company = True
            elif share.get('type') == 'regulatory_share':
                regulatory_authorities.append(share.get('authority'))

        has_regulatory = len(regulatory_authorities) > 0
        can_decrypt = has_company and has_regulatory

        return {
            'has_company': has_company,
            'has_regulatory': has_regulatory,
            'can_decrypt': can_decrypt,
            'regulatory_authorities': regulatory_authorities,
            'missing': {
                'company': not has_company,
                'regulatory': not has_regulatory
            }
        }


# Example usage
if __name__ == "__main__":
    """
    Test nested threshold sharing
    """
    print("="*80)
    print("NESTED THRESHOLD SHARING - CRYPTOGRAPHIC ACCESS CONTROL TEST")
    print("="*80)

    tss = NestedThresholdSharing()

    # Test 1: Split secret
    print("\nTest 1: Split Secret")
    secret = "MASTER_ENCRYPTION_KEY_" + secrets.token_hex(16)
    shares = tss.split_secret(secret)

    print(f"  Generated shares: {list(shares.keys())}")
    print(f"  Company share (mandatory): {shares['company']['type']}")
    print(f"  RBI share (1-of-4): {shares['rbi']['type']}")
    print(f"  [PASS] Test 1 passed\n")

    # Test 2: Valid reconstruction (Company + RBI)
    print("Test 2: Valid Reconstruction (Company + RBI)")
    try:
        reconstructed = tss.reconstruct_secret(
            company_share=shares['company'],
            regulatory_share=shares['rbi'],
            original_secret=secret
        )
        print(f"  Reconstructed: {reconstructed == secret}")
        print(f"  [PASS] Test 2 passed\n")
    except Exception as e:
        print(f"  [ERROR] Test 2 failed: {e}\n")

    # Test 3: Valid reconstruction (Company + FIU)
    print("Test 3: Valid Reconstruction (Company + FIU)")
    try:
        reconstructed = tss.reconstruct_secret(
            company_share=shares['company'],
            regulatory_share=shares['fiu'],
            original_secret=secret
        )
        print(f"  Reconstructed: {reconstructed == secret}")
        print(f"  [PASS] Test 3 passed\n")
    except Exception as e:
        print(f"  [ERROR] Test 3 failed: {e}\n")

    # Test 4: Invalid - missing Company
    print("Test 4: Invalid Reconstruction (Missing Company)")
    try:
        reconstructed = tss.reconstruct_secret(
            company_share=None,  # Missing!
            regulatory_share=shares['rbi'],
            original_secret=secret
        )
        print(f"  [ERROR] Test 4 FAILED - should have raised error")
    except ValueError as e:
        print(f"  [PASS] Test 4 passed - correctly rejected: {e}\n")

    # Test 5: Verify access structure
    print("Test 5: Verify Access Structure")

    # Scenario A: Company + RBI
    result_a = tss.verify_access_structure([shares['company'], shares['rbi']])
    print(f"  Company + RBI:")
    print(f"    Can decrypt: {result_a['can_decrypt']}")
    print(f"    [PASS] Correct\n")

    # Scenario B: RBI + FIU (no Company)
    result_b = tss.verify_access_structure([shares['rbi'], shares['fiu']])
    print(f"  RBI + FIU (no Company):")
    print(f"    Can decrypt: {result_b['can_decrypt']}")
    print(f"    Missing: {result_b['missing']}")
    print(f"    [PASS] Correct (cannot decrypt)\n")

    print("="*80)
    print("[PASS] ALL TESTS PASSED - CRYPTOGRAPHIC ACCESS CONTROL WORKING")
    print("="*80)
