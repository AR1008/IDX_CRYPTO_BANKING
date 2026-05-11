"""
Database Migration: Multi-Bank Support
Purpose: Add support for multiple bank accounts per user

Changes:
1. Create bank_accounts table
2. Create recipients table
3. ALTER sessions table (add bank_account_id column)
4. ALTER transactions table (add sender_account_id, receiver_account_id columns)
5. Migrate existing data
"""

# [DOC] sys/os let us insert the project root into sys.path so local packages resolve
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# [DOC] Decimal is used for monetary amounts — avoids floating-point rounding errors
from decimal import Decimal
# [DOC] SessionLocal creates DB sessions; engine is the SQLAlchemy connection pool;
# Base holds ORM metadata used to create tables
from database.connection import SessionLocal, engine, Base
# [DOC] Import ORM model classes so SQLAlchemy knows their table schemas
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.recipient import Recipient
from database.models.transaction import Transaction, TransactionStatus
from database.models.session import Session as UserSession
# [DOC] text() wraps raw SQL strings for safe execution via SQLAlchemy
from sqlalchemy import text
# [DOC] random is used to add a 4-digit suffix to account numbers to avoid collisions
import random


# [DOC] Generate a bank account number by combining the bank code, last 8 chars of IDX, and a random suffix
def generate_account_number(bank_code, user_idx):
    """Generate unique bank account number"""
    # [DOC] Last 8 chars of the IDX hex string give enough entropy for uniqueness within a bank
    idx_part = user_idx[-8:]
    # [DOC] Random 4-digit number further reduces collision probability
    random_part = str(random.randint(1000, 9999))
    return f"{bank_code}{idx_part}{random_part}"


# [DOC] Query information_schema to check if a column already exists before attempting ALTER TABLE
# Prevents "duplicate column" errors when the migration is run more than once
def column_exists(engine, table_name, column_name):
    """Check if column exists in table"""
    with engine.connect() as conn:
        # [DOC] information_schema.columns is a standard SQL view listing every column in the DB
        result = conn.execute(text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='{table_name}'
            AND column_name='{column_name}'
        """))
        # [DOC] fetchone() returns None when no matching row is found — i.e. column absent
        return result.fetchone() is not None


# [DOC] Main migration function: creates new tables, adds columns, and back-fills existing data
def migrate_database():
    """Run migration"""

    print("=" * 70)
    print("DATABASE MIGRATION: Multi-Bank Support")
    print("=" * 70)

    # [DOC] Open a session for ORM-level queries (used in steps 3–5)
    db = SessionLocal()

    try:
        # [DOC] Step 1: create_all creates any missing tables (bank_accounts, recipients, etc.)
        # without touching tables that already exist — safe to re-run
        # Step 1: Create new tables
        print("\n📋 Step 1: Creating new tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created: bank_accounts, recipients")

        # [DOC] Step 2: add new columns to existing tables using raw DDL via a connection context
        print("\n📋 Step 2: Adding new columns to existing tables...")

        with engine.connect() as conn:
            # [DOC] bank_account_id links each session to exactly one bank account
            # allowing users to have accounts at multiple banks simultaneously
            # Add bank_account_id to sessions table
            if not column_exists(engine, 'sessions', 'bank_account_id'):
                print("  Adding bank_account_id to sessions table...")
                conn.execute(text("""
                    ALTER TABLE sessions
                    ADD COLUMN bank_account_id INTEGER
                """))
                conn.commit()
                print("  ✅ Added bank_account_id to sessions")
            else:
                # [DOC] Column already present — idempotent, skip silently
                print("  ⏭️  bank_account_id already exists in sessions")

            # [DOC] sender_account_id tracks which specific bank account the sender used
            # needed for multi-bank balance deduction
            # Add sender_account_id to transactions table
            if not column_exists(engine, 'transactions', 'sender_account_id'):
                print("  Adding sender_account_id to transactions table...")
                conn.execute(text("""
                    ALTER TABLE transactions
                    ADD COLUMN sender_account_id INTEGER
                """))
                conn.commit()
                print("  ✅ Added sender_account_id to transactions")
            else:
                print("  ⏭️  sender_account_id already exists in transactions")

            # [DOC] receiver_account_id tracks which bank account the receiver designated for credit
            # Add receiver_account_id to transactions table
            if not column_exists(engine, 'transactions', 'receiver_account_id'):
                print("  Adding receiver_account_id to transactions table...")
                conn.execute(text("""
                    ALTER TABLE transactions
                    ADD COLUMN receiver_account_id INTEGER
                """))
                conn.commit()
                print("  ✅ Added receiver_account_id to transactions")
            else:
                print("  ⏭️  receiver_account_id already exists in transactions")

        # [DOC] Step 3: create a default HDFC bank account for every user that doesn't have one yet
        # This preserves the existing balance by copying it into the new account
        # Step 3: Migrate existing users to have default HDFC accounts
        print("\n📋 Step 3: Migrating existing users...")

        # [DOC] Load all existing users to iterate and create accounts for each
        users = db.query(User).all()

        if not users:
            # [DOC] Nothing to migrate — fresh database with no users yet
            print("⚠️  No existing users found. Skipping migration.")
        else:
            for user in users:
                # [DOC] Check if this user already has a bank account so we don't create duplicates
                # Check if user already has accounts
                existing_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == user.idx
                ).first()

                if existing_account:
                    # [DOC] User already migrated — skip to avoid duplicate accounts
                    print(f"  ⏭️  User {user.full_name} already has accounts. Skipping.")
                    continue

                # [DOC] Generate a unique account number combining bank code + IDX tail + random suffix
                # Create default HDFC account with user's current balance
                account_number = generate_account_number("HDFC", user.idx)

                # [DOC] Transfer the user's existing top-level balance into the new HDFC account
                bank_account = BankAccount(
                    user_idx=user.idx,
                    bank_code="HDFC",
                    account_number=account_number,
                    balance=user.balance,
                    is_active=True,
                    is_frozen=False
                )

                db.add(bank_account)
                print(f"  ✅ Created HDFC account for {user.full_name}")
                print(f"     Account: {account_number}")
                print(f"     Balance: ₹{user.balance}")

            # [DOC] Commit all new BankAccount rows at once after iterating all users
            db.commit()
            print(f"\n✅ Migrated {len(users)} users")

        # [DOC] Step 4: back-fill bank_account_id on sessions that were created before this migration
        print("\n📋 Step 4: Linking existing sessions to bank accounts...")

        # [DOC] Find sessions where bank_account_id is still NULL (pre-migration rows)
        sessions = db.query(UserSession).filter(
            UserSession.bank_account_id == None
        ).all()

        if not sessions:
            print("⚠️  No unlinked sessions found.")
        else:
            for session in sessions:
                # [DOC] Match each session to the user's default HDFC account created in Step 3
                # Find user's HDFC account (default)
                account = db.query(BankAccount).filter(
                    BankAccount.user_idx == session.user_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()

                if account:
                    # [DOC] Set the foreign key so the session is now linked to the account
                    session.bank_account_id = account.id
                    print(f"  ✅ Linked session to {account.bank_code} account")

            db.commit()
            print(f"\n✅ Linked {len(sessions)} sessions")

        # [DOC] Step 5: back-fill account IDs on transactions that predate the multi-bank schema
        print("\n📋 Step 5: Linking existing transactions to bank accounts...")

        # [DOC] Only process transactions whose sender_account_id was never set
        transactions = db.query(Transaction).filter(
            Transaction.sender_account_id == None
        ).all()

        if not transactions:
            print("⚠️  No unlinked transactions found.")
        else:
            for tx in transactions:
                # [DOC] Resolve the sender's HDFC account (the default assigned in Step 3)
                # Find sender's HDFC account
                sender_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == tx.sender_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()

                # [DOC] Resolve the receiver's HDFC account
                # Find receiver's HDFC account
                receiver_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == tx.receiver_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()

                # [DOC] Only update the fields that were resolved; NULL stays if no account found
                if sender_account:
                    tx.sender_account_id = sender_account.id

                if receiver_account:
                    tx.receiver_account_id = receiver_account.id

                print(f"  ✅ Linked transaction {tx.transaction_hash[:16]}...")

            db.commit()
            print(f"\n✅ Linked {len(transactions)} transactions")

        # [DOC] Step 6: print final row counts to confirm the migration result
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)

        # [DOC] Count rows in each key table after all changes are committed
        total_users = db.query(User).count()
        total_accounts = db.query(BankAccount).count()
        total_sessions = db.query(UserSession).count()
        total_transactions = db.query(Transaction).count()

        print(f"\n📊 Statistics:")
        print(f"   Users: {total_users}")
        print(f"   Bank Accounts: {total_accounts}")
        print(f"   Sessions: {total_sessions}")
        print(f"   Transactions: {total_transactions}")

        print("\n✅ Migration completed successfully!")
        print("=" * 70)

    except Exception as e:
        # [DOC] Roll back any partial changes on failure so the DB remains consistent
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise

    finally:
        # [DOC] Always close the session regardless of success or failure
        db.close()


# [DOC] Script entry point: require explicit user confirmation before touching the database
if __name__ == "__main__":
    print("\n⚠️  WARNING: This will modify your database structure!")
    print("Make sure you have a backup before proceeding.\n")

    # [DOC] Input gate: user must type 'yes' to proceed — protects against accidental runs
    response = input("Continue with migration? (yes/no): ")

    if response.lower() == 'yes':
        # [DOC] Run the full migration when confirmed
        migrate_database()
    else:
        # [DOC] Print a cancellation notice and exit cleanly without touching the DB
        print("Migration cancelled.")
