-- Migration 006: Access Control & Recipient Enhancements
-- Purpose: Add three-layer identity access control and recipient waiting period
-- Date: 2025-12-27

-- ============================================================
-- PART 1: Access Control Tables
-- ============================================================

-- [DOC] TABLE: access_tokens
-- [DOC] The IDX system grants time-limited API access to two external parties:
-- [DOC]   government agencies (FFA, FIU, FLEA, NTA) — to execute court orders and view frozen accounts
-- [DOC]   chartered accountants (CAs)               — to view their specific client's transaction history
-- [DOC] Rather than issuing permanent credentials, access is scoped to a token with an expiry date.
-- [DOC] When the token expires or is revoked, access is automatically cut off — no key rotation needed.
-- [DOC] Note: This table uses MySQL/MariaDB syntax (ENGINE=InnoDB, AUTO_INCREMENT, ENUM).
-- [DOC] If running on PostgreSQL, use migration 006_pg_access_control.sql instead.

-- 1.1 Create access_tokens table
-- Purpose: Time-limited access tokens for Government/CAs
CREATE TABLE IF NOT EXISTS access_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- [DOC] token is a UUID-style random string used as a Bearer token in the Authorization header.
    -- [DOC] UNIQUE ensures that even if two tokens are issued to the same grantee, each is distinct.
    token VARCHAR(255) NOT NULL UNIQUE,

    -- [DOC] role determines what this token is permitted to do:
    -- [DOC]   company_admin       — IDX Corp internal admin (full access)
    -- [DOC]   government          — court order execution, frozen account statement view
    -- [DOC]   chartered_accountant — read-only view of one specific client's transaction history
    -- [DOC]   bank_admin          — consortium bank operator access
    role ENUM('company_admin', 'government', 'chartered_accountant', 'bank_admin') NOT NULL,

    -- [DOC] granted_to identifies the organisation or individual who holds this token,
    -- [DOC] e.g. "Financial Intelligence Unit" or "ABC Tax Consultants Pvt Ltd".
    granted_to VARCHAR(255) NOT NULL,
    -- [DOC] granted_by records who issued the token — typically a company_admin username or "SYSTEM".
    granted_by VARCHAR(255) NOT NULL,

    -- [DOC] purpose is a human-readable description of why this token was issued,
    -- [DOC] e.g. "Court order #CO-2026-0042 investigation access". Mandatory for auditability.
    purpose TEXT NOT NULL,
    -- [DOC] scope is an optional JSON object that further restricts what this token can access,
    -- [DOC] e.g. {"user_idx": "IDX_abc123"} limits a CA token to one specific client.
    scope TEXT NULL COMMENT 'JSON scope restrictions (optional)',

    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    -- [DOC] expires_at is mandatory — all external access must have a hard end date.
    -- [DOC] The API middleware rejects any token where expires_at < NOW() even if is_active = TRUE.
    expires_at TIMESTAMP NOT NULL,

    -- [DOC] is_active can be set to FALSE to instantly revoke a token before its expiry,
    -- [DOC] e.g. if a government official leaves their role or an investigation is closed early.
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    revoked_at TIMESTAMP NULL,
    revoked_by VARCHAR(255) NULL,

    last_used_at TIMESTAMP NULL,

    INDEX idx_access_tokens_token (token),
    -- [DOC] Composite index on (is_active, expires_at): the middleware checks both in one query —
    -- [DOC] "WHERE token = ? AND is_active = TRUE AND expires_at > NOW()".
    INDEX idx_access_tokens_active (is_active, expires_at),
    INDEX idx_access_tokens_granted_to (granted_to),
    INDEX idx_access_tokens_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Time-limited access tokens for Gov/CA';


-- [DOC] TABLE: access_audit_logs
-- [DOC] Every time an access_token is used to read from the IDX registry (identity lookup,
-- [DOC] statement view, court order execution, etc.) a row is appended here.
-- [DOC] This provides a complete, query-able trail of who accessed whose data and when.
-- [DOC] Regulators can use this table to verify that government access was lawful and scoped.

-- 1.2 Create access_audit_logs table
-- Purpose: Complete audit trail of all IDX registry access
CREATE TABLE IF NOT EXISTS access_audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- [DOC] access_token_id links to the access_tokens row that was used.
    -- [DOC] NULL is allowed for company_admin actions which use a different auth path.
    access_token_id INT NULL COMMENT 'NULL for company admin access',

    accessed_by VARCHAR(255) NOT NULL,

    -- [DOC] action is a short code for what was done, e.g.:
    -- [DOC]   IDX_LOOKUP       — identity resolved from IDX to real name
    -- [DOC]   STATEMENT_VIEW   — transaction history pulled for a user
    -- [DOC]   COURT_ORDER_EXEC — decryption keys assembled and used
    action VARCHAR(100) NOT NULL,

    -- [DOC] target_idx is the IDX of the user whose data was accessed.
    -- [DOC] NULL if the action was not user-specific (e.g. system-level queries).
    target_idx VARCHAR(255) NULL COMMENT 'Which user data was accessed',

    details TEXT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    INDEX idx_access_audit_accessed_by (accessed_by),
    INDEX idx_access_audit_action (action),
    -- [DOC] INDEX on target_idx: Enables "show me all accesses to user X's data" —
    -- [DOC] essential for user-facing transparency reports and judicial review.
    INDEX idx_access_audit_target (target_idx),
    INDEX idx_access_audit_time (accessed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Complete access audit trail';


-- ============================================================
-- PART 2: Recipient Enhancements
-- ============================================================

-- [DOC] COLUMN: recipients.can_transact_at
-- [DOC] Anti-fraud waiting period: when a user adds a new recipient (by IDX), they cannot
-- [DOC] immediately send money to that recipient. They must wait 30 minutes first.
-- [DOC] Rationale: many social-engineering scams work by urgently pressuring a victim to
-- [DOC] add a new payee and send money immediately. A 30-minute delay breaks this pattern
-- [DOC] and gives the user time to reconsider or notice the deception.
-- [DOC] can_transact_at stores the earliest datetime a transfer to this recipient is allowed.

-- 2.1 Add 30-minute waiting period to recipients table
ALTER TABLE recipients
ADD COLUMN IF NOT EXISTS can_transact_at TIMESTAMP NULL DEFAULT NULL
COMMENT 'When user can first send money (30 min after adding recipient)';

-- [DOC] Existing recipients were added before this rule existed, so they are grandfathered in:
-- [DOC] set their can_transact_at = NOW() so they are immediately transactable.
-- 2.2 Set default for existing recipients (allow immediate transactions)
UPDATE recipients
SET can_transact_at = NOW()
WHERE can_transact_at IS NULL;

-- [DOC] TRIGGER: set_recipient_waiting_period
-- [DOC] For every new recipient row inserted, if the application did not explicitly set
-- [DOC] can_transact_at, this trigger sets it to NOW() + 30 minutes automatically.
-- [DOC] This ensures the waiting period is enforced at the database level — even if the
-- [DOC] application layer has a bug and forgets to set the field.

-- 2.3 Add trigger to set waiting period for new recipients
DELIMITER //

DROP TRIGGER IF EXISTS set_recipient_waiting_period//

CREATE TRIGGER set_recipient_waiting_period
BEFORE INSERT ON recipients
FOR EACH ROW
BEGIN
    IF NEW.can_transact_at IS NULL THEN
        SET NEW.can_transact_at = DATE_ADD(NOW(), INTERVAL 30 MINUTE);
    END IF;
END//

DELIMITER ;


-- ============================================================
-- PART 3: Indexes for Performance
-- ============================================================

-- [DOC] Composite INDEX on (user_idx, can_transact_at):
-- [DOC] The transaction initiation flow queries "get recipients for user X where can_transact_at <= NOW()".
-- [DOC] This composite index satisfies both the equality filter (user_idx) and the range filter
-- [DOC] (can_transact_at) in one index scan — no table access needed.
CREATE INDEX IF NOT EXISTS idx_recipients_can_transact
ON recipients (user_idx, can_transact_at);


-- ============================================================
-- PART 4: Sample Data (Optional - for testing)
-- ============================================================

-- [DOC] This inserts a sample chartered_accountant token for testing the access control endpoints.
-- [DOC] ON DUPLICATE KEY UPDATE token=token means re-running this migration is safe — if the
-- [DOC] token already exists, the INSERT does nothing rather than failing.
-- [DOC] IMPORTANT: Revoke or delete this token before going to production. It is only for dev.

-- 4.1 Create sample company admin access token
-- NOTE: In production, use /api/admin/access/grant endpoint instead
-- This is ONLY for initial testing
INSERT INTO access_tokens (
    token,
    role,
    granted_to,
    granted_by,
    purpose,
    expires_at
) VALUES (
    'SAMPLE_CA_TOKEN_12345_DO_NOT_USE_IN_PRODUCTION',
    'chartered_accountant',
    'ABC Tax Consultants Pvt Ltd',
    'SYSTEM_MIGRATION',
    'Initial testing token - REVOKE BEFORE PRODUCTION',
    DATE_ADD(NOW(), INTERVAL 7 DAY)
) ON DUPLICATE KEY UPDATE token=token;


-- ============================================================
-- PART 5: Validation Queries
-- ============================================================

-- 5.1 Verify access_tokens table
SELECT
    'access_tokens created' AS status,
    COUNT(*) AS token_count
FROM access_tokens;

-- 5.2 Verify access_audit_logs table
SELECT
    'access_audit_logs created' AS status,
    COUNT(*) AS log_count
FROM access_audit_logs;

-- 5.3 Verify recipients waiting period
SELECT
    'recipients updated' AS status,
    COUNT(*) AS total_recipients,
    SUM(CASE WHEN can_transact_at IS NOT NULL THEN 1 ELSE 0 END) AS with_waiting_period
FROM recipients;

-- 5.4 Show sample token (for testing)
SELECT
    'Sample CA Token' AS description,
    token,
    granted_to,
    expires_at,
    is_active
FROM access_tokens
WHERE granted_by = 'SYSTEM_MIGRATION'
LIMIT 1;


-- ============================================================
-- PART 6: Rollback Instructions (for emergencies)
-- ============================================================

-- To rollback this migration (NOT recommended):
-- DROP TABLE access_tokens;
-- DROP TABLE access_audit_logs;
-- DROP TRIGGER IF EXISTS set_recipient_waiting_period;
-- ALTER TABLE recipients DROP COLUMN can_transact_at;


-- ============================================================
-- Migration Complete!
-- ============================================================

SELECT '✅ Migration 006 completed successfully!' AS status;
