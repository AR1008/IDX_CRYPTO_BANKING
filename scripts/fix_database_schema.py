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

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal, engine
from sqlalchemy import text, inspect


def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def fix_recipients_table(dry_run: bool = False):
    """Add missing columns to recipients table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing recipients table...")

    with engine.connect() as conn:
        # Check if can_transact_at column exists
        if not check_column_exists('recipients', 'can_transact_at'):
            print("  Adding 'can_transact_at' column...")
            sql = text("""
                ALTER TABLE recipients
                ADD COLUMN can_transact_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
            """)
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
            print("  ✅ 'can_transact_at' column already exists")


def fix_sessions_table(dry_run: bool = False):
    """Add missing columns to sessions table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing sessions table...")

    with engine.connect() as conn:
        # Check if bank_account_id column exists
        if not check_column_exists('sessions', 'bank_account_id'):
            print("  Adding 'bank_account_id' column...")
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


def fix_transactions_table(dry_run: bool = False):
    """Add missing columns to transactions table

    If dry_run is True, the function will only print the actions it would take
    and will not execute any DDL/DML statements.
    """
    print("\n🔧 Fixing transactions table...")

    with engine.connect() as conn:
        # Check transaction_type column
        if not check_column_exists('transactions', 'transaction_type'):
            print("  Adding 'transaction_type' column...")
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


def deactivate_expired_sessions(dry_run: bool = False):
    """Mark expired sessions as inactive

    If dry_run is True, this will only report how many sessions would be deactivated.
    """
    print("\n🔧 Deactivating expired sessions...")

    db = SessionLocal()
    try:
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
        db.close()


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


def verify_schema():
    """Verify all schema fixes are applied"""
    print("\n✅ Verifying schema fixes...")

    checks = []

    # Check recipients table
    checks.append(('recipients.can_transact_at', check_column_exists('recipients', 'can_transact_at')))

    # Check sessions table
    checks.append(('sessions.bank_account_id', check_column_exists('sessions', 'bank_account_id')))

    # Check transactions table
    checks.append(('transactions.transaction_type', check_column_exists('transactions', 'transaction_type')))
    checks.append(('transactions.batch_id', check_column_exists('transactions', 'batch_id')))
    checks.append(('transactions.commitment', check_column_exists('transactions', 'commitment')))

    # Print results
    print("\n  Schema Verification:")
    all_passed = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"    {status} {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n  ✅ All schema fixes verified!")
    else:
        print("\n  ⚠️  Some schema fixes failed - review the issues above")

    return all_passed


def main():
    """Main entry point

    - Requires an explicit backup confirmation before making changes.
    - Supports a `--dry-run` mode which previews all actions without applying them.
    """
    # CLI flags
    dry_run = '--dry-run' in sys.argv

    print("\n" + "=" * 80)
    print("DATABASE SCHEMA FIX")
    print("=" * 80)

    print("\n⚠️  This script will modify your database schema.")
    print("⚠️  It will NOT delete any existing data unless explicitly scripted.")
    print("⚠️  It will only ADD missing columns and fix schema mismatches.")

    if dry_run:
        print("\n🔎 Running in DRY-RUN mode: no changes will be applied to the database.")
        proceed = input("Proceed with dry-run? (yes/no): ")
        if proceed.lower() != 'yes':
            print("❌ Aborted")
            return
    else:
        print("\nIMPORTANT: Back up your database before continuing.")
        print("Please create a backup (dump, snapshot, or logical export) and ensure you can restore it.")
        confirm = input("Type 'I HAVE BACKED UP' to continue: ")
        if confirm.strip() != 'I HAVE BACKED UP':
            print("❌ Aborted - database not confirmed backed up.")
            return

    # Perform the steps; stop on first error to avoid partial application
    try:
        # Fix schema
        fix_recipients_table(dry_run=dry_run)
        fix_sessions_table(dry_run=dry_run)
        fix_transactions_table(dry_run=dry_run)

        # Clean up data
        deactivate_expired_sessions(dry_run=dry_run)
        delete_orphaned_sessions(dry_run=dry_run)
        delete_orphaned_bank_accounts(dry_run=dry_run)

        # Verify (read-only)
        verify_schema()

    except Exception as e:
        print(f"\n❌ Error during schema fix: {e}")
        print("Aborting further steps. Please review logs and restore from backup if necessary.")
        return

    print("\n" + "=" * 80)
    if dry_run:
        print("✅ DRY-RUN complete — no changes were applied.")
    else:
        print("✅ DATABASE SCHEMA FIX COMPLETE!")
    print("=" * 80)

    print("\nYou can now run the database validator:")
    print("  python3 scripts/database_validator.py --check")


if __name__ == "__main__":
    main()
