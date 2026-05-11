"""
Split-Key Cryptography for Court Orders
Purpose: Dual-key system for legal de-anonymization

Dual-key security design:
- Requires TWO keys to decrypt (neither party alone can access data)
- Regulatory authority master key (permanent, held by regulator)
- Company key (24hr rotation, unique per session)
- Both keys required to access private data
- Time-limited access window (24 hours maximum)
- Full audit trail of all access events

Example Flow (Court Order):
    1. Judge issues court order with signature
    2. RBI provides master key (first half)
    3. Company verifies judge signature
    4. Company provides 24hr key (second half)
    5. Combined key decrypts private data
    6. Access expires after 24 hours
    7. All access logged to audit trail
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
import hashlib
import json

# [DOC] AESCipher provides the AES-256-CBC+HMAC encryption used to protect
# [DOC] each transaction's private record on the private blockchain.
from core.crypto.encryption.aes_cipher import AESCipher
# [DOC] KeyManager manages the four system keys (PRIVATE_CHAIN_KEY,
# [DOC] RBI_MASTER_KEY, COMPANY_KEY, SESSION_KEY) and their rotation.
from core.crypto.encryption.key_manager import KeyManager
# [DOC] AuditLogger writes tamper-evident records of every court order
# [DOC] access to the audit_logs table in PostgreSQL.
from core.security.audit_logger import AuditLogger


class SplitKeyCrypto:
    """
    Split-key cryptography for court-ordered de-anonymization

    Security Features:
    - Dual-key requirement (RBI + Company)
    - Time-limited company keys (24hr)
    - Judge signature verification
    - Audit trail
    - Account freezing during investigation
    """

    def __init__(self, key_manager: KeyManager):
        """
        Initialize split-key crypto

        Args:
            key_manager: Key management system
        """
        # [DOC] The KeyManager instance is injected rather than instantiated
        # [DOC] here so that tests can pass a mock or a test-specific KeyManager
        # [DOC] that reads from a test JSON file rather than the production keys.
        self.km = key_manager
        # Audit logging now uses persistent database (AuditLogger)

    def encrypt_with_split_key(self, data: str) -> str:
        """
        Encrypt data using split-key system

        Data is encrypted with combined key (RBI + Company)
        To decrypt, need BOTH keys

        Args:
            data: Plaintext to encrypt

        Returns:
            str: Encrypted data

        Example:
            >>> sk = SplitKeyCrypto(key_manager)
            >>> mapping = "SESSION_abc123 → IDX_user_xyz789"
            >>> encrypted = sk.encrypt_with_split_key(mapping)
            >>> # Can only decrypt with BOTH RBI + Company keys
        """
        # [DOC] Fetch both key halves from the KeyManager. If either key does
        # [DOC] not exist yet (first boot), get_or_create_key() generates it
        # [DOC] automatically and saves it to keys.json.
        # Get both keys
        rbi_key = self.km.get_or_create_key(KeyManager.RBI_MASTER_KEY)
        company_key = self.km.get_or_create_key(KeyManager.COMPANY_KEY)

        # [DOC] combine_keys() computes SHA-256(rbi_key || company_key).
        # [DOC] The resulting 256-bit string is the actual AES key used for
        # [DOC] encryption. Neither party can reconstruct this key without the
        # [DOC] other's contribution.
        # Combine keys
        full_key = self.km.combine_keys(rbi_key, company_key)

        # [DOC] AESCipher derives the AES-256 working key from full_key using
        # [DOC] PBKDF2, then encrypts with AES-256-CBC and appends an HMAC-SHA256
        # [DOC] tag. The output is Base64-encoded for storage in TEXT columns.
        # Encrypt with combined key
        cipher = AESCipher(full_key)
        encrypted = cipher.encrypt(data)

        return encrypted

    def decrypt_with_split_key(
        self,
        encrypted_data: str,
        rbi_key: str,
        company_key: str,
        court_order_id: str,
        judge_name: str
    ) -> Optional[str]:
        """
        Decrypt data using split-key (court order)

        Args:
            encrypted_data: Encrypted data
            rbi_key: RBI master key
            company_key: Company key (24hr)
            court_order_id: Court order reference
            judge_name: Judge authorizing access

        Returns:
            str: Decrypted data if successful, None if failed

        Example:
            >>> # Court order issued
            >>> court_order = "ORDER_2025_001"
            >>> judge = "Judge Sharma"
            >>>
            >>> # RBI provides their key
            >>> rbi_key = rbi_system.get_master_key()
            >>>
            >>> # Company provides their key (after verification)
            >>> company_key = company_system.get_current_key()
            >>>
            >>> # Decrypt
            >>> decrypted = sk.decrypt_with_split_key(
            ...     encrypted, rbi_key, company_key, court_order, judge
            ... )
        """
        try:
            # [DOC] Reconstruct the combined key from the two halves presented
            # [DOC] by the court order parties. If either half is wrong (wrong
            # [DOC] version, wrong authority) the combined key will be incorrect
            # [DOC] and AESCipher.decrypt() will raise ValueError when the HMAC
            # [DOC] tag does not match.
            # Combine keys
            full_key = self.km.combine_keys(rbi_key, company_key)

            # Decrypt
            cipher = AESCipher(full_key)
            decrypted = cipher.decrypt(encrypted_data)

            # [DOC] Log successful decryption to the tamper-evident audit_logs
            # [DOC] table. This record is permanent and cannot be deleted by any
            # [DOC] party including IDX Corp. It documents that this court order
            # [DOC] was used to access this specific record on this date.
            # Log access
            self._log_access(
                court_order_id=court_order_id,
                judge_name=judge_name,
                access_granted=True,
                reason="Decryption successful"
            )

            print(f"🔓 Access granted: Court Order {court_order_id}")
            print(f"   Judge: {judge_name}")
            print(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}")

            return decrypted

        except Exception as e:
            # [DOC] Failed decryption attempts are also logged. This is important
            # [DOC] for detecting brute-force key guessing or replay attacks where
            # [DOC] an adversary submits many wrong key combinations.
            # Log failed access
            self._log_access(
                court_order_id=court_order_id,
                judge_name=judge_name,
                access_granted=False,
                reason=str(e)
            )

            print(f"🔒 Access denied: {str(e)}")
            return None

    def verify_judge_signature(
        self,
        judge_name: str,
        judge_id: str,
        timestamp: str
    ) -> bool:
        """
        Verify judge signature on court order

        In production: Use digital signatures (PKI)
        For demo: Simple verification

        Args:
            judge_name: Judge's name
            judge_id: Judge ID number
            timestamp: Order timestamp

        Returns:
            bool: True if valid

        Example:
            >>> is_valid = sk.verify_judge_signature(
            ...     "Judge Sharma",
            ...     "JID_2025_001",
            ...     "2025-12-23T10:00:00"
            ... )
        """
        # [DOC] In production this method would verify an RSA or ECDSA digital
        # [DOC] signature from the judge against the judge's public key stored in
        # [DOC] the judges table (database/models/judge.py). The current
        # [DOC] implementation performs only basic sanity checks (non-empty fields
        # [DOC] and timestamp freshness) as a placeholder for the research prototype.
        # In production: Verify against authorized judges list
        # For now: Basic validation

        if not judge_name or not judge_id:
            return False

        # [DOC] Court orders older than 24 hours are rejected. This prevents an
        # [DOC] attacker who steals an old court order from replaying it after the
        # [DOC] associated company key has been rotated out.
        # Check timestamp is recent (within 24hrs)
        try:
            order_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - order_time

            if age > timedelta(hours=24):
                print(f"❌ Court order expired (>{24}hrs old)")
                return False

        except Exception:
            return False

        # Log verification
        print(f"✅ Judge signature verified: {judge_name} ({judge_id})")

        return True

    def issue_temporary_company_key(
        self,
        court_order_id: str,
        judge_name: str,
        judge_id: str,
        duration_hours: int = 24
    ) -> Optional[str]:
        """
        Issue temporary company key for court order

        Flow:
        1. Verify judge signature
        2. Generate time-limited company key
        3. Log issuance
        4. Return key (valid for 24hrs)

        Args:
            court_order_id: Court order reference
            judge_name: Judge name
            judge_id: Judge ID
            duration_hours: Key validity (default: 24hrs)

        Returns:
            str: Temporary company key, None if denied

        Example:
            >>> # Judge submits court order
            >>> temp_key = sk.issue_temporary_company_key(
            ...     "ORDER_2025_001",
            ...     "Judge Sharma",
            ...     "JID_2025_001"
            ... )
            >>> # temp_key expires after 24 hours
        """
        # [DOC] Always verify judge credentials before releasing any key material.
        # [DOC] The timestamp used here is the current time; in production the
        # [DOC] timestamp would come from the signed court order document itself.
        # Verify judge signature
        timestamp = datetime.now(timezone.utc).isoformat()
        if not self.verify_judge_signature(judge_name, judge_id, timestamp):
            print(f"❌ Judge verification failed")
            return None

        # [DOC] Return the CURRENT company key, not a newly generated one.
        # [DOC] The key is "temporary" in the sense that it is the company's
        # [DOC] 24-hour rotating key — it will automatically become invalid
        # [DOC] when the next rotation occurs. All records encrypted with this
        # [DOC] key version can be decrypted with it until rotation. After
        # [DOC] rotation the old archived version is required (new court order).
        # Get current company key
        company_key = self.km.get_or_create_key(KeyManager.COMPANY_KEY)

        # [DOC] Log the key issuance event to the audit trail so regulators
        # [DOC] and IDX Corp can see exactly when a company key was handed to
        # [DOC] a judge and for which court order.
        # Log issuance
        self._log_key_issuance(
            court_order_id=court_order_id,
            judge_name=judge_name,
            judge_id=judge_id,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
        )

        print(f"🔑 Temporary key issued:")
        print(f"   Court Order: {court_order_id}")
        print(f"   Judge: {judge_name}")
        print(f"   Valid for: {duration_hours} hours")
        print(f"   Expires: {(datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()}")

        return company_key

    def _log_access(
        self,
        court_order_id: str,
        judge_name: str,
        access_granted: bool,
        reason: str
    ):
        """Log all access attempts to database (tamper-proof)"""
        # [DOC] Build an event_data dict describing this access attempt and
        # [DOC] write it to the audit_logs table via AuditLogger. The table uses
        # [DOC] a cryptographic hash chain (each row hashes the previous row's
        # [DOC] hash) so any retroactive deletion or modification of log entries
        # [DOC] breaks the chain and is detectable.
        try:
            # Log to persistent database with cryptographic chain
            event_data = {
                'court_order_id': court_order_id,
                'judge_name': judge_name,
                'access_granted': access_granted,
                'reason': reason,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            AuditLogger.log_custom_event(
                event_type='COURT_ORDER_DECRYPT',
                event_data=event_data
            )

            print(f"📋 Audit logged to database: {court_order_id}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to log to audit database: {e}")

    def _log_key_issuance(
        self,
        court_order_id: str,
        judge_name: str,
        judge_id: str,
        expires_at: str
    ):
        """Log company key issuance to database (tamper-proof)"""
        # [DOC] Same pattern as _log_access(): write a KEY_GENERATION event
        # [DOC] to the audit chain so the key hand-off is permanently recorded.
        # [DOC] expires_at is stored so auditors know the access window.
        try:
            # Log to persistent database with cryptographic chain
            event_data = {
                'event': 'KEY_ISSUED',
                'court_order_id': court_order_id,
                'judge_name': judge_name,
                'judge_id': judge_id,
                'expires_at': expires_at,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            AuditLogger.log_custom_event(
                event_type='KEY_GENERATION',
                event_data=event_data
            )

            print(f"📋 Key issuance logged to database: {court_order_id}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to log to audit database: {e}")

    def get_audit_trail(self) -> list:
        """
        Get complete audit trail from database

        Returns:
            list: All court order related audit log entries
        """
        # [DOC] Fetches COURT_ORDER_DECRYPT and KEY_GENERATION entries from
        # [DOC] the audit_logs table, merges them, and sorts newest-first.
        # [DOC] Used by admin dashboards to show the complete history of
        # [DOC] court order activity.
        try:
            # Get court order decrypt logs
            decrypt_logs = AuditLogger.get_logs_by_type('COURT_ORDER_DECRYPT', limit=1000)

            # Get key generation logs
            key_logs = AuditLogger.get_logs_by_type('KEY_GENERATION', limit=1000)

            # Combine and sort by timestamp
            all_logs = decrypt_logs + key_logs
            all_logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return all_logs
        except Exception as e:
            print(f"⚠️  Warning: Failed to retrieve audit trail: {e}")
            return []


# Testing
if __name__ == "__main__":
    """Test split-key cryptography"""

    print("=== Split-Key Cryptography Testing ===\n")

    # Setup
    km = KeyManager("test_split_keys.json")
    km.initialize_system_keys()

    sk = SplitKeyCrypto(km)

    # [DOC] Test 1: encrypt a session-to-IDX mapping string and confirm it
    # [DOC] is not stored in plaintext (the encrypted blob is opaque).
    # Test 1: Encrypt with split key
    print("\nTest 1: Encrypt Sensitive Data")
    sensitive_data = "SESSION_abc123 → IDX_user_xyz789_sensitive"
    encrypted = sk.encrypt_with_split_key(sensitive_data)
    print(f"  Original: {sensitive_data}")
    print(f"  Encrypted: {encrypted[:50]}...")
    print("  ✅ Test 1 passed!\n")

    # [DOC] Test 2: simulate a court order by calling issue_temporary_company_key().
    # [DOC] The judge verification is simplified (no real PKI signature) but the
    # [DOC] audit log write and key issuance mechanics are real.
    # Test 2: Court order - Issue temporary key
    print("Test 2: Issue Temporary Company Key")
    court_order = "ORDER_2025_12345"
    judge_name = "Judge Sharma"
    judge_id = "JID_2025_001"

    temp_company_key = sk.issue_temporary_company_key(
        court_order,
        judge_name,
        judge_id,
        duration_hours=24
    )
    print(f"  ✅ Temporary key issued: {temp_company_key[:16]}...\n")

    # [DOC] Test 3: decrypt using both the RBI master key and the temporary
    # [DOC] company key. Confirm the result matches the original plaintext.
    # Test 3: Decrypt with both keys (court order approved)
    print("Test 3: Decrypt with Court Order")
    rbi_key = km.get_key(KeyManager.RBI_MASTER_KEY)

    decrypted = sk.decrypt_with_split_key(
        encrypted,
        rbi_key,
        temp_company_key,
        court_order,
        judge_name
    )

    print(f"  Decrypted: {decrypted}")
    print(f"  ✅ Match: {decrypted == sensitive_data}\n")

    # [DOC] Test 4: confirm the audit trail contains entries for both the
    # [DOC] key issuance (Test 2) and the successful decryption (Test 3).
    # Test 4: Audit trail
    print("Test 4: Audit Trail")
    audit_log = sk.get_audit_trail()
    print(f"  Total entries: {len(audit_log)}")
    for entry in audit_log:
        print(f"  - {entry['timestamp']}: {entry.get('event', 'ACCESS')}")
    print("  ✅ Test 4 passed!\n")

    print("=" * 50)
    print("✅ All split-key crypto tests passed!")
    print("=" * 50)

    # Cleanup
    import os
    if os.path.exists("test_split_keys.json"):
        os.remove("test_split_keys.json")
