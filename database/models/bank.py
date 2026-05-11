"""
Bank Model - Consortium Banks for PoS Validation

Purpose: Store 12 consortium banks that validate private blockchain

Consortium Banks:
- Total: 12 banks (8 public sector + 4 private sector)
- Public: SBI, PNB, BOB, Canara, Union, Indian, Central, UCO
- Private: HDFC, ICICI, Axis, Kotak
- Role: Validate transactions on private blockchain
- Consensus: 8/12 must approve (67% Byzantine fault tolerance)
- Rewards: Share 1% fee equally

Example Flow:
1. Transaction mined on public chain (PoW by users/miners)
2. 12 banks vote on private chain (PoS consensus)
3. 8/12 approval required (both sender & receiver banks must approve)
4. Transaction added to private blockchain
5. All 12 banks receive equal fee share
"""

# [DOC] Standard SQLAlchemy column types imported for declaring table schema

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Index
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
# [DOC] Base is the SQLAlchemy declarative base — all ORM models inherit from it
from database.connection import Base


# [DOC] One row per consortium bank; table name is 'consortium_banks'
class Bank(Base):
    """
    Consortium bank table

    Stores information about the 12 banks that form the
    validation consortium for the private blockchain.

    Each bank:
    - Participates in PoS consensus (voting)
    - Receives equal share of 1% transaction fee
    - Stakes 1% of total assets (can be slashed for malicious behavior)
    - Tracked for honest/malicious verifications (fiscal year rewards)

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

    # [DOC] Maps this Python class to the 'consortium_banks' PostgreSQL table
    __tablename__ = 'consortium_banks'

    # Primary key
    # [DOC] Auto-incrementing integer; internal row ID, not used in business logic
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Bank identification
    # [DOC] Short uppercase code, e.g. "SBI", "HDFC" — used in session IDs (SESSION_HDFC_...) and voting records
    bank_code = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Short bank code (HDFC, ICICI, SBI, etc.)"
    )

    # [DOC] Human-readable full legal name, e.g. "HDFC Bank Ltd" — used in API responses and reports
    bank_name = Column(
        String(100),
        nullable=False,
        comment="Full bank name"
    )

    # Staking (Proof of Stake)
    # [DOC] Current stake balance in paise (integer rupees × 100); starts at initial_stake, reduced by slashing
    stake_amount = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Amount staked by bank (can be slashed)"
    )

    # Bank financials (for minimum stake calculation)
    # [DOC] Declared total assets of the bank; used to compute the mandatory 1% minimum stake
    total_assets = Column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal('10000000000.00'),  # ₹10,000 crore default
        comment="Total assets/market cap of bank (for 1% minimum stake calculation)"
    )

    # Initial stake (for deactivation threshold calculation)
    # [DOC] Stake when the bank first joined; bank is deactivated if stake_amount falls below 30% of this
    initial_stake = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('100000000.00'),  # ₹10 crore default
        comment="Initial stake amount (deactivation if falls below 30% of this)"
    )

    # Status
    # [DOC] False means this bank is excluded from consensus rounds — no votes accepted from it
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether bank is actively validating"
    )

    # Statistics
    # [DOC] Cumulative count of transaction batches this bank has successfully validated; used in reward calculation
    total_validations = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total blocks validated by this bank"
    )

    # [DOC] Cumulative fee income earned by this bank from the 1% transaction fee pool (split equally among N banks)
    total_fees_earned = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total fees earned from validation"
    )

    # Penalties
    # [DOC] Total number of times this bank has been penalized (for escalating penalty schedule: 1st, 2nd, 3rd offense)
    penalty_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times penalized for misbehavior"
    )

    # [DOC] Total rupee value slashed from this bank's stake across all offenses; cross-referenced with treasury table
    total_penalties = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Total amount slashed as penalties"
    )

    # Honest behavior tracking (for fiscal year rewards)
    # [DOC] Count of batches where this bank cast a CORRECT vote (APPROVE on valid, REJECT on invalid)
    # [DOC] Used at fiscal year end to divide treasury rewards proportionally among honest banks
    honest_verifications = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of correct verifications (for reward calculation)"
    )

    # [DOC] Count of batches where this bank voted APPROVE but the batch was later found invalid by RBI re-verification
    malicious_verifications = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of incorrect verifications (voted ACCEPT on invalid tx)"
    )

    # [DOC] Amount received in the most recent annual treasury redistribution; reset each fiscal year
    last_fiscal_year_reward = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal('0.00'),
        comment="Reward received in last fiscal year distribution"
    )

    # BBS+ Group Signature keys (added by migration 010)
    # Generated by BBSGroupSignature().setup(); stored as JSON strings.
    # bbs_secret_key: bank's individual signing key (Ai, xi) — keep secret per bank node.
    # bbs_public_key: consortium group public key (gpk) — same for all 12 banks.
    # [DOC] BBS04 individual signing key for this bank; JSON-serialized (Ai, xi) pair generated at startup
    # [DOC] Each bank gets a unique secret key so signatures are unlinkable — you cannot tell which bank signed
    # [DOC] The opening authority (regulatory body) can de-anonymize a signature only under court order
    bbs_secret_key = Column(
        String,
        nullable=True,
        comment="BBS04 signing key for this bank (JSON, from core/crypto/real/bbs_group_signature.py)"
    )

    # [DOC] BBS04 group public key (gpk) shared by ALL 12 banks — used by anyone to verify a batch approval signature
    # [DOC] Same value stored in every bank row for convenient lookup during batch verification
    bbs_public_key = Column(
        String,
        nullable=True,
        comment="BBS04 group public key shared by all consortium banks (JSON)"
    )

    # Contact information
    # [DOC] Hostname:port of this bank's validator node, e.g. "validator-hdfc.idxbanking.com:8009"
    validator_address = Column(
        String(255),
        nullable=True,
        comment="Network address for validator node"
    )

    # Timestamps
    # [DOC] When this bank was added to the consortium; set automatically by the database on INSERT
    joined_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When bank joined consortium"
    )

    # [DOC] Timestamp of the most recent batch this bank validated; NULL if the bank has never voted
    last_validation_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time bank validated a block"
    )

    # Indexes
    # [DOC] Composite index on bank_code for fast lookup by short code; index on is_active to filter live banks quickly
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

    # [DOC] Serializes the bank record for REST API responses; excludes BBS secret key for security
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'stake_amount': str(self.stake_amount),
            'total_assets': str(self.total_assets),
            'initial_stake': str(self.initial_stake),
            'is_active': self.is_active,
            'total_validations': self.total_validations,
            'total_fees_earned': str(self.total_fees_earned),
            'penalty_count': self.penalty_count,
            'total_penalties': str(self.total_penalties),
            'honest_verifications': self.honest_verifications,
            'malicious_verifications': self.malicious_verifications,
            'last_fiscal_year_reward': str(self.last_fiscal_year_reward),
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
        
        # Test 1: Create the 12 consortium banks
        print("Test 1: Create 12 Consortium Banks (8 Public + 4 Private)")

        banks_data = [
            # Public Sector Banks (8)
            {
                'bank_code': 'SBI',
                'bank_name': 'State Bank of India',
                'total_assets': Decimal('45000000000000.00'),  # ₹45 lakh crore
                'initial_stake': Decimal('450000000000.00'),  # 1% of assets = ₹4,500 crore
                'stake_amount': Decimal('450000000000.00'),
                'validator_address': 'validator-sbi.idxbanking.com:8001'
            },
            {
                'bank_code': 'PNB',
                'bank_name': 'Punjab National Bank',
                'total_assets': Decimal('12000000000000.00'),  # ₹12 lakh crore
                'initial_stake': Decimal('120000000000.00'),  # 1% = ₹1,200 crore
                'stake_amount': Decimal('120000000000.00'),
                'validator_address': 'validator-pnb.idxbanking.com:8002'
            },
            {
                'bank_code': 'BOB',
                'bank_name': 'Bank of Baroda',
                'total_assets': Decimal('11000000000000.00'),  # ₹11 lakh crore
                'initial_stake': Decimal('110000000000.00'),  # 1% = ₹1,100 crore
                'stake_amount': Decimal('110000000000.00'),
                'validator_address': 'validator-bob.idxbanking.com:8003'
            },
            {
                'bank_code': 'CANARA',
                'bank_name': 'Canara Bank',
                'total_assets': Decimal('10000000000000.00'),  # ₹10 lakh crore
                'initial_stake': Decimal('100000000000.00'),  # 1% = ₹1,000 crore
                'stake_amount': Decimal('100000000000.00'),
                'validator_address': 'validator-canara.idxbanking.com:8004'
            },
            {
                'bank_code': 'UNION',
                'bank_name': 'Union Bank of India',
                'total_assets': Decimal('9000000000000.00'),  # ₹9 lakh crore
                'initial_stake': Decimal('90000000000.00'),  # 1% = ₹900 crore
                'stake_amount': Decimal('90000000000.00'),
                'validator_address': 'validator-union.idxbanking.com:8005'
            },
            {
                'bank_code': 'INDIAN',
                'bank_name': 'Indian Bank',
                'total_assets': Decimal('6000000000000.00'),  # ₹6 lakh crore
                'initial_stake': Decimal('60000000000.00'),  # 1% = ₹600 crore
                'stake_amount': Decimal('60000000000.00'),
                'validator_address': 'validator-indian.idxbanking.com:8006'
            },
            {
                'bank_code': 'CENTRAL',
                'bank_name': 'Central Bank of India',
                'total_assets': Decimal('5000000000000.00'),  # ₹5 lakh crore
                'initial_stake': Decimal('50000000000.00'),  # 1% = ₹500 crore
                'stake_amount': Decimal('50000000000.00'),
                'validator_address': 'validator-central.idxbanking.com:8007'
            },
            {
                'bank_code': 'UCO',
                'bank_name': 'UCO Bank',
                'total_assets': Decimal('4500000000000.00'),  # ₹4.5 lakh crore
                'initial_stake': Decimal('45000000000.00'),  # 1% = ₹450 crore
                'stake_amount': Decimal('45000000000.00'),
                'validator_address': 'validator-uco.idxbanking.com:8008'
            },
            # Private Sector Banks (4)
            {
                'bank_code': 'HDFC',
                'bank_name': 'HDFC Bank Ltd',
                'total_assets': Decimal('18000000000000.00'),  # ₹18 lakh crore
                'initial_stake': Decimal('180000000000.00'),  # 1% = ₹1,800 crore
                'stake_amount': Decimal('180000000000.00'),
                'validator_address': 'validator-hdfc.idxbanking.com:8009'
            },
            {
                'bank_code': 'ICICI',
                'bank_name': 'ICICI Bank Ltd',
                'total_assets': Decimal('15000000000000.00'),  # ₹15 lakh crore
                'initial_stake': Decimal('150000000000.00'),  # 1% = ₹1,500 crore
                'stake_amount': Decimal('150000000000.00'),
                'validator_address': 'validator-icici.idxbanking.com:8010'
            },
            {
                'bank_code': 'AXIS',
                'bank_name': 'Axis Bank Ltd',
                'total_assets': Decimal('10000000000000.00'),  # ₹10 lakh crore
                'initial_stake': Decimal('100000000000.00'),  # 1% = ₹1,000 crore
                'stake_amount': Decimal('100000000000.00'),
                'validator_address': 'validator-axis.idxbanking.com:8011'
            },
            {
                'bank_code': 'KOTAK',
                'bank_name': 'Kotak Mahindra Bank',
                'total_assets': Decimal('6000000000000.00'),  # ₹6 lakh crore
                'initial_stake': Decimal('60000000000.00'),  # 1% = ₹600 crore
                'stake_amount': Decimal('60000000000.00'),
                'validator_address': 'validator-kotak.idxbanking.com:8012'
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
        print(f"  Active banks: {len(active_banks)}/12")

        assert len(active_banks) == 12
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

        # Deactivate UCO Bank
        uco_bank = db.query(Bank).filter(Bank.bank_code == "UCO").first()
        uco_bank.is_active = False
        db.commit()

        active_count = db.query(Bank).filter(Bank.is_active == True).count()
        print(f"  Deactivated: {uco_bank.bank_name}")
        print(f"  Active banks remaining: {active_count}/12")

        assert active_count == 11
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