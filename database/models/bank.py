"""
Bank Model - Consortium Banks for PoS Validation

Purpose: Store 6 consortium banks that validate private blockchain

Consortium Banks:
- Total: 6 banks (HDFC, ICICI, SBI, Axis, Kotak, YES)
- Role: Validate transactions on private blockchain
- Consensus: 4/6 must approve (PBFT)
- Rewards: Share 1% fee equally (0.167% each)

Example Flow:
1. Transaction mined on public chain (PoW)
2. 6 banks vote on private chain (PoS)
3. 4/6 approval required
4. Transaction added to private blockchain
5. All 6 banks receive equal fee share
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Index
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
from database.connection import Base


class Bank(Base):
    """
    Consortium bank table
    
    Stores information about the 6 banks that form the
    validation consortium for the private blockchain.
    
    Each bank:
    - Participates in PoS consensus (voting)
    - Receives equal share of 1% transaction fee
    - Stakes regulatory license + collateral
    - Can be penalized for misbehavior
    
    Example:
        >>> from database.connection import SessionLocal
        >>> from decimal import Decimal
        >>> 
        >>> db = SessionLocal()
        >>> 
        >>> # Create consortium bank
        >>> hdfc = Bank(
        ...     bank_code="HDFC",
        ...     bank_name="HDFC Bank Ltd",
        ...     stake_amount=Decimal('100000000.00'),  # ₹10 crore
        ...     is_active=True
        ... )
        >>> 
        >>> db.add(hdfc)
        >>> db.commit()
    """
    
    __tablename__ = 'consortium_banks'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Bank identification
    bank_code = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Short bank code (HDFC, ICICI, SBI, etc.)"
    )
    
    bank_name = Column(
        String(100),
        nullable=False,
        comment="Full bank name"
    )
    
    # Staking (Proof of Stake)
    stake_amount = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Amount staked by bank (can be slashed)"
    )
    
    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether bank is actively validating"
    )
    
    # Statistics
    total_validations = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total blocks validated by this bank"
    )
    
    total_fees_earned = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total fees earned from validation"
    )
    
    # Penalties
    penalty_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times penalized for misbehavior"
    )
    
    total_penalties = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total amount slashed as penalties"
    )
    
    # Contact information
    validator_address = Column(
        String(255),
        nullable=True,
        comment="Network address for validator node"
    )
    
    # Timestamps
    joined_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When bank joined consortium"
    )
    
    last_validation_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time bank validated a block"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_bank_code', 'bank_code'),
        Index('idx_bank_active', 'is_active'),
    )
    
    def __repr__(self):
        status = "active" if self.is_active else "inactive"
        return (
            f"<Bank(code={self.bank_code}, "
            f"name={self.bank_name}, "
            f"status={status})>"
        )
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'stake_amount': str(self.stake_amount),
            'is_active': self.is_active,
            'total_validations': self.total_validations,
            'total_fees_earned': str(self.total_fees_earned),
            'penalty_count': self.penalty_count,
            'total_penalties': str(self.total_penalties),
            'joined_at': self.joined_at.isoformat(),
            'last_validation_at': self.last_validation_at.isoformat() if self.last_validation_at else None
        }


# Example usage / testing
if __name__ == "__main__":
    """
    Test the Bank model and create the 6 consortium banks
    Run: python3 -m database.models.bank
    """
    from database.connection import engine, SessionLocal
    
    print("=== Bank Model Testing ===\n")
    
    # Create table
    print("Creating consortium_banks table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Cleanup
        print("Test 0: Cleanup")
        db.query(Bank).delete()
        db.commit()
        print("✅ Cleanup complete!\n")
        
        # Test 1: Create the 6 consortium banks
        print("Test 1: Create 6 Consortium Banks")
        
        banks_data = [
            {
                'bank_code': 'HDFC',
                'bank_name': 'HDFC Bank Ltd',
                'stake_amount': Decimal('100000000.00'),  # ₹10 crore
                'validator_address': 'validator-hdfc.idxbanking.com:8001'
            },
            {
                'bank_code': 'ICICI',
                'bank_name': 'ICICI Bank Ltd',
                'stake_amount': Decimal('100000000.00'),
                'validator_address': 'validator-icici.idxbanking.com:8002'
            },
            {
                'bank_code': 'SBI',
                'bank_name': 'State Bank of India',
                'stake_amount': Decimal('100000000.00'),
                'validator_address': 'validator-sbi.idxbanking.com:8003'
            },
            {
                'bank_code': 'AXIS',
                'bank_name': 'Axis Bank Ltd',
                'stake_amount': Decimal('100000000.00'),
                'validator_address': 'validator-axis.idxbanking.com:8004'
            },
            {
                'bank_code': 'KOTAK',
                'bank_name': 'Kotak Mahindra Bank',
                'stake_amount': Decimal('100000000.00'),
                'validator_address': 'validator-kotak.idxbanking.com:8005'
            },
            {
                'bank_code': 'YES',
                'bank_name': 'Yes Bank Ltd',
                'stake_amount': Decimal('100000000.00'),
                'validator_address': 'validator-yes.idxbanking.com:8006'
            }
        ]
        
        for bank_data in banks_data:
            bank = Bank(**bank_data)
            db.add(bank)
        
        db.commit()
        
        print(f"  Created {len(banks_data)} consortium banks")
        for bank_data in banks_data:
            print(f"    - {bank_data['bank_code']}: {bank_data['bank_name']}")
        print("  ✅ Test 1 passed!\n")
        
        # Test 2: Query all active banks
        print("Test 2: Query Active Banks")
        
        active_banks = db.query(Bank).filter(Bank.is_active == True).all()
        print(f"  Active banks: {len(active_banks)}/6")
        
        assert len(active_banks) == 6
        print("  ✅ Test 2 passed!\n")
        
        # Test 3: Update bank statistics (simulate validation)
        print("Test 3: Update Bank Statistics (Simulate Validation)")
        
        hdfc = db.query(Bank).filter(Bank.bank_code == "HDFC").first()
        
        # Simulate HDFC validating a block
        hdfc.total_validations += 1
        hdfc.total_fees_earned += Decimal('1.67')  # ₹1.67 fee (1% ÷ 6)
        hdfc.last_validation_at = datetime.now()
        
        db.commit()
        db.refresh(hdfc)
        
        print(f"  Bank: {hdfc.bank_name}")
        print(f"  Validations: {hdfc.total_validations}")
        print(f"  Fees earned: ₹{hdfc.total_fees_earned}")
        print("  ✅ Test 3 passed!\n")
        
        # Test 4: Deactivate a bank
        print("Test 4: Deactivate Bank (Remove from Consortium)")
        
        yes_bank = db.query(Bank).filter(Bank.bank_code == "YES").first()
        yes_bank.is_active = False
        db.commit()
        
        active_count = db.query(Bank).filter(Bank.is_active == True).count()
        print(f"  Deactivated: {yes_bank.bank_name}")
        print(f"  Active banks remaining: {active_count}/6")
        
        assert active_count == 5
        print("  ✅ Test 4 passed!\n")
        
        # Test 5: Apply penalty
        print("Test 5: Apply Penalty (Slash Stake)")
        
        # Simulate penalty for misbehavior
        penalty = Decimal('1000000.00')  # ₹10 lakh penalty
        
        hdfc.penalty_count += 1
        hdfc.total_penalties += penalty
        hdfc.stake_amount -= penalty  # Slash from stake
        
        db.commit()
        db.refresh(hdfc)
        
        print(f"  Bank: {hdfc.bank_name}")
        print(f"  Penalty applied: ₹{penalty:,.2f}")
        print(f"  Remaining stake: ₹{hdfc.stake_amount:,.2f}")
        print(f"  Total penalties: {hdfc.penalty_count}")
        print("  ✅ Test 5 passed!\n")
        
        # Test 6: Get bank by code
        print("Test 6: Get Bank by Code")
        
        sbi = db.query(Bank).filter(Bank.bank_code == "SBI").first()
        print(f"  Found: {sbi}")
        assert sbi.bank_name == "State Bank of India"
        print("  ✅ Test 6 passed!\n")
        
        # Test 7: to_dict
        print("Test 7: Bank Dictionary")
        
        data = hdfc.to_dict()
        print(f"  Dictionary keys: {list(data.keys())}")
        print(f"  Bank: {data['bank_name']}")
        print(f"  Stake: ₹{data['stake_amount']}")
        print("  ✅ Test 7 passed!\n")
        
        print("=" * 50)
        print("✅ All Bank model tests passed!")
        print("")
        print("Consortium Summary:")
        all_banks = db.query(Bank).all()
        print(f"  Total banks: {len(all_banks)}")
        print(f"  Active banks: {db.query(Bank).filter(Bank.is_active == True).count()}")
        print(f"  Total validations: {sum(b.total_validations for b in all_banks)}")
        print(f"  Total fees distributed: ₹{sum(b.total_fees_earned for b in all_banks):,.2f}")
        print("=" * 50)
        
    finally:
        db.close()