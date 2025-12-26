#!/usr/bin/env python3
"""
Transaction Data Generation Script
Purpose: Generate realistic transaction patterns for testing

Usage:
    python scripts/testing/generate_transactions.py --count 10000
    python scripts/testing/generate_transactions.py --count 5000 --pattern burst
    python scripts/testing/generate_transactions.py --count 1000 --domestic 800 --travel 200

Features:
- Generates realistic transaction amounts
- Creates domestic transactions (Indian → Indian)
- Creates travel transactions (deposits, withdrawals, transfers)
- Supports different patterns: random, burst, steady
- Validates balances before transactions
"""

import sys
import os
import argparse
import random
import time
from decimal import Decimal
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.connection import SessionLocal
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.travel_account import TravelAccount
from database.models.transaction import Transaction
from core.services.transaction_service import TransactionService


class TransactionGenerator:
    """Generate realistic transaction data for testing"""

    # Transaction amount ranges
    SMALL_AMOUNT_RANGE = (100, 5_000)          # ₹100 - ₹5,000
    MEDIUM_AMOUNT_RANGE = (5_000, 50_000)      # ₹5K - ₹50K
    LARGE_AMOUNT_RANGE = (50_000, 500_000)     # ₹50K - ₹5L
    VERY_LARGE_AMOUNT_RANGE = (500_000, 5_000_000)  # ₹5L - ₹50L

    @staticmethod
    def generate_transaction_amount(category: str = 'medium') -> Decimal:
        """
        Generate random transaction amount

        Args:
            category: 'small', 'medium', 'large', 'very_large'

        Returns:
            Transaction amount as Decimal
        """
        if category == 'small':
            amount = random.uniform(*TransactionGenerator.SMALL_AMOUNT_RANGE)
        elif category == 'large':
            amount = random.uniform(*TransactionGenerator.LARGE_AMOUNT_RANGE)
        elif category == 'very_large':
            amount = random.uniform(*TransactionGenerator.VERY_LARGE_AMOUNT_RANGE)
        else:  # medium (default)
            amount = random.uniform(*TransactionGenerator.MEDIUM_AMOUNT_RANGE)

        return Decimal(str(round(amount, 2)))

    @staticmethod
    def select_random_category() -> str:
        """
        Select random transaction category with realistic distribution

        Distribution:
        - 60% small
        - 30% medium
        - 9% large
        - 1% very large
        """
        rand = random.random()
        if rand < 0.60:
            return 'small'
        elif rand < 0.90:
            return 'medium'
        elif rand < 0.99:
            return 'large'
        else:
            return 'very_large'

    @staticmethod
    def get_random_account_with_balance(db: SessionLocal, min_balance: Decimal) -> BankAccount:
        """
        Get random bank account with sufficient balance

        Args:
            db: Database session
            min_balance: Minimum balance required

        Returns:
            BankAccount or None
        """
        # Get accounts with sufficient balance
        accounts = db.query(BankAccount).filter(
            BankAccount.is_active == True,
            BankAccount.is_frozen == False,
            BankAccount.balance >= min_balance
        ).all()

        if not accounts:
            return None

        return random.choice(accounts)

    @staticmethod
    def get_random_receiver_account(db: SessionLocal, sender_idx: str) -> BankAccount:
        """
        Get random receiver account (different from sender)

        Args:
            db: Database session
            sender_idx: Sender's user IDX (to exclude)

        Returns:
            BankAccount or None
        """
        accounts = db.query(BankAccount).filter(
            BankAccount.is_active == True,
            BankAccount.is_frozen == False,
            BankAccount.user_idx != sender_idx
        ).all()

        if not accounts:
            return None

        return random.choice(accounts)

    @staticmethod
    def create_domestic_transaction(db: SessionLocal) -> tuple:
        """
        Create a domestic transaction (Indian → Indian)

        Args:
            db: Database session

        Returns:
            Tuple of (success: bool, transaction_hash: str or None, error: str or None)
        """
        try:
            # Select amount category
            category = TransactionGenerator.select_random_category()
            amount = TransactionGenerator.generate_transaction_amount(category)

            # Get sender account with sufficient balance
            sender_account = TransactionGenerator.get_random_account_with_balance(
                db,
                amount * Decimal('1.02')  # Amount + 2% fees
            )

            if not sender_account:
                return (False, None, "No sender account with sufficient balance")

            # Get receiver account (different user)
            receiver_account = TransactionGenerator.get_random_receiver_account(
                db,
                sender_account.user_idx
            )

            if not receiver_account:
                return (False, None, "No receiver account found")

            # Create transaction
            transaction_service = TransactionService(db)
            tx_hash = transaction_service.create_transaction(
                sender_account_number=sender_account.account_number,
                receiver_account_number=receiver_account.account_number,
                amount=amount,
                description=f"Test transaction - {category}",
                transaction_type='DOMESTIC'
            )

            return (True, tx_hash, None)

        except Exception as e:
            return (False, None, str(e))

    @staticmethod
    def create_travel_deposit(db: SessionLocal) -> tuple:
        """
        Create a travel deposit transaction (Indian → Foreign travel account)

        Args:
            db: Database session

        Returns:
            Tuple of (success: bool, transaction_hash: str or None, error: str or None)
        """
        try:
            # Get random active travel account
            travel_accounts = db.query(TravelAccount).filter(
                TravelAccount.is_active == True,
                TravelAccount.is_frozen == False
            ).all()

            if not travel_accounts:
                return (False, None, "No active travel accounts")

            travel_account = random.choice(travel_accounts)

            # Generate deposit amount
            category = TransactionGenerator.select_random_category()
            amount = TransactionGenerator.generate_transaction_amount(category)

            # Get sender account (same user as travel account)
            sender_account = db.query(BankAccount).filter(
                BankAccount.user_idx == travel_account.user_idx,
                BankAccount.is_active == True,
                BankAccount.is_frozen == False,
                BankAccount.balance >= amount * Decimal('1.02')
            ).first()

            if not sender_account:
                return (False, None, "Sender has no account with sufficient balance")

            # Create transaction
            transaction_service = TransactionService(db)
            tx_hash = transaction_service.create_transaction(
                sender_account_number=sender_account.account_number,
                receiver_account_number=travel_account.account_number,
                amount=amount,
                description=f"Travel deposit - {category}",
                transaction_type='TRAVEL_DEPOSIT'
            )

            return (True, tx_hash, None)

        except Exception as e:
            return (False, None, str(e))

    @staticmethod
    def generate_transactions(
        count: int,
        domestic_ratio: float,
        pattern: str,
        db: SessionLocal
    ) -> tuple:
        """
        Generate transactions

        Args:
            count: Total number of transactions to generate
            domestic_ratio: Ratio of domestic transactions (0.0 - 1.0)
            pattern: 'random', 'burst', or 'steady'
            db: Database session

        Returns:
            Tuple of (domestic_created, travel_created, errors)
        """
        print(f"\n💸 Generating {count} transactions...")
        print(f"   Pattern: {pattern}")
        print(f"   Domestic ratio: {domestic_ratio * 100:.0f}%")

        domestic_created = 0
        travel_created = 0
        errors = 0

        # Calculate target counts
        domestic_target = int(count * domestic_ratio)
        travel_target = count - domestic_target

        for i in range(count):
            try:
                # Determine transaction type
                if i < domestic_target:
                    tx_type = 'domestic'
                else:
                    tx_type = 'travel'

                # Create transaction
                if tx_type == 'domestic':
                    success, tx_hash, error = TransactionGenerator.create_domestic_transaction(db)
                    if success:
                        domestic_created += 1
                    else:
                        errors += 1
                        if errors <= 5:
                            print(f"  ❌ Domestic transaction failed: {error}")

                else:  # travel
                    success, tx_hash, error = TransactionGenerator.create_travel_deposit(db)
                    if success:
                        travel_created += 1
                    else:
                        errors += 1
                        if errors <= 5:
                            print(f"  ❌ Travel transaction failed: {error}")

                # Apply pattern delay
                if pattern == 'burst':
                    # Burst: Random short delays
                    if random.random() < 0.1:  # 10% chance of pause
                        time.sleep(random.uniform(0.5, 2.0))
                elif pattern == 'steady':
                    # Steady: Fixed small delay
                    time.sleep(0.1)
                # 'random' has no delay

                # Progress indicator
                if (i + 1) % 500 == 0:
                    print(f"  ✅ Created {i + 1}/{count} transactions...")

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  ❌ Unexpected error: {e}")

        print(f"\n✅ Domestic transactions created: {domestic_created}")
        print(f"✅ Travel transactions created: {travel_created}")
        if errors > 0:
            print(f"❌ Errors: {errors}")

        return (domestic_created, travel_created, errors)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate test transaction data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 10,000 transactions (80% domestic, 20% travel)
  python scripts/testing/generate_transactions.py --count 10000

  # Generate 5,000 burst transactions
  python scripts/testing/generate_transactions.py --count 5000 --pattern burst

  # Generate 1,000 transactions (90% domestic, 10% travel)
  python scripts/testing/generate_transactions.py --count 1000 --domestic-ratio 0.9
        """
    )

    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of transactions to generate'
    )

    parser.add_argument(
        '--domestic-ratio',
        type=float,
        default=0.8,
        help='Ratio of domestic transactions (0.0 - 1.0, default: 0.8)'
    )

    parser.add_argument(
        '--pattern',
        choices=['random', 'burst', 'steady'],
        default='random',
        help='Transaction pattern (default: random)'
    )

    args = parser.parse_args()

    # Validate
    if not 0.0 <= args.domestic_ratio <= 1.0:
        parser.error("--domestic-ratio must be between 0.0 and 1.0")

    print("=" * 60)
    print("💸 Transaction Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        # Check if we have users and accounts
        user_count = db.query(User).count()
        account_count = db.query(BankAccount).filter(BankAccount.is_active == True).count()

        if user_count == 0:
            print("\n❌ ERROR: No users found in database!")
            print("   Run: python scripts/testing/generate_users.py --count 1000")
            return 1

        if account_count == 0:
            print("\n❌ ERROR: No bank accounts found in database!")
            print("   Run: python scripts/testing/generate_users.py --count 1000")
            return 1

        print(f"\n📊 Found {user_count} users with {account_count} bank accounts")

        # Generate transactions
        domestic_created, travel_created, errors = TransactionGenerator.generate_transactions(
            args.count,
            args.domestic_ratio,
            args.pattern,
            db
        )

        print("\n" + "=" * 60)
        print(f"✅ COMPLETE")
        print(f"   Domestic transactions: {domestic_created}")
        print(f"   Travel transactions: {travel_created}")
        print(f"   Total: {domestic_created + travel_created}")
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
