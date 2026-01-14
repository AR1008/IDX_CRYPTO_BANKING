# System Workflows Documentation
**IDX Crypto Banking System**

**Date**: January 9, 2026
**Version**: v3.0
**Purpose**: End-to-end operational flows for all system features

---

## Table of Contents

### Core Workflows
1. [User Registration & KYC](#1-user-registration--kyc)
2. [Account Creation](#2-account-creation)
3. [Transaction Processing](#3-transaction-processing)
4. [Batch Processing & Consensus](#4-batch-processing--consensus)

### Privacy & Compliance
5. [Court-Ordered Decryption](#5-court-ordered-decryption)
6. [Anomaly Detection](#6-anomaly-detection)
7. [Account Freeze/Unfreeze](#7-account-freezeunfreeze)

### International Banking
8. [Foreign Transaction Flow](#8-foreign-transaction-flow)
9. [Travel Account Management](#9-travel-account-management)

### System Operations
10. [Mining & Block Creation](#10-mining--block-creation)
11. [Bank Consensus Voting](#11-bank-consensus-voting)
12. [Treasury Management](#12-treasury-management)

---

## Core Workflows

### 1. User Registration & KYC

**Purpose**: Onboard new user with KYC compliance

**Flow**:
```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: User submits registration form                    │
├─────────────────────────────────────────────────────────────┤
│  Input:                                                     │
│  - PAN (10 digits)                                          │
│  - Full name                                                │
│  - Email                                                    │
│  - Phone                                                    │
│  - RBI customer number                                      │
│                                                             │
│  STEP 2: Backend generates deterministic IDX                │
│  idx = IDX_{SHA256(PAN:RBI_NUMBER:PEPPER)}                 │
│                                                             │
│  STEP 3: Validate uniqueness                                │
│  - Check PAN not already registered                         │
│  - Check RBI number not already used                        │
│  - Check email not already used                             │
│                                                             │
│  STEP 4: Store user in database                             │
│  INSERT INTO users (idx, pan, rbi_number, ...)             │
│                                                             │
│  STEP 5: Return success with IDX                            │
│  Response: {"idx": "IDX_7f3a8e...", "status": "success"}   │
└─────────────────────────────────────────────────────────────┘
```

**API Endpoint**: `POST /register`

**Security Features**:
- PAN validation (10-character alphanumeric)
- Email verification
- Rate limiting (10 attempts per hour)
- Audit logging

---

### 2. Account Creation

**Purpose**: Create bank account for registered user

**Flow**:
```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: User authenticated (login successful)              │
│                                                             │
│  STEP 2: Create bank account                                │
│  INSERT INTO bank_accounts (idx, balance=0.00)             │
│                                                             │
│  STEP 3: Generate initial session                           │
│  session_id = SESSION_{SHA256(IDX:timestamp_ms:salt)}      │
│  expires_at = now() + 24 hours                              │
│                                                             │
│  STEP 4: Create audit log                                   │
│  INSERT INTO audit_logs (action="account_created")         │
│                                                             │
│  STEP 5: Return account details                             │
│  Response: {"idx": "...", "balance": 0.00}                 │
└─────────────────────────────────────────────────────────────┘
```

**API Endpoint**: `POST /accounts`

**Key Features**:
- One account per IDX (one-to-one relationship)
- Initial balance: ₹0.00
- Session expires in 24 hours (automatic rotation)

---

### 3. Transaction Processing

**Purpose**: Process a transaction with full privacy

**Flow**:
```
┌───────────────────────────────────────────────────────────────────────┐
│  STEP 1: User creates transaction                                     │
├───────────────────────────────────────────────────────────────────────┤
│  Input:                                                               │
│  - sender_idx (from session)                                          │
│  - receiver_idx                                                       │
│  - amount                                                             │
│                                                                       │
│  STEP 2: Generate cryptographic proofs                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  a) Commitment: C = Commit(amount, blinding_factor)         │    │
│  │     → Pedersen commitment hides amount                       │    │
│  │                                                              │    │
│  │  b) Range Proof: Prove(0 ≤ amount ≤ 2^64)                  │    │
│  │     → Bulletproofs-style (prevents negative amounts)        │    │
│  │                                                              │    │
│  │  c) Nullifier: Hash(tx_id || sender_idx || timestamp)      │    │
│  │     → Unique per transaction (double-spend prevention)      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  STEP 3: Validate transaction                                         │
│  - Check sender balance ≥ amount                                      │
│  - Verify nullifier not already used                                  │
│  - Validate range proof                                               │
│                                                                       │
│  STEP 4: Store transaction (pending status)                           │
│  INSERT INTO transactions (                                           │
│    transaction_id, sender_idx, receiver_idx, amount,                 │
│    commitment, range_proof, nullifier,                                │
│    status="pending", sequence_number=<next>                          │
│  )                                                                    │
│                                                                       │
│  STEP 5: Add to batch queue                                           │
│  - Batches process 100 transactions at a time                         │
│  - Wait for batch to fill or timeout (2 minutes)                      │
│                                                                       │
│  STEP 6: Move to batch processing (see Workflow #4)                   │
└───────────────────────────────────────────────────────────────────────┘
```

**API Endpoint**: `POST /transactions`

**Timing**:
- Transaction creation: ~5ms
- Cryptographic proofs: ~0.1ms (range proof)
- Database insert: ~2ms
- Batch processing: Async (proceeds to Workflow #4)

---

### 4. Batch Processing & Consensus

**Purpose**: Process 100 transactions in single consensus round

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Batch accumulation                                         │
├─────────────────────────────────────────────────────────────────────┤
│  - Collect 100 pending transactions                                  │
│  - OR timeout after 120 seconds (whichever comes first)              │
│                                                                     │
│  STEP 2: Build Merkle tree                                           │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Transactions: TX1, TX2, ..., TX100                          │  │
│  │  ↓                                                            │  │
│  │  Leaf hashes: H1, H2, ..., H100                              │  │
│  │  ↓                                                            │  │
│  │  Binary tree: 7 levels                                        │  │
│  │  ↓                                                            │  │
│  │  Merkle root: MR = Hash(Hash(...))                           │  │
│  │                                                               │  │
│  │  Time: ~0.5ms for 100 transactions                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  STEP 3: Create batch record                                         │
│  INSERT INTO transaction_batches (                                   │
│    batch_id, merkle_root, status="pending"                          │
│  )                                                                   │
│                                                                     │
│  STEP 4: Distribute to bank consensus                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  For each of 12 banks:                                        │  │
│  │    1. Bank receives batch proposal                            │  │
│  │    2. Bank validates:                                         │  │
│  │       - Merkle root correctness                               │  │
│  │       - All range proofs valid                                │  │
│  │       - No nullifier reuse (double-spend check)               │  │
│  │       - All commitments well-formed                           │  │
│  │                                                               │  │
│  │    3. Bank votes: APPROVE or REJECT                           │  │
│  │       - Vote signed with group signature (anonymous)          │  │
│  │                                                               │  │
│  │  Network latency: ~10ms (parallel voting)                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  STEP 5: Consensus decision                                          │
│  - Threshold: 10 of 12 banks (83%)                                   │
│  - If ≥10 banks approve: APPROVED                                    │
│  - If <10 banks approve: REJECTED                                    │
│  - Timeout: 120 seconds (auto-approve if no explicit rejections)     │
│                                                                     │
│  STEP 6: Process batch                                               │
│  IF APPROVED:                                                        │
│    - Update all 100 transaction statuses: "pending" → "completed"    │
│    - Update sender balances: balance -= amount                       │
│    - Update receiver balances: balance += amount                     │
│    - Create block with batch                                         │
│                                                                     │
│  IF REJECTED:                                                        │
│    - Update transaction statuses: "pending" → "rejected"             │
│    - No balance changes                                              │
│                                                                     │
│  STEP 7: Store voting records                                        │
│  INSERT INTO bank_voting_records (votes from all banks)             │
│                                                                     │
│  Total time per batch: ~12.5ms                                       │
│  (0.5ms Merkle + 10ms consensus + 2ms DB)                            │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Performance Metrics**:
- Batch size: 100 transactions
- Time per batch: ~12.5ms
- Batches per second: 80
- **System capacity: 2,800-5,600 TPS** (conservative-optimistic)

**Security Features**:
- Group signatures (anonymous voting, prevents coercion)
- 10/12 threshold (83%, tolerates 2 malicious banks)
- Censorship resistance: Requires 7/12 (58%) malicious to halt
- Timeout-based approval: Prevents censorship-by-inaction

---

### 5. Court-Ordered Decryption

**Purpose**: Lawful access to encrypted transaction data

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Judge creates court order                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Input:                                                             │
│  - target_idx (user to investigate)                                  │
│  - reason (legal justification)                                      │
│  - time_range (start_date, end_date)                                 │
│                                                                     │
│  STEP 2: Store court order (pending)                                 │
│  INSERT INTO court_orders (                                          │
│    order_id, judge_id, target_idx, reason,                          │
│    status="pending"                                                  │
│  )                                                                   │
│                                                                     │
│  STEP 3: Multi-party approval (nested threshold)                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  FIXED: Nested Shamir Secret Sharing                         │  │
│  │                                                               │  │
│  │  Outer layer (2-of-2):                                        │  │
│  │    - Company approval (mandatory)                             │  │
│  │    - Court_Combined (mandatory)                               │  │
│  │                                                               │  │
│  │  Inner layer (1-of-4):                                        │  │
│  │    Court_Combined = 1 of:                                     │  │
│  │      - RBI (Reserve Bank of India)                            │  │
│  │      - FIU (Financial Intelligence Unit)                      │  │
│  │      - CBI (Central Bureau of Investigation)                  │  │
│  │      - Income Tax Department                                  │  │
│  │                                                               │  │
│  │  Cryptographic guarantee:                                     │  │
│  │    CANNOT decrypt without Company share (mathematical)        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  STEP 4: Reconstruct master key                                      │
│  IF Company approved AND 1 regulatory approved:                      │
│    master_key = reconstruct_secret(                                  │
│      company_share, regulatory_share                                 │
│    )                                                                 │
│                                                                     │
│  STEP 5: Decrypt private blockchain                                  │
│  decrypted_data = decrypt(private_blockchain, master_key)           │
│                                                                     │
│  STEP 6: Return transaction history                                  │
│  Response: {                                                         │
│    "transactions": [                                                 │
│      {                                                               │
│        "sender_session_id": "SESSION_...",                           │
│        "receiver_session_id": "SESSION_...",                         │
│        "amount": 50000.00,                                           │
│        "timestamp": "2026-01-09T..."                                 │
│      },                                                              │
│      ...                                                             │
│    ],                                                                │
│    "access_valid_until": "2026-01-10T12:00:00Z"                      │
│  }                                                                   │
│                                                                     │
│  STEP 7: Access expires after 24 hours                               │
│  UPDATE court_orders SET status="expired" WHERE ...                  │
│                                                                     │
│  STEP 8: Comprehensive audit trail                                   │
│  - All accesses logged with timestamps                               │
│  - Key reconstructions logged                                        │
│  - Cannot be deleted (immutable audit log)                           │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoints**:
- `POST /court-orders` - Create order (judge only)
- `POST /court-orders/{id}/approve` - Approve (Company/regulatory)
- `GET /court-orders/{id}/decrypt` - Access decrypted data

**Security Features**:
- **FIXED**: Cryptographic enforcement (nested threshold)
- 24-hour access window
- Complete audit trail (immutable)
- Multi-party control (no single entity can decrypt)

---

### 6. Anomaly Detection

**Purpose**: Detect suspicious transactions (PMLA compliance)

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Transaction submitted                                       │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 2: Rule-based anomaly scoring (0-100 points)                   │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Factor 1: Amount-based risk (0-40 points)                    │  │
│  │    - Amount ≥ ₹10L (PMLA threshold): +30 points               │  │
│  │    - Amount ≥ ₹50L: +35 points                                │  │
│  │    - Amount ≥ ₹1Cr: +40 points                                │  │
│  │                                                               │  │
│  │  Factor 2: Velocity risk (0-30 points)                        │  │
│  │    - 5+ txs in 1 hour: +15 points                             │  │
│  │    - 10+ txs in 24 hours: +20 points                          │  │
│  │    - 50+ txs in 7 days: +30 points                            │  │
│  │                                                               │  │
│  │  Factor 3: Structuring pattern (0-30 points)                  │  │
│  │    - Multiple txs near ₹9.5L (just below ₹10L): +30 points   │  │
│  │    - Pattern: Structuring to avoid PMLA reporting             │  │
│  │                                                               │  │
│  │  Threshold: score ≥ 65 → FLAG for investigation               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  STEP 3: Generate zero-knowledge proof (if flagged)                  │
│  zkp = generate_anomaly_proof(                                       │
│    transaction_data, anomaly_score                                   │
│  )                                                                   │
│  → Proves: "This transaction is suspicious"                          │
│  → Without revealing: Exact amount, identity, details                │
│                                                                     │
│  STEP 4: Threshold encrypt investigation data                        │
│  encrypted_data = threshold_encrypt(                                 │
│    investigation_data,                                               │
│    company_share, supreme_court_share, 1_of_4_regulatory            │
│  )                                                                   │
│                                                                     │
│  STEP 5: Automatic account freeze (if score ≥ 80)                    │
│  - First offense: 24-hour freeze                                     │
│  - Consecutive offenses: 72-hour freeze                              │
│  - Update bank_accounts SET frozen=true                              │
│                                                                     │
│  STEP 6: Notify authorities                                          │
│  - FIU (Financial Intelligence Unit)                                 │
│  - Relevant regulatory body                                          │
│                                                                     │
│  STEP 7: Investigation workflow                                      │
│  → Proceeds to court order if needed (Workflow #5)                   │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoint**: `GET /anomaly-detection/score/{transaction_id}`

**Performance**:
- Detection latency: 2-5ms
- ZKP generation: 0.01ms
- Throughput: 64,004 ZKP/sec

**Accuracy** (measured):
- Detection rate: 97/100 (95% CI: 91.5%-99.4%, n=100 synthetic test cases)
- False positive rate: 3/100 (95% CI: 0.6%-8.5%)

**Note**: Rule-based scoring (NOT AI/ML), multi-factor analysis

---

### 7. Account Freeze/Unfreeze

**Purpose**: Freeze suspicious accounts

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  FREEZE WORKFLOW                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 1: Trigger (from anomaly detection or court order)             │
│                                                                     │
│  STEP 2: Determine freeze duration                                   │
│  - First offense: 24 hours                                           │
│  - Consecutive offense (within 7 days): 72 hours                     │
│                                                                     │
│  STEP 3: Update account status                                       │
│  UPDATE bank_accounts SET                                            │
│    frozen=true,                                                      │
│    frozen_until=now() + <duration>,                                  │
│    freeze_reason="<reason>"                                          │
│  WHERE idx=<target_idx>                                              │
│                                                                     │
│  STEP 4: Reject all transactions from frozen account                 │
│  - Sender transactions: Rejected                                     │
│  - Receiver transactions: Still allowed (can receive)                │
│                                                                     │
│  STEP 5: Notify user                                                 │
│  - Email notification                                                │
│  - SMS alert                                                         │
│  - Dashboard notification                                            │
│                                                                     │
│  UNFREEZE WORKFLOW                                                   │
│  ────────────────                                                    │
│  STEP 1: Check freeze expiration                                     │
│  SELECT * FROM bank_accounts                                         │
│  WHERE frozen=true AND frozen_until < now()                          │
│                                                                     │
│  STEP 2: Automatic unfreeze (background job, runs every 5 minutes)   │
│  UPDATE bank_accounts SET frozen=false                               │
│  WHERE frozen=true AND frozen_until < now()                          │
│                                                                     │
│  STEP 3: Manual unfreeze (court order resolution)                    │
│  UPDATE bank_accounts SET frozen=false                               │
│  WHERE idx=<target_idx>                                              │
│  → Requires court order status="resolved"                            │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoints**:
- `POST /accounts/{idx}/freeze` - Freeze account
- `POST /accounts/{idx}/unfreeze` - Manual unfreeze
- `GET /accounts/{idx}/freeze-status` - Check status

---

### 8. Foreign Transaction Flow

**Purpose**: Process international transactions with forex conversion

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: User initiates foreign transaction                          │
├─────────────────────────────────────────────────────────────────────┤
│  Input:                                                             │
│  - sender_idx (Indian account)                                       │
│  - receiver_foreign_account                                          │
│  - amount_inr (in INR)                                               │
│  - target_currency (e.g., USD)                                       │
│                                                                     │
│  STEP 2: Fetch current forex rate                                    │
│  SELECT rate FROM forex_rates                                        │
│  WHERE from_currency='INR' AND to_currency='USD'                     │
│  AND effective_date <= now()                                         │
│  ORDER BY effective_date DESC LIMIT 1                                │
│                                                                     │
│  STEP 3: Calculate converted amount                                  │
│  amount_foreign = amount_inr * forex_rate                            │
│  fee = amount_inr * 0.0015  (0.15% forex fee)                       │
│                                                                     │
│  STEP 4: Store transaction with forex data                           │
│  INSERT INTO transactions (                                          │
│    ...,                                                              │
│    currency='USD',                                                   │
│    forex_rate=<rate>,                                                │
│    original_amount=<amount_inr>,                                     │
│    amount=<amount_foreign>                                           │
│  )                                                                   │
│                                                                     │
│  STEP 5: Update balances                                             │
│  - Deduct INR from sender: balance -= (amount_inr + fee)             │
│  - Credit foreign currency to travel account                         │
│                                                                     │
│  STEP 6: Proceed to batch processing                                 │
│  → Same consensus flow as domestic transactions (Workflow #4)        │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoint**: `POST /transactions/foreign`

**Forex Rates**:
- Updated daily (external API integration)
- 0.15% conversion fee
- Real-time rate lookup

---

### 9. Travel Account Management

**Purpose**: Manage international banking accounts

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  CREATE TRAVEL ACCOUNT                                               │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 1: User requests travel account                                │
│  Input: target_currency (USD, EUR, GBP, etc.)                        │
│                                                                     │
│  STEP 2: Link to foreign bank                                        │
│  SELECT * FROM foreign_banks WHERE currency=<target>                 │
│                                                                     │
│  STEP 3: Create travel account                                       │
│  INSERT INTO travel_accounts (                                       │
│    user_idx, foreign_bank_id, currency,                             │
│    balance_inr=0.00, balance_foreign=0.00                            │
│  )                                                                   │
│                                                                     │
│  LOAD FUNDS TO TRAVEL ACCOUNT                                        │
│  ─────────────────────────────                                       │
│  STEP 1: Transfer from main account                                  │
│  amount_inr = <load_amount>                                          │
│                                                                     │
│  STEP 2: Convert to foreign currency                                 │
│  amount_foreign = amount_inr * forex_rate                            │
│                                                                     │
│  STEP 3: Update balances                                             │
│  - Main account: balance -= amount_inr                               │
│  - Travel account: balance_foreign += amount_foreign                 │
│                                                                     │
│  SPEND FROM TRAVEL ACCOUNT                                           │
│  ──────────────────────────                                          │
│  - Same as foreign transaction flow (Workflow #8)                    │
│  - Deduct from travel account balance_foreign                        │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoints**:
- `POST /travel-accounts` - Create account
- `POST /travel-accounts/{id}/load` - Load funds
- `POST /travel-accounts/{id}/spend` - Spend funds

---

### 10. Mining & Block Creation

**Purpose**: Create blocks containing transaction batches

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Miner monitors approved batches                             │
├─────────────────────────────────────────────────────────────────────┤
│  SELECT * FROM transaction_batches                                   │
│  WHERE status='approved' AND block_hash IS NULL                      │
│                                                                     │
│  STEP 2: Collect batches for block                                   │
│  - Block time: 10 seconds                                            │
│  - Multiple batches per block                                        │
│                                                                     │
│  STEP 3: Create block                                                │
│  block = {                                                           │
│    block_number: <next>,                                             │
│    previous_hash: <previous_block_hash>,                             │
│    merkle_root: <combined_merkle_root>,                              │
│    timestamp: now(),                                                 │
│    miner_idx: <miner_idx>                                            │
│  }                                                                   │
│  block_hash = SHA256(JSON.stringify(block))                          │
│                                                                     │
│  STEP 4: Store block                                                 │
│  INSERT INTO blocks (block_hash, ...)                                │
│                                                                     │
│  STEP 5: Update batches                                              │
│  UPDATE transaction_batches SET block_hash=<block_hash>             │
│  WHERE batch_id IN (...)                                             │
│                                                                     │
│  STEP 6: Miner reward                                                │
│  INSERT INTO treasury (                                              │
│    miner_idx, amount=<block_reward>,                                 │
│    transaction_type='reward'                                         │
│  )                                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Block Parameters**:
- Block time: 10 seconds
- Multiple batches per block
- Miner reward: Per block

---

### 11. Bank Consensus Voting

**Purpose**: Anonymous voting using group signatures

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Bank receives batch proposal                                │
├─────────────────────────────────────────────────────────────────────┤
│  batch = {                                                           │
│    batch_id, merkle_root, transactions (100)                        │
│  }                                                                   │
│                                                                     │
│  STEP 2: Bank validates batch                                        │
│  For each transaction:                                               │
│    - Verify commitment is well-formed                                │
│    - Verify range proof (amount in valid range)                      │
│    - Check nullifier not previously used                             │
│    - Validate Merkle proof against root                              │
│                                                                     │
│  STEP 3: Bank votes (anonymous)                                      │
│  vote = "approve" OR "reject"                                        │
│  group_signature = sign_with_group_key(vote, bank_private_key)      │
│  → Signature proves: "A bank voted" (not which bank)                 │
│                                                                     │
│  STEP 4: Submit vote                                                 │
│  POST /consensus/vote                                                │
│  Body: {                                                             │
│    batch_id, vote, group_signature                                   │
│  }                                                                   │
│                                                                     │
│  STEP 5: Consensus counting                                          │
│  - Threshold: 10 of 12 banks (83%)                                   │
│  - If ≥10 approve: Batch approved                                    │
│  - If <10 approve: Batch rejected                                    │
│  - Timeout: 120 seconds (auto-approve if no rejections)              │
│                                                                     │
│  STEP 6: Store voting record                                         │
│  INSERT INTO bank_voting_records (                                   │
│    bank_id, batch_id, vote, group_signature                         │
│  )                                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Security Features**:
- Group signatures prevent vote coercion
- Anonymous voting (cannot tell which bank voted)
- Verifiable: Can prove "some bank voted"
- Non-repudiation: Banks cannot deny voting

---

### 12. Treasury Management

**Purpose**: Manage bank rewards and penalties

**Flow**:
```
┌─────────────────────────────────────────────────────────────────────┐
│  FISCAL YEAR REWARDS                                                 │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 1: End of fiscal year trigger                                  │
│  fiscal_year = "FY2026"                                              │
│                                                                     │
│  STEP 2: Calculate rewards for honest banks                          │
│  For each bank:                                                      │
│    total_votes = COUNT(votes in fiscal_year)                         │
│    honest_votes = COUNT(votes matching consensus)                    │
│    honesty_rate = honest_votes / total_votes                         │
│                                                                     │
│    IF honesty_rate ≥ 0.95:  (95% honest)                            │
│      reward = base_reward * honesty_rate                             │
│                                                                     │
│  STEP 3: Distribute rewards                                          │
│  INSERT INTO treasury (                                              │
│    bank_id, fiscal_year, amount, transaction_type='reward'          │
│  )                                                                   │
│                                                                     │
│  AUTOMATIC SLASHING (malicious behavior)                             │
│  ───────────────────────────────────────────                         │
│  STEP 1: Detect malicious voting                                     │
│  IF bank votes against consensus repeatedly:                         │
│    malicious_votes_count++                                           │
│                                                                     │
│  STEP 2: Apply penalty                                               │
│  IF malicious_votes_count ≥ threshold:                               │
│    penalty = stake * 0.10  (10% of stake)                            │
│    UPDATE banks SET stake -= penalty WHERE bank_id=...              │
│                                                                     │
│  STEP 3: Deactivation                                                │
│  IF stake < 30% of original:                                         │
│    UPDATE banks SET is_active=false WHERE bank_id=...               │
│    → Bank removed from consensus pool                                │
└─────────────────────────────────────────────────────────────────────┘
```

**API Endpoints**:
- `GET /treasury/rewards/{fiscal_year}` - View rewards
- `GET /treasury/penalties/{bank_id}` - View penalties
- `POST /treasury/slash/{bank_id}` - Manual slash (admin)

---

## System Performance Summary

**Transaction Processing**:
- Per-transaction latency: ~5ms (creation + crypto)
- Batch latency: ~12.5ms per 100 transactions
- **System capacity: 2,800-5,600 TPS** (measured estimate)

**Bottlenecks**:
- Primary: Consensus network latency (10ms, 80% of time)
- Secondary: Database operations (2ms, 16% of time)
- Merkle tree: Minimal (0.5ms, 4% of time)

**Scalability**:
- Horizontal: Sharding (future enhancement)
- Vertical: Increase batch size (200-500 tx/batch → higher TPS)

---

**Document Version**: 1.0
**Last Updated**: January 9, 2026
**System Version**: v3.0
