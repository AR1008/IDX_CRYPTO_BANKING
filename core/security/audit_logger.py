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

import hashlib
import json
import threading
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from database.connection import SessionLocal
from database.models.audit_log import AuditLog


class AuditLogger:
    """
    Audit Logger Service - Cryptographic audit trail

    All logs are linked via SHA-256 hash chain:
    Log N → previous_hash = hash(Log N-1)

    Any tampering breaks the chain and is detectable.
    """

    # Thread lock for concurrent logging
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
        # Create deterministic string representation
        log_content = f"{previous_hash}|{event_type}|{json.dumps(event_data, sort_keys=True)}|{timestamp.isoformat()}"

        # Calculate SHA-256
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
            # Thread-safe logging
            with AuditLogger._lock:
                # Get previous log
                previous_log = AuditLog.get_latest_log(db)
                previous_hash = previous_log.current_log_hash if previous_log else "GENESIS"

                # Current timestamp
                timestamp = datetime.utcnow()

                # Calculate current hash
                current_hash = AuditLogger._calculate_hash(
                    previous_hash=previous_hash,
                    event_type=event_type,
                    event_data=event_data,
                    timestamp=timestamp
                )

                # Create log entry
                log = AuditLog(
                    event_type=event_type,
                    event_data=event_data,
                    judge_id=judge_id,
                    court_order_number=court_order_number,
                    previous_log_hash=previous_hash,
                    current_log_hash=current_hash,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    created_at=timestamp
                )

                # Save to database (append-only)
                db.add(log)
                db.commit()
                db.refresh(log)

                print(f"✅ Audit log created: {event_type} (ID: {log.id}, Hash: {current_hash[:16]}...)")

                return log

        except Exception as e:
            db.rollback()
            print(f"❌ Error creating audit log: {e}")
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
        event_data = {
            'session_id': session_id,
            'revealed_idx': revealed_idx,
            'reason': reason
        }

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
            'timestamp': datetime.utcnow().isoformat()
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
        # Mask PAN card (show first 4 and last 1 characters)
        masked_pan = f"{pan_card[:4]}****{pan_card[-1]}" if len(pan_card) >= 5 else "****"

        event_data = {
            'user_idx': user_idx,
            'pan_card_masked': masked_pan,
            'timestamp': datetime.utcnow().isoformat()
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
        event_data = {
            'transaction_hash': transaction_hash,
            'sender_idx': sender_idx,
            'receiver_idx': receiver_idx,
            'amount': str(amount),
            'transaction_type': transaction_type,
            'timestamp': datetime.utcnow().isoformat()
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
            'timestamp': datetime.utcnow().isoformat()
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
