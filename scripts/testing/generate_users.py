#!/usr/bin/env python3
# [DOC] FILE: scripts/testing/generate_users.py
# [DOC] PURPOSE: Populate the database with synthetic user records, bank accounts,
# [DOC]   and optionally travel accounts for testing and load benchmarks.
# [DOC]
# [DOC] PRE-REQUISITE: At least one active Bank row must exist in the DB.
# [DOC]   Run generate_banks.py first.
# [DOC]
# [DOC] WHAT THIS CREATES PER USER:
# [DOC]   1. A User row with a unique IDX (SHA-256 of PAN + RBI number + pepper).
# [DOC]   2. 1–3 BankAccount rows linked to randomly chosen active Banks.
# [DOC]   3. Optionally a TravelAccount row linked to a random active ForeignBank.
# [DOC]
# [DOC] USAGE:
# [DOC]   python scripts/testing/generate_users.py --count 10000
# [DOC]   python scripts/testing/generate_users.py --count 1000 --with-travel 100
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

# [DOC] sys/os: add project root to sys.path for absolute imports
import sys
import os
# [DOC] argparse: parse --count and --with-travel CLI flags
import argparse
# [DOC] random: pick names, account counts, bank assignments, travel durations
import random
# [DOC] string: letter/digit character pools used in PAN generation
import string
# [DOC] Decimal: fixed-precision balance amounts
from decimal import Decimal
# [DOC] datetime: timestamp in progress output
from datetime import datetime

# [DOC] Add the project root to sys.path so imports work from any cwd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# [DOC] ORM models and DB session factory
from database.connection import SessionLocal
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.travel_account import TravelAccount
from database.models.bank import Bank
from database.models.foreign_bank import ForeignBank
# [DOC] IDXGenerator: computes the permanent pseudonym IDX = SHA256(pan_card:rbi_number:PEPPER)
from core.crypto.idx_generator import IDXGenerator


class UserGenerator:
    # [DOC] Static helper class — all methods are @staticmethod.
    """Generate realistic user data for testing"""

    # [DOC] Indian first-name pool: mix of modern and traditional names, male and female
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

    # [DOC] Indian surname pool spanning major regional surname families
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
        # [DOC] Pick a random first name + last name and concatenate with a space.
        """Generate realistic Indian name"""
        first = random.choice(UserGenerator.FIRST_NAMES)
        last = random.choice(UserGenerator.LAST_NAMES)
        return f"{first} {last}"

    @staticmethod
    def generate_pan_card() -> str:
        # [DOC] Indian PAN card format: AAAAA9999A (10 characters).
        # [DOC]   Chars 1–3: initials (random uppercase letters)
        # [DOC]   Char 4: always 'P' for individual (Person) accounts
        # [DOC]   Char 5: random uppercase letter
        # [DOC]   Chars 6–9: 4 digits (sequential number in real PANs, random here)
        # [DOC]   Char 10: check letter (random here — real check uses a specific algorithm)
        """
        Generate realistic PAN card number
        Format: AAAAA9999A
        - First 5 chars: Letters (first 3 = initials, 4th = P for personal)
        - Next 4 chars: Numbers
        - Last char: Letter (check digit)
        """
        first_three = ''.join(random.choices(string.ascii_uppercase, k=3))
        fourth = 'P'                                            # [DOC] Always 'P' for individuals
        fifth = random.choice(string.ascii_uppercase)
        digits = ''.join(random.choices(string.digits, k=4))
        last = random.choice(string.ascii_uppercase)           # [DOC] Random check letter

        return f"{first_three}{fourth}{fifth}{digits}{last}"

    @staticmethod
    def generate_rbi_number(index: int) -> str:
        # [DOC] Synthetic RBI registration number — just an offset integer as a string.
        # [DOC]   Starting at 100000 avoids leading zeros and mimics real numbering.
        """Generate RBI number (starts from 100000)"""
        return str(100000 + index)

    @staticmethod
    def generate_account_number(user_idx: str, bank_code: str) -> str:
        # [DOC] Derive a stable 12-char account number from (user_idx, bank_code) via SHA-256.
        # [DOC]   This ensures the same user always gets the same account number at the same bank,
        # [DOC]   and that no two users share an account number at the same bank.
        """Generate unique account number"""
        import hashlib
        hash_input = f"{user_idx}{bank_code}".encode()
        hash_digest = hashlib.sha256(hash_input).hexdigest()[:12]  # [DOC] First 12 hex chars
        return hash_digest.upper()                                   # [DOC] Uppercase for readability

    @staticmethod
    def generate_initial_balance() -> Decimal:
        # [DOC] Random starting balance ₹1,000–₹1,000,000 so test transactions can succeed
        # [DOC]   without triggering insufficient-funds errors.
        """Generate random initial balance (₹1,000 - ₹1,000,000)"""
        amount = random.uniform(1_000, 1_000_000)
        return Decimal(str(round(amount, 2)))

    @staticmethod
    def get_random_banks(db: SessionLocal, count: int) -> list:
        # [DOC] Query all active Banks, then sample `count` of them randomly.
        # [DOC]   If fewer than `count` banks exist, returns all of them (no error).
        """Get random active consortium banks"""
        banks = db.query(Bank).filter(Bank.is_active == True).all()
        if len(banks) < count:
            return banks
        return random.sample(banks, count)

    @staticmethod
    def get_random_foreign_bank(db: SessionLocal):
        # [DOC] Returns one random active ForeignBank or None if no foreign banks exist.
        # [DOC]   None is handled gracefully in generate_users() — travel account is skipped.
        """Get random active foreign bank"""
        foreign_banks = db.query(ForeignBank).filter(ForeignBank.is_active == True).all()
        if not foreign_banks:
            return None
        return random.choice(foreign_banks)

    @staticmethod
    def generate_users(count: int, with_travel: int, db: SessionLocal) -> tuple:
        # [DOC] Core generation loop — creates count users, each with 1–3 bank accounts.
        # [DOC]
        # [DOC] PAN uniqueness: PANs are tracked in `created_pans` (a Python set) and
        # [DOC]   re-generated if a collision occurs (up to 10 attempts per user).
        # [DOC]   A duplicate PAN would violate the DB unique constraint and cause a rollback.
        # [DOC]
        # [DOC] db.flush() vs db.commit():
        # [DOC]   flush() writes the User row to the DB transaction buffer so bank accounts
        # [DOC]   can reference user.idx, but does not make it visible to other connections.
        # [DOC]   commit() at the end of each user loop makes everything visible atomically.
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

        # [DOC] Track PAN cards already inserted in this run to avoid DB unique-constraint errors
        created_pans = set()

        for i in range(count):
            try:
                # [DOC] Try up to 10 times to get a PAN not already used in this run
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

                # [DOC] IDX = SHA256(pan_card:rbi_number:PEPPER) — permanent pseudonym
                rbi_number = UserGenerator.generate_rbi_number(i)
                idx = IDXGenerator.generate(pan_card, rbi_number)

                full_name = UserGenerator.generate_name()

                # [DOC] User.balance is kept at 0.00 — actual balances live in BankAccount rows
                user = User(
                    idx=idx,
                    pan_card=pan_card,
                    full_name=full_name,
                    balance=Decimal('0.00')  # Balance stored in bank accounts
                )

                db.add(user)
                db.flush()  # [DOC] Write user to transaction buffer so we can reference idx below

                users_created += 1

                # [DOC] Assign 1–3 bank accounts to each user, at randomly chosen banks
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
                        is_frozen=False   # [DOC] Not frozen at creation; freeze requires court order
                    )

                    db.add(bank_account)
                    accounts_created += 1

                # [DOC] Create a travel account for the first `with_travel` users (index i < with_travel)
                if i < with_travel:
                    foreign_bank = UserGenerator.get_random_foreign_bank(db)
                    if foreign_bank:
                        # [DOC] duration_days: how long the travel account stays active (30/60/90/180)
                        travel_duration_days = random.choice([30, 60, 90, 180])

                        travel_account = TravelAccount(
                            user_idx=idx,
                            foreign_bank_id=foreign_bank.id,
                            duration_days=travel_duration_days,
                            balance=Decimal('0.00'),   # [DOC] Funded by a separate deposit transaction
                            is_active=True,
                            is_frozen=False
                        )

                        db.add(travel_account)
                        travel_created += 1

                # [DOC] Commit the user + all their accounts atomically; rollback on error
                db.commit()

                # [DOC] Print progress every 500 users
                if (i + 1) % 500 == 0:
                    print(f"  ✅ Created {i + 1}/{count} users...")

            except Exception as e:
                db.rollback()   # [DOC] Undo the partially-created user and their accounts
                errors += 1
                if errors <= 5:
                    print(f"  ❌ Error creating user {i + 1}: {e}")

        print(f"\n✅ Users created: {users_created}")
        print(f"✅ Bank accounts created: {accounts_created}")
        if with_travel > 0:
            print(f"✅ Travel accounts created: {travel_created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return (users_created, accounts_created, travel_created, errors)


def main():
    # [DOC] Entry point: parse arguments, verify pre-conditions, delegate to UserGenerator.
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

    # [DOC] --count: total number of users to create; required
    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of users to generate'
    )

    # [DOC] --with-travel: how many of those users also get a travel account (default: none)
    parser.add_argument(
        '--with-travel',
        type=int,
        default=0,
        help='Number of users who should have travel accounts (default: 0)'
    )

    args = parser.parse_args()

    # [DOC] Sanity check: cannot have more travel users than total users
    if args.with_travel > args.count:
        parser.error("--with-travel cannot be greater than --count")

    print("=" * 60)
    print("👥 User Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        # [DOC] Pre-condition check: require at least one active consortium bank to exist
        consortium_count = db.query(Bank).filter(Bank.is_active == True).count()
        if consortium_count == 0:
            print("\n❌ ERROR: No consortium banks found in database!")
            print("   Run: python scripts/testing/generate_banks.py --type consortium --count 100")
            return 1

        print(f"\n📊 Found {consortium_count} consortium banks in database")

        if args.with_travel > 0:
            foreign_count = db.query(ForeignBank).filter(ForeignBank.is_active == True).count()
            if foreign_count == 0:
                # [DOC] Foreign banks are optional — warn but don't abort
                print("\n⚠️  WARNING: No foreign banks found! Travel accounts will be skipped.")
                print("   Run: python scripts/testing/generate_banks.py --type foreign --count 50")
            else:
                print(f"📊 Found {foreign_count} foreign banks in database")

        # [DOC] Delegate all creation logic to the generator
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

        # [DOC] Return exit code 0 on full success, 1 if any user failed
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
