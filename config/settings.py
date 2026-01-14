"""
IDX Crypto Banking - Configuration Settings
Purpose: Central configuration for entire application

This file stores ALL settings in one place:
- Database connection
- Security keys
- Blockchain parameters
- Fee rates
- Session settings
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
# This lets us keep secrets OUT of our code (secure!)
load_dotenv()


class Settings:
    """
    Main application settings class
    
    All other files import this to get configuration values
    Example: from config.settings import settings
    """
    
    # ==========================================
    # DATABASE CONFIGURATION
    # ==========================================
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://ashutoshrajesh@localhost/idx_banking"
    )
    # Format: postgresql://USERNAME@HOST/DATABASE_NAME
    # Change USERNAME to your Mac username if different
    
    
    # ==========================================
    # SECURITY CONFIGURATION
    # ==========================================
    
    # Secret key for application (used for general encryption)
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", 
        "dev-secret-key-CHANGE-IN-PRODUCTION"
    )
    
    # JWT (JSON Web Token) configuration for user authentication
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY", 
        "dev-jwt-secret-CHANGE-IN-PRODUCTION"
    )
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256
    JWT_EXPIRATION_MINUTES: int = 15  # Tokens expire after 15 minutes
    
    # Application Pepper - CRITICAL for IDX generation
    # This should be stored in HSM (Hardware Security Module) in production
    # NEVER store in database or commit to Git!
    APPLICATION_PEPPER: str = os.getenv(
        "APPLICATION_PEPPER",
        "dev-pepper-XYZ123-CHANGE-IN-PRODUCTION"
    )
    
    
    # ==========================================
    # RBI CONFIGURATION
    # ==========================================
    
    # RBI's half of the split-key for court orders
    # This is the PERMANENT half (never expires)
    RBI_MASTER_KEY_HALF: str = os.getenv(
        "RBI_MASTER_KEY_HALF",
        "dev-rbi-key-half-CHANGE-IN-PRODUCTION"
    )
    
    
    # ==========================================
    # BLOCKCHAIN CONFIGURATION
    # ==========================================
    
    # Proof of Work difficulty (number of leading zeros required)
    # Difficulty 4 = hash must start with "0000"
    # Higher number = harder mining = more secure but slower
    POW_DIFFICULTY: int = int(os.getenv("POW_DIFFICULTY", "4"))
    
    # Target time for each block (in seconds)
    # System will adjust difficulty to maintain this target
    BLOCK_TIME_TARGET: int = int(os.getenv("BLOCK_TIME_TARGET", "3"))
    
    
    # ==========================================
    # SESSION CONFIGURATION
    # ==========================================
    
    # How often to rotate session IDs (in hours)
    # 24 hours = sessions expire and new ones created daily
    SESSION_ROTATION_HOURS: int = int(os.getenv("SESSION_ROTATION_HOURS", "24"))
    
    
    # ==========================================
    # FEE CONFIGURATION
    # ==========================================
    
    # Fee rates (as decimal percentages)
    POW_MINER_FEE_RATE: float = 0.005   # 0.5% of transaction goes to miners
    BANK_CONSENSUS_FEE_RATE: float = 0.01  # 1% split among 6 consortium banks
    
    # Total fee = 0.5% + 1% = 1.5% of transaction amount
    # Example: ₹1,000 transaction
    #   - Miner gets: ₹5 (0.5%)
    #   - 6 Banks get: ₹10 total = ₹1.67 each (1% ÷ 6)
    #   - Sender pays: ₹1,015 total
    
    
    # ==========================================
    # REDIS CONFIGURATION (for background tasks)
    # ==========================================
    
    # Redis URL for Celery background workers
    # Miners run in background using this
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    
    # ==========================================
    # API CONFIGURATION
    # ==========================================
    
    # API version prefix for all routes
    # Example: /api/v1/transactions/send
    API_V1_PREFIX: str = "/api/v1"
    
    # Project name (shown in API documentation)
    PROJECT_NAME: str = "IDX Crypto Banking Framework"
    
    # CORS (Cross-Origin Resource Sharing) - which websites can call our API
    CORS_ORIGINS: list = [
        "http://localhost:3000",  # React frontend
        "http://localhost:8000",  # API docs
    ]


    # ==========================================
    # MINING CONFIGURATION
    # ==========================================

    # Maximum number of concurrent miners (prevent resource exhaustion)
    MAX_MINERS: int = int(os.getenv("MAX_MINERS", "100"))

    # Mining timeout in seconds (stop mining if taking too long)
    MINING_TIMEOUT_SECONDS: int = int(os.getenv("MINING_TIMEOUT_SECONDS", "300"))

    # Mining thread priority (1-10, higher = more priority)
    MINING_THREAD_PRIORITY: int = int(os.getenv("MINING_THREAD_PRIORITY", "5"))


    # ==========================================
    # RATE LIMITING CONFIGURATION
    # ==========================================

    # Enable/disable rate limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"

    # Redis storage for rate limiting (separate DB from main Redis)
    RATE_LIMIT_STORAGE_URL: str = os.getenv("RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/1")

    # Rate limits per endpoint (format: "X per Y" where Y is: second, minute, hour, day)
    RATE_LIMITS: dict = {
        # Authentication endpoints (most restrictive)
        'auth_register': '10 per hour',     # Prevent mass account creation
        'auth_login': '20 per hour',        # Prevent brute force attacks

        # Transaction endpoints (moderate)
        'transaction_create': '100 per hour',
        'transaction_status': '500 per hour',
        'transaction_confirm': '200 per hour',

        # Mining endpoints (lenient - computational cost already limits)
        'mining_start': '10 per day',       # Prevent mining spam
        'mining_stop': '50 per hour',
        'mining_stats': '1000 per hour',

        # Court order endpoints (restrictive)
        'court_order_create': '5 per day',
        'court_order_execute': '10 per day',

        # Audit endpoints (government/authorized access)
        'audit_query': '1000 per hour',

        # Travel account endpoints
        'travel_create': '20 per hour',
        'travel_close': '50 per hour',

        # General API default
        'default': '1000 per hour',
    }

    # DDoS protection thresholds
    DDOS_THRESHOLD: int = int(os.getenv("DDOS_THRESHOLD", "1000"))  # Requests per minute before auto-block
    DDOS_BLOCK_DURATION_MINUTES: int = int(os.getenv("DDOS_BLOCK_DURATION_MINUTES", "60"))


    # ==========================================
    # AUDIT & COMPLIANCE CONFIGURATION
    # ==========================================

    # Audit log retention period (in days)
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "2555"))  # ~7 years

    # Enable cryptographic signing of audit logs
    AUDIT_LOG_SIGNING_ENABLED: bool = os.getenv("AUDIT_LOG_SIGNING_ENABLED", "True").lower() == "true"


    # ==========================================
    # TRAVEL ACCOUNT CONFIGURATION
    # ==========================================

    # Default travel account duration (in days)
    DEFAULT_TRAVEL_ACCOUNT_DURATION_DAYS: int = int(os.getenv("DEFAULT_TRAVEL_ACCOUNT_DURATION_DAYS", "90"))

    # Maximum travel account duration (in days)
    MAX_TRAVEL_ACCOUNT_DURATION_DAYS: int = int(os.getenv("MAX_TRAVEL_ACCOUNT_DURATION_DAYS", "365"))

    # Forex fee percentage (0.15% = 0.0015)
    FOREX_FEE_PERCENTAGE: float = float(os.getenv("FOREX_FEE_PERCENTAGE", "0.0015"))


    # ==========================================
    # LOGGING CONFIGURATION
    # ==========================================

    # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Where to store log files
    LOG_DIR: str = "logs"
    
    
    class Config:
        """Pydantic configuration"""
        case_sensitive = True

    def validate_production_secrets(self) -> None:
        """
        Fail-fast validation for production secrets

        SECURITY: Prevents accidental production deployment with default keys
        This method checks that all critical secrets are properly set and
        are not using development default values.

        Raises:
            ValueError: If any required secret is missing or using default value
        """
        # List of critical secrets that must not use default values
        critical_secrets = [
            ('SECRET_KEY', self.SECRET_KEY, 'dev-secret-key-CHANGE-IN-PRODUCTION'),
            ('JWT_SECRET_KEY', self.JWT_SECRET_KEY, 'dev-jwt-secret-CHANGE-IN-PRODUCTION'),
            ('APPLICATION_PEPPER', self.APPLICATION_PEPPER, 'dev-pepper-XYZ123-CHANGE-IN-PRODUCTION'),
            ('RBI_MASTER_KEY_HALF', self.RBI_MASTER_KEY_HALF, 'dev-rbi-key-half-CHANGE-IN-PRODUCTION'),
        ]

        # Check if running in production mode (check for common production indicators)
        is_production = (
            os.getenv('ENVIRONMENT') == 'production' or
            os.getenv('ENV') == 'production' or
            os.getenv('FLASK_ENV') == 'production'
        )

        # In production, fail fast if any secrets are using defaults
        if is_production:
            for secret_name, secret_value, default_value in critical_secrets:
                if not secret_value or secret_value == default_value:
                    raise ValueError(
                        f"PRODUCTION DEPLOYMENT BLOCKED: {secret_name} must be set in environment variables. "
                        f"Current value is missing or using development default. "
                        f"Set {secret_name}=<secure-random-value> in your .env file or environment."
                    )

        # In development, warn if using defaults (but don't fail)
        else:
            warnings = []
            for secret_name, secret_value, default_value in critical_secrets:
                if not secret_value or secret_value == default_value:
                    warnings.append(
                        f"⚠️  WARNING: {secret_name} is using development default value. "
                        f"This is INSECURE for production!"
                    )

            if warnings:
                print("\n" + "=" * 80)
                print("🔓 DEVELOPMENT MODE - Security Warnings:")
                print("=" * 80)
                for warning in warnings:
                    print(warning)
                print("\nTo fix: Set these values in your .env file or environment variables.")
                print("=" * 80 + "\n")


# Create a single instance that all files will import
# Usage: from config.settings import settings
settings = Settings()

# Validate secrets on startup
settings.validate_production_secrets()


# Example usage (for testing this file)
if __name__ == "__main__":
    print("=== IDX Banking Configuration ===")
    print(f"Database: {settings.DATABASE_URL}")
    print(f"PoW Difficulty: {settings.POW_DIFFICULTY}")
    print(f"Miner Fee: {settings.POW_MINER_FEE_RATE * 100}%")
    print(f"Bank Fee: {settings.BANK_CONSENSUS_FEE_RATE * 100}%")
    print(f"Session Rotation: {settings.SESSION_ROTATION_HOURS} hours")
    print("✅ Settings loaded successfully!")