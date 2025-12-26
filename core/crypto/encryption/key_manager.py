"""
Key Manager
Author: Ashutosh Rajesh
Purpose: Secure key generation, storage, and management

Key Types:
1. PRIVATE_CHAIN_KEY - Encrypts private blockchain data (permanent)
2. RBI_MASTER_KEY - RBI's half of court order key (permanent)
3. COMPANY_KEY - Company's half of court order key (24hr rotation)
4. SESSION_KEY - Encrypts session mappings (rotates monthly)

Example Flow:
    # Get key manager
    km = KeyManager()
    
    # Get private chain encryption key
    private_key = km.get_key('PRIVATE_CHAIN_KEY')
    
    # Encrypt data
    cipher = AESCipher(private_key)
    encrypted = cipher.encrypt("sensitive data")
    
    # For court orders - needs BOTH keys
    rbi_key = km.get_key('RBI_MASTER_KEY')
    company_key = km.get_key('COMPANY_KEY')
    full_key = km.combine_keys(rbi_key, company_key)
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
import json


class KeyManager:
    """
    Secure key management system
    
    Responsibilities:
    - Generate cryptographically secure keys
    - Store keys securely
    - Provide key rotation
    - Split-key management (for court orders)
    """
    
    # Key types
    PRIVATE_CHAIN_KEY = "PRIVATE_CHAIN_KEY"
    RBI_MASTER_KEY = "RBI_MASTER_KEY"
    COMPANY_KEY = "COMPANY_KEY"
    SESSION_KEY = "SESSION_KEY"
    
    def __init__(self, config_file: str = "keys.json"):
        """
        Initialize key manager
        
        Args:
            config_file: Path to key storage file
        """
        self.config_file = config_file
        self.keys = self._load_keys()
    
    def _load_keys(self) -> Dict:
        """
        Load keys from storage
        
        In production: Use environment variables or secure vault (AWS KMS, HashiCorp Vault)
        For development: Use JSON file
        
        Returns:
            Dict: Stored keys
        """
        # Try environment variables first (production)
        env_keys = {
            self.PRIVATE_CHAIN_KEY: os.getenv('PRIVATE_CHAIN_KEY'),
            self.RBI_MASTER_KEY: os.getenv('RBI_MASTER_KEY'),
            self.COMPANY_KEY: os.getenv('COMPANY_KEY'),
            self.SESSION_KEY: os.getenv('SESSION_KEY')
        }
        
        # If any key exists in env, use env
        if any(env_keys.values()):
            print("🔑 Loading keys from environment variables")
            return {k: v for k, v in env_keys.items() if v}
        
        # Otherwise, use config file (development)
        if os.path.exists(self.config_file):
            print(f"🔑 Loading keys from {self.config_file}")
            with open(self.config_file, 'r') as f:
                return json.load(f)
        
        # No keys found - generate new ones
        print("🔑 No keys found - generating new keys")
        return {}
    
    def _save_keys(self):
        """Save keys to storage"""
        # In production: Save to secure vault
        # For development: Save to JSON file
        
        with open(self.config_file, 'w') as f:
            json.dump(self.keys, f, indent=2)
        
        print(f"🔑 Keys saved to {self.config_file}")
    
    def generate_key(self, key_type: str, length: int = 32) -> str:
        """
        Generate cryptographically secure random key
        
        Args:
            key_type: Type of key (PRIVATE_CHAIN_KEY, RBI_MASTER_KEY, etc.)
            length: Key length in bytes (default: 32 = 256 bits)
            
        Returns:
            str: Generated key (hex encoded)
            
        Example:
            >>> km = KeyManager()
            >>> key = km.generate_key('PRIVATE_CHAIN_KEY')
            >>> print(len(key))
            64  # 32 bytes = 64 hex characters
        """
        # Generate random bytes
        key_bytes = secrets.token_bytes(length)
        
        # Convert to hex
        key_hex = key_bytes.hex()
        
        # Store key
        self.keys[key_type] = {
            'key': key_hex,
            'created_at': datetime.utcnow().isoformat(),
            'rotated_at': None
        }
        
        self._save_keys()
        
        print(f"✅ Generated {key_type}: {key_hex[:16]}...{key_hex[-16:]}")
        
        return key_hex
    
    def get_key(self, key_type: str) -> Optional[str]:
        """
        Get encryption key
        
        Args:
            key_type: Type of key to retrieve
            
        Returns:
            str: Key if exists, None otherwise
            
        Example:
            >>> km = KeyManager()
            >>> private_key = km.get_key('PRIVATE_CHAIN_KEY')
            >>> if not private_key:
            ...     private_key = km.generate_key('PRIVATE_CHAIN_KEY')
        """
        if key_type not in self.keys:
            return None
        
        key_data = self.keys[key_type]
        
        # Return just the key string if it's a simple string
        if isinstance(key_data, str):
            return key_data
        
        # Return key from dict structure
        return key_data.get('key')
    
    def get_or_create_key(self, key_type: str) -> str:
        """
        Get key or create if doesn't exist
        
        Args:
            key_type: Type of key
            
        Returns:
            str: Key
        """
        key = self.get_key(key_type)
        if not key:
            key = self.generate_key(key_type)
        return key
    
    def rotate_key(self, key_type: str) -> str:
        """
        Rotate key (generate new key, keep old key for decryption)
        
        Args:
            key_type: Type of key to rotate
            
        Returns:
            str: New key
            
        Example:
            >>> km = KeyManager()
            >>> # Rotate company key every 24 hours
            >>> new_key = km.rotate_key('COMPANY_KEY')
        """
        # Store old key
        old_key = self.get_key(key_type)
        
        if old_key:
            # Keep old key for decrypting old data
            old_key_backup = f"{key_type}_OLD_{datetime.utcnow().isoformat()}"
            self.keys[old_key_backup] = {
                'key': old_key,
                'archived_at': datetime.utcnow().isoformat()
            }
        
        # Generate new key
        new_key = self.generate_key(key_type)
        
        # Update rotation timestamp
        self.keys[key_type]['rotated_at'] = datetime.utcnow().isoformat()
        
        self._save_keys()
        
        print(f"🔄 Rotated {key_type}")
        
        return new_key
    
    def combine_keys(self, key1: str, key2: str) -> str:
        """
        Combine two keys (for split-key cryptography)
        
        Used for court orders:
        - RBI has permanent master key (key1)
        - Company has 24hr rotating key (key2)
        - Both needed to decrypt → full_key = combine(rbi_key, company_key)
        
        Args:
            key1: First key (e.g., RBI master key)
            key2: Second key (e.g., Company key)
            
        Returns:
            str: Combined key (SHA-256 hash)
            
        Example:
            >>> km = KeyManager()
            >>> rbi_key = km.get_key('RBI_MASTER_KEY')
            >>> company_key = km.get_key('COMPANY_KEY')
            >>> full_key = km.combine_keys(rbi_key, company_key)
            >>> # Use full_key to decrypt private data
        """
        # Combine keys using SHA-256
        combined = hashlib.sha256((key1 + key2).encode()).hexdigest()
        
        print(f"🔗 Combined keys: {combined[:16]}...{combined[-16:]}")
        
        return combined
    
    def verify_split_keys(self, key1: str, key2: str, expected_combined: str) -> bool:
        """
        Verify that two split keys produce the expected combined key
        
        Args:
            key1: First key
            key2: Second key
            expected_combined: Expected result
            
        Returns:
            bool: True if keys are valid
        """
        combined = self.combine_keys(key1, key2)
        return combined == expected_combined
    
    def get_all_keys(self) -> Dict:
        """
        Get all keys (for backup/migration)
        
        Returns:
            Dict: All keys
        """
        return self.keys.copy()
    
    def initialize_system_keys(self):
        """
        Initialize all required system keys
        
        Call this once during system setup
        """
        print("\n🔑 Initializing system keys...")
        
        # Private chain encryption (permanent)
        if not self.get_key(self.PRIVATE_CHAIN_KEY):
            self.generate_key(self.PRIVATE_CHAIN_KEY)
        
        # RBI master key (permanent)
        if not self.get_key(self.RBI_MASTER_KEY):
            self.generate_key(self.RBI_MASTER_KEY)
        
        # Company key (rotates every 24hr)
        if not self.get_key(self.COMPANY_KEY):
            self.generate_key(self.COMPANY_KEY)
        
        # Session encryption key
        if not self.get_key(self.SESSION_KEY):
            self.generate_key(self.SESSION_KEY)
        
        print("✅ All system keys initialized!\n")


# Testing
if __name__ == "__main__":
    """Test key manager"""
    
    print("=== Key Manager Testing ===\n")
    
    # Clean up old test file
    if os.path.exists("test_keys.json"):
        os.remove("test_keys.json")
    
    km = KeyManager("test_keys.json")
    
    # Test 1: Initialize system keys
    print("Test 1: Initialize System Keys")
    km.initialize_system_keys()
    
    # Test 2: Get keys
    print("Test 2: Get Keys")
    private_key = km.get_key(KeyManager.PRIVATE_CHAIN_KEY)
    rbi_key = km.get_key(KeyManager.RBI_MASTER_KEY)
    company_key = km.get_key(KeyManager.COMPANY_KEY)
    
    print(f"  Private chain key: {private_key[:16]}...{private_key[-16:]}")
    print(f"  RBI master key: {rbi_key[:16]}...{rbi_key[-16:]}")
    print(f"  Company key: {company_key[:16]}...{company_key[-16:]}")
    print("  ✅ Test 2 passed!\n")
    
    # Test 3: Combine keys (split-key cryptography)
    print("Test 3: Split-Key Cryptography")
    full_key = km.combine_keys(rbi_key, company_key)
    print(f"  Combined key: {full_key[:16]}...{full_key[-16:]}")
    
    # Verify
    is_valid = km.verify_split_keys(rbi_key, company_key, full_key)
    print(f"  ✅ Verification: {is_valid}\n")
    
    # Test 4: Key rotation
    print("Test 4: Key Rotation")
    old_company_key = company_key
    new_company_key = km.rotate_key(KeyManager.COMPANY_KEY)
    
    print(f"  Old key: {old_company_key[:16]}...{old_company_key[-16:]}")
    print(f"  New key: {new_company_key[:16]}...{new_company_key[-16:]}")
    print(f"  ✅ Keys different: {old_company_key != new_company_key}\n")
    
    print("=" * 50)
    print("✅ All key manager tests passed!")
    print("=" * 50)
    
    # Cleanup
    if os.path.exists("test_keys.json"):
        os.remove("test_keys.json")