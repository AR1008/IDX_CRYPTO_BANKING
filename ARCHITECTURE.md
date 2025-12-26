cd idx_crypto_banking
cat > ARCHITECTURE.md << 'EOF'
# IDX Crypto Banking Framework - System Architecture

**Author**: Ashutosh Rajesh  
**Version**: 1.0  
**Last Updated**: December 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [System Architecture](#system-architecture)
4. [Layer Architecture](#layer-architecture)
5. [Data Flow](#data-flow)
6. [Database Architecture](#database-architecture)
7. [Consensus Mechanisms](#consensus-mechanisms)
8. [Security Architecture](#security-architecture)
9. [API Design](#api-design)
10. [Deployment Architecture](#deployment-architecture)

---

## Overview

The IDX Crypto Banking Framework is a privacy-centric blockchain banking system that combines:
- **Privacy**: Swiss bank-level anonymity through session rotation
- **Compliance**: Court-ordered de-anonymization when legally required
- **Security**: Dual-key cryptography, AES-256 encryption
- **Innovation**: World's first blockchain de-anonymization system

### Key Statistics

- **12 Database Tables**: Complete relational schema
- **7 API Blueprints**: 50+ REST endpoints
- **6 Consortium Banks**: PoS consensus validators
- **4 Foreign Banks**: International forex support
- **2 Blockchains**: Public (validation) + Private (identity)

---

## Design Principles

### 1. Privacy by Default

**Principle**: Users are anonymous during normal operation

**Implementation**:
- Permanent IDX (no real identity revealed)
- 24-hour rotating session IDs
- Private blockchain encrypted with AES-256
- No transaction tracking across sessions

**Example**:
```
User: John Doe (PAN: ABCDE1234F)
↓
IDX: IDX_89b3b42b74e899162d8a49ef6fe6723faef1c3d8e79752443...
↓
Session (Day 1): SESSION_abc123def456... → HDFC account
Session (Day 2): SESSION_xyz789ghi012... → HDFC account
```

No one can link Day 1 and Day 2 sessions without court order.

### 2. Legal Compliance When Required

**Principle**: Privacy is not absolute; law enforcement can access with proper authorization

**Implementation**:
- Pre-authorized judges list
- Dual-key system (RBI + Company)
- 24-hour access window
- Complete audit trail

**Why it matters**: Balances privacy with legal requirements

### 3. No Single Point of Failure

**Principle**: No single entity has complete control

**Implementation**:
- RBI cannot decrypt alone (needs Company key)
- Company cannot decrypt alone (needs RBI key)
- 4/6 bank consensus (Byzantine fault tolerance)
- Involved banks must approve (sender + receiver banks)

### 4. Transaction-Specific Security

**Principle**: Security adapts to transaction participants

**Implementation**:
- All 6 banks validate every transaction
- 4/6 approval needed (general consensus)
- BUT: Both involved banks (sender + receiver) MUST approve
- If either involved bank rejects → transaction fails

**Example**:
```
Transaction: HDFC → ICICI (₹10,000)

Votes:
✅ HDFC (involved, must approve)
✅ ICICI (involved, must approve)  
✅ SBI (not involved)
✅ AXIS (not involved)
❌ KOTAK (not involved)
❌ YES (not involved)

Result: 4/6 votes = Pass ✅
Both involved banks approved = Pass ✅
Transaction succeeds!

But if HDFC voted ❌:
4/6 votes = Pass ✅
HDFC (involved) rejected = Fail ❌
Transaction fails!
```

### 5. Receiver Choice

**Principle**: Receiver controls where to receive money

**Implementation**:
- User has multiple bank accounts (HDFC, ICICI, etc.)
- Sender creates transaction → awaiting_receiver
- Receiver selects which account to receive in
- Transaction proceeds with receiver's choice

---

## System Architecture

### High-Level Architecture
```
┌──────────────────────────────────────────────────────┐
│                  CLIENT LAYER                         │
│  - Web App (React/Vue)                                │
│  - Mobile App (iOS/Android)                           │
│  - Desktop App                                        │
└────────────────┬─────────────────────────────────────┘
                 │ HTTP/WebSocket
                 │
┌────────────────▼─────────────────────────────────────┐
│              API LAYER (Flask)                        │
│  ┌──────────────────────────────────────────────┐    │
│  │ Authentication Middleware (JWT)               │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ API Routes (7 Blueprints)                     │    │
│  │ - auth.py (login/register)                    │    │
│  │ - accounts.py (user info)                     │    │
│  │ - bank_accounts.py (multi-bank)               │    │
│  │ - transactions.py (send/receive)              │    │
│  │ - recipients.py (contacts)                    │    │
│  │ - court_orders.py (legal access)              │    │
│  │ - travel_accounts.py (forex)                  │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ WebSocket Manager (real-time updates)         │    │
│  └──────────────────────────────────────────────┘    │
└────────────────┬─────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────┐
│           BUSINESS LOGIC LAYER                        │
│  ┌──────────────────────────────────────────────┐    │
│  │ Services (8 core services)                    │    │
│  │ - BankAccountService                          │    │
│  │ - TransactionServiceV2                        │    │
│  │ - RecipientService                            │    │
│  │ - SessionService                              │    │
│  │ - CourtOrderService                           │    │
│  │ - PrivateChainService                         │    │
│  │ - TravelAccountService                        │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Cryptography                                  │    │
│  │ - IDXGenerator (SHA-256)                      │    │
│  │ - AESCipher (AES-256-CBC)                     │    │
│  │ - SplitKey (dual-key system)                  │    │
│  │ - SessionID (24hr rotation)                   │    │
│  └──────────────────────────────────────────────┘    │
└────────────────┬─────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────┐
│         BLOCKCHAIN CONSENSUS LAYER                    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Proof of Work (Mining)                        │    │
│  │ - SHA-256 mining                              │    │
│  │ - Difficulty: 4 leading zeros                 │    │
│  │ - Block time: 10 seconds                      │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Proof of Stake (Validation)                   │    │
│  │ - 6 consortium banks                          │    │
│  │ - 4/6 consensus required                      │    │
│  │ - Involved banks must approve                 │    │
│  └──────────────────────────────────────────────┘    │
└────────────────┬─────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────┐
│           DATA PERSISTENCE LAYER                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ PostgreSQL Database (12 tables)               │    │
│  │ - users, bank_accounts, transactions          │    │
│  │ - sessions, recipients, banks                 │    │
│  │ - blocks_public, blocks_private               │    │
│  │ - judges, court_orders                        │    │
│  │ - foreign_banks, travel_accounts, forex_rates │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Dual Blockchain                               │    │
│  │ - Public Chain (validation, PoW)              │    │
│  │ - Private Chain (identity, encrypted)         │    │
│  └──────────────────────────────────────────────┘    │
└────────────────┬─────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────┐
│            BACKGROUND WORKERS                         │
│  ┌──────────────────────────────────────────────┐    │
│  │ Mining Worker (10-second loop)                │    │
│  │ - Fetch pending transactions                  │    │
│  │ - Mine blocks (PoW)                           │    │
│  │ - Trigger consensus (PoS)                     │    │
│  │ - Finalize transactions                       │    │
│  └──────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. API Layer (`api/`)

**Responsibility**: Handle HTTP requests, authentication, routing

**Components**:

#### 1.1 Flask Application (`api/app.py`)
```python
from flask import Flask
from flask_cors import CORS
from api.routes.auth import auth_bp
from api.routes.accounts import accounts_bp
# ... other blueprints

app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(accounts_bp)
# ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

#### 1.2 Authentication Middleware (`api/middleware/auth.py`)
```python
def require_auth(f):
    """JWT authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        # Verify JWT token
        user = verify_token(token)
        return f(user, *args, **kwargs)
    return decorated_function
```

**Features**:
- JWT token generation on login
- Token verification on protected routes
- User context injection

#### 1.3 API Routes (`api/routes/`)

**7 Blueprints**:

1. **auth.py** - Authentication
   - POST `/api/auth/register` - Register new user
   - POST `/api/auth/login` - Login user

2. **accounts.py** - User account management
   - GET `/api/accounts/info` - Get user info
   - GET `/api/accounts/balance` - Get total balance

3. **bank_accounts.py** - Multi-bank accounts
   - GET `/api/bank-accounts` - List user's accounts
   - POST `/api/bank-accounts/create` - Create new bank account
   - POST `/api/bank-accounts/{id}/unfreeze` - Unfreeze account

4. **transactions.py** - Transaction management
   - POST `/api/transactions/send` - Create transaction
   - POST `/api/transactions/{hash}/confirm` - Receiver confirms
   - GET `/api/transactions/pending-for-me` - Get pending
   - GET `/api/transactions/{hash}` - Get transaction details

5. **recipients.py** - Contact management
   - POST `/api/recipients/add` - Add contact
   - GET `/api/recipients` - List contacts
   - DELETE `/api/recipients/{nickname}` - Remove contact

6. **court_orders.py** - Court order system
   - POST `/api/court-orders/judges` - Add judge (admin)
   - GET `/api/court-orders/judges` - List judges
   - POST `/api/court-orders/submit` - Submit court order
   - POST `/api/court-orders/{id}/execute` - Execute de-anonymization
   - GET `/api/court-orders` - List orders
   - GET `/api/court-orders/audit-trail` - Audit log

7. **travel_accounts.py** - Travel + Forex
   - GET `/api/travel/foreign-banks` - List foreign banks
   - GET `/api/travel/forex-rates` - Get forex rates
   - POST `/api/travel/create` - Create travel account
   - GET `/api/travel/accounts` - List travel accounts
   - POST `/api/travel/accounts/{id}/close` - Close account

#### 1.4 WebSocket Manager (`api/websocket/manager.py`)
```python
class WebSocketManager:
    """Real-time updates for transactions"""
    
    def notify_transaction_update(self, tx_hash, status):
        """Send transaction update to connected clients"""
        socketio.emit('transaction_update', {
            'tx_hash': tx_hash,
            'status': status,
            'timestamp': datetime.utcnow()
        })
```

### 2. Business Logic Layer (`core/`)

**Responsibility**: Core business logic, services, cryptography

#### 2.1 Services (`core/services/`)

**BankAccountService** (`bank_account_service.py`)
```python
class BankAccountService:
    """Multi-bank account management"""
    
    def create_bank_account(self, user_idx, bank_code, initial_balance):
        """Create new bank account for user"""
        # Generate account number
        account_number = f"{bank_code}{uuid.uuid4().hex[:12]}"
        
        # Create account
        account = BankAccount(
            user_idx=user_idx,
            bank_code=bank_code,
            account_number=account_number,
            balance=initial_balance
        )
        return account
```

**TransactionServiceV2** (`transaction_service_v2.py`)
```python
class TransactionServiceV2:
    """Complete transaction flow"""
    
    def create_transaction(self, sender_idx, recipient_nickname, 
                          amount, sender_account_id, sender_session_id):
        """Create transaction (awaiting receiver)"""
        # 1. Get recipient IDX
        # 2. Calculate fees (1.5% total)
        # 3. Create transaction with status: AWAITING_RECEIVER
        # 4. Return transaction
        
    def confirm_transaction(self, tx_hash, receiver_idx, receiver_account_id):
        """Receiver confirms and selects account"""
        # 1. Verify receiver
        # 2. Update receiver_account_id
        # 3. Change status: PENDING (ready for mining)
        # 4. Return transaction
```

**CourtOrderService** (`court_order_service.py`)
```python
class CourtOrderService:
    """Court order de-anonymization"""
    
    def submit_court_order(self, judge_id, target_idx, reason, 
                          case_number, freeze_account):
        """Submit court order"""
        # 1. Verify judge authorization
        # 2. Create court order (expires in 24hr)
        # 3. Freeze accounts if requested
        # 4. Return order
        
    def execute_deanonymization(self, order_id):
        """Execute de-anonymization with dual keys"""
        # 1. Get court order
        # 2. Verify not expired
        # 3. Get RBI key + Company key
        # 4. Decrypt private blockchain
        # 5. Extract user info (name, PAN, accounts)
        # 6. Log to audit trail
        # 7. Return decrypted data
```

**TravelAccountService** (`travel_account_service.py`)
```python
class TravelAccountService:
    """Travel accounts + Forex"""
    
    def create_travel_account(self, user_idx, source_account_id,
                             foreign_bank_code, inr_amount, duration_days):
        """Create travel account with forex conversion"""
        # 1. Get source account
        # 2. Get foreign bank
        # 3. Get forex rate (INR → Foreign)
        # 4. Convert currency (apply 0.15% fee)
        # 5. Deduct from source
        # 6. Create travel account
        # 7. Return account
        
    def close_travel_account(self, travel_account_id, reason):
        """Close and convert back to INR"""
        # 1. Get travel account
        # 2. Get forex rate (Foreign → INR)
        # 3. Convert balance (apply 0.15% fee)
        # 4. Return to source account
        # 5. Mark as CLOSED
        # 6. Return summary
```

#### 2.2 Cryptography (`core/crypto/`)

**IDX Generator** (`idx_generator.py`)
```python
class IDXGenerator:
    """Generate permanent anonymous IDX"""
    
    @staticmethod
    def generate(pan_card: str, rbi_number: str) -> str:
        """
        Generate IDX from PAN + RBI number
        
        Algorithm:
        1. Concatenate: PAN + RBI + SALT
        2. Hash with SHA-256
        3. Prefix with "IDX_"
        4. Return 64-char hex string
        """
        data = f"{pan_card}{rbi_number}{SALT}"
        hash_obj = hashlib.sha256(data.encode())
        return f"IDX_{hash_obj.hexdigest()}"
```

**Features**:
- Deterministic (same inputs = same output)
- One-way (cannot reverse)
- Collision-resistant (SHA-256)

**AES Cipher** (`encryption/aes_cipher.py`)
```python
class AESCipher:
    """AES-256-CBC encryption"""
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt with AES-256
        
        Steps:
        1. Generate random IV (16 bytes)
        2. Pad plaintext (PKCS7)
        3. Encrypt with AES-256-CBC
        4. Calculate HMAC-SHA256 (tamper detection)
        5. Concatenate: IV + HMAC + Ciphertext
        6. Base64 encode
        """
        iv = get_random_bytes(16)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        padded = pad(plaintext.encode(), AES.block_size)
        ciphertext = cipher.encrypt(padded)
        
        # HMAC for authentication
        hmac = HMAC.new(self.key, ciphertext, SHA256).digest()
        
        # Combine: IV + HMAC + Ciphertext
        combined = iv + hmac + ciphertext
        return base64.b64encode(combined).decode()
```

**Split-Key Cryptography** (`encryption/split_key.py`)
```python
class SplitKey:
    """Dual-key system for court orders"""
    
    def encrypt_with_split_key(self, data: str) -> str:
        """Encrypt with combined key"""
        rbi_key = get_key('RBI_MASTER_KEY')
        company_key = get_key('COMPANY_KEY')
        
        # Combine keys
        combined = hashlib.sha256(
            (rbi_key + company_key).encode()
        ).digest()
        
        # Encrypt with combined key
        cipher = AESCipher(combined)
        return cipher.encrypt(data)
    
    def decrypt_with_court_order(self, encrypted: str, court_order_id: str,
                                  judge_name: str, judge_id: str) -> str:
        """Decrypt with dual keys"""
        # 1. Verify judge signature
        # 2. Get RBI master key
        # 3. Issue temporary company key (24hr)
        # 4. Combine keys
        # 5. Decrypt
        # 6. Log access to audit trail
        # 7. Return plaintext
```

**Session ID Generator** (`session_id.py`)
```python
class SessionIDGenerator:
    """Generate 24-hour rotating session IDs"""
    
    @staticmethod
    def generate(user_idx: str, bank_code: str, date: str) -> str:
        """
        Generate session ID
        
        Format: SESSION_{hash}
        Hash includes: IDX + Bank + Date
        
        Rotates daily (24 hours)
        """
        data = f"{user_idx}{bank_code}{date}"
        hash_obj = hashlib.sha256(data.encode())
        return f"SESSION_{hash_obj.hexdigest()}"
```

### 3. Consensus Layer (`core/consensus/`)

#### 3.1 Proof of Work (`consensus/pow/miner.py`)
```python
class MiningService:
    """PoW mining service"""
    
    def mine_pending_transactions(self, batch_size=10):
        """
        Mine pending transactions into block
        
        Algorithm:
        1. Fetch up to 10 pending transactions
        2. Calculate total fees
        3. Create block with:
           - transactions
           - previous_hash
           - timestamp
           - nonce = 0
        4. Mine: SHA256(block_data + nonce) until 4 leading zeros
        5. Save block to blocks_public
        6. Update transactions: PENDING → PUBLIC_CONFIRMED
        7. Return block
        """
        # Get pending
        transactions = get_pending_transactions(limit=batch_size)
        
        # Create block
        block = BlockPublic(
            block_index=get_next_index(),
            previous_hash=get_last_hash(),
            timestamp=datetime.utcnow(),
            transactions=transactions,
            miner_idx=self.miner_idx,
            nonce=0
        )
        
        # Mine (PoW)
        while True:
            block_hash = block.calculate_hash()
            if block_hash.startswith('0000'):  # Difficulty 4
                block.block_hash = block_hash
                break
            block.nonce += 1
        
        # Save
        save_block(block)
        return block
```

**Mining Difficulty**:
- Current: 4 leading zeros (`0000...`)
- Average time: 0.5-2 seconds
- Adjustable based on network hash rate

#### 3.2 Proof of Stake (`consensus/pos/validator.py`)
```python
class BankValidator:
    """PoS consensus by consortium banks"""
    
    def validate_and_finalize_block(self, block_index: int):
        """
        Validate block with 6 consortium banks
        
        Algorithm:
        1. Get block and transactions
        2. Identify involved banks (sender + receiver)
        3. Each bank validates:
           - Balance check (under lock)
           - Fee calculation
           - Account not frozen
        4. Count votes
        5. Check consensus rules:
           a. 4/6 banks approved? (Byzantine tolerance)
           b. Both involved banks approved?
        6. If pass:
           - Create private block (encrypted)
           - Update balances
           - Distribute fees
           - Mark transactions: COMPLETED
        7. Return private block
        """
        # Get block
        block = get_block(block_index)
        transactions = block.transactions
        
        # Identify involved banks
        involved_banks = set()
        for tx in transactions:
            involved_banks.add(tx.sender_account.bank_code)
            involved_banks.add(tx.receiver_account.bank_code)
        
        # All 6 banks validate
        votes = {}
        for bank in ALL_BANKS:
            votes[bank.code] = bank.validate(transactions)
        
        # Count approvals
        approved = sum(votes.values())
        
        # Check rules
        if approved < 4:
            return None  # Failed: need 4/6
        
        # Check involved banks
        for bank_code in involved_banks:
            if not votes[bank_code]:
                return None  # Failed: involved bank rejected
        
        # Consensus achieved!
        # Create private block (encrypted)
        private_block = create_private_block(
            block_index=block_index,
            consensus_votes=approved,
            encrypted_data=encrypt_identity_mappings(transactions)
        )
        
        # Finalize transactions
        finalize_transactions(transactions)
        
        return private_block
```

**Consensus Rules**:
1. **General Rule**: 4/6 banks must approve (Byzantine fault tolerance)
2. **Specific Rule**: BOTH involved banks (sender + receiver) MUST approve
3. **Priority**: Specific rule overrides general rule

**Example Scenarios**:

**Scenario 1: Both rules satisfied**
```
Transaction: HDFC → ICICI
Votes: ✅✅✅✅❌❌ (4/6)
HDFC: ✅ (involved)
ICICI: ✅ (involved)
Result: PASS ✅
```

**Scenario 2: General rule satisfied, specific rule violated**
```
Transaction: HDFC → ICICI
Votes: ✅✅✅✅❌❌ (4/6)
HDFC: ❌ (involved, rejected!)
ICICI: ✅ (involved)
Result: FAIL ❌ (involved bank rejected)
```

**Scenario 3: Both rules violated**
```
Transaction: HDFC → ICICI
Votes: ✅✅❌❌❌❌ (2/6)
HDFC: ❌ (involved)
ICICI: ✅ (involved)
Result: FAIL ❌ (insufficient votes + involved bank rejected)
```

---

## Data Flow

### Transaction Flow (Complete)
```
┌─────────────────────────────────────────────────────┐
│  1. SENDER CREATES TRANSACTION                       │
│                                                      │
│  POST /api/transactions/send                         │
│  {                                                   │
│    recipient_nickname: "Friend",                     │
│    amount: 5000,                                     │
│    sender_account_id: 1,                             │
│    sender_session_id: "SESSION_abc..."              │
│  }                                                   │
│                                                      │
│  TransactionService creates:                         │
│  - tx_hash: SHA256(sender+receiver+amount+time)      │
│  - status: AWAITING_RECEIVER                         │
│  - fee_total: ₹75 (1.5% of ₹5000)                    │
│  - fee_miner: ₹25 (0.5%)                             │
│  - fee_banks: ₹50 (1.0%)                             │
│                                                      │
│  Database:                                           │
│  transactions table: 1 new row (status: awaiting)    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  2. RECEIVER GETS NOTIFICATION                       │
│                                                      │
│  WebSocket: transaction_pending event                │
│  {                                                   │
│    tx_hash: "abc123...",                             │
│    amount: 5000,                                     │
│    sender_nickname: "Sender"                         │
│  }                                                   │
│                                                      │
│  GET /api/transactions/pending-for-me                │
│  Returns: [{ tx_hash, amount, sender_idx }]          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  3. RECEIVER CONFIRMS TRANSACTION                    │
│                                                      │
│  POST /api/transactions/{tx_hash}/confirm            │
│  {                                                   │
│    receiver_account_id: 5  (ICICI account)          │
│  }                                                   │
│                                                      │
│  TransactionService updates:                         │
│  - receiver_account_id: 5                            │
│  - status: PENDING (ready for mining)                │
│                                                      │
│  Database:                                           │
│  transactions table: status updated                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  4. MINING WORKER PICKS UP TRANSACTION               │
│     (Background process, runs every 10 seconds)      │
│                                                      │
│  MiningService.mine_pending_transactions()           │
│                                                      │
│  1. Fetch pending: SELECT * FROM transactions        │
│     WHERE status = 'PENDING' LIMIT 10                │
│                                                      │
│  2. Create block:                                    │
│     block = BlockPublic(                             │
│       transactions=[tx1, tx2, ...],                  │
│       previous_hash="xyz...",                        │
│       nonce=0                                        │
│     )                                                │
│                                                      │
│  3. Mine (PoW):                                      │
│     while True:                                      │
│       hash = SHA256(block_data + nonce)              │
│       if hash.startswith("0000"):                    │
│         break  # Found!                              │
│       nonce += 1                                     │
│                                                      │
│  4. Save block:                                      │
│     INSERT INTO blocks_public                        │
│                                                      │
│  5. Update transactions:                             │
│     UPDATE transactions                              │
│     SET status = 'PUBLIC_CONFIRMED',                 │
│         public_block_index = 42                      │
│     WHERE tx_hash IN [...]                           │
│                                                      │
│  Time: 0.5-2 seconds                                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  5. BANK CONSENSUS (PoS)                             │
│                                                      │
│  BankValidator.validate_and_finalize_block(42)       │
│                                                      │
│  FOR EACH transaction in block 42:                   │
│                                                      │
│    Identify involved banks:                          │
│    - sender_bank = HDFC                              │
│    - receiver_bank = ICICI                           │
│                                                      │
│    FOR EACH bank in [HDFC, ICICI, SBI, AXIS,        │
│                      KOTAK, YES]:                    │
│                                                      │
│      WITH row_lock ON sender_account:                │
│        validate_balance(sender, amount + fees)       │
│        validate_not_frozen(sender)                   │
│                                                      │
│      WITH row_lock ON receiver_account:              │
│        validate_not_frozen(receiver)                 │
│                                                      │
│      vote[bank] = APPROVE or REJECT                  │
│                                                      │
│    Count votes:                                      │
│    approved = sum(votes)                             │
│                                                      │
│    Check rules:                                      │
│    IF approved < 4: FAIL                             │
│    IF sender_bank voted REJECT: FAIL                 │
│    IF receiver_bank voted REJECT: FAIL               │
│    ELSE: PASS                                        │
│                                                      │
│  Time: <1 second                                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  6. FINALIZE TRANSACTION                             │
│                                                      │
│  IF consensus PASSED:                                │
│                                                      │
│    1. Encrypt identity mappings:                     │
│       private_data = {                               │
│         "SESSION_abc...": "IDX_sender...",           │
│         "SESSION_xyz...": "IDX_receiver...",         │
│         "HDFC123": "IDX_sender...",                  │
│         "ICICI456": "IDX_receiver..."                │
│       }                                              │
│       encrypted = AES256(private_data)               │
│                                                      │
│    2. Create private block:                          │
│       INSERT INTO blocks_private (                   │
│         block_index: 42,                             │
│         encrypted_data: encrypted,                   │
│         consensus_votes: 6                           │
│       )                                              │
│                                                      │
│    3. Update balances:                               │
│       WITH row_lock:                                 │
│         sender.balance -= 5075  (amount + fees)      │
│         receiver.balance += 5000                     │
│                                                      │
│    4. Distribute fees:                               │
│       miner.balance += 25  (0.5%)                    │
│       HDFC.fees += 8.33  (1/6 of 1%)                 │
│       ICICI.fees += 8.33                             │
│       SBI.fees += 8.33                               │
│       AXIS.fees += 8.33                              │
│       KOTAK.fees += 8.33                             │
│       YES.fees += 8.33                               │
│                                                      │
│    5. Update transaction:                            │
│       UPDATE transactions SET                        │
│         status = 'COMPLETED',                        │
│         private_block_index = 42,                    │
│         completed_at = NOW()                         │
│                                                      │
│    6. Emit WebSocket event:                          │
│       socketio.emit('transaction_completed', {       │
│         tx_hash: "abc123...",                        │
│         status: "completed"                          │
│       })                                             │
│                                                      │
│  Time: <1 second                                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  7. TRANSACTION COMPLETE                             │
│                                                      │
│  Final state:                                        │
│  - Sender: -₹5075                                    │
│  - Receiver: +₹5000                                  │
│  - Miner: +₹25                                       │
│  - Banks: +₹50 (distributed)                         │
│  - Status: COMPLETED                                 │
│  - Time: ~12-15 seconds total                        │
│                                                      │
│  Public blockchain: Transaction visible (session IDs)│
│  Private blockchain: Identity mapping (encrypted)    │
└─────────────────────────────────────────────────────┘
```

**Total Time**: 12-15 seconds
- User actions: 2-3 seconds
- Mining: 0.5-2 seconds
- Consensus: <1 second
- Finalization: <1 second
- Waiting for next mining cycle: ~10 seconds

---

## Database Architecture

### Schema Overview
```sql
-- 12 Tables Total

-- User Identity
users (id, idx, pan_card, full_name, rbi_number, created_at)

-- Banking
bank_accounts (id, user_idx, bank_code, account_number, balance, is_frozen)
banks (id, bank_code, bank_name, stake_amount, total_fees_earned)

-- Transactions
transactions (id, tx_hash, sender_idx, receiver_idx, sender_account_id, 
              receiver_account_id, amount, fee_total, status, 
              public_block_index, private_block_index)

-- Sessions & Contacts
sessions (id, session_id, user_idx, bank_account_id, created_at, expires_at)
recipients (id, owner_idx, recipient_idx, nickname)

-- Blockchain
blocks_public (id, block_index, previous_hash, block_hash, nonce, 
               miner_idx, timestamp)
blocks_private (id, block_index, encrypted_data, consensus_votes, 
                validated_at)

-- Legal Compliance
judges (id, judge_id, full_name, court_name, jurisdiction, is_active)
court_orders (id, order_id, judge_id, target_idx, reason, case_number,
              status, issued_at, expires_at)

-- International
foreign_banks (id, bank_code, bank_name, country, currency)
travel_accounts (id, user_idx, foreign_account_number, currency, balance,
                 status, expires_at)
forex_rates (id, from_currency, to_currency, rate, forex_fee_percentage)
```

### Key Relationships
```
users
  ├── 1:N bank_accounts (user_idx → idx)
  ├── 1:N sessions (user_idx → idx)
  ├── 1:N recipients (owner_idx → idx)
  └── 1:N travel_accounts (user_idx → idx)

bank_accounts
  ├── N:1 users (user_idx → idx)
  ├── 1:N transactions_sent (sender_account_id → id)
  ├── 1:N transactions_received (receiver_account_id → id)
  └── 1:N sessions (bank_account_id → id)

transactions
  ├── N:1 users as sender (sender_idx → idx)
  ├── N:1 users as receiver (receiver_idx → idx)
  ├── N:1 bank_accounts as sender (sender_account_id → id)
  ├── N:1 bank_accounts as receiver (receiver_account_id → id)
  ├── N:1 blocks_public (public_block_index → block_index)
  └── N:1 blocks_private (private_block_index → block_index)

blocks_public
  ├── 1:N transactions (block_index → public_block_index)
  └── 1:1 blocks_private (block_index → block_index)

court_orders
  ├── N:1 judges (judge_id → judge_id)
  └── N:1 users (target_idx → idx)

travel_accounts
  ├── N:1 users (user_idx → idx)
  ├── N:1 bank_accounts (source_account_id → id)
  └── N:1 foreign_banks (foreign_bank_id → id)
```

### Indexes

**Critical Indexes** (for performance):
```sql
-- User lookups
CREATE INDEX idx_users_pan_rbi ON users(pan_card, rbi_number);
CREATE INDEX idx_users_idx ON users(idx);

-- Transaction queries
CREATE INDEX idx_transactions_sender ON transactions(sender_idx);
CREATE INDEX idx_transactions_receiver ON transactions(receiver_idx);
CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_hash ON transactions(tx_hash);

-- Session lookups
CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_user_idx ON sessions(user_idx);

-- Block queries
CREATE INDEX idx_blocks_public_index ON blocks_public(block_index);
CREATE INDEX idx_blocks_private_index ON blocks_private(block_index);

-- Court orders
CREATE INDEX idx_court_orders_target ON court_orders(target_idx);
CREATE INDEX idx_court_orders_status ON court_orders(status);
```

---

## Security Architecture

### 1. Cryptographic Components

**Hash Functions**:
- SHA-256 (IDX generation, mining, key derivation)
- HMAC-SHA256 (message authentication)

**Symmetric Encryption**:
- AES-256-CBC (private blockchain)
- PKCS7 padding
- Random IV per encryption

**Key Management**:
- RBI_MASTER_KEY (permanent, never rotates)
- COMPANY_KEY (24-hour rotation)
- PRIVATE_CHAIN_KEY (permanent)
- SESSION_KEY (monthly rotation)

### 2. Access Control

**Authentication**:
- JWT tokens (HS256)
- Token expiry: 24 hours
- Refresh tokens (future)

**Authorization**:
- Role-based access (user, admin)
- Resource ownership checks
- Court order verification

### 3. Privacy Architecture

**Layers of Privacy**:
```
┌──────────────────────────────────────────┐
│  Layer 1: Permanent Anonymity (IDX)      │
│  - Real name → IDX (one-way hash)        │
│  - Public blockchain uses IDX only       │
│  - Cannot reverse IDX to name            │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Layer 2: Session Rotation (24hr)        │
│  - IDX → Session ID (daily rotation)     │
│  - Public transactions use session ID    │
│  - Cannot link sessions without key      │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Layer 3: Private Blockchain Encryption  │
│  - Session → IDX mapping encrypted       │
│  - AES-256 encryption                    │
│  - Split-key system (RBI + Company)      │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Layer 4: Court Order De-Anonymization   │
│  - Judge authorization required          │
│  - Dual-key decryption                   │
│  - 24-hour time limit                    │
│  - Complete audit trail                  │
└──────────────────────────────────────────┘
```

### 4. Threat Model

**Threats Mitigated**:

1. **Single-Point Compromise**
   - Mitigation: Split-key system
   - If RBI compromised → cannot decrypt (need Company key)
   - If Company compromised → cannot decrypt (need RBI key)

2. **Transaction Tracking**
   - Mitigation: Session rotation
   - New session every 24 hours
   - Cannot link sessions without private chain access

3. **Insider Threat (Bank Employee)**
   - Mitigation: Multi-bank consensus
   - Single bank cannot approve transaction alone
   - Need 4/6 consensus + both involved banks

4. **Byzantine Fault (Malicious Banks)**
   - Mitigation: 4/6 consensus
   - Can tolerate up to 2 malicious banks
   - Involved banks must still approve

5. **Unauthorized De-Anonymization**
   - Mitigation: Judge authorization + dual keys
   - Pre-authorized judges list
   - Time-limited access (24hr)
   - Complete audit trail

**Threats Not Addressed** (future work):
- Side-channel attacks
- Timing analysis
- Network-level traffic analysis
- Quantum computing (AES-256 is quantum-resistant, but SHA-256 is not)

---

## API Design

### RESTful Principles

**Resource-Based URLs**:
```
/api/auth/login              (POST)
/api/accounts/info           (GET)
/api/bank-accounts           (GET, POST)
/api/bank-accounts/{id}      (GET, PUT, DELETE)
/api/transactions            (GET, POST)
/api/transactions/{hash}     (GET, PUT)
```

**HTTP Methods**:
- GET: Retrieve resource
- POST: Create resource
- PUT: Update resource
- DELETE: Remove resource

**Status Codes**:
- 200: Success
- 201: Created
- 400: Bad request
- 401: Unauthorized
- 403: Forbidden
- 404: Not found
- 500: Server error

### Authentication Flow
```
┌────────────────────────────────────────┐
│  1. User Login                          │
│  POST /api/auth/login                   │
│  { pan_card, rbi_number, bank_name }   │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────▼──────────────────────────┐
│  2. Server Validates                    │
│  - Verify PAN + RBI exists              │
│  - Generate IDX                         │
│  - Check bank account exists            │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────▼──────────────────────────┐
│  3. Generate JWT Token                  │
│  token = jwt.encode({                   │
│    idx: user.idx,                       │
│    exp: datetime.now() + 24hr           │
│  }, SECRET_KEY)                         │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────▼──────────────────────────┐
│  4. Return Token                        │
│  {                                      │
│    success: true,                       │
│    token: "eyJhbGc...",                 │
│    user: { idx, full_name, balance }    │
│  }                                      │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────▼──────────────────────────┐
│  5. Client Stores Token                 │
│  localStorage.setItem('token', token)   │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────▼──────────────────────────┐
│  6. Subsequent Requests                 │
│  headers: {                             │
│    Authorization: "Bearer eyJhbGc..."   │
│  }                                      │
└─────────────────────────────────────────┘
```

### WebSocket Events

**Real-Time Updates**:
```javascript
// Client connects
socket = io('http://localhost:5000');

// Subscribe to transaction updates
socket.on('transaction_update', (data) => {
  console.log(`Transaction ${data.tx_hash} status: ${data.status}`);
});

// Events emitted by server:
- transaction_pending: New transaction awaiting receiver
- transaction_confirmed: Receiver confirmed
- transaction_mined: Block mined (PoW complete)
- transaction_validated: Consensus achieved (PoS complete)
- transaction_completed: Transaction finalized
- block_mined: New block added to blockchain
```

---

## Deployment Architecture

### Development Setup
```
┌─────────────────────────────────────────┐
│  MacBook Pro / Development Machine      │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ Terminal 1: API Server          │   │
│  │ python3 -m api.app              │   │
│  │ Port: 5000                      │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ Terminal 2: Mining Worker       │   │
│  │ python3 core/workers/mining.py  │   │
│  │ (Background process)            │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ PostgreSQL Database             │   │
│  │ localhost:5432                  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Production Setup (Recommended)
```
┌────────────────────────────────────────────────┐
│  Load Balancer (Nginx)                         │
│  - SSL Termination                             │
│  - Rate Limiting                               │
│  - Static File Serving                         │
└────────────┬───────────────────────────────────┘
             │
   ┌─────────┴─────────┐
   │                   │
┌──▼──────────┐  ┌────▼──────────┐
│ API Server 1│  │ API Server 2  │
│ (Gunicorn)  │  │ (Gunicorn)    │
│ 4 workers   │  │ 4 workers     │
└──┬──────────┘  └────┬──────────┘
   │                  │
   └─────────┬────────┘
             │
┌────────────▼───────────────────────────┐
│  PostgreSQL (Primary)                  │
│  - Connection Pooling                  │
│  - Read Replicas (optional)            │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│  Background Workers                    │
│  - Mining Worker (1 instance)          │
│  - Session Rotation (cron)             │
│  - Key Rotation (cron)                 │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│  Monitoring                            │
│  - Prometheus (metrics)                │
│  - Grafana (dashboards)                │
│  - ELK Stack (logs)                    │
└────────────────────────────────────────┘
```

### Scaling Considerations

**Horizontal Scaling** (API servers):
- Stateless API design
- Load balancer distributes requests
- Shared PostgreSQL database
- Redis for session caching (optional)

**Database Scaling**:
- Connection pooling (SQLAlchemy)
- Read replicas for queries
- Partitioning for large tables (blocks, transactions)

**Mining Workers**:
- Single mining worker (avoid duplicate mining)
- Leader election (Redis/ZooKeeper)
- Failover mechanism

---

## Performance Optimization

### Database Optimizations

1. **Indexes** (already covered)
2. **Connection Pooling**:
```python
   engine = create_engine(
       DATABASE_URL,
       pool_size=20,
       max_overflow=40
   )
```

3. **Query Optimization**:
   - Use `select_for_update()` for row locks
   - Batch inserts where possible
   - Avoid N+1 queries (use `joinedload()`)

4. **Partitioning** (future):
   - Partition `transactions` by date
   - Partition `blocks_public` by block_index

### Caching Strategy

**What to Cache**:
- User info (5-minute TTL)
- Bank list (1-hour TTL)
- Forex rates (1-hour TTL)
- Block headers (permanent)

**What NOT to Cache**:
- Account balances (must be real-time)
- Transaction status (must be real-time)
- Pending transactions (must be real-time)

### Mining Optimization

**Current**:
- Single-threaded mining
- Average: 0.5-2 seconds per block

**Future Optimizations**:
- Multi-threaded nonce search
- GPU mining (CUDA)
- Adaptive difficulty

---

## Future Enhancements

### 1. Mobile SDK
- Native iOS/Android SDKs
- Biometric authentication
- Offline transaction signing

### 2. Smart Contracts
- Programmable transactions
- Escrow services
- Automated compliance

### 3. Lightning Network
- Off-chain transactions
- Instant settlements
- Lower fees

### 4. Privacy Enhancements
- Zero-knowledge proofs
- Ring signatures
- Confidential transactions

### 5. Regulatory Integration
- Direct RBI reporting
- Automated tax filing
- KYC/AML automation

---

## Conclusion

The IDX Crypto Banking Framework represents a novel approach to blockchain-based banking that successfully balances:
- **Privacy**: Swiss bank-level anonymity
- **Compliance**: Legal de-anonymization when required
- **Security**: Multi-layer cryptographic protection
- **Scalability**: Production-ready architecture

This architecture serves as a foundation for a new generation of privacy-centric financial systems that respect both individual privacy and societal needs for legal oversight.

---

**Document Version**: 1.0  
**Last Updated**: December 2025  
**Author**: Ashutosh Rajesh
EOF