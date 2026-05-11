# Database Schema Documentation
**IDX Crypto Banking System**

**Date**: January 9, 2026
**Database**: PostgreSQL 14+
**ORM**: SQLAlchemy
**Total Tables**: 20

---

## Overview

The IDX Crypto Banking system uses PostgreSQL with connection pooling for high-performance transaction processing. All tables use SQLAlchemy ORM with proper relationships, indexes, and constraints.

**Connection Configuration** (`database/connection.py`):
- **Connection Pool**: 20 base connections + 10 overflow (max 30 concurrent)
- **Pool Pre-Ping**: Enabled (connection health checks)
- **Pool Recycle**: 3600 seconds (1 hour)
- **Statement Timeout**: Prevents long-running queries

---

## Table of Contents

### Core Tables
1. [users](#1-users) - User accounts and KYC data
2. [bank_accounts](#2-bank_accounts) - IDX-based bank accounts
3. [transactions](#3-transactions) - All transaction records
4. [sessions](#4-sessions) - User sessions (24h rotation)

### Blockchain Tables
5. [blocks](#5-blocks) - Blockchain blocks
6. [transaction_batches](#6-transaction_batches) - Batch processing (100 tx/batch)

### Banking Infrastructure
7. [banks](#7-banks) - 12-bank consortium
8. [bank_voting_records](#8-bank_voting_records) - Consensus voting history
9. [miners](#9-miners) - Mining nodes
10. [treasury](#10-treasury) - Bank rewards and penalties

### Recipients & Travel
11. [recipients](#11-recipients) - Saved recipients/contacts
12. [travel_accounts](#12-travel_accounts) - International banking
13. [foreign_banks](#13-foreign_banks) - Foreign bank entities
14. [forex_rates](#14-forex_rates) - Currency exchange rates

### Compliance & Security
15. [court_orders](#15-court_orders) - Court-ordered decryption
16. [judges](#16-judges) - Judicial authority
17. [access_control](#17-access_control) - Role-based access control
18. [audit_logs](#18-audit_logs) - Comprehensive audit trail
19. [security](#19-security) - Security configurations

### Migrations
20. [Migration Files](#20-migration-files) - Database schema versions

---

## Core Tables

### 1. users

**Purpose**: Store user accounts with KYC data

**Schema**:
```python
class User(Base):
    __tablename__ = "users"

    idx = Column(String, primary_key=True)  # IDX_<hash>
    pan = Column(String(10), unique=True, nullable=False)
    rbi_number = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Relationships
    bank_account = relationship("BankAccount", back_populates="user", uselist=False)
    sessions = relationship("Session", back_populates="user")
```

**Key Features**:
- IDX is deterministic: `IDX_{SHA256(PAN:RBI:PEPPER)}`
- PAN and RBI are unique (KYC compliance)
- One-to-one relationship with bank_account

---

### 2. bank_accounts

**Purpose**: IDX-based bank accounts with encrypted balances

**Schema**:
```python
class BankAccount(Base):
    __tablename__ = "bank_accounts"

    idx = Column(String, ForeignKey("users.idx"), primary_key=True)
    balance = Column(Numeric(18, 2), nullable=False, default=0.00)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="bank_account")
    sent_transactions = relationship("Transaction", foreign_keys="Transaction.sender_idx")
    received_transactions = relationship("Transaction", foreign_keys="Transaction.receiver_idx")
```

**Key Features**:
- Balance stored as `Numeric(18, 2)` for precision
- Foreign key to users.idx
- Tracks sent and received transactions

---

### 3. transactions

**Purpose**: All transaction records (public + private data)

**Schema**:
```python
class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(String, primary_key=True)
    sender_idx = Column(String, ForeignKey("bank_accounts.idx"), nullable=False)
    receiver_idx = Column(String, ForeignKey("bank_accounts.idx"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    session_id = Column(String, ForeignKey("sessions.session_id"), nullable=False)

    # Cryptographic fields
    commitment = Column(String)  # Pedersen commitment
    range_proof = Column(Text)  # Bulletproofs-style range proof
    nullifier = Column(String, unique=True)  # Double-spend prevention

    # Batch processing
    batch_id = Column(String, ForeignKey("transaction_batches.batch_id"))
    sequence_number = Column(BigInteger)  # Global sequence

    # Status
    status = Column(String, default="pending")  # pending, approved, rejected, completed

    # Foreign transaction fields
    currency = Column(String(3), default="INR")
    forex_rate = Column(Numeric(10, 6))
    original_amount = Column(Numeric(18, 2))
```

**Key Features**:
- Cryptographic commitments hide transaction details on public chain
- Nullifier prevents double-spending (unique per transaction)
- Batch processing (100 tx/batch)
- Supports foreign currency transactions

---

### 4. sessions

**Purpose**: User sessions with 24-hour rotation

**Schema**:
```python
class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)  # SESSION_<hash>
    idx = Column(String, ForeignKey("users.idx"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="sessions")
    transactions = relationship("Transaction", back_populates="session")
```

**Key Features**:
- Session ID: `SESSION_{SHA256(IDX:timestamp_ms:salt)}`
- 24-hour rotation (expires_at = created_at + 24h)
- Prevents session linkability attacks

---

## Blockchain Tables

### 5. blocks

**Purpose**: Blockchain blocks

**Schema**:
```python
class Block(Base):
    __tablename__ = "blocks"

    block_hash = Column(String, primary_key=True)
    block_number = Column(BigInteger, unique=True, nullable=False)
    previous_hash = Column(String, nullable=False)
    merkle_root = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    miner_idx = Column(String, ForeignKey("miners.idx"))

    # Relationships
    batches = relationship("TransactionBatch", back_populates="block")
```

---

### 6. transaction_batches

**Purpose**: Batch processing (100 transactions per batch, single consensus round)

**Schema**:
```python
class TransactionBatch(Base):
    __tablename__ = "transaction_batches"

    batch_id = Column(String, primary_key=True)
    block_hash = Column(String, ForeignKey("blocks.block_hash"))
    merkle_root = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Consensus
    approved_banks = Column(Integer, default=0)  # Count of approvals
    rejected_banks = Column(Integer, default=0)  # Count of rejections
    status = Column(String, default="pending")  # pending, approved, rejected

    # Relationships
    transactions = relationship("Transaction", back_populates="batch")
    block = relationship("Block", back_populates="batches")
```

**Key Features**:
- 100 transactions per batch
- Merkle tree root for efficient verification
- Consensus: 10/12 banks (83%)

---

## Banking Infrastructure

### 7. banks

**Purpose**: 12-bank consortium

**Schema**:
```python
class Bank(Base):
    __tablename__ = "banks"

    bank_id = Column(String, primary_key=True)
    bank_name = Column(String, nullable=False)
    bank_type = Column(String, nullable=False)  # public, private
    stake = Column(Numeric(18, 2), default=0.00)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True))

    # Relationships
    voting_records = relationship("BankVotingRecord", back_populates="bank")
```

**Configuration**:
- 8 public banks + 4 private banks = 12 total
- Consensus: 10/12 (83%)
- Deactivation: stake < 30% threshold

---

### 8. bank_voting_records

**Purpose**: Track consensus voting history

**Schema**:
```python
class BankVotingRecord(Base):
    __tablename__ = "bank_voting_records"

    vote_id = Column(String, primary_key=True)
    bank_id = Column(String, ForeignKey("banks.bank_id"), nullable=False)
    batch_id = Column(String, ForeignKey("transaction_batches.batch_id"))
    vote = Column(String, nullable=False)  # approve, reject
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Anonymous voting via group signatures
    group_signature = Column(Text)
```

---

### 9. miners

**Purpose**: Mining nodes for block creation

**Schema**:
```python
class Miner(Base):
    __tablename__ = "miners"

    idx = Column(String, primary_key=True)
    public_key = Column(String, nullable=False)
    blocks_mined = Column(Integer, default=0)
    total_rewards = Column(Numeric(18, 2), default=0.00)
    is_active = Column(Boolean, default=True)
```

---

### 10. treasury

**Purpose**: Bank rewards and penalties

**Schema**:
```python
class Treasury(Base):
    __tablename__ = "treasury"

    record_id = Column(String, primary_key=True)
    bank_id = Column(String, ForeignKey("banks.bank_id"), nullable=False)
    fiscal_year = Column(String, nullable=False)  # FY2024, FY2025
    amount = Column(Numeric(18, 2), nullable=False)
    transaction_type = Column(String, nullable=False)  # reward, penalty, stake
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    reason = Column(Text)
```

**Key Features**:
- Fiscal year rewards for honest banks
- Automatic slashing for malicious behavior
- Stake management

---

## Recipients & Travel

### 11. recipients

**Purpose**: Saved recipients/contacts

**Schema**:
```python
class Recipient(Base):
    __tablename__ = "recipients"

    recipient_id = Column(String, primary_key=True)
    user_idx = Column(String, ForeignKey("users.idx"), nullable=False)
    recipient_idx = Column(String, ForeignKey("bank_accounts.idx"), nullable=False)
    nickname = Column(String)
    created_at = Column(DateTime(timezone=True))
```

---

### 12. travel_accounts

**Purpose**: International banking accounts

**Schema**:
```python
class TravelAccount(Base):
    __tablename__ = "travel_accounts"

    travel_account_id = Column(String, primary_key=True)
    user_idx = Column(String, ForeignKey("users.idx"), nullable=False)
    foreign_bank_id = Column(String, ForeignKey("foreign_banks.foreign_bank_id"))
    balance_inr = Column(Numeric(18, 2), default=0.00)
    balance_foreign = Column(Numeric(18, 2), default=0.00)
    currency = Column(String(3), nullable=False)
    is_active = Column(Boolean, default=True)
```

---

### 13. foreign_banks

**Purpose**: Foreign bank entities

**Schema**:
```python
class ForeignBank(Base):
    __tablename__ = "foreign_banks"

    foreign_bank_id = Column(String, primary_key=True)
    bank_name = Column(String, nullable=False)
    swift_code = Column(String(11), unique=True)
    country = Column(String(2), nullable=False)  # ISO 3166-1
    currency = Column(String(3), nullable=False)  # ISO 4217
    is_active = Column(Boolean, default=True)
```

---

### 14. forex_rates

**Purpose**: Currency exchange rates

**Schema**:
```python
class ForexRate(Base):
    __tablename__ = "forex_rates"

    rate_id = Column(String, primary_key=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(10, 6), nullable=False)
    effective_date = Column(DateTime(timezone=True))
```

---

## Compliance & Security

### 15. court_orders

**Purpose**: Court-ordered decryption

**Schema**:
```python
class CourtOrder(Base):
    __tablename__ = "court_orders"

    order_id = Column(String, primary_key=True)
    judge_id = Column(String, ForeignKey("judges.judge_id"), nullable=False)
    target_idx = Column(String, ForeignKey("users.idx"), nullable=False)
    reason = Column(Text, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="pending")  # pending, approved, executed, expired

    # Threshold decryption
    company_approval = Column(Boolean, default=False)
    court_approval = Column(Boolean, default=False)
    regulatory_approvals = Column(Integer, default=0)  # 1 of 4 required
```

**Key Features**:
- Requires: Company + Court + 1-of-4 regulatory (NOW: Nested threshold, cryptographically enforced)
- 24-hour access window
- Full audit trail

---

### 16. judges

**Purpose**: Judicial authority

**Schema**:
```python
class Judge(Base):
    __tablename__ = "judges"

    judge_id = Column(String, primary_key=True)
    full_name = Column(String, nullable=False)
    court_name = Column(String, nullable=False)
    jurisdiction = Column(String, nullable=False)
    public_key = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
```

---

### 17. access_control

**Purpose**: Role-based access control

**Schema**:
```python
class AccessControl(Base):
    __tablename__ = "access_control"

    access_id = Column(String, primary_key=True)
    user_idx = Column(String, ForeignKey("users.idx"), nullable=False)
    role = Column(String, nullable=False)  # user, admin, auditor, regulator
    permissions = Column(JSONB)  # JSON list of permissions
    granted_at = Column(DateTime(timezone=True))
    granted_by = Column(String)
```

---

### 18. audit_logs

**Purpose**: Comprehensive audit trail

**Schema**:
```python
class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(String, primary_key=True)
    user_idx = Column(String, ForeignKey("users.idx"))
    action = Column(String, nullable=False)  # login, transaction, court_order, etc.
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    ip_address = Column(String)
    event_data = Column(JSONB)  # JSON details
```

---

### 19. security

**Purpose**: Security configurations (rate limiting, MFA)

**Schema**:
```python
class Security(Base):
    __tablename__ = "security"

    security_id = Column(String, primary_key=True)
    user_idx = Column(String, ForeignKey("users.idx"), nullable=False)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
```

---

## 20. Migration Files

**Location**: `scripts/migrations/`

**Migration History**:
1. `001_initial_schema.sql` - Base tables
2. `002_rate_limiting.sql` - Security features
3. `003_audit_logs.sql` - Audit trail
4. `004_user_mining.sql` - Mining infrastructure
5. `005_foreign_consensus.sql` - International banking
6. `006_access_control_and_recipients.sql` - RBAC + recipients
7. `007_v3_advanced_crypto.sql` - Advanced crypto features
8. `008_security_features_migration.sql` - Security governance
9. `009_anomaly_detection.sql` - Anomaly detection (Phases 1-5)

---

## Database Performance

**Connection Pooling**:
- Base pool: 20 connections
- Max overflow: 10 connections
- Total capacity: 30 concurrent connections
- Pre-ping: Enabled (health checks)
- Recycle time: 3600 seconds

**Indexes** (automatically created by SQLAlchemy):
- Primary keys: B-tree indexes
- Foreign keys: B-tree indexes
- Unique constraints: Unique indexes
- `transaction.nullifier`: Unique index (double-spend prevention)
- `transaction.sequence_number`: B-tree index (ordering)

**Query Performance**:
- Bulk inserts: Used for batch processing (100 tx)
- Connection pooling: Reduces connection overhead
- Statement timeout: Prevents long-running queries

---

## Data Integrity

**Foreign Key Constraints**: Enforced at database level
**Unique Constraints**:
- users.pan (PAN numbers)
- users.rbi_number (RBI numbers)
- users.email (email addresses)
- transactions.nullifier (double-spend prevention)

**Default Values**: Used for timestamps, boolean flags, numeric fields

**Relationships**: SQLAlchemy relationships maintain consistency

---

**Document Version**: 1.0
**Last Updated**: January 9, 2026
**Database Version**: PostgreSQL 14+
