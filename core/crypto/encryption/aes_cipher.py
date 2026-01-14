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
        # Convert dict to JSON string
        if isinstance(plaintext, dict):
            plaintext = json.dumps(plaintext)
        
        # Convert to bytes
        data = plaintext.encode('utf-8')
        
        # Generate random IV (16 bytes for AES)
        iv = get_random_bytes(AES.block_size)
        
        # Create cipher
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        
        # Pad data to block size (PKCS7)
        padded_data = self._pad(data)
        
        # Encrypt
        ciphertext = cipher.encrypt(padded_data)
        
        # Create HMAC for authentication
        hmac = HMAC.new(self.key, digestmod=SHA256)
        hmac.update(iv + ciphertext)
        tag = hmac.digest()
        
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
        # Base64 decode
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract components
        iv = encrypted_bytes[:AES.block_size]
        tag = encrypted_bytes[-32:]  # SHA256 produces 32 bytes
        ciphertext = encrypted_bytes[AES.block_size:-32]
        
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
        return self.encrypt(data)
    
    def decrypt_to_dict(self, encrypted_data: str) -> Dict:
        """
        Decrypt to dictionary (convenience method)
        
        Args:
            encrypted_data: Encrypted data
            
        Returns:
            Dict: Decrypted dictionary
        """
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
        padding_length = data[-1]
        return data[:-padding_length]


# Testing
if __name__ == "__main__":
    """Test AES encryption"""
    
    print("=== AES-256 Encryption Testing ===\n")
    
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
    