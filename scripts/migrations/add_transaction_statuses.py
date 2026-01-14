"""
Add New Transaction Statuses
Purpose: Add AWAITING_RECEIVER and REJECTED to transaction status enum
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.connection import engine
from sqlalchemy import text


def add_enum_values():
    """Add new values to transactionstatus enum"""
    
    print("=" * 70)
    print("ADDING NEW TRANSACTION STATUSES")
    print("=" * 70)
    
    with engine.connect() as conn:
        # Check if values already exist
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
        
        # Add AWAITING_RECEIVER if not exists
        if 'AWAITING_RECEIVER' not in existing_values:
            print("Adding 'AWAITING_RECEIVER'...")
            conn.execute(text("""
                ALTER TYPE transactionstatus ADD VALUE 'AWAITING_RECEIVER'
            """))
            conn.commit()
            print("✅ Added 'awaiting_receiver'")
        else:
            print("⏭️  'awaiting_receiver' already exists")
        
        # Add REJECTED if not exists
        if 'REJECTED' not in existing_values:
            print("Adding 'REJECTED'...")
            conn.execute(text("""
                ALTER TYPE transactionstatus ADD VALUE 'REJECTED'
            """))
        else:
            print("⏭️  'rejected' already exists")
        
        # Verify
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