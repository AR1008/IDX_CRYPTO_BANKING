"""
Anomaly Threshold Encryption - Threshold encrypt flagged transaction details for court orders.

WARNING: Demo uses XOR (weak). Production requires AES-256-GCM.
Requires 3 parties: Company (mandatory) + Court (mandatory) + 1-of-4 regulatory (RBI/FIU/CBI/IT).
"""

import secrets
import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timezone

from core.crypto.threshold_secret_sharing import ThresholdSecretSharing


class AnomalyThresholdEncryption:
    """Threshold encryption for anomaly-flagged transactions. Requires Company + Court + 1-of-4 regulatory keys."""

    # Share holder IDs for anomaly encryption
    # Different from regular court orders to allow different key holders
    ANOMALY_SHARE_HOLDERS = {
        'company': 1,
        'supreme_court': 2,
        'rbi': 3,      # Reserve Bank of India
        'fiu': 4,      # Financial Intelligence Unit
        'cbi': 5,      # Central Bureau of Investigation
        'income_tax': 6  # Income Tax Department
    }

    # Mandatory share holders
    MANDATORY = ['company', 'supreme_court']

    # Optional share holders (need any 1)
    OPTIONAL = ['rbi', 'fiu', 'cbi', 'income_tax']

    def __init__(self):
        """Initialize anomaly threshold encryption"""
        # Use custom prime for anomaly encryption
        # Larger than regular TSS for extra security
        self.prime = 2**256 - 189

    def _generate_encryption_key(self) -> str:
        """
        Generate random encryption key for AES

        Returns:
            str: Hex-encoded 256-bit encryption key
        """
        key_bytes = secrets.token_bytes(32)  # 256 bits
        return '0x' + key_bytes.hex()

    def _xor_encrypt(self, data: str, key: str) -> str:
        """
        ⚠️  SECURITY WARNING: XOR encryption (DEVELOPMENT/TESTING ONLY)

        CRITICAL: This is CRYPTOGRAPHICALLY WEAK. Replace before production with:

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        def aes_gcm_encrypt(data: str, key: bytes) -> dict:
            aesgcm = AESGCM(key)  # key must be 256-bit
            nonce = os.urandom(12)  # 96-bit nonce
            ciphertext = aesgcm.encrypt(nonce, data.encode(), None)
            return {'ciphertext': ciphertext.hex(), 'nonce': nonce.hex()}

        Args:
            data: Data to encrypt
            key: Encryption key

        Returns:
            str: Encrypted data (hex-encoded)
        """
        # Hash key to get consistent length
        key_hash = hashlib.sha256(key.encode()).digest()

        # Convert data to bytes
        data_bytes = data.encode('utf-8')

        # XOR encryption
        encrypted_bytes = bytearray()
        for i, byte in enumerate(data_bytes):
            key_byte = key_hash[i % len(key_hash)]
            encrypted_bytes.append(byte ^ key_byte)

        return '0x' + encrypted_bytes.hex()

    def _xor_decrypt(self, encrypted: str, key: str) -> str:
        """
        Simple XOR decryption

        Args:
            encrypted: Encrypted data (hex-encoded)
            key: Encryption key

        Returns:
            str: Decrypted data
        """
        # Hash key
        key_hash = hashlib.sha256(key.encode()).digest()

        # Convert hex to bytes
        encrypted_bytes = bytes.fromhex(encrypted[2:])  # Remove '0x' prefix

        # XOR decryption
        decrypted_bytes = bytearray()
        for i, byte in enumerate(encrypted_bytes):
            key_byte = key_hash[i % len(key_hash)]
            decrypted_bytes.append(byte ^ key_byte)

        try:
            return decrypted_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            raise ValueError(f"Decryption failed: invalid key or corrupted data (Unicode error: {e})")

    def encrypt_transaction_details(
        self,
        transaction_hash: str,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal,
        anomaly_score: float,
        anomaly_flags: List[str]
    ) -> Dict[str, Any]:
        """
        Encrypt transaction details with threshold scheme

        Args:
            transaction_hash: Transaction hash
            sender_idx: Sender IDX (encrypted identity)
            receiver_idx: Receiver IDX (encrypted identity)
            amount: Transaction amount
            anomaly_score: Anomaly detection score
            anomaly_flags: List of anomaly flags

        Returns:
            dict: Encrypted data with key shares for each authority

        Example:
            >>> enc = AnomalyThresholdEncryption()
            >>> encrypted = enc.encrypt_transaction_details(
            ...     transaction_hash="0xabc123",
            ...     sender_idx="IDX_SENDER",
            ...     receiver_idx="IDX_RECEIVER",
            ...     amount=Decimal('10000000.00'),
            ...     anomaly_score=75.5,
            ...     anomaly_flags=['HIGH_VALUE_TIER_1']
            ... )
            >>> 'encrypted_details' in encrypted
            True
            >>> 'key_shares' in encrypted
            True
        """
        # Generate random encryption key
        encryption_key = self._generate_encryption_key()

        # Package transaction details
        transaction_details = {
            'transaction_hash': transaction_hash,
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount),
            'anomaly_score': anomaly_score,
            'anomaly_flags': anomaly_flags,
            'encrypted_at': datetime.now(timezone.utc).isoformat()
        }

        # Encrypt details with the key
        details_json = json.dumps(transaction_details, sort_keys=True)
        encrypted_details = self._xor_encrypt(details_json, encryption_key)

        # Split encryption key using threshold secret sharing
        key_shares, key_hash = self._split_encryption_key(encryption_key)

        # Package encrypted data (THIS PACKAGE IS SAFE TO STORE ON-CHAIN)
        # It intentionally omits `key_shares`; shares must be distributed
        # out-of-band to each authority. We include `key_hash` so later
        # the chain can be used to verify shares without leaking the key.
        encrypted_package = {
            'version': '1.0',
            'encryption_scheme': 'XOR-SHA256',  # In production: AES-256-GCM
            'threshold_scheme': 'Shamir-Secret-Sharing',
            'access_structure': 'Company + Supreme Court + 1-of-4 (RBI/FIU/CBI/IT)',

            # Encrypted transaction details (stored on private chain)
            'encrypted_details': encrypted_details,
            # Public metadata (safe to store on-chain)
            'transaction_hash': transaction_hash,
            'encrypted_at': transaction_details['encrypted_at'],
            'threshold': 3,
            'key_hash': key_hash
        }

        # Return both the on-chain package (without shares) and the
        # out-of-band key shares mapping. Callers MUST persist only
        # `encrypted_package` on-chain and distribute `key_shares` to
        # authorities via a secure channel.
        return {
            'encrypted_package': encrypted_package,
            'key_shares': key_shares
        }

    def _split_encryption_key(self, encryption_key: str) -> Tuple[Dict[str, Dict[str, Any]], str]:
        """
        Split encryption key into threshold shares

        SECURITY FIX: Now properly shares the encryption key itself (not its hash).
        The reconstructed secret can be used to derive the original encryption key.

        Args:
            encryption_key: Master encryption key (hex string starting with '0x')

        Returns:
            tuple: (shares dict, key_hash for verification)
        """
        # Remove '0x' prefix and convert hex key to integer
        key_hex = encryption_key[2:] if encryption_key.startswith('0x') else encryption_key

        # Convert key bytes to integer representation
        # This is the actual secret we're sharing (not a hash!)
        secret_int = int(key_hex, 16) % self.prime

        # Store hash for verification (doesn't reveal the key)
        key_hash = hashlib.sha256(encryption_key.encode()).hexdigest()

        # Generate random polynomial coefficients
        # P(x) = secret + a1*x + a2*x^2
        coefficients = [secret_int]
        for _ in range(2):  # threshold - 1 = 3 - 1 = 2
            coeff = secrets.randbelow(self.prime)
            coefficients.append(coeff)

        # Generate shares for each holder
        shares = {}
        for holder, holder_id in self.ANOMALY_SHARE_HOLDERS.items():
            # Evaluate polynomial at holder_id
            share_value = 0
            for i, coeff in enumerate(coefficients):
                share_value += coeff * pow(holder_id, i, self.prime)
                share_value %= self.prime

            shares[holder] = {
                'holder': holder,
                'holder_id': holder_id,
                'x': holder_id,
                'y': share_value,
                'threshold': 3,
                'is_mandatory': holder in self.MANDATORY
                # SECURITY FIX: Removed 'encryption_key' field
                # Shares now only contain mathematical values (x, y)
                # The encryption key must be reconstructed from shares
            }
        return shares, key_hash

    def decrypt_transaction_details(
        self,
        encrypted_package: Dict[str, Any],
        provided_shares: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Decrypt transaction details using provided key shares

        Args:
            encrypted_package: Encrypted transaction package
            provided_shares: Key shares from authorities (need 3)

        Returns:
            dict: Decrypted transaction details

        Raises:
            ValueError: If insufficient shares or wrong access structure

        Example:
            >>> enc = AnomalyThresholdEncryption()
            >>> encrypted = enc.encrypt_transaction_details(...)
            >>>
            >>> # Court order: Company + Supreme Court + RBI provide shares
            >>> decrypted = enc.decrypt_transaction_details(
            ...     encrypted,
            ...     [
            ...         encrypted['key_shares']['company'],
            ...         encrypted['key_shares']['supreme_court'],
            ...         encrypted['key_shares']['rbi']
            ...     ]
            ... )
        """
        # Verify access structure
        if not self._verify_access_structure(provided_shares):
            raise ValueError(
                "Invalid access structure. Need: Company + Supreme Court + "
                "ONE of (RBI/FIU/CBI/Income Tax)"
            )

        # Reconstruct encryption key from provided shares. Note: the
        # on-chain `encrypted_package` does not contain `key_shares`;
        # `provided_shares` must be the out-of-band shares collected
        # from authorities.
        encryption_key = self._reconstruct_encryption_key(provided_shares)

        # Decrypt transaction details
        encrypted_details = encrypted_package['encrypted_details']
        details_json = self._xor_decrypt(encrypted_details, encryption_key)

        # Parse decrypted details
        transaction_details = json.loads(details_json)

        return transaction_details

    def _reconstruct_encryption_key(
        self,
        provided_shares: List[Dict[str, Any]]
    ) -> str:
        """
        Reconstruct encryption key from provided shares

        SECURITY FIX: Now properly reconstructs the key from mathematical shares
        without relying on plaintext key being stored in shares.

        Args:
            provided_shares: Shares provided by authorities

        Returns:
            str: Reconstructed encryption key

        Raises:
            ValueError: If reconstruction fails or shares are invalid
        """
        # Perform Lagrange interpolation to recover secret
        secret_int = 0

        for i, share_i in enumerate(provided_shares):
            xi = share_i['x']
            yi = share_i['y']

            # Calculate Lagrange basis polynomial
            numerator = 1
            denominator = 1

            for j, share_j in enumerate(provided_shares):
                if i != j:
                    xj = share_j['x']
                    numerator *= (0 - xj)  # Evaluate at x=0 to get secret
                    denominator *= (xi - xj)

            # Compute modular inverse
            denominator_inv = pow(denominator % self.prime, -1, self.prime)

            # Add to secret
            secret_int += yi * numerator * denominator_inv
            secret_int %= self.prime

        # Convert reconstructed secret_int back to encryption key
        # The secret_int is the integer representation of the original key
        # Convert to hex string with proper padding (64 hex chars = 32 bytes = 256 bits)
        reconstructed_key_hex = format(secret_int, '064x')  # Pad to 64 hex chars
        encryption_key = '0x' + reconstructed_key_hex

        return encryption_key

    def _verify_access_structure(self, shares: List[Dict[str, Any]]) -> bool:
        """
        Verify that provided shares satisfy access structure

        Access structure:
        - Company (mandatory)
        - Supreme Court (mandatory)
        - Any 1 of: RBI, FIU, CBI, Income Tax

        Args:
            shares: Provided key shares

        Returns:
            bool: True if valid access structure
        """
        if len(shares) < 3:
            return False

        holders = [s['holder'] for s in shares]

        # Check mandatory shares
        for mandatory in self.MANDATORY:
            if mandatory not in holders:
                return False

        # Check at least one optional share
        has_optional = any(holder in self.OPTIONAL for holder in holders)

        return has_optional

    def get_share_for_authority(
        self,
        key_shares: Dict[str, Dict[str, Any]],
        authority: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get key share for specific authority

        Args:
            encrypted_package: Encrypted package
            authority: Authority name ('company', 'supreme_court', 'rbi', etc.)

        Returns:
            dict: Key share for authority, or None if not found
        """
        return key_shares.get(authority)

    def distribute_key_shares(self, key_shares: Dict[str, Dict[str, Any]], sender_func=None) -> Dict[str, bool]:
        """Distribute key shares to authorities.

        This helper iterates key_shares and either calls `sender_func(authority, share)`
        for each share (if provided) or returns the mapping of authority->True to
        indicate readiness. `sender_func` should perform secure out-of-band delivery.
        """
        results = {}
        for auth, share in key_shares.items():
            if sender_func:
                try:
                    sender_func(auth, share)
                    results[auth] = True
                except Exception:
                    results[auth] = False
            else:
                # No-op: just mark as available for manual distribution
                results[auth] = True
        return results

    def list_required_authorities(self) -> Dict[str, List[str]]:
        """
        List required authorities for decryption

        Returns:
            dict: Mandatory and optional authorities
        """
        return {
            'mandatory': self.MANDATORY.copy(),
            'optional': self.OPTIONAL.copy(),
            'description': 'Need ALL mandatory + ANY ONE optional'
        }


# Testing
if __name__ == "__main__":
    """
    Test Anomaly Threshold Encryption
    Run: python3 -m core.crypto.anomaly_threshold_encryption
    """
    print("=== Anomaly Threshold Encryption Testing ===\n")

    enc = AnomalyThresholdEncryption()

    # Test 1: Encrypt transaction details
    print("Test 1: Encrypt Transaction Details")

    encrypted = enc.encrypt_transaction_details(
        transaction_hash="0xabc123def456",
        sender_idx="IDX_SENDER_9ada28aeb",
        receiver_idx="IDX_RECEIVER_1f498a455",
        amount=Decimal('10000000.00'),  # ₹1 crore
        anomaly_score=85.5,
        anomaly_flags=['HIGH_VALUE_TIER_2', 'PMLA_MANDATORY_REPORTING']
    )
    # encrypted now contains two keys: 'encrypted_package' (safe to store on-chain)
    # and 'key_shares' (must be distributed out-of-band).
    encrypted_package = encrypted['encrypted_package']
    key_shares = encrypted['key_shares']

    print(f"  Transaction hash: {encrypted_package['transaction_hash']}")
    print(f"  Encrypted details: {encrypted_package['encrypted_details'][:30]}...")
    print(f"  Key shares created: {len(key_shares)}")
    print(f"  Threshold: {encrypted_package['threshold']}")
    assert 'encrypted_details' in encrypted_package
    assert 'key_shares' in encrypted
    assert len(key_shares) == 6  # 6 authorities
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Decrypt with Company + Supreme Court + RBI
    print("Test 2: Decrypt with Company + Supreme Court + RBI")

    # Decrypt using the out-of-band shares
    decrypted = enc.decrypt_transaction_details(
        encrypted_package,
        [
            key_shares['company'],
            key_shares['supreme_court'],
            key_shares['rbi']
        ]
    )

    print(f"  Transaction hash: {decrypted['transaction_hash']}")
    print(f"  Amount: ₹{decrypted['amount']}")
    print(f"  Anomaly score: {decrypted['anomaly_score']}")
    print(f"  Anomaly flags: {decrypted['anomaly_flags']}")
    assert decrypted['transaction_hash'] == "0xabc123def456"
    assert decrypted['amount'] == '10000000.00'
    assert decrypted['anomaly_score'] == 85.5
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Decrypt with different authority (FIU instead of RBI)
    print("Test 3: Decrypt with Company + Supreme Court + FIU")

    decrypted = enc.decrypt_transaction_details(
        encrypted_package,
        [
            key_shares['company'],
            key_shares['supreme_court'],
            key_shares['fiu']
        ]
    )

    assert decrypted['transaction_hash'] == "0xabc123def456"
    print(f"  Decrypted successfully with FIU")
    print("  [PASS] Test 3 passed!\n")

    # Test 4: Try with CBI
    print("Test 4: Decrypt with Company + Supreme Court + CBI")

    decrypted = enc.decrypt_transaction_details(
        encrypted_package,
        [
            key_shares['company'],
            key_shares['supreme_court'],
            key_shares['cbi']
        ]
    )

    assert decrypted['transaction_hash'] == "0xabc123def456"
    print(f"  Decrypted successfully with CBI")
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Try with Income Tax
    print("Test 5: Decrypt with Company + Supreme Court + Income Tax")

    decrypted = enc.decrypt_transaction_details(
        encrypted_package,
        [
            key_shares['company'],
            key_shares['supreme_court'],
            key_shares['income_tax']
        ]
    )

    assert decrypted['transaction_hash'] == "0xabc123def456"
    print(f"  Decrypted successfully with Income Tax")
    print("  [PASS] Test 5 passed!\n")

    # Test 6: Fail without Company (mandatory)
    print("Test 6: Should Fail Without Company (Mandatory)")

    try:
        decrypted = enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['supreme_court'],
                key_shares['rbi'],
                key_shares['fiu']
            ]
        )
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 6 passed!\n")

    # Test 7: Fail without Supreme Court (mandatory)
    print("Test 7: Should Fail Without Supreme Court (Mandatory)")

    try:
        decrypted = enc.decrypt_transaction_details(
            encrypted_package,
            [
                key_shares['company'],
                key_shares['rbi'],
                key_shares['fiu']
            ]
        )
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 7 passed!\n")

    # Test 8: Fail with only 2 shares
    print("Test 8: Should Fail With Only 2 Shares")

    try:
        decrypted = enc.decrypt_transaction_details(
            encrypted,
            [
                encrypted['key_shares']['company'],
                encrypted['key_shares']['supreme_court']
            ]
        )
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        print("  [PASS] Test 8 passed!\n")

    # Test 9: Get share for specific authority
    print("Test 9: Get Share for Specific Authority")

    rbi_share = enc.get_share_for_authority(key_shares, 'rbi')
    print(f"  RBI share holder: {rbi_share['holder']}")
    print(f"  RBI share ID: {rbi_share['holder_id']}")
    assert rbi_share['holder'] == 'rbi'
    print("  [PASS] Test 9 passed!\n")

    # Test 10: List required authorities
    print("Test 10: List Required Authorities")

    authorities = enc.list_required_authorities()
    print(f"  Mandatory: {authorities['mandatory']}")
    print(f"  Optional: {authorities['optional']}")
    print(f"  Description: {authorities['description']}")
    assert 'company' in authorities['mandatory']
    assert 'supreme_court' in authorities['mandatory']
    assert 'rbi' in authorities['optional']
    assert 'fiu' in authorities['optional']
    print("  [PASS] Test 10 passed!\n")

    print("=" * 50)
    print("[PASS] All Anomaly Threshold Encryption tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Transaction details encryption")
    print("  • Threshold key splitting (6 shares)")
    print("  • Mandatory keys (Company + Supreme Court)")
    print("  • Optional keys (1-of-4: RBI/FIU/CBI/IT)")
    print("  • Secure decryption (need exactly 3 shares)")
    print("  • Access control enforcement")
    print()
    print("Court Order Decryption Model:")
    print("  Required shares:")
    print("    [PASS] Company (always)")
    print("    [PASS] Supreme Court (always)")
    print("    [PASS] RBI OR FIU OR CBI OR Income Tax (any 1)")
    print()
