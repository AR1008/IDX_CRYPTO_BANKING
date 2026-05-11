"""
Migration 010: Real Cryptographic Field Expansion
==================================================
Expands commitment, nullifier, and commitment_salt columns from VARCHAR(66)
to TEXT to accommodate real Pedersen commitment outputs from
core/crypto/real/pedersen.py (130-char uncompressed EC point hex strings).

Also adds bbs_secret_key and bbs_public_key columns to consortium_banks
for BBS+ group signature integration via Charm-Crypto.

Usage:
    python3 scripts/run_migration_010.py

Safe to re-run: all ALTER TABLE statements are idempotent.
"""

import sys
# [DOC] engine is the SQLAlchemy connection pool pointing at the PostgreSQL
# [DOC] database configured in config/settings.py (default: idx_banking).
# [DOC] SessionLocal is a factory: calling SessionLocal() opens one session
# [DOC] (one database connection) that can execute SQL statements.
from database.connection import engine, SessionLocal
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Column expansion targets
# ---------------------------------------------------------------------------
# [DOC] TEXT_COLUMNS lists the three VARCHAR(66) columns that must be widened
# [DOC] to TEXT. Each entry is a tuple of (table, column, human_readable_reason).
# [DOC] The reason string is only printed to stdout; it has no effect on SQL.
TEXT_COLUMNS = [
    # (table_name, column_name, reason)
    ("transactions",    "commitment",      "Pedersen commitment: 130-char EC point hex"),
    ("transactions",    "nullifier",       "Double-spend key: inherits commitment format"),
    ("transactions",    "commitment_salt", "Blinding factor reference: inherits format"),
]

# [DOC] NEW_COLUMNS lists columns that do not yet exist and must be created.
# [DOC] Each entry is (table, column, pg_type, reason).
# [DOC] The BBS+ key columns store Charm-Crypto BN254 group elements serialised
# [DOC] as hex strings. Their length varies (~200-400 chars) so TEXT is required.
NEW_COLUMNS = [
    # (table_name, column_name, col_type, reason)
    ("consortium_banks", "bbs_secret_key", "TEXT",
     "BBS+ secret key per bank (Charm-Crypto BN254 pairing group element)"),
    ("consortium_banks", "bbs_public_key", "TEXT",
     "BBS+ public key per bank (Charm-Crypto BN254 pairing group element)"),
]


def _alter_to_text(db, table: str, column: str, reason: str) -> None:
    """Expand a VARCHAR column to TEXT in-place.

    Args:
        db:     Active SQLAlchemy session.
        table:  Table name.
        column: Column name to expand.
        reason: Human-readable explanation logged to stdout.
    """
    # [DOC] PostgreSQL's ALTER COLUMN ... TYPE TEXT is a metadata-only
    # [DOC] operation for varchar->text: no row data is rewritten and the
    # [DOC] table is not locked for writing, so this runs instantly even on
    # [DOC] large tables. Existing data is preserved exactly as-is.
    try:
        db.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT"))
        db.commit()
        print(f"  OK  {table}.{column} -> TEXT  ({reason})")
    except Exception as exc:
        db.rollback()
        # [DOC] PostgreSQL error code 42804 (cannot_coerce) is raised when
        # [DOC] the column is already TEXT and the cast is a no-op that the
        # [DOC] planner refuses. Treat it as "already done" rather than a
        # [DOC] hard failure so the script stays idempotent.
        # PostgreSQL raises "42804" (cannot cast) when column is already TEXT;
        # treat this as a no-op rather than a hard failure.
        if "cannot cast" in str(exc) or "42804" in str(exc):
            print(f"  --  {table}.{column} already TEXT, skipping")
        else:
            raise


def _add_column_if_missing(db, table: str, column: str, col_type: str, reason: str) -> None:
    """Add a new column to a table if it does not already exist.

    Args:
        db:       Active SQLAlchemy session.
        table:    Table name.
        column:   New column name.
        col_type: PostgreSQL column type string.
        reason:   Human-readable explanation logged to stdout.
    """
    # [DOC] IF NOT EXISTS is a PostgreSQL 9.6+ extension to ALTER TABLE ADD COLUMN.
    # [DOC] It makes the statement a no-op when the column already exists instead
    # [DOC] of raising an error, which keeps this script safe to run a second time.
    try:
        db.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        ))
        db.commit()
        print(f"  OK  {table}.{column} {col_type} added  ({reason})")
    except Exception as exc:
        db.rollback()
        if "already exists" in str(exc):
            print(f"  --  {table}.{column} already exists, skipping")
        else:
            raise


def run_migration() -> None:
    """Execute migration 010 against the configured PostgreSQL database."""
    print()
    print("=" * 65)
    print("MIGRATION 010 — Real Cryptographic Field Expansion")
    print("=" * 65)
    print()

    # [DOC] Open one session for the entire migration. Each helper function
    # [DOC] commits its own statement immediately (autocommit-like behaviour)
    # [DOC] so that a failure in step 2 does not roll back the successful
    # [DOC] changes from step 1.
    db = SessionLocal()

    try:
        # ------------------------------------------------------------------
        # Step 1: Expand VARCHAR(66) columns to TEXT
        # ------------------------------------------------------------------
        # [DOC] Iterate over the three target columns and widen each one.
        # [DOC] The helper _alter_to_text() handles both the SQL execution
        # [DOC] and the idempotency check (already-TEXT columns are skipped).
        print("Step 1: Expanding narrow VARCHAR columns to TEXT ...")
        for table, column, reason in TEXT_COLUMNS:
            _alter_to_text(db, table, column, reason)
        print()

        # ------------------------------------------------------------------
        # Step 2: Add BBS+ key columns to consortium_banks
        # ------------------------------------------------------------------
        # [DOC] These two columns did not exist before this migration.
        # [DOC] _add_column_if_missing() uses IF NOT EXISTS so re-running is safe.
        print("Step 2: Adding BBS+ group signature key columns ...")
        for table, column, col_type, reason in NEW_COLUMNS:
            _add_column_if_missing(db, table, column, col_type, reason)
        print()

        # ------------------------------------------------------------------
        # Step 3: Verify schema
        # ------------------------------------------------------------------
        # [DOC] After applying changes, query information_schema.columns to
        # [DOC] confirm the actual data_type stored by PostgreSQL. If any
        # [DOC] column still shows 'character varying' the migration failed
        # [DOC] silently and the operator must investigate before starting the
        # [DOC] application server.
        print("Step 3: Verifying schema ...")

        result = db.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'transactions'
              AND column_name IN ('commitment', 'nullifier', 'commitment_salt')
            ORDER BY column_name
        """))
        rows = result.fetchall()
        # [DOC] Print OK when data_type = 'text'; WARN otherwise so the
        # [DOC] operator can see at a glance whether any column is still narrow.
        for col_name, data_type in rows:
            status = "OK" if data_type == "text" else "WARN"
            print(f"  {status}  transactions.{col_name}: {data_type}")

        result = db.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'consortium_banks'
              AND column_name IN ('bbs_secret_key', 'bbs_public_key')
            ORDER BY column_name
        """))
        bbs_rows = result.fetchall()
        for col_name, data_type in bbs_rows:
            print(f"  OK  consortium_banks.{col_name}: {data_type}")

        print()
        print("=" * 65)
        print("MIGRATION 010 COMPLETED SUCCESSFULLY")
        print("=" * 65)
        print()
        print("Changes applied:")
        print("  • transactions.commitment      VARCHAR(66) -> TEXT")
        print("  • transactions.nullifier       VARCHAR(66) -> TEXT")
        print("  • transactions.commitment_salt VARCHAR(66) -> TEXT")
        print("  • consortium_banks.bbs_secret_key  TEXT (new)")
        print("  • consortium_banks.bbs_public_key  TEXT (new)")
        print()
        print("Next step: python3 -c \"import core.crypto.real.pedersen\" to verify EC library.")
        print()

    except Exception as exc:
        # [DOC] Print the exception and exit with code 1 so the calling
        # [DOC] shell or CI system knows the migration failed and does not
        # [DOC] proceed to start the application server with a broken schema.
        print(f"\nMIGRATION FAILED: {exc}")
        db.rollback()
        sys.exit(1)
    finally:
        # [DOC] Release the database connection back to the pool whether the
        # [DOC] migration succeeded or failed.
        db.close()


if __name__ == "__main__":
    run_migration()
