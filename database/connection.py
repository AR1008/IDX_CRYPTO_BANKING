"""
IDX Crypto Banking - Database Connection Management
Author: Ashutosh Rajesh
Purpose: Manages PostgreSQL connections with connection pooling

Key Features:
1. Connection pooling for high performance (20-30 concurrent connections)
2. Automatic connection health checks (pre-ping)
3. Statement timeout (prevents long-running queries from blocking)
4. Session management for transaction control (ACID compliance)
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from config.settings import settings
from sqlalchemy import text

# ==========================================
# DATABASE ENGINE SETUP
# ==========================================

# Create database engine with connection pooling
# This is the "master connection manager" for the entire application
engine = create_engine(
    settings.DATABASE_URL,
    
    # Use QueuePool for managing connections efficiently
    # QueuePool maintains a pool of connections that can be reused
    poolclass=QueuePool,
    
    # Connection pool configuration
    pool_size=20,           # Keep 20 connections always open and ready
                            # These are "hot" connections, ready to use instantly
    
    max_overflow=10,        # Can create up to 10 additional temporary connections
                            # Total max = pool_size + max_overflow = 30 connections
                            # After use, overflow connections are closed
    
    pool_pre_ping=True,     # Test each connection before using it
                            # Prevents errors from stale/dead connections
                            # Small overhead (~1ms) but prevents crashes
    
    pool_recycle=3600,      # Recycle connections after 1 hour (3600 seconds)
                            # Prevents connections from becoming stale
                            # PostgreSQL may close idle connections, this prevents errors
    
    echo=False,             # Set to True to see all SQL queries (useful for debugging)
                            # Production: False (better performance)
                            # Development: True (see what's happening)
)


# ==========================================
# SESSION FACTORY
# ==========================================

# SessionLocal is a factory that creates database sessions
# Each session represents a "conversation" with the database
SessionLocal = sessionmaker(
    autocommit=False,       # CRITICAL for banking: We control when to commit
                            # All changes stay in memory until we explicitly commit
                            # This enables ALL-or-NOTHING transactions
    
    autoflush=False,        # We control when to sync Python objects to database
                            # Better performance: batch multiple operations
    
    bind=engine             # Connect this session factory to our engine
)


# ==========================================
# BASE CLASS FOR ALL MODELS
# ==========================================

# Base is the parent class for ALL database tables
# Every model (User, Account, Transaction, etc.) will inherit from Base
Base = declarative_base()


# ==========================================
# DATABASE EVENT HANDLERS
# ==========================================

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
    cursor = dbapi_connection.cursor()
    cursor.execute("SET statement_timeout = 30000")  # 30 seconds in milliseconds
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
    db = SessionLocal()  # Create new session
    try:
        yield db  # Give session to the route
    finally:
        db.close()  # ALWAYS close session (even if error occurred)


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
    # Import all models here so SQLAlchemy knows about them
    # We'll create these models in the next files
    from database.models import (
        user,           # User model (IDX, PAN, name, etc.)
        account,        # Bank accounts (HDFC, ICICI, etc.)
        transaction,    # Transactions between users
        block,          # Blockchain blocks (public + private)
        session,        # Session IDs (24-hour rotation)
        court_order,    # Court orders for de-anonymization
        bank            # Consortium banks (6 validators)
    )
    
    # Create all tables defined in models
    # Base.metadata contains info about all tables
    # create_all() creates tables that don't exist yet
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
    
    # Test connection by executing a simple query
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Connected to PostgreSQL!")
        print(f"📌 Version: {version}")
    
    print("\n=== Connection Pool Status ===")
    print(f"Checked out: {engine.pool.checkedout()}")
    print(f"Overflow: {engine.pool.overflow()}")
    print(f"Size: {engine.pool.size()}")
    
    print("\n✅ Database connection test completed!")