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

# [DOC] os gives access to environment variables — values set outside the code (e.g. in a .env file or shell)
import os
# [DOC] load_dotenv reads a .env file on disk and injects its key=value pairs into os.getenv() — keeps secrets out of source code
from dotenv import load_dotenv

# [DOC] Actually load the .env file now; must be called before any os.getenv() reads
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
    # [DOC] DATABASE_URL tells SQLAlchemy where PostgreSQL is running and which database to open
    # [DOC] os.getenv("DATABASE_URL", <default>) reads the env var; if absent, falls back to the default string
    # [DOC] The default URL points to localhost with database name "idx_banking" — override this in .env for other machines
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://db_user@localhost/idx_banking"
    )
    # Format: postgresql://USERNAME@HOST/DATABASE_NAME
    # Set DATABASE_URL env var (or update the default above) to match your local PostgreSQL username


    # ==========================================
    # SECURITY CONFIGURATION
    # ==========================================

    # [DOC] SECRET_KEY is a random string used by Flask for general-purpose signing (e.g. flash messages, cookies)
    # [DOC] The dev default is intentionally weak — MUST be replaced with a long random value before going to production
    # Secret key for application (used for general encryption)
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "dev-secret-key-CHANGE-IN-PRODUCTION"
    )

    # [DOC] JWT_SECRET_KEY signs JSON Web Tokens — anyone with this key can forge valid login tokens, so keep it secret
    # JWT (JSON Web Token) configuration for user authentication
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "dev-jwt-secret-CHANGE-IN-PRODUCTION"
    )
    # [DOC] JWT_ALGORITHM specifies the signing algorithm: HS256 = HMAC with SHA-256 (symmetric — same key to sign and verify)
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256
    # [DOC] JWT_EXPIRATION_MINUTES = 15 means every login token expires after 15 minutes — limits damage if a token is stolen
    JWT_EXPIRATION_MINUTES: int = 15  # Tokens expire after 15 minutes

    # [DOC] APPLICATION_PEPPER is a secret string mixed into IDX derivation: IDX = SHA256(national_id + authority_id + PEPPER)
    # [DOC] Without the pepper an attacker who reads the database cannot reverse-engineer real identities from IDX values
    # [DOC] Production: store this in an HSM (Hardware Security Module), never in version control
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

    # [DOC] RBI_MASTER_KEY_HALF is one half of the split-key used for court-order decryption
    # [DOC] The two-of-two scheme means: Company key half AND this regulatory key half are both required to decrypt
    # [DOC] Storing only one half here means even a full database breach cannot decrypt private transaction records alone
    # RBI's half of the split-key for court orders
    # This is the PERMANENT half (never expires)
    RBI_MASTER_KEY_HALF: str = os.getenv(
        "RBI_MASTER_KEY_HALF",
        "dev-rbi-key-half-CHANGE-IN-PRODUCTION"
    )


    # ==========================================
    # CONSORTIUM POLICY — General (N, X) parametrisation
    # ==========================================
    #
    # N = total consortium banks
    # X = maximum tolerated dishonest banks (policy-defined)
    # T = N - X  = required approval threshold (auto-computed)
    #
    # BFT safety condition (from Castro-Liskov PBFT, OSDI 1999):
    #   X must be < N/3  to guarantee quorum intersection with at least
    #   one honest bank.  Startup will assert this condition.
    #
    # Indian consortium instantiation (default):
    #   N=12, X=2, T=10 (83%) — more conservative than BFT minimum (X<4)
    #
    # Alternative instantiations:
    #   Small consortium:   N=4,  X=1, T=3  (75%)
    #   Large network:      N=50, X=16, T=34 (68%)  — exactly at BFT limit
    # [DOC] CONSENSUS_N = total number of banks in the consortium; default 12
    # [DOC] Changing this via env var lets you deploy the same code with a different-sized consortium
    CONSENSUS_N: int = int(os.getenv("CONSENSUS_N", "12"))
    # [DOC] CONSENSUS_X = the maximum number of banks that may act dishonestly (collude, go offline, lie)
    # [DOC] Must satisfy X < N/3 (Byzantine Fault Tolerance bound); default 2 out of 12 = well within limit
    CONSENSUS_X: int = int(os.getenv("CONSENSUS_X", "2"))

    @property
    # [DOC] CONSENSUS_T is the required approval count computed automatically as N - X (here: 12 - 2 = 10)
    # [DOC] Using @property means Python recomputes this whenever it is accessed, so it always reflects current N and X
    def CONSENSUS_T(self) -> int:
        """Required approval threshold T = N - X. Auto-computed."""
        return self.CONSENSUS_N - self.CONSENSUS_X

    # [DOC] CONSENSUS_MANDATORY_BANKS is a comma-separated list of bank codes that MUST be in every approving quorum
    # [DOC] Empty string means no mandatory sub-quorum; set e.g. "SBI,HDFC" to require both sender's and receiver's bank
    # Comma-separated bank codes that MUST be in any approving quorum.
    # E.g. "SBI,HDFC" means sender's and receiver's banks must approve.
    # Leave empty ("") to enforce no mandatory sub-quorum.
    CONSENSUS_MANDATORY_BANKS: str = os.getenv("CONSENSUS_MANDATORY_BANKS", "")

    # ==========================================
    # DISTRIBUTED CONSENSUS CONFIGURATION
    # ==========================================

    # [DOC] CONSENSUS_MODE controls how bank votes are collected.
    # [DOC] "local" = in-process simulation (default for dev/test — no network needed).
    # [DOC] "distributed" = real HTTP POST to each bank node's /consensus/vote endpoint.
    CONSENSUS_MODE: str = os.getenv("CONSENSUS_MODE", "local")

    # [DOC] CONSENSUS_VOTE_TIMEOUT_SECONDS = 10: how long to wait for a remote bank's HTTP vote response.
    # [DOC] A bank that doesn't respond within this window counts as REJECT (fail-safe).
    CONSENSUS_VOTE_TIMEOUT_SECONDS: int = int(os.getenv("CONSENSUS_VOTE_TIMEOUT_SECONDS", "10"))

    # [DOC] INTER_BANK_SECRET: shared pre-shared key used by /consensus/vote to authenticate callers.
    # [DOC] All consortium nodes share this secret; a caller without it receives HTTP 403.
    # [DOC] In production this should be replaced by mutual TLS; this PSK suffices for the research prototype.
    INTER_BANK_SECRET: str = os.getenv("INTER_BANK_SECRET", "idx-inter-bank-dev-secret-2026")

    # [DOC] THIS_BANK_CODE: the bank code identifying which node this Flask process represents.
    # [DOC] Used by /consensus/vote to label its own response with the correct bank_code.
    # [DOC] Set via env var when deploying multiple bank nodes (e.g. THIS_BANK_CODE=HDFC).
    THIS_BANK_CODE: str = os.getenv("THIS_BANK_CODE", "UNKNOWN")

    def validate_consortium_policy(self) -> None:
        """Assert BFT safety condition X < N/3.  Call once at startup."""
        # [DOC] Read the current N and X values into local variables for clarity
        N, X = self.CONSENSUS_N, self.CONSENSUS_X
        # [DOC] X=0 would require unanimous agreement — impractical in any real consortium, so reject it
        if X < 1:
            raise ValueError(f"CONSENSUS_X must be ≥ 1 (got {X}); X=0 requires unanimity.")
        # [DOC] X >= N would mean tolerating more dishonest banks than there are banks — makes no sense
        if X >= N:
            raise ValueError(f"CONSENSUS_X ({X}) must be < CONSENSUS_N ({N}).")
        # [DOC] The core BFT safety check: if X >= N/3, two valid quorums of size T could have zero overlap in honest banks
        # [DOC] That lets a Byzantine attacker convince two honest sub-groups of conflicting facts (network split)
        if X >= N / 3:
            raise ValueError(
                f"BFT safety violated: CONSENSUS_X={X} must be < N/3={N/3:.2f}. "
                f"With X={X} dishonest banks out of N={N}, two quorums of size T={N-X} "
                f"may not overlap in an honest bank — Byzantine faults can split the network. "
                f"Lower CONSENSUS_X or raise CONSENSUS_N."
            )

    # ==========================================
    # BLOCKCHAIN CONFIGURATION
    # ==========================================

    # [DOC] POW_DIFFICULTY = 4 means the SHA-256 block hash must start with exactly 4 hex zeros ("0000...")
    # [DOC] Each extra zero multiplies the expected mining work by 16 (hex digits are base-16)
    # [DOC] Difficulty 4 gives ~47,000 hash attempts per block — takes a few seconds on commodity hardware
    # Proof of Work difficulty (number of leading zeros required)
    # Difficulty 4 = hash must start with "0000"
    # Higher number = harder mining = more secure but slower
    POW_DIFFICULTY: int = int(os.getenv("POW_DIFFICULTY", "4"))

    # [DOC] BLOCK_TIME_TARGET sets the desired seconds between blocks — the system could auto-adjust difficulty to hit this
    # Target time for each block (in seconds)
    # System will adjust difficulty to maintain this target
    BLOCK_TIME_TARGET: int = int(os.getenv("BLOCK_TIME_TARGET", "3"))


    # ==========================================
    # SESSION CONFIGURATION
    # ==========================================

    # [DOC] SESSION_ROTATION_HOURS = 24 means every user's public session ID changes once per day
    # [DOC] This is Layer 1 of the three-layer identity system — rotating IDs break long-term linkability on the public chain
    # [DOC] Rotation is invisible to users; the background worker handles it automatically
    # How often to rotate session IDs (in hours)
    # 24 hours = sessions expire and new ones created daily
    SESSION_ROTATION_HOURS: int = int(os.getenv("SESSION_ROTATION_HOURS", "24"))


    # ==========================================
    # FEE CONFIGURATION
    # ==========================================

    # [DOC] POW_MINER_FEE_RATE = 0.5% of each transaction amount is paid to the miner who mines the block
    # [DOC] BANK_CONSENSUS_FEE_RATE = 1.0% is split equally among the consortium banks that voted to approve the batch
    # Fee rates (as decimal percentages)
    POW_MINER_FEE_RATE: float = 0.005   # 0.5% of transaction goes to miners
    BANK_CONSENSUS_FEE_RATE: float = 0.01  # 1% split equally among the N consortium banks that approved

    # Total fee = 0.5% + 1% = 1.5% of transaction amount
    # Example: ₹1,000 transaction with N=12 banks
    #   - Miner gets: ₹5 (0.5%)
    #   - N banks share: ₹10 total = ₹10/N each (1% ÷ N)
    #   - Sender pays: ₹1,015 total


    # ==========================================
    # REDIS CONFIGURATION (for background tasks)
    # ==========================================

    # [DOC] REDIS_URL points to the Redis in-memory store used by Celery task workers (e.g. the mining background job)
    # [DOC] Redis database index /0 is used here; /1 is used separately for rate-limit counters below
    # Redis URL for Celery background workers
    # Miners run in background using this
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


    # ==========================================
    # API CONFIGURATION
    # ==========================================

    # [DOC] API_V1_PREFIX is prepended to every route URL — e.g. /api/v1/transactions — making versioning explicit
    # API version prefix for all routes
    # Example: /api/v1/transactions/send
    API_V1_PREFIX: str = "/api/v1"

    # [DOC] PROJECT_NAME appears in auto-generated API documentation (Swagger/OpenAPI)
    # Project name (shown in API documentation)
    PROJECT_NAME: str = "IDX Crypto Banking Framework"

    # [DOC] CORS_ORIGINS is the whitelist of browser origins allowed to call the API
    # [DOC] Browsers enforce CORS; only origins in this list can make cross-origin fetch/XHR calls
    # CORS (Cross-Origin Resource Sharing) - which websites can call our API
    CORS_ORIGINS: list = [
        "http://localhost:3000",  # React frontend
        "http://localhost:8000",  # API docs
    ]


    # ==========================================
    # MINING CONFIGURATION
    # ==========================================

    # [DOC] MAX_MINERS caps how many concurrent mining threads can run at once — prevents CPU/memory exhaustion
    # Maximum number of concurrent miners (prevent resource exhaustion)
    MAX_MINERS: int = int(os.getenv("MAX_MINERS", "100"))

    # [DOC] MINING_TIMEOUT_SECONDS = 300 — if a block takes longer than 5 minutes to mine, the attempt is abandoned
    # [DOC] This guards against runaway loops if difficulty is accidentally set too high
    # Mining timeout in seconds (stop mining if taking too long)
    MINING_TIMEOUT_SECONDS: int = int(os.getenv("MINING_TIMEOUT_SECONDS", "300"))

    # [DOC] MINING_THREAD_PRIORITY (1–10) hints to the OS scheduler how important mining threads are relative to others
    # Mining thread priority (1-10, higher = more priority)
    MINING_THREAD_PRIORITY: int = int(os.getenv("MINING_THREAD_PRIORITY", "5"))


    # ==========================================
    # RATE LIMITING CONFIGURATION
    # ==========================================

    # [DOC] RATE_LIMIT_ENABLED is a kill-switch — set to False in unit tests to avoid hitting Redis
    # Enable/disable rate limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"

    # [DOC] RATE_LIMIT_STORAGE_URL uses Redis database /1 (separate from the Celery /0 database) to store per-IP counters
    # Redis storage for rate limiting (separate DB from main Redis)
    RATE_LIMIT_STORAGE_URL: str = os.getenv("RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/1")

    # [DOC] RATE_LIMITS maps each endpoint name to a Flask-Limiter rule string like "20 per hour"
    # [DOC] Flask-Limiter reads these at request time and returns HTTP 429 when the limit is exceeded
    # Rate limits per endpoint (format: "X per Y" where Y is: second, minute, hour, day)
    RATE_LIMITS: dict = {
        # Authentication endpoints (most restrictive)
        # [DOC] auth_register limited to 10/hour — prevents mass automated account creation
        'auth_register': '10 per hour',     # Prevent mass account creation
        # [DOC] auth_login limited to 20/hour — slows brute-force password guessing
        'auth_login': '20 per hour',        # Prevent brute force attacks

        # Transaction endpoints (moderate)
        'transaction_create': '100 per hour',
        'transaction_status': '500 per hour',
        'transaction_confirm': '200 per hour',

        # Mining endpoints (lenient - computational cost already limits)
        # [DOC] mining_start limited to 10/day — mining is CPU-intensive so high-rate abuse is self-limiting anyway
        'mining_start': '10 per day',       # Prevent mining spam
        'mining_stop': '50 per hour',
        'mining_stats': '1000 per hour',

        # Court order endpoints (restrictive)
        # [DOC] court_order_create limited to 5/day — court orders are rare legal events; high rates would be suspicious
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

    # [DOC] DDOS_THRESHOLD — if a single IP exceeds 1000 requests per minute it is auto-blocked as a likely DDoS attacker
    # DDoS protection thresholds
    DDOS_THRESHOLD: int = int(os.getenv("DDOS_THRESHOLD", "1000"))  # Requests per minute before auto-block
    # [DOC] DDOS_BLOCK_DURATION_MINUTES = 60 — blocked IPs are banned for 1 hour before being automatically unblocked
    DDOS_BLOCK_DURATION_MINUTES: int = int(os.getenv("DDOS_BLOCK_DURATION_MINUTES", "60"))


    # ==========================================
    # AUDIT & COMPLIANCE CONFIGURATION
    # ==========================================

    # [DOC] AUDIT_LOG_RETENTION_DAYS = 2555 (~7 years) — financial regulations often require 7-year record retention
    # Audit log retention period (in days)
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "2555"))  # ~7 years

    # [DOC] AUDIT_LOG_SIGNING_ENABLED — when True, each audit log entry gets a cryptographic signature proving it was not tampered with
    # Enable cryptographic signing of audit logs
    AUDIT_LOG_SIGNING_ENABLED: bool = os.getenv("AUDIT_LOG_SIGNING_ENABLED", "True").lower() == "true"


    # ==========================================
    # TRAVEL ACCOUNT CONFIGURATION
    # ==========================================

    # [DOC] DEFAULT_TRAVEL_ACCOUNT_DURATION_DAYS = 90 — travel accounts (for cross-border payments) expire after 3 months by default
    # Default travel account duration (in days)
    DEFAULT_TRAVEL_ACCOUNT_DURATION_DAYS: int = int(os.getenv("DEFAULT_TRAVEL_ACCOUNT_DURATION_DAYS", "90"))

    # [DOC] MAX_TRAVEL_ACCOUNT_DURATION_DAYS = 365 — no travel account can be kept open longer than one year
    # Maximum travel account duration (in days)
    MAX_TRAVEL_ACCOUNT_DURATION_DAYS: int = int(os.getenv("MAX_TRAVEL_ACCOUNT_DURATION_DAYS", "365"))

    # [DOC] FOREX_FEE_PERCENTAGE = 0.15% charged on currency-conversion transactions (forex spread)
    # Forex fee percentage (0.15% = 0.0015)
    FOREX_FEE_PERCENTAGE: float = float(os.getenv("FOREX_FEE_PERCENTAGE", "0.0015"))


    # ==========================================
    # LOGGING CONFIGURATION
    # ==========================================

    # [DOC] LOG_LEVEL controls which messages appear in the log; INFO shows normal operations, DEBUG adds verbose detail
    # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # [DOC] LOG_DIR is the directory where rotating log files are written — relative to the project root
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
        # [DOC] critical_secrets lists every secret that must not use its dev-default value in production
        # [DOC] Each tuple is (env_var_name, current_value, dev_default_value)
        # List of critical secrets that must not use default values
        critical_secrets = [
            ('SECRET_KEY', self.SECRET_KEY, 'dev-secret-key-CHANGE-IN-PRODUCTION'),
            ('JWT_SECRET_KEY', self.JWT_SECRET_KEY, 'dev-jwt-secret-CHANGE-IN-PRODUCTION'),
            ('APPLICATION_PEPPER', self.APPLICATION_PEPPER, 'dev-pepper-XYZ123-CHANGE-IN-PRODUCTION'),
            ('RBI_MASTER_KEY_HALF', self.RBI_MASTER_KEY_HALF, 'dev-rbi-key-half-CHANGE-IN-PRODUCTION'),
        ]

        # [DOC] is_production checks three common environment variable conventions to detect a production deployment
        # Check if running in production mode (check for common production indicators)
        is_production = (
            os.getenv('ENVIRONMENT') == 'production' or
            os.getenv('ENV') == 'production' or
            os.getenv('FLASK_ENV') == 'production'
        )

        # [DOC] In production: raise immediately if any secret is still at its dev default — blocks a dangerous deployment
        # In production, fail fast if any secrets are using defaults
        if is_production:
            for secret_name, secret_value, default_value in critical_secrets:
                if not secret_value or secret_value == default_value:
                    raise ValueError(
                        f"PRODUCTION DEPLOYMENT BLOCKED: {secret_name} must be set in environment variables. "
                        f"Current value is missing or using development default. "
                        f"Set {secret_name}=<secure-random-value> in your .env file or environment."
                    )

        # [DOC] In development: print a visible warning but do not crash — lets developers run without configuring secrets
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


# [DOC] Create exactly one Settings instance shared by the entire application — all modules do "from config.settings import settings"
# Create a single instance that all files will import
# Usage: from config.settings import settings
settings = Settings()

# [DOC] Run the secret-validation check immediately at import time so a misconfigured production box fails before serving any requests
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
