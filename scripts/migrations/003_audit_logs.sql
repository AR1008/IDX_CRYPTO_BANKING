-- Migration 003: Audit Trail Persistence
-- Purpose: Create tamper-proof audit log for court orders and sensitive operations
-- Author: Ashutosh Rajesh
-- Date: 2025-12-26

-- Table: audit_logs
-- Append-only, cryptographically chained audit log

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,

    -- Event details
    event_type VARCHAR(50) NOT NULL,          -- COURT_ORDER_ACCESS, KEY_GENERATION, etc.
    event_data JSONB NOT NULL,                -- Flexible JSON storage for event details

    -- Court order details (if applicable)
    judge_id VARCHAR(100),
    court_order_number VARCHAR(100),

    -- Cryptographic tamper-evident chain
    previous_log_hash VARCHAR(64),            -- Hash of previous log entry (blockchain-style)
    current_log_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hash of this entry
    signature VARCHAR(512),                   -- Optional: Digital signature from HSM

    -- Metadata
    ip_address VARCHAR(45),
    user_agent TEXT,

    -- Timestamps (immutable - append only)
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_audit_type ON audit_logs(event_type);
CREATE INDEX idx_audit_court_order ON audit_logs(court_order_number);
CREATE INDEX idx_audit_judge ON audit_logs(judge_id);
CREATE INDEX idx_audit_time ON audit_logs(created_at);
CREATE INDEX idx_audit_hash ON audit_logs(current_log_hash);

-- Make table append-only (prevent updates and deletes)
CREATE RULE audit_logs_no_update AS
    ON UPDATE TO audit_logs
    DO INSTEAD NOTHING;

CREATE RULE audit_logs_no_delete AS
    ON DELETE TO audit_logs
    DO INSTEAD NOTHING;

COMMENT ON TABLE audit_logs IS 'Tamper-proof audit log with cryptographic chaining';
COMMENT ON COLUMN audit_logs.previous_log_hash IS 'Hash of previous log entry (creates tamper-evident chain)';
COMMENT ON COLUMN audit_logs.current_log_hash IS 'SHA-256 hash of this entry (for chain integrity verification)';
COMMENT ON COLUMN audit_logs.signature IS 'Optional digital signature from Hardware Security Module';

-- Verification query
SELECT 'Migration 003 applied successfully - audit_logs table created (append-only)' AS status;
