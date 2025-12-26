"""
Travel Account Service
Author: Ashutosh Rajesh
Purpose: Manage international travel accounts with forex

Features:
- Create temporary foreign bank accounts
- Convert INR → Foreign currency (0.15% fee)
- Make transactions in foreign currency
- Convert back to INR on closure
- Preserve transaction history forever

Flow:
1. User planning USA trip
2. Create travel account: convert ₹100,000 → $1,200 USD
3. Use foreign account during trip
4. Close account: convert remaining $200 → ₹16,500 INR
5. Account locked, history preserved

Example:
    service = TravelAccountService(db)
    
    # Create travel account
    travel_acc = service.create_travel_account(
        user_idx="IDX_abc123...",
        source_account_id=hdfc_account.id,
        foreign_bank_code="CITI_USA",
        inr_amount=100000,
        duration_days=30
    )
    
    # Close after trip
    service.close_travel_account(
        travel_acc.id,
        reason="Trip completed"
    )
"""

from typing import Optional, List
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random

from sqlalchemy.orm import Session
from database.models.travel_account import TravelAccount
from database.models.foreign_bank import ForeignBank
from database.models.forex_rate import ForexRate
from database.models.bank_account import BankAccount
from database.models.user import User


class TravelAccountService:
    """
    Travel account management service
    
    Responsibilities:
    - Create foreign bank accounts
    - Forex conversion (INR ↔ Foreign)
    - Account closure
    - Transaction history
    """
    
    def __init__(self, db: Session):
        """
        Initialize service
        
        Args:
            db: Database session
        """
        self.db = db
    
    def setup_foreign_banks(self):
        """
        Setup foreign banks (one-time setup)
        
        Creates:
        - Citibank USA (USD)
        - HSBC UK (GBP)
        - Deutsche Bank Germany (EUR)
        - DBS Bank Singapore (SGD)
        """
        foreign_banks = [
            {
                'bank_code': 'CITI_USA',
                'bank_name': 'Citibank USA',
                'country': 'United States',
                'country_code': 'USA',
                'currency': 'USD',
                'partner_indian_banks': 'HDFC,ICICI,SBI,AXIS,KOTAK,YES'
            },
            {
                'bank_code': 'HSBC_UK',
                'bank_name': 'HSBC UK',
                'country': 'United Kingdom',
                'country_code': 'GBR',
                'currency': 'GBP',
                'partner_indian_banks': 'HDFC,ICICI,SBI,AXIS,KOTAK,YES'
            },
            {
                'bank_code': 'DEUTSCHE_DE',
                'bank_name': 'Deutsche Bank Germany',
                'country': 'Germany',
                'country_code': 'DEU',
                'currency': 'EUR',
                'partner_indian_banks': 'HDFC,ICICI,SBI,AXIS,KOTAK,YES'
            },
            {
                'bank_code': 'DBS_SG',
                'bank_name': 'DBS Bank Singapore',
                'country': 'Singapore',
                'country_code': 'SGP',
                'currency': 'SGD',
                'partner_indian_banks': 'HDFC,ICICI,SBI,AXIS,KOTAK,YES'
            }
        ]
        
        created_count = 0
        for bank_data in foreign_banks:
            existing = self.db.query(ForeignBank).filter(
                ForeignBank.bank_code == bank_data['bank_code']
            ).first()
            
            if not existing:
                bank = ForeignBank(**bank_data)
                self.db.add(bank)
                created_count += 1
        
        self.db.commit()
        print(f"✅ Setup {created_count} foreign banks (total: {len(foreign_banks)})")
    
    def setup_forex_rates(self):
        """
        Setup forex rates (updated daily in production)
        
        Current rates (demo):
        - 1 INR = 0.012 USD (1 USD = ₹83.33)
        - 1 INR = 0.0095 GBP (1 GBP = ₹105.26)
        - 1 INR = 0.011 EUR (1 EUR = ₹90.91)
        - 1 INR = 0.016 SGD (1 SGD = ₹62.50)
        """
        rates = [
            ('INR', 'USD', Decimal('0.012000')),  # ₹1 = $0.012
            ('USD', 'INR', Decimal('83.333333')),  # $1 = ₹83.33
            ('INR', 'GBP', Decimal('0.009500')),  # ₹1 = £0.0095
            ('GBP', 'INR', Decimal('105.263158')),  # £1 = ₹105.26
            ('INR', 'EUR', Decimal('0.011000')),  # ₹1 = €0.011
            ('EUR', 'INR', Decimal('90.909091')),  # €1 = ₹90.91
            ('INR', 'SGD', Decimal('0.016000')),  # ₹1 = S$0.016
            ('SGD', 'INR', Decimal('62.500000')),  # S$1 = ₹62.50
        ]
        
        created_count = 0
        for from_curr, to_curr, rate in rates:
            existing = self.db.query(ForexRate).filter(
                ForexRate.from_currency == from_curr,
                ForexRate.to_currency == to_curr,
                ForexRate.is_active == True
            ).first()
            
            if not existing:
                forex_rate = ForexRate(
                    from_currency=from_curr,
                    to_currency=to_curr,
                    rate=rate,
                    forex_fee_percentage=Decimal('0.15')
                )
                self.db.add(forex_rate)
                created_count += 1
        
        self.db.commit()
        print(f"✅ Setup {created_count} forex rates (total: {len(rates)})")
    
    def get_forex_rate(self, from_currency: str, to_currency: str) -> Optional[ForexRate]:
        """
        Get current forex rate
        
        Args:
            from_currency: Source currency (INR, USD, etc.)
            to_currency: Target currency
            
        Returns:
            ForexRate: Current rate, None if not found
        """
        return self.db.query(ForexRate).filter(
            ForexRate.from_currency == from_currency,
            ForexRate.to_currency == to_currency,
            ForexRate.is_active == True
        ).first()
    
    def create_travel_account(
        self,
        user_idx: str,
        source_account_id: int,
        foreign_bank_code: str,
        inr_amount: Decimal,
        duration_days: int = 30
    ) -> TravelAccount:
        """
        Create travel account with forex conversion
        
        Args:
            user_idx: User's IDX
            source_account_id: Indian bank account ID
            foreign_bank_code: Foreign bank (CITI_USA, HSBC_UK, etc.)
            inr_amount: Amount to convert from INR
            duration_days: Account validity (default: 30 days)
            
        Returns:
            TravelAccount: Created travel account
            
        Example:
            >>> service = TravelAccountService(db)
            >>> travel_acc = service.create_travel_account(
            ...     "IDX_abc123...",
            ...     hdfc_account.id,
            ...     "CITI_USA",
            ...     Decimal('100000'),  # ₹1 lakh
            ...     duration_days=30
            ... )
            >>> print(f"Created: {travel_acc.currency} {travel_acc.balance}")
            Created: USD 1198.20
        """
        print(f"\n✈️  Creating Travel Account")
        print(f"   Source: Indian bank account #{source_account_id}")
        print(f"   Destination: {foreign_bank_code}")
        print(f"   Amount: ₹{inr_amount:,.2f}")
        
        # Step 1: Get source account
        source_account = self.db.query(BankAccount).filter(
            BankAccount.id == source_account_id
        ).first()
        
        if not source_account:
            raise ValueError("Source account not found")
        
        if source_account.balance < inr_amount:
            raise ValueError(f"Insufficient balance (have: ₹{source_account.balance}, need: ₹{inr_amount})")
        
        print(f"   ✅ Source: {source_account.bank_code} (₹{source_account.balance})")
        
        # Step 2: Get foreign bank
        foreign_bank = self.db.query(ForeignBank).filter(
            ForeignBank.bank_code == foreign_bank_code
        ).first()
        
        if not foreign_bank:
            raise ValueError(f"Foreign bank not found: {foreign_bank_code}")
        
        print(f"   ✅ Foreign bank: {foreign_bank.bank_name} ({foreign_bank.currency})")
        
        # Step 3: Get forex rate
        forex_rate = self.get_forex_rate('INR', foreign_bank.currency)
        
        if not forex_rate:
            raise ValueError(f"Forex rate not found for INR → {foreign_bank.currency}")
        
        print(f"   ✅ Forex rate: 1 INR = {forex_rate.rate} {foreign_bank.currency}")
        
        # Step 4: Convert currency
        foreign_amount = forex_rate.convert(inr_amount, apply_fee=True)
        forex_fee = inr_amount * forex_rate.rate * (forex_rate.forex_fee_percentage / Decimal('100'))
        
        print(f"   💱 Conversion: ₹{inr_amount:,.2f} → {foreign_bank.currency} {foreign_amount:,.2f}")
        print(f"   💰 Forex fee (0.15%): {foreign_bank.currency} {forex_fee:,.2f}")
        
        # Step 5: Generate foreign account number
        foreign_account_number = f"{foreign_bank_code}_{user_idx[-8:]}{random.randint(1000, 9999)}"
        
        # Step 6: Create travel account
        travel_account = TravelAccount(
            user_idx=user_idx,
            source_account_id=source_account_id,
            foreign_bank_id=foreign_bank.id,
            foreign_account_number=foreign_account_number,
            currency=foreign_bank.currency,
            balance=foreign_amount,
            initial_inr_amount=inr_amount,
            initial_forex_rate=forex_rate.rate,
            initial_foreign_amount=foreign_amount,
            forex_fee_paid=forex_fee,
            status='ACTIVE',
            expires_at=datetime.now(timezone.utc) + timedelta(days=duration_days)
        )
        
        # Step 7: Deduct from source account
        source_account.balance -= inr_amount
        
        # Step 8: Save
        self.db.add(travel_account)
        self.db.commit()
        self.db.refresh(travel_account)
        
        print(f"\n   ✅ Travel account created!")
        print(f"   Account: {foreign_account_number}")
        print(f"   Balance: {foreign_bank.currency} {foreign_amount:,.2f}")
        print(f"   Expires: {travel_account.expires_at.isoformat()}")
        
        return travel_account
    
    def close_travel_account(
        self,
        travel_account_id: int,
        reason: str = "Trip completed"
    ) -> dict:
        """
        Close travel account and convert back to INR
        
        Args:
            travel_account_id: Travel account ID
            reason: Closure reason
            
        Returns:
            dict: Closure summary
            
        Example:
            >>> service = TravelAccountService(db)
            >>> result = service.close_travel_account(
            ...     travel_acc.id,
            ...     "Trip completed"
            ... )
            >>> print(f"Returned: ₹{result['final_inr_amount']}")
        """
        print(f"\n✈️  Closing Travel Account #{travel_account_id}")
        
        # Get account
        travel_account = self.db.query(TravelAccount).filter(
            TravelAccount.id == travel_account_id
        ).first()
        
        if not travel_account:
            raise ValueError("Travel account not found")
        
        if travel_account.status == 'CLOSED':
            raise ValueError("Account already closed")
        
        print(f"   Account: {travel_account.foreign_account_number}")
        print(f"   Balance: {travel_account.currency} {travel_account.balance:,.2f}")
        
        # Get forex rate (reverse direction)
        forex_rate = self.get_forex_rate(travel_account.currency, 'INR')
        
        if not forex_rate:
            raise ValueError(f"Forex rate not found for {travel_account.currency} → INR")
        
        print(f"   Forex rate: 1 {travel_account.currency} = {forex_rate.rate} INR")
        
        # Convert back to INR
        inr_amount = forex_rate.convert(travel_account.balance, apply_fee=True)
        forex_fee = travel_account.balance * forex_rate.rate * (forex_rate.forex_fee_percentage / Decimal('100'))
        
        print(f"   💱 Conversion: {travel_account.currency} {travel_account.balance:,.2f} → ₹{inr_amount:,.2f}")
        print(f"   💰 Forex fee (0.15%): ₹{forex_fee:,.2f}")
        
        # Update travel account
        travel_account.status = 'CLOSED'
        travel_account.closed_at = datetime.now(timezone.utc)
        travel_account.closure_reason = reason
        travel_account.final_foreign_amount = travel_account.balance
        travel_account.final_forex_rate = forex_rate.rate
        travel_account.final_inr_amount = inr_amount
        travel_account.final_forex_fee_paid = forex_fee
        travel_account.balance = Decimal('0.00')
        
        # Return to source account
        source_account = self.db.query(BankAccount).filter(
            BankAccount.id == travel_account.source_account_id
        ).first()
        
        source_account.balance += inr_amount
        
        self.db.commit()
        
        print(f"\n   ✅ Account closed!")
        print(f"   Returned: ₹{inr_amount:,.2f} to {source_account.bank_code}")
        
        return {
            'travel_account_id': travel_account_id,
            'foreign_currency': travel_account.currency,
            'foreign_amount_spent': float(travel_account.initial_foreign_amount - travel_account.final_foreign_amount),
            'final_foreign_amount': float(travel_account.final_foreign_amount),
            'final_inr_amount': float(inr_amount),
            'forex_fee_paid': float(forex_fee),
            'closed_at': travel_account.closed_at.isoformat()
        }
    
    def get_user_travel_accounts(self, user_idx: str) -> List[TravelAccount]:
        """Get all travel accounts for user"""
        return self.db.query(TravelAccount).filter(
            TravelAccount.user_idx == user_idx
        ).order_by(TravelAccount.created_at.desc()).all()
    
    def get_travel_account(self, account_id: int) -> Optional[TravelAccount]:
        """Get travel account by ID"""
        return self.db.query(TravelAccount).filter(
            TravelAccount.id == account_id
        ).first()


# Testing
if __name__ == "__main__":
    """Test travel account service"""
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    
    from database.connection import SessionLocal
    
    print("=== Travel Account Service Testing ===\n")
    
    db = SessionLocal()
    service = TravelAccountService(db)
    
    try:
        # Setup
        print("Setup: Foreign Banks & Forex Rates")
        service.setup_foreign_banks()
        service.setup_forex_rates()
        print()
        
        # Get a user with bank account
        account = db.query(BankAccount).filter(
            BankAccount.balance >= Decimal('50000')
        ).first()
        
        if not account:
            # No user with balance, add money to first account
            print("⚠️  No account with sufficient balance, adding funds...")
            account = db.query(BankAccount).first()
            if not account:
                print("❌ No bank account found")
                exit(1)
            
            # Add ₹100,000 for testing
            account.balance += Decimal('100000')
            db.commit()
            print(f"   Added ₹100,000 to account")
        
        user = db.query(User).filter(User.idx == account.user_idx).first()
        
        print(f"Test User: {user.full_name}")
        print(f"Account: {account.bank_code} (₹{account.balance:,.2f})")
        
        # Test 1: Create travel account
        print("\n" + "="*50)
        print("Test 1: Create Travel Account (USA Trip)")
        print("="*50)
        
        travel_acc = service.create_travel_account(
            user.idx,
            account.id,
            "CITI_USA",
            Decimal('50000'),  # ₹50,000
            duration_days=30
        )
        
        print("\n✅ Test 1 passed!")
        
        # Test 2: Close travel account
        print("\n" + "="*50)
        print("Test 2: Close Travel Account")
        print("="*50)
        
        result = service.close_travel_account(
            travel_acc.id,
            "Trip completed successfully"
        )
        
        print("\n✅ Test 2 passed!")
        
        print("\n" + "="*50)
        print("✅ All travel account tests passed!")
        print("="*50)
        
    finally:
        db.close()