#!/usr/bin/env python3
"""
User Data Generation Script
Purpose: Generate realistic users with bank accounts for testing

Usage:
    python scripts/testing/generate_users.py --count 10000
    python scripts/testing/generate_users.py --count 1000 --with-travel 100

Features:
- Generates realistic Indian names (first + last)
- Generates valid PAN card numbers
- Creates IDX identifiers using IDXGenerator
- Creates 1-3 bank accounts per user
- Optionally creates travel accounts
- Assigns initial random balances
"""

import sys
import os
import argparse
import random
import string
from decimal import Decimal
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.connection import SessionLocal
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.travel_account import TravelAccount
from database.models.bank import Bank
from database.models.foreign_bank import ForeignBank
from core.crypto.idx_generator import IDXGenerator


class UserGenerator:
    """Generate realistic user data for testing"""

    # Indian first names
    FIRST_NAMES = [
        # Male names
        "Aarav", "Aditya", "Arjun", "Arnav", "Aryan", "Ayush", "Dev", "Dhruv",
        "Harsh", "Ishaan", "Kabir", "Kartik", "Krishna", "Lakshya", "Manav",
        "Pranav", "Raj", "Reyansh", "Rohan", "Sai", "Shaurya", "Shivansh",
        "Vihaan", "Vivaan", "Yash", "Rajesh", "Suresh", "Ramesh", "Mahesh",
        "Dinesh", "Ganesh", "Vikram", "Amit", "Sumit", "Rohit", "Mohit",
        "Nikhil", "Akhil", "Vishal", "Varun", "Tarun", "Karan", "Aryan",
        # Female names
        "Aadhya", "Aanya", "Ananya", "Angel", "Avni", "Diya", "Ishita",
        "Kavya", "Khushi", "Myra", "Navya", "Pari", "Pihu", "Priya",
        "Riya", "Saanvi", "Sara", "Shanaya", "Shreya", "Siya", "Tara",
        "Anushka", "Divya", "Pooja", "Sneha", "Anjali", "Preeti", "Neha",
        "Ria", "Sakshi", "Simran", "Tanvi", "Aditi", "Kritika", "Nidhi"
    ]

    # Indian last names
    LAST_NAMES = [
        "Sharma", "Verma", "Singh", "Kumar", "Patel", "Gupta", "Reddy",
        "Rao", "Nair", "Menon", "Iyer", "Agarwal", "Jain", "Shah", "Mehta",
        "Desai", "Kulkarni", "Joshi", "Deshpande", "Patil", "More", "Naik",
        "Sawant", "Pawar", "Jadhav", "Bhosale", "Kadam", "Mane", "Shinde",
        "Gaikwad", "Yadav", "Chauhan", "Rajput", "Thakur", "Saxena", "Sinha",
        "Pandey", "Tiwari", "Dubey", "Shukla", "Mishra", "Tripathi", "Chaturvedi",
        "Banerjee", "Chatterjee", "Mukherjee", "Ghosh", "Das", "Sen", "Roy",
        "Bose", "Dutta", "Chakraborty", "Bhattacharya", "Ganguly", "Mitra"
    ]

    @staticmethod
    def generate_name() -> str:
        """Generate realistic Indian name"""
        first = random.choice(UserGenerator.FIRST_NAMES)
        last = random.choice(UserGenerator.LAST_NAMES)
        return f"{first} {last}"

    @staticmethod
    def generate_pan_card() -> str:
        """
        Generate realistic PAN card number
        Format: AAAAA9999A
        - First 5 chars: Letters (first 3 = initials, 4th = P for personal)
        - Next 4 chars: Numbers
        - Last char: Letter (check digit)
        """
        # First 3 letters (name initials)
        first_three = ''.join(random.choices(string.ascii_uppercase, k=3))

        # 4th letter: Always 'P' for Personal
        fourth = 'P'

        # 5th letter: Random
        fifth = random.choice(string.ascii_uppercase)

        # 4 digits
        digits = ''.join(random.choices(string.digits, k=4))

        # Last letter (check digit)
        last = random.choice(string.ascii_uppercase)

        return f"{first_three}{fourth}{fifth}{digits}{last}"

    @staticmethod
    def generate_rbi_number(index: int) -> str:
        """Generate RBI number (starts from 100000)"""
        return str(100000 + index)

    @staticmethod
    def generate_account_number(user_idx: str, bank_code: str) -> str:
        """Generate unique account number"""
        # Hash-based account number
        import hashlib
        hash_input = f"{user_idx}{bank_code}".encode()
        hash_digest = hashlib.sha256(hash_input).hexdigest()[:12]
        return hash_digest.upper()

    @staticmethod
    def generate_initial_balance() -> Decimal:
        """Generate random initial balance (₹1,000 - ₹1,000,000)"""
        amount = random.uniform(1_000, 1_000_000)
        return Decimal(str(round(amount, 2)))

    @staticmethod
    def get_random_banks(db: SessionLocal, count: int) -> list:
        """Get random active consortium banks"""
        banks = db.query(Bank).filter(Bank.is_active == True).all()
        if len(banks) < count:
            return banks
        return random.sample(banks, count)

    @staticmethod
    def get_random_foreign_bank(db: SessionLocal):
        """Get random active foreign bank"""
        foreign_banks = db.query(ForeignBank).filter(ForeignBank.is_active == True).all()
        if not foreign_banks:
            return None
        return random.choice(foreign_banks)

    @staticmethod
    def generate_users(count: int, with_travel: int, db: SessionLocal) -> tuple:
        """
        Generate users with bank accounts

        Args:
            count: Number of users to generate
            with_travel: Number of users who should have travel accounts
            db: Database session

        Returns:
            Tuple of (users_created, accounts_created, travel_created, errors)
        """
        print(f"\n👥 Generating {count} users...")
        if with_travel > 0:
            print(f"   (including {with_travel} with travel accounts)")

        users_created = 0
        accounts_created = 0
        travel_created = 0
        errors = 0

        # Track created PAN cards to avoid duplicates
        created_pans = set()

        for i in range(count):
            try:
                # Generate unique PAN
                max_attempts = 10
                pan_card = None
                for attempt in range(max_attempts):
                    pan_candidate = UserGenerator.generate_pan_card()
                    if pan_candidate not in created_pans:
                        pan_card = pan_candidate
                        created_pans.add(pan_card)
                        break

                if not pan_card:
                    raise Exception(f"Could not generate unique PAN after {max_attempts} attempts")

                # Generate IDX
                rbi_number = UserGenerator.generate_rbi_number(i)
                idx = IDXGenerator.generate(pan_card, rbi_number)

                # Generate user
                full_name = UserGenerator.generate_name()

                user = User(
                    idx=idx,
                    pan_card=pan_card,
                    full_name=full_name,
                    balance=Decimal('0.00')  # Balance stored in bank accounts
                )

                db.add(user)
                db.flush()  # Get user ID without committing

                users_created += 1

                # Create 1-3 bank accounts
                num_accounts = random.randint(1, 3)
                banks = UserGenerator.get_random_banks(db, num_accounts)

                for bank in banks:
                    account_number = UserGenerator.generate_account_number(idx, bank.bank_code)
                    initial_balance = UserGenerator.generate_initial_balance()

                    bank_account = BankAccount(
                        user_idx=idx,
                        bank_code=bank.bank_code,
                        account_number=account_number,
                        balance=initial_balance,
                        is_active=True,
                        is_frozen=False
                    )

                    db.add(bank_account)
                    accounts_created += 1

                # Create travel account if requested
                if i < with_travel:
                    foreign_bank = UserGenerator.get_random_foreign_bank(db)
                    if foreign_bank:
                        travel_duration_days = random.choice([30, 60, 90, 180])

                        travel_account = TravelAccount(
                            user_idx=idx,
                            foreign_bank_id=foreign_bank.id,
                            duration_days=travel_duration_days,
                            balance=Decimal('0.00'),
                            is_active=True,
                            is_frozen=False
                        )

                        db.add(travel_account)
                        travel_created += 1

                # Commit this user and all their accounts
                db.commit()

                # Progress indicator
                if (i + 1) % 500 == 0:
                    print(f"  ✅ Created {i + 1}/{count} users...")

            except Exception as e:
                db.rollback()
                errors += 1
                if errors <= 5:  # Show first 5 errors
                    print(f"  ❌ Error creating user {i + 1}: {e}")

        print(f"\n✅ Users created: {users_created}")
        print(f"✅ Bank accounts created: {accounts_created}")
        if with_travel > 0:
            print(f"✅ Travel accounts created: {travel_created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return (users_created, accounts_created, travel_created, errors)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate test user data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 10,000 users
  python scripts/testing/generate_users.py --count 10000

  # Generate 1,000 users, 100 with travel accounts
  python scripts/testing/generate_users.py --count 1000 --with-travel 100
        """
    )

    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of users to generate'
    )

    parser.add_argument(
        '--with-travel',
        type=int,
        default=0,
        help='Number of users who should have travel accounts (default: 0)'
    )

    args = parser.parse_args()

    # Validate
    if args.with_travel > args.count:
        parser.error("--with-travel cannot be greater than --count")

    print("=" * 60)
    print("👥 User Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        # Check if we have banks
        consortium_count = db.query(Bank).filter(Bank.is_active == True).count()
        if consortium_count == 0:
            print("\n❌ ERROR: No consortium banks found in database!")
            print("   Run: python scripts/testing/generate_banks.py --type consortium --count 100")
            return 1

        print(f"\n📊 Found {consortium_count} consortium banks in database")

        if args.with_travel > 0:
            foreign_count = db.query(ForeignBank).filter(ForeignBank.is_active == True).count()
            if foreign_count == 0:
                print("\n⚠️  WARNING: No foreign banks found! Travel accounts will be skipped.")
                print("   Run: python scripts/testing/generate_banks.py --type foreign --count 50")
            else:
                print(f"📊 Found {foreign_count} foreign banks in database")

        # Generate users
        users_created, accounts_created, travel_created, errors = UserGenerator.generate_users(
            args.count,
            args.with_travel,
            db
        )

        print("\n" + "=" * 60)
        print(f"✅ COMPLETE")
        print(f"   Users: {users_created}")
        print(f"   Bank Accounts: {accounts_created}")
        if args.with_travel > 0:
            print(f"   Travel Accounts: {travel_created}")
        if errors > 0:
            print(f"   Errors: {errors}")
        print("=" * 60)
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return 0 if errors == 0 else 1

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
