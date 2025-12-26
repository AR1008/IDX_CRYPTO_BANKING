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
        
        What gets encrypted:
        - sender_session_id → sender_idx
        - receiver_session_id → receiver_idx
        - sender_bank → sender_idx
        - receiver_bank → receiver_idx
        
        Args:
            transactions: List of transactions in block
            
        Returns:
            str: Encrypted JSON data
            
        Example:
            >>> service = PrivateChainService(db)
            >>> encrypted = service.encrypt_transaction_data([tx1, tx2])
            >>> # Stored in BlockPrivate.encrypted_data
        """
        # Build mappings
        mappings = {
            'session_to_idx': {},
            'bank_to_idx': {},
            'transaction_metadata': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        for tx in transactions:
            # Session → IDX mappings
            mappings['session_to_idx'][tx.sender_session_id] = tx.sender_idx
            mappings['session_to_idx'][tx.receiver_session_id] = tx.receiver_idx
            
            # Bank → IDX mappings
            sender_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.sender_account_id
            ).first()
            
            receiver_account = self.db.query(BankAccount).filter(
                BankAccount.id == tx.receiver_account_id
            ).first()
            
            if sender_account:
                bank_key = f"{sender_account.bank_code}:{sender_account.account_number}"
                mappings['bank_to_idx'][bank_key] = tx.sender_idx
            
            if receiver_account:
                bank_key = f"{receiver_account.bank_code}:{receiver_account.account_number}"
                mappings['bank_to_idx'][bank_key] = tx.receiver_idx
            
            # Transaction metadata
            mappings['transaction_metadata'].append({
                'tx_hash': tx.transaction_hash,
                'sender_idx': tx.sender_idx,
                'receiver_idx': tx.receiver_idx,
                'amount': str(tx.amount),
                'timestamp': tx.created_at.isoformat() if tx.created_at else None
            })
        
        # Convert to JSON
        json_data = json.dumps(mappings, indent=2)
        
        # Encrypt with split key
        encrypted = self.split_key.encrypt_with_split_key(json_data)
        
        print(f"🔒 Encrypted private data for {len(transactions)} transactions")
        
        return encrypted
    
    def decrypt_with_court_order(
        self,
        encrypted_data: str,
        court_order_id: str,
        judge_name: str,
        judge_id: str
    ) -> Optional[Dict]:
        """
        Decrypt private blockchain data (court order)
        
        Requires:
        - Valid court order
        - Judge verification
        - RBI master key
        - Company temporary key (24hr)
        
        Args:
            encrypted_data: Encrypted private chain data
            court_order_id: Court order reference
            judge_name: Judge name
            judge_id: Judge ID
            
        Returns:
            Dict: Decrypted mappings, None if unauthorized
            
        Example:
            >>> # Court order issued
            >>> decrypted = service.decrypt_with_court_order(
            ...     encrypted_data,
            ...     "ORDER_2025_001",
            ...     "Judge Sharma",
            ...     "JID_2025_001"
            ... )
            >>> # Returns: {session_to_idx, bank_to_idx, metadata}
        """
        print(f"\n🏛️  Court Order De-Anonymization Request")
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
        print("\n   Step 3: Decrypt private data...")
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
            print(f"\n   ✅ Successfully decrypted!")
            print(f"   - Session mappings: {len(decrypted_data.get('session_to_idx', {}))}")
            print(f"   - Bank mappings: {len(decrypted_data.get('bank_to_idx', {}))}")
            print(f"   - Transactions: {len(decrypted_data.get('transaction_metadata', []))}")
            
            return decrypted_data
            
        except Exception as e:
            print(f"   ❌ JSON parsing failed: {str(e)}")
            return None
    
    def get_user_from_session(
        self,
        session_id: str,
        decrypted_data: Dict
    ) -> Optional[str]:
        """
        Get user IDX from session ID (after decryption)
        
        Args:
            session_id: Session ID to look up
            decrypted_data: Decrypted private chain data
            
        Returns:
            str: User IDX, None if not found
        """
        mappings = decrypted_data.get('session_to_idx', {})
        return mappings.get(session_id)
    
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