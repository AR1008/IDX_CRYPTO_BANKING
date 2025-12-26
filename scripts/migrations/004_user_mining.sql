-- Migration 004: User Mining System
-- Purpose: Enable multiple users to mine competitively
-- Author: Ashutosh Rajesh
-- Date: 2025-12-26

-- Table: miner_statistics
-- Tracks mining performance and rewards for each user who mines

CREATE TABLE IF NOT EXISTS miner_statistics (
    id SERIAL PRIMARY KEY,
    user_idx VARCHAR(255) NOT NULL REFERENCES users(idx) ON DELETE CASCADE,

    -- Mining statistics
    total_blocks_mined INTEGER NOT NULL DEFAULT 0,
    total_fees_earned NUMERIC(15, 2) NOT NULL DEFAULT 0.00,

    -- Performance metrics
    avg_mining_time_seconds NUMERIC(10, 2),
    total_hash_attempts BIGINT NOT NULL DEFAULT 0,
    hash_rate_per_second NUMERIC(15, 2),

    -- Competition statistics
    blocks_won INTEGER NOT NULL DEFAULT 0,  -- Won the mining race
    blocks_lost INTEGER NOT NULL DEFAULT 0, -- Found solution but too late

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_mined_at TIMESTAMP,

    -- Timestamps
    started_mining_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    UNIQUE(user_idx)
);

-- Indexes for performance
CREATE INDEX idx_miner_user ON miner_statistics(user_idx);
CREATE INDEX idx_miner_active ON miner_statistics(is_active);
CREATE INDEX idx_miner_blocks_won ON miner_statistics(blocks_won DESC);
CREATE INDEX idx_miner_fees_earned ON miner_statistics(total_fees_earned DESC);

-- Comments for documentation
COMMENT ON TABLE miner_statistics IS 'Tracks mining performance and rewards for users who participate in competitive mining';
COMMENT ON COLUMN miner_statistics.total_blocks_mined IS 'Total number of blocks this miner has successfully mined';
COMMENT ON COLUMN miner_statistics.total_fees_earned IS 'Total mining fees earned (0.5% of transaction fees)';
COMMENT ON COLUMN miner_statistics.blocks_won IS 'Number of times this miner won the mining race';
COMMENT ON COLUMN miner_statistics.blocks_lost IS 'Number of times this miner found a solution but was too late (another miner won)';
COMMENT ON COLUMN miner_statistics.hash_rate_per_second IS 'Average hash rate (hashes per second) for this miner';
COMMENT ON COLUMN miner_statistics.is_active IS 'Whether this miner is currently actively mining';

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_miner_statistics_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER trigger_update_miner_statistics_timestamp
    BEFORE UPDATE ON miner_statistics
    FOR EACH ROW
    EXECUTE FUNCTION update_miner_statistics_timestamp();

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON miner_statistics TO idx_banking_app;
-- GRANT USAGE, SELECT ON SEQUENCE miner_statistics_id_seq TO idx_banking_app;

-- Verification query
SELECT 'Migration 004 applied successfully - miner_statistics table created' AS status;
