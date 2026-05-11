"""
Audit Log Model
Purpose: Tamper-proof audit trail for security-critical events

Features:
- Append-only (UPDATE/DELETE blocked by database rules)
- Cryptographic chain (previous_log_hash → current_log_hash)
- Supports multiple event types (COURT_ORDER_ACCESS, KEY_GENERATION, etc.)
- JSONB data storage for flexible event details

Usage:
    from database.models.audit_log import AuditLog

    # Query audit logs
    logs = db.query(AuditLog).filter(
        AuditLog.event_type == 'COURT_ORDER_ACCESS'
    ).all()
"""

from sqlalchemy import Column, String, Integer, DateTime, func, Text, Index
# [DOC] JSONB is PostgreSQL's binary JSON type — faster to query and index than plain TEXT JSON
from sqlalchemy.dialects.postgresql import JSONB
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base
from datetime import datetime
from typing import Optional, Dict, Any


# [DOC] One row = one immutable system event; rows are never updated or deleted — append-only by design
# [DOC] The cryptographic hash chain means any tampering with a row invalidates all subsequent rows
class AuditLog(Base):
    """
    Audit Log Model - Tamper-proof event logging

    Table: audit_logs

    Rules:
    - Append-only (database rules prevent UPDATE/DELETE)
    - Each log links to previous via cryptographic hash
    - Supports any event type with flexible JSONB data
    """
    # [DOC] Maps this Python class to the 'audit_logs' PostgreSQL table
    __tablename__ = "audit_logs"

    # Primary key
    # [DOC] Monotonically increasing integer; ordering by id gives exact insertion sequence
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Event information
    # [DOC] Short uppercase string identifying what happened; drives which fields appear in event_data
    # [DOC] Known values: COURT_ORDER_ACCESS, KEY_GENERATION, USER_REGISTRATION,
    # [DOC]               TRANSACTION_CREATED, BLOCK_MINED, ACCOUNT_FREEZE, KEY_ASSEMBLY, etc.
    event_type = Column(String(50), nullable=False, index=True)

    # [DOC] PostgreSQL JSONB column holding all event-specific fields; schema varies by event_type
    # [DOC] Example for COURT_ORDER_ACCESS:
    # [DOC]   {"session_id": "SESSION_...", "revealed_idx": "IDX_...",
    # [DOC]    "court_order_number": "CO_2025_001", "judge_id": "JUDGE_12345"}
    event_data = Column(JSONB, nullable=False)

    # Court order specific fields (for COURT_ORDER_ACCESS events)
    # [DOC] Denormalized from event_data for fast indexed lookups; NULL for non-court-order events
    judge_id = Column(String(100), nullable=True, index=True)
    # [DOC] Court order reference number; denormalized from event_data for fast lookup; NULL for other event types
    court_order_number = Column(String(100), nullable=True, index=True)

    # Cryptographic chain (tamper-evident)
    # [DOC] SHA-256 hash of the PREVIOUS log row's content; NULL (treated as "GENESIS") for the very first row
    # [DOC] If any row is modified, this chain breaks and verify_chain_integrity() detects it
    previous_log_hash = Column(String(64), nullable=True)

    # [DOC] SHA-256 hash computed over: previous_hash | event_type | event_data (sorted JSON) | created_at
    # [DOC] Unique constraint ensures no two rows have the same content hash (prevents replay attacks)
    current_log_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Metadata
    # [DOC] IPv4 or IPv6 address of the HTTP client that triggered this event; used for forensic analysis
    ip_address = Column(String(45), nullable=True)

    # [DOC] HTTP User-Agent header of the client; stored for forensic analysis alongside ip_address
    user_agent = Column(Text, nullable=True)

    # [DOC] UTC timestamp set by the DB at INSERT time; immutable; used in the hash so rows cannot be backdated
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)

    # Indexes for efficient queries
    # [DOC] Composite index on (event_type, created_at) for time-ranged queries filtered by type
    __table_args__ = (
        Index('idx_audit_type_created', 'event_type', 'created_at'),
        Index('idx_audit_court_order', 'court_order_number'),
        Index('idx_audit_judge', 'judge_id'),
        Index('idx_audit_created', 'created_at'),
    )


    def __repr__(self):
        return f"<AuditLog(id={self.id}, type={self.event_type}, created_at={self.created_at})>"


    def to_dict(self) -> Dict[str, Any]:
        """
        Convert audit log to dictionary

        Returns:
            Dictionary representation of audit log
        """
        return {
            'id': self.id,
            'event_type': self.event_type,
            'event_data': self.event_data,
            'judge_id': self.judge_id,
            'court_order_number': self.court_order_number,
            'previous_log_hash': self.previous_log_hash,
            'current_log_hash': self.current_log_hash,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


    @classmethod
    def get_latest_log(cls, db) -> Optional['AuditLog']:
        """
        Get the most recent audit log entry

        Args:
            db: Database session

        Returns:
            Latest AuditLog or None if no logs exist
        """
        return db.query(cls).order_by(cls.id.desc()).first()


    @classmethod
    def get_by_event_type(cls, db, event_type: str, limit: int = 100) -> list:
        """
        Get audit logs by event type

        Args:
            db: Database session
            event_type: Type of event to filter by
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog objects
        """
        return db.query(cls).filter(
            cls.event_type == event_type
        ).order_by(cls.created_at.desc()).limit(limit).all()


    @classmethod
    def get_by_court_order(cls, db, court_order_number: str) -> list:
        """
        Get all audit logs for a specific court order

        Args:
            db: Database session
            court_order_number: Court order number

        Returns:
            List of AuditLog objects
        """
        return db.query(cls).filter(
            cls.court_order_number == court_order_number
        ).order_by(cls.created_at.asc()).all()


    @classmethod
    def get_by_judge(cls, db, judge_id: str, limit: int = 100) -> list:
        """
        Get all court order accesses by a specific judge

        Args:
            db: Database session
            judge_id: Judge identifier
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog objects
        """
        return db.query(cls).filter(
            cls.judge_id == judge_id,
            cls.event_type == 'COURT_ORDER_ACCESS'
        ).order_by(cls.created_at.desc()).limit(limit).all()


    @classmethod
    def verify_chain_integrity(cls, db, start_id: int = None, end_id: int = None) -> tuple:
        """
        Verify the integrity of the audit log chain

        Args:
            db: Database session
            start_id: Starting log ID (None = from beginning)
            end_id: Ending log ID (None = to end)

        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        import hashlib
        import json

        # Get logs in order
        query = db.query(cls).order_by(cls.id.asc())

        if start_id is not None:
            query = query.filter(cls.id >= start_id)
        if end_id is not None:
            query = query.filter(cls.id <= end_id)

        logs = query.all()

        if not logs:
            return (True, "No logs to verify")

        # Verify each log
        for i, log in enumerate(logs):
            # First log should have GENESIS or NULL as previous hash
            if i == 0:
                if log.previous_log_hash not in [None, "GENESIS"]:
                    return (False, f"First log (ID {log.id}) has invalid previous_log_hash: {log.previous_log_hash}")
            else:
                # Subsequent logs should link to previous
                previous_log = logs[i - 1]
                if log.previous_log_hash != previous_log.current_log_hash:
                    return (False, f"Chain break at log ID {log.id}: expected previous_hash={previous_log.current_log_hash}, got {log.previous_log_hash}")

            # Verify current hash is correct
            # Recalculate hash
            log_content = f"{log.previous_log_hash or 'GENESIS'}|{log.event_type}|{json.dumps(log.event_data, sort_keys=True)}|{log.created_at.isoformat()}"
            expected_hash = hashlib.sha256(log_content.encode()).hexdigest()

            if log.current_log_hash != expected_hash:
                return (False, f"Hash mismatch at log ID {log.id}: expected {expected_hash}, got {log.current_log_hash}")

        return (True, f"Chain verified: {len(logs)} logs intact")


# Export model
__all__ = ['AuditLog']
