#!/usr/bin/env python3
# [DOC] FILE: scripts/testing/generate_transactions.py
# [DOC] PURPOSE: Populate the database with synthetic transactions to create a
# [DOC]   realistic dataset for integration testing and performance benchmarks.
# [DOC]
# [DOC] PRE-REQUISITES (must run first):
# [DOC]   1. generate_banks.py  — at least one Bank row must exist.
# [DOC]   2. generate_users.py  — at least two User + BankAccount rows with balance.
# [DOC]
# [DOC] TRANSACTION MIX:
# [DOC]   domestic (80% default): Indian bank account → Indian bank account
# [DOC]   travel   (20% default): Indian bank account → foreign travel account
# [DOC]
# [DOC] AMOUNT DISTRIBUTION (realistic):
# [DOC]   60% small   (₹100–₹5K)   → daily retail payments
# [DOC]   30% medium  (₹5K–₹50K)   → regular transfers
# [DOC]    9% large   (₹50K–₹5L)   → significant transfers
# [DOC]    1% very large (₹5L–₹50L) → triggers anomaly scoring (amount risk +40 pts)
# [DOC]
# [DOC] PATTERNS:
# [DOC]   random: no delay between transactions (maximum throughput)
# [DOC]   burst: 10% chance of 0.5–2s pause (simulates bursty real-world traffic)
# [DOC]   steady: 0.1s fixed delay (simulates steady-state processing)
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

# [DOC] sys/os: add project root to sys.path for absolute imports
import sys
import os
# [DOC] argparse: parse --count, --domestic-ratio, --pattern CLI flags
import argparse
# [DOC] random: select amount category, sender/receiver accounts
import random
# [DOC] time: implement burst/steady delay patterns
import time
# [DOC] Decimal: fixed-precision amounts
from decimal import Decimal
# [DOC] datetime: timestamp in progress output
from datetime import datetime

# [DOC] Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# [DOC] ORM models for querying and creating records
from database.connection import SessionLocal
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.travel_account import TravelAccount
from database.models.transaction import Transaction
# [DOC] TransactionService: the main service that runs the full transaction pipeline
# [DOC]   (commitment, range proof, anomaly scoring, batch queuing)
from core.services.transaction_service import TransactionService


class TransactionGenerator:
    # [DOC] Static helper class — no instance state; all logic is in @staticmethod methods.
    """Generate realistic transaction data for testing"""

    # [DOC] Amount ranges in INR; each tier maps to a realistic use-case category
    SMALL_AMOUNT_RANGE = (100, 5_000)           # [DOC] Retail payments, small transfers
    MEDIUM_AMOUNT_RANGE = (5_000, 50_000)       # [DOC] Regular bank transfers
    LARGE_AMOUNT_RANGE = (50_000, 500_000)      # [DOC] High-value transfers (may flag AML)
    VERY_LARGE_AMOUNT_RANGE = (500_000, 5_000_000)  # [DOC] PMLA-class amounts (definitely flags)

    @staticmethod
    def generate_transaction_amount(category: str = 'medium') -> Decimal:
        # [DOC] Pick a random float in the chosen range, round to 2 decimals,
        # [DOC]   then convert to Decimal to avoid float precision issues in DB storage.
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
        # [DOC] Weighted random selection mirrors the real-world distribution of bank transfers:
        # [DOC]   most transfers are small (daily payments), few are very large.
        # [DOC] Implementation: rand in [0.0, 1.0); thresholds define bucket boundaries.
        """
        Select random transaction category with realistic distribution

        Distribution:
        - 60% small
        - 30% medium
        - 9% large
        - 1% very large
        """
        rand = random.random()          # [DOC] Uniform [0.0, 1.0)
        if rand < 0.60:
            return 'small'              # [DOC] 60% chance
        elif rand < 0.90:
            return 'medium'             # [DOC] 30% chance (0.60–0.90)
        elif rand < 0.99:
            return 'large'              # [DOC] 9% chance (0.90–0.99)
        else:
            return 'very_large'         # [DOC] 1% chance (0.99–1.00)

    @staticmethod
    def get_random_account_with_balance(db: SessionLocal, min_balance: Decimal) -> BankAccount:
        # [DOC] Query all active, non-frozen accounts with balance >= min_balance.
        # [DOC]   min_balance is typically amount * 1.02 (amount + 2% fees) so the
        # [DOC]   transaction does not immediately trigger an insufficient-funds error.
        # [DOC] Returns None if no suitable account exists.
        """
        Get random bank account with sufficient balance

        Args:
            db: Database session
            min_balance: Minimum balance required

        Returns:
            BankAccount or None
        """
        accounts = db.query(BankAccount).filter(
            BankAccount.is_active == True,
            BankAccount.is_frozen == False,
            BankAccount.balance >= min_balance      # [DOC] Only accounts that can afford it
        ).all()

        if not accounts:
            return None

        return random.choice(accounts)

    @staticmethod
    def get_random_receiver_account(db: SessionLocal, sender_idx: str) -> BankAccount:
        # [DOC] Query active, non-frozen accounts belonging to a DIFFERENT user (sender_idx excluded).
        # [DOC]   Self-transfers are not meaningful for testing the system's privacy properties.
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
            BankAccount.user_idx != sender_idx      # [DOC] Exclude sender's own accounts
        ).all()

        if not accounts:
            return None

        return random.choice(accounts)

    @staticmethod
    def create_domestic_transaction(db: SessionLocal) -> tuple:
        # [DOC] End-to-end domestic transaction:
        # [DOC]   1. Pick a random amount category.
        # [DOC]   2. Find a sender with enough balance (amount + 2% fees).
        # [DOC]   3. Find a different-user receiver.
        # [DOC]   4. Delegate to TransactionService.create_transaction() which handles
        # [DOC]      commitment, nullifier, range proof, anomaly scoring, and batch queuing.
        # [DOC] Returns: (success: bool, tx_hash or None, error_message or None)
        """
        Create a domestic transaction (Indian → Indian)

        Args:
            db: Database session

        Returns:
            Tuple of (success: bool, transaction_hash: str or None, error: str or None)
        """
        try:
            category = TransactionGenerator.select_random_category()
            amount = TransactionGenerator.generate_transaction_amount(category)

            # [DOC] Require sender balance >= amount + 2% to cover miner + bank fees
            sender_account = TransactionGenerator.get_random_account_with_balance(
                db,
                amount * Decimal('1.02')
            )

            if not sender_account:
                return (False, None, "No sender account with sufficient balance")

            receiver_account = TransactionGenerator.get_random_receiver_account(
                db,
                sender_account.user_idx
            )

            if not receiver_account:
                return (False, None, "No receiver account found")

            # [DOC] TransactionService runs the full pipeline: ZK crypto, anomaly, batch queue
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
        # [DOC] Travel deposit: move funds from a domestic bank account into a travel account.
        # [DOC]   The sender and travel account must belong to the same user.
        # [DOC] Returns: (success, tx_hash or None, error or None)
        """
        Create a travel deposit transaction (Indian → Foreign travel account)

        Args:
            db: Database session

        Returns:
            Tuple of (success: bool, transaction_hash: str or None, error: str or None)
        """
        try:
            # [DOC] Find a random active travel account to deposit into
            travel_accounts = db.query(TravelAccount).filter(
                TravelAccount.is_active == True,
                TravelAccount.is_frozen == False
            ).all()

            if not travel_accounts:
                return (False, None, "No active travel accounts")

            travel_account = random.choice(travel_accounts)

            category = TransactionGenerator.select_random_category()
            amount = TransactionGenerator.generate_transaction_amount(category)

            # [DOC] Find a domestic bank account owned by the SAME user as the travel account
            sender_account = db.query(BankAccount).filter(
                BankAccount.user_idx == travel_account.user_idx,
                BankAccount.is_active == True,
                BankAccount.is_frozen == False,
                BankAccount.balance >= amount * Decimal('1.02')  # [DOC] Sufficient for amount + fees
            ).first()

            if not sender_account:
                return (False, None, "Sender has no account with sufficient balance")

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
        # [DOC] Main generation loop: create `count` transactions with the requested
        # [DOC]   domestic/travel split and timing pattern.
        # [DOC]
        # [DOC] Split calculation:
        # [DOC]   domestic_target = int(count * domestic_ratio)  e.g. 0.8 * 10000 = 8000
        # [DOC]   travel_target   = count - domestic_target       e.g. 2000
        # [DOC]   First domestic_target iterations create domestic txns; rest create travel txns.
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

        domestic_target = int(count * domestic_ratio)
        # [DOC] travel_target is implicitly count - domestic_target

        for i in range(count):
            try:
                # [DOC] First domestic_target iterations → domestic; remainder → travel
                if i < domestic_target:
                    tx_type = 'domestic'
                else:
                    tx_type = 'travel'

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

                # [DOC] Apply pattern-specific inter-transaction delay
                if pattern == 'burst':
                    # [DOC] 10% chance of a random pause (0.5–2s) to simulate bursty traffic
                    if random.random() < 0.1:
                        time.sleep(random.uniform(0.5, 2.0))
                elif pattern == 'steady':
                    # [DOC] Fixed 100ms delay for steady-state simulation
                    time.sleep(0.1)
                # [DOC] 'random' pattern: no sleep — maximum throughput

                # [DOC] Print progress every 500 transactions
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
    # [DOC] Entry point: parse CLI flags, validate pre-conditions, run generation.
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

    # [DOC] --count: total number of transactions to create; required
    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of transactions to generate'
    )

    # [DOC] --domestic-ratio: fraction of transactions that are domestic (0.0–1.0)
    parser.add_argument(
        '--domestic-ratio',
        type=float,
        default=0.8,
        help='Ratio of domestic transactions (0.0 - 1.0, default: 0.8)'
    )

    # [DOC] --pattern: timing pattern between transactions
    parser.add_argument(
        '--pattern',
        choices=['random', 'burst', 'steady'],
        default='random',
        help='Transaction pattern (default: random)'
    )

    args = parser.parse_args()

    # [DOC] Validate ratio is in [0.0, 1.0]
    if not 0.0 <= args.domestic_ratio <= 1.0:
        parser.error("--domestic-ratio must be between 0.0 and 1.0")

    print("=" * 60)
    print("💸 Transaction Data Generation Script")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        # [DOC] Pre-condition checks: need users and bank accounts to run transactions
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
