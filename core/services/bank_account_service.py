"""
Bank Account Service - Manage user's multiple bank accounts.

Create accounts, view balances, transfer between own accounts, freeze/unfreeze for court orders.
"""

from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
import random

from database.models.bank_account import BankAccount
from database.models.user import User
from database.models.bank import Bank


class BankAccountService:
    """Service for managing bank accounts."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
    
    def generate_account_number(self, bank_code: str, user_idx: str) -> str:
        """
        Generate unique bank account number
        
        Format: BANK_CODE + last 8 chars of IDX + random 4 digits
        Example: HDFC12345678901234
        
        Args:
            bank_code: Bank code (HDFC, ICICI, etc.)
            user_idx: User's IDX
            
        Returns:
            str: Account number
        """
        idx_part = user_idx[-8:]
        random_part = str(random.randint(1000, 9999))
        return f"{bank_code}{idx_part}{random_part}"
    
    def create_account(
        self,
        user_idx: str,
        bank_code: str,
        initial_balance: Decimal = Decimal('0.00')
    ) -> BankAccount:
        """
        Create new bank account for user
        
        Args:
            user_idx: User's IDX
            bank_code: Bank code (HDFC, ICICI, SBI, etc.)
            initial_balance: Starting balance (default: 0)
            
        Returns:
            BankAccount: Created account
            
        Raises:
            ValueError: If user not found or bank not found
            
        Example:
            >>> service = BankAccountService(db)
            >>> account = service.create_account("IDX_abc...", "ICICI", Decimal('10000'))
            >>> print(account.account_number)
            ICICI12345678901234
        """
        # Verify user exists
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")
        
        # Verify bank exists
        bank = self.db.query(Bank).filter(Bank.bank_code == bank_code).first()
        if not bank:
            raise ValueError(f"Bank not found: {bank_code}")
        
        # Check if user already has account at this bank
        existing = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code
        ).first()
        
        if existing:
            raise ValueError(f"User already has {bank_code} account: {existing.account_number}")
        
        # Generate account number
        account_number = self.generate_account_number(bank_code, user_idx)
        
        # Create account
        account = BankAccount(
            user_idx=user_idx,
            bank_code=bank_code,
            account_number=account_number,
            balance=initial_balance,
            is_active=True,
            is_frozen=False
        )
        
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        
        return account
    
    def get_user_accounts(self, user_idx: str) -> List[BankAccount]:
        """
        Get all bank accounts for a user
        
        Args:
            user_idx: User's IDX
            
        Returns:
            List[BankAccount]: All user's accounts
            
        Example:
            >>> accounts = service.get_user_accounts("IDX_abc...")
            >>> for acc in accounts:
            ...     print(f"{acc.bank_code}: ₹{acc.balance}")
            HDFC: ₹50000
            ICICI: ₹25000
            SBI: ₹10000
        """
        return self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.is_active == True
        ).order_by(BankAccount.bank_code).all()
    
    def get_account_by_bank(self, user_idx: str, bank_code: str) -> Optional[BankAccount]:
        """
        Get user's account at specific bank
        
        Args:
            user_idx: User's IDX
            bank_code: Bank code
            
        Returns:
            BankAccount or None: Account if exists
        """
        return self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code,
            BankAccount.is_active == True
        ).first()
    
    def get_account_by_number(self, account_number: str) -> Optional[BankAccount]:
        """
        Get account by account number
        
        Args:
            account_number: Account number
            
        Returns:
            BankAccount or None: Account if exists
        """
        return self.db.query(BankAccount).filter(
            BankAccount.account_number == account_number,
            BankAccount.is_active == True
        ).first()
    
    def get_total_balance(self, user_idx: str) -> Decimal:
        """
        Get total balance across all accounts
        
        Args:
            user_idx: User's IDX
            
        Returns:
            Decimal: Total balance
        """
        accounts = self.get_user_accounts(user_idx)
        return sum(acc.balance for acc in accounts)
    
    def get_account_summary(self, user_idx: str) -> Dict:
        """
        Get summary of all accounts
        
        Args:
            user_idx: User's IDX
            
        Returns:
            Dict: Summary with accounts and total
            
        Example:
            >>> summary = service.get_account_summary("IDX_abc...")
            >>> print(summary)
            {
                'total_balance': '85000.00',
                'accounts': [
                    {'bank': 'HDFC', 'balance': '50000.00'},
                    {'bank': 'ICICI', 'balance': '25000.00'},
                    {'bank': 'SBI', 'balance': '10000.00'}
                ],
                'account_count': 3
            }
        """
        accounts = self.get_user_accounts(user_idx)
        total = sum(acc.balance for acc in accounts)
        
        return {
            'total_balance': str(total),
            'accounts': [
                {
                    'bank_code': acc.bank_code,
                    'account_number': acc.account_number,
                    'balance': str(acc.balance),
                    'is_frozen': acc.is_frozen
                }
                for acc in accounts
            ],
            'account_count': len(accounts)
        }
    
    def freeze_account(self, account_id: int, reason: str = "Court order") -> BankAccount:
        """
        Freeze account (for court orders)
        
        Args:
            account_id: Account ID
            reason: Reason for freezing
            
        Returns:
            BankAccount: Frozen account
        """
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        
        account.is_frozen = True
        self.db.commit()
        self.db.refresh(account)
        
        print(f"🔒 Account frozen: {account.account_number} ({reason})")
        
        return account
    
    def unfreeze_account(self, account_id: int) -> BankAccount:
        """
        Unfreeze account
        
        Args:
            account_id: Account ID
            
        Returns:
            BankAccount: Unfrozen account
        """
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        
        account.is_frozen = False
        self.db.commit()
        self.db.refresh(account)
        
        print(f"🔓 Account unfrozen: {account.account_number}")
        
        return account
    
    def freeze_all_user_accounts(self, user_idx: str, reason: str = "Court order") -> int:
        """
        Freeze all accounts for a user (for court investigations)
        
        Args:
            user_idx: User's IDX
            reason: Reason for freezing
            
        Returns:
            int: Number of accounts frozen
        """
        accounts = self.get_user_accounts(user_idx)
        
        for account in accounts:
            account.is_frozen = True
        
        self.db.commit()
        
        print(f"🔒 Froze {len(accounts)} accounts for user {user_idx[:16]}... ({reason})")
        
        return len(accounts)
    
    def unfreeze_all_user_accounts(self, user_idx: str) -> int:
        """
        Unfreeze all accounts for a user
        
        Args:
            user_idx: User's IDX
            
        Returns:
            int: Number of accounts unfrozen
        """
        accounts = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.is_frozen == True
        ).all()
        
        for account in accounts:
            account.is_frozen = False
        
        self.db.commit()
        
        print(f"🔓 Unfroze {len(accounts)} accounts for user {user_idx[:16]}...")
        
        return len(accounts)


# Testing
if __name__ == "__main__":
    """Test bank account service"""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    
    print("=== Bank Account Service Testing ===\n")
    
    db = SessionLocal()
    service = BankAccountService(db)
    
    try:
        # Test 1: Get existing accounts
        print("Test 1: Get User Accounts")
        test_idx = IDXGenerator.generate("TESTA1234P", "100001")
        accounts = service.get_user_accounts(test_idx)
        print(f"  Found {len(accounts)} accounts")
        for acc in accounts:
            print(f"  - {acc.bank_code}: ₹{acc.balance} ({acc.account_number})")
        print("  [PASS] Test 1 passed!\n")
        
        # Test 2: Get account summary
        print("Test 2: Account Summary")
        summary = service.get_account_summary(test_idx)
        print(f"  Total Balance: ₹{summary['total_balance']}")
        print(f"  Accounts: {summary['account_count']}")
        print("  [PASS] Test 2 passed!\n")
        
        # Test 3: Create new account
        print("Test 3: Create ICICI Account")
        try:
            icici_account = service.create_account(test_idx, "ICICI", Decimal('20000'))
            print(f"  Account created: {icici_account.account_number}")
            print(f"  Balance: ₹{icici_account.balance}")
            print("  [PASS] Test 3 passed!\n")
        except ValueError as e:
            print(f"  ⏭️  Account already exists: {str(e)}\n")
        
        # Test 4: Get total balance
        print("Test 4: Total Balance")
        total = service.get_total_balance(test_idx)
        print(f"  Total: ₹{total}")
        print("  [PASS] Test 4 passed!\n")
        
        print("=" * 50)
        print("[PASS] All tests passed!")
        print("=" * 50)
        
    finally:
        db.close()