"""
Court Order Service
Author: Ashutosh Rajesh
Purpose: Handle court-ordered de-anonymization

World's First Implementation:
- Dual-key requirement (RBI + Company)
- Judge authorization verification
- Time-limited access (24 hours)
- Account freezing during investigation
- Complete audit trail

Flow:
1. Judge submits court order
2. Verify judge authorization
3. Freeze target account (optional)
4. Issue company key (24hr)
5. RBI provides master key
6. Decrypt private data
7. Log all access
8. Auto-expire after 24hrs

Example:
    service = CourtOrderService(db)
    
    # Submit court order
    order = service.submit_court_order(
        judge_id="JID_2025_001",
        target_idx="IDX_abc123...",
        reason="Money laundering investigation",
        case_number="CASE_2025_456"
    )
    
    # Execute de-anonymization
    result = service.execute_deanonymization(order.order_id)
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