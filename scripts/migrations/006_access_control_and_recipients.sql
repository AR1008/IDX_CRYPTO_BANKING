-- Migration 006: Access Control & Recipient Enhancements
-- Purpose: Add three-layer identity access control and recipient waiting period
-- Date: 2025-12-27

-- ============================================================
-- PART 1: Access Control Tables
-- ============================================================

-- 1.1 Create access_tokens table
-- Purpose: Time-limited access tokens for Government/CAs
CREATE TABLE IF NOT EXISTS access_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Token (UUID for API authentication)
    token VARCHAR(255) NOT NULL UNIQUE,

    -- Role
    role ENUM('company_admin', 'government', 'chartered_accountant', 'bank_admin') NOT NULL,

    -- Who was granted access
    granted_to VARCHAR(255) NOT NULL,
    granted_by VARCHAR(255) NOT NULL,

    -- Purpose and scope
    purpose TEXT NOT NULL,
    scope TEXT NULL COMMENT 'JSON scope restrictions (optional)',

    -- Time limits
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,

    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    revoked_at TIMESTAMP NULL,
    revoked_by VARCHAR(255) NULL,

    -- Last used
    last_used_at TIMESTAMP NULL,

    -- Indexes
    INDEX idx_access_tokens_token (token),
    INDEX idx_access_tokens_active (is_active, expires_at),
    INDEX idx_access_tokens_granted_to (granted_to),
    INDEX idx_access_tokens_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Time-limited access tokens for Gov/CA';


-- 1.2 Create access_audit_logs table
-- Purpose: Complete audit trail of all IDX registry access
CREATE TABLE IF NOT EXISTS access_audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Which access token was used
    access_token_id INT NULL COMMENT 'NULL for company admin access',

    -- Who accessed
    accessed_by VARCHAR(255) NOT NULL,

    -- What action
    action VARCHAR(100) NOT NULL,

    -- Target of access
    target_idx VARCHAR(255) NULL COMMENT 'Which user data was accessed',

    -- Additional details (JSON)
    details TEXT NULL,

    -- IP address and user agent
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,

    -- Timestamp
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    -- Indexes
    INDEX idx_access_audit_accessed_by (accessed_by),
    INDEX idx_access_audit_action (action),
    INDEX idx_access_audit_target (target_idx),
    INDEX idx_access_audit_time (accessed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Complete access audit trail';


-- ============================================================
-- PART 2: Recipient Enhancements
-- ============================================================

-- 2.1 Add 30-minute waiting period to recipients table
-- Purpose: Fraud prevention - prevent immediate transactions to newly added recipients
ALTER TABLE recipients
ADD COLUMN IF NOT EXISTS can_transact_at TIMESTAMP NULL DEFAULT NULL
COMMENT 'When user can first send money (30 min after adding recipient)';

-- 2.2 Set default for existing recipients (allow immediate transactions)
UPDATE recipients
SET can_transact_at = NOW()
WHERE can_transact_at IS NULL;

-- 2.3 Add trigger to set waiting period for new recipients
DELIMITER //

DROP TRIGGER IF EXISTS set_recipient_waiting_period//

CREATE TRIGGER set_recipient_waiting_period
BEFORE INSERT ON recipients
FOR EACH ROW
BEGIN
    -- Set 30-minute waiting period for new recipients
    IF NEW.can_transact_at IS NULL THEN
        SET NEW.can_transact_at = DATE_ADD(NOW(), INTERVAL 30 MINUTE);
    END IF;
END//

DELIMITER ;


-- ============================================================
-- PART 3: Indexes for Performance
-- ============================================================

-- 3.1 Add index for can_transact_at (for queries finding recipients ready to transact)
CREATE INDEX IF NOT EXISTS idx_recipients_can_transact
ON recipients (user_idx, can_transact_at);


-- ============================================================
-- PART 4: Sample Data (Optional - for testing)
-- ============================================================

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
