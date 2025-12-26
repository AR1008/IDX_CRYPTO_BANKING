-- Migration 002: Rate Limiting & DDoS Protection
-- Purpose: Add IP blocking and rate limit violation tracking
-- Author: Ashutosh Rajesh
-- Date: 2025-12-26

-- Table: blocked_ips
-- Stores IP addresses that have been blocked (manual or automatic)

CREATE TABLE IF NOT EXISTS blocked_ips (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL UNIQUE,  -- IPv6 compatible (max 45 chars)
    reason VARCHAR(255),                      -- Why was this IP blocked
    blocked_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,                     -- NULL = permanent block
    blocked_by VARCHAR(100),                  -- "AUTO" or admin username

    -- Indexes
    CONSTRAINT unique_ip UNIQUE(ip_address)
);

CREATE INDEX idx_blocked_ip ON blocked_ips(ip_address);
CREATE INDEX idx_blocked_expiry ON blocked_ips(expires_at);

COMMENT ON TABLE blocked_ips IS 'IP addresses blocked from accessing the system (DDoS protection)';
COMMENT ON COLUMN blocked_ips.ip_address IS 'Blocked IP address (IPv4 or IPv6)';
COMMENT ON COLUMN blocked_ips.expires_at IS 'When block expires (NULL = permanent)';
COMMENT ON COLUMN blocked_ips.blocked_by IS '"AUTO" for automatic DDoS blocking, or admin username for manual blocks';


-- Table: rate_limit_violations
-- Logs all rate limit violations for analysis

CREATE TABLE IF NOT EXISTS rate_limit_violations (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,           -- Which endpoint was hit
    violated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    violation_count INTEGER NOT NULL DEFAULT 1,

    -- For analysis
    user_agent TEXT,
    request_path TEXT
);

CREATE INDEX idx_violation_ip ON rate_limit_violations(ip_address);
CREATE INDEX idx_violation_time ON rate_limit_violations(violated_at);
CREATE INDEX idx_violation_endpoint ON rate_limit_violations(endpoint);

COMMENT ON TABLE rate_limit_violations IS 'Log of all rate limit violations for security analysis';
COMMENT ON COLUMN rate_limit_violations.violation_count IS 'How many times rate limit was exceeded in this request';


-- Verification query
SELECT 'Migration 002 applied successfully - rate limiting tables created' AS status;
