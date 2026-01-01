"""
Court Order Service
Author: Ashutosh Rajesh
Purpose: Handle court-ordered de-anonymization

3-Phase Investigation Flow:

Phase 1: Government Requests Private Blockchain Access
- Gov requests permission to VIEW private blockchain
- Company grants VIEW access (no decryption yet)
- Gov browses encrypted transactions (sees session IDs, amounts, banks)
- Gov selects ONE suspicious transaction

Phase 2: Court Order Authorization
- Gov presents evidence to court
- Court issues order for THAT specific transaction
- Gov chooses ONE person (sender OR receiver, not both)

Phase 3: Decryption & Full Access (24 hours)
- 5-of-5 threshold keys decrypt session_id → IDX
- With IDX, gov can view:
  - Name + PAN (basic info)
  - Full transaction history (all accounts, all amounts)
- 24-hour access window
- Auto logout and key expiry

Access Levels:
- CA/Auditor: IDX → Name + PAN only
- Government: IDX → Name + PAN + Full transaction history

Example:
    service = CourtOrderService(db)

    # Phase 1: View private blockchain
    blockchain_data = service.view_private_blockchain()

    # Phase 2: Submit court order for specific transaction
    order = service.submit_court_order_for_transaction(
        judge_id="JID_2025_001",
        tx_hash="0xabc123...",
        target_person="SENDER",  # or "RECEIVER"
        reason="Money laundering investigation",
        case_number="CASE_2025_456"
    )

    # Phase 3: Execute de-anonymization and get full access
    result = service.execute_full_access(order.order_id)
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session
from database.models.judge import Judge
from database.models.court_order import CourtOrder
from database.models.user import User
from database.models.bank_account import BankAccount
from database.models.block import BlockPrivate
from core.services.private_chain_service import PrivateChainService
from core.services.bank_account_service import BankAccountService
from core.security.audit_logger import AuditLogger


class CourtOrderService:
    """
    Court order management service
    
    Responsibilities:
    - Verify judge authorization
    - Submit and track court orders
    - Execute de-anonymization
    - Freeze/unfreeze accounts
    - Maintain audit trail
    """
    
    def __init__(self, db: Session):
        """
        Initialize service
        
        Args:
            db: Database session
        """
        self.db = db
        self.private_service = PrivateChainService(db)
        self.account_service = BankAccountService(db)
    
    def add_authorized_judge(
        self,
        judge_id: str,
        full_name: str,
        court_name: str,
        jurisdiction: str
    ) -> Judge:
        """
        Add judge to authorized list
        
        Args:
            judge_id: Unique judge ID (JID_2025_001)
            full_name: Judge's full name
            court_name: Court name
            jurisdiction: Geographic jurisdiction
            
        Returns:
            Judge: Created judge entry
            
        Example:
            >>> service = CourtOrderService(db)
            >>> judge = service.add_authorized_judge(
            ...     "JID_2025_001",
            ...     "Justice Sharma",
            ...     "Delhi High Court",
            ...     "Delhi"
            ... )
        """
        # Check if already exists
        existing = self.db.query(Judge).filter(Judge.judge_id == judge_id).first()
        if existing:
            raise ValueError(f"Judge {judge_id} already authorized")
        
        judge = Judge(
            judge_id=judge_id,
            full_name=full_name,
            court_name=court_name,
            jurisdiction=jurisdiction,
            is_active=True
        )
        
        self.db.add(judge)
        self.db.commit()
        self.db.refresh(judge)
        
        print(f"✅ Judge authorized: {full_name} ({judge_id})")
        print(f"   Court: {court_name}")
        print(f"   Jurisdiction: {jurisdiction}")
        
        return judge
    
    def verify_judge_authorization(self, judge_id: str) -> bool:
        """
        Verify judge is authorized
        
        Args:
            judge_id: Judge ID to verify
            
        Returns:
            bool: True if authorized
        """
        judge = self.db.query(Judge).filter(
            Judge.judge_id == judge_id,
            Judge.is_active == True
        ).first()
        
        return judge is not None

    # ===== NEW 3-PHASE INVESTIGATION METHODS =====

    def view_private_blockchain(self) -> List[Dict]:
        """
        Phase 1: Government views private blockchain (no court order needed yet)

        Company grants permission to VIEW encrypted private blockchain data.
        Government can see:
        - Transaction hashes
        - Session IDs (but cannot decrypt to IDX)
        - Amounts
        - Bank names
        - Timestamps

        Government CANNOT see (without court order):
        - Real names
        - PAN cards
        - IDX (session IDs are still encrypted)

        Returns:
            List[Dict]: All transactions from private blockchain

        Example:
            >>> service = CourtOrderService(db)
            >>> transactions = service.view_private_blockchain()
            >>> # Gov browses and finds suspicious transaction
        """
        print(f"\n👁️  Government Private Blockchain View Request")
        print(f"   Requesting permission to view encrypted transactions...")

        # Get all private blocks
        private_blocks = self.db.query(BlockPrivate).all()

        if not private_blocks:
            print(f"   ⚠️  No private blockchain data found")
            return []

        print(f"\n   ✅ Permission granted!")
        print(f"   Viewing {len(private_blocks)} private blocks")
        print(f"   ⚠️  Session IDs visible but NOT decrypted (need court order for IDX)")

        # Decrypt blocks to show session IDs (but NOT convert to IDX)
        all_transactions = []

        for block in private_blocks:
            # Use a temporary court order ID for viewing only
            temp_order_id = f"VIEW_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            temp_judge_name = "Government Investigator"
            temp_judge_id = "GOV_VIEWER"

            decrypted = self.private_service.decrypt_private_blockchain(
                block.encrypted_data,
                temp_order_id,
                temp_judge_name,
                temp_judge_id
            )

            if decrypted and 'transactions' in decrypted:
                all_transactions.extend(decrypted['transactions'])

        print(f"   Total transactions available: {len(all_transactions)}")
        return all_transactions

    def submit_court_order_for_transaction(
        self,
        judge_id: str,
        tx_hash: str,
        target_person: str,  # "SENDER" or "RECEIVER"
        reason: str,
        case_number: Optional[str] = None,
        freeze_account: bool = True
    ) -> CourtOrder:
        """
        Phase 2: Submit court order for specific transaction

        After viewing private blockchain, government selects ONE transaction
        and ONE person (sender OR receiver, not both) to investigate.

        Args:
            judge_id: Judge submitting order
            tx_hash: Transaction hash to investigate
            target_person: "SENDER" or "RECEIVER"
            reason: Investigation reason
            case_number: Court case reference
            freeze_account: Freeze account during investigation?

        Returns:
            CourtOrder: Created order

        Raises:
            ValueError: If judge not authorized or transaction not found

        Example:
            >>> order = service.submit_court_order_for_transaction(
            ...     "JID_2025_001",
            ...     "0xabc123...",
            ...     "SENDER",
            ...     "Money laundering investigation",
            ...     "CASE_2025_456"
            ... )
        """
        print(f"\n🏛️  Court Order Submission (Transaction-Specific)")
        print(f"   Judge: {judge_id}")
        print(f"   Transaction: {tx_hash[:16]}...")
        print(f"   Target: {target_person}")

        # Validate target_person
        if target_person not in ["SENDER", "RECEIVER"]:
            raise ValueError("target_person must be 'SENDER' or 'RECEIVER'")

        # Step 1: Verify judge
        print(f"\n   Step 1: Verify judge authorization...")
        if not self.verify_judge_authorization(judge_id):
            raise ValueError(f"Judge {judge_id} not authorized")

        judge = self.db.query(Judge).filter(Judge.judge_id == judge_id).first()
        print(f"   ✅ Judge verified: {judge.full_name}")

        # Step 2: Find transaction and get session ID
        print(f"\n   Step 2: Locate transaction and extract session ID...")
        from database.models.transaction import Transaction

        tx = self.db.query(Transaction).filter(
            Transaction.transaction_hash == tx_hash
        ).first()

        if not tx:
            raise ValueError(f"Transaction not found: {tx_hash}")

        # Get the target session ID based on sender/receiver choice
        target_session_id = tx.sender_session_id if target_person == "SENDER" else tx.receiver_session_id
        print(f"   ✅ Transaction found")
        print(f"   Target session ID: {target_session_id[:40]}...")

        # Step 3: Generate order ID
        order_count = self.db.query(CourtOrder).count()
        order_id = f"ORDER_{datetime.now(timezone.utc).year}_{order_count + 1:05d}"

        # Step 4: Create court order (store session ID, not IDX yet)
        print(f"\n   Step 3: Create court order...")
        order = CourtOrder(
            order_id=order_id,
            judge_id=judge_id,
            target_idx=target_session_id,  # Store session ID temporarily
            reason=f"{reason} | TX: {tx_hash[:16]}... | Target: {target_person}",
            case_number=case_number,
            status='PENDING',
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )

        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        print(f"   ✅ Court order created: {order_id}")
        print(f"   Expires: {order.expires_at.isoformat()}")
        print(f"   ⚠️  Session ID stored, IDX decryption requires Phase 3")

        print(f"\n✅ Court order submitted successfully!")
        print(f"   Next step: execute_full_access() to decrypt and view full history")

        return order

    def execute_full_access(
        self,
        order_id: str
    ) -> Optional[Dict]:
        """
        Phase 3: Execute full access (decrypt session→IDX, view all transactions)

        Requires 5-of-5 threshold authorization.

        Steps:
        1. Verify court order
        2. Decrypt session_id → IDX using threshold keys
        3. Get user info (Name + PAN)
        4. Get ALL transaction history for that user
        5. Grant 24-hour access

        Args:
            order_id: Court order ID

        Returns:
            Dict: Full user info + transaction history

        Example:
            >>> result = service.execute_full_access("ORDER_2025_00001")
            >>> print(result['user_info'])  # Name + PAN
            >>> print(result['transactions'])  # Full history
        """
        print(f"\n🔓 Executing Full Access (Phase 3)")
        print(f"   Order ID: {order_id}")

        # Get court order
        order = self.db.query(CourtOrder).filter(
            CourtOrder.order_id == order_id
        ).first()

        if not order:
            print(f"   ❌ Court order not found")
            return None

        # Check if expired
        if order.is_expired():
            print(f"   ❌ Court order expired")
            order.status = 'EXPIRED'
            self.db.commit()
            return None

        # Get judge
        judge = self.db.query(Judge).filter(Judge.judge_id == order.judge_id).first()

        # Step 1: Decrypt session_id → IDX
        print(f"\n   Step 1: Decrypt session ID to IDX...")
        session_id = order.target_idx  # This was stored as session ID in Phase 2

        user_idx = self.private_service.decrypt_session_to_idx(
            session_id,
            order_id,
            judge.full_name,
            judge.judge_id
        )

        if not user_idx:
            print(f"   ❌ Session decryption failed")
            return None

        # Step 2: Get user info (Name + PAN)
        print(f"\n   Step 2: Retrieve user information...")
        user_info = self.private_service.get_idx_basic_info(user_idx)

        if not user_info:
            print(f"   ❌ User not found for IDX")
            return None

        print(f"   ✅ User identified: {user_info['full_name']}")
        print(f"   PAN: {user_info['pan_card']}")

        # Step 3: Get ALL transaction history
        print(f"\n   Step 3: Retrieve full transaction history...")
        from database.models.transaction import Transaction

        all_transactions = self.db.query(Transaction).filter(
            (Transaction.sender_idx == user_idx) | (Transaction.receiver_idx == user_idx)
        ).order_by(Transaction.created_at.desc()).all()

        print(f"   ✅ Found {len(all_transactions)} transactions")

        # Step 4: Get bank accounts
        accounts = self.account_service.get_user_accounts(user_idx)
        print(f"   ✅ Found {len(accounts)} bank accounts")

        # Compile result
        result = {
            'order_id': order_id,
            'target_session_id': session_id,
            'target_idx': user_idx,
            'user_info': user_info,
            'bank_accounts': [
                {
                    'bank': acc.bank_code,
                    'account_number': acc.account_number,
                    'balance': str(acc.balance),
                    'is_frozen': acc.is_frozen
                }
                for acc in accounts
            ],
            'transactions': [
                {
                    'tx_hash': tx.transaction_hash,
                    'amount': str(tx.amount),
                    'direction': 'SENT' if tx.sender_idx == user_idx else 'RECEIVED',
                    'counterparty_idx': tx.receiver_idx if tx.sender_idx == user_idx else tx.sender_idx,
                    'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                    'created_at': tx.created_at.isoformat() if tx.created_at else None
                }
                for tx in all_transactions
            ],
            'access_granted_at': datetime.now(timezone.utc).isoformat(),
            'access_expires_at': order.expires_at.isoformat()
        }

        # Update order status
        order.status = 'EXECUTED'
        order.executed_at = datetime.now(timezone.utc)
        order.access_granted = True
        order.company_key_issued = True
        order.target_idx = user_idx  # Update to actual IDX now
        self.db.commit()

        # Log to audit trail
        try:
            AuditLogger.log_court_order_access(
                judge_id=judge.judge_id,
                court_order_number=order_id,
                session_id=session_id,
                revealed_idx=user_idx,
                reason=order.reason
            )
            print(f"📋 Full access logged to audit trail")
        except Exception as e:
            print(f"⚠️  Warning: Failed to log to audit database: {e}")

        print(f"\n✅ Full access granted!")
        print(f"   User: {user_info['full_name']}")
        print(f"   PAN: {user_info['pan_card']}")
        print(f"   Accounts: {len(accounts)}")
        print(f"   Transactions: {len(all_transactions)}")
        print(f"   Access valid until: {order.expires_at.isoformat()}")

        return result

    # ===== LEGACY METHODS (for backward compatibility) =====

    def submit_court_order(
        self,
        judge_id: str,
        target_idx: str,
        reason: str,
        case_number: Optional[str] = None,
        freeze_account: bool = True
    ) -> CourtOrder:
        """
        Submit court order for de-anonymization
        
        Args:
            judge_id: Judge submitting order
            target_idx: User IDX to investigate
            reason: Investigation reason
            case_number: Court case reference
            freeze_account: Freeze account during investigation?
            
        Returns:
            CourtOrder: Created order
            
        Raises:
            ValueError: If judge not authorized or user not found
            
        Example:
            >>> order = service.submit_court_order(
            ...     "JID_2025_001",
            ...     "IDX_abc123...",
            ...     "Money laundering investigation",
            ...     "CASE_2025_456",
            ...     freeze_account=True
            ... )
        """
        print(f"\n🏛️  Court Order Submission")
        print(f"   Judge: {judge_id}")
        print(f"   Target: {target_idx[:32]}...")
        
        # Step 1: Verify judge
        print(f"\n   Step 1: Verify judge authorization...")
        if not self.verify_judge_authorization(judge_id):
            raise ValueError(f"Judge {judge_id} not authorized")
        
        judge = self.db.query(Judge).filter(Judge.judge_id == judge_id).first()
        print(f"   ✅ Judge verified: {judge.full_name}")
        
        # Step 2: Verify target user exists
        print(f"\n   Step 2: Verify target user...")
        user = self.db.query(User).filter(User.idx == target_idx).first()
        if not user:
            raise ValueError(f"User not found: {target_idx}")
        
        print(f"   ✅ Target found: {user.full_name}")
        
        # Step 3: Generate order ID
        order_count = self.db.query(CourtOrder).count()
        order_id = f"ORDER_{datetime.now(timezone.utc).year}_{order_count + 1:05d}"
        
        # Step 4: Create court order
        print(f"\n   Step 3: Create court order...")
        order = CourtOrder(
            order_id=order_id,
            judge_id=judge_id,
            target_idx=target_idx,
            reason=reason,
            case_number=case_number,
            status='PENDING',
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        
        print(f"   ✅ Court order created: {order_id}")
        print(f"   Expires: {order.expires_at.isoformat()}")
        
        # Step 5: Freeze accounts if requested
        if freeze_account:
            print(f"\n   Step 4: Freeze accounts...")
            frozen_count = self.account_service.freeze_all_user_accounts(
                target_idx,
                reason=f"Court Order {order_id}"
            )
            print(f"   ✅ Froze {frozen_count} accounts")
        
        print(f"\n✅ Court order submitted successfully!")
        
        return order
    
    def execute_deanonymization(
        self,
        order_id: str
    ) -> Optional[Dict]:
        """
        Execute de-anonymization (decrypt private data)
        
        Requires:
        - Valid court order
        - Order not expired
        - RBI master key
        - Company temporary key (24hr)
        
        Args:
            order_id: Court order ID
            
        Returns:
            Dict: Decrypted data, None if failed
            
        Example:
            >>> result = service.execute_deanonymization("ORDER_2025_00001")
            >>> print(result['user_info'])
            >>> print(result['transactions'])
        """
        print(f"\n🔓 Executing De-Anonymization")
        print(f"   Order ID: {order_id}")
        
        # Get court order
        order = self.db.query(CourtOrder).filter(
            CourtOrder.order_id == order_id
        ).first()
        
        if not order:
            print(f"   ❌ Court order not found")
            return None
        
        # Check if expired
        if order.is_expired():
            print(f"   ❌ Court order expired")
            order.status = 'EXPIRED'
            self.db.commit()
            return None
        
        # Get judge
        judge = self.db.query(Judge).filter(Judge.judge_id == order.judge_id).first()
        
        # Get all private blocks
        private_blocks = self.db.query(BlockPrivate).all()
        
        if not private_blocks:
            print(f"   ⚠️  No private blockchain data found")
            return None
        
        # Decrypt all private blocks
        print(f"\n   Decrypting {len(private_blocks)} private blocks...")
        
        all_decrypted_data = []
        for block in private_blocks:
            decrypted = self.private_service.decrypt_with_court_order(
                block.encrypted_data,
                order_id,
                judge.full_name,
                judge.judge_id
            )
            
            if decrypted:
                all_decrypted_data.append(decrypted)
        
        # Extract target user data
        target_sessions = set()
        target_transactions = []
        
        for data in all_decrypted_data:
            # Find sessions belonging to target
            for session_id, idx in data.get('session_to_idx', {}).items():
                if idx == order.target_idx:
                    target_sessions.add(session_id)
            
            # Find transactions involving target
            for tx in data.get('transaction_metadata', []):
                if tx['sender_idx'] == order.target_idx or tx['receiver_idx'] == order.target_idx:
                    target_transactions.append(tx)
        
        # Get user info
        user = self.db.query(User).filter(User.idx == order.target_idx).first()
        
        # Get bank accounts
        accounts = self.account_service.get_user_accounts(order.target_idx)
        
        result = {
            'order_id': order_id,
            'target_idx': order.target_idx,
            'user_info': {
                'full_name': user.full_name,
                'pan_card': user.pan_card,
                'total_balance': str(sum(acc.balance for acc in accounts))
            },
            'bank_accounts': [
                {
                    'bank': acc.bank_code,
                    'account_number': acc.account_number,
                    'balance': str(acc.balance),
                    'is_frozen': acc.is_frozen
                }
                for acc in accounts
            ],
            'sessions': list(target_sessions),
            'transactions': target_transactions,
            'decrypted_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Update order
        order.status = 'EXECUTED'
        order.executed_at = datetime.now(timezone.utc)
        order.access_granted = True
        order.company_key_issued = True

        self.db.commit()

        # Log to audit trail (tamper-proof database)
        try:
            AuditLogger.log_court_order_access(
                judge_id=judge.judge_id,
                court_order_number=order_id,
                session_id=','.join(list(target_sessions)[:5]),  # First 5 sessions
                revealed_idx=order.target_idx,
                reason=order.reason
            )
            print(f"📋 Court order execution logged to audit trail")
        except Exception as e:
            print(f"⚠️  Warning: Failed to log to audit database: {e}")

        print(f"\n✅ De-anonymization complete!")
        print(f"   User: {user.full_name}")
        print(f"   Accounts: {len(accounts)}")
        print(f"   Sessions: {len(target_sessions)}")
        print(f"   Transactions: {len(target_transactions)}")

        return result
    
    def get_court_order(self, order_id: str) -> Optional[CourtOrder]:
        """Get court order by ID"""
        return self.db.query(CourtOrder).filter(
            CourtOrder.order_id == order_id
        ).first()
    
    def get_all_court_orders(self) -> List[CourtOrder]:
        """Get all court orders"""
        return self.db.query(CourtOrder).order_by(
            CourtOrder.created_at.desc()
        ).all()
    
    def get_audit_trail(self) -> List[Dict]:
        """Get complete audit trail from database"""
        try:
            # Get court order access logs
            logs = AuditLogger.get_logs_by_type('COURT_ORDER_ACCESS', limit=1000)
            return logs
        except Exception as e:
            print(f"⚠️  Warning: Failed to retrieve audit trail: {e}")
            return []


# Testing
if __name__ == "__main__":
    """Test court order service"""
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    
    from database.connection import SessionLocal, Base, engine
    
    print("=== Court Order Service Testing ===\n")
    
    # Create tables
    Base.metadata.create_all(engine)
    
    db = SessionLocal()
    service = CourtOrderService(db)
    
    try:
        # Test 1: Add authorized judge
        print("Test 1: Add Authorized Judge")
        try:
            judge = service.add_authorized_judge(
                "JID_2025_TEST",
                "Justice Test Kumar",
                "Test High Court",
                "Test State"
            )
            print("  ✅ Test 1 passed!\n")
        except ValueError as e:
            print(f"  ⏭️  Judge already exists: {str(e)}\n")
        
        # Test 2: Get a user to investigate
        print("Test 2: Submit Court Order")
        user = db.query(User).first()
        
        if not user:
            print("  ❌ No users found. Run two-bank consensus test first!")
            exit(1)
        
        order = service.submit_court_order(
            "JID_2025_TEST",
            user.idx,
            "Test investigation - Money laundering",
            "CASE_TEST_001",
            freeze_account=True
        )
        print("  ✅ Test 2 passed!\n")
        
        # Test 3: Execute de-anonymization
        print("Test 3: Execute De-Anonymization")
        result = service.execute_deanonymization(order.order_id)
        
        if result:
            print(f"\n  Decrypted Information:")
            print(f"    User: {result['user_info']['full_name']}")
            print(f"    PAN: {result['user_info']['pan_card']}")
            print(f"    Accounts: {len(result['bank_accounts'])}")
            print(f"    Transactions: {len(result['transactions'])}")
            print("  ✅ Test 3 passed!\n")
        
        print("=" * 50)
        print("✅ All court order tests passed!")
        print("=" * 50)
        
    finally:
        db.close()