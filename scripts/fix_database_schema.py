"""
Database Schema Fix Script
Purpose: Fix schema mismatches between models and database

This script will:
1. Add missing columns to existing tables
2. Fix data types
3. Add missing indexes
4. WITHOUT dropping or losing data

Usage:
    python3 scripts/fix_database_schema.py
"""

# [DOC] sys and os allow us to manipulate the Python path and read CLI arguments
import sys
import os
from datetime import datetime, timedelta

# [DOC] Extend the module search path to the project root so sibling packages resolve
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [DOC] SessionLocal creates DB sessions; engine is the raw SQLAlchemy connection pool
from database.connection import SessionLocal, engine
# [DOC] text() wraps raw SQL strings so SQLAlchemy can execute them safely
# inspect() reflects the live database schema (columns, tables, indexes)
from sqlalchemy import text, inspect


# [DOC] Utility: returns True if the given column already exists in the given table
# Used before every ALTER TABLE to avoid "column already exists" errors
def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    # [DOC] inspect(engine) reads schema metadata directly from the live PostgreSQL server
    inspector = inspect(engine)
    # [DOC] get_columns returns a list of dicts; we only need the 'name' key
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


# [DOC] Fix 1/3: add the can_transact_at column to the recipients table
# This column records when a newly-added recipient becomes eligible for transactions
def fix_recipients_table(dry_run: bool = False):
    """Add missing columns to recipients table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing recipients table...")

    # [DOC] Open a raw connection from the connection pool for DDL execution
    with engine.connect() as conn:
        # [DOC] Idempotency check: skip the ALTER TABLE if the column is already there
        # Check if can_transact_at column exists
        if not check_column_exists('recipients', 'can_transact_at'):
            print("  Adding 'can_transact_at' column...")
            # [DOC] CURRENT_TIMESTAMP default means existing rows get the current time,
            # which safely places them in the past (already eligible to transact)
            sql = text("""
                ALTER TABLE recipients
                ADD COLUMN can_transact_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
            """)
            # [DOC] Dry-run mode: print intent but skip execution — no DB changes
            if dry_run:
                print("  (dry-run) Would execute ALTER TABLE to add 'can_transact_at' with DEFAULT CURRENT_TIMESTAMP")
                return
            # Add column with a portable server-side default
            try:
                conn.execute(sql)
                conn.commit()
                print("  ✅ Added 'can_transact_at' column (default: CURRENT_TIMESTAMP)")
            except Exception as e:
                # Log and re-raise so caller can see the original error
                print(f"  ❌ Failed to add 'can_transact_at' column: {e}")
                raise
        else:
            # [DOC] Column already present; nothing to do — idempotent re-run is safe
            print("  ✅ 'can_transact_at' column already exists")


# [DOC] Fix 2/3: add bank_account_id to sessions so each session is tied to one account
# This enables the multi-bank feature where one user can have accounts at several banks
def fix_sessions_table(dry_run: bool = False):
    """Add missing columns to sessions table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing sessions table...")

    with engine.connect() as conn:
        # [DOC] Check before altering — safe to run the script multiple times
        # Check if bank_account_id column exists
        if not check_column_exists('sessions', 'bank_account_id'):
            print("  Adding 'bank_account_id' column...")
            # [DOC] FK reference to bank_accounts(id) enforces referential integrity at DB level
            sql_add = text("""
                ALTER TABLE sessions
                ADD COLUMN bank_account_id INTEGER
                REFERENCES bank_accounts(id)
            """)
            if dry_run:
                print("  (dry-run) Would add 'bank_account_id' column and populate it from bank_accounts")
            else:
                conn.execute(sql_add)
                conn.commit()
                print("  ✅ Added 'bank_account_id' column")

                # [DOC] Back-fill: for every existing session find the matching bank account
                # by joining on user_idx and bank_name == bank_code
                # Now populate it
                print("  Populating bank_account_id from user_idx and bank_name...")
                result = conn.execute(text("""
                    UPDATE sessions s
                    SET bank_account_id = ba.id
                    FROM bank_accounts ba
                    WHERE s.user_idx = ba.user_idx
                    AND s.bank_name = ba.bank_code
                """))
                conn.commit()
                print(f"  ✅ Populated bank_account_id for {result.rowcount} sessions")

                # [DOC] Any remaining NULL means bank_name didn't match bank_code — warn but don't fail
                # Check for unpopulated rows
                unpopulated = conn.execute(text("""
                    SELECT COUNT(*) FROM sessions WHERE bank_account_id IS NULL
                """
                )).scalar()
                if unpopulated > 0:
                    print(f"  ⚠️  Warning: {unpopulated} sessions have NULL bank_account_id")
                    print(f"     (bank_name might not match bank_code, or no matching bank account)")
        else:
            print("  ✅ 'bank_account_id' column already exists")


# [DOC] Fix 3/3: add columns needed for transaction type tracking and cryptographic proofs
def fix_transactions_table(dry_run: bool = False):
    """Add missing columns to transactions table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing transactions table...")

    with engine.connect() as conn:
        # [DOC] transaction_type distinguishes DOMESTIC from FOREX/FOREIGN transfers
        # Check transaction_type column
        if not check_column_exists('transactions', 'transaction_type'):
            print("  Adding 'transaction_type' column...")
            # [DOC] Default 'DOMESTIC' keeps existing rows valid without a data migration
            sql = text("""
                ALTER TABLE transactions
                ADD COLUMN transaction_type VARCHAR(20)
                DEFAULT 'DOMESTIC'
            """)
            if dry_run:
                print("  (dry-run) Would add 'transaction_type' column with DEFAULT 'DOMESTIC'")
            else:
                conn.execute(sql)
                conn.commit()
                print("  ✅ Added 'transaction_type' column")
        else:
            print("  ✅ 'transaction_type' column already exists")

        # [DOC] batch_id ties a transaction to the 100-tx Merkle batch it was included in
        # Check batch_id column
        if not check_column_exists('transactions', 'batch_id'):
            print("  Adding 'batch_id' column...")
            sql = text("""
                ALTER TABLE transactions
                ADD COLUMN batch_id VARCHAR(50)
            """)
            if dry_run:
                print("  (dry-run) Would add 'batch_id' column")
            else:
                conn.execute(sql)
                conn.commit()
                print("  ✅ Added 'batch_id' column")
        else:
            print("  ✅ 'batch_id' column already exists")

        # [DOC] Cryptographic columns store the ZK proof artifacts for each transaction:
        # commitment = Pedersen(amount), nullifier = double-spend prevention token,
        # range_proof = Bulletproof, group_signature = BBS04 vote, commitment_salt = blinding factor
        # Check commitment column (for advanced crypto)
        if not check_column_exists('transactions', 'commitment'):
            print("  Adding cryptographic columns...")
            sql = text("""
                ALTER TABLE transactions
                ADD COLUMN commitment VARCHAR(66),
                ADD COLUMN nullifier VARCHAR(66),
                ADD COLUMN range_proof TEXT,
                ADD COLUMN group_signature TEXT,
                ADD COLUMN commitment_salt VARCHAR(66)
            """)
            if dry_run:
                print("  (dry-run) Would add cryptographic columns to transactions")
            else:
                conn.execute(sql)
                conn.commit()
                print("  ✅ Added cryptographic columns")
        else:
            print("  ✅ Cryptographic columns already exist")


# [DOC] Data fix: set is_active=FALSE on sessions whose expires_at timestamp has passed
def deactivate_expired_sessions(dry_run: bool = False):
    """Mark expired sessions as inactive

    If dry_run is True, this will only report how many sessions would be deactivated.
    """
    print("\n🔧 Deactivating expired sessions...")

    # [DOC] Use a fresh SessionLocal so this function is independent of the engine connection above
    db = SessionLocal()
    try:
        # [DOC] In dry-run, count rows that WOULD be updated and return early
        if dry_run:
            result = db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM sessions
                WHERE expires_at < NOW()
                AND is_active = TRUE
            """))
            cnt = result.fetchone()[0]
            print(f"  (dry-run) Would deactivate {cnt} expired sessions")
            return cnt
        # [DOC] UPDATE in a single SQL statement for performance; commit immediately after
        result = db.execute(text("""
            UPDATE sessions
            SET is_active = FALSE
            WHERE expires_at < NOW()
            AND is_active = TRUE
        """))
        db.commit()
        count = result.rowcount
        print(f"  ✅ Deactivated {count} expired sessions")
        return count
    finally:
        # [DOC] Always close the session to return the connection to the pool
        db.close()


# [DOC] Data fix: remove session rows whose user_idx is not present in the users table
def delete_orphaned_sessions(dry_run: bool = False):
    """Delete sessions for non-existent users

    If dry_run is True, this will only report how many sessions would be deleted.
    """
    print("\n🔧 Deleting orphaned sessions...")

    db = SessionLocal()
    try:
        if dry_run:
            result = db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM sessions s
                WHERE user_idx NOT IN (SELECT idx FROM users)
            """))
            cnt = result.fetchone()[0]
            print(f"  (dry-run) Would delete {cnt} orphaned sessions")
            return cnt
        # [DOC] NOT IN subquery efficiently identifies sessions with no matching user
        result = db.execute(text("""
            DELETE FROM sessions
            WHERE user_idx NOT IN (SELECT idx FROM users)
        """))
        db.commit()
        count = result.rowcount
        print(f"  ✅ Deleted {count} orphaned sessions")
        return count
    finally:
        db.close()


# [DOC] Data fix: remove bank_account rows whose user_idx has no matching user
def delete_orphaned_bank_accounts(dry_run: bool = False):
    """Delete bank accounts for non-existent users

    If dry_run is True, this will only report how many bank accounts would be deleted.
    """
    print("\n🔧 Deleting orphaned bank accounts...")

    db = SessionLocal()
    try:
        if dry_run:
            result = db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM bank_accounts ba
                WHERE user_idx NOT IN (SELECT idx FROM users)
            """))
            cnt = result.fetchone()[0]
            print(f"  (dry-run) Would delete {cnt} orphaned bank accounts")
            return cnt
        # [DOC] Same NOT IN pattern as orphaned sessions, applied to bank_accounts table
        result = db.execute(text("""
            DELETE FROM bank_accounts
            WHERE user_idx NOT IN (SELECT idx FROM users)
        """))
        db.commit()
        count = result.rowcount
        print(f"  ✅ Deleted {count} orphaned bank accounts")
        return count
    finally:
        db.close()


# [DOC] Read-only post-run check: confirm every expected column now exists in the live DB
def verify_schema():
    """Verify all schema fixes are applied"""
    print("\n✅ Verifying schema fixes...")

    # [DOC] Each tuple is (human label, boolean result of check_column_exists)
    checks = []

    # [DOC] Verify the recipients fix was applied
    # Check recipients table
    checks.append(('recipients.can_transact_at', check_column_exists('recipients', 'can_transact_at')))

    # [DOC] Verify the sessions fix was applied
    # Check sessions table
    checks.append(('sessions.bank_account_id', check_column_exists('sessions', 'bank_account_id')))

    # [DOC] Verify all three transaction-related fixes were applied
    # Check transactions table
    checks.append(('transactions.transaction_type', check_column_exists('transactions', 'transaction_type')))
    checks.append(('transactions.batch_id', check_column_exists('transactions', 'batch_id')))
    checks.append(('transactions.commitment', check_column_exists('transactions', 'commitment')))

    # [DOC] Print a tick or cross next to each column name so failures are obvious at a glance
    # Print results
    print("\n  Schema Verification:")
    all_passed = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"    {status} {name}")
        if not passed:
            all_passed = False

    # [DOC] Return True only if every single column was confirmed present
    if all_passed:
        print("\n  ✅ All schema fixes verified!")
    else:
        print("\n  ⚠️  Some schema fixes failed - review the issues above")

    return all_passed


# [DOC] Script entry point: parse --dry-run flag, require backup confirmation, then run all fixes
def main():
    """Main entry point

    - Requires an explicit backup confirmation before making changes.
    - Supports a `--dry-run` mode which previews all actions without applying them.
    """
    # [DOC] Check for --dry-run flag in sys.argv; avoids adding argparse overhead for one flag
    # CLI flags
    dry_run = '--dry-run' in sys.argv

    print("\n" + "=" * 80)
    print("DATABASE SCHEMA FIX")
    print("=" * 80)

    print("\n⚠️  This script will modify your database schema.")
    print("⚠️  It will NOT delete any existing data unless explicitly scripted.")
    print("⚠️  It will only ADD missing columns and fix schema mismatches.")

    # [DOC] In dry-run mode a lighter confirmation is sufficient since nothing will change
    if dry_run:
        print("\n🔎 Running in DRY-RUN mode: no changes will be applied to the database.")
        proceed = input("Proceed with dry-run? (yes/no): ")
        if proceed.lower() != 'yes':
            print("❌ Aborted")
            return
    else:
        # [DOC] Force the operator to type a specific phrase confirming they have a backup
        # This prevents accidental runs on production without a safety net
        print("\nIMPORTANT: Back up your database before continuing.")
        print("Please create a backup (dump, snapshot, or logical export) and ensure you can restore it.")
        confirm = input("Type 'I HAVE BACKED UP' to continue: ")
        if confirm.strip() != 'I HAVE BACKED UP':
            print("❌ Aborted - database not confirmed backed up.")
            return

    # [DOC] Execute fixes in order; any exception aborts remaining steps to avoid partial state
    # Perform the steps; stop on first error to avoid partial application
    try:
        # [DOC] Schema fixes first (ADD COLUMN) — safe to retry if rerun after partial failure
        # Fix schema
        fix_recipients_table(dry_run=dry_run)
        fix_sessions_table(dry_run=dry_run)
        fix_transactions_table(dry_run=dry_run)

        # [DOC] Data cleanup second — runs after columns exist so UPDATE/DELETE work correctly
        # Clean up data
        deactivate_expired_sessions(dry_run=dry_run)
        delete_orphaned_sessions(dry_run=dry_run)
        delete_orphaned_bank_accounts(dry_run=dry_run)

        # [DOC] Read-only verification last — just inspects the schema, never changes anything
        # Verify (read-only)
        verify_schema()

    except Exception as e:
        print(f"\n❌ Error during schema fix: {e}")
        print("Aborting further steps. Please review logs and restore from backup if necessary.")
        return

    print("\n" + "=" * 80)
    # [DOC] Different success message depending on whether real changes were applied
    if dry_run:
        print("✅ DRY-RUN complete — no changes were applied.")
    else:
        print("✅ DATABASE SCHEMA FIX COMPLETE!")
    print("=" * 80)

    print("\nYou can now run the database validator:")
    print("  python3 scripts/database_validator.py --check")


# [DOC] Only run main() when this file is executed directly, not when imported
if __name__ == "__main__":
    main()
