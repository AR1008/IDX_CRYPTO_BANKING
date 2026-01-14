-- Security Features Migration
-- Purpose: Add security and governance features to existing database
--
-- Changes:
-- 1. Add new columns to consortium_banks table
-- 2. Create treasury table
-- 3. Create bank_voting_records table
--
-- SAFE: All operations are additive - no data loss

-- ============================================
-- 1. Add new columns to consortium_banks table
-- ============================================

-- Add total_assets column (for 1% minimum stake calculation)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS total_assets NUMERIC(18, 2)
NOT NULL DEFAULT 10000000000.00;

COMMENT ON COLUMN consortium_banks.total_assets IS 'Total assets/market cap of bank (for 1% minimum stake calculation)';

-- Add initial_stake column (for deactivation threshold)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS initial_stake NUMERIC(15, 2)
NOT NULL DEFAULT 100000000.00;

COMMENT ON COLUMN consortium_banks.initial_stake IS 'Initial stake amount (deactivation if falls below 30% of this)';

-- Add honest_verifications column (for reward calculation)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS honest_verifications INTEGER
NOT NULL DEFAULT 0;

COMMENT ON COLUMN consortium_banks.honest_verifications IS 'Count of correct verifications (for reward calculation)';

-- Add malicious_verifications column (for tracking malicious behavior)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS malicious_verifications INTEGER
NOT NULL DEFAULT 0;

COMMENT ON COLUMN consortium_banks.malicious_verifications IS 'Count of incorrect verifications (voted ACCEPT on invalid tx)';

-- Add last_fiscal_year_reward column (for tracking rewards)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS last_fiscal_year_reward NUMERIC(15, 2)
NOT NULL DEFAULT 0.00;

COMMENT ON COLUMN consortium_banks.last_fiscal_year_reward IS 'Reward received in last fiscal year distribution';

-- ============================================
-- 2. Create treasury table
-- ============================================

CREATE TABLE IF NOT EXISTS treasury (
    id SERIAL PRIMARY KEY,
    entry_type VARCHAR(20) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    bank_code VARCHAR(20),
    fiscal_year VARCHAR(20) NOT NULL,
    reason TEXT,
    offense_count INTEGER,
    honest_verification_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    processed_by VARCHAR(100)
);

-- Add comments
COMMENT ON TABLE treasury IS 'Treasury for slashed funds and reward distribution';
COMMENT ON COLUMN treasury.entry_type IS 'SLASH (funds received) or REWARD (funds distributed)';
COMMENT ON COLUMN treasury.amount IS 'Amount slashed or rewarded';
COMMENT ON COLUMN treasury.bank_code IS 'Bank code (for SLASH: source bank, for REWARD: receiving bank)';
COMMENT ON COLUMN treasury.fiscal_year IS 'Fiscal year (e.g., 2025-2026)';
COMMENT ON COLUMN treasury.reason IS 'Reason for slash or reward details';
COMMENT ON COLUMN treasury.offense_count IS 'For SLASH: which offense (1st, 2nd, 3rd for escalating penalties)';
COMMENT ON COLUMN treasury.honest_verification_count IS 'For REWARD: number of honest verifications (for proportional distribution)';
COMMENT ON COLUMN treasury.created_at IS 'When entry was created';
COMMENT ON COLUMN treasury.processed_by IS 'System component that processed this entry';

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_treasury_type ON treasury(entry_type);
CREATE INDEX IF NOT EXISTS idx_treasury_fiscal_year ON treasury(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_treasury_bank ON treasury(bank_code);
CREATE INDEX IF NOT EXISTS idx_treasury_created ON treasury(created_at);

-- ============================================
-- 3. Create bank_voting_records table
-- ============================================

CREATE TABLE IF NOT EXISTS bank_voting_records (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(50) NOT NULL,
    bank_code VARCHAR(20) NOT NULL,
    vote VARCHAR(10) NOT NULL,
    validation_time_ms INTEGER,
    is_correct BOOLEAN,
    rbi_verified BOOLEAN NOT NULL DEFAULT FALSE,
    rbi_verification_time TIMESTAMP WITH TIME ZONE,
    was_slashed BOOLEAN NOT NULL DEFAULT FALSE,
    slash_amount BIGINT,
    group_signature TEXT,
    challenged_by VARCHAR(20),
    challenge_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Add comments
COMMENT ON TABLE bank_voting_records IS 'Records every bank vote on every batch for slashing detection';
COMMENT ON COLUMN bank_voting_records.batch_id IS 'Batch ID that was voted on';
COMMENT ON COLUMN bank_voting_records.bank_code IS 'Bank code (HDFC, ICICI, SBI, etc.)';
COMMENT ON COLUMN bank_voting_records.vote IS 'APPROVE or REJECT';
COMMENT ON COLUMN bank_voting_records.validation_time_ms IS 'Time taken to validate in milliseconds';
COMMENT ON COLUMN bank_voting_records.is_correct IS 'True if vote was correct (filled by RBI re-verification)';
COMMENT ON COLUMN bank_voting_records.rbi_verified IS 'Whether RBI has verified this vote';
COMMENT ON COLUMN bank_voting_records.rbi_verification_time IS 'When RBI verified this vote';
COMMENT ON COLUMN bank_voting_records.was_slashed IS 'Whether bank was slashed for this vote';
COMMENT ON COLUMN bank_voting_records.slash_amount IS 'Amount slashed if vote was incorrect';
COMMENT ON COLUMN bank_voting_records.group_signature IS 'Group signature (ring signature) for anonymous voting';
COMMENT ON COLUMN bank_voting_records.challenged_by IS 'Bank code that challenged this vote (if any)';
COMMENT ON COLUMN bank_voting_records.challenge_time IS 'When vote was challenged';
COMMENT ON COLUMN bank_voting_records.created_at IS 'When vote was cast';

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_vote_batch ON bank_voting_records(batch_id);
CREATE INDEX IF NOT EXISTS idx_vote_bank ON bank_voting_records(bank_code);
CREATE INDEX IF NOT EXISTS idx_vote_correct ON bank_voting_records(is_correct);
CREATE INDEX IF NOT EXISTS idx_vote_slashed ON bank_voting_records(was_slashed);
CREATE INDEX IF NOT EXISTS idx_vote_rbi_verified ON bank_voting_records(rbi_verified);
CREATE INDEX IF NOT EXISTS idx_vote_batch_bank ON bank_voting_records(batch_id, bank_code);

-- ============================================
-- 4. Update existing banks with realistic values
-- ============================================

-- Update existing banks with total_assets and initial_stake based on their current stake
-- This assumes existing banks have stake_amount set

UPDATE consortium_banks SET
    total_assets = stake_amount * 100,  -- Assume stake is 1% of total assets
    initial_stake = stake_amount
WHERE total_assets = 10000000000.00;  -- Only update if still at default

-- ============================================
-- Migration complete
-- ============================================

-- Verify migration
SELECT 'Migration successful! Tables and columns added.' AS status;
SELECT COUNT(*) AS bank_count FROM consortium_banks;
SELECT COUNT(*) AS treasury_count FROM treasury;
SELECT COUNT(*) AS voting_records_count FROM bank_voting_records;
