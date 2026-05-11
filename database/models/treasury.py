"""
Treasury Model - Slashed Funds Management

Purpose: Track slashed funds from malicious banks and distribute as rewards

Flow:
1. Bank gets slashed for malicious behavior → Funds moved to treasury
2. Throughout fiscal year → Treasury accumulates slashed amounts
3. End of fiscal year → Treasury distributes to honest banks
4. Distribution proportional to honest_verifications count

Benefits:
✅ Transparent fund management
✅ Incentivizes honest behavior
✅ Complete audit trail
✅ Fair reward distribution
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, Index
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row = one monetary event in the consortium incentive system; either a SLASH (money in) or REWARD (money out)
# [DOC] The treasury accumulates slashed stakes throughout the year and distributes them to honest banks at fiscal year end
class Treasury(Base):
    """
    Treasury table for slashed funds management

    Tracks all slashed funds from malicious banks and their
    distribution to honest banks at fiscal year end.

    Example:
        >>> # Bank slashed for malicious behavior
        >>> entry = Treasury(
        ...     entry_type='SLASH',
        ...     amount=Decimal('100000000.00'),  # ₹10 crore slashed
        ...     bank_code='HDFC',
        ...     reason='Voted APPROVE on invalid transaction',
        ...     fiscal_year='2025-2026'
        ... )
    """

    # [DOC] Maps this Python class to the 'treasury' PostgreSQL table
    __tablename__ = 'treasury'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Entry type
    # [DOC] "SLASH": funds moved FROM a misbehaving bank INTO the treasury (source of funds)
    # [DOC] "REWARD": funds moved FROM the treasury TO an honest bank at fiscal year end (distribution)
    entry_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="SLASH (funds received) or REWARD (funds distributed)"
    )

    # Amount
    # [DOC] Rupee amount involved in this event; precision=18 handles India's largest bank stakes
    # [DOC] For SLASH: amount removed from bank.stake_amount; for REWARD: amount added to bank.total_fees_earned
    amount = Column(
        Numeric(precision=18, scale=2),
        nullable=False,
        comment="Amount slashed or rewarded"
    )

    # Bank involved
    # [DOC] For SLASH: the bank_code of the bank whose stake was reduced (the offender)
    # [DOC] For REWARD: the bank_code of the bank receiving the distribution (an honest bank)
    # [DOC] NULL for system-level entries (e.g. initial treasury seeding)
    bank_code = Column(
        String(20),
        nullable=True,
        index=True,
        comment="Bank code (for SLASH: source bank, for REWARD: receiving bank)"
    )

    # Fiscal year
    # [DOC] String in "YYYY-YYYY" format, e.g. "2025-2026"; groups entries for annual reward distribution queries
    fiscal_year = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Fiscal year (e.g., '2025-2026')"
    )

    # Reason/description
    # [DOC] Human-readable explanation, e.g. "Voted APPROVE on invalid transaction (batch #1042)"
    reason = Column(
        Text,
        nullable=True,
        comment="Reason for slash or reward details"
    )

    # Metadata
    # [DOC] For SLASH rows only: which offense number this is for the offending bank (1st, 2nd, 3rd)
    # [DOC] Escalating penalties: 1st offense = 5% of stake, 2nd = 10%, 3rd = deactivation
    offense_count = Column(
        Integer,
        nullable=True,
        comment="For SLASH: which offense (1st, 2nd, 3rd for escalating penalties)"
    )

    # [DOC] For REWARD rows only: the receiving bank's honest_verifications count used in the proportional split
    # [DOC] Reward formula: bank_share = (bank.honest_verifications / total_honest_verifications) × treasury_balance
    honest_verification_count = Column(
        Integer,
        nullable=True,
        comment="For REWARD: number of honest verifications (for proportional distribution)"
    )

    # Timestamps
    # [DOC] Set automatically by the DB when the row is inserted; immutable audit trail
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When entry was created"
    )

    # [DOC] Name of the system component that created this row, e.g. "RBI_VALIDATOR" or "FISCAL_YEAR_PROCESSOR"
    processed_by = Column(
        String(100),
        nullable=True,
        comment="System component that processed this entry (e.g., 'RBI_VALIDATOR', 'FISCAL_YEAR_PROCESSOR')"
    )

    # Indexes
    # [DOC] Four indexes: by type (find all slashes or rewards), by fiscal year (annual reports), by bank, by time
    __table_args__ = (
        Index('idx_treasury_type', 'entry_type'),
        Index('idx_treasury_fiscal_year', 'fiscal_year'),
        Index('idx_treasury_bank', 'bank_code'),
        Index('idx_treasury_created', 'created_at'),
    )

    def __repr__(self):
        return (
            f"<Treasury(type={self.entry_type}, "
            f"amount=₹{self.amount}, "
            f"bank={self.bank_code}, "
            f"fiscal_year={self.fiscal_year})>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'entry_type': self.entry_type,
            'amount': str(self.amount),
            'bank_code': self.bank_code,
            'fiscal_year': self.fiscal_year,
            'reason': self.reason,
            'offense_count': self.offense_count,
            'honest_verification_count': self.honest_verification_count,
            'created_at': self.created_at.isoformat(),
            'processed_by': self.processed_by
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test the Treasury model
    Run: python3 -m database.models.treasury
    """
    from database.connection import engine, SessionLocal

    print("=== Treasury Model Testing ===\n")

    # Create table
    print("Creating treasury table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")

    # Create session
    db = SessionLocal()

    try:
        # Cleanup
        print("Test 0: Cleanup")
        db.query(Treasury).delete()
        db.commit()
        print("✅ Cleanup complete!\n")

        # Test 1: Record slashed funds
        print("Test 1: Record Slashed Funds")

        slash_entry = Treasury(
            entry_type='SLASH',
            amount=Decimal('100000000.00'),  # ₹10 crore
            bank_code='HDFC',
            fiscal_year='2025-2026',
            reason='Voted APPROVE on invalid transaction (batch #1042)',
            offense_count=1,
            processed_by='RBI_VALIDATOR'
        )

        db.add(slash_entry)
        db.commit()

        print(f"  Slashed: ₹{slash_entry.amount:,.2f} from {slash_entry.bank_code}")
        print(f"  Reason: {slash_entry.reason}")
        print("  ✅ Test 1 passed!\n")

        # Test 2: Record multiple slashes
        print("Test 2: Record Multiple Slashes")

        slashes = [
            Treasury(
                entry_type='SLASH',
                amount=Decimal('50000000.00'),  # ₹5 crore
                bank_code='ICICI',
                fiscal_year='2025-2026',
                reason='Voted APPROVE on invalid transaction (batch #1055)',
                offense_count=1,
                processed_by='RBI_VALIDATOR'
            ),
            Treasury(
                entry_type='SLASH',
                amount=Decimal('200000000.00'),  # ₹20 crore (2nd offense)
                bank_code='HDFC',
                fiscal_year='2025-2026',
                reason='Second offense - voted APPROVE on invalid transaction (batch #1089)',
                offense_count=2,
                processed_by='RBI_VALIDATOR'
            )
        ]

        for slash in slashes:
            db.add(slash)

        db.commit()

        print(f"  Recorded {len(slashes)} additional slashes")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Calculate total treasury balance
        print("Test 3: Calculate Treasury Balance")

        total_slashed = db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'SLASH',
            Treasury.fiscal_year == '2025-2026'
        ).scalar() or Decimal('0.00')

        total_rewarded = db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'REWARD',
            Treasury.fiscal_year == '2025-2026'
        ).scalar() or Decimal('0.00')

        balance = total_slashed - total_rewarded

        print(f"  Total slashed: ₹{total_slashed:,.2f}")
        print(f"  Total rewarded: ₹{total_rewarded:,.2f}")
        print(f"  Balance: ₹{balance:,.2f}")

        assert balance == Decimal('350000000.00')  # ₹35 crore total
        print("  ✅ Test 3 passed!\n")

        # Test 4: Record reward distribution
        print("Test 4: Record Reward Distribution (Fiscal Year End)")

        # Simulate distributing treasury to honest banks
        rewards = [
            Treasury(
                entry_type='REWARD',
                amount=Decimal('150000000.00'),  # ₹15 crore
                bank_code='SBI',
                fiscal_year='2025-2026',
                reason='Fiscal year 2025-2026 reward',
                honest_verification_count=1200,
                processed_by='FISCAL_YEAR_PROCESSOR'
            ),
            Treasury(
                entry_type='REWARD',
                amount=Decimal('100000000.00'),  # ₹10 crore
                bank_code='PNB',
                fiscal_year='2025-2026',
                reason='Fiscal year 2025-2026 reward',
                honest_verification_count=800,
                processed_by='FISCAL_YEAR_PROCESSOR'
            ),
            Treasury(
                entry_type='REWARD',
                amount=Decimal('100000000.00'),  # ₹10 crore
                bank_code='AXIS',
                fiscal_year='2025-2026',
                reason='Fiscal year 2025-2026 reward',
                honest_verification_count=800,
                processed_by='FISCAL_YEAR_PROCESSOR'
            )
        ]

        for reward in rewards:
            db.add(reward)

        db.commit()

        print(f"  Distributed rewards to {len(rewards)} honest banks")
        print("  ✅ Test 4 passed!\n")

        # Test 5: Query by fiscal year
        print("Test 5: Query Treasury by Fiscal Year")

        entries = db.query(Treasury).filter(
            Treasury.fiscal_year == '2025-2026'
        ).order_by(Treasury.created_at).all()

        print(f"  Total entries for 2025-2026: {len(entries)}")
        print(f"    - Slashes: {sum(1 for e in entries if e.entry_type == 'SLASH')}")
        print(f"    - Rewards: {sum(1 for e in entries if e.entry_type == 'REWARD')}")

        assert len(entries) == 6
        print("  ✅ Test 5 passed!\n")

        # Test 6: to_dict
        print("Test 6: Treasury Dictionary")

        data = slash_entry.to_dict()
        print(f"  Dictionary keys: {list(data.keys())}")
        print(f"  Type: {data['entry_type']}")
        print(f"  Amount: ₹{data['amount']}")
        print("  ✅ Test 6 passed!\n")

        print("=" * 50)
        print("✅ All Treasury model tests passed!")
        print("")
        print("Treasury Summary:")
        print(f"  Total entries: {len(entries)}")
        print(f"  Total slashed: ₹{total_slashed:,.2f}")
        new_total_rewarded = db.query(func.sum(Treasury.amount)).filter(
            Treasury.entry_type == 'REWARD',
            Treasury.fiscal_year == '2025-2026'
        ).scalar() or Decimal('0.00')
        new_balance = total_slashed - new_total_rewarded
        print(f"  Total rewarded: ₹{new_total_rewarded:,.2f}")
        print(f"  Remaining balance: ₹{new_balance:,.2f}")
        print("=" * 50)

    finally:
        db.close()
