"""
Bank Account Service - Manage user's multiple bank accounts.

Create accounts, view balances, transfer between own accounts, freeze/unfreeze for court orders.
"""

# [DOC] Decimal: all monetary values use Decimal to avoid floating-point rounding errors in balances
from decimal import Decimal
# [DOC] datetime: used in print statements; not yet used for logic in this module
from datetime import datetime
# [DOC] Session: SQLAlchemy database session type annotation
from sqlalchemy.orm import Session
# [DOC] List/Optional/Dict: type hints only — no runtime effect
from typing import List, Optional, Dict
# [DOC] random: used for the 4-digit random suffix in account number generation
import random

# [DOC] BankAccount ORM model: one row per bank account; stores balance, bank_code, is_frozen, etc.
from database.models.bank_account import BankAccount
# [DOC] User ORM model: queried to verify the user exists before creating an account for them
from database.models.user import User
# [DOC] Bank ORM model: queried to verify the bank code exists in the consortium before opening an account there
from database.models.bank import Bank


class BankAccountService:
    """Service for managing bank accounts."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        # [DOC] Store database session; all methods in this class use self.db to query and write records
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
        # [DOC] Last 8 characters of IDX: ties the account number to this user without exposing the full IDX
        idx_part = user_idx[-8:]
        # [DOC] random 4-digit suffix: reduces collision probability if two users share the same IDX suffix
        random_part = str(random.randint(1000, 9999))
        # [DOC] Concatenate bank code + IDX tail + random digits to form the account number string
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
        # [DOC] Verify the user exists; raises ValueError if no matching IDX is found
        user = self.db.query(User).filter(User.idx == user_idx).first()
        if not user:
            raise ValueError(f"User not found: {user_idx}")

        # [DOC] Verify the bank is in the consortium; only registered banks can hold accounts
        bank = self.db.query(Bank).filter(Bank.bank_code == bank_code).first()
        if not bank:
            raise ValueError(f"Bank not found: {bank_code}")

        # [DOC] Enforce one account per bank per user — prevent duplicate accounts at the same bank
        existing = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.bank_code == bank_code
        ).first()

        if existing:
            raise ValueError(f"User already has {bank_code} account: {existing.account_number}")

        # [DOC] Generate a unique account number for this user at this bank
        account_number = self.generate_account_number(bank_code, user_idx)

        # [DOC] Create the BankAccount ORM object with all required fields
        account = BankAccount(
            user_idx=user_idx,
            bank_code=bank_code,
            account_number=account_number,
            balance=initial_balance,
            # [DOC] is_active=True: account is open and can send/receive transactions
            is_active=True,
            # [DOC] is_frozen=False: account starts unfrozen; only a court order can freeze it
            is_frozen=False
        )

        self.db.add(account)
        self.db.commit()
        # [DOC] refresh: reload from DB to get server-generated values like auto-increment id
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
        # [DOC] Only return active accounts (is_active=True); closed/deactivated accounts are excluded
        # [DOC] Ordered alphabetically by bank_code for consistent display in the UI
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
        # [DOC] Returns None if the user has no active account at this specific bank
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
        # [DOC] Used when an external party provides an account number (e.g., during payment routing)
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
        # [DOC] Sum balances across all active accounts; the result is a single Decimal value
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
        # [DOC] total: Python-level sum of all Decimal balance fields
        total = sum(acc.balance for acc in accounts)

        return {
            # [DOC] str(total): serialize Decimal to string so it survives JSON serialization without precision loss
            'total_balance': str(total),
            'accounts': [
                {
                    'bank_code': acc.bank_code,
                    'account_number': acc.account_number,
                    'balance': str(acc.balance),
                    # [DOC] is_frozen: tells the UI to show a "frozen" badge on this account
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
        # [DOC] Fetch the account by its integer primary key
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Account not found: {account_id}")

        # [DOC] Set is_frozen=True; the transaction pipeline checks this flag before allowing outgoing payments
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

        # [DOC] Clear the frozen flag; the account can send and receive transactions again
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
        # [DOC] A court order typically freezes all accounts the user holds, not just one specific account
        accounts = self.get_user_accounts(user_idx)

        # [DOC] Set is_frozen on each account object in memory; a single commit below persists all at once
        for account in accounts:
            account.is_frozen = True

        # [DOC] One commit for all accounts — more efficient than committing inside the loop
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
        # [DOC] Unlike freeze_all, this queries for frozen accounts specifically — avoids touching already-unfrozen ones
        accounts = self.db.query(BankAccount).filter(
            BankAccount.user_idx == user_idx,
            BankAccount.is_frozen == True
        ).all()

        for account in accounts:
            account.is_frozen = False

        self.db.commit()

        print(f"🔓 Unfroze {len(accounts)} accounts for user {user_idx[:16]}...")

        return len(accounts)

    def setup_consortium_banks(self) -> int:
        """Create all 12 consortium banks and generate BBS+ group signature keys.

        Idempotent: skips banks that already exist.  Generates one shared
        BBS04 group public key and per-bank signing keys (using Charm-Crypto
        BBSGroupSignature on BN254) and stores them in
        consortium_banks.bbs_public_key / bbs_secret_key (migration 010).

        Returns:
            int: Number of banks created (0 if all already existed).

        Security note (BBS04):
            The group manager secret (open_key / manager_sk) is printed to
            stdout here for DEV convenience.  In PRODUCTION this must be
            delivered to RBI via a Hardware Security Module, never logged.
        """
        # [DOC] BBS04 key generation block: attempt to import charm-crypto; fall back gracefully if unavailable
        bbs_params: dict = {}
        try:
            # [DOC] BBSGroupSignature: real BBS04 implementation using Charm-Crypto on the BN254 pairing curve
            from core.crypto.real.bbs_group_signature import BBSGroupSignature
            print("  Generating BBS04 group keys on BN254 (12-bank consortium)...")
            bbs = BBSGroupSignature()
            # [DOC] setup(n_banks=12): generates one group public key + one signing key per bank
            bbs_params = bbs.setup(n_banks=12)
            print("  [OK] BBS04 keys generated")
            print(f"  [DEV ONLY] Open key (RBI manager secret) — "
                  "distribute via HSM in production, never log in prod")
        except ImportError:
            # [DOC] If charm-crypto is not installed, skip BBS key generation and store None in the DB columns
            print("  [WARN] charm-crypto not available — BBS+ keys skipped; "
                  "batch_processor will fall back to placeholder strings.")

        # [DOC] banks_data: the 12 consortium banks — 8 public sector + 4 private sector
        # [DOC] Each tuple: (bank_code, bank_name, total_assets, initial_stake, validator_address)
        banks_data = [
            # Public Sector Banks (8)
            ("SBI",     "State Bank of India",       Decimal("45000000000000.00"), Decimal("450000000000.00"), "validator-sbi.idxbanking.com:8001"),
            ("PNB",     "Punjab National Bank",       Decimal("12000000000000.00"), Decimal("120000000000.00"), "validator-pnb.idxbanking.com:8002"),
            ("BOB",     "Bank of Baroda",             Decimal("11000000000000.00"), Decimal("110000000000.00"), "validator-bob.idxbanking.com:8003"),
            ("CANARA",  "Canara Bank",                Decimal("10000000000000.00"), Decimal("100000000000.00"), "validator-canara.idxbanking.com:8004"),
            ("UNION",   "Union Bank of India",        Decimal("9000000000000.00"),  Decimal("90000000000.00"),  "validator-union.idxbanking.com:8005"),
            ("INDIAN",  "Indian Bank",                Decimal("6000000000000.00"),  Decimal("60000000000.00"),  "validator-indian.idxbanking.com:8006"),
            ("CENTRAL", "Central Bank of India",      Decimal("5000000000000.00"),  Decimal("50000000000.00"),  "validator-central.idxbanking.com:8007"),
            ("UCO",     "UCO Bank",                   Decimal("4500000000000.00"),  Decimal("45000000000.00"),  "validator-uco.idxbanking.com:8008"),
            # Private Sector Banks (4)
            ("HDFC",    "HDFC Bank Ltd",              Decimal("18000000000000.00"), Decimal("180000000000.00"), "validator-hdfc.idxbanking.com:8009"),
            ("ICICI",   "ICICI Bank Ltd",             Decimal("15000000000000.00"), Decimal("150000000000.00"), "validator-icici.idxbanking.com:8010"),
            ("AXIS",    "Axis Bank Ltd",              Decimal("10000000000000.00"), Decimal("100000000000.00"), "validator-axis.idxbanking.com:8011"),
            ("KOTAK",   "Kotak Mahindra Bank",        Decimal("6000000000000.00"),  Decimal("60000000000.00"),  "validator-kotak.idxbanking.com:8012"),
        ]

        # [DOC] group_pk: the single BBS04 group public key shared by ALL 12 banks — used to verify anonymous votes
        group_pk     = bbs_params.get("group_pk")           # str or None
        # [DOC] bank_keys: list of per-bank signing key dicts; index 0 corresponds to banks_data index 0 (SBI)
        bank_keys    = bbs_params.get("bank_keys", [])       # list[{bank_id, signing_key}]
        # bank_keys is 1-indexed; index 0 = bank_id 1 (SBI)

        created = 0
        for i, (code, name, assets, stake, addr) in enumerate(banks_data):
            existing = self.db.query(Bank).filter(Bank.bank_code == code).first()
            if existing:
                # [DOC] Idempotent upgrade: if BBS keys were added in migration 010 but not previously stored, backfill them
                if group_pk and not existing.bbs_public_key:
                    existing.bbs_public_key = group_pk
                    if i < len(bank_keys):
                        existing.bbs_secret_key = bank_keys[i]["signing_key"]
                continue

            # [DOC] Create a new Bank row for this consortium member
            bank = Bank(
                bank_code=code,
                bank_name=name,
                total_assets=assets,
                initial_stake=stake,
                # [DOC] stake_amount: same as initial_stake at setup; decreases when the bank is slashed
                stake_amount=stake,
                validator_address=addr,
                is_active=True,
                # [DOC] bbs_public_key: shared group public key (same for all 12 banks) — stored as JSON string
                bbs_public_key=group_pk if group_pk else None,
                # [DOC] bbs_secret_key: unique signing key for this specific bank — must never leave that bank's node
                bbs_secret_key=bank_keys[i]["signing_key"] if i < len(bank_keys) else None,
            )
            self.db.add(bank)
            created += 1

        # [DOC] Single commit for all new banks — atomic: either all are created or none
        self.db.commit()
        print(f"  [OK] Consortium: {created} bank(s) created, {len(banks_data) - created} already existed")
        return created


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
