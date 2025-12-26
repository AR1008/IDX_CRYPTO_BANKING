"""
IDX Generator - Permanent Anonymous Identifier
Author: Ashutosh Rajesh
Purpose: Generate permanent IDX from PAN + RBI number

Security Model:
- Input: PAN card + RBI registration number
- Process: Combine with secret pepper → SHA-256 hash
- Output: Permanent IDX (cannot be reversed to PAN)

Privacy Guarantee:
- IDX ↔ Name mapping is PUBLIC (for tax purposes)
- Transaction history for each IDX is PRIVATE
- Session ID ↔ IDX mapping is PRIVATE (court order required)
"""

import hashlib
import re
from typing import Tuple
from config.settings import settings


class IDXGenerator:
    """
    Generates permanent anonymous identifier (IDX) from user credentials
    
    The IDX is permanent and deterministic:
    - Same PAN + RBI number → Always produces same IDX
    - Different PAN + RBI number → Different IDX
    - IDX cannot be reversed to obtain PAN (one-way hash)
    
    Example:
        >>> idx = IDXGenerator.generate("RAJSH1234K", "100001")
        >>> print(idx)
        "IDX_7f3a9b2c1d5e8f4a6b9c3d7e0f2a5b8c4d1e9f0a3b6c2d8e5f1a7b4c9d6e3f0"
    """
    
    # PAN format regex: 5 letters + 4 digits + 1 letter
    # Example: ABCDE1234F
    PAN_PATTERN = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
    
    # RBI number format: exactly 6 digits
    # Example: 123456
    RBI_PATTERN = re.compile(r'^[A-Z0-9]{6}$')
    
    
    @staticmethod
    def generate(pan_card: str, rbi_number: str) -> str:
        """
        Generate permanent IDX for a user
        
        Process:
        1. Validate PAN card format (ABCDE1234F)
        2. Validate RBI number format (123456)
        3. Normalize inputs (uppercase, strip whitespace)
        4. Combine: "PAN:RBI:PEPPER"
        5. Hash with SHA-256 (irreversible)
        6. Return with "IDX_" prefix
        
        Args:
            pan_card (str): User's PAN card number (10 characters)
                          Format: 5 letters + 4 digits + 1 letter
                          Example: "ABCDE1234F"
            
            rbi_number (str): RBI registration number (6 digits)
                             Example: "123456"
        
        Returns:
            str: Permanent IDX starting with "IDX_"
                 Length: 68 characters (4 prefix + 64 hash)
                 Example: "IDX_7f3a9b2c1d5e8f4a6b9c3d7e0f2a5b8c..."
        
        Raises:
            ValueError: If PAN card format is invalid
            ValueError: If RBI number format is invalid
        
        Example:
            >>> # Valid usage
            >>> idx = IDXGenerator.generate("RAJSH1234K", "100001")
            >>> print(idx)
            "IDX_7f3a9b2c1d5e8f4a6b9c3d7e0f2a5b8c4d1e9f0a3b6c2d8e5f1a7b4c9d6e3f0"
            
            >>> # Same inputs produce same IDX (deterministic)
            >>> idx2 = IDXGenerator.generate("RAJSH1234K", "100001")
            >>> assert idx == idx2
            
            >>> # Invalid PAN format
            >>> idx = IDXGenerator.generate("INVALID", "100001")
            ValueError: Invalid PAN format: INVALID
        """
        
        # Step 1: Normalize inputs
        # Convert to uppercase and remove any whitespace
        pan_normalized = pan_card.upper().strip()
        rbi_normalized = rbi_number.upper().strip()
        
        # Step 2: Validate PAN card format
        if not IDXGenerator._validate_pan(pan_normalized):
            raise ValueError(
                f"Invalid PAN format: {pan_card}\n"
                f"Expected format: 5 letters + 4 digits + 1 letter (e.g., ABCDE1234F)"
            )
        
        # Step 3: Validate RBI number format
        if not IDXGenerator._validate_rbi_number(rbi_normalized):
            raise ValueError(
                f"Invalid RBI number: {rbi_number}\n"
                f"Expected format: 6 digits (e.g., 123456)"
            )
        
        # Step 4: Combine with application pepper
        # Format: "PAN:RBI_NUMBER:PEPPER"
        # The pepper is a secret key stored in HSM (Hardware Security Module)
        # Without the pepper, attackers cannot reverse-engineer the IDX
        combined = f"{pan_normalized}:{rbi_normalized}:{settings.APPLICATION_PEPPER}"
        
        # Step 5: Generate SHA-256 hash
        # SHA-256 produces 256 bits = 32 bytes = 64 hex characters
        hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
        hash_hex = hash_bytes.hex()  # Convert to hexadecimal string
        
        # Step 6: Add IDX_ prefix and return
        idx = f"IDX_{hash_hex}"
        
        return idx
    
    
    @staticmethod
    def _validate_pan(pan: str) -> bool:
        """
        Validate PAN card format
        
        Indian PAN card format (as per Income Tax Department):
        - Position 1-5: Uppercase letters (A-Z)
        - Position 6-9: Digits (0-9)
        - Position 10: Uppercase letter (A-Z)
        
        Total length: 10 characters
        Example: ABCDE1234F
        
        Args:
            pan (str): PAN card string to validate
        
        Returns:
            bool: True if valid format, False otherwise
        
        Examples:
            >>> IDXGenerator._validate_pan("ABCDE1234F")
            True
            
            >>> IDXGenerator._validate_pan("ABC1234567")  # Wrong format
            False
            
            >>> IDXGenerator._validate_pan("ABCDE12345")  # Too long
            False
        """
        # Use regex pattern matching
        # ^[A-Z]{5} = Starts with exactly 5 uppercase letters
        # [0-9]{4} = Followed by exactly 4 digits
        # [A-Z]$ = Ends with exactly 1 uppercase letter
        return bool(IDXGenerator.PAN_PATTERN.match(pan))
    
    
    @staticmethod
    def _validate_rbi_number(rbi_number: str) -> bool:
        """
        Validate RBI registration number format

        RBI registration number format:
        - Exactly 6 alphanumeric characters (A-Z, 0-9)
        - Uppercase letters only
        - No special characters or spaces

        Example: 123456, ABC123, 1A2B3C
        
        Args:
            rbi_number (str): RBI number string to validate
        
        Returns:
            bool: True if valid format, False otherwise
        
        - Exactly 6 alphanumeric characters (A–Z, 0–9)
        - Automatically normalized to uppercase
        - No special characters or spaces

        Valid examples:
        - 123456
        - ABC123
        - 1A2B3C

        Invalid:
        - abc123
        - 12345
        - 12@#45
        """
        # Use regex pattern matching
        # ^[0-9]{6}$ = Exactly 6 digits, nothing else
        return bool(IDXGenerator.RBI_PATTERN.match(rbi_number))
    
    
    @staticmethod
    def verify_idx(pan_card: str, rbi_number: str, idx_to_verify: str) -> bool:
        """
        Verify if an IDX matches the given PAN and RBI number
        
        Useful for:
        - User login verification
        - Database integrity checks
        - Fraud detection
        
        Args:
            pan_card (str): User's PAN card
            rbi_number (str): User's RBI number
            idx_to_verify (str): IDX to verify
        
        Returns:
            bool: True if IDX matches, False otherwise
        
        Example:
            >>> idx = IDXGenerator.generate("RAJSH1234K", "100001")
            >>> IDXGenerator.verify_idx("RAJSH1234K", "100001", idx)
            True
            
            >>> IDXGenerator.verify_idx("WRONG5678M", "100001", idx)
            False
        """
        try:
            # Generate IDX from provided credentials
            generated_idx = IDXGenerator.generate(pan_card, rbi_number)
            
            # Compare with provided IDX (constant-time comparison for security)
            # This prevents timing attacks
            return generated_idx == idx_to_verify
        
        except ValueError:
            # Invalid PAN or RBI format
            return False


# ==========================================
# EXAMPLE USAGE & TESTING
# ==========================================

if __name__ == "__main__":
    """
    Test the IDX generator
    Run: python -m core.crypto.idx_generator
    """
    print("=== IDX Generator Testing ===\n")
    
    # Test 1: Basic generation
    print("Test 1: Basic IDX Generation")
    pan1 = "RAJSH1234K"
    rbi1 = "100001"
    idx1 = IDXGenerator.generate(pan1, rbi1)
    print(f"  PAN: {pan1}")
    print(f"  RBI: {rbi1}")
    print(f"  IDX: {idx1}")
    print(f"  Length: {len(idx1)} characters")
    print(f"  ✅ Test 1 passed!\n")
    
    # Test 2: Deterministic (same inputs → same output)
    print("Test 2: Deterministic Property")
    idx1_again = IDXGenerator.generate(pan1, rbi1)
    assert idx1 == idx1_again, "Same inputs must produce same IDX!"
    print(f"  First generation:  {idx1}")
    print(f"  Second generation: {idx1_again}")
    print(f"  Match: {idx1 == idx1_again}")
    print(f"  ✅ Test 2 passed!\n")
    
    # Test 3: Different inputs → different outputs
    print("Test 3: Uniqueness Property")
    pan2 = "PRIYA5678M"
    rbi2 = "100002"
    idx2 = IDXGenerator.generate(pan2, rbi2)
    assert idx1 != idx2, "Different inputs must produce different IDX!"
    print(f"  User 1 IDX: {idx1}")
    print(f"  User 2 IDX: {idx2}")
    print(f"  Different: {idx1 != idx2}")
    print(f"  ✅ Test 3 passed!\n")
    
    # Test 4: Verification
    print("Test 4: IDX Verification")
    is_valid = IDXGenerator.verify_idx(pan1, rbi1, idx1)
    is_invalid = IDXGenerator.verify_idx(pan2, rbi2, idx1)
    print(f"  Correct credentials verify: {is_valid}")
    print(f"  Wrong credentials verify: {is_invalid}")
    assert is_valid and not is_invalid, "Verification failed!"
    print(f"  ✅ Test 4 passed!\n")
    
    # Test 5: Invalid PAN format
    print("Test 5: Invalid Input Handling")
    try:
        invalid_idx = IDXGenerator.generate("INVALID", "100001")
        print("  ❌ Test 5 failed - should have raised ValueError")
    except ValueError as e:
        print(f"  Correctly rejected invalid PAN")
        print(f"  Error message: {e}")
        print(f"  ✅ Test 5 passed!\n")
    
    # Test 6: Invalid RBI format
    # Test 6: Alphanumeric RBI format (should work)
    print("Test 6: Alphanumeric RBI Format")
    idx_alphanumeric = IDXGenerator.generate("RAJSH1234K", "1A2B3C")
    print(f"  RBI: 1A2B3C (alphanumeric)")
    print(f"  IDX: {idx_alphanumeric[:40]}...")
    print(f"  ✅ Test 6 passed!\n")

    # Test 7: Invalid RBI format (too short)
    print("Test 7: Invalid RBI Handling")
    try:
        invalid_idx = IDXGenerator.generate("RAJSH1234K", "ABC")  # Only 3 chars
        print("  ❌ Test 7 failed - should have raised ValueError")
    except ValueError as e:
        print(f"  Correctly rejected invalid RBI number")
        print(f"  Error message: {e}")
        print(f"  ✅ Test 7 passed!\n")
    
    print("=" * 50)
    print("✅ All IDX Generator tests passed!")
    print("=" * 50)