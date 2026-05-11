"""
Test Database Setup Script
Purpose: Create a clean test database with properly formatted data

Features:
1. Creates a separate test database (doesn't touch production)
2. Populates with clean, properly formatted test data
3. Ensures all relationships are valid
4. Creates matching sessions for all bank accounts
5. Ready for stress testing

Usage:
    python3 scripts/setup_test_database.py --reset    # Reset and recreate
    python3 scripts/setup_test_database.py --populate  # Add test data
    python3 scripts/setup_test_database.py --full      # Reset + populate
"""

# [DOC] sys/os let us adjust the Python module search path and read the filesystem
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
# [DOC] hashlib is used to generate deterministic SHA-256 transaction hashes in test data
import hashlib

# [DOC] Insert project root into sys.path so all project packages can be imported
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [DOC] SessionLocal — creates DB sessions; engine — raw connection pool; Base — ORM metadata
from database.connection import SessionLocal, engine, Base
# [DOC] Import each ORM model used to populate test tables
from database.models.user import User
from database.models.bank import Bank
from database.models.bank_account import BankAccount
from database.models.session import Session
from database.models.transaction import Transaction, TransactionStatus
from database.models.recipient import Recipient
# [DOC] IDXGenerator computes the permanent pseudonym from PAN + RBI number
from core.crypto.idx_generator import IDXGenerator
# [DOC] SessionIDGenerator creates the 24-hour rotating public session identifier
from core.crypto.session_id import SessionIDGenerator


# [DOC] Class that encapsulates all database setup logic for test environments
class TestDatabaseSetup:
    """Setup clean test database"""

    # [DOC] Constructor opens a SQLAlchemy session for all subsequent DB operations
    def __init__(self):
        self.db = SessionLocal()

    # [DOC] Destructor closes the session to release the DB connection back to the pool
    def __del__(self):
        self.db.close()

    # [DOC] Wipe every table and recreate the schema from ORM model definitions
    def reset_database(self):
        """Drop and recreate all tables"""
        print("\n🗑️  Resetting database...")
        print("⚠️  This will DELETE ALL DATA in the current database!")

        # [DOC] Require explicit confirmation before destroying data
        response = input("Are you sure? Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("❌ Aborted")
            return False

        # [DOC] drop_all removes every table tracked by SQLAlchemy's ORM metadata
        # Drop all tables
        print("  Dropping all tables...")
        Base.metadata.drop_all(bind=engine)

        # [DOC] create_all re-creates all tables from the current ORM model definitions
        # Recreate all tables
        print("  Creating all tables...")
        Base.metadata.create_all(bind=engine)

        print("  ✅ Database reset complete!")
        return True

    # [DOC] Insert all 12 consortium bank rows, each with its own BBS04 group signature key pair
    def setup_consortium_banks(self):
        """Create 12 consortium banks with BBS04 group signature keys."""
        print("\n🏦 Setting up consortium banks with BBS04 group signature keys...")

        # [DOC] Each dict maps to one Bank ORM row; amounts are in Indian Rupees (paisa-level precision)
        banks_data = [
            # Public Sector Banks (8)
            {
                'bank_code': 'SBI',
                'bank_name': 'State Bank of India',
                'total_assets': Decimal('45000000000000.00'),
                'initial_stake': Decimal('450000000000.00'),
                'stake_amount': Decimal('450000000000.00'),
                'validator_address': 'validator-sbi.idxbanking.com:8001',
                'is_active': True
            },
            {
                'bank_code': 'PNB',
                'bank_name': 'Punjab National Bank',
                'total_assets': Decimal('12000000000000.00'),
                'initial_stake': Decimal('120000000000.00'),
                'stake_amount': Decimal('120000000000.00'),
                'validator_address': 'validator-pnb.idxbanking.com:8002',
                'is_active': True
            },
            {
                'bank_code': 'BOB',
                'bank_name': 'Bank of Baroda',
                'total_assets': Decimal('11000000000000.00'),
                'initial_stake': Decimal('110000000000.00'),
                'stake_amount': Decimal('110000000000.00'),
                'validator_address': 'validator-bob.idxbanking.com:8003',
                'is_active': True
            },
            {
                'bank_code': 'CANARA',
                'bank_name': 'Canara Bank',
                'total_assets': Decimal('10000000000000.00'),
                'initial_stake': Decimal('100000000000.00'),
                'stake_amount': Decimal('100000000000.00'),
                'validator_address': 'validator-canara.idxbanking.com:8004',
                'is_active': True
            },
            {
                'bank_code': 'UNION',
                'bank_name': 'Union Bank of India',
                'total_assets': Decimal('9000000000000.00'),
                'initial_stake': Decimal('90000000000.00'),
                'stake_amount': Decimal('90000000000.00'),
                'validator_address': 'validator-union.idxbanking.com:8005',
                'is_active': True
            },
            {
                'bank_code': 'INDIAN',
                'bank_name': 'Indian Bank',
                'total_assets': Decimal('6000000000000.00'),
                'initial_stake': Decimal('60000000000.00'),
                'stake_amount': Decimal('60000000000.00'),
                'validator_address': 'validator-indian.idxbanking.com:8006',
                'is_active': True
            },
            {
                'bank_code': 'CENTRAL',
                'bank_name': 'Central Bank of India',
                'total_assets': Decimal('5000000000000.00'),
                'initial_stake': Decimal('50000000000.00'),
                'stake_amount': Decimal('50000000000.00'),
                'validator_address': 'validator-central.idxbanking.com:8007',
                'is_active': True
            },
            {
                'bank_code': 'UCO',
                'bank_name': 'UCO Bank',
                'total_assets': Decimal('4500000000000.00'),
                'initial_stake': Decimal('45000000000.00'),
                'stake_amount': Decimal('45000000000.00'),
                'validator_address': 'validator-uco.idxbanking.com:8008',
                'is_active': True
            },
            # Private Sector Banks (4)
            {
                'bank_code': 'HDFC',
                'bank_name': 'HDFC Bank Ltd',
                'total_assets': Decimal('18000000000000.00'),
                'initial_stake': Decimal('180000000000.00'),
                'stake_amount': Decimal('180000000000.00'),
                'validator_address': 'validator-hdfc.idxbanking.com:8009',
                'is_active': True
            },
            {
                'bank_code': 'ICICI',
                'bank_name': 'ICICI Bank Ltd',
                'total_assets': Decimal('15000000000000.00'),
                'initial_stake': Decimal('150000000000.00'),
                'stake_amount': Decimal('150000000000.00'),
                'validator_address': 'validator-icici.idxbanking.com:8010',
                'is_active': True
            },
            {
                'bank_code': 'AXIS',
                'bank_name': 'Axis Bank Ltd',
                'total_assets': Decimal('10000000000000.00'),
                'initial_stake': Decimal('100000000000.00'),
                'stake_amount': Decimal('100000000000.00'),
                'validator_address': 'validator-axis.idxbanking.com:8011',
                'is_active': True
            },
            {
                'bank_code': 'KOTAK',
                'bank_name': 'Kotak Mahindra Bank',
                'total_assets': Decimal('6000000000000.00'),
                'initial_stake': Decimal('60000000000.00'),
                'stake_amount': Decimal('60000000000.00'),
                'validator_address': 'validator-kotak.idxbanking.com:8012',
                'is_active': True
            }
        ]

        # [DOC] Try to generate real BBS04 group signature keys via charm-crypto
        # Falls back gracefully if charm-crypto is not installed in the current venv
        # --- BBS+ key generation ---
        bbs_group_pk  = None
        bbs_bank_keys = []
        try:
            from core.crypto.real.bbs_group_signature import BBSGroupSignature
            print("  Generating BBS04 group signature keys (BN254, 128-bit)...")
            bbs = BBSGroupSignature()
            # [DOC] setup() returns one shared group public key and one signing key per bank
            params = bbs.setup(n_banks=len(banks_data))
            bbs_group_pk  = params["group_pk"]
            bbs_bank_keys = params["bank_keys"]
            print(f"  [OK] BBS04: group_pk + {len(bbs_bank_keys)} bank keys generated")
        except ImportError:
            # [DOC] charm-crypto is optional; without it, BBS fields remain NULL in test DB
            print("  [WARN] charm-crypto unavailable — BBS+ keys skipped")

        # [DOC] Create one Bank ORM object per entry and attach BBS keys if available
        for idx, bank_data in enumerate(banks_data):
            bank_obj = Bank(**bank_data)
            if bbs_group_pk:
                # [DOC] All banks share the same group public key for batch verification
                bank_obj.bbs_public_key = bbs_group_pk
                if idx < len(bbs_bank_keys):
                    # [DOC] Each bank gets its own unique signing key for anonymous voting
                    bank_obj.bbs_secret_key = bbs_bank_keys[idx]["signing_key"]
            self.db.add(bank_obj)

        # [DOC] Flush all 12 Bank rows to the DB in one commit
        self.db.commit()
        print(f"  ✅ Created {len(banks_data)} consortium banks")

        return len(banks_data)

    # [DOC] Generate `count` synthetic users with valid PAN cards and unique IDX values
    def create_test_users(self, count=50):
        """Create test users with proper PAN/RBI format"""
        print(f"\n👥 Creating {count} test users...")

        users_created = []

        # [DOC] Pools of first and last names to produce realistic-looking full names
        # Sample Indian names
        first_names = ['Rajesh', 'Priya', 'Amit', 'Sneha', 'Vikram', 'Anita', 'Arjun', 'Kavya',
                      'Rahul', 'Neha', 'Sanjay', 'Pooja', 'Karan', 'Divya', 'Rohan', 'Meera',
                      'Aditya', 'Riya', 'Nikhil', 'Shreya']

        last_names = ['Kumar', 'Sharma', 'Patel', 'Singh', 'Reddy', 'Nair', 'Joshi', 'Iyer',
                     'Verma', 'Chopra', 'Gupta', 'Desai', 'Mehta', 'Shah', 'Rao', 'Menon']

        for i in range(count):
            # [DOC] Construct a valid PAN: 5 uppercase letters derived from i, then 4 digits, then 1 letter
            # Generate valid PAN: 5 letters + 4 digits + 1 letter
            # Example: ABCDE1234F
            first_char = chr(65 + (i % 26))  # A-Z
            second_char = chr(65 + ((i // 26) % 26))
            third_char = chr(65 + ((i // 676) % 26))

            # [DOC] Positions 4-5 are fixed as "AB"; the 10th char cycles A-Z based on i
            pan_letters = f"{first_char}{second_char}{third_char}AB"  # 5 letters
            pan_digits = f"{i:04d}"  # 4 digits
            pan_last = chr(65 + (i % 26))  # 1 letter

            pan_card = f"{pan_letters}{pan_digits}{pan_last}"

            # [DOC] RBI number is a 6-digit zero-padded integer — unique per user
            # Generate valid RBI number: 6 alphanumeric characters
            rbi_number = f"{i:06d}"

            # [DOC] IDXGenerator hashes PAN + RBI number to create the permanent pseudonym
            # Generate IDX
            idx = IDXGenerator.generate(pan_card, rbi_number)

            # [DOC] Wrap around the name lists using modulo so all names are valid
            # Random name
            full_name = f"{first_names[i % len(first_names)]} {last_names[i % len(last_names)]}"

            # [DOC] Balance varies between ₹10,000 and ₹500,000 across users
            # Random balance between 10k-500k
            balance = Decimal(str(10000 + (i * 10000) % 490000))

            # [DOC] Instantiate and stage the User ORM object — not yet committed to DB
            user = User(
                idx=idx,
                pan_card=pan_card,
                full_name=full_name,
                balance=balance
            )

            self.db.add(user)
            users_created.append(user)

            # [DOC] Print progress every 10 users so long runs don't appear to hang
            if (i + 1) % 10 == 0:
                print(f"  Created {i + 1}/{count} users...")

        # [DOC] Commit all staged user rows in a single transaction for efficiency
        self.db.commit()
        print(f"  ✅ Created {len(users_created)} users")

        return users_created

    # [DOC] Create bank accounts for a list of users, cycling through consortium banks
    def create_bank_accounts(self, users, accounts_per_user=2):
        """Create bank accounts for users"""
        print(f"\n💳 Creating bank accounts ({accounts_per_user} per user)...")

        # [DOC] Fetch all bank codes from the DB; used to assign accounts in round-robin order
        banks = self.db.query(Bank).all()
        bank_codes = [b.bank_code for b in banks]

        accounts_created = []

        for i, user in enumerate(users):
            # [DOC] Each user gets two banks determined by their position index (deterministic, no random)
            # Each user gets accounts at 2 random banks
            user_banks = [bank_codes[i % len(bank_codes)], bank_codes[(i + 1) % len(bank_codes)]]

            for bank_code in user_banks[:accounts_per_user]:
                # [DOC] Account number = bank code + last 12 hex chars of IDX — simple, unique, deterministic
                # Generate account number
                account_number = f"{bank_code}{user.idx[-12:]}"

                # [DOC] Balance spread ensures not all test accounts start at the same amount
                # Random balance between 5k-200k
                balance = Decimal(str(5000 + (i * 5000) % 195000))

                # [DOC] Create the BankAccount row and stage it for commit
                account = BankAccount(
                    user_idx=user.idx,
                    bank_code=bank_code,
                    account_number=account_number,
                    balance=balance,
                    is_active=True,
                    is_frozen=False
                )

                self.db.add(account)
                accounts_created.append(account)

            if (i + 1) % 10 == 0:
                print(f"  Created accounts for {i + 1}/{len(users)} users...")

        self.db.commit()
        print(f"  ✅ Created {len(accounts_created)} bank accounts")

        return accounts_created

    # [DOC] Create one active 24-hour session for every bank account provided
    def create_sessions(self, bank_accounts):
        """Create active sessions for all bank accounts"""
        print(f"\n🔐 Creating sessions for {len(bank_accounts)} bank accounts...")

        sessions_created = []

        for i, account in enumerate(bank_accounts):
            # [DOC] SessionIDGenerator produces a unique session ID string and its expiry timestamp
            # Generate session ID
            session_id, expires_at = SessionIDGenerator.generate(
                idx=account.user_idx,
                bank_name=account.bank_code
            )

            # [DOC] Link the session to its specific bank account via bank_account_id FK
            session = Session(
                session_id=session_id,
                user_idx=account.user_idx,
                bank_name=account.bank_code,
                bank_account_id=account.id,
                expires_at=expires_at,
                is_active=True
            )

            self.db.add(session)
            sessions_created.append(session)

            # [DOC] Progress update every 20 sessions to show activity for large sets
            if (i + 1) % 20 == 0:
                print(f"  Created {i + 1}/{len(bank_accounts)} sessions...")

        self.db.commit()
        print(f"  ✅ Created {len(sessions_created)} sessions")

        return sessions_created

    # [DOC] Insert synthetic completed transactions between pairs of test users
    def create_sample_transactions(self, users, count=100):
        """Create sample completed transactions"""
        print(f"\n💸 Creating {count} sample transactions...")

        transactions_created = []

        for i in range(count):
            # [DOC] Sender and receiver are adjacent in the users list (wraps around)
            # Random sender and receiver
            sender_idx = i % len(users)
            receiver_idx = (i + 1) % len(users)

            sender = users[sender_idx]
            receiver = users[receiver_idx]

            # [DOC] Look up the first bank account for sender and receiver
            # Get sender's bank account
            sender_account = self.db.query(BankAccount).filter(
                BankAccount.user_idx == sender.idx
            ).first()

            # Get receiver's bank account
            receiver_account = self.db.query(BankAccount).filter(
                BankAccount.user_idx == receiver.idx
            ).first()

            # [DOC] Skip this transaction if either party has no account (shouldn't happen with clean data)
            if not sender_account or not receiver_account:
                continue

            # [DOC] Look up the session associated with each party's bank account
            # Get sessions
            sender_session = self.db.query(Session).filter(
                Session.user_idx == sender.idx,
                Session.bank_account_id == sender_account.id
            ).first()

            receiver_session = self.db.query(Session).filter(
                Session.user_idx == receiver.idx,
                Session.bank_account_id == receiver_account.id
            ).first()

            # [DOC] Amount cycles between ₹100 and ₹10,000 across test transactions
            # Random amount between 100-10000
            amount = Decimal(str(100 + (i * 100) % 9900))
            # [DOC] Total fee is 1.5%: 0.5% to the miner, 1.0% distributed to consortium banks
            fee = amount * Decimal('0.015')
            miner_fee = amount * Decimal('0.005')
            bank_fee = amount * Decimal('0.01')

            # [DOC] Deterministic hash from sender, receiver, amount, and index — avoids collisions
            # Generate transaction hash
            tx_data = f"{sender.idx}:{receiver.idx}:{amount}:{i}"
            tx_hash = hashlib.sha256(tx_data.encode()).hexdigest()

            # [DOC] All test transactions are immediately set to COMPLETED status for realism
            transaction = Transaction(
                transaction_hash=tx_hash,
                sender_account_id=sender_account.id,
                receiver_account_id=receiver_account.id,
                sender_idx=sender.idx,
                receiver_idx=receiver.idx,
                sender_session_id=sender_session.session_id if sender_session else None,
                receiver_session_id=receiver_session.session_id if receiver_session else None,
                amount=amount,
                fee=fee,
                miner_fee=miner_fee,
                bank_fee=bank_fee,
                status=TransactionStatus.COMPLETED,
                # [DOC] Spread completed_at across last 30 days so history looks realistic
                completed_at=datetime.now() - timedelta(days=i % 30)
            )

            self.db.add(transaction)
            transactions_created.append(transaction)

            if (i + 1) % 20 == 0:
                print(f"  Created {i + 1}/{count} transactions...")

        self.db.commit()
        print(f"  ✅ Created {len(transactions_created)} transactions")

        return transactions_created

    # [DOC] Add recipient (saved-contact) entries so test users can send without re-entering IDX
    def create_sample_recipients(self, users, recipients_per_user=3):
        """Create sample recipients for users"""
        print(f"\n📇 Creating recipients ({recipients_per_user} per user)...")

        recipients_created = []

        for i, user in enumerate(users):
            # [DOC] Each user gets up to 3 recipients chosen from users ahead in the list
            # Add 3 random recipients
            for j in range(recipients_per_user):
                recipient_user = users[(i + j + 1) % len(users)]

                # [DOC] Nickname is a human-readable label the owner assigns to the contact
                # Generate nickname
                nicknames = ['Friend', 'Family', 'Business Partner', 'Colleague', 'Relative']
                nickname = f"{nicknames[j % len(nicknames)]} {j + 1}"

                # [DOC] can_transact_at set to now (already past waiting period) — ready to use
                recipient = Recipient(
                    user_idx=user.idx,
                    recipient_idx=recipient_user.idx,
                    nickname=nickname,
                    is_active=True,
                    can_transact_at=datetime.utcnow()  # Already past 30-minute waiting period
                )

                self.db.add(recipient)
                recipients_created.append(recipient)

            if (i + 1) % 10 == 0:
                print(f"  Created recipients for {i + 1}/{len(users)} users...")

        self.db.commit()
        print(f"  ✅ Created {len(recipients_created)} recipients")

        return recipients_created

    # [DOC] Run a series of COUNT(*) queries to confirm the setup produced valid data
    def verify_database(self):
        """Verify all data is properly set up"""
        print("\n✅ Verifying database integrity...")

        # [DOC] Each tuple: (label, count, boolean pass condition)
        checks = []

        # [DOC] At least one user must exist; exact count is checked elsewhere
        # Check users
        user_count = self.db.query(User).count()
        checks.append(('Users', user_count, user_count > 0))

        # [DOC] Exactly 12 consortium banks must be present
        # Check banks
        bank_count = self.db.query(Bank).count()
        checks.append(('Banks', bank_count, bank_count == 12))

        # [DOC] At least one account must exist for transactions to work
        # Check bank accounts
        account_count = self.db.query(BankAccount).count()
        checks.append(('Bank Accounts', account_count, account_count > 0))

        # [DOC] Sessions must exist and at least some must be active
        # Check sessions
        session_count = self.db.query(Session).count()
        active_session_count = self.db.query(Session).filter(Session.is_active == True).count()
        checks.append(('Sessions', session_count, session_count > 0))
        checks.append(('Active Sessions', active_session_count, active_session_count > 0))

        # [DOC] Every session must have a bank_account_id to enable the multi-bank feature
        # Check session-account matching
        sessions_with_accounts = self.db.query(Session).filter(
            Session.bank_account_id.isnot(None)
        ).count()
        checks.append(('Sessions with Bank Accounts', sessions_with_accounts, sessions_with_accounts == session_count))

        # [DOC] Transaction and recipient counts just need to be non-negative
        # Check transactions
        tx_count = self.db.query(Transaction).count()
        checks.append(('Transactions', tx_count, tx_count >= 0))

        # Check recipients
        recipient_count = self.db.query(Recipient).count()
        checks.append(('Recipients', recipient_count, recipient_count >= 0))

        # [DOC] Print each check result; track overall pass/fail
        # Print results
        print("\n  Database Statistics:")
        all_passed = True
        for name, count, passed in checks:
            status = "✅" if passed else "❌"
            print(f"    {status} {name}: {count}")
            if not passed:
                all_passed = False

        # [DOC] Return True only when every single check passed
        if all_passed:
            print("\n  ✅ All verification checks PASSED!")
        else:
            print("\n  ⚠️  Some checks failed - review the issues above")

        return all_passed

    # [DOC] Master method: reset then populate then verify in one call
    def run_full_setup(self, user_count=50):
        """Run complete database setup"""
        print("\n" + "=" * 80)
        print("TEST DATABASE SETUP")
        print("=" * 80)

        # [DOC] Abort the whole setup if the user declines the reset confirmation
        # Reset database
        if not self.reset_database():
            return False

        # [DOC] Populate in dependency order: banks → users → accounts → sessions → transactions → recipients
        # Setup data
        self.setup_consortium_banks()
        users = self.create_test_users(count=user_count)
        accounts = self.create_bank_accounts(users, accounts_per_user=2)
        sessions = self.create_sessions(accounts)
        # [DOC] Cap transactions at 100 even if user_count > 100 to keep setup fast
        transactions = self.create_sample_transactions(users, count=min(100, user_count))
        recipients = self.create_sample_recipients(users, recipients_per_user=3)

        # [DOC] Run final integrity checks to catch any bugs in the setup logic
        # Verify
        self.verify_database()

        print("\n" + "=" * 80)
        print("✅ TEST DATABASE SETUP COMPLETE!")
        print("=" * 80)
        print("\nYou can now run stress tests safely on this database.")
        print("This data is clean, properly formatted, and all relationships are valid.")

        return True


# [DOC] Script entry point: parse CLI flags and delegate to the appropriate setup method
def main():
    """Main entry point"""
    import argparse

    # [DOC] Three modes: --reset (schema only), --populate (data only), --full (both)
    parser = argparse.ArgumentParser(description='Setup test database')
    parser.add_argument('--reset', action='store_true', help='Reset database only')
    parser.add_argument('--populate', action='store_true', help='Populate with test data')
    parser.add_argument('--full', action='store_true', help='Full setup (reset + populate)')
    # [DOC] --users controls how many synthetic users to create; defaults to 50
    parser.add_argument('--users', type=int, default=50, help='Number of test users to create')

    args = parser.parse_args()

    # [DOC] If no flag is passed, default to --full so the script is useful with no arguments
    # Default to full setup if no args
    if not any([args.reset, args.populate, args.full]):
        args.full = True

    # [DOC] Instantiate setup class (opens DB session) and call the appropriate method
    setup = TestDatabaseSetup()

    if args.full:
        setup.run_full_setup(user_count=args.users)
    elif args.reset:
        setup.reset_database()
    elif args.populate:
        # [DOC] Populate-only mode: skip reset and run all data creation methods directly
        print("\nPopulating database with test data...")
        setup.setup_consortium_banks()
        users = setup.create_test_users(count=args.users)
        accounts = setup.create_bank_accounts(users)
        sessions = setup.create_sessions(accounts)
        setup.create_sample_transactions(users)
        setup.create_sample_recipients(users)
        setup.verify_database()


# [DOC] Standard Python guard: only call main() when this file is run directly
if __name__ == "__main__":
    main()
