"""
Database Migration: Multi-Bank Support
Author: Ashutosh Rajesh
Purpose: Add support for multiple bank accounts per user

Changes:
1. Create bank_accounts table
2. Create recipients table
3. ALTER sessions table (add bank_account_id column)
4. ALTER transactions table (add sender_account_id, receiver_account_id columns)
5. Migrate existing data
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from decimal import Decimal
from database.connection import SessionLocal, engine, Base
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.recipient import Recipient
from database.models.transaction import Transaction, TransactionStatus
from database.models.session import Session as UserSession
from sqlalchemy import text
import random


def generate_account_number(bank_code, user_idx):
    """Generate unique bank account number"""
    idx_part = user_idx[-8:]
    random_part = str(random.randint(1000, 9999))
    return f"{bank_code}{idx_part}{random_part}"


def column_exists(engine, table_name, column_name):
    """Check if column exists in table"""
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='{table_name}' 
            AND column_name='{column_name}'
        """))
        return result.fetchone() is not None


def migrate_database():
    """Run migration"""
    
    print("=" * 70)
    print("DATABASE MIGRATION: Multi-Bank Support")
    print("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Step 1: Create new tables
        print("\n📋 Step 1: Creating new tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created: bank_accounts, recipients")
        
        # Step 2: Add columns to existing tables
        print("\n📋 Step 2: Adding new columns to existing tables...")
        
        with engine.connect() as conn:
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
                print("  ⏭️  bank_account_id already exists in sessions")
            
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
        
        # Step 3: Migrate existing users to have default HDFC accounts
        print("\n📋 Step 3: Migrating existing users...")
        
        users = db.query(User).all()
        
        if not users:
            print("⚠️  No existing users found. Skipping migration.")
        else:
            for user in users:
                # Check if user already has accounts
                existing_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == user.idx
                ).first()
                
                if existing_account:
                    print(f"  ⏭️  User {user.full_name} already has accounts. Skipping.")
                    continue
                
                # Create default HDFC account with user's current balance
                account_number = generate_account_number("HDFC", user.idx)
                
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
            
            db.commit()
            print(f"\n✅ Migrated {len(users)} users")
        
        # Step 4: Update existing sessions
        print("\n📋 Step 4: Linking existing sessions to bank accounts...")
        
        sessions = db.query(UserSession).filter(
            UserSession.bank_account_id == None
        ).all()
        
        if not sessions:
            print("⚠️  No unlinked sessions found.")
        else:
            for session in sessions:
                # Find user's HDFC account (default)
                account = db.query(BankAccount).filter(
                    BankAccount.user_idx == session.user_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()
                
                if account:
                    session.bank_account_id = account.id
                    print(f"  ✅ Linked session to {account.bank_code} account")
            
            db.commit()
            print(f"\n✅ Linked {len(sessions)} sessions")
        
        # Step 5: Update existing transactions
        print("\n📋 Step 5: Linking existing transactions to bank accounts...")
        
        transactions = db.query(Transaction).filter(
            Transaction.sender_account_id == None
        ).all()
        
        if not transactions:
            print("⚠️  No unlinked transactions found.")
        else:
            for tx in transactions:
                # Find sender's HDFC account
                sender_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == tx.sender_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()
                
                # Find receiver's HDFC account
                receiver_account = db.query(BankAccount).filter(
                    BankAccount.user_idx == tx.receiver_idx,
                    BankAccount.bank_code == "HDFC"
                ).first()
                
                if sender_account:
                    tx.sender_account_id = sender_account.id
                
                if receiver_account:
                    tx.receiver_account_id = receiver_account.id
                
                print(f"  ✅ Linked transaction {tx.transaction_hash[:16]}...")
            
            db.commit()
            print(f"\n✅ Linked {len(transactions)} transactions")
        
        # Step 6: Display summary
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        
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
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    
    finally:
        db.close()


if __name__ == "__main__":
    print("\n⚠️  WARNING: This will modify your database structure!")
    print("Make sure you have a backup before proceeding.\n")
    
    response = input("Continue with migration? (yes/no): ")
    
    if response.lower() == 'yes':
        migrate_database()
    else:
        print("Migration cancelled.")