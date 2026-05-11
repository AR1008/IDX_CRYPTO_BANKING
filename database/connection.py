"""
IDX Crypto Banking - Database Connection Management
Purpose: Manages PostgreSQL connections with connection pooling

Key Features:
1. Connection pooling for high performance (20-30 concurrent connections)
2. Automatic connection health checks (pre-ping)
3. Statement timeout (prevents long-running queries from blocking)
4. Session management for transaction control (ACID compliance)
"""

# [DOC] SQLAlchemy imports: create_engine builds the DB engine, event lets us hook into connection lifecycle
from sqlalchemy import create_engine, event
# [DOC] sessionmaker creates DB session factories; declarative_base is the parent class for all ORM models
from sqlalchemy.orm import sessionmaker, declarative_base
# [DOC] QueuePool manages a fixed pool of reusable connections to avoid overhead of creating new ones
from sqlalchemy.pool import QueuePool
# [DOC] settings holds all environment-driven config values including DATABASE_URL
from config.settings import settings
# [DOC] text() wraps raw SQL strings so SQLAlchemy can execute them safely
from sqlalchemy import text

# ==========================================
# DATABASE ENGINE SETUP
# ==========================================

# [DOC] The engine is the central object that knows how to talk to PostgreSQL
# [DOC] All sessions, queries, and connections flow through this single engine instance
engine = create_engine(
    # [DOC] DATABASE_URL is read from environment, e.g. postgresql://user:pass@localhost/idx_banking
    settings.DATABASE_URL,

    # [DOC] QueuePool: maintains a pool of persistent connections — reuses them instead of creating new ones per request
    poolclass=QueuePool,

    # [DOC] pool_size=20: keep 20 connections permanently open and ready; avoids per-request TCP handshake overhead
    pool_size=20,

    # [DOC] max_overflow=10: allow up to 10 extra connections beyond the pool when traffic spikes; total cap = 30
    max_overflow=10,

    # [DOC] pool_pre_ping=True: before handing a connection to a caller, send a trivial query to confirm it is alive
    pool_pre_ping=True,

    # [DOC] pool_recycle=3600: forcibly replace connections older than 1 hour; prevents PostgreSQL from closing idle ones silently
    pool_recycle=3600,

    # [DOC] echo=False: do not print every SQL statement to stdout; set True only when debugging queries
    echo=False,
)


# ==========================================
# SESSION FACTORY
# ==========================================

# [DOC] SessionLocal is a factory: calling SessionLocal() creates one database session (think: one conversation with DB)
SessionLocal = sessionmaker(
    # [DOC] autocommit=False: changes are NOT saved to DB until code explicitly calls db.commit() — critical for banking atomicity
    autocommit=False,

    # [DOC] autoflush=False: Python-side changes are NOT pushed to DB until we choose; allows batching multiple operations
    autoflush=False,

    # [DOC] bind=engine: all sessions created by this factory use the engine configured above
    bind=engine
)


# ==========================================
# BASE CLASS FOR ALL MODELS
# ==========================================

# [DOC] Base is the superclass every ORM model (User, Transaction, Block, etc.) must inherit from
# [DOC] SQLAlchemy inspects Base.metadata to discover all tables at runtime
Base = declarative_base()


# ==========================================
# DATABASE EVENT HANDLERS
# ==========================================

# [DOC] This decorator registers set_statement_timeout to run every time a new DB connection is opened
@event.listens_for(engine, "connect")
def set_statement_timeout(dbapi_connection, connection_record):
    """
    Set statement timeout for all database connections

    Purpose: Prevent any single query from running too long and blocking others
    Timeout: 30 seconds (30,000 milliseconds)

    Why this matters:
    - Without timeout: A bad query could run forever, blocking the system
    - With timeout: Query automatically cancelled after 30 seconds

    Example:
        # Bad query that scans entire blockchain
        SELECT * FROM blocks WHERE hash LIKE '%abc%'  # Could take minutes!

        # With timeout:
        After 30 seconds → PostgreSQL kills the query → Error returned
        Other transactions continue normally
    """
    # [DOC] Open a cursor on the raw DB-API connection (bypasses SQLAlchemy to set a session-level variable)
    cursor = dbapi_connection.cursor()
    # [DOC] Tell PostgreSQL to abort any query that runs longer than 30 000 ms (30 seconds)
    cursor.execute("SET statement_timeout = 30000")  # 30 seconds in milliseconds
    # [DOC] Close cursor immediately — we only needed it for the SET command
    cursor.close()


# ==========================================
# DEPENDENCY INJECTION FOR FASTAPI
# ==========================================

def get_db():
    """
    Dependency function for FastAPI routes
    Provides database session with automatic cleanup

    How it works:
    1. Creates a new session
    2. Yields (gives) the session to the route
    3. Route uses the session
    4. After route finishes, automatically closes session

    Usage in FastAPI:
        from database.connection import get_db

        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            users = db.query(User).all()
            return users

        # After this function returns, session is automatically closed!

    Why this pattern?
    - Ensures sessions are ALWAYS closed (no connection leaks)
    - Even if route crashes, session is closed in the finally block
    - Clean, reusable code (DRY principle)
    """
    # [DOC] Instantiate a new session from the factory — this opens one connection from the pool
    db = SessionLocal()
    try:
        # [DOC] yield pauses here and hands db to the caller (route function); resumes after the route returns
        yield db
    finally:
        # [DOC] Always executed — even if the route raised an exception — returns the connection to the pool
        db.close()


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():
    """
    Initialize database - Create all tables

    This function:
    1. Imports all models (User, Account, Transaction, etc.)
    2. Creates corresponding tables in PostgreSQL
    3. If tables already exist, does nothing (safe to run multiple times)

    When to run:
    - First time setting up the project
    - After adding new models
    - After modifying existing models (with migrations)

    How to run:
        Method 1 (from terminal):
            python -c "from database.connection import init_db; init_db()"

        Method 2 (from Python script):
            from database.connection import init_db
            init_db()

    What it creates:
    - users table
    - accounts table
    - transactions table
    - blocks_public table
    - blocks_private table
    - sessions table
    - court_orders table
    - consortium_banks table
    - ... and all other models we define
    """
    # [DOC] Import every model module so their classes register themselves on Base.metadata
    from database.models import (
        user,           # User model (IDX, PAN, name, etc.)
        account,        # Bank accounts (HDFC, ICICI, etc.)
        transaction,    # Transactions between users
        block,          # Blockchain blocks (public + private)
        session,        # Session IDs (24-hour rotation)
        court_order,    # Court orders for de-anonymization
        bank            # Consortium banks (6 validators)
    )

    # [DOC] create_all scans Base.metadata for every table definition and issues CREATE TABLE IF NOT EXISTS
    Base.metadata.create_all(bind=engine)

    print("✅ Database tables created successfully!")
    print(f"📊 Database: {settings.DATABASE_URL}")
    print(f"📁 Tables created from Base.metadata")


# ==========================================
# EXAMPLE USAGE (for testing this file)
# ==========================================

if __name__ == "__main__":
    """
    Test the database connection
    Run this file directly to test: python database/connection.py
    """
    print("=== Testing Database Connection ===")
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Pool size: {engine.pool.size()}")
    print(f"Max overflow: 10")

    # [DOC] engine.connect() borrows one connection from the pool for the duration of the with-block
    with engine.connect() as connection:
        # [DOC] Execute raw SQL to confirm PostgreSQL is reachable and responding
        result = connection.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Connected to PostgreSQL!")
        print(f"📌 Version: {version}")

    print("\n=== Connection Pool Status ===")
    # [DOC] checkedout(): how many connections are currently in use by active sessions
    print(f"Checked out: {engine.pool.checkedout()}")
    # [DOC] overflow(): how many extra connections (beyond pool_size) are currently open
    print(f"Overflow: {engine.pool.overflow()}")
    print(f"Size: {engine.pool.size()}")

    print("\n✅ Database connection test completed!")
