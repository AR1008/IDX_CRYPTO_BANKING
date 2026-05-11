-- Migration 002: Rate Limiting & DDoS Protection
-- Purpose: Add IP blocking and rate limit violation tracking
-- Date: 2025-12-26

-- [DOC] TABLE: blocked_ips
-- [DOC] Tracks IP addresses that have been banned from accessing the API.
-- [DOC] Two types of blocks: automatic (triggered by DDoS detection) and manual (admin decision).
-- [DOC] A NULL expires_at means the block never automatically lifts — it must be removed by an admin.

CREATE TABLE IF NOT EXISTS blocked_ips (
    id SERIAL PRIMARY KEY,
    -- [DOC] VARCHAR(45) fits both IPv4 (max 15 chars: 255.255.255.255) and IPv6 (max 45 chars).
    ip_address VARCHAR(45) NOT NULL UNIQUE,  -- IPv6 compatible (max 45 chars)
    reason VARCHAR(255),                      -- Why was this IP blocked
    blocked_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- [DOC] expires_at = NULL means the block is permanent and must be manually removed.
    -- [DOC] A non-NULL value allows the middleware to auto-lift the block when the timestamp passes.
    expires_at TIMESTAMP,                     -- NULL = permanent block
    -- [DOC] blocked_by records who or what created the ban. "AUTO" = DDoS detection system;
    -- [DOC] any other value is an admin username who manually blocked this IP.
    blocked_by VARCHAR(100),                  -- "AUTO" or admin username

    -- Indexes
    CONSTRAINT unique_ip UNIQUE(ip_address)
);

-- [DOC] INDEX on ip_address: Every inbound request checks whether its source IP is blocked.
-- [DOC] Without this index, that check would be a full-table scan — too slow under load.
CREATE INDEX idx_blocked_ip ON blocked_ips(ip_address);

-- [DOC] INDEX on expires_at: A background cleanup job periodically removes expired blocks
-- [DOC] by querying WHERE expires_at < NOW(). This index makes that query fast.
CREATE INDEX idx_blocked_expiry ON blocked_ips(expires_at);

COMMENT ON TABLE blocked_ips IS 'IP addresses blocked from accessing the system (DDoS protection)';
COMMENT ON COLUMN blocked_ips.ip_address IS 'Blocked IP address (IPv4 or IPv6)';
COMMENT ON COLUMN blocked_ips.expires_at IS 'When block expires (NULL = permanent)';
COMMENT ON COLUMN blocked_ips.blocked_by IS '"AUTO" for automatic DDoS blocking, or admin username for manual blocks';


-- [DOC] TABLE: rate_limit_violations
-- [DOC] Every time a client exceeds its rate limit for an endpoint, a row is appended here.
-- [DOC] This is NOT used to enforce the rate limit in real-time (that is handled by Flask-Limiter
-- [DOC] in memory/Redis). This table is a post-hoc audit log so security analysts can:
-- [DOC]   1. Identify IPs that repeatedly violate limits (candidates for blocking).
-- [DOC]   2. Identify which endpoints are being abused most often.
-- [DOC]   3. Investigate suspicious patterns over historical time windows.

CREATE TABLE IF NOT EXISTS rate_limit_violations (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,           -- Which endpoint was hit
    violated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- [DOC] violation_count records how many times the limit was exceeded in this single request
    -- [DOC] burst. Usually 1, but could be higher if the client made many calls simultaneously.
    violation_count INTEGER NOT NULL DEFAULT 1,

    -- For analysis
    user_agent TEXT,
    request_path TEXT
);

-- [DOC] INDEX on ip_address: Enables fast lookup of all violations from a specific IP,
-- [DOC] e.g. "show me everything this IP has done" during a security investigation.
CREATE INDEX idx_violation_ip ON rate_limit_violations(ip_address);

-- [DOC] INDEX on violated_at: Enables fast time-range queries, e.g.
-- [DOC] "how many violations occurred in the last 5 minutes?" for real-time dashboards.
CREATE INDEX idx_violation_time ON rate_limit_violations(violated_at);

-- [DOC] INDEX on endpoint: Enables fast aggregation per endpoint, e.g.
-- [DOC] "which API route is being attacked the most?" for capacity planning and hardening.
CREATE INDEX idx_violation_endpoint ON rate_limit_violations(endpoint);

COMMENT ON TABLE rate_limit_violations IS 'Log of all rate limit violations for security analysis';
COMMENT ON COLUMN rate_limit_violations.violation_count IS 'How many times rate limit was exceeded in this request';


-- Verification query
SELECT 'Migration 002 applied successfully - rate limiting tables created' AS status;
