"""
Add New Transaction Statuses
Purpose: Add AWAITING_RECEIVER and REJECTED to transaction status enum
"""

# [DOC] Add the project root to Python's module search path so we can import from database/.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# [DOC] engine is the SQLAlchemy connection pool — used to run raw SQL when ORM is not needed.
from database.connection import engine
# [DOC] text() wraps a raw SQL string so SQLAlchemy can execute it safely.
from sqlalchemy import text


# [DOC] Adds the AWAITING_RECEIVER and REJECTED values to PostgreSQL's transactionstatus enum type.
# [DOC] PostgreSQL enums must be explicitly extended with ALTER TYPE; you cannot add values via ORM alone.
def add_enum_values():
    """Add new values to transactionstatus enum"""

    print("=" * 70)
    print("ADDING NEW TRANSACTION STATUSES")
    print("=" * 70)

    with engine.connect() as conn:
        # [DOC] Query pg_enum (PostgreSQL's internal catalog) to get the current values of the enum.
        # [DOC] pg_type.oid links the enum type name to its list of labels in pg_enum.
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (
                SELECT oid
                FROM pg_type
                WHERE typname = 'transactionstatus'
            )
        """))

        existing_values = [row[0] for row in result]
        print(f"\nExisting values: {existing_values}\n")

        # [DOC] AWAITING_RECEIVER: set when sender creates a transaction but receiver hasn't confirmed yet.
        if 'AWAITING_RECEIVER' not in existing_values:
            print("Adding 'AWAITING_RECEIVER'...")
            conn.execute(text("""
                ALTER TYPE transactionstatus ADD VALUE 'AWAITING_RECEIVER'
            """))
            conn.commit()
            print("✅ Added 'awaiting_receiver'")
        else:
            print("⏭️  'awaiting_receiver' already exists")

        # [DOC] REJECTED: set if the receiver declines the transaction or consensus fails.
        if 'REJECTED' not in existing_values:
            print("Adding 'REJECTED'...")
            conn.execute(text("""
                ALTER TYPE transactionstatus ADD VALUE 'REJECTED'
            """))
        else:
            print("⏭️  'rejected' already exists")

        # [DOC] Re-query the catalog after ALTER TYPE to confirm both values are now present.
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (
                SELECT oid
                FROM pg_type
                WHERE typname = 'transactionstatus'
            )
            ORDER BY enumlabel
        """))

        all_values = [row[0] for row in result]
        print(f"\n✅ All enum values: {all_values}")
        print("\n" + "=" * 70)
        print("MIGRATION COMPLETE")
        print("=" * 70)


if __name__ == "__main__":
    add_enum_values()