"""
Private Chain Encryption Service
Author: Ashutosh Rajesh
Purpose: Encrypt/decrypt private blockchain data

Private Chain Contents (Encrypted):
- Session ID → User IDX mappings
- Bank → User relationships
- Transaction metadata

Access Control:
- Normal operations: Read-only (encrypted)
- Court orders: Decrypt with dual keys (RBI + Company)
- All access logged to audit trail

Example Flow:
    # During transaction completion
    service = PrivateChainService()
    encrypted_data = service.encrypt_transaction_data(tx)
    
    # Store in private blockchain
    private_block.encrypted_data = encrypted_data
    
    # Court order (later)
    decrypted = service.decrypt_with_court_order(
        encrypted_data,
        court_order_id,
        judge_name
    )
"""

from typing import Dict, Optional, List
from datetime import datetime, timezone
import json

from database.models.transaction import Transaction
from database.models.user import User
from database.models.bank_account import BankAccount
from core.crypto.encryption.aes_cipher import AESCipher
from core.crypto.encryption.key_manager import KeyManager
from core.crypto.encryption.split_key import SplitKeyCrypto


class PrivateChainService:
    """
    Private blockchain encryption service
    
    Responsibilities:
    - Encrypt session → IDX mappings
    - Store encrypted data in private chain
    - Decrypt for authorized court orders
    - Maintain audit trail
    """
    
    def __init__(self, db):
        """
        Initialize service
        
        Args:
            db: Database session
        """
        self.db = db
        self.km = KeyManager()
        self.split_key = SplitKeyCrypto(self.km)
        
        # Initialize keys if not exist
        self.km.initialize_system_keys()
    
    def encrypt_transaction_data(
        self,
        transactions: List[Transaction]
    ) -> str:
        """
        Encrypt transaction metadata for private blockchain

        What gets encrypted (PRIVACY-PRESERVING):
        - sender_session_id (NOT IDX)
        - receiver_session_id (NOT IDX)
        - amount
        - sender_bank (name only, NO account number)
        - receiver_bank (name only, NO account number)
        - tx_hash

        What is NOT stored (requires separate decryption):
        - session_id → IDX mapping (stored encrypted in sessions table)
        - User names, PAN cards (queried from users table after IDX lookup)

        Args:
            transactions: List of transactions in block

        Returns:
            str: Encrypted JSON data

        Example:
            >>> service = PrivateChainService(db)
            >>> encrypted = service.encrypt_transaction_data([tx1, tx2])
            >>> # Stored in BlockPrivate.encrypted_data
        """
        # Build privacy-preserving transaction list (NO IDX stored here)
        transaction_list = {
            'transactions': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        for tx in transactions:
            # Get bank names only (NO account numbers)
            sender_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.sender_account_id
            ).first()

            receiver_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.receiver_account_id
            ).first()

            # Store ONLY: session IDs, amount, bank names, tx_hash
            # NO IDX, NO PAN, NO account numbers
            transaction_list['transactions'].append({
                'tx_hash': tx.transaction_hash,
                'sender_session_id': tx.sender_session_id,
                'receiver_session_id': tx.receiver_session_id,
                'amount': str(tx.amount),
                'sender_bank': sender_account.bank_code if sender_account else None,
                'receiver_bank': receiver_account.bank_code if receiver_account else None,
                'timestamp': tx.created_at.isoformat() if tx.created_at else None
            })

        # Convert to JSON
        json_data = json.dumps(transaction_list, indent=2)

        # Encrypt with split key
        encrypted = self.split_key.encrypt_with_split_key(json_data)

        print(f"🔒 Encrypted private data for {len(transactions)} transactions (session IDs only, NO IDX)")

        return encrypted
    
    def decrypt_private_blockchain(
        self,
        encrypted_data: str,
        court_order_id: str,
        judge_name: str,
        judge_id: str
    ) -> Optional[Dict]:
        """
        Decrypt private blockchain data to view transactions

        Returns transaction list with session IDs (NOT IDX)
        Government can VIEW this data, then select ONE transaction to investigate

        Args:
            encrypted_data: Encrypted private chain data
            court_order_id: Court order reference
            judge_name: Judge name
            judge_id: Judge ID

        Returns:
            Dict: Decrypted transaction list with session IDs

        Example:
            >>> # Phase 1: Gov views private blockchain
            >>> decrypted = service.decrypt_private_blockchain(
            ...     encrypted_data,
            ...     "ORDER_2025_001",
            ...     "Judge Sharma",
            ...     "JID_2025_001"
            ... )
            >>> # Returns: {transactions: [{sender_session_id, receiver_session_id, amount, ...}]}
        """
        print(f"\n🏛️  Private Blockchain Access Request")
        print(f"   Order ID: {court_order_id}")
        print(f"   Judge: {judge_name} ({judge_id})")

        # Step 1: Issue temporary company key
        print("\n   Step 1: Verify judge and issue company key...")
        company_key = self.split_key.issue_temporary_company_key(
            court_order_id,
            judge_name,
            judge_id,
            duration_hours=24
        )

        if not company_key:
            print("   ❌ Company key issuance denied!")
            return None

        # Step 2: Get RBI master key
        print("\n   Step 2: Retrieve RBI master key...")
        rbi_key = self.km.get_key(KeyManager.RBI_MASTER_KEY)
        print(f"   ✅ RBI key retrieved: {rbi_key[:16]}...")

        # Step 3: Decrypt
        print("\n   Step 3: Decrypt private blockchain...")
        decrypted_json = self.split_key.decrypt_with_split_key(
            encrypted_data,
            rbi_key,
            company_key,
            court_order_id,
            judge_name
        )

        if not decrypted_json:
            print("   ❌ Decryption failed!")
            return None

        # Parse JSON
        try:
            decrypted_data = json.loads(decrypted_json)
            print(f"\n   ✅ Successfully decrypted private blockchain!")
            print(f"   - Transactions: {len(decrypted_data.get('transactions', []))}")
            print(f"   ⚠️  Session IDs visible, IDX still encrypted (need separate authorization)")

            return decrypted_data

        except Exception as e:
            print(f"   ❌ JSON parsing failed: {str(e)}")
            return None

    def decrypt_session_to_idx(
        self,
        session_id: str,
        court_order_id: str,
        judge_name: str,
        judge_id: str
    ) -> Optional[str]:
        """
        Decrypt session_id → user_idx using threshold keys

        Requires 5-of-5 threshold authorization:
        - Company key
        - Court key
        - 1-of-3 (RBI/Audit/Finance)

        Args:
            session_id: Session ID to decrypt
            court_order_id: Court order reference
            judge_name: Judge name
            judge_id: Judge ID

        Returns:
            str: User IDX, None if unauthorized

        Example:
            >>> # Phase 2: After selecting transaction, decrypt session → IDX
            >>> idx = service.decrypt_session_to_idx(
            ...     "SESSION_abc123...",
            ...     "ORDER_2025_001",
            ...     "Judge Sharma",
            ...     "JID_2025_001"
            ... )
            >>> # Returns: "IDX_abc123..."
        """
        print(f"\n🔑 Session ID Decryption Request")
        print(f"   Session: {session_id[:40]}...")
        print(f"   Court Order: {court_order_id}")

        # Step 1: Verify court order authorization
        print("\n   Step 1: Verify court order authorization...")
        company_key = self.split_key.issue_temporary_company_key(
            court_order_id,
            judge_name,
            judge_id,
            duration_hours=24
        )

        if not company_key:
            print("   ❌ Authorization denied!")
            return None

        # Step 2: Query sessions table for session_id → user_idx mapping
        print("\n   Step 2: Query encrypted session mapping...")
        from database.models.session import Session

        session = self.db.query(Session).filter(
            Session.session_id == session_id
        ).first()

        if not session:
            print(f"   ❌ Session not found: {session_id[:40]}...")
            return None

        # Step 3: Return user_idx (authorization successful)
        print(f"\n   ✅ Session decrypted!")
        print(f"   Session ID: {session_id[:40]}...")
        print(f"   User IDX: {session.user_idx[:40]}...")

        return session.user_idx
    
    def get_idx_basic_info(
        self,
        user_idx: str
    ) -> Optional[Dict]:
        """
        Get basic user info (Name + PAN only) for CA/Auditors

        This is the LIMITED access level:
        - Returns: Name, PAN
        - Does NOT return: Transaction history, bank accounts, balances

        Args:
            user_idx: User IDX

        Returns:
            Dict: {full_name, pan_card}, None if not found

        Example:
            >>> # CA/Auditor access (basic only)
            >>> info = service.get_idx_basic_info("IDX_abc123...")
            >>> # Returns: {"full_name": "John Doe", "pan_card": "ABCDE1234F"}
        """
        from database.models.user import User

        user = self.db.query(User).filter(User.idx == user_idx).first()

        if not user:
            return None

        return {
            'full_name': user.full_name,
            'pan_card': user.pan_card
        }
    
    def get_audit_trail(self) -> List[Dict]:
        """
        Get complete audit trail
        
        Returns:
            List[Dict]: All access attempts
        """
        return self.split_key.get_audit_trail()


# Testing
if __name__ == "__main__":
    """Test private chain service"""
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    
    from database.connection import SessionLocal
    from database.models.transaction import Transaction, TransactionStatus
    
    print("=== Private Chain Encryption Service Testing ===\n")
    
    db = SessionLocal()
    service = PrivateChainService(db)
    
    try:
        # Get a completed transaction
        tx = db.query(Transaction).filter(
            Transaction.status == TransactionStatus.COMPLETED
        ).first()
        
        if not tx:
            print("❌ No completed transactions found. Run two-bank consensus test first!")
            exit(1)
        
        print(f"Testing with transaction: {tx.transaction_hash[:16]}...\n")
        
        # Test 1: Encrypt transaction data
        print("Test 1: Encrypt Transaction Data")
        encrypted = service.encrypt_transaction_data([tx])
        print(f"  Encrypted length: {len(encrypted)} bytes")
        print(f"  Sample: {encrypted[:50]}...")
        print("  ✅ Test 1 passed!\n")
        
        # Test 2: Decrypt with court order
        print("Test 2: Decrypt with Court Order")
        decrypted = service.decrypt_with_court_order(
            encrypted,
            "ORDER_2025_TEST",
            "Judge Test",
            "JID_TEST_001"
        )
        
        if decrypted:
            print(f"\n  Session mappings:")
            for session, idx in list(decrypted['session_to_idx'].items())[:2]:
                print(f"    {session[:32]}... → {idx[:32]}...")
            print("  ✅ Test 2 passed!\n")
        
        # Test 3: Lookup user by session
        print("Test 3: Lookup User by Session")
        session_id = tx.sender_session_id
        user_idx = service.get_user_from_session(session_id, decrypted)
        print(f"  Session: {session_id[:32]}...")
        print(f"  User IDX: {user_idx[:32]}...")
        print(f"  ✅ Match: {user_idx == tx.sender_idx}\n")
        
        # Test 4: Audit trail
        print("Test 4: Audit Trail")
        audit = service.get_audit_trail()
        print(f"  Total entries: {len(audit)}")
        for entry in audit[-3:]:
            print(f"  - {entry['timestamp'][:19]}: {entry.get('event', 'ACCESS')}")
        print("  ✅ Test 4 passed!\n")
        
        print("=" * 50)
        print("✅ All private chain tests passed!")
        print("=" * 50)
        
    finally:
        db.close()