-- Security Features Migration
-- Purpose: Add security and governance features to existing database
--
-- Changes:
-- 1. Add new columns to consortium_banks table
-- 2. Create treasury table
-- 3. Create bank_voting_records table
--
-- SAFE: All operations are additive - no data loss

-- [DOC] ============================================================
-- [DOC] SECTION 1: Additional columns on consortium_banks
-- [DOC] These columns track each bank's financial stake in the system
-- [DOC] and their validation behaviour. Banks that act dishonestly lose
-- [DOC] stake (slashing); banks that act correctly earn rewards.
-- [DOC] ============================================================

-- ============================================
-- 1. Add new columns to consortium_banks table
-- ============================================

-- [DOC] total_assets is the bank's declared balance sheet size.
-- [DOC] The consortium rules require each bank to stake at least 1% of
-- [DOC] its total assets, so this figure anchors the minimum-stake check.
-- [DOC] Default of 10,000,000,000 (10 billion) suits a mid-size bank.
-- Add total_assets column (for 1% minimum stake calculation)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS total_assets NUMERIC(18, 2)
NOT NULL DEFAULT 10000000000.00;

COMMENT ON COLUMN consortium_banks.total_assets IS 'Total assets/market cap of bank (for 1% minimum stake calculation)';

-- [DOC] initial_stake records how much the bank deposited when it first
-- [DOC] joined the consortium. If its current stake falls below 30% of
-- [DOC] this initial amount due to slashing penalties, the bank is
-- [DOC] automatically deactivated and removed from voting quorums.
-- Add initial_stake column (for deactivation threshold)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS initial_stake NUMERIC(15, 2)
NOT NULL DEFAULT 100000000.00;

COMMENT ON COLUMN consortium_banks.initial_stake IS 'Initial stake amount (deactivation if falls below 30% of this)';

-- [DOC] honest_verifications counts how many times this bank voted
-- [DOC] correctly on a transaction batch (i.e., its vote matched the
-- [DOC] true validity of the batch as later confirmed by the regulator).
-- [DOC] Used at fiscal-year-end to calculate each bank's proportional
-- [DOC] share of treasury rewards.
-- Add honest_verifications column (for reward calculation)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS honest_verifications INTEGER
NOT NULL DEFAULT 0;

COMMENT ON COLUMN consortium_banks.honest_verifications IS 'Count of correct verifications (for reward calculation)';

-- [DOC] malicious_verifications counts how many times this bank voted
-- [DOC] APPROVE on a batch that was later found to contain an invalid
-- [DOC] transaction. Each malicious vote triggers a slashing event:
-- [DOC] 1st offence = 10% stake, 2nd = 20%, 3rd = deactivation.
-- Add malicious_verifications column (for tracking malicious behavior)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS malicious_verifications INTEGER
NOT NULL DEFAULT 0;

COMMENT ON COLUMN consortium_banks.malicious_verifications IS 'Count of incorrect verifications (voted ACCEPT on invalid tx)';

-- [DOC] last_fiscal_year_reward records the most recent annual payout
-- [DOC] to this bank from the treasury. Kept for auditing and reporting
-- [DOC] rather than for any active business logic.
-- Add last_fiscal_year_reward column (for tracking rewards)
ALTER TABLE consortium_banks
ADD COLUMN IF NOT EXISTS last_fiscal_year_reward NUMERIC(15, 2)
NOT NULL DEFAULT 0.00;

COMMENT ON COLUMN consortium_banks.last_fiscal_year_reward IS 'Reward received in last fiscal year distribution';

-- [DOC] ============================================================
-- [DOC] SECTION 2: treasury table
-- [DOC] The treasury acts as a central pool that receives slashed funds
-- [DOC] from dishonest banks and pays them out as rewards to honest banks
-- [DOC] at the end of each fiscal year. Every entry is one of two types:
-- [DOC]   SLASH  — funds received from a penalised bank
-- [DOC]   REWARD — funds paid out to an honest bank
-- [DOC] Keeping both directions in one table gives a complete double-
-- [DOC] entry view of the treasury's life-cycle.
-- [DOC] ============================================================

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

-- [DOC] Indexes below speed up the most common treasury queries:
-- [DOC]   - "Show all SLASHes this year" (entry_type + fiscal_year)
-- [DOC]   - "Show all entries for bank X" (bank_code)
-- [DOC]   - "Show recent activity" (created_at)
-- Create indexes
CREATE INDEX IF NOT EXISTS idx_treasury_type ON treasury(entry_type);
CREATE INDEX IF NOT EXISTS idx_treasury_fiscal_year ON treasury(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_treasury_bank ON treasury(bank_code);
CREATE INDEX IF NOT EXISTS idx_treasury_created ON treasury(created_at);

-- [DOC] ============================================================
-- [DOC] SECTION 3: bank_voting_records table
-- [DOC] Every vote cast by every bank on every batch is stored here.
-- [DOC] The regulatory authority (FFA/FIU) spot-checks 10% of batches
-- [DOC] by re-running independent validation. The result of that check
-- [DOC] is written back into is_correct / rbi_verified. If a bank voted
-- [DOC] incorrectly, was_slashed and slash_amount record the penalty.
-- [DOC]
-- [DOC] The group_signature column stores the BBS04 group signature that
-- [DOC] each bank attached to its vote. The signature proves a valid
-- [DOC] consortium member voted (unlinkable to which bank) until the
-- [DOC] regulator opens it during a dispute — at which point the bank
-- [DOC] is identified and can be slashed.
-- [DOC] ============================================================

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

-- [DOC] The composite index (batch_id, bank_code) is the most important:
-- [DOC] "Did bank X already vote on batch Y?" is checked before every
-- [DOC] vote to prevent a bank from casting two votes on the same batch.
-- Create indexes
CREATE INDEX IF NOT EXISTS idx_vote_batch ON bank_voting_records(batch_id);
CREATE INDEX IF NOT EXISTS idx_vote_bank ON bank_voting_records(bank_code);
CREATE INDEX IF NOT EXISTS idx_vote_correct ON bank_voting_records(is_correct);
CREATE INDEX IF NOT EXISTS idx_vote_slashed ON bank_voting_records(was_slashed);
CREATE INDEX IF NOT EXISTS idx_vote_rbi_verified ON bank_voting_records(rbi_verified);
CREATE INDEX IF NOT EXISTS idx_vote_batch_bank ON bank_voting_records(batch_id, bank_code);

-- [DOC] ============================================================
-- [DOC] SECTION 4: Back-fill existing bank rows
-- [DOC] Banks that were created before this migration have their stake
-- [DOC] recorded in stake_amount. We infer total_assets by assuming
-- [DOC] stake = 1% of assets, so total_assets = stake * 100.
-- [DOC] initial_stake is set equal to the current stake because no
-- [DOC] slashing has occurred yet.
-- [DOC] The WHERE clause limits the update to rows still sitting at
-- [DOC] the default placeholder value (10,000,000,000) so that running
-- [DOC] this migration twice does not overwrite already-correct data.
-- [DOC] ============================================================

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

-- [DOC] Sanity-check queries: the migration runner prints these counts
-- [DOC] so the operator can confirm all three objects now exist and
-- [DOC] that banks were updated correctly.
-- Verify migration
SELECT 'Migration successful! Tables and columns added.' AS status;
SELECT COUNT(*) AS bank_count FROM consortium_banks;
SELECT COUNT(*) AS treasury_count FROM treasury;
SELECT COUNT(*) AS voting_records_count FROM bank_voting_records;
