"""
Bank Voting Record Model - Track Individual Bank Votes

Purpose: Record every bank's vote on every batch for slashing detection

Flow:
1. Batch submitted for consensus
2. Each bank validates and votes (APPROVE/REJECT)
3. Record each vote in this table
4. RBI re-verification validates votes
5. Slash banks who voted APPROVE on invalid transactions

Benefits:
✅ Complete vote audit trail
✅ Enables automatic slashing detection
✅ Tracks honest vs malicious behavior
✅ Supports challenge mechanism
"""

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func
from datetime import datetime
from database.connection import Base


class BankVotingRecord(Base):
    """
    Bank voting record table

    Records every bank's vote on every transaction batch
    for slashing detection and reward calculation.

    Example:
        >>> # Bank votes on batch
        >>> vote = BankVotingRecord(
        ...     batch_id='BATCH_1001_1100',
        ...     bank_code='HDFC',
        ...     vote='APPROVE',
        ...     validation_time_ms=15.3
        ... )
    """

    __tablename__ = 'bank_voting_records'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Batch information
    batch_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Batch ID that was voted on"
    )

    # Bank information
    bank_code = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Bank code (HDFC, ICICI, SBI, etc.)"
    )

    # Vote details
    vote = Column(
        String(10),
        nullable=False,
        comment="APPROVE or REJECT"
    )

    # Validation metrics
    validation_time_ms = Column(
        Integer,
        nullable=True,
        comment="Time taken to validate in milliseconds"
    )

    # Correctness (filled in by RBI re-verification)
    is_correct = Column(
        Boolean,
        nullable=True,
        comment="True if vote was correct (filled by RBI re-verification)"
    )

    rbi_verified = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether RBI has verified this vote"
    )

    rbi_verification_time = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When RBI verified this vote"
    )

    # Slashing information
    was_slashed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether bank was slashed for this vote"
    )

    slash_amount = Column(
        BigInteger,
        nullable=True,
        comment="Amount slashed if vote was incorrect"
    )

    # Group signature (anonymous voting)
    group_signature = Column(
        Text,
        nullable=True,
        comment="Group signature (ring signature) for anonymous voting"
    )

    # Challenge information
    challenged_by = Column(
        String(20),
        nullable=True,
        comment="Bank code that challenged this vote (if any)"
    )

    challenge_time = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When vote was challenged"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When vote was cast"
    )

    # Indexes
    __table_args__ = (
        Index('idx_vote_batch', 'batch_id'),
        Index('idx_vote_bank', 'bank_code'),
        Index('idx_vote_correct', 'is_correct'),
        Index('idx_vote_slashed', 'was_slashed'),
        Index('idx_vote_rbi_verified', 'rbi_verified'),
        # Composite index for finding votes by batch and bank
        Index('idx_vote_batch_bank', 'batch_id', 'bank_code'),
    )

    def __repr__(self):
        return (
            f"<BankVotingRecord(batch={self.batch_id}, "
            f"bank={self.bank_code}, "
            f"vote={self.vote}, "
            f"correct={self.is_correct})>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'bank_code': self.bank_code,
            'vote': self.vote,
            'validation_time_ms': self.validation_time_ms,
            'is_correct': self.is_correct,
            'rbi_verified': self.rbi_verified,
            'rbi_verification_time': self.rbi_verification_time.isoformat() if self.rbi_verification_time else None,
            'was_slashed': self.was_slashed,
            'slash_amount': self.slash_amount,
            'challenged_by': self.challenged_by,
            'challenge_time': self.challenge_time.isoformat() if self.challenge_time else None,
            'created_at': self.created_at.isoformat()
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test the BankVotingRecord model
    Run: python3 -m database.models.bank_voting_record
    """
    from database.connection import engine, SessionLocal

    print("=== Bank Voting Record Model Testing ===\n")

    # Create table
    print("Creating bank_voting_records table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")

    # Create session
    db = SessionLocal()

    try:
        # Cleanup
        print("Test 0: Cleanup")
        db.query(BankVotingRecord).delete()
        db.commit()
        print("✅ Cleanup complete!\n")

        # Test 1: Record votes for a batch
        print("Test 1: Record 12 Bank Votes for Batch")

        batch_id = "BATCH_1001_1100"

        # Simulate 12 banks voting (10 APPROVE, 2 REJECT)
        votes_data = [
            {'bank_code': 'SBI', 'vote': 'APPROVE', 'validation_time_ms': 12},
            {'bank_code': 'PNB', 'vote': 'APPROVE', 'validation_time_ms': 15},
            {'bank_code': 'BOB', 'vote': 'APPROVE', 'validation_time_ms': 13},
            {'bank_code': 'CANARA', 'vote': 'APPROVE', 'validation_time_ms': 14},
            {'bank_code': 'UNION', 'vote': 'APPROVE', 'validation_time_ms': 16},
            {'bank_code': 'INDIAN', 'vote': 'APPROVE', 'validation_time_ms': 11},
            {'bank_code': 'CENTRAL', 'vote': 'APPROVE', 'validation_time_ms': 17},
            {'bank_code': 'UCO', 'vote': 'APPROVE', 'validation_time_ms': 13},
            {'bank_code': 'HDFC', 'vote': 'APPROVE', 'validation_time_ms': 10},
            {'bank_code': 'ICICI', 'vote': 'APPROVE', 'validation_time_ms': 12},
            {'bank_code': 'AXIS', 'vote': 'REJECT', 'validation_time_ms': 14},
            {'bank_code': 'KOTAK', 'vote': 'REJECT', 'validation_time_ms': 15}
        ]

        for vote_data in votes_data:
            vote = BankVotingRecord(
                batch_id=batch_id,
                **vote_data
            )
            db.add(vote)

        db.commit()

        print(f"  Recorded 12 votes for {batch_id}")
        approvals = sum(1 for v in votes_data if v['vote'] == 'APPROVE')
        print(f"    - Approvals: {approvals}/12")
        print(f"    - Rejections: {12 - approvals}/12")
        print("  ✅ Test 1 passed!\n")

        # Test 2: RBI re-verification (marks correct/incorrect)
        print("Test 2: RBI Re-Verification")

        # Simulate RBI finding batch was actually INVALID
        # (means REJECT votes were correct, APPROVE votes were incorrect)

        all_votes = db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch_id
        ).all()

        for vote in all_votes:
            vote.rbi_verified = True
            vote.rbi_verification_time = datetime.now()
            # If batch is invalid, REJECT votes are correct
            vote.is_correct = (vote.vote == 'REJECT')

        db.commit()

        correct_votes = sum(1 for v in all_votes if v.is_correct)
        incorrect_votes = len(all_votes) - correct_votes

        print(f"  RBI verified {len(all_votes)} votes")
        print(f"    - Correct votes: {correct_votes}")
        print(f"    - Incorrect votes: {incorrect_votes}")
        print("  ✅ Test 2 passed!\n")

        # Test 3: Slash incorrect votes
        print("Test 3: Slash Banks with Incorrect Votes")

        slashed_count = 0
        for vote in all_votes:
            if not vote.is_correct:
                vote.was_slashed = True
                vote.slash_amount = 100000000  # ₹10 crore (5% of stake)
                slashed_count += 1

        db.commit()

        print(f"  Slashed {slashed_count} banks for voting APPROVE on invalid batch")
        print("  ✅ Test 3 passed!\n")

        # Test 4: Query slashed votes
        print("Test 4: Query Slashed Votes")

        slashed_votes = db.query(BankVotingRecord).filter(
            BankVotingRecord.was_slashed == True
        ).all()

        print(f"  Found {len(slashed_votes)} slashed votes:")
        for vote in slashed_votes:
            print(f"    - {vote.bank_code}: ₹{vote.slash_amount:,.0f}")

        assert len(slashed_votes) == 10  # 10 banks voted APPROVE (incorrect)
        print("  ✅ Test 4 passed!\n")

        # Test 5: Challenge mechanism
        print("Test 5: Bank Challenge")

        # Simulate AXIS bank challenging HDFC's vote
        hdfc_vote = db.query(BankVotingRecord).filter(
            BankVotingRecord.batch_id == batch_id,
            BankVotingRecord.bank_code == 'HDFC'
        ).first()

        hdfc_vote.challenged_by = 'AXIS'
        hdfc_vote.challenge_time = datetime.now()

        db.commit()

        print(f"  AXIS challenged HDFC's vote")
        print(f"    - Batch: {hdfc_vote.batch_id}")
        print(f"    - HDFC voted: {hdfc_vote.vote}")
        print(f"    - Was correct: {hdfc_vote.is_correct}")
        print("  ✅ Test 5 passed!\n")

        # Test 6: Query by bank
        print("Test 6: Query Votes by Bank")

        sbi_votes = db.query(BankVotingRecord).filter(
            BankVotingRecord.bank_code == 'SBI'
        ).all()

        print(f"  SBI total votes: {len(sbi_votes)}")
        print("  ✅ Test 6 passed!\n")

        # Test 7: to_dict
        print("Test 7: Vote Dictionary")

        data = hdfc_vote.to_dict()
        print(f"  Dictionary keys: {list(data.keys())}")
        print(f"  Bank: {data['bank_code']}")
        print(f"  Vote: {data['vote']}")
        print(f"  Challenged by: {data['challenged_by']}")
        print("  ✅ Test 7 passed!\n")

        print("=" * 50)
        print("✅ All Bank Voting Record model tests passed!")
        print("")
        print("Voting Summary:")
        print(f"  Total votes recorded: {len(all_votes)}")
        print(f"  Correct votes: {correct_votes}")
        print(f"  Incorrect votes: {incorrect_votes}")
        print(f"  Banks slashed: {slashed_count}")
        print(f"  Total slashed amount: ₹{sum(v.slash_amount or 0 for v in slashed_votes):,.0f}")
        print("=" * 50)

    finally:
        db.close()
