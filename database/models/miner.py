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
from database.connection import Base
from decimal import Decimal


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

    __tablename__ = "miner_statistics"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Miner identification (foreign key to users table)
    user_idx = Column(
        String(255),
        ForeignKey('users.idx', ondelete='CASCADE'),
        nullable=False,
        unique=True,  # One statistics record per user
        index=True
    )

    # Mining statistics
    total_blocks_mined = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of blocks successfully mined by this user"
    )

    total_fees_earned = Column(
        Numeric(15, 2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total mining fees earned (0.5% of transaction fees)"
    )

    # Performance metrics
    avg_mining_time_seconds = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Average time taken to mine a block (in seconds)"
    )

    total_hash_attempts = Column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total number of hash attempts made (across all mining)"
    )

    hash_rate_per_second = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Average hash rate (hashes per second)"
    )

    # Competition results
    blocks_won = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times this miner won the mining race (first to find nonce)"
    )

    blocks_lost = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times found solution but another miner was faster"
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this miner is currently actively mining"
    )

    last_mined_at = Column(
        DateTime,
        nullable=True,
        comment="Timestamp of last successful block mine"
    )

    # Timestamps
    started_mining_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="When this user first started mining"
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Last time statistics were updated"
    )

    # Relationships
    user = relationship("User", backref="miner_statistics", lazy="joined")

    # Indexes (in addition to those defined in columns)
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
