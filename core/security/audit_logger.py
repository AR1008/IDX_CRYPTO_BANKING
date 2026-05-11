# [DOC] AuditLogger — the single class responsible for writing the cryptographic hash-chained audit trail.
# [DOC] Every sensitive action (court order access, key generation, user registration, block mining)
# [DOC] is recorded here with a SHA-256 hash linking each entry to the previous one.
# [DOC] If any entry is tampered with, verify_chain() will detect the broken link.

"""
Audit Logger Service
Purpose: Cryptographically-signed, tamper-proof audit trail

Features:
- Automatic cryptographic chaining (each log links to previous)
- Multiple event types supported
- Thread-safe logging
- Chain integrity verification
- Immutable (database rules prevent UPDATE/DELETE)

Usage:
    from core.security.audit_logger import AuditLogger

    # Log court order access
    AuditLogger.log_court_order_access(
        judge_id="JUDGE_12345",
        court_order_number="CO_2025_001",
        session_id="SESSION_abc123...",
        revealed_idx="IDX_def456...",
        ip_address="192.168.1.100"
    )

    # Log key generation
    AuditLogger.log_key_generation(
        user_idx="IDX_abc123...",
        key_type="split_key",
        bank_code="HDFC"
    )

    # Verify chain integrity
    is_valid, message = AuditLogger.verify_chain()
"""

# [DOC] hashlib provides SHA-256; every log entry's hash is computed here.
import hashlib
# [DOC] json.dumps() with sort_keys=True ensures the dict serialisation is deterministic (order-independent).
import json
import logging
# [DOC] threading.Lock prevents two threads from writing log entries simultaneously (which would corrupt the chain).
import threading
from typing import Optional, Dict, Any, Tuple
# [DOC] timezone.utc gives timezone-aware UTC timestamps — avoids DST-related inconsistencies.
from datetime import datetime, timezone
from database.connection import SessionLocal
from database.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit Logger Service - Cryptographic audit trail

    All logs are linked via SHA-256 hash chain:
    Log N → previous_hash = hash(Log N-1)

    Any tampering breaks the chain and is detectable.
    """

    # [DOC] Class-level lock — all instances share the same lock so concurrent writes from different
    # [DOC] threads still serialize correctly (only one log entry is committed at a time).
    _lock = threading.Lock()

    @staticmethod
    def _calculate_hash(
        previous_hash: str,
        event_type: str,
        event_data: Dict[str, Any],
        timestamp: datetime
    ) -> str:
        """
        Calculate SHA-256 hash for log entry

        Args:
            previous_hash: Hash of previous log entry
            event_type: Type of event
            event_data: Event details (dict)
            timestamp: Event timestamp

        Returns:
            SHA-256 hash (hex string)
        """
        # [DOC] Concatenate all entry fields with | separators into a canonical string.
        # [DOC] sort_keys=True ensures the JSON is identical regardless of Python dict ordering.
        # [DOC] timestamp.isoformat() produces a deterministic string from the datetime object.
        log_content = f"{previous_hash}|{event_type}|{json.dumps(event_data, sort_keys=True)}|{timestamp.isoformat()}"

        # [DOC] SHA-256 of the canonical string — .hexdigest() returns a 64-character lowercase hex string.
        return hashlib.sha256(log_content.encode()).hexdigest()

    @staticmethod
    def _create_log(
        event_type: str,
        event_data: Dict[str, Any],
        judge_id: Optional[str] = None,
        court_order_number: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Create audit log entry with cryptographic chain

        Args:
            event_type: Type of event
            event_data: Event details
            judge_id: Judge ID (for court orders)
            court_order_number: Court order number
            ip_address: IP address of requester
            user_agent: User agent string

        Returns:
            Created AuditLog object
        """
        db = SessionLocal()

        try:
            # [DOC] Acquire the class-level lock before reading the latest log or writing a new one.
            # [DOC] Without this lock, two concurrent threads could both read the same "previous" hash
            # [DOC] and produce two entries with the same previous_hash — breaking the chain.
            with AuditLogger._lock:
                # [DOC] Get the most recently written log entry to extract its hash.
                previous_log = AuditLog.get_latest_log(db)
                # [DOC] If no logs exist yet, use the sentinel string "GENESIS" as the anchor.
                previous_hash = previous_log.current_log_hash if previous_log else "GENESIS"

                # [DOC] Capture the timestamp inside the lock so it's consistent with the hash order.
                timestamp = datetime.now(timezone.utc)

                # [DOC] Compute the SHA-256 hash that binds this entry to the previous one.
                current_hash = AuditLogger._calculate_hash(
                    previous_hash=previous_hash,
                    event_type=event_type,
                    event_data=event_data,
                    timestamp=timestamp
                )

                # [DOC] Build the ORM object — the DB row that will be stored.
                log = AuditLog(
                    event_type=event_type,
                    event_data=event_data,
                    judge_id=judge_id,
                    court_order_number=court_order_number,
                    previous_log_hash=previous_hash,   # [DOC] Hash of the immediately preceding entry.
                    current_log_hash=current_hash,     # [DOC] This entry's own hash — future entries will link to it.
                    ip_address=ip_address,
                    user_agent=user_agent,
                    created_at=timestamp
                )

                # [DOC] Append-only write — the DB does not allow UPDATE or DELETE on this table.
                db.add(log)
                db.commit()
                # [DOC] refresh() re-reads the row from DB to populate auto-generated fields (e.g. id).
                db.refresh(log)

                logger.debug(f"Audit log created: {event_type} (ID: {log.id}, Hash: {current_hash[:16]}...)")

                return log

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating audit log: {e}")
            raise

        finally:
            db.close()

    @staticmethod
    def log_court_order_access(
        judge_id: str,
        court_order_number: str,
        session_id: str,
        revealed_idx: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None
    ) -> AuditLog:
        """
        Log court order access to user data

        Args:
            judge_id: Unique identifier for judge
            court_order_number: Court order reference number
            session_id: Session ID that was revealed
            revealed_idx: User IDX that was revealed
            ip_address: IP address of requester
            user_agent: User agent string
            reason: Reason for court order

        Returns:
            Created AuditLog object
        """
        # [DOC] Build a structured dict describing exactly what was revealed — stored as JSON in the DB.
        event_data = {
            'session_id': session_id,
            'revealed_idx': revealed_idx,
            'reason': reason
        }

        # [DOC] Delegate to the internal _create_log() with the specific event type and metadata.
        return AuditLogger._create_log(
            event_type='COURT_ORDER_ACCESS',
            event_data=event_data,
            judge_id=judge_id,
            court_order_number=court_order_number,
            ip_address=ip_address,
            user_agent=user_agent
        )

    @staticmethod
    def log_key_generation(
        user_idx: str,
        key_type: str,
        bank_code: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log cryptographic key generation

        Args:
            user_idx: User IDX for whom key was generated
            key_type: Type of key (split_key, session_key, etc.)
            bank_code: Bank code (if applicable)
            ip_address: IP address of requester

        Returns:
            Created AuditLog object
        """
        event_data = {
            'user_idx': user_idx,
            'key_type': key_type,
            'bank_code': bank_code,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return AuditLogger._create_log(
            event_type='KEY_GENERATION',
            event_data=event_data,
            ip_address=ip_address
        )

    @staticmethod
    def log_user_registration(
        user_idx: str,
        pan_card: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log user registration

        Args:
            user_idx: Generated user IDX
            pan_card: PAN card number (partially masked)
            ip_address: IP address of requester

        Returns:
            Created AuditLog object
        """
        # [DOC] Mask the PAN card before logging: show first 4 chars + **** + last char.
        # [DOC] e.g. "RAJSH1234K" → "RAJS****K" — enough to correlate but not expose the full ID.
        masked_pan = f"{pan_card[:4]}****{pan_card[-1]}" if len(pan_card) >= 5 else "****"

        event_data = {
            'user_idx': user_idx,
            'pan_card_masked': masked_pan,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return AuditLogger._create_log(
            event_type='USER_REGISTRATION',
            event_data=event_data,
            ip_address=ip_address
        )

    @staticmethod
    def log_transaction_created(
        transaction_hash: str,
        sender_idx: str,
        receiver_idx: str,
        amount: float,
        transaction_type: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log transaction creation

        Args:
            transaction_hash: Transaction hash
            sender_idx: Sender user IDX
            receiver_idx: Receiver user IDX
            amount: Transaction amount
            transaction_type: Type of transaction (DOMESTIC, TRAVEL_DEPOSIT, etc.)
            ip_address: IP address of requester

        Returns:
            Created AuditLog object
        """
        # [DOC] Store amount as a string to avoid JSON floating-point representation issues.
        event_data = {
            'transaction_hash': transaction_hash,
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount),
            'transaction_type': transaction_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return AuditLogger._create_log(
            event_type='TRANSACTION_CREATED',
            event_data=event_data,
            ip_address=ip_address
        )

    @staticmethod
    def log_block_mined(
        block_index: int,
        block_hash: str,
        miner_idx: str,
        transaction_count: int,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log block mining

        Args:
            block_index: Block index
            block_hash: Block hash
            miner_idx: Miner user IDX
            transaction_count: Number of transactions in block
            ip_address: IP address of miner

        Returns:
            Created AuditLog object
        """
        event_data = {
            'block_index': block_index,
            'block_hash': block_hash,
            'miner_idx': miner_idx,
            'transaction_count': transaction_count,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return AuditLogger._create_log(
            event_type='BLOCK_MINED',
            event_data=event_data,
            ip_address=ip_address
        )

    @staticmethod
    def log_custom_event(
        event_type: str,
        event_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log custom event

        Args:
            event_type: Custom event type
            event_data: Event details
            ip_address: IP address of requester
            user_agent: User agent string

        Returns:
            Created AuditLog object
        """
        # [DOC] Flexible entry point for any event type not covered by the typed methods above.
        return AuditLogger._create_log(
            event_type=event_type,
            event_data=event_data,
            ip_address=ip_address,
            user_agent=user_agent
        )

    @staticmethod
    def verify_chain(
        start_id: Optional[int] = None,
        end_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Verify integrity of audit log chain

        Args:
            start_id: Starting log ID (None = from beginning)
            end_id: Ending log ID (None = to end)

        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        db = SessionLocal()

        try:
            # [DOC] Delegate to the ORM model's class method which walks the chain and re-computes hashes.
            # [DOC] Returns (True, "OK message") if unbroken, or (False, "Tampered at ID X") if not.
            return AuditLog.verify_chain_integrity(db, start_id, end_id)

        finally:
            db.close()

    @staticmethod
    def get_logs_by_type(event_type: str, limit: int = 100) -> list:
        """
        Get audit logs by event type

        Args:
            event_type: Type of event
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog dictionaries
        """
        db = SessionLocal()

        try:
            # [DOC] AuditLog.get_by_event_type() issues SELECT ... WHERE event_type = ? ORDER BY created_at DESC.
            logs = AuditLog.get_by_event_type(db, event_type, limit)
            return [log.to_dict() for log in logs]

        finally:
            db.close()

    @staticmethod
    def get_court_order_logs(court_order_number: str) -> list:
        """
        Get all logs for a specific court order

        Args:
            court_order_number: Court order number

        Returns:
            List of AuditLog dictionaries
        """
        db = SessionLocal()

        try:
            # [DOC] Returns all log entries tagged with this court order number — entire lifecycle of the order.
            logs = AuditLog.get_by_court_order(db, court_order_number)
            return [log.to_dict() for log in logs]

        finally:
            db.close()

    @staticmethod
    def get_judge_logs(judge_id: str, limit: int = 100) -> list:
        """
        Get all court order accesses by a specific judge

        Args:
            judge_id: Judge identifier
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog dictionaries
        """
        db = SessionLocal()

        try:
            # [DOC] All log entries where judge_id column matches — shows all orders a judge has issued.
            logs = AuditLog.get_by_judge(db, judge_id, limit)
            return [log.to_dict() for log in logs]

        finally:
            db.close()


# Export service
__all__ = ['AuditLogger']


# For testing
if __name__ == "__main__":
    print("=== Audit Logger Test ===\n")

    # Test 1: Log court order access
    print("1. Logging court order access...")
    log1 = AuditLogger.log_court_order_access(
        judge_id="JUDGE_12345",
        court_order_number="CO_2025_001",
        session_id="SESSION_test123",
        revealed_idx="IDX_testuser",
        ip_address="192.168.1.100",
        reason="Tax investigation"
    )
    print(f"   Created log ID: {log1.id}, Hash: {log1.current_log_hash[:32]}...\n")

    # Test 2: Log key generation
    print("2. Logging key generation...")
    log2 = AuditLogger.log_key_generation(
        user_idx="IDX_testuser",
        key_type="split_key",
        bank_code="HDFC",
        ip_address="192.168.1.101"
    )
    print(f"   Created log ID: {log2.id}, Hash: {log2.current_log_hash[:32]}...\n")

    # Test 3: Verify chain
    print("3. Verifying audit chain...")
    is_valid, message = AuditLogger.verify_chain()
    print(f"   Result: {'✅ VALID' if is_valid else '❌ INVALID'}")
    print(f"   Message: {message}\n")

    # Test 4: Get logs by type
    print("4. Retrieving court order logs...")
    court_logs = AuditLogger.get_logs_by_type('COURT_ORDER_ACCESS', limit=10)
    print(f"   Found {len(court_logs)} court order access logs\n")

    # Test 5: Get logs by court order
    print("5. Retrieving logs for court order CO_2025_001...")
    co_logs = AuditLogger.get_court_order_logs('CO_2025_001')
    print(f"   Found {len(co_logs)} logs for this court order\n")

    print("✅ Audit logger test complete!")
