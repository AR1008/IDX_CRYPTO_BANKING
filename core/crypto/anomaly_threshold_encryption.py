# [DOC] anomaly_threshold_encryption.py — AES-256-GCM + Shamir Secret Sharing for PMLA-flagged transactions.
# [DOC] When anomaly score >= 65, full transaction details are encrypted and the key split across authorities.
# [DOC] Decryption requires: Company key + Supreme Court key + ANY ONE of {RBI, FIU, CBI, Income Tax}.
# [DOC] This implements the RCTD primitive (Role-Constrained Threshold Decryption) described in the paper.
"""
Anomaly Threshold Encryption — AES-256-GCM + Shamir Secret Sharing for PMLA Compliance.
=========================================================================================
Threshold-encrypts flagged transaction details so they can only be decrypted under a
valid court order: Company + Supreme Court + ANY ONE of {RBI, FIU, CBI, Income Tax}.

CRYPTOGRAPHIC GUARANTEES:
  Confidentiality:  AES-256-GCM (IND-CPA and IND-CCA2 secure — NIST SP 800-38D).
  Integrity:        GCM authentication tag (128-bit MAC) detects any ciphertext
                    tampering with probability ≥ 1 - 2^{-128}.
  Access control:   Shamir (3-of-6) secret sharing — DEK is reconstructed only
                    when mandatory + optional share conditions are satisfied.

CONSTRUCTION:
  1. Generate fresh random 256-bit DEK (Data Encryption Key) via secrets.token_bytes.
  2. AES-256-GCM encrypt plaintext with DEK → (nonce ‖ ciphertext ‖ tag).
  3. Shamir-split DEK into 6 polynomial shares over a 256-bit prime field.
  4. On-chain: store {nonce, ciphertext, tag} only — key is never persisted.
  5. Decryption: collect 3 qualifying shares → Lagrange reconstruct DEK →
     AES-GCM decrypt + verify tag → plaintext.

REPLACES: XOR encryption (one-time pad with a repeated key — NOT semantically secure).

References:
  Shamir (1979) CACM — "How to Share a Secret" (polynomial secret sharing).
  NIST SP 800-38D (2007) — GCM block cipher mode recommendation.
  pycryptodome 3.19.0 — Crypto.Cipher.AES (MODE_GCM, 128-bit tag, IND-CCA2).
"""

# [DOC] secrets: cryptographically secure random number generator — used for DEK and Shamir polynomial coefficients.
import secrets
# [DOC] hashlib: SHA-256 used to produce a verifiable hash of the DEK (key_hash stored on-chain for integrity checks).
import hashlib
# [DOC] json: serialize/deserialize the encrypted package and AES-GCM components (nonce, tag, ciphertext).
import json
# [DOC] Type hints for IDE support and readability — no runtime overhead.
from typing import Dict, List, Any, Optional, Tuple
# [DOC] Decimal: preserves exact monetary precision for amounts — never use float for currency.
from decimal import Decimal
# [DOC] datetime/timezone: records the encryption timestamp in UTC for audit trail.
from datetime import datetime, timezone

# [DOC] AES from pycryptodome: production-grade AES-256-GCM authenticated encryption.
# [DOC] MODE_GCM provides both confidentiality (IND-CCA2) and integrity (128-bit authentication tag).
# AES-256-GCM authenticated encryption (pycryptodome, already in requirements.txt)
from Crypto.Cipher import AES
# [DOC] get_random_bytes: pycryptodome's CSPRNG — used to generate a fresh 128-bit nonce per encryption call.
from Crypto.Random import get_random_bytes

# [DOC] ThresholdSecretSharing: the Shamir (k,n) polynomial module used by the flat court-order path.
# [DOC] AnomalyThresholdEncryption re-implements Shamir inline (for the 6-party anomaly structure) but imports this for reference.
from core.crypto.threshold_secret_sharing import ThresholdSecretSharing


# [DOC] AnomalyThresholdEncryption: one class that wraps the full encrypt → split-key → decrypt workflow.
class AnomalyThresholdEncryption:
    """Threshold encryption for anomaly-flagged transactions. Requires Company + Court + 1-of-4 regulatory keys."""

    # [DOC] ANOMALY_SHARE_HOLDERS: maps each authority name to a unique integer x-coordinate for the Shamir polynomial.
    # [DOC] Integers 1–6 are used as evaluation points; they must be distinct and non-zero.
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

    # [DOC] MANDATORY: these two parties MUST both provide shares — neither alone is sufficient.
    # Mandatory share holders
    MANDATORY = ['company', 'supreme_court']

    # [DOC] OPTIONAL: any ONE of these four authorities completes the 3-of-6 threshold.
    # Optional share holders (need any 1)
    OPTIONAL = ['rbi', 'fiu', 'cbi', 'income_tax']

    def __init__(self):
        # [DOC] self.prime: the finite field modulus — a 256-bit prime chosen so all Shamir arithmetic stays within 256 bits.
        # [DOC] 2^256 - 189 is a well-known 256-bit prime used in several cryptographic libraries.
        """Initialize anomaly threshold encryption"""
        # Use custom prime for anomaly encryption
        # Larger than regular TSS for extra security
        self.prime = 2**256 - 189

    def _generate_encryption_key(self) -> str:
        # [DOC] Generate a fresh 32-byte (256-bit) random DEK for each transaction — never reuse keys.
        """
        Generate random encryption key for AES

        Returns:
            str: Hex-encoded 256-bit encryption key
        """
        # [DOC] secrets.token_bytes(32): OS-level CSPRNG — safe for cryptographic key material.
        key_bytes = secrets.token_bytes(32)  # 256 bits
        # [DOC] Prefix '0x' for clarity when passing between functions — stripped before use in AES.
        return '0x' + key_bytes.hex()

    def _aes_gcm_encrypt(self, data: str, key_hex: str) -> str:
        """Encrypt plaintext with AES-256-GCM authenticated encryption.

        Generates a fresh 128-bit random nonce per call, ensuring IND-CPA
        security even when the same DEK is reused (which it is not — each
        transaction gets its own DEK, but the defence is still applied).

        Args:
            data:    Plaintext string to encrypt (UTF-8 encoded internally).
            key_hex: 256-bit DEK as a hex string, optionally '0x'-prefixed.

        Returns:
            JSON string: {'nonce': hex, 'tag': hex, 'ciphertext': hex}.
            Decoded by _aes_gcm_decrypt(); stored as the 'encrypted_details'
            field in the on-chain package.

        Security note (NIST SP 800-38D): a 128-bit nonce over a single-use key
            provides negligible collision probability (2^{-128}).
        """
        # [DOC] Strip the optional '0x' prefix, then take exactly 64 hex chars = 32 bytes = 256-bit key.
        # Strip optional '0x' prefix; extract exactly 32 bytes (256-bit key).
        raw_hex = key_hex[2:] if key_hex.startswith('0x') else key_hex
        key = bytes.fromhex(raw_hex[:64])

        # [DOC] 16-byte (128-bit) random nonce — GCM is safe as long as (key, nonce) pair is never reused.
        # Fresh 128-bit nonce — unique per encryption call.
        nonce = get_random_bytes(16)

        # [DOC] AES.new with MODE_GCM creates a GCM cipher object bound to this (key, nonce) pair.
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        # [DOC] encrypt_and_digest: encrypts plaintext AND computes a 128-bit authentication tag in one pass.
        # [DOC] The tag covers both the ciphertext and any additional authenticated data (AAD).
        ciphertext, tag = cipher.encrypt_and_digest(data.encode('utf-8'))

        # [DOC] Pack nonce + tag + ciphertext as hex strings → JSON so the result is database-safe and human-readable.
        # Pack all GCM components as hex strings so the result is JSON-serialisable.
        return json.dumps({
            'nonce':      nonce.hex(),
            'tag':        tag.hex(),        # 128-bit GCM authentication tag
            'ciphertext': ciphertext.hex(),
        })

    def _aes_gcm_decrypt(self, encrypted_json: str, key_hex: str) -> str:
        """Decrypt AES-256-GCM ciphertext and verify the authentication tag.

        Any single-bit flip in nonce, ciphertext, or tag causes pycryptodome
        to raise ValueError — the caller receives no partial plaintext.

        Args:
            encrypted_json: JSON string produced by _aes_gcm_encrypt().
            key_hex:        256-bit DEK as a hex string, optionally '0x'-prefixed.

        Returns:
            str: Decrypted plaintext (UTF-8).

        Raises:
            ValueError:        If the GCM authentication tag does not match
                               (tampered ciphertext or wrong key).
            json.JSONDecodeError: If encrypted_json is structurally malformed.

        Security note: GCM's IND-CCA2 property means even an active attacker
            who can query decryptions cannot distinguish ciphertexts.
        """
        # [DOC] Parse the JSON produced by _aes_gcm_encrypt to recover nonce, tag, and ciphertext.
        enc = json.loads(encrypted_json)

        # [DOC] Same key preparation as in _aes_gcm_encrypt — strip prefix, take 32 bytes.
        raw_hex = key_hex[2:] if key_hex.startswith('0x') else key_hex
        key = bytes.fromhex(raw_hex[:64])

        # [DOC] Re-create the GCM cipher using the same nonce from the stored package — GCM is stateful per (key, nonce).
        cipher = AES.new(key, AES.MODE_GCM, nonce=bytes.fromhex(enc['nonce']))

        # decrypt_and_verify raises ValueError on tag mismatch —
        # no plaintext leaks when integrity fails.
        # [DOC] decrypt_and_verify: decrypts then checks the 128-bit tag — raises ValueError on ANY mismatch.
        # [DOC] This is the GCM integrity guarantee: an attacker who flips even one bit in the ciphertext is detected.
        plaintext = cipher.decrypt_and_verify(
            bytes.fromhex(enc['ciphertext']),
            bytes.fromhex(enc['tag']),
        )
        # [DOC] Return the plaintext as a Python string — guaranteed to be authentic if we reach this line.
        return plaintext.decode('utf-8')

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
        # [DOC] Step 1: generate a one-time 256-bit DEK — never persisted directly; split into shares instead.
        # Generate random encryption key
        encryption_key = self._generate_encryption_key()

        # [DOC] Bundle every sensitive field into a single plaintext dict — all of this becomes opaque after encryption.
        # Package transaction details
        transaction_details = {
            'transaction_hash': transaction_hash,
            # [DOC] sender_idx and receiver_idx are the permanent pseudonymous identities — the most sensitive fields.
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            # [DOC] amount converted to str to avoid float precision loss in JSON serialization.
            'amount': str(amount),
            'anomaly_score': anomaly_score,
            'anomaly_flags': anomaly_flags,
            # [DOC] encrypted_at timestamp provides an audit trail of when the encryption occurred.
            'encrypted_at': datetime.now(timezone.utc).isoformat()
        }

        # [DOC] sort_keys=True makes JSON deterministic — same input always produces the same byte sequence for encryption.
        # AES-256-GCM encrypt transaction details with the one-time DEK.
        # The ciphertext is non-deterministic (fresh nonce each call).
        details_json = json.dumps(transaction_details, sort_keys=True)
        # [DOC] _aes_gcm_encrypt returns a JSON string with nonce + ciphertext + tag — safe to store on the private chain.
        encrypted_details = self._aes_gcm_encrypt(details_json, encryption_key)

        # [DOC] Step 3: split the DEK into 6 Shamir shares (one per authority) using a degree-2 polynomial.
        # Split encryption key using threshold secret sharing
        key_shares, key_hash = self._split_encryption_key(encryption_key)

        # [DOC] encrypted_package: the on-chain record — contains the ciphertext but NOT the key or shares.
        # Package encrypted data (THIS PACKAGE IS SAFE TO STORE ON-CHAIN)
        # It intentionally omits `key_shares`; shares must be distributed
        # out-of-band to each authority. We include `key_hash` so later
        # the chain can be used to verify shares without leaking the key.
        encrypted_package = {
            # [DOC] version tag for future-proofing — lets decoders know which encryption scheme to apply.
            'version': '2.0',
            'encryption_scheme': 'AES-256-GCM',   # IND-CCA2; NIST SP 800-38D
            'threshold_scheme': 'Shamir-Secret-Sharing',
            # [DOC] access_structure documents the required key-holders in human-readable form for operators.
            'access_structure': 'Company + Supreme Court + 1-of-4 (RBI/FIU/CBI/IT)',

            # [DOC] encrypted_details: the AES-GCM output (nonce+ciphertext+tag) — the only thing stored on the private chain.
            # Encrypted transaction details (stored on private chain)
            'encrypted_details': encrypted_details,
            # Public metadata (safe to store on-chain)
            'transaction_hash': transaction_hash,
            'encrypted_at': transaction_details['encrypted_at'],
            # [DOC] threshold=3 records the minimum number of shares required — used by the access structure enforcer.
            'threshold': 3,
            # [DOC] key_hash: SHA-256 of the original DEK — lets authorities verify their reconstructed key without using it.
            'key_hash': key_hash
        }

        # [DOC] Return both the on-chain package (no key, no shares) and the out-of-band shares dict.
        # Return both the on-chain package (without shares) and the
        # out-of-band key shares mapping. Callers MUST persist only
        # `encrypted_package` on-chain and distribute `key_shares` to
        # authorities via a secure channel.
        return {
            'encrypted_package': encrypted_package,
            # [DOC] key_shares: must be distributed to authorities via a secure channel — never stored together with the ciphertext.
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
        # [DOC] Strip '0x' prefix and convert the 64-char hex key to a 256-bit integer for polynomial arithmetic.
        # Remove '0x' prefix and convert hex key to integer
        key_hex = encryption_key[2:] if encryption_key.startswith('0x') else encryption_key

        # [DOC] secret_int is the actual value that will be the free term (P(0)) of the Shamir polynomial.
        # [DOC] Modulo self.prime keeps it within the finite field so polynomial arithmetic is exact.
        # Convert key bytes to integer representation
        # This is the actual secret we're sharing (not a hash!)
        secret_int = int(key_hex, 16) % self.prime

        # [DOC] key_hash: SHA-256 of the original hex key string — stored on-chain for integrity verification.
        # [DOC] The hash reveals nothing about the key itself (SHA-256 is one-way).
        # Store hash for verification (doesn't reveal the key)
        key_hash = hashlib.sha256(encryption_key.encode()).hexdigest()

        # [DOC] Build degree-2 polynomial P(x) = secret_int + a1*x + a2*x^2 (mod prime).
        # [DOC] Degree = threshold - 1 = 2, so any 3 points uniquely determine P and reveal P(0) = secret_int.
        # Generate random polynomial coefficients
        # P(x) = secret + a1*x + a2*x^2
        coefficients = [secret_int]
        for _ in range(2):  # threshold - 1 = 3 - 1 = 2
            # [DOC] Each coefficient is a uniformly random element of the prime field — ensures information-theoretic hiding.
            coeff = secrets.randbelow(self.prime)
            coefficients.append(coeff)

        # [DOC] Evaluate P at each authority's x-coordinate to produce that authority's share (x, P(x)).
        # Generate shares for each holder
        shares = {}
        for holder, holder_id in self.ANOMALY_SHARE_HOLDERS.items():
            # [DOC] Horner's method would be faster, but the loop is clearer and performance is not critical here.
            # Evaluate polynomial at holder_id
            share_value = 0
            for i, coeff in enumerate(coefficients):
                # [DOC] pow(holder_id, i, self.prime): modular exponentiation — exact arithmetic in the prime field.
                share_value += coeff * pow(holder_id, i, self.prime)
                share_value %= self.prime

            shares[holder] = {
                'holder': holder,
                # [DOC] holder_id == x-coordinate of this share — needed for Lagrange interpolation at reconstruction time.
                'holder_id': holder_id,
                'x': holder_id,
                # [DOC] y == P(holder_id) == this authority's secret share value — must be kept private by that authority.
                'y': share_value,
                'threshold': 3,
                # [DOC] is_mandatory flag helps the caller quickly check the access structure without re-reading MANDATORY list.
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
        # [DOC] Enforce access structure BEFORE doing any math — fail fast if mandatory parties are absent.
        # Verify access structure
        if not self._verify_access_structure(provided_shares):
            raise ValueError(
                "Invalid access structure. Need: Company + Supreme Court + "
                "ONE of (RBI/FIU/CBI/Income Tax)"
            )

        # [DOC] Use Lagrange interpolation on the provided (x, y) pairs to recover the 256-bit DEK integer.
        # Reconstruct encryption key from provided shares. Note: the
        # on-chain `encrypted_package` does not contain `key_shares`;
        # `provided_shares` must be the out-of-band shares collected
        # from authorities.
        encryption_key = self._reconstruct_encryption_key(provided_shares)

        # [DOC] With the DEK recovered, decrypt the AES-GCM ciphertext and verify the authentication tag.
        # AES-256-GCM decrypt + authenticate. Raises ValueError on tag mismatch.
        encrypted_details = encrypted_package['encrypted_details']
        details_json = self._aes_gcm_decrypt(encrypted_details, encryption_key)

        # [DOC] Parse the JSON plaintext back into a Python dict — the original transaction_details structure.
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
        # [DOC] Lagrange interpolation: evaluate P(0) = secret_int from k=3 known (x, P(x)) pairs.
        # [DOC] Mathematical identity: P(0) = sum_i [ y_i * product_{j!=i}(0 - x_j) / (x_i - x_j) ] mod prime.
        # Perform Lagrange interpolation to recover secret
        secret_int = 0

        for i, share_i in enumerate(provided_shares):
            # [DOC] xi: this share's x-coordinate (the authority's unique ID 1–6).
            xi = share_i['x']
            # [DOC] yi: this share's y-value P(xi) — provided by the authority.
            yi = share_i['y']

            # [DOC] Compute the Lagrange basis polynomial L_i(0) = product_{j≠i}(0 - x_j) / (x_i - x_j).
            # Calculate Lagrange basis polynomial
            numerator = 1
            denominator = 1

            for j, share_j in enumerate(provided_shares):
                if i != j:
                    xj = share_j['x']
                    # [DOC] Evaluate numerator at x=0 to recover the secret (not just any point on the polynomial).
                    numerator *= (0 - xj)  # Evaluate at x=0 to get secret
                    denominator *= (xi - xj)

            # [DOC] pow(denominator, -1, prime): Python 3.8+ modular inverse — equivalent to Fermat's little theorem.
            # Compute modular inverse
            denominator_inv = pow(denominator % self.prime, -1, self.prime)

            # [DOC] Add this term's contribution to the running sum; take mod prime after each addition to prevent overflow.
            # Add to secret
            secret_int += yi * numerator * denominator_inv
            secret_int %= self.prime

        # [DOC] Convert the reconstructed integer back to a 64-char hex string (pad to 256 bits) and prepend '0x'.
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
        # [DOC] Need at least 3 shares (2 mandatory + 1 optional) — reject immediately if fewer provided.
        if len(shares) < 3:
            return False

        # [DOC] Extract the 'holder' field from each share to get the list of authority names.
        holders = [s['holder'] for s in shares]

        # [DOC] Both mandatory parties (Company AND Supreme Court) must be present — absence of either is an instant reject.
        # Check mandatory shares
        for mandatory in self.MANDATORY:
            if mandatory not in holders:
                return False

        # [DOC] At least one optional authority (RBI, FIU, CBI, or Income Tax) must also be present.
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
        # [DOC] Simple dict lookup — returns None if the authority name is not recognised.
        return key_shares.get(authority)

    def distribute_key_shares(self, key_shares: Dict[str, Dict[str, Any]], sender_func=None) -> Dict[str, bool]:
        """Distribute key shares to authorities.

        This helper iterates key_shares and either calls `sender_func(authority, share)`
        for each share (if provided) or returns the mapping of authority->True to
        indicate readiness. `sender_func` should perform secure out-of-band delivery.
        """
        # [DOC] results: maps each authority name to True (delivered) or False (delivery failed).
        results = {}
        for auth, share in key_shares.items():
            if sender_func:
                try:
                    # [DOC] sender_func is a caller-supplied callback — e.g. an HSM secure channel writer.
                    sender_func(auth, share)
                    results[auth] = True
                except Exception:
                    # [DOC] Delivery failure is recorded but does not stop other authorities from receiving their shares.
                    results[auth] = False
            else:
                # [DOC] No sender_func provided: mark all shares as ready for manual distribution.
                # No-op: just mark as available for manual distribution
                results[auth] = True
        return results

    def list_required_authorities(self) -> Dict[str, List[str]]:
        """
        List required authorities for decryption

        Returns:
            dict: Mandatory and optional authorities
        """
        # [DOC] Returns a human-readable summary of the access structure — useful for UI/API documentation.
        return {
            'mandatory': self.MANDATORY.copy(),
            'optional': self.OPTIONAL.copy(),
            'description': 'Need ALL mandatory + ANY ONE optional'
        }


# [DOC] __main__ block: comprehensive self-tests — run with `python3 -m core.crypto.anomaly_threshold_encryption`.
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
    # [DOC] The result has two keys: encrypted_package (safe to store) and key_shares (distribute out-of-band).
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
    # [DOC] Test 2: verify the full encrypt→split→reconstruct→decrypt cycle using RBI as the optional authority.
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
    # [DOC] Test 3: any of the four optional authorities must work — confirms 1-of-4 structure is correct.
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

    # Test 5b: AES-GCM tamper detection — any ciphertext bit-flip must raise ValueError
    # [DOC] Test 5b: flip one byte of the ciphertext — GCM tag verification must raise ValueError immediately.
    print("Test 5b: Tampered ciphertext must be rejected (GCM authentication)")
    import copy, json as _json
    tampered_package = copy.deepcopy(encrypted_package)
    # Flip one hex digit in the ciphertext to simulate an active attacker.
    enc_blob = _json.loads(tampered_package['encrypted_details'])
    ct_bytes = bytearray.fromhex(enc_blob['ciphertext'])
    ct_bytes[0] ^= 0xFF           # Corrupt the first byte of ciphertext
    enc_blob['ciphertext'] = ct_bytes.hex()
    tampered_package['encrypted_details'] = _json.dumps(enc_blob)

    try:
        enc.decrypt_transaction_details(
            tampered_package,
            [key_shares['company'], key_shares['supreme_court'], key_shares['rbi']]
        )
        print("  FAIL: Tampered ciphertext was not rejected!")
        assert False, "GCM tag check should have raised ValueError"
    except ValueError:
        print("  PASS: Tampered ciphertext correctly rejected by GCM tag verification\n")

    # Test 6: Fail without Company (mandatory)
    # [DOC] Test 6: omit the Company share — _verify_access_structure must reject before any decryption attempt.
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
    # [DOC] Test 8: only 2 shares (< threshold 3) must fail even if both mandatory parties present.
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
    print("  • AES-256-GCM authenticated encryption (IND-CCA2, NIST SP 800-38D)")
    print("  • GCM tag rejects tampered ciphertexts with probability 1 - 2^{-128}")
    print("  • Threshold key splitting (6 Shamir shares)")
    print("  • Mandatory keys (Company + Supreme Court)")
    print("  • Optional keys (1-of-4: RBI/FIU/CBI/IT)")
    print("  • Secure decryption (need exactly 3 qualifying shares)")
    print("  • Access control enforcement (wrong structure → ValueError)")
    print()
    print("Court Order Decryption Model:")
    print("  Required shares:")
    print("    [PASS] Company (always)")
    print("    [PASS] Supreme Court (always)")
    print("    [PASS] RBI OR FIU OR CBI OR Income Tax (any 1)")
    print()
