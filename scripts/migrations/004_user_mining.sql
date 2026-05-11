-- Migration 004: User Mining System
-- Purpose: Enable multiple users to mine competitively
-- Date: 2025-12-26

-- [DOC] TABLE: miner_statistics
-- [DOC] The IDX system uses Proof-of-Work (PoW) mining to finalize transaction batches onto
-- [DOC] the public blockchain. Any user can run a mining client and compete to find the next
-- [DOC] valid block hash. The winner earns 0.5% of every transaction fee in that batch.
-- [DOC] This table tracks each miner's cumulative performance, earnings, and activity state.
-- [DOC] One row per miner user (enforced by UNIQUE(user_idx)).

CREATE TABLE IF NOT EXISTS miner_statistics (
    id SERIAL PRIMARY KEY,

    -- [DOC] user_idx links to the users table (the miner's permanent pseudonym / identity key).
    -- [DOC] ON DELETE CASCADE means if a user account is removed, their mining stats are also deleted.
    user_idx VARCHAR(255) NOT NULL REFERENCES users(idx) ON DELETE CASCADE,

    -- [DOC] total_blocks_mined counts every block this miner successfully added to the chain,
    -- [DOC] whether they won or lost the race (see blocks_won vs blocks_lost below).
    total_blocks_mined INTEGER NOT NULL DEFAULT 0,

    -- [DOC] total_fees_earned is the running total of mining rewards credited to this miner.
    -- [DOC] Each mined batch earns 0.5% of all transaction amounts in that batch.
    -- [DOC] NUMERIC(15,2) stores up to 9,999,999,999,999.99 — sufficient for any realistic balance.
    total_fees_earned NUMERIC(15, 2) NOT NULL DEFAULT 0.00,

    -- [DOC] avg_mining_time_seconds and total_hash_attempts help benchmark miner hardware.
    -- [DOC] At difficulty=4, the expected number of SHA-256 attempts before finding a valid
    -- [DOC] nonce is approximately 16^4 = 65,536 (each hex digit needs a leading zero).
    avg_mining_time_seconds NUMERIC(10, 2),
    total_hash_attempts BIGINT NOT NULL DEFAULT 0,
    hash_rate_per_second NUMERIC(15, 2),

    -- [DOC] blocks_won: how many times this miner found the valid nonce FIRST (won the race).
    -- [DOC] blocks_lost: how many times this miner found a valid nonce but another miner
    -- [DOC] submitted theirs first — valid work, no reward. Tracks wasted computation.
    blocks_won INTEGER NOT NULL DEFAULT 0,  -- Won the mining race
    blocks_lost INTEGER NOT NULL DEFAULT 0, -- Found solution but too late

    -- [DOC] is_active = FALSE means this miner has paused or stopped their mining client.
    -- [DOC] The mining worker uses this flag to skip inactive miners when distributing rewards.
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_mined_at TIMESTAMP,

    started_mining_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- [DOC] updated_at is automatically refreshed by a trigger (see below) whenever any field
    -- [DOC] changes. This lets dashboards show "last seen active" without a separate query.
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(user_idx)
);

-- [DOC] INDEX on user_idx: The primary lookup — "get stats for miner X". Used after every block.
CREATE INDEX idx_miner_user ON miner_statistics(user_idx);

-- [DOC] INDEX on is_active: Mining worker queries WHERE is_active = TRUE every 10 seconds
-- [DOC] to find which miners are currently competing. Without this index that scan is O(n).
CREATE INDEX idx_miner_active ON miner_statistics(is_active);

-- [DOC] INDEX on blocks_won DESC: Powers the mining leaderboard — "top miners by blocks won".
-- [DOC] DESC ordering in the index means the leaderboard query doesn't need a sort step.
CREATE INDEX idx_miner_blocks_won ON miner_statistics(blocks_won DESC);

-- [DOC] INDEX on total_fees_earned DESC: Powers the earnings leaderboard — "top earners".
CREATE INDEX idx_miner_fees_earned ON miner_statistics(total_fees_earned DESC);

COMMENT ON TABLE miner_statistics IS 'Tracks mining performance and rewards for users who participate in competitive mining';
COMMENT ON COLUMN miner_statistics.total_blocks_mined IS 'Total number of blocks this miner has successfully mined';
COMMENT ON COLUMN miner_statistics.total_fees_earned IS 'Total mining fees earned (0.5% of transaction fees)';
COMMENT ON COLUMN miner_statistics.blocks_won IS 'Number of times this miner won the mining race';
COMMENT ON COLUMN miner_statistics.blocks_lost IS 'Number of times this miner found a solution but was too late (another miner won)';
COMMENT ON COLUMN miner_statistics.hash_rate_per_second IS 'Average hash rate (hashes per second) for this miner';
COMMENT ON COLUMN miner_statistics.is_active IS 'Whether this miner is currently actively mining';

-- [DOC] TRIGGER: auto-update updated_at on every row change.
-- [DOC] The function sets NEW.updated_at = NOW() before the UPDATE is written to disk.
-- [DOC] This pattern ("before update" trigger) is the standard PostgreSQL way to maintain
-- [DOC] an "updated at" timestamp without requiring the application to set it manually.
CREATE OR REPLACE FUNCTION update_miner_statistics_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- [DOC] Attach the function to the miner_statistics table so it fires before every UPDATE row.
CREATE TRIGGER trigger_update_miner_statistics_timestamp
    BEFORE UPDATE ON miner_statistics
    FOR EACH ROW
    EXECUTE FUNCTION update_miner_statistics_timestamp();

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON miner_statistics TO idx_banking_app;
-- GRANT USAGE, SELECT ON SEQUENCE miner_statistics_id_seq TO idx_banking_app;

-- Verification query
SELECT 'Migration 004 applied successfully - miner_statistics table created' AS status;
