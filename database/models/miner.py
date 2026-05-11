"""
Miner Statistics Model - Track User Mining Performance
Purpose: Enable competitive mining and track mining rewards

Table Structure:
- id: Auto-increment primary key
- user_idx: Foreign key to users table (which user is mining)
- total_blocks_mined: Count of successfully mined blocks
- total_fees_earned: Total 0.5% mining fees earned
- blocks_won: Times won the mining race (first to find nonce)
- blocks_lost: Times found solution but another miner was faster
- hash_rate_per_second: Average mining performance
- is_active: Whether user is currently mining
- started_mining_at: When user first started mining
- last_mined_at: Last successful block mine
- updated_at: Last statistics update

Mining Model:
- Competitive mining: Multiple users race to find valid nonce
- Winner: First to find valid block hash with required difficulty
- Reward: 0.5% of transaction fees in the block
- Losers: Get nothing (wasted computation)
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, BigInteger, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base
from decimal import Decimal


# [DOC] One row per mining user; stores their cumulative mining performance and reward history
# [DOC] Mining is competitive: multiple users race to find a valid PoW nonce; only the winner earns a reward
class MinerStatistics(Base):
    """
    Miner statistics table

    Tracks performance and rewards for users who participate in competitive mining.

    Each miner has:
    - Performance metrics (hash rate, mining time)
    - Competition results (blocks won vs lost)
    - Financial tracking (total fees earned)
    - Activity status (currently mining or stopped)

    Example:
        >>> from database.connection import SessionLocal
        >>>
        >>> # Start mining for a user
        >>> db = SessionLocal()
        >>> miner = MinerStatistics(
        ...     user_idx="IDX_abc123...",
        ...     is_active=True
        ... )
        >>> db.add(miner)
        >>> db.commit()
        >>>
        >>> # Update after winning a block
        >>> miner.total_blocks_mined += 1
        >>> miner.blocks_won += 1
        >>> miner.total_fees_earned += Decimal('50.00')  # 0.5% of ₹10,000
        >>> miner.last_mined_at = datetime.utcnow()
        >>> db.commit()
    """

    # [DOC] Maps this Python class to the 'miner_statistics' PostgreSQL table
    __tablename__ = "miner_statistics"

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID only
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Miner identification (foreign key to users table)
    # [DOC] Permanent IDX pseudonym of the user who is mining; foreign key to users.idx
    # [DOC] UNIQUE constraint: each user has at most one statistics row (counters are cumulative)
    # [DOC] CASCADE delete: if the user is deleted, their mining stats are also deleted
    user_idx = Column(
        String(255),
        ForeignKey('users.idx', ondelete='CASCADE'),
        nullable=False,
        unique=True,  # One statistics record per user
        index=True
    )

    # Mining statistics
    # [DOC] Count of blocks this miner has successfully mined (i.e. blocks_won); incremented only when this miner finds the nonce first
    total_blocks_mined = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of blocks successfully mined by this user"
    )

    # [DOC] Cumulative rupee earnings from mining; each win adds 0.5% of the total transaction fees in that block
    # [DOC] Example: block with 100 transactions of ₹1,000 each → fees = ₹1,500 (1.5%) → miner earns ₹50
    total_fees_earned = Column(
        Numeric(15, 2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total mining fees earned (0.5% of transaction fees)"
    )

    # Performance metrics
    # [DOC] Running average of seconds taken to mine each block; lower is better; updated after every win
    avg_mining_time_seconds = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Average time taken to mine a block (in seconds)"
    )

    # [DOC] Total number of SHA-256 hash computations this miner has performed across all mining sessions
    # [DOC] BigInteger because at difficulty=4, a miner may need millions of attempts per block
    total_hash_attempts = Column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total number of hash attempts made (across all mining)"
    )

    # [DOC] Average hashes computed per second by this miner; derived from total_hash_attempts / total mining time
    hash_rate_per_second = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Average hash rate (hashes per second)"
    )

    # Competition results
    # [DOC] Times this miner found a valid nonce before any other miner; equals total_blocks_mined
    blocks_won = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times this miner won the mining race (first to find nonce)"
    )

    # [DOC] Times this miner found a valid nonce but another miner submitted it first; wasted computation, no reward
    blocks_lost = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times found solution but another miner was faster"
    )

    # Status
    # [DOC] True while the mining_worker.py daemon is actively running for this user; set to False if they stop mining
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this miner is currently actively mining"
    )

    # [DOC] UTC datetime of the most recent block this miner successfully mined; NULL if they have never won
    last_mined_at = Column(
        DateTime,
        nullable=True,
        comment="Timestamp of last successful block mine"
    )

    # Timestamps
    # [DOC] UTC datetime when this user first registered as a miner and this row was created
    started_mining_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="When this user first started mining"
    )

    # [DOC] Auto-updated by the DB whenever any statistic field is changed; used to detect stale mining sessions
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Last time statistics were updated"
    )

    # Relationships
    # [DOC] ORM relationship to the User row; enables miner.user.idx lookups without extra queries
    user = relationship("User", backref="miner_statistics", lazy="joined")

    # Indexes (in addition to those defined in columns)
    # [DOC] Four indexes: by user_idx, by active status (find active miners), by blocks_won (leaderboard), by fees_earned (leaderboard)
    __table_args__ = (
        Index('idx_miner_user', 'user_idx'),
        Index('idx_miner_active', 'is_active'),
        Index('idx_miner_blocks_won', 'blocks_won'),
        Index('idx_miner_fees_earned', 'total_fees_earned'),
    )

    def __repr__(self):
        return (
            f"<MinerStatistics("
            f"id={self.id}, "
            f"user_idx={self.user_idx[:16]}..., "
            f"blocks_mined={self.total_blocks_mined}, "
            f"fees_earned={self.total_fees_earned}, "
            f"is_active={self.is_active}"
            f")>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'user_idx': self.user_idx,
            'total_blocks_mined': self.total_blocks_mined,
            'total_fees_earned': str(self.total_fees_earned),
            'avg_mining_time_seconds': str(self.avg_mining_time_seconds) if self.avg_mining_time_seconds else None,
            'total_hash_attempts': self.total_hash_attempts,
            'hash_rate_per_second': str(self.hash_rate_per_second) if self.hash_rate_per_second else None,
            'blocks_won': self.blocks_won,
            'blocks_lost': self.blocks_lost,
            'win_rate': round(self.blocks_won / (self.blocks_won + self.blocks_lost) * 100, 2) if (self.blocks_won + self.blocks_lost) > 0 else 0,
            'is_active': self.is_active,
            'last_mined_at': self.last_mined_at.isoformat() if self.last_mined_at else None,
            'started_mining_at': self.started_mining_at.isoformat() if self.started_mining_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def get_leaderboard(cls, db, limit=10):
        """
        Get top miners by blocks mined

        Args:
            db: Database session
            limit: Number of miners to return (default 10)

        Returns:
            List of top miners ordered by total_blocks_mined DESC
        """
        return db.query(cls).order_by(
            cls.total_blocks_mined.desc()
        ).limit(limit).all()

    @classmethod
    def get_by_fees_earned(cls, db, limit=10):
        """
        Get top miners by total fees earned

        Args:
            db: Database session
            limit: Number of miners to return (default 10)

        Returns:
            List of top miners ordered by total_fees_earned DESC
        """
        return db.query(cls).order_by(
            cls.total_fees_earned.desc()
        ).limit(limit).all()

    @classmethod
    def get_active_miners(cls, db):
        """
        Get all currently active miners

        Args:
            db: Database session

        Returns:
            List of active miners
        """
        return db.query(cls).filter(cls.is_active == True).all()

    @classmethod
    def get_active_count(cls, db):
        """
        Get count of active miners

        Args:
            db: Database session

        Returns:
            Number of currently active miners
        """
        return db.query(cls).filter(cls.is_active == True).count()


# For testing
if __name__ == "__main__":
    from database.connection import SessionLocal, engine

    # Create table
    print("Creating miner_statistics table...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Test creating a miner
    print("\nTesting miner creation...")
    miner = MinerStatistics(
        user_idx="IDX_test123",
        is_active=True
    )
    db.add(miner)
    db.commit()

    print(f"Created: {miner}")
    print(f"Dict: {miner.to_dict()}")

    # Test updating statistics
    print("\nTesting statistics update...")
    miner.total_blocks_mined = 5
    miner.blocks_won = 5
    miner.total_fees_earned = Decimal('250.00')
    db.commit()

    print(f"Updated: {miner}")

    db.close()
    print("\n✅ Miner statistics model working correctly!")
