"""
User Model - User Accounts with IDX
Purpose: Store user information and link IDX to real identity

Table Structure:
- id: Auto-increment primary key
- idx: Permanent anonymous identifier (unique)
- pan_card: Encrypted PAN card (sensitive!)
- full_name: User's real name (public with IDX)
- balance: Current balance in INR
- created_at: Account creation timestamp
- updated_at: Last update timestamp

Privacy Model:
✅ Public: IDX ↔ Full Name (for tax verification)
❌ Private: PAN card (encrypted, only us + court)
❌ Private: Balance (encrypted in private chain)
❌ Private: Transaction history (requires court order for session→IDX mapping)
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Index
from sqlalchemy.sql import func
from datetime import datetime
from database.connection import Base
from decimal import Decimal
from sqlalchemy.orm import relationship
class User(Base):
    """
    User accounts table
    
    Each user has:
    - Permanent IDX (never changes)
    - Encrypted PAN card (stored but never exposed)
    - Real name (public with IDX for tax purposes)
    - Balance (updated with each transaction)
    
    Example:
        >>> from database.connection import SessionLocal
        >>> from core.crypto.idx_generator import IDXGenerator
        >>> 
        >>> # Create new user
        >>> db = SessionLocal()
        >>> idx = IDXGenerator.generate("RAJSH1234K", "100001")
        >>> 
        >>> user = User(
        ...     idx=idx,
        ...     pan_card="RAJSH1234K",  # Will be encrypted
        ...     full_name="Rajesh Kumar",
        ...     balance=10000.00
        ... )
        >>> 
        >>> db.add(user)
        >>> db.commit()
    """
    
    __tablename__ = 'users'
    # NEW RELATIONSHIPS - Add these at the end of User class
    bank_accounts = relationship("BankAccount", back_populates="user", cascade="all, delete-orphan")
    freeze_records = relationship("FreezeRecord", back_populates="user", cascade="all, delete-orphan")
    #recipients = relationship("Recipient", foreign_keys="Recipient.user_idx", back_populates="owner", cascade="all, delete-orphan")
    # Primary key (auto-increment)
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # IDX - Permanent anonymous identifier
    # Format: "IDX_abc123def456..."
    # This is PUBLIC (anyone can look up IDX → Name)
    idx = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Permanent anonymous identifier (public with name)"
    )
    
    # PAN Card - SENSITIVE (encrypted in production)
    # Format: "ABCDE1234F"
    # This is PRIVATE (only stored for verification, never shown)
    pan_card = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="PAN card number (encrypted, never public)"
    )
    
    # Full Name - PUBLIC (linked to IDX)
    # This is shown in public IDX database for tax verification
    full_name = Column(
        String(255),
        nullable=False,
        comment="User's real name (public with IDX)"
    )
    
    # Balance - Current account balance
    # Precision: 10 digits total, 2 decimal places
    # Max: 99,999,999.99 (99 million rupees)
    balance = Column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=0.00,
        comment="Current balance in INR"
    )
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Account creation timestamp"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp"
    )
    
    # Indexes for fast lookups
    __table_args__ = (
        Index('idx_users_idx', 'idx'),  # Fast IDX lookup
        Index('idx_users_pan', 'pan_card'),  # Fast PAN lookup
        Index('idx_users_created', 'created_at'),  # Date range queries
    )
    
    def __repr__(self):
        """String representation"""
        return (
            f"<User(id={self.id}, "
            f"idx={self.idx[:20]}..., "
            f"name={self.full_name}, "
            f"balance=₹{self.balance:,.2f})>"
        )
    
    def to_dict(self, include_sensitive=False):
        """
        Convert to dictionary for API responses
        
        Args:
            include_sensitive (bool): Include PAN card? (Only for admin/court)
        
        Returns:
            dict: User data
        
        Example:
            >>> user.to_dict()
            {
                'id': 1,
                'idx': 'IDX_abc123...',
                'full_name': 'Rajesh Kumar',
                'balance': '10000.00',
                'created_at': '2025-12-21T10:30:45'
            }
            
            >>> user.to_dict(include_sensitive=True)
            {
                ...,
                'pan_card': 'RAJSH1234K'  # Only for court orders!
            }
        """
        data = {
            'id': self.id,
            'idx': self.idx,
            'full_name': self.full_name,
            'balance': str(self.balance),  # Convert Decimal to string
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        # Only include PAN with court order or admin access
        if include_sensitive:
            data['pan_card'] = self.pan_card
        
        return data


# Example usage / testing
if __name__ == "__main__":
    """
    Test the User model
    Run: python3 -m database.models.user
    """
    from database.connection import engine, SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    
    print("=== User Model Testing ===\n")
    
    # Create table
    print("Creating users table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Table created!\n")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Test 1: Create users
        print("Test 1: Create Users")
        
        # User 1: Rajesh
        idx1 = IDXGenerator.generate("RAJSH1234K", "100001")
        user1 = User(
            idx=idx1,
            pan_card="RAJSH1234K",
            full_name="Rajesh Kumar",
            balance=10000.00
        )
        
        # User 2: Priya
        idx2 = IDXGenerator.generate("PRIYA5678M", "100002")
        user2 = User(
            idx=idx2,
            pan_card="PRIYA5678M",
            full_name="Priya Sharma",
            balance=5000.00
        )
        
        db.add(user1)
        db.add(user2)
        db.commit()
        
        print(f"  User 1: {user1}")
        print(f"  User 2: {user2}")
        print("  ✅ Test 1 passed!\n")
        
        # Test 2: Query by IDX
        print("Test 2: Query by IDX")
        found = db.query(User).filter(User.idx == idx1).first()
        print(f"  Found: {found.full_name}")
        assert found.full_name == "Rajesh Kumar"
        print("  ✅ Test 2 passed!\n")
        
        # Test 3: Query by PAN
        print("Test 3: Query by PAN")
        found = db.query(User).filter(User.pan_card == "PRIYA5678M").first()
        print(f"  Found: {found.full_name}")
        assert found.full_name == "Priya Sharma"
        print("  ✅ Test 3 passed!\n")
        
        # Test 4: Update balance
        print("Test 4: Update Balance")
        user1.balance += Decimal('1000.00')
        db.commit()
        
        db.refresh(user1)
        print(f"  New balance: ₹{user1.balance:,.2f}")
        assert user1.balance == 11000.00
        print("  ✅ Test 4 passed!\n")
        
        # Test 5: to_dict (public)
        print("Test 5: Public Dictionary")
        public_data = user1.to_dict(include_sensitive=False)
        print(f"  Public data: {public_data}")
        assert 'pan_card' not in public_data
        print("  ✅ Test 5 passed! (PAN hidden)\n")
        
        # Test 6: to_dict (sensitive - court order)
        print("Test 6: Sensitive Dictionary (Court Order)")
        sensitive_data = user1.to_dict(include_sensitive=True)
        print(f"  Sensitive data: {sensitive_data}")
        assert 'pan_card' in sensitive_data
        print("  ✅ Test 6 passed! (PAN shown)\n")
        
        print("=" * 50)
        print("✅ All User model tests passed!")
        print("=" * 50)
        
    finally:
        db.close()