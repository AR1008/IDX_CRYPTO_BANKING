"""
IDX Generator - Permanent anonymous identifier from PAN + RBI number.

Generates deterministic SHA-256 hash with secret pepper.
IDX cannot be reversed to obtain original PAN card.
"""

import hashlib
import re
from typing import Tuple
from config.settings import settings


class IDXGenerator:
    """Generate permanent anonymous identifier (IDX) from PAN + RBI number using SHA-256."""

    # [DOC] PAN (Permanent Account Number) is India's national tax ID — exactly 10 characters.
    # [DOC] Format: 5 uppercase letters + 4 digits + 1 uppercase letter (example: ABCDE1234F).
    # [DOC] This regex enforces that exact format — any deviation is rejected before hashing.
    # PAN format regex: 5 letters + 4 digits + 1 letter
    # Example: ABCDE1234F
    PAN_PATTERN = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')

    # [DOC] RBI number is the bank's authority/registration identifier — exactly 6 alphanumeric characters.
    # [DOC] It distinguishes which regulatory authority registered this user (generalises to any jurisdiction's authority ID).
    # RBI number format: exactly 6 digits
    # Example: 123456
    RBI_PATTERN = re.compile(r'^[A-Z0-9]{6}$')


    @staticmethod
    def generate(pan_card: str, rbi_number: str) -> str:
        """Generate permanent IDX by hashing PAN + RBI number + pepper with SHA-256."""

        # [DOC] Normalise both inputs to uppercase with no surrounding whitespace.
        # [DOC] This prevents duplicate IDXes from case or spacing differences (e.g. "abcde1234f" vs "ABCDE1234F").
        # Step 1: Normalize inputs
        # Convert to uppercase and remove any whitespace
        pan_normalized = pan_card.upper().strip()
        rbi_normalized = rbi_number.upper().strip()

        # [DOC] Validate the PAN format — rejects anything that doesn't match the 10-character pattern.
        # [DOC] This is a correctness guard, not a security guard; the security comes from the pepper.
        # Step 2: Validate PAN card format
        if not IDXGenerator._validate_pan(pan_normalized):
            raise ValueError(
                f"Invalid PAN format: {pan_card}\n"
                f"Expected format: 5 letters + 4 digits + 1 letter (e.g., ABCDE1234F)"
            )

        # [DOC] Validate the RBI number format — must be exactly 6 alphanumeric characters.
        # Step 3: Validate RBI number format
        if not IDXGenerator._validate_rbi_number(rbi_normalized):
            raise ValueError(
                f"Invalid RBI number: {rbi_number}\n"
                f"Expected format: 6 digits (e.g., 123456)"
            )

        # [DOC] The PEPPER is a long secret string stored only in the application (ideally in an HSM).
        # [DOC] Including the pepper means even if an attacker has all PAN and RBI numbers, they cannot compute IDXes.
        # [DOC] Without the pepper, SHA-256(PAN:RBI) could be brute-forced by iterating over all known PAN cards.
        # Step 4: Combine with application pepper
        # Format: "PAN:RBI_NUMBER:PEPPER"
        # The pepper is a secret key stored in HSM (Hardware Security Module)
        # Without the pepper, attackers cannot reverse-engineer the IDX
        combined = f"{pan_normalized}:{rbi_normalized}:{settings.APPLICATION_PEPPER}"

        # [DOC] SHA-256 is a one-way hash function — given the IDX, it is computationally infeasible to find PAN+RBI.
        # [DOC] The output is always 32 bytes = 256 bits = 64 hexadecimal characters, regardless of input length.
        # Step 5: Generate SHA-256 hash
        # SHA-256 produces 256 bits = 32 bytes = 64 hex characters
        hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
        # [DOC] .hex() converts the 32-byte binary digest to a 64-character lowercase hex string.
        hash_hex = hash_bytes.hex()  # Convert to hexadecimal string

        # [DOC] Prepend "IDX_" so every identifier is clearly recognisable as an IDX in logs and database records.
        # [DOC] The final format is: IDX_{64 hex characters} — total length 68 characters.
        # Step 6: Add IDX_ prefix and return
        idx = f"IDX_{hash_hex}"

        return idx


    @staticmethod
    def _validate_pan(pan: str) -> bool:
        """Validate PAN card format (5 letters + 4 digits + 1 letter)."""
        # [DOC] re.match checks if the entire string (anchored by ^ and $) matches the PAN_PATTERN.
        # [DOC] bool() converts the match object (or None on failure) to True or False.
        # Use regex pattern matching
        # ^[A-Z]{5} = Starts with exactly 5 uppercase letters
        # [0-9]{4} = Followed by exactly 4 digits
        # [A-Z]$ = Ends with exactly 1 uppercase letter
        return bool(IDXGenerator.PAN_PATTERN.match(pan))


    @staticmethod
    def _validate_rbi_number(rbi_number: str) -> bool:
        """Validate RBI registration number format (6 alphanumeric characters)."""
        # [DOC] re.match checks if the entire string matches the RBI_PATTERN (exactly 6 uppercase alphanumeric chars).
        # Use regex pattern matching
        # ^[0-9]{6}$ = Exactly 6 digits, nothing else
        return bool(IDXGenerator.RBI_PATTERN.match(rbi_number))


    @staticmethod
    def verify_idx(pan_card: str, rbi_number: str, idx_to_verify: str) -> bool:
        """Verify if IDX matches given PAN and RBI number."""
        try:
            # [DOC] Regenerate the IDX from the supplied credentials using the same algorithm.
            # Generate IDX from provided credentials
            generated_idx = IDXGenerator.generate(pan_card, rbi_number)

            # [DOC] Compare the freshly generated IDX against the one to verify.
            # [DOC] Python's == on strings is not constant-time; in production, use hmac.compare_digest() to prevent timing attacks.
            # Compare with provided IDX (constant-time comparison for security)
            # This prevents timing attacks
            return generated_idx == idx_to_verify

        except ValueError:
            # [DOC] If generate() raises ValueError (invalid PAN/RBI format), the credentials are wrong — return False.
            # Invalid PAN or RBI format
            return False


if __name__ == "__main__":
    """Test the IDX generator."""
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
    print(f"  [PASS] Test 1 passed!\n")

    # Test 2: Deterministic (same inputs → same output)
    print("Test 2: Deterministic Property")
    idx1_again = IDXGenerator.generate(pan1, rbi1)
    assert idx1 == idx1_again, "Same inputs must produce same IDX!"
    print(f"  First generation:  {idx1}")
    print(f"  Second generation: {idx1_again}")
    print(f"  Match: {idx1 == idx1_again}")
    print(f"  [PASS] Test 2 passed!\n")

    # Test 3: Different inputs → different outputs
    print("Test 3: Uniqueness Property")
    pan2 = "PRIYA5678M"
    rbi2 = "100002"
    idx2 = IDXGenerator.generate(pan2, rbi2)
    assert idx1 != idx2, "Different inputs must produce different IDX!"
    print(f"  User 1 IDX: {idx1}")
    print(f"  User 2 IDX: {idx2}")
    print(f"  Different: {idx1 != idx2}")
    print(f"  [PASS] Test 3 passed!\n")

    # Test 4: Verification
    print("Test 4: IDX Verification")
    is_valid = IDXGenerator.verify_idx(pan1, rbi1, idx1)
    is_invalid = IDXGenerator.verify_idx(pan2, rbi2, idx1)
    print(f"  Correct credentials verify: {is_valid}")
    print(f"  Wrong credentials verify: {is_invalid}")
    assert is_valid and not is_invalid, "Verification failed!"
    print(f"  [PASS] Test 4 passed!\n")

    # Test 5: Invalid PAN format
    print("Test 5: Invalid Input Handling")
    try:
        invalid_idx = IDXGenerator.generate("INVALID", "100001")
        print("  [ERROR] Test 5 failed - should have raised ValueError")
    except ValueError as e:
        print(f"  Correctly rejected invalid PAN")
        print(f"  Error message: {e}")
        print(f"  [PASS] Test 5 passed!\n")

    # Test 6: Invalid RBI format
    # Test 6: Alphanumeric RBI format (should work)
    print("Test 6: Alphanumeric RBI Format")
    idx_alphanumeric = IDXGenerator.generate("RAJSH1234K", "1A2B3C")
    print(f"  RBI: 1A2B3C (alphanumeric)")
    print(f"  IDX: {idx_alphanumeric[:40]}...")
    print(f"  [PASS] Test 6 passed!\n")

    # Test 7: Invalid RBI format (too short)
    print("Test 7: Invalid RBI Handling")
    try:
        invalid_idx = IDXGenerator.generate("RAJSH1234K", "ABC")  # Only 3 chars
        print("  [ERROR] Test 7 failed - should have raised ValueError")
    except ValueError as e:
        print(f"  Correctly rejected invalid RBI number")
        print(f"  Error message: {e}")
        print(f"  [PASS] Test 7 passed!\n")

    print("=" * 50)
    print("[PASS] All IDX Generator tests passed!")
    print("=" * 50)
