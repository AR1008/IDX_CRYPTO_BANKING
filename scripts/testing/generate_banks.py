#!/usr/bin/env python3
# [DOC] FILE: scripts/testing/generate_banks.py
# [DOC] PURPOSE: Populate the database with realistic consortium and foreign bank records
# [DOC]   for testing and benchmarking. Run this BEFORE generate_users.py because
# [DOC]   users require at least one active Bank record to open a bank account.
# [DOC]
# [DOC] USAGE:
# [DOC]   python scripts/testing/generate_banks.py --type consortium --count 1000
# [DOC]   python scripts/testing/generate_banks.py --type foreign   --count 500
# [DOC]   python scripts/testing/generate_banks.py --type all --consortium 1000 --foreign 500
# [DOC]
# [DOC] OUTPUT:
# [DOC]   Inserts Bank rows (consortium) or ForeignBank rows (foreign) into PostgreSQL.
# [DOC]   Each Bank row includes stake_amount (₹50M–₹500M) needed by the BFT governance model.
"""
Bank Data Generation Script
Purpose: Generate realistic consortium and foreign banks for testing

Usage:
    python scripts/testing/generate_banks.py --type consortium --count 1000
    python scripts/testing/generate_banks.py --type foreign --count 500
    python scripts/testing/generate_banks.py --type all --consortium 1000 --foreign 500

Features:
- Generates realistic Indian bank names
- Generates foreign banks (US, UK, Singapore, UAE)
- Assigns random stake amounts (₹50M - ₹500M)
- Creates unique bank codes
- Inserts into database with progress tracking
"""

# [DOC] sys/os: used to add the project root to sys.path so imports like
# [DOC]   "from database.connection import ..." work from any working directory.
import sys
import os
# [DOC] argparse: parses command-line flags (--type, --count, --consortium, --foreign)
import argparse
# [DOC] random: pick random bank names and stake amounts
import random
# [DOC] Decimal: fixed-precision amounts for stake_amount DB column
from decimal import Decimal
# [DOC] datetime: timestamp in progress output
from datetime import datetime

# [DOC] Add the project root (two levels up from this script) to the Python path
# [DOC]   so "from database.connection import SessionLocal" works correctly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# [DOC] SessionLocal: SQLAlchemy session factory — creates DB connections
from database.connection import SessionLocal
# [DOC] Bank: ORM model for consortium (domestic) banks
from database.models.bank import Bank
# [DOC] ForeignBank: ORM model for international correspondent banks
from database.models.foreign_bank import ForeignBank


class BankGenerator:
    # [DOC] Static helper class — all methods are @staticmethod, no instance state needed.
    """Generate realistic bank data for testing"""

    # [DOC] Word pools used to construct random Indian bank names
    INDIAN_BANK_PREFIXES = [
        "State", "National", "Indian", "United", "Central", "Federal", "Metropolitan",
        "Regional", "Urban", "Rural", "Industrial", "Commercial", "People's", "Citizens",
        "Union", "Progressive", "Development", "Cooperative", "Mercantile", "Imperial"
    ]

    INDIAN_BANK_TYPES = [
        "Bank", "Bank of India", "Banking Corporation", "Co-operative Bank",
        "Gramin Bank", "Financial Services", "Banking Company"
    ]

    INDIAN_STATES = [
        "Maharashtra", "Punjab", "Karnataka", "Gujarat", "Rajasthan", "Tamil Nadu",
        "Uttar Pradesh", "West Bengal", "Kerala", "Andhra Pradesh", "Telangana",
        "Madhya Pradesh", "Bihar", "Odisha", "Haryana", "Delhi"
    ]

    # [DOC] Known real foreign bank names grouped by country code for authenticity
    FOREIGN_BANKS = {
        'US': [
            'JPMorgan Chase', 'Bank of America', 'Wells Fargo', 'Citibank',
            'Goldman Sachs', 'Morgan Stanley', 'U.S. Bank', 'PNC Financial',
            'Capital One', 'TD Bank', 'Bank of New York Mellon', 'State Street',
            'Charles Schwab', 'American Express', 'Citizens Bank'
        ],
        'UK': [
            'HSBC', 'Barclays', 'Lloyds Banking Group', 'NatWest Group',
            'Standard Chartered', 'Santander UK', 'Nationwide', 'Metro Bank',
            'Virgin Money UK', 'TSB Bank', 'Clydesdale Bank', 'Yorkshire Bank'
        ],
        'Singapore': [
            'DBS Bank', 'OCBC Bank', 'United Overseas Bank', 'Maybank Singapore',
            'Standard Chartered Singapore', 'CIMB Bank Singapore', 'RHB Bank Singapore',
            'Bank of China Singapore', 'ICBC Singapore', 'ANZ Singapore'
        ],
        'UAE': [
            'Emirates NBD', 'First Abu Dhabi Bank', 'Dubai Islamic Bank',
            'Abu Dhabi Commercial Bank', 'Mashreq Bank', 'Commercial Bank of Dubai',
            'Union National Bank', 'Sharjah Islamic Bank', 'Al Hilal Bank',
            'National Bank of Fujairah', 'Noor Bank', 'RAKBANK'
        ]
    }

    # [DOC] Map short country code → full country name for the ForeignBank.country column
    FOREIGN_COUNTRIES = {
        'US': 'United States',
        'UK': 'United Kingdom',
        'Singapore': 'Singapore',
        'UAE': 'United Arab Emirates'
    }

    @staticmethod
    def generate_indian_bank_name() -> str:
        # [DOC] Randomly pick one of three name patterns to create variety:
        # [DOC]   1. "<State> State Bank / Gramin Bank / Co-operative Bank"
        # [DOC]   2. "<Prefix> <BankType>"
        # [DOC]   3. "<Prefix> Bank of <State>"
        """Generate realistic Indian bank name"""
        choice = random.randint(1, 3)

        if choice == 1:
            # [DOC] Pattern 1: state-branded bank (e.g. "Punjab State Bank")
            state = random.choice(BankGenerator.INDIAN_STATES)
            bank_type = random.choice(["State Bank", "Gramin Bank", "Co-operative Bank"])
            return f"{state} {bank_type}"

        elif choice == 2:
            # [DOC] Pattern 2: generic name (e.g. "National Bank of India")
            prefix = random.choice(BankGenerator.INDIAN_BANK_PREFIXES)
            bank_type = random.choice(BankGenerator.INDIAN_BANK_TYPES)
            return f"{prefix} {bank_type}"

        else:
            # [DOC] Pattern 3: prefix + state (e.g. "Progressive Bank of Kerala")
            prefix = random.choice(BankGenerator.INDIAN_BANK_PREFIXES)
            state = random.choice(BankGenerator.INDIAN_STATES)
            return f"{prefix} Bank of {state}"

    @staticmethod
    def generate_bank_code(index: int, prefix: str = "BANK") -> str:
        # [DOC] Zero-pad index to 5 digits so codes sort lexicographically:
        # [DOC]   CBANK00001, CBANK00002, … CBANK01000
        """Generate unique bank code"""
        return f"{prefix}{index:05d}"

    @staticmethod
    def generate_stake_amount() -> Decimal:
        # [DOC] Random stake in ₹50M–₹500M range.
        # [DOC] Stake is used by the governance model: banks with higher stakes have
        # [DOC]   more to lose from slashing, incentivising honest behaviour.
        """Generate random stake amount (₹50M - ₹500M)"""
        amount = random.uniform(50_000_000, 500_000_000)
        return Decimal(str(round(amount, 2)))

    @staticmethod
    def generate_consortium_banks(count: int, db: SessionLocal) -> int:
        # [DOC] Loop count times: generate name + code + stake, create a Bank ORM object,
        # [DOC]   add it to the session, and commit after each bank.
        # [DOC] Committing per-bank (rather than once at the end) means partial progress
        # [DOC]   is not lost if the script crashes halfway through.
        """
        Generate consortium banks (Indian banks)

        Args:
            count: Number of banks to generate
            db: Database session

        Returns:
            Number of banks created
        """
        print(f"\n🏦 Generating {count} consortium banks...")

        created = 0
        errors = 0

        for i in range(count):
            try:
                # [DOC] Build a fresh random name and code for this bank
                bank_name = BankGenerator.generate_indian_bank_name()
                bank_code = BankGenerator.generate_bank_code(i + 1, "CBANK")
                stake = BankGenerator.generate_stake_amount()

                # [DOC] Create ORM instance — not yet persisted until db.add() + db.commit()
                bank = Bank(
                    bank_code=bank_code,
                    bank_name=bank_name,
                    stake_amount=stake,
                    is_active=True,              # [DOC] Active at creation; can be deactivated by slashing
                    total_fees_earned=Decimal('0.00'),  # [DOC] Accumulated fee income starts at zero
                    total_validations=0          # [DOC] Validation counter starts at zero
                )

                db.add(bank)    # [DOC] Stage the bank for insertion (not yet in DB)
                db.commit()     # [DOC] Flush to DB; generates the bank's auto-increment id

                created += 1

                # [DOC] Print progress every 100 banks to show liveness during long runs
                if (i + 1) % 100 == 0:
                    print(f"  ✅ Created {i + 1}/{count} banks...")

            except Exception as e:
                db.rollback()   # [DOC] Undo the failed insert so the session stays clean
                errors += 1
                if errors <= 5:  # [DOC] Show only the first 5 errors to avoid log spam
                    print(f"  ❌ Error creating bank {i + 1}: {e}")

        print(f"\n✅ Consortium banks created: {created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return created

    @staticmethod
    def generate_foreign_banks(count: int, db: SessionLocal) -> int:
        # [DOC] Distribute `count` banks evenly across 4 countries (US, UK, SG, UAE).
        # [DOC] If count is not divisible by 4, the remainder is distributed one-per-country
        # [DOC]   until exhausted (the remainder -= 1 logic below).
        """
        Generate foreign banks (US, UK, Singapore, UAE)

        Args:
            count: Number of banks to generate
            db: Database session

        Returns:
            Number of banks created
        """
        print(f"\n🌍 Generating {count} foreign banks...")

        created = 0
        errors = 0

        # [DOC] Integer division gives the base count per country
        banks_per_country = count // 4
        # [DOC] Remaining banks (0–3) get distributed one at a time
        remainder = count % 4

        all_banks = []
        for country_code, banks in BankGenerator.FOREIGN_BANKS.items():
            # [DOC] Countries with remaining quota get one extra bank
            country_banks = banks_per_country + (1 if remainder > 0 else 0)
            remainder -= 1

            # [DOC] Duplicate the bank name list if we need more banks than names exist
            while len(banks) < country_banks:
                banks = banks + banks  # [DOC] Double the list repeatedly until long enough

            # [DOC] Pick `country_banks` unique names; sample() raises if len(banks) < k,
            # [DOC]   so we use min() as a safety cap
            selected_banks = random.sample(banks, min(country_banks, len(banks)))

            for bank_name in selected_banks:
                all_banks.append({
                    'name': bank_name,
                    'country_code': country_code,
                    'country': BankGenerator.FOREIGN_COUNTRIES[country_code]
                })

        # [DOC] Shuffle so that country clusters are interspersed in insertion order
        random.shuffle(all_banks)

        for i, bank_data in enumerate(all_banks[:count]):
            try:
                bank = ForeignBank(
                    bank_name=bank_data['name'],
                    country=bank_data['country'],
                    country_code=bank_data['country_code'],
                    # [DOC] SWIFT code: country code + 4 random digits (realistic format)
                    swift_code=f"{bank_data['country_code']}{random.randint(1000, 9999)}",
                    is_active=True,
                    total_fees_earned=Decimal('0.00'),
                    total_validations=0
                )

                db.add(bank)
                db.commit()

                created += 1

                if (i + 1) % 50 == 0:
                    print(f"  ✅ Created {i + 1}/{count} foreign banks...")

            except Exception as e:
                db.rollback()
                errors += 1
                if errors <= 5:
                    print(f"  ❌ Error creating foreign bank {i + 1}: {e}")

        print(f"\n✅ Foreign banks created: {created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return created


def main():
    # [DOC] Entry point: parse CLI arguments, open a DB session, delegate to BankGenerator.
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate test bank data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 1000 consortium banks
  python scripts/testing/generate_banks.py --type consortium --count 1000

  # Generate 500 foreign banks
  python scripts/testing/generate_banks.py --type foreign --count 500

  # Generate both types
  python scripts/testing/generate_banks.py --type all --consortium 1000 --foreign 500
        """
    )

    # [DOC] --type: which table(s) to populate; required argument
    parser.add_argument(
        '--type',
        choices=['consortium', 'foreign', 'all'],
        required=True,
        help='Type of banks to generate'
    )

    # [DOC] --count: how many rows to create for single-type runs
    parser.add_argument(
        '--count',
        type=int,
        help='Number of banks to generate (for consortium or foreign)'
    )

    # [DOC] --consortium / --foreign: separate counts when --type all is used
    parser.add_argument(
        '--consortium',
        type=int,
        help='Number of consortium banks (when --type all)'
    )

    parser.add_argument(
        '--foreign',
        type=int,
        help='Number of foreign banks (when --type all)'
    )

    args = parser.parse_args()

    # [DOC] Validate that the required count argument is present for each mode
    if args.type in ['consortium', 'foreign'] and not args.count:
        parser.error(f"--count is required when --type is {args.type}")

    if args.type == 'all' and (not args.consortium or not args.foreign):
        parser.error("--consortium and --foreign are required when --type is all")

    print("=" * 60)
    print("🏦 Bank Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # [DOC] Open a fresh DB session for the entire generation run
    db = SessionLocal()

    try:
        total_created = 0

        # [DOC] Dispatch to the appropriate generator based on --type
        if args.type == 'consortium':
            total_created = BankGenerator.generate_consortium_banks(args.count, db)

        elif args.type == 'foreign':
            total_created = BankGenerator.generate_foreign_banks(args.count, db)

        elif args.type == 'all':
            consortium_count = BankGenerator.generate_consortium_banks(args.consortium, db)
            foreign_count = BankGenerator.generate_foreign_banks(args.foreign, db)
            total_created = consortium_count + foreign_count

        print("\n" + "=" * 60)
        print(f"✅ COMPLETE - Total banks created: {total_created}")
        print("=" * 60)
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # [DOC] Always close the session so DB connections are returned to the pool
        db.close()

    return 0


# [DOC] Guard: only run main() when this file is executed directly, not when imported.
if __name__ == "__main__":
    sys.exit(main())
