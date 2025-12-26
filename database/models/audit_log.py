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
from sqlalchemy.dialects.postgresql import JSONB
from database.connection import Base
from datetime import datetime
from typing import Optional, Dict, Any


class AuditLog(Base):
    """
    Audit Log Model - Tamper-proof event logging

    Table: audit_logs

    Rules:
    - Append-only (database rules prevent UPDATE/DELETE)
    - Each log links to previous via cryptographic hash
    - Supports any event type with flexible JSONB data
    """
    __tablename__ = "audit_logs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Event information
    event_type = Column(String(50), nullable=False, index=True)
    # Event types: COURT_ORDER_ACCESS, KEY_GENERATION, USER_REGISTRATION,
    #              TRANSACTION_CREATED, BLOCK_MINED, etc.

    event_data = Column(JSONB, nullable=False)
    # Flexible JSON storage for event-specific data
    # Example for COURT_ORDER_ACCESS:
    # {
    #   "session_id": "SESSION_...",
    #   "revealed_idx": "IDX_...",
    #   "court_order_number": "CO_2025_001",
    #   "judge_id": "JUDGE_12345",
    #   "reason": "Tax investigation"
    # }

    # Court order specific fields (for COURT_ORDER_ACCESS events)
    judge_id = Column(String(100), nullable=True, index=True)
    court_order_number = Column(String(100), nullable=True, index=True)

    # Cryptographic chain (tamper-evident)
    previous_log_hash = Column(String(64), nullable=True)
    # SHA-256 hash of previous log entry (NULL for first entry = "GENESIS")

    current_log_hash = Column(String(64), nullable=False, unique=True, index=True)
    # SHA-256 hash of this log entry
    # Calculated: SHA256(previous_hash | event_type | event_data | timestamp)

    # Metadata
    ip_address = Column(String(45), nullable=True)
    # IPv4 or IPv6 address of requester

    user_agent = Column(Text, nullable=True)
    # Browser/client user agent

    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    # Timestamp (immutable, enforced by database)


    # Indexes for efficient queries
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
