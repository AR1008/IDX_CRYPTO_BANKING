-- Migration 005: Foreign Bank Consensus
-- Purpose: Enable foreign banks to validate travel account transactions
-- Date: 2025-12-26

-- [DOC] COLUMN: transactions.transaction_type
-- [DOC] Distinguishes between purely domestic transactions (sender and receiver both use
-- [DOC] domestic IDX bank accounts) and travel-related transactions (used when a customer
-- [DOC] opens a temporary "travel account" in a foreign currency while abroad).
-- [DOC] The four allowed values are:
-- [DOC]   DOMESTIC          — standard transfer between two domestic accounts
-- [DOC]   TRAVEL_DEPOSIT    — customer loads money into their travel account before a trip
-- [DOC]   TRAVEL_WITHDRAWAL — customer withdraws from travel account while abroad
-- [DOC]   TRAVEL_TRANSFER   — transfer between travel accounts (e.g. splitting expenses)
-- [DOC] Domestic consensus (N=12 banks) handles DOMESTIC transactions.
-- [DOC] Foreign bank validators are added to the quorum for TRAVEL_* transactions.
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS transaction_type VARCHAR(20) DEFAULT 'DOMESTIC';

-- [DOC] Back-fill all existing rows: every transaction created before this migration is
-- [DOC] domestic by definition, so set them all to 'DOMESTIC'.
UPDATE transactions SET transaction_type = 'DOMESTIC' WHERE transaction_type IS NULL;

-- [DOC] INDEX on transaction_type: The batch processor and consensus engine frequently
-- [DOC] filter transactions by type to decide which validator set to use.
-- [DOC] This index makes those WHERE transaction_type = 'TRAVEL_*' queries fast.
CREATE INDEX IF NOT EXISTS idx_transaction_type ON transactions(transaction_type);

COMMENT ON COLUMN transactions.transaction_type IS 'Transaction type: DOMESTIC, TRAVEL_DEPOSIT, TRAVEL_WITHDRAWAL, TRAVEL_TRANSFER';

-- [DOC] COLUMNS: foreign_banks.total_validations and foreign_banks.last_validation_at
-- [DOC] Each foreign bank in the system acts as an optional validator for travel account
-- [DOC] transactions that originate in or pass through their jurisdiction.
-- [DOC] total_validations is an ever-growing counter: how many travel transactions has
-- [DOC] this foreign bank co-signed? This feeds into the annual reward / slashing calculation —
-- [DOC] banks that validate more earn a larger share of the consortium fee pool.
ALTER TABLE foreign_banks
ADD COLUMN IF NOT EXISTS total_validations INTEGER DEFAULT 0;

-- [DOC] last_validation_at records the timestamp of the most recent validation this bank
-- [DOC] performed. Used by the health-check daemon to detect unresponsive foreign validators
-- [DOC] (e.g. if last_validation_at is more than 24 hours ago, alert the operator).
ALTER TABLE foreign_banks
ADD COLUMN IF NOT EXISTS last_validation_at TIMESTAMP;

COMMENT ON COLUMN foreign_banks.total_validations IS 'Number of travel account transactions validated by this foreign bank';
COMMENT ON COLUMN foreign_banks.last_validation_at IS 'Timestamp of last validation performed';

-- Verification query
SELECT 'Migration 005 applied successfully - foreign bank consensus enabled' AS status;
