#!/usr/bin/env python3
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

import sys
import os
import argparse
import random
from decimal import Decimal
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.connection import SessionLocal
from database.models.bank import Bank
from database.models.foreign_bank import ForeignBank


class BankGenerator:
    """Generate realistic bank data for testing"""

    # Indian bank name components
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

    # Foreign banks by country
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

    FOREIGN_COUNTRIES = {
        'US': 'United States',
        'UK': 'United Kingdom',
        'Singapore': 'Singapore',
        'UAE': 'United Arab Emirates'
    }

    @staticmethod
    def generate_indian_bank_name() -> str:
        """Generate realistic Indian bank name"""
        choice = random.randint(1, 3)

        if choice == 1:
            # State-based bank
            state = random.choice(BankGenerator.INDIAN_STATES)
            bank_type = random.choice(["State Bank", "Gramin Bank", "Co-operative Bank"])
            return f"{state} {bank_type}"

        elif choice == 2:
            # Prefix + Type
            prefix = random.choice(BankGenerator.INDIAN_BANK_PREFIXES)
            bank_type = random.choice(BankGenerator.INDIAN_BANK_TYPES)
            return f"{prefix} {bank_type}"

        else:
            # Prefix + State + Type
            prefix = random.choice(BankGenerator.INDIAN_BANK_PREFIXES)
            state = random.choice(BankGenerator.INDIAN_STATES)
            return f"{prefix} Bank of {state}"

    @staticmethod
    def generate_bank_code(index: int, prefix: str = "BANK") -> str:
        """Generate unique bank code"""
        return f"{prefix}{index:05d}"

    @staticmethod
    def generate_stake_amount() -> Decimal:
        """Generate random stake amount (₹50M - ₹500M)"""
        amount = random.uniform(50_000_000, 500_000_000)
        return Decimal(str(round(amount, 2)))

    @staticmethod
    def generate_consortium_banks(count: int, db: SessionLocal) -> int:
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
                bank_name = BankGenerator.generate_indian_bank_name()
                bank_code = BankGenerator.generate_bank_code(i + 1, "CBANK")
                stake = BankGenerator.generate_stake_amount()

                bank = Bank(
                    bank_code=bank_code,
                    bank_name=bank_name,
                    stake_amount=stake,
                    is_active=True,
                    total_fees_earned=Decimal('0.00'),
                    total_validations=0
                )

                db.add(bank)
                db.commit()

                created += 1

                # Progress indicator
                if (i + 1) % 100 == 0:
                    print(f"  ✅ Created {i + 1}/{count} banks...")

            except Exception as e:
                db.rollback()
                errors += 1
                if errors <= 5:  # Show first 5 errors
                    print(f"  ❌ Error creating bank {i + 1}: {e}")

        print(f"\n✅ Consortium banks created: {created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return created

    @staticmethod
    def generate_foreign_banks(count: int, db: SessionLocal) -> int:
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

        # Distribute banks across countries
        banks_per_country = count // 4
        remainder = count % 4

        all_banks = []
        for country_code, banks in BankGenerator.FOREIGN_BANKS.items():
            country_banks = banks_per_country + (1 if remainder > 0 else 0)
            remainder -= 1

            # Repeat bank names if needed
            while len(banks) < country_banks:
                banks = banks + banks  # Double the list

            selected_banks = random.sample(banks, min(country_banks, len(banks)))

            for bank_name in selected_banks:
                all_banks.append({
                    'name': bank_name,
                    'country_code': country_code,
                    'country': BankGenerator.FOREIGN_COUNTRIES[country_code]
                })

        # Shuffle for random insertion
        random.shuffle(all_banks)

        for i, bank_data in enumerate(all_banks[:count]):
            try:
                bank = ForeignBank(
                    bank_name=bank_data['name'],
                    country=bank_data['country'],
                    country_code=bank_data['country_code'],
                    swift_code=f"{bank_data['country_code']}{random.randint(1000, 9999)}",
                    is_active=True,
                    total_fees_earned=Decimal('0.00'),
                    total_validations=0
                )

                db.add(bank)
                db.commit()

                created += 1

                # Progress indicator
                if (i + 1) % 50 == 0:
                    print(f"  ✅ Created {i + 1}/{count} foreign banks...")

            except Exception as e:
                db.rollback()
                errors += 1
                if errors <= 5:  # Show first 5 errors
                    print(f"  ❌ Error creating foreign bank {i + 1}: {e}")

        print(f"\n✅ Foreign banks created: {created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return created


def main():
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

    parser.add_argument(
        '--type',
        choices=['consortium', 'foreign', 'all'],
        required=True,
        help='Type of banks to generate'
    )

    parser.add_argument(
        '--count',
        type=int,
        help='Number of banks to generate (for consortium or foreign)'
    )

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

    # Validate arguments
    if args.type in ['consortium', 'foreign'] and not args.count:
        parser.error(f"--count is required when --type is {args.type}")

    if args.type == 'all' and (not args.consortium or not args.foreign):
        parser.error("--consortium and --foreign are required when --type is all")

    print("=" * 60)
    print("🏦 Bank Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        total_created = 0

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
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
