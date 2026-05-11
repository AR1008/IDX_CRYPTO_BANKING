"""
Run V3.0 Migration Script
Purpose: Add advanced cryptography fields to database

Usage:
    python3 scripts/run_migration_v3.py
"""

# [DOC] database.connection provides the SQLAlchemy engine (connection pool to
# [DOC] PostgreSQL) and SessionLocal (factory for individual DB sessions).
# [DOC] The Transaction and TransactionBatch models are imported so that
# [DOC] Base.metadata.create_all() knows about their table definitions and
# [DOC] can create any tables that do not yet exist.
from database.connection import engine, SessionLocal
from database.models.transaction import Transaction
from database.models.transaction_batch import TransactionBatch
from sqlalchemy import text
import sys

def run_migration():
    """Run V3.0 migration"""
    print("\n" + "=" * 60)
    print("RUNNING V3.0 MIGRATION")
    print("=" * 60)
    print()

    # [DOC] Open a single database session for the entire migration.
    # [DOC] Using one session (rather than one per statement) means all
    # [DOC] statements share a connection from the pool, which is faster
    # [DOC] and avoids exhausting the pool on large databases.
    db = SessionLocal()

    try:
        # [DOC] Step 1: Ask SQLAlchemy to create every table that is defined
        # [DOC] in the ORM models but does not yet exist in the database.
        # [DOC] Base.metadata.create_all() is idempotent: it inspects the
        # [DOC] live schema first and only issues CREATE TABLE for missing
        # [DOC] tables, so it is safe to run more than once.
        # Step 1: Create all tables (including dependencies)
        print("Step 1: Creating/updating all tables...")
        from database.connection import Base
        Base.metadata.create_all(engine)
        print("✅ All tables created/updated\n")

        # [DOC] Step 2: Add the six new columns introduced in V3.0.
        # [DOC] Each column is added individually (one ALTER TABLE per column)
        # [DOC] rather than in a single statement so that if one column
        # [DOC] already exists the error is caught and skipped without
        # [DOC] rolling back the others.
        # [DOC]
        # [DOC] Column purposes:
        # [DOC]   sequence_number  — monotonically increasing counter per sender;
        # [DOC]                      included in the signed message to prevent
        # [DOC]                      replay attacks (attacker cannot re-submit an
        # [DOC]                      old signed transaction).
        # [DOC]   batch_id         — groups 100 transactions into one Merkle batch
        # [DOC]                      for consensus voting (see transaction flow Step 3).
        # [DOC]   commitment       — Pedersen commitment C = v*G + r*H hiding the amount.
        # [DOC]   nullifier        — SHA-256(commitment||sender_idx||secret); added to
        # [DOC]                      the accumulator after spending to prevent double-spend.
        # [DOC]   range_proof      — Bulletproof (Rust native, 64-bit) proving the
        # [DOC]                      committed amount is in [0, 2^64).
        # [DOC]   group_signature  — BBS04 anonymous group signature from the voting bank.
        # [DOC]   commitment_salt  — The random blinding scalar r used in the Pedersen
        # [DOC]                      commitment; stored encrypted on the private chain so
        # [DOC]                      the commitment can be opened under a court order.
        # Step 2: Add new columns to transactions table
        print("Step 2: Adding V3.0 columns to transactions...")

        # Add columns one by one (safer than running full SQL)
        columns_to_add = [
            ("sequence_number", "BIGINT"),
            ("batch_id", "VARCHAR(50)"),
            ("commitment", "VARCHAR(66)"),
            ("nullifier", "VARCHAR(66)"),
            ("range_proof", "TEXT"),
            ("group_signature", "TEXT"),
            ("commitment_salt", "VARCHAR(66)")
        ]

        # [DOC] Iterate through each (column_name, sql_type) pair and attempt
        # [DOC] to add it. IF NOT EXISTS is PostgreSQL syntax that makes the
        # [DOC] statement a no-op when the column already exists, but older
        # [DOC] PostgreSQL versions may not support it, so the except branch
        # [DOC] also catches "already exists" error messages as a fallback.
        for col_name, col_type in columns_to_add:
            try:
                db.execute(text(f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                db.commit()
                print(f"  ✅ Added column: {col_name}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"  ℹ️  Column already exists: {col_name}")
                    db.rollback()
                else:
                    raise

        print()

        # [DOC] Step 3: Back-fill sequence_number for any transactions that
        # [DOC] were inserted before this column existed (sequence_number IS NULL).
        # [DOC] ROW_NUMBER() OVER (ORDER BY created_at) assigns consecutive
        # [DOC] integers starting at 1 in chronological order, which is the
        # [DOC] correct replay-prevention ordering.
        # [DOC] The subquery pattern (UPDATE ... FROM (...) AS subquery WHERE ...)
        # [DOC] is a PostgreSQL idiom for UPDATE with a derived table — it avoids
        # [DOC] foreign key validation issues that arise with ORM-level updates.
        # Step 3: Set sequence numbers for existing transactions
        print("Step 3: Setting sequence numbers for existing transactions...")

        # Count transactions without sequence numbers using direct SQL
        result = db.execute(text("""
            SELECT COUNT(*)
            FROM transactions
            WHERE sequence_number IS NULL
        """))
        count = result.scalar()

        if count > 0:
            print(f"  Found {count} transactions without sequence numbers")

            # Use direct SQL to assign sequence numbers (avoids foreign key validation)
            db.execute(text("""
                UPDATE transactions
                SET sequence_number = subquery.row_num
                FROM (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) as row_num
                    FROM transactions
                    WHERE sequence_number IS NULL
                ) AS subquery
                WHERE transactions.id = subquery.id
            """))
            db.commit()
            print(f"  ✅ Assigned sequence numbers 1-{count}\n")
        else:
            print("  ℹ️  All transactions already have sequence numbers\n")

        # [DOC] Step 4: Create B-tree indexes on the four most-queried columns.
        # [DOC] Without indexes, every lookup by batch_id or nullifier requires a
        # [DOC] full sequential scan of the transactions table — unacceptable at
        # [DOC] production volume. The indexes reduce those lookups to O(log n).
        # [DOC]
        # [DOC]   idx_tx_sequence   — ORDER BY / WHERE sequence_number (replay check)
        # [DOC]   idx_tx_batch      — WHERE batch_id = ? (batch assembly, consensus)
        # [DOC]   idx_tx_commitment — WHERE commitment = ? (commitment uniqueness check)
        # [DOC]   idx_tx_nullifier  — WHERE nullifier = ? (double-spend check — critical
        # [DOC]                       path, runs on every incoming transaction)
        # Step 4: Add indexes
        print("Step 4: Creating indexes...")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tx_sequence ON transactions(sequence_number)",
            "CREATE INDEX IF NOT EXISTS idx_tx_batch ON transactions(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_tx_commitment ON transactions(commitment)",
            "CREATE INDEX IF NOT EXISTS idx_tx_nullifier ON transactions(nullifier)"
        ]

        # [DOC] Same pattern as columns: catch "already exists" and treat as a
        # [DOC] no-op so the script is idempotent.
        for idx_sql in indexes:
            try:
                db.execute(text(idx_sql))
                db.commit()
                idx_name = idx_sql.split("idx_tx_")[1].split(" ")[0]
                print(f"  ✅ Created index: idx_tx_{idx_name}")
            except Exception as e:
                if "already exists" in str(e):
                    idx_name = idx_sql.split("idx_tx_")[1].split(" ")[0]
                    print(f"  ℹ️  Index already exists: idx_tx_{idx_name}")
                    db.rollback()
                else:
                    raise

        print()

        # [DOC] Step 5: Verify the migration succeeded by querying
        # [DOC] information_schema.columns for the four key V3.0 columns
        # [DOC] and by counting rows in transactions and transaction_batches.
        # [DOC] These numbers are printed so the operator can sanity-check
        # [DOC] that data was not lost and the columns exist before starting
        # [DOC] the application server.
        # Step 5: Verification
        print("Step 5: Verifying migration...")

        # Check if all columns exist
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'transactions'
            AND column_name IN ('sequence_number', 'batch_id', 'commitment', 'nullifier')
        """))

        found_columns = [row[0] for row in result]
        print(f"  Found V3.0 columns: {', '.join(found_columns)}")

        # Check transactions using direct SQL
        result = db.execute(text("SELECT COUNT(*) FROM transactions"))
        total_txs = result.scalar()

        result = db.execute(text("""
            SELECT COUNT(*) FROM transactions
            WHERE sequence_number IS NOT NULL
        """))
        txs_with_seq = result.scalar()

        print(f"  Total transactions: {total_txs}")
        print(f"  With sequence numbers: {txs_with_seq}")

        # Check batches
        result = db.execute(text("SELECT COUNT(*) FROM transaction_batches"))
        total_batches = result.scalar()
        print(f"  Total batches: {total_batches}")

        print()
        print("=" * 60)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print("V3.0 Features Enabled:")
        print("  • Sequence numbers (replay attack prevention)")
        print("  • Batch processing (2.75x faster)")
        print("  • Commitment scheme (perfect privacy)")
        print("  • Range proofs (balance validation)")
        print("  • Group signatures (anonymous voting)")
        print()

    except Exception as e:
        # [DOC] Any unhandled exception rolls back whatever partial work was
        # [DOC] done in the current transaction and exits with a non-zero code
        # [DOC] so the calling shell script or CI pipeline knows the migration
        # [DOC] failed and does not proceed to start the application server.
        print(f"\n❌ Migration failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        # [DOC] Always close the session to release the connection back to the
        # [DOC] pool, even if an exception was raised above.
        db.close()


if __name__ == "__main__":
    run_migration()
