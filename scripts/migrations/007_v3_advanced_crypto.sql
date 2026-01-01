-- Migration 007: Advanced Cryptography V3.0
-- Purpose: Add sequence numbers, batching, and cryptographic fields
-- Date: 2025-12-27
-- Author: Ashutosh Rajesh

-- ============================================================
-- PART 1: Add V3.0 Fields to Transactions Table
-- ============================================================

-- 1.1 Add sequence number (CRITICAL - prevents replay attacks)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS sequence_number BIGINT UNIQUE;

-- Create sequence for auto-increment
CREATE SEQUENCE IF NOT EXISTS transaction_sequence_seq START 1;

-- Set sequence number for existing transactions
UPDATE transactions
SET sequence_number = nextval('transaction_sequence_seq')
WHERE sequence_number IS NULL;

-- Make it NOT NULL after setting values
ALTER TABLE transactions
ALTER COLUMN sequence_number SET NOT NULL;

-- 1.2 Add batch ID
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS batch_id VARCHAR(50);

-- 1.3 Add cryptographic fields for advanced privacy
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS commitment VARCHAR(66),
ADD COLUMN IF NOT EXISTS nullifier VARCHAR(66) UNIQUE,
ADD COLUMN IF NOT EXISTS range_proof TEXT,
ADD COLUMN IF NOT EXISTS group_signature TEXT,
ADD COLUMN IF NOT EXISTS commitment_salt VARCHAR(66);

-- 1.4 Add indexes for new fields
CREATE INDEX IF NOT EXISTS idx_tx_sequence ON transactions(sequence_number);
CREATE INDEX IF NOT EXISTS idx_tx_batch ON transactions(batch_id);
CREATE INDEX IF NOT EXISTS idx_tx_commitment ON transactions(commitment);
CREATE INDEX IF NOT EXISTS idx_tx_nullifier ON transactions(nullifier);

-- ============================================================
-- PART 2: Validation Queries
-- ============================================================

-- 2.1 Verify sequence numbers assigned
SELECT
    'Sequence Numbers' AS check_name,
    COUNT(*) AS total_transactions,
    MIN(sequence_number) AS min_sequence,
    MAX(sequence_number) AS max_sequence,
    COUNT(DISTINCT sequence_number) AS unique_sequences
FROM transactions;

-- 2.2 Show sample data
SELECT
    'Sample V3.0 Data' AS description,
    id,
    sequence_number,
    batch_id,
    commitment IS NOT NULL AS has_commitment,
    created_at
FROM transactions
ORDER BY sequence_number DESC
LIMIT 5;

-- ============================================================
-- Migration Complete!
-- ============================================================

SELECT '✅ Migration 007 completed successfully!' AS status;
SELECT 'V3.0 features enabled: Sequence numbers, Batching, Advanced Cryptography' AS features;
