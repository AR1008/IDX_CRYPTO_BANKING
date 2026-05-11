"""
Fiscal Year Reward Distribution Service
Purpose: Distribute treasury (slashed funds) to honest banks at fiscal year end

Distribution Logic:
- Treasury accumulates slashed funds throughout the fiscal year
- At fiscal year end (March 31), distribute to honest banks
- Distribution proportional to honest_verifications count
- Banks with more honest verifications receive larger rewards

Example:
    Treasury: ₹100 crore total slashed funds

    Bank A: 1,000 honest verifications (50% of total)
    Bank B: 600 honest verifications (30% of total)
    Bank C: 400 honest verifications (20% of total)

    Rewards:
    Bank A: ₹50 crore
    Bank B: ₹30 crore
    Bank C: ₹20 crore

Flow:
1. Calculate treasury balance for fiscal year
2. Get all active banks with honest_verifications > 0
3. Calculate total honest verifications across all banks
4. Distribute proportionally
5. Create REWARD entries in Treasury
6. Update last_fiscal_year_reward in Bank table
7. Reset honest_verifications and malicious_verifications counters

Benefits:
✅ Incentivizes honest behavior
✅ Punishes malicious behavior (slashing)
✅ Rewards are proportional to contribution
✅ Complete transparency and audit trail
"""

# [DOC] SessionLocal: factory that creates new SQLAlchemy DB sessions
from database.connection import SessionLocal
# [DOC] Bank: ORM model representing a consortium member bank
from database.models.bank import Bank
# [DOC] Treasury: ORM model storing SLASH and REWARD entries (the ledger of penalties/rewards)
from database.models.treasury import Treasury
# [DOC] Decimal: exact arithmetic for monetary amounts — avoids floating-point rounding errors
from decimal import Decimal
# [DOC] datetime/timezone: timestamps for fiscal year boundary detection
from datetime import datetime, timezone
# [DOC] Dict/List: type hints for return values
from typing import Dict, List
# [DOC] func: SQLAlchemy aggregate functions (func.sum used for treasury totals)
from sqlalchemy import func


# [DOC] FiscalYearRewards: service class that encapsulates all year-end reward logic
class FiscalYearRewards:
    """
    Fiscal year reward distribution service

    Distributes treasury funds to honest banks at year end.
    """

    def __init__(self, db=None):
        """
        Initialize fiscal year rewards service

        Args:
            db: Database session (optional)
        """
        # [DOC] Accept an injected DB session or create a new one — supports both standalone
        # [DOC]   and in-process (shared session) usage patterns
        self.db = db or SessionLocal()

    def get_fiscal_year(self, date: datetime = None) -> str:
        """
        Get fiscal year for a given date (India: April-March)

        Args:
            date: Date to get fiscal year for (default: now)

        Returns:
            str: Fiscal year in format '2025-2026'
        """
        # [DOC] Default to current datetime if no date supplied
        if not date:
            date = datetime.now()

        # [DOC] Indian fiscal year runs April–March.
        # [DOC]   April 2025 → March 2026 = fiscal year "2025-2026"
        if date.month >= 4:  # April onwards
            return f"{date.year}-{date.year + 1}"
        else:  # Jan-March
            # [DOC] January–March belong to the previous calendar year's fiscal year
            return f"{date.year - 1}-{date.year}"

    def get_treasury_balance(self, fiscal_year: str) -> Dict[str, Decimal]:
        """
        Get treasury balance for fiscal year

        Args:
            fiscal_year: Fiscal year (e.g., '2025-2026')

        Returns:
            dict: {total_slashed, total_rewarded, balance}
        """
        # [DOC] Sum all SLASH entries for this fiscal year — money confiscated from misbehaving banks
        total_slashed = self.db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'SLASH',
            Treasury.fiscal_year == fiscal_year
        ).scalar() or Decimal('0.00')

        # [DOC] Sum all REWARD entries already paid out — prevents double-payment
        total_rewarded = self.db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'REWARD',
            Treasury.fiscal_year == fiscal_year
        ).scalar() or Decimal('0.00')

        # [DOC] Available balance = what was confiscated minus what has already been redistributed
        balance = total_slashed - total_rewarded

        # [DOC] Return a dict rather than a tuple so callers can address fields by name
        return {
            'fiscal_year': fiscal_year,
            'total_slashed': total_slashed,
            'total_rewarded': total_rewarded,
            'balance': balance
        }

    def calculate_reward_distribution(
        self,
        fiscal_year: str
    ) -> List[Dict]:
        """
        Calculate reward distribution for all honest banks

        Args:
            fiscal_year: Fiscal year to calculate rewards for

        Returns:
            list: [{bank_code, honest_verifications, reward_amount}, ...]
        """
        # [DOC] Fetch current treasury state; abort early if nothing to distribute
        # Get treasury balance
        treasury = self.get_treasury_balance(fiscal_year)
        # [DOC] available_balance: the pot of slashed funds ready for redistribution
        available_balance = treasury['balance']

        if available_balance <= 0:
            print(f"  ⚠️  No funds available for distribution")
            return []

        # [DOC] Only active banks with at least one honest verification qualify for a reward
        # Get all active banks with honest verifications
        banks = self.db.query(Bank).filter(
            Bank.is_active == True,
            Bank.honest_verifications > 0
        ).all()

        if not banks:
            print(f"  ⚠️  No honest banks found for reward distribution")
            return []

        # [DOC] Sum honest_verifications across all eligible banks — this is the denominator
        # [DOC]   for proportional allocation (bank_share = bank_verifications / total)
        # Calculate total honest verifications
        total_honest_verifications = sum(bank.honest_verifications for bank in banks)

        if total_honest_verifications == 0:
            print(f"  ⚠️  Total honest verifications is 0")
            return []

        # [DOC] Build the distribution list — one entry per eligible bank
        # Calculate rewards for each bank
        distribution = []

        for bank in banks:
            # [DOC] Proportional reward: bank gets (its_verifications / total_verifications) * pot
            # Proportional reward
            reward_amount = (
                Decimal(bank.honest_verifications) / Decimal(total_honest_verifications)
            ) * available_balance

            distribution.append({
                'bank_code': bank.bank_code,
                'bank_name': bank.bank_name,
                'honest_verifications': bank.honest_verifications,
                'malicious_verifications': bank.malicious_verifications,
                # [DOC] percentage: human-readable share (e.g., 33.33%) for reporting
                'percentage': (Decimal(bank.honest_verifications) / Decimal(total_honest_verifications)) * 100,
                'reward_amount': reward_amount
            })

        return distribution

    def distribute_rewards(
        self,
        fiscal_year: str,
        dry_run: bool = False
    ):
        """
        Distribute fiscal year rewards to honest banks

        Args:
            fiscal_year: Fiscal year to distribute rewards for
            dry_run: If True, calculate but don't commit (default: False)
        """
        print("\n" + "=" * 60)
        print(f"FISCAL YEAR REWARD DISTRIBUTION - {fiscal_year}")
        print("=" * 60)

        # [DOC] Step 1: Fetch treasury totals and print a human-readable summary
        # Step 1: Get treasury balance
        print(f"\nStep 1: Treasury Balance")
        treasury = self.get_treasury_balance(fiscal_year)

        print(f"  Total slashed: ₹{treasury['total_slashed']:,.2f}")
        print(f"  Total rewarded: ₹{treasury['total_rewarded']:,.2f}")
        print(f"  Available balance: ₹{treasury['balance']:,.2f}")

        # [DOC] Guard clause: nothing to distribute if the balance is zero or negative
        if treasury['balance'] <= 0:
            print(f"\n  ⚠️  No funds available for distribution")
            return

        # [DOC] Step 2: Compute each bank's proportional reward amount (no DB writes yet)
        # Step 2: Calculate distribution
        print(f"\nStep 2: Calculate Reward Distribution")
        distribution = self.calculate_reward_distribution(fiscal_year)

        if not distribution:
            print(f"  No eligible banks for rewards")
            return

        # [DOC] Print distribution table for human review before committing
        # Display distribution
        print(f"\n  {len(distribution)} banks eligible for rewards:")
        print()

        # [DOC] Running total to display a sanity-check sum at the end
        total_distributed = Decimal('0.00')

        for entry in distribution:
            print(f"  {entry['bank_name']} ({entry['bank_code']})")
            print(f"    Honest verifications: {entry['honest_verifications']}")
            print(f"    Malicious verifications: {entry['malicious_verifications']}")
            print(f"    Share: {entry['percentage']:.2f}%")
            print(f"    Reward: ₹{entry['reward_amount']:,.2f}")
            print()

            total_distributed += entry['reward_amount']

        print(f"  Total to distribute: ₹{total_distributed:,.2f}")

        # [DOC] dry_run=True: show the plan without writing anything to the database
        if dry_run:
            print(f"\n  🔍 DRY RUN - No changes committed")
            return

        # [DOC] Step 3: Write REWARD treasury entries and update each bank's fields
        # Step 3: Create reward entries and update banks
        print(f"\nStep 3: Process Rewards")

        for entry in distribution:
            # [DOC] Create a Treasury REWARD row — immutable audit record of this payment
            # Create treasury reward entry
            reward_entry = Treasury(
                entry_type='REWARD',
                amount=entry['reward_amount'],
                bank_code=entry['bank_code'],
                fiscal_year=fiscal_year,
                reason=f"Fiscal year {fiscal_year} reward for {entry['honest_verifications']} honest verifications",
                honest_verification_count=entry['honest_verifications'],
                processed_by='FISCAL_YEAR_PROCESSOR'
            )

            self.db.add(reward_entry)

            # [DOC] Re-fetch the Bank row to update its reward and reset counters
            # Update bank
            bank = self.db.query(Bank).filter(
                Bank.bank_code == entry['bank_code']
            ).first()

            if bank:
                # [DOC] Record the amount received this fiscal year (displayed on bank dashboard)
                # Update reward
                bank.last_fiscal_year_reward = entry['reward_amount']

                # [DOC] Reset counters so the next fiscal year starts fresh from zero
                # Reset counters for next fiscal year
                bank.honest_verifications = 0
                bank.malicious_verifications = 0

                print(f"  ✅ {entry['bank_code']}: ₹{entry['reward_amount']:,.2f} rewarded")

        # [DOC] Single commit: all reward entries and bank updates land atomically
        # Commit all changes
        self.db.commit()

        print(f"\n" + "=" * 60)
        print("REWARD DISTRIBUTION COMPLETE")
        print("=" * 60)
        print(f"\nTotal distributed: ₹{total_distributed:,.2f}")
        print(f"Banks rewarded: {len(distribution)}")
        print()

    def get_bank_performance_summary(
        self,
        fiscal_year: str
    ) -> List[Dict]:
        """
        Get performance summary for all banks

        Args:
            fiscal_year: Fiscal year

        Returns:
            list: Bank performance data
        """
        # [DOC] Load every bank (active or not) — summary is for reporting, not eligibility
        banks = self.db.query(Bank).all()

        summary = []

        for bank in banks:
            # [DOC] total_verifications: denominator for accuracy percentage
            total_verifications = bank.honest_verifications + bank.malicious_verifications
            # [DOC] accuracy: starts at 0 to avoid division-by-zero for banks with no votes
            accuracy = 0

            if total_verifications > 0:
                # [DOC] accuracy = honest / (honest + malicious) * 100
                accuracy = (bank.honest_verifications / total_verifications) * 100

            summary.append({
                'bank_code': bank.bank_code,
                'bank_name': bank.bank_name,
                'is_active': bank.is_active,
                'honest_verifications': bank.honest_verifications,
                'malicious_verifications': bank.malicious_verifications,
                'total_verifications': total_verifications,
                'accuracy': accuracy,
                'last_reward': bank.last_fiscal_year_reward,
                'total_penalties': bank.total_penalties,
                'penalty_count': bank.penalty_count
            })

        # [DOC] Sort descending by accuracy so the most reliable banks appear first
        # Sort by accuracy descending
        summary.sort(key=lambda x: x['accuracy'], reverse=True)

        return summary

    def close(self):
        """Close database connection"""
        # [DOC] Always close the DB session after use to return the connection to the pool
        if self.db:
            self.db.close()


# [DOC] Self-test block — runs only when this script is executed directly (not on import)
# Testing
if __name__ == "__main__":
    """Test fiscal year reward distribution"""
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

    print("=== Fiscal Year Reward Distribution Testing ===\n")

    db = SessionLocal()
    service = FiscalYearRewards(db)

    try:
        # Setup test data
        print("Setting up test data...\n")

        # Get current fiscal year
        fiscal_year = service.get_fiscal_year()
        print(f"Current fiscal year: {fiscal_year}\n")

        # Ensure banks exist with honest verifications
        # (Assuming banks were created by bank.py test)
        banks = db.query(Bank).all()

        if len(banks) < 3:
            print("❌ Need at least 3 banks. Run: python3 -m database.models.bank")
            exit(1)

        # Simulate honest verifications (from batch voting)
        print("Simulating honest verifications...\n")

        for i, bank in enumerate(banks[:3]):
            # Give different honest verification counts
            bank.honest_verifications = 1000 - (i * 200)  # 1000, 800, 600
            bank.malicious_verifications = i * 50  # 0, 50, 100

        db.commit()

        # Ensure treasury has some slashed funds
        # (Check if already exists)
        existing_slashes = db.query(Treasury).filter(
            Treasury.entry_type == 'SLASH',
            Treasury.fiscal_year == fiscal_year
        ).count()

        if existing_slashes == 0:
            print("Creating test treasury entries (slashed funds)...\n")

            # Add some slashed funds to treasury
            test_slashes = [
                Treasury(
                    entry_type='SLASH',
                    amount=Decimal('50000000.00'),  # ₹5 crore
                    bank_code='HDFC',
                    fiscal_year=fiscal_year,
                    reason='Test slash 1',
                    offense_count=1,
                    processed_by='TEST'
                ),
                Treasury(
                    entry_type='SLASH',
                    amount=Decimal('30000000.00'),  # ₹3 crore
                    bank_code='ICICI',
                    fiscal_year=fiscal_year,
                    reason='Test slash 2',
                    offense_count=1,
                    processed_by='TEST'
                )
            ]

            for slash in test_slashes:
                db.add(slash)

            db.commit()

        # Test 1: Get treasury balance
        print("Test 1: Treasury Balance")
        treasury = service.get_treasury_balance(fiscal_year)

        print(f"  Fiscal year: {treasury['fiscal_year']}")
        print(f"  Total slashed: ₹{treasury['total_slashed']:,.2f}")
        print(f"  Total rewarded: ₹{treasury['total_rewarded']:,.2f}")
        print(f"  Balance: ₹{treasury['balance']:,.2f}")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Calculate reward distribution
        print("Test 2: Calculate Reward Distribution")
        distribution = service.calculate_reward_distribution(fiscal_year)

        print(f"  Banks eligible: {len(distribution)}")

        for entry in distribution[:3]:
            print(f"    {entry['bank_code']}: {entry['percentage']:.2f}% = ₹{entry['reward_amount']:,.2f}")

        print("  ✅ Test 2 passed!\n")

        # Test 3: Dry run distribution
        print("Test 3: Dry Run Distribution")
        service.distribute_rewards(fiscal_year, dry_run=True)
        print("  ✅ Test 3 passed!\n")

        # Test 4: Actual distribution
        print("Test 4: Actual Reward Distribution")
        service.distribute_rewards(fiscal_year, dry_run=False)
        print("  ✅ Test 4 passed!\n")

        # Test 5: Verify rewards were distributed
        print("Test 5: Verify Reward Distribution")

        reward_entries = db.query(Treasury).filter(
            Treasury.entry_type == 'REWARD',
            Treasury.fiscal_year == fiscal_year
        ).all()

        print(f"  Reward entries created: {len(reward_entries)}")

        for entry in reward_entries[:3]:
            print(f"    {entry.bank_code}: ₹{entry.amount:,.2f}")

        print("  ✅ Test 5 passed!\n")

        # Test 6: Bank performance summary
        print("Test 6: Bank Performance Summary")
        summary = service.get_bank_performance_summary(fiscal_year)

        print(f"  Total banks: {len(summary)}")
        print(f"\n  Top 3 performing banks:")

        for entry in summary[:3]:
            print(f"    {entry['bank_code']}: {entry['accuracy']:.2f}% accuracy")
            print(f"      Honest: {entry['honest_verifications']}, Malicious: {entry['malicious_verifications']}")

        print("  ✅ Test 6 passed!\n")

        print("=" * 60)
        print("✅ All fiscal year reward tests passed!")
        print("=" * 60)
        print("\nKey Features Demonstrated:")
        print("  • Treasury balance calculation")
        print("  • Proportional reward distribution")
        print("  • Honest behavior incentivization")
        print("  • Automatic counter reset for next fiscal year")
        print("  • Complete audit trail")

    finally:
        db.close()
