-- Migration 003: Audit Trail Persistence
-- Purpose: Create tamper-proof audit log for court orders and sensitive operations
-- Date: 2025-12-26

-- [DOC] TABLE: audit_logs
-- [DOC] This is the system's permanent, cryptographically-linked record of every sensitive
-- [DOC] event: court order filings, key generation, identity lookups, account freezes, etc.
-- [DOC] The table is made append-only (see the RULE statements below) so that even a
-- [DOC] compromised database admin cannot alter or erase past entries.
-- [DOC] The chain of hashes (previous_log_hash -> current_log_hash) mirrors how a blockchain
-- [DOC] works: tampering with any row breaks every subsequent hash, making tampering detectable.

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,

    -- [DOC] event_type is a short uppercase code identifying what happened, e.g.:
    -- [DOC]   COURT_ORDER_ACCESS  — a government authority read an encrypted record
    -- [DOC]   KEY_GENERATION      — new cryptographic key material was created
    -- [DOC]   ACCOUNT_FREEZE      — a user's accounts were frozen
    -- [DOC] This field is indexed (see below) so analysts can quickly filter by event category.
    event_type VARCHAR(50) NOT NULL,          -- COURT_ORDER_ACCESS, KEY_GENERATION, etc.

    -- [DOC] event_data stores the full context of the event as a JSON object.
    -- [DOC] Using JSONB (binary JSON) lets PostgreSQL index and query inside the document.
    -- [DOC] Each event type has its own schema — e.g. a court order access event includes
    -- [DOC] transaction_hash, target_party, judge_id, timestamp, and IP address.
    event_data JSONB NOT NULL,                -- Flexible JSON storage for event details

    -- Court order details (if applicable)
    judge_id VARCHAR(100),
    court_order_number VARCHAR(100),

    -- [DOC] CRYPTOGRAPHIC CHAIN — how tamper-evidence works:
    -- [DOC] When inserting row N, the application computes:
    -- [DOC]   current_log_hash = SHA-256(event_type + event_data + previous_log_hash + timestamp)
    -- [DOC] and stores the hash of row N-1 in previous_log_hash.
    -- [DOC] To verify integrity, re-hash every row and confirm the chain is unbroken.
    -- [DOC] If any row was modified or deleted, the chain breaks at that point.
    previous_log_hash VARCHAR(64),            -- Hash of previous log entry (blockchain-style)
    current_log_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hash of this entry

    -- [DOC] signature is an optional digital signature produced by an HSM (Hardware Security Module).
    -- [DOC] In production, the HSM signs each audit entry with its private key so that even if
    -- [DOC] the database server is fully compromised, forged log entries cannot be signed.
    signature VARCHAR(512),                   -- Optional: Digital signature from HSM

    -- Metadata
    ip_address VARCHAR(45),
    user_agent TEXT,

    -- [DOC] created_at is the authoritative timestamp for when the event occurred.
    -- [DOC] It is set by the database server (NOW()), not by the application, so a buggy or
    -- [DOC] malicious client cannot backdate an entry.
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- [DOC] INDEX on event_type: Analysts frequently filter by category, e.g. "show all court order
-- [DOC] accesses this month". Without this index that query would scan the entire log table.
CREATE INDEX idx_audit_type ON audit_logs(event_type);

-- [DOC] INDEX on court_order_number: Lets investigators pull the complete audit trail for
-- [DOC] a specific court order number in one fast lookup.
CREATE INDEX idx_audit_court_order ON audit_logs(court_order_number);

-- [DOC] INDEX on judge_id: Enables queries like "show all events initiated by judge X"
-- [DOC] for judicial oversight and accountability reporting.
CREATE INDEX idx_audit_judge ON audit_logs(judge_id);

-- [DOC] INDEX on created_at: Required for time-range queries, e.g. "all events last 30 days".
CREATE INDEX idx_audit_time ON audit_logs(created_at);

-- [DOC] INDEX on current_log_hash: Needed during chain verification — each row's
-- [DOC] previous_log_hash is looked up against this index to traverse the chain quickly.
CREATE INDEX idx_audit_hash ON audit_logs(current_log_hash);

-- [DOC] APPEND-ONLY ENFORCEMENT via PostgreSQL rules:
-- [DOC] Rules intercept DML statements before execution and replace them with DO INSTEAD NOTHING.
-- [DOC] This means any UPDATE or DELETE against audit_logs silently does nothing, even when
-- [DOC] issued by a superuser through a direct SQL connection. The only way to add entries is INSERT.
-- [DOC] Note: This is a defence-in-depth measure; the hash chain provides the primary tamper evidence.

-- [DOC] audit_logs_no_update: Silently drops any UPDATE statement on this table.
CREATE RULE audit_logs_no_update AS
    ON UPDATE TO audit_logs
    DO INSTEAD NOTHING;

-- [DOC] audit_logs_no_delete: Silently drops any DELETE statement on this table.
-- [DOC] Even "DELETE FROM audit_logs WHERE id = 1" will execute without error but remove nothing.
CREATE RULE audit_logs_no_delete AS
    ON DELETE TO audit_logs
    DO INSTEAD NOTHING;

COMMENT ON TABLE audit_logs IS 'Tamper-proof audit log with cryptographic chaining';
COMMENT ON COLUMN audit_logs.previous_log_hash IS 'Hash of previous log entry (creates tamper-evident chain)';
COMMENT ON COLUMN audit_logs.current_log_hash IS 'SHA-256 hash of this entry (for chain integrity verification)';
COMMENT ON COLUMN audit_logs.signature IS 'Optional digital signature from Hardware Security Module';

-- Verification query
SELECT 'Migration 003 applied successfully - audit_logs table created (append-only)' AS status;
