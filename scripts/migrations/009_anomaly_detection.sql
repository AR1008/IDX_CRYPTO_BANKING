-- Anomaly Detection Migration
-- Purpose: Add anomaly detection fields to transactions table
-- Date: 2026-01-03
--
-- This migration adds:
-- - Anomaly score (0-100)
-- - Anomaly flags (JSON array)
-- - Investigation status tracking
-- - ZKP anomaly proof field
-- - Threshold encrypted details (for court orders)
-- - Timestamps for flagging and clearing

BEGIN;

-- Add anomaly_score column (0-100, default 0.00)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS anomaly_score NUMERIC(5, 2) DEFAULT 0.00 NOT NULL;

-- Add anomaly_flags column (JSON array of flag names)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS anomaly_flags JSON;

-- Add requires_investigation flag (score >= 65)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS requires_investigation BOOLEAN DEFAULT FALSE NOT NULL;

-- Add zkp_anomaly_proof column (zero-knowledge proof of anomaly)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS zkp_anomaly_proof TEXT;

-- Add threshold_encrypted_details column (encrypted for court orders)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS threshold_encrypted_details BYTEA;

-- Add investigation_status column
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS investigation_status VARCHAR(20);

-- Add flagged_at timestamp
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS flagged_at TIMESTAMP WITH TIME ZONE;

-- Add cleared_at timestamp
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS cleared_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for fast anomaly queries
CREATE INDEX IF NOT EXISTS idx_tx_anomaly_score
ON transactions(anomaly_score);

CREATE INDEX IF NOT EXISTS idx_tx_requires_investigation
ON transactions(requires_investigation);

CREATE INDEX IF NOT EXISTS idx_tx_investigation_status
ON transactions(investigation_status);

CREATE INDEX IF NOT EXISTS idx_tx_flagged_at
ON transactions(flagged_at);

-- Add comments to columns
COMMENT ON COLUMN transactions.anomaly_score IS 'Anomaly detection score (0-100, higher = more suspicious)';
COMMENT ON COLUMN transactions.anomaly_flags IS 'JSON array of anomaly flags detected';
COMMENT ON COLUMN transactions.requires_investigation IS 'Flagged for investigation if score >= 65';
COMMENT ON COLUMN transactions.zkp_anomaly_proof IS 'Zero-knowledge proof of anomaly flag (flag hidden)';
COMMENT ON COLUMN transactions.threshold_encrypted_details IS 'Threshold-encrypted transaction details (3-party: Company+Court+RBI)';
COMMENT ON COLUMN transactions.investigation_status IS 'Investigation status: None, PENDING, UNDER_REVIEW, CLEARED, AUTO_CLEARED, CONFIRMED_SUSPICIOUS';
COMMENT ON COLUMN transactions.flagged_at IS 'Timestamp when transaction was flagged';
COMMENT ON COLUMN transactions.cleared_at IS 'Timestamp when investigation cleared the transaction';

COMMIT;

-- Verification queries
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'transactions'
AND column_name IN (
    'anomaly_score',
    'anomaly_flags',
    'requires_investigation',
    'zkp_anomaly_proof',
    'threshold_encrypted_details',
    'investigation_status',
    'flagged_at',
    'cleared_at'
)
ORDER BY column_name;

-- Check indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'transactions'
AND indexname LIKE 'idx_tx_%anomaly%' OR indexname LIKE 'idx_tx_%investigation%' OR indexname LIKE 'idx_tx_flagged%'
ORDER BY indexname;
