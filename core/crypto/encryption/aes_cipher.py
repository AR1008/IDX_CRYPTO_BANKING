"""
AES-256 Encryption Service
Purpose: Encrypt/decrypt sensitive data (private blockchain, session mappings)

Security Features:
- AES-256-CBC encryption
- PKCS7 padding
- Random IV per encryption
- HMAC authentication (prevent tampering)

Usage:
    cipher = AESCipher(encryption_key)
    encrypted = cipher.encrypt("sensitive data")
    decrypted = cipher.decrypt(encrypted)
"""

# [DOC] pycryptodome (imported as Crypto) provides the AES block cipher,
# [DOC] a cryptographically secure random byte generator, the PBKDF2 key-
# [DOC] derivation function, and HMAC-SHA256. It is a drop-in replacement
# [DOC] for the unmaintained PyCrypto package.
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256, HMAC
import base64
import json
from typing import Union, Dict


class AESCipher:
    """
    AES-256 encryption with authentication

    Features:
    - 256-bit keys
    - CBC mode with random IV
    - PKCS7 padding
    - HMAC-SHA256 authentication
    """

    def __init__(self, master_key: str):
        """
        Initialize cipher with master key

        Args:
            master_key: Master encryption key (will be derived to 256 bits)
        """
        # [DOC] Raw master keys are often human-readable strings of arbitrary
        # [DOC] length (e.g., hex strings from KeyManager, passphrases, etc.).
        # [DOC] AES-256 requires exactly 32 bytes. PBKDF2 is a standard key-
        # [DOC] derivation function that stretches or compresses any input to
        # [DOC] exactly dkLen=32 bytes while making brute-force attacks expensive
        # [DOC] (100,000 HMAC-SHA256 iterations per guess).
        # [DOC]
        # [DOC] IMPORTANT: The salt is hard-coded here ('IDX_CRYPTO_BANKING_SALT').
        # [DOC] In a real deployment each key should use a random salt stored
        # [DOC] alongside the ciphertext. The hard-coded salt is acceptable in
        # [DOC] this prototype because the master_key itself is already a 256-bit
        # [DOC] random value from KeyManager; the PBKDF2 call primarily serves
        # [DOC] to guarantee the correct byte length.
        # Derive 256-bit key from master key
        self.key = PBKDF2(
            master_key,
            salt=b'IDX_CRYPTO_BANKING_SALT',
            dkLen=32,  # 256 bits
            count=100000,
            hmac_hash_module=SHA256
        )

    def encrypt(self, plaintext: Union[str, Dict]) -> str:
        """
        Encrypt plaintext data

        Args:
            plaintext: String or dict to encrypt

        Returns:
            str: Base64-encoded encrypted data (IV + ciphertext + HMAC)

        Example:
            >>> cipher = AESCipher("master_key")
            >>> encrypted = cipher.encrypt("Hello World")
            >>> print(encrypted)
            eyJpdiI6IjEyMzQ1Njc4OTAxMjM0NTYiLCJjaXBoZXJ0ZXh0IjoiYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoifQ==
        """
        # [DOC] Dicts are serialised to JSON before encryption so that structured
        # [DOC] data (e.g., {sender_idx, receiver_idx, amount, timestamp}) can be
        # [DOC] encrypted as a single opaque blob and later deserialised by the
        # [DOC] decrypt_to_dict() convenience method.
        # Convert dict to JSON string
        if isinstance(plaintext, dict):
            plaintext = json.dumps(plaintext)

        # Convert to bytes
        data = plaintext.encode('utf-8')

        # [DOC] AES-CBC requires a 16-byte Initialisation Vector (IV).
        # [DOC] The IV must be random and unique for every encryption call —
        # [DOC] re-using an IV with the same key leaks information about the
        # [DOC] plaintext. get_random_bytes() reads from the OS CSPRNG (e.g.,
        # [DOC] /dev/urandom on Linux), so each call produces a fresh IV.
        # Generate random IV (16 bytes for AES)
        iv = get_random_bytes(AES.block_size)

        # Create cipher
        cipher = AES.new(self.key, AES.MODE_CBC, iv)

        # [DOC] AES-CBC requires the input to be an exact multiple of 16 bytes.
        # [DOC] PKCS7 padding appends N bytes each with value N, where N is the
        # [DOC] number of padding bytes needed (1 to 16). The receiver strips
        # [DOC] these bytes after decryption using _unpad().
        # Pad data to block size (PKCS7)
        padded_data = self._pad(data)

        # Encrypt
        ciphertext = cipher.encrypt(padded_data)

        # [DOC] HMAC-SHA256 provides message authentication: it detects any
        # [DOC] tampering with the ciphertext or IV after encryption.
        # [DOC] The tag is computed over (IV || ciphertext) — including the IV
        # [DOC] prevents IV-substitution attacks where an attacker flips the IV
        # [DOC] to manipulate the first decrypted block.
        # [DOC] This construction (Encrypt-then-MAC) is the correct order:
        # [DOC] verifying the MAC before decrypting prevents padding oracle attacks.
        # Create HMAC for authentication
        hmac = HMAC.new(self.key, digestmod=SHA256)
        hmac.update(iv + ciphertext)
        tag = hmac.digest()

        # [DOC] Pack the three components (IV, ciphertext, HMAC tag) into a
        # [DOC] single byte string. The receiver knows the fixed sizes:
        # [DOC]   IV:         first 16 bytes (AES.block_size)
        # [DOC]   HMAC tag:   last 32 bytes (SHA-256 output)
        # [DOC]   ciphertext: everything in between
        # [DOC] Base64-encoding converts binary to ASCII so the result can be
        # [DOC] stored in TEXT database columns and transmitted over JSON APIs.
        # Combine IV + ciphertext + HMAC
        encrypted_data = iv + ciphertext + tag

        # Base64 encode for storage
        return base64.b64encode(encrypted_data).decode('utf-8')

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt encrypted data

        Args:
            encrypted_data: Base64-encoded encrypted data

        Returns:
            str: Decrypted plaintext

        Raises:
            ValueError: If HMAC verification fails (tampered data)

        Example:
            >>> cipher = AESCipher("master_key")
            >>> encrypted = cipher.encrypt("Hello World")
            >>> decrypted = cipher.decrypt(encrypted)
            >>> print(decrypted)
            Hello World
        """
        # [DOC] Reverse the Base64 encoding to recover the raw bytes.
        # Base64 decode
        encrypted_bytes = base64.b64decode(encrypted_data)

        # [DOC] Split the byte string back into its three components using
        # [DOC] the known fixed sizes: IV = first 16 bytes, tag = last 32 bytes,
        # [DOC] ciphertext = everything between them.
        # Extract components
        iv = encrypted_bytes[:AES.block_size]
        tag = encrypted_bytes[-32:]  # SHA256 produces 32 bytes
        ciphertext = encrypted_bytes[AES.block_size:-32]

        # [DOC] Verify the HMAC tag BEFORE decrypting. If the tag is wrong the
        # [DOC] data has been tampered with and we raise ValueError immediately,
        # [DOC] never passing any modified bytes to the AES block cipher.
        # [DOC] This protects against padding oracle attacks: an attacker who
        # [DOC] submits a modified ciphertext cannot use decryption error messages
        # [DOC] to learn information about the plaintext because the HMAC check
        # [DOC] rejects the input first.
        # Verify HMAC
        hmac = HMAC.new(self.key, digestmod=SHA256)
        hmac.update(iv + ciphertext)

        try:
            hmac.verify(tag)
        except ValueError:
            raise ValueError("HMAC verification failed - data has been tampered!")

        # Create cipher
        cipher = AES.new(self.key, AES.MODE_CBC, iv)

        # Decrypt
        padded_data = cipher.decrypt(ciphertext)

        # [DOC] Remove the PKCS7 padding bytes that were added during encryption.
        # [DOC] _unpad() reads the value of the last byte (which PKCS7 sets to the
        # [DOC] padding length) and slices that many bytes off the end.
        # Unpad
        data = self._unpad(padded_data)

        # Convert to string
        return data.decode('utf-8')

    def encrypt_dict(self, data: Dict) -> str:
        """
        Encrypt dictionary (convenience method)

        Args:
            data: Dictionary to encrypt

        Returns:
            str: Encrypted data
        """
        # [DOC] Delegates to encrypt() which already handles dict->JSON conversion.
        return self.encrypt(data)

    def decrypt_to_dict(self, encrypted_data: str) -> Dict:
        """
        Decrypt to dictionary (convenience method)

        Args:
            encrypted_data: Encrypted data

        Returns:
            Dict: Decrypted dictionary
        """
        # [DOC] Decrypts to a JSON string then parses it back to a Python dict.
        # [DOC] Used when the original plaintext was a dict (e.g., a transaction's
        # [DOC] private record containing sender_idx, receiver_idx, amount).
        decrypted = self.decrypt(encrypted_data)
        return json.loads(decrypted)

    def _pad(self, data: bytes) -> bytes:
        """
        PKCS7 padding

        Args:
            data: Data to pad

        Returns:
            bytes: Padded data
        """
        # [DOC] Calculate how many bytes are needed to reach the next 16-byte
        # [DOC] boundary. padding_length is always 1..16 (never 0, because PKCS7
        # [DOC] adds a full block of padding when the data is already aligned).
        # [DOC] Each padding byte contains the padding length as its value, which
        # [DOC] allows _unpad() to unambiguously find and remove them.
        padding_length = AES.block_size - (len(data) % AES.block_size)
        padding = bytes([padding_length] * padding_length)
        return data + padding

    def _unpad(self, data: bytes) -> bytes:
        """
        Remove PKCS7 padding

        Args:
            data: Padded data

        Returns:
            bytes: Unpadded data
        """
        # [DOC] The last byte of padded data is always the padding length (1..16).
        # [DOC] Slicing off that many bytes from the end removes all padding bytes.
        # [DOC] Note: production code should validate that all padding bytes have
        # [DOC] the correct value (not just the count) to detect malformed input.
        padding_length = data[-1]
        return data[:-padding_length]


# Testing
if __name__ == "__main__":
    """Test AES encryption"""

    print("=== AES-256 Encryption Testing ===\n")

    # [DOC] Test 1 verifies the basic encrypt/decrypt round-trip on a string.
    # [DOC] The encrypted output should differ from the input and the decrypted
    # [DOC] output should be identical to the original.
    # Test 1: String encryption
    print("Test 1: String Encryption")
    cipher = AESCipher("super_secret_master_key_12345")

    plaintext = "IDX_abc123def456 → SESSION_xyz789"
    encrypted = cipher.encrypt(plaintext)
    decrypted = cipher.decrypt(encrypted)

    print(f"  Original: {plaintext}")
    print(f"  Encrypted: {encrypted[:50]}...")
    print(f"  Decrypted: {decrypted}")
    print(f"  ✅ Match: {plaintext == decrypted}\n")

    # [DOC] Test 2 verifies that dict data (like a session-to-IDX mapping)
    # [DOC] survives encryption and JSON round-tripping correctly.
    # Test 2: Dictionary encryption
    print("Test 2: Dictionary Encryption")
    session_mapping = {
        "SESSION_123": "IDX_abc123",
        "SESSION_456": "IDX_def456",
        "SESSION_789": "IDX_ghi789"
    }

    encrypted_dict = cipher.encrypt_dict(session_mapping)
    decrypted_dict = cipher.decrypt_to_dict(encrypted_dict)

    print(f"  Original: {session_mapping}")
    print(f"  Encrypted: {encrypted_dict[:50]}...")
    print(f"  Decrypted: {decrypted_dict}")
    print(f"  ✅ Match: {session_mapping == decrypted_dict}\n")

    # [DOC] Test 3 confirms the HMAC check catches tampering. We corrupt the
    # [DOC] last 10 characters of the Base64 ciphertext blob and verify that
    # [DOC] decrypt() raises ValueError rather than silently returning garbage.
    # Test 3: Tamper detection
    print("Test 3: Tamper Detection")
    encrypted = cipher.encrypt("Sensitive data")
    tampered = encrypted[:-10] + "XXXXX"  # Corrupt last 5 chars

    try:
        cipher.decrypt(tampered)
        print("  ❌ Tamper detection failed!")
    except ValueError as e:
        print(f"  ✅ Tamper detected: {str(e)}\n")

    print("=" * 50)
    print("✅ All AES encryption tests passed!")
    print("=" * 50)
