-- Migration 005: Foreign Bank Consensus
-- Purpose: Enable foreign banks to validate travel account transactions
-- Date: 2025-12-26

-- Add transaction_type column to transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS transaction_type VARCHAR(20) DEFAULT 'DOMESTIC';

-- Update existing transactions to DOMESTIC
UPDATE transactions SET transaction_type = 'DOMESTIC' WHERE transaction_type IS NULL;

-- Add index for transaction_type
CREATE INDEX IF NOT EXISTS idx_transaction_type ON transactions(transaction_type);

COMMENT ON COLUMN transactions.transaction_type IS 'Transaction type: DOMESTIC, TRAVEL_DEPOSIT, TRAVEL_WITHDRAWAL, TRAVEL_TRANSFER';

-- Add validation tracking columns to foreign_banks table
ALTER TABLE foreign_banks
ADD COLUMN IF NOT EXISTS total_validations INTEGER DEFAULT 0;

ALTER TABLE foreign_banks
ADD COLUMN IF NOT EXISTS last_validation_at TIMESTAMP;

COMMENT ON COLUMN foreign_banks.total_validations IS 'Number of travel account transactions validated by this foreign bank';
COMMENT ON COLUMN foreign_banks.last_validation_at IS 'Timestamp of last validation performed';

-- Verification query
SELECT 'Migration 005 applied successfully - foreign bank consensus enabled' AS status;
