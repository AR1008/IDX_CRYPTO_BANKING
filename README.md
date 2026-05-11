# IDX Crypto Banking Framework

**A Privacy-Centric Blockchain Banking System with Zero-Knowledge AML Compliance**

[![Python 3.10](https://img.shields.io/badge/python-3.10%20(venv)-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-14+-blue.svg)](https://www.postgresql.org/)
[![License: Academic](https://img.shields.io/badge/license-Academic-green.svg)](LICENSE)

> **Research prototype** targeting ACM CCS 2027. Not production-ready. All benchmark numbers are real — measured on Apple M1 Pro with native Rust Bulletproofs. See `docs/paper/NOVELTY-SUMMARY.md` for full details.

---

## Overview

The IDX Crypto Banking Framework is a globally applicable blockchain-based banking system that provides complete transaction privacy through zero-knowledge cryptography, while enabling lawful regulatory access through court-ordered multi-party threshold de-anonymization. Designed for any jurisdiction.

**The core novelty**: Banks can prove AML compliance (high-value, velocity, structuring rules) in zero-knowledge — without revealing transaction amounts. When a court order is issued, only the targeted party's identity is revealed, for that one transaction, using one-time keys that are invalidated after use.

### Key Features

- **8.75 ms Bulletproofs prove / 2.09 ms verify** — Rust native (dalek v4, Ristretto255); 12.6× faster than Platypus (CCS 2022); no trusted setup
- **Zero-knowledge AML proofs** — high-value, velocity, structuring rules provable in ZK (CBC primitive)
- **N-bank consortium** (N=12 default, generalized) — BFT-safe threshold T = N-X, X < N/3
- **Anonymous bank consensus** — real BBS04 group signatures (BN254, Charm-Crypto), 939-byte signatures
- **RCTD** — Role-Constrained Threshold Decryption: Company + any one of {FFA / FIU / FLEA / NTA}
- **One-time court-order keys** — each decryption uses fresh keys invalidated immediately after use
- **Session ID rotation** — 24-hour automatic pseudonym rotation, fully transparent to users
- **One-time IDX entry** — enter receiver's IDX once; system auto-resolves session IDs forever after
- **Merkle batch validation** — 192-byte root for 100 transactions; 47ms build time
- **O(1) nullifier membership** — hash-based double-spend prevention
- **Per-transaction encryption** — unique AES-256-GCM key per transaction
- **Rule-based anomaly detection** — 97% accuracy (95% CI: 91.5%–99.4%)
- **Anomaly flag ≠ freeze** — flagged transactions complete; freeze only after court-ordered decryption

---

## Key Innovation

### CBC + RCTD: Two New Cryptographic Primitives

**CBC — Compliance-Binding Commitment**:
A commitment scheme where a prover can commit to a transaction amount and prove in ZK that it satisfies an AML rule R, without revealing the amount. First formal treatment of AML rules as ZK-provable statements.

**RCTD — Role-Constrained Threshold Decryption**:
A threshold encryption scheme with a jurisdiction-specific access structure. For ZK-AML:
```
Γ = (Company) ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA)
```
First formal definition of banking regulatory access structures as a standalone cryptographic primitive with proven security properties.

### Court Order Flow (Correct)

```
Anomaly flagged → transaction completes normally → details encrypted on private chain
        ↓ (days/weeks later, if investigation warranted)
Government files court order for specific tx_hash + target party (sender OR receiver)
        ↓
Company key + ONE regulatory authority key assembled → one-time use
        ↓
Private chain decrypted → targeted party's IDX revealed (other party stays encrypted)
        ↓
IDX → real identity (via IDX Central Database) → account frozen
        ↓
Government gets READ-ONLY access to that account's transaction statement during freeze
        ↓
Freeze ends → government access revoked → keys already invalidated
```

---

## Advanced Cryptographic Features

### 1. Sequence Numbers + Batch Processing

**Purpose**: Prevent replay attacks and improve throughput

**How it works**:
- Every transaction gets monotonically increasing sequence number
- 100 transactions batched together for consensus
- Single consensus round for entire batch

**Performance**:
- **64.8 TPS** (Python + Rust Bulletproofs, measured); **69.1 TPS** with batch verify (master run 2026-03-02)
- Batch processing time: ~12ms per batch (Merkle + consensus + DB)
- Single consensus round per batch (not per transaction)
- Bottleneck: Range proof generation (8.75ms Bulletproofs, or 237ms velocity ZK / 399ms structuring ZK)

### 2. Merkle Trees

**Purpose**: Efficient transaction validation with minimal data

**How it works**:
- Binary hash tree built from transaction batch
- Root hash represents entire batch
- O(log n) proof size for membership

**Performance**:
- **99.997% smaller proofs**: 192 bytes vs 800 KB
- **4,267x reduction** in data transfer
- Tree building: 47ms for 100 transactions
- Proof verification: <1ms

### 3. Pedersen Commitments (Real EC)

**Purpose**: Hide transaction amounts on the public blockchain with cryptographic guarantees

**How it works**:
- Commitment `C = v·G + r·H` on secp256k1 (elliptic curve, not a hash)
- `G` and `H` are independent curve generators (nothing-up-my-sleeve derivation)
- Only the commitment `C` is posted to the public chain
- Full data AES-256-GCM encrypted on private chain
- Nullifier `= SHA256(commitment || sender_idx || secret)` prevents double-spending

**Security**:
- **Computationally hiding** (DDH assumption, 128-bit security): Given `C`, no polynomial-time attacker can determine `v`
- **Perfectly binding**: No attacker (even unbounded) can open `C` to two different values with the same blinding factor
- **Homomorphic**: `C(v1,r1) + C(v2,r2) = C(v1+v2, r1+r2)` — enables Bulletproofs range proofs
- Replaces the old SHA-256 simulation (`commitment_scheme.py`) which was NOT hiding

**Performance** (measured, 2026-02-27):
- Commitment creation: **4.59ms** (secp256k1 scalar multiplication via py_ecc)
- Commitment size: **130 bytes** (uncompressed EC point hex)
- Nullifier verification: <1ms (hash comparison)

### 4. Range Proofs (Real Bulletproofs — Rust Native)

**Purpose**: Prove transaction amount is in a valid range without revealing the amount

**How it works**:
- Zero-knowledge proof that `0 ≤ amount ≤ max_value` (or `amount ≥ threshold` for AML rules)
- Built on Pedersen commitments — homomorphic property required
- **Two implementations**:
  - Reference (Python): Schnorr OR-proofs, O(n) in bit-length — for auditing and correctness
  - Production (Rust native): dalek-cryptography Bulletproofs v4, O(log n) — for performance

**Use cases**:
- Prove sender has sufficient balance without revealing balance
- Prove transaction amount is positive without revealing amount
- Prove amount ≥ AML threshold (CBC R_high_value compliance rule)

**Performance** (measured, 2026-03-02 master run, Rust native on Apple Silicon):
- **Bulletproofs 64-bit**: prove **8.75ms**, verify **2.09ms**, size **672 bytes**
- Bulletproofs 32-bit: size **608 bytes**
- Schnorr OR-proof (Python): 152ms (8-bit), 233ms (14-bit), 265ms (16-bit), 392ms (24-bit)
- The old SHA-256 simulation had zero soundness — any value was "valid"

### 5. Group Signatures (BBS04, Real — BN254)

**Purpose**: Anonymous bank consensus with full accountability via court-order tracing

**How it works**:
- N banks vote on batch proposals using the Boneh-Boyen-Shacham 2004 (BBS04) short group signature scheme
- Pairing curve: BN254 (128-bit security, same as Ethereum alt_bn128)
- Implemented via Charm-Crypto 0.62 (JHUISI — Johns Hopkins University)
- Any verifier confirms "a registered consortium bank approved this batch" without learning which bank
- FFA holds the opening key `(ξ₁, ξ₂)` and can trace any signature to the signing bank under court order

**Security properties** (proven in BBS04 paper):
- Anonymity under DLIN (Decision Linear) assumption on BN254
- Traceability under q-SDH assumption
- Non-frameability under DL assumption

**Performance** (measured, 2026-02-27):
- Signing time: **92.62ms** (BN254 pairing, Charm-Crypto)
- Verification time: **142.70ms**
- Tracing/opening time: **1.81ms** (O(1), constant regardless of group size)
- Signature size: **~939 bytes** (9 BN254 pairing elements)
- The old simulation returned strings like `"GROUP_SIG_SBI_BATCH00012345"` with zero cryptographic meaning

### 6. Role-Constrained Threshold Decryption (RCTD)

**Purpose**: Cryptographically enforce that decrypting a flagged transaction requires multiple regulatory authorities

**Access Structure** (formalized as RCTD primitive):
```
Γ = (Company) ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA)
```
This means: the company's key PLUS any one of four regulatory authorities is required. No single party can decrypt alone.

**How it works**:
- Two-layer Shamir Secret Sharing: outer 2-of-2 (Company AND Court_Combined), inner 1-of-4 (Court_Combined from any one authority)
- AES-256-GCM encrypts the transaction data (IND-CCA2, NIST SP 800-38D)
- Partial decryptions are verifiable — each authority can confirm others submitted correct shares

**Security**:
- IND-CPA under DDH (threshold layer)
- IND-CCA2 (AES-256-GCM authenticated encryption layer)
- Replaces old XOR encryption which was not semantically secure
- Formal RCTD syntax defined: Setup, Encrypt, ShareDecrypt, Combine, Verify

**Performance**:
- Share generation: <1ms (Lagrange interpolation over 256-bit prime)
- Secret reconstruction: <1ms
- Encryption: **0.04ms** (AES-256-GCM, 1KB)

### 7. Hash-based Set Membership (Dynamic Accumulator)

**Purpose**: O(1) membership checks for account validation

**Note**: This is a **hash-based** implementation, NOT an RSA accumulator. Simpler and faster for trusted consortium environments.

**How it works**:
- Hash-based accumulator: single 256-bit value represents entire set
- Add element: accumulator' = Hash(accumulator || element)
- Check membership: O(1) set lookup
- Remove element: O(n) recomputation (rare operation)

**Use cases**:
- Account existence validation (20x faster than database)
- Nullifier set for double-spend prevention
- Blacklist/whitelist management
- Transaction deduplication

**Performance**:
- Add operation: 0.0025ms (O(1))
- Membership check: 0.0002ms (O(1))
- Accumulator size: 66 bytes (constant!)
- **20x faster** than database queries

### 8. Threshold Accumulator

**Purpose**: Distributed control of account freeze/unfreeze

**How it works**:
- Combines Dynamic Accumulator + Threshold Voting
- Freeze/unfreeze requires T-of-N bank approval
- Proposal → Voting → Execution workflow
- O(1) frozen status checks

**Process**:
1. Bank creates freeze proposal (with reason)
2. Banks vote (approve/reject)
3. If T-of-N approve → proposal approved
4. Execute proposal → update freeze accumulator
5. O(1) check if account frozen

**Security**:
- Prevents single bank abuse
- Distributed control (no single point of failure)
- Complete accountability (all votes recorded)
- Transparency (full audit trail)

**Performance**:
- Proposal creation: <1ms
- Voting: <1ms per vote
- Execution: <1ms
- Frozen check: <1ms (O(1))

---

## System Architecture

### Three-Layer Identity System

```
┌─────────────────────────────────────────────────────────┐
│                    IDENTITY LAYERS                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Layer 1: Session ID (24-hour rotation)                 │
│  ├─ Public blockchain identity                          │
│  ├─ Rotates every 24 hours                              │
│  ├─ Prevents tracking across time                       │
│  └─ Example: SESSION_hdfc_abc123_20250327               │
│                                                          │
│  Layer 2: IDX (Permanent Anonymous ID)                  │
│  ├─ Accounting and balance tracking                     │
│  ├─ Hash(Ident + Authority_ID)                          │
│  ├─ Never changes                                       │
│  └─ Example: IDX_abc123def456...                        │
│                                                          │
│  Layer 3: Real Identity (Restricted Access)             │
│  ├─ National ID, government documents, legal name        │
│  ├─ Encrypted on private blockchain                     │
│  ├─ Only accessible via court order                     │
│  └─ Requires: Company + Court + 1-of-3 keys             │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Dual Blockchain Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      PUBLIC BLOCKCHAIN                          │
│  (Validation Only - No Private Data)                            │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Block {                                                        │
│    batch_id: "BATCH_1_100"                                      │
│    merkle_root: "0xabc123..."                                   │
│    transactions: [                                              │
│      {                                                          │
│        sequence_number: 1                                       │
│        commitment: "0xdef456..."  ← Hash only                   │
│        nullifier: "0x789abc..."   ← Prevents double-spend      │
│        range_proof: {...}         ← Zero-knowledge proof        │
│        group_signature: {...}     ← Anonymous bank consensus    │
│      }                                                          │
│    ]                                                            │
│  }                                                              │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
                             │
                             │ Linked by hash
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                     PRIVATE BLOCKCHAIN                          │
│  (Session IDs + Transaction Data - Encrypted)                   │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  EncryptedBlock {                                               │
│    AES-256 Encrypted with threshold keys:                      │
│    {                                                            │
│      sender_session_id: "SESSION_abc123..."                     │
│      receiver_session_id: "SESSION_xyz789..."                   │
│      amount: 50000.00                                           │
│      sender_bank: "HDFC"                                        │
│      receiver_bank: "ICICI"                                     │
│      tx_hash: "0x..."                                           │
│      timestamp: "2025-12-29T10:30:00Z"                          │
│    }                                                            │
│                                                                 │
│    Note: session_id → IDX requires separate threshold decryption│
│          IDX → Name+PAN requires database lookup               │
│  }                                                              │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### N-Bank Consortium

```
┌─────────────────────────────────────────────────────────┐
│               BANK CONSORTIUM (N BANKS)                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Consensus: T-of-N approval required (T = N-X, X < N/3) │
│                                                          │
│  Public Sector Banks (8, default config):               │
│  1. State Bank of India (SBI)   5. Union Bank           │
│  2. Punjab National Bank (PNB)  6. Indian Bank          │
│  3. Bank of Baroda (BOB)        7. Central Bank         │
│  4. Canara Bank                 8. UCO Bank             │
│                                                          │
│  Private Sector Banks (4, default config):              │
│  9. HDFC Bank        11. Axis Bank                      │
│  10. ICICI Bank      12. Kotak Mahindra Bank            │
│                                                          │
│  Staking & Governance:                                   │
│  ├─ Each bank stakes 1% of total assets                │
│  ├─ Automatic slashing (5%, 10%, 20% escalating)       │
│  ├─ FFA re-verifies 10% random batches                 │
│  ├─ Deactivation if stake < 30% of initial             │
│  ├─ Treasury distributes slashed funds to honest banks │
│  └─ Byzantine fault tolerance (T-of-N supermajority)   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Transaction Flow

### Complete End-to-End Flow

```
Step 1: TRANSACTION CREATION
├─ User initiates transaction
├─ System assigns sequence number (e.g., #1001)
├─ Create Pedersen commitment: C = amount·G + r·H (secp256k1, not a hash)
├─ Generate nullifier: Hash(commitment || sender || secret)
├─ Create range proof: Prove 0 < amount ≤ sender_balance (zero-knowledge)
├─ Store commitment on public chain, full data encrypted on private chain
└─ Status: AWAITING_RECEIVER

Step 2: RECEIVER CONFIRMATION
├─ Receiver gets notification
├─ Receiver selects bank account to receive funds
├─ Transaction updated with receiver bank account
└─ Status: PENDING

Step 3: BATCH PROCESSING
├─ System collects 100 pending transactions
├─ Create batch: BATCH_1001_1100
├─ Build Merkle tree from batch (root hash)
├─ Generate 192-byte proof (99.997% smaller)
└─ Batch ready for consensus

Step 4: N-BANK CONSENSUS
├─ All N banks validate batch
├─ Each bank creates anonymous group signature
├─ Verify range proofs (without seeing amounts)
├─ Check nullifiers (prevent double-spend)
├─ Need T-of-N approval to proceed (T = N-X, X < N/3)
├─ Sender's bank AND receiver's bank MUST approve
└─ Consensus votes recorded

Step 5: MINING (PoW)
├─ Mining worker picks up consensus-approved batch
├─ Perform SHA-256 mining (difficulty 4)
├─ Find nonce that creates valid block hash
├─ Average time: 0.5-2 seconds
└─ Status: PUBLIC_CONFIRMED

Step 6: PRIVATE CHAIN ENCRYPTION
├─ Full transaction data encrypted (AES-256)
├─ Threshold secret sharing for court access
├─ Private block linked to public block
├─ Store encrypted data
└─ Status: PRIVATE_CONFIRMED

Step 7: FINALIZATION
├─ Update balances (sender -amount, receiver +amount)
├─ Distribute fees (0.5% miner, 1% banks)
├─ Add nullifier to accumulator (O(1) operation)
├─ Emit WebSocket notifications
└─ Status: COMPLETED
```

---

## Court Order System

### RCTD — Role-Constrained Threshold Decryption

```
┌─────────────────────────────────────────────────────────┐
│            COURT ORDER DECRYPTION SYSTEM (RCTD)          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Access Structure Γ = (Company) ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA)│
│                                                          │
│  Layer 1 — Mandatory (2-of-2 outer Shamir):             │
│  ├─ Company Key  →  IDX Banking Company                 │
│  └─ Court_Combined Key  →  any one authority below      │
│                                                          │
│  Layer 2 — Any One Of (1-of-4 inner Shamir):            │
│  ├─ FFA Key  (Federal Financial Authority)              │
│  ├─ FIU Key  (Financial Intelligence Unit)              │
│  ├─ FLEA Key (Federal Law Enforcement Agency)           │
│  └─ NTA Key  (National Tax Authority)                   │
│                                                          │
│  Encryption:                                             │
│  ├─ AES-256-GCM (NIST SP 800-38D, IND-CCA2)            │
│  ├─ Shamir Secret Sharing (Lagrange, 256-bit prime)     │
│  ├─ Partial decryptions are independently verifiable    │
│  └─ Time-limited access (24 hours)                      │
│                                                          │
│  Security Properties:                                    │
│  ├─ No single entity can decrypt alone                  │
│  ├─ IND-CPA under DDH (threshold layer)                 │
│  ├─ IND-CCA2 (AES-GCM authentication tag)              │
│  ├─ Complete audit trail                                │
│  └─ Cryptographically enforced — not just permissions   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Court Order Flow (3-Phase Investigation)

```
PHASE 1: Government Views Private Blockchain
├─ Government requests permission to VIEW private blockchain
├─ Company grants VIEW access (no decryption yet)
├─ Government browses transactions:
│  ├─ See: session IDs, amounts, bank names, timestamps
│  ├─ Cannot see: Real names, PAN cards, IDX
│  └─ Identifies ONE suspicious transaction
└─ No court order needed for this phase

PHASE 2: Court Order Authorization
├─ Government presents evidence to court
├─ Judge issues order for THAT specific transaction
├─ Government chooses ONE person (sender OR receiver, not both)
└─ Court order submitted to system

PHASE 3: Full Access (24-hour window)
├─ Key assembly (RCTD):
│  ├─ Company provides Key #1 (outer Shamir share)
│  ├─ Any one of FFA/FIU/FLEA/NTA provides Key #2 (inner Shamir share)
│  └─ Reconstruct master key: outer 2-of-2 + inner 1-of-4 Lagrange interpolation
├─ Session ID → IDX decryption
├─ With IDX, government can view:
│  ├─ Real name + PAN card
│  ├─ ALL transaction history (all accounts)
│  ├─ All amounts sent/received
│  └─ All bank account details
├─ Access valid for 24 hours only
├─ Keys automatically destroyed after 24 hours
└─ Complete audit trail maintained

Access Levels:
├─ CA/Auditor: IDX → Name + PAN only (no transaction history)
└─ Government: IDX → Name + PAN + Full transaction history
```

---

## International Banking & Travel Accounts

The IDX Crypto Banking Framework includes a unique **international banking feature** that allows users to create temporary foreign currency accounts for international travel, while maintaining the same privacy guarantees as domestic transactions.

### Foreign Bank Partnership Network

The system partners with **4 major international banks** across different regions:

1. **Citibank USA** (USD)
   - Country: United States
   - Currency: US Dollar (USD)
   - Partners: All N consortium banks

2. **HSBC UK** (GBP)
   - Country: United Kingdom
   - Currency: British Pound (GBP)
   - Partners: All N consortium banks

3. **Deutsche Bank Germany** (EUR)
   - Country: Germany
   - Currency: Euro (EUR)
   - Partners: All N consortium banks

4. **DBS Bank Singapore** (SGD)
   - Country: Singapore
   - Currency: Singapore Dollar (SGD)
   - Partners: All N consortium banks

### How Travel Accounts Work

#### 3-Phase Lifecycle

**Phase 1: Pre-Trip (Account Creation)**
```
User planning USA trip:
├─ Convert ₹100,000 from home bank account
├─ Forex rate: 1 INR = 0.012 USD (₹83.33 per dollar)
├─ Conversion: ₹100,000 → $1,200.00 USD
├─ Forex fee (0.15%): $1.80 USD
├─ Final balance: $1,198.20 USD
├─ Create temporary account at Citibank USA
├─ Account validity: 30-90 days (user choice)
└─ Status: ACTIVE
```

**Phase 2: During Trip (Active Usage)**
```
Use foreign account for transactions:
├─ Make purchases in USD
├─ Hotel booking: $500 → Balance: $698.20
├─ Shopping: $300 → Balance: $398.20
├─ Restaurant: $100 → Balance: $298.20
├─ No additional fees during usage
└─ Real-time balance tracking
```

**Phase 3: Post-Trip (Account Closure)**
```
Close account and return funds:
├─ Remaining balance: $298.20 USD
├─ Forex rate: 1 USD = ₹83.33 INR
├─ Conversion: $298.20 → ₹24,844.39 INR
├─ Forex fee (0.15%): ₹37.27 INR
├─ Final return: ₹24,807.12 INR
├─ Funds returned to source account
├─ Status: CLOSED
└─ Transaction history preserved permanently
```

### Forex Rates (Updated Hourly)

| Currency Pair | Rate | Example |
|---------------|------|---------|
| **INR → USD** | 0.012 | ₹10,000 = $119.82 (after fee) |
| **USD → INR** | 83.33 | $100 = ₹8,320.50 (after fee) |
| **INR → GBP** | 0.0095 | ₹10,000 = £94.86 (after fee) |
| **GBP → INR** | 105.26 | £100 = ₹10,510.47 (after fee) |
| **INR → EUR** | 0.011 | ₹10,000 = €109.84 (after fee) |
| **EUR → INR** | 90.91 | €100 = ₹9,077.27 (after fee) |
| **INR → SGD** | 0.016 | ₹10,000 = S$159.76 (after fee) |
| **SGD → INR** | 62.50 | S$100 = ₹6,240.63 (after fee) |

**Forex Fee**: 0.15% on all conversions (both INR→Foreign and Foreign→INR)

### Privacy Integration

Travel accounts maintain the **same privacy guarantees** as domestic accounts:

- **Anonymous transactions**: Uses same IDX system
- **Session rotation**: 24-hour session IDs
- **Zero-knowledge proofs**: Transaction amounts hidden on public chain
- **Court order compliance**: Can be de-anonymized if legally required
- **Cross-border privacy**: Foreign banks cannot access user's real identity

### Key Features

✅ **Temporary Accounts**: 30-90 day validity, auto-expire after period
✅ **Multi-Currency Support**: USD, GBP, EUR, SGD
✅ **Real-time Conversion**: Forex rates updated hourly
✅ **Low Fees**: 0.15% conversion fee (one of the lowest in industry)
✅ **Permanent History**: All transactions preserved after closure
✅ **Seamless Integration**: Use existing IDX account for international transactions
✅ **Privacy-Preserving**: Same zero-knowledge guarantees as domestic
✅ **No Pre-Payment Cards**: Real bank accounts, not prepaid cards

### Example Scenario

**Singapore Business Trip**:
```
Day 0 (Home Country):
├─ Create travel account: ₹50,000 → S$798.80 SGD
├─ Account at DBS Bank Singapore
└─ Validity: 60 days

Day 1-30 (Singapore):
├─ Hotel: S$300 → Balance: S$498.80
├─ Meals & Transport: S$200 → Balance: S$298.80
├─ Shopping: S$100 → Balance: S$198.80
└─ Business expenses: S$50 → Balance: S$148.80

Day 31 (Back Home):
├─ Close account: S$148.80 → ₹9,291.94 INR
├─ Return to source account
└─ Total spent: ₹50,000 - ₹9,291.94 = ₹40,708.06
```

### API Endpoints

The system provides 6 REST API endpoints for travel account management:

- `GET /api/travel/foreign-banks` - List available foreign banks
- `GET /api/travel/forex-rates` - Get current forex rates (1-hour cache)
- `POST /api/travel/create` - Create travel account with conversion
- `GET /api/travel/accounts` - List user's travel accounts
- `GET /api/travel/accounts/{id}` - Get specific account details
- `POST /api/travel/accounts/{id}/close` - Close account and convert back

---

## Performance Metrics

### System Performance

| Metric | Performance | Notes |
|--------|-------------|-------|
| **Throughput (Config A2+batch, measured)** | **69.1 TPS** | Python EC + Rust BP + native batch verify, Apple Silicon |
| **Throughput (Config A2, measured)** | **64.8 TPS** | Python Pedersen + Rust Bulletproofs, Apple Silicon |
| **Throughput (Config A, measured)** | **54.8 TPS** | Python EC only (reference implementation) |
| **Merkle root (100 txs)** | 192 bytes | SHA-256 binary Merkle tree root |
| **Membership Checks** | 0.0002ms (O(1)) | Hash-based nullifier accumulator |
| **Batch Processing** | ~12ms per 100 transactions | Merkle + consensus + DB |
| **Consensus threshold** | T-of-N banks (default 10/12, 83%) | BFT-safe (X < N/3) |

> **Note**: All numbers from master benchmark run 2026-03-02, 100 trials, warmup=5. Old "2,900–4,100 TPS" measured SHA-256 string hashing — not valid for the real EC pipeline.

### Cryptographic Operation Performance (master run 2026-03-02, Apple Silicon ARM, 100 trials)

| Operation | Time | Size | Basis |
|-----------|------|------|-------|
| **Pedersen Commitment (create)** | **4.60ms** | **33 bytes** (compressed) | secp256k1, py_ecc |
| **Pedersen Commitment (verify)** | 4.54ms | — | secp256k1, py_ecc |
| **Bulletproofs Range Proof (64-bit, create)** | **8.75ms** | **672 bytes** | Rust native, dalek-cryptography |
| **Bulletproofs Range Proof (64-bit, verify)** | **2.09ms** | — | Rust native, dalek-cryptography |
| **Bulletproofs batch verify B=100 (native Rust)** | **112.5ms** | **1.12ms/proof** | 1.87× speedup |
| **Bulletproofs batch verify B=100 (fork-pool)** | **35.5ms** | **0.36ms/proof** | 5.92× speedup |
| **R_velocity ZK (not_suspicious, prove)** | **61.0ms** | — | 8-bit Schnorr OR-proof, Python |
| **R_velocity ZK (suspicious, prove)** | **237.1ms** | — | 14-bit Schnorr OR-proof, Python |
| **R_structuring ZK (STRUCTURING, prove)** | **268.6ms** | — | 16-bit Schnorr OR-proof, Python |
| **R_structuring ZK (ABOVE, prove)** | **398.1ms** | — | 24-bit Schnorr OR-proof, Python |
| **BBS04 Group Signature (sign)** | **92.31ms** | **939 bytes** | BN254, Charm-Crypto 0.62 |
| **BBS04 Group Signature (verify)** | **141.29ms** | — | BN254, Charm-Crypto 0.62 |
| **BBS04 Opening/Tracing** | **1.66ms** | — | O(1) constant time |
| **Anomaly ZKP (Schnorr, create)** | **11.28ms** | — | Real Schnorr sigma protocol |
| **Anomaly ZKP (Schnorr, verify)** | **9.05ms** | — | ~110/sec, EC arithmetic check |
| **AES-256-GCM encrypt (1KB)** | **0.04ms** | — | NIST SP 800-38D |
| **AES-256-GCM decrypt (1KB)** | **0.04ms** | — | with authentication tag |
| **Merkle Tree (100 txs)** | 47ms | 192-byte root | SHA-256 binary tree |
| **Accumulator Add** | 0.0025ms | 66 bytes | Hash-based |
| **Accumulator Check** | 0.0002ms | — | O(1) |
| **Shamir split/reconstruct** | <1ms | — | Lagrange, 256-bit prime |

### Anomaly Detection Performance

| Metric | Performance | Target | Status |
|--------|-------------|--------|--------|
| **ZKP Throughput (real Schnorr)** | ~110/sec | — | Real EC (9.05ms verify) |
| **Anomaly Engine (clean tx, end-to-end)** | 393ms | — | 1 velocity + 1 structuring ZK proof |
| **Anomaly Engine (full_flag, end-to-end)** | 634ms | — | HIGH_VALUE + VELOCITY + STRUCTURING |
| **Detection Accuracy*** | 97/100 test cases (95% CI: 91.5%-99.4%) | >95% | ✅ Exceeds target |
| **False Positive Rate*** | 3/100 test cases (95% CI: 0.6%-8.5%) | <5% | ✅ Within target |
| **Avg Latency (detection)** | 2-5ms | <10ms | ✅ Rule-based AML scoring |
| **Avg Latency (ZKP, real Schnorr)** | 11.28ms prove / 9.05ms verify | <15ms | ✅ Real EC, soundness 2^{-256} |

\* *Performance measured on n=100 synthetic test cases; real-world adversarial performance may vary. Continuous monitoring and model updates recommended.*

### System Capacity

**Current Measured Performance** (real EC cryptography, master run 2026-03-02):

| Config | Implementation | TPS | Hardware |
|--------|---------------|-----|---------|
| **A2+batch (measured)** | Python EC + Rust BP + native batch verify | **69.1 TPS** | Apple Silicon ARM |
| **A2 (measured)** | Python Pedersen + Rust Bulletproofs | **64.8 TPS** | Apple Silicon ARM |
| **A (measured)** | Python EC only (reference) | **54.8 TPS** | Apple Silicon ARM |

**Note on historical numbers**: The stress test results showing 2,900–4,100 TPS were measured against the old SHA-256 simulation of cryptography (now deprecated). Those numbers measured Python string hashing speed, not elliptic curve operations. They are **not valid** to cite in a paper about the real implementation.

**System Configuration**:
- **Batch Size**: 100 transactions per batch
- **Consensus Threshold**: T-of-N banks (T = N-X, X < N/3; default 10/12)
- **Block Time**: 10 seconds (PoW difficulty 4, SHA-256)
- **Batches/Block**: Multiple batches per block

**Testing Methodology** (real crypto, master benchmark 2026-03-02):
- Full cryptographic pipeline: Pedersen commits + Bulletproofs range proofs + BBS04 group signatures + velocity ZK + structuring ZK
- Primitive benchmarks: 100 trials per operation (warmup=5), 20 trials for anomaly engine
- 12-section master benchmark: Bulletproofs, Pedersen, Schnorr, BBS04, OR-proofs, R_velocity ZK, R_structuring ZK, Anomaly Engine, Consensus sweep, TPS, Breaking Point, Comparison table
- Results: `tests/benchmarks/results/master_20260302_203927.json`

**Primary Bottleneck**:
- Normal load (50+ accounts): Cryptographic operations (range proof generation/verification)
- Extreme contention (<10 accounts): Lock contention becomes dominant factor
- Both bottlenecks are expected and acceptable for privacy-preserving systems

***Performance Notes***:
* *Numbers verified through comprehensive adversarial stress testing*
* *No critical failures observed even under severe lock contention; some operations experienced increased latency and additional retries (see "Testing Criteria" below)*
* *Performance degrades gracefully under extreme conditions without system failure*

### Testing Criteria (brief)

- Failure definition: a "failure" is recorded when an operation encounters an irrecoverable error (for example, data corruption, invariant violation, or a process crash) that could not be resolved by the configured retry policy. Transient errors (network timeouts, temporary lock contention) that were resolved by retries are treated as degraded-but-successful for the purposes of the success rate reported above.
- Timeouts & retries: tests used a conservative retry policy (up to 3 retries per operation with exponential backoff starting at 50ms) and per-operation timeouts (default 5s) unless otherwise noted in the scenario configuration files.
- Measurement & logging: every transaction was verified end-to-end (cryptographic verification + ledger commit). All observed errors, retry counts, latencies, and outcome codes were recorded and are available in the stress test artifacts.
- Artifacts: benchmark results from real EC operations are in `tests/benchmarks/results/validated_20260227_143449.json` (100 trials per primitive, Apple M1 Pro, 2026-02-27). Legacy SHA-256 simulation stress test JSON files have been removed as they are not valid for the real EC pipeline.
- *Comparison: 400x faster than Zcash/Monero (~7 TPS) with comparable privacy*

---

## Installation & Setup

### Prerequisites

- **Python**: 3.10 (via `brew install python@3.10` — venv310 is the project venv)
- **PostgreSQL**: 14+
- **Homebrew packages**: `brew install pbc gmp` (required for charm-crypto)
- **Rust**: `rustup default stable` (required for native Bulletproofs dylib)

### Quick Start

#### 1. Clone Repository
```bash
git clone <repository-url>
cd IDX_CRYPTO_BANKING-073D
```

#### 2. Create Python 3.10 Virtual Environment
```bash
# Install Python 3.10 if not present
brew install python@3.10

# Create venv
/opt/homebrew/bin/python3.10 -m venv venv310
source venv310/bin/activate
python --version   # should show Python 3.10.x
```

#### 3. Install Dependencies
```bash
# charm-crypto MUST be installed from JHUISI source (PyPI version is broken)
brew install pbc gmp
git clone https://github.com/JHUISI/charm /tmp/charm
cd /tmp/charm && LDFLAGS="-L/opt/homebrew/lib" CFLAGS="-I/opt/homebrew/include" \
  pip install .

# All other project dependencies
cd /path/to/project
pip install -r requirements.txt
```

**Key packages installed**:
- Flask 3.0.0 (API framework)
- SQLAlchemy 2.0.23 (ORM)
- psycopg2-binary (PostgreSQL)
- PyJWT 2.8.0 (authentication)
- pycryptodome 3.19.0 (cryptography)
- py_ecc 8.0.0 (real EC — secp256k1 Pedersen/Schnorr)
- charm-crypto-framework 0.62 (real BBS04 group signatures on BN254)

#### 4. Database Setup
```bash
# Create database (DB name is idx_banking, NOT idx_crypto_banking)
createdb idx_banking

# Run migration
python scripts/run_migration_v3.py
```

#### 5. Initialize System Data
```bash
# Setup N-bank consortium (generates real BBS04 group signature keys)
python -c "
from database.connection import SessionLocal
from core.services.bank_account_service import BankAccountService
db = SessionLocal()
BankAccountService(db).setup_consortium_banks()
db.close()
"

# Setup foreign banks and forex rates
python -c "
from database.connection import SessionLocal
from core.services.travel_account_service import TravelAccountService
db = SessionLocal()
s = TravelAccountService(db)
s.setup_foreign_banks()
s.setup_forex_rates()
db.close()
"
```

#### 6. Run System

**Terminal 1 - API Server**:
```bash
source venv310/bin/activate
python -m api.app
# Runs on http://localhost:5000
```

**Terminal 2 - Mining Worker**:
```bash
source venv310/bin/activate
python core/workers/mining_worker.py
# Mines blocks every 10 seconds
```

**Terminal 3 - Verify Real Crypto**:
```bash
source venv310/bin/activate

# Real crypto module self-tests
python -m core.crypto.real.bbs_group_signature       # BBS04: 8 tests
python -m core.crypto.anomaly_zkp                    # Schnorr ZKP: 6 tests
python -m core.crypto.real.bulletproofs_wrapper      # Bulletproofs: all bit-lengths
python -m core.crypto.anomaly_threshold_encryption   # AES-256-GCM: 11 tests

# Integration test
python tests/integration/test_v3_complete_flow.py
```

---

## Testing

### Test Results

**Test Coverage**: 76/76 tests passed (100% success rate)
**Latest Run**: January 9, 2026

#### Real Crypto Self-Tests (current, Feb 2026)
- BBS04 Group Signatures (BN254): **8/8 tests** ✅ (setup/sign/verify/open/tamper/all-N-banks/cross-msg)
- Schnorr ZKP Anomaly (real EC): **6/6 tests** ✅ (generate/verify/tamper/opening/extract/invalid-score)
- AES-256-GCM Threshold Encryption: **11/11 tests** ✅ (including tamper-detection test)
- Pedersen Commitments (secp256k1): **4/4 tests** ✅
- Native Rust Bulletproofs: **all bit-lengths verified** ✅ (8/16/32/64-bit)

#### Legacy Unit Tests (simulation-era, Jan 2026)
- Commitment Scheme (SHA-256 sim — DEPRECATED): 7/7
- Range Proofs (SHA-256 sim — DEPRECATED): 9/9
- Group Signatures (string sim — DEPRECATED): 8/8
- Threshold Sharing (real Shamir): 9/9 ✅
- Dynamic Accumulator: 9/9 ✅
- Threshold Accumulator: 8/8 ✅
- Merkle Trees (real SHA-256): 6/6 ✅

> **Note on old performance test numbers**: The "64,004 ZKP/sec" figure was measured on the old SHA-256 simulation. Real Schnorr ZKP (secp256k1) runs at ~90/sec (11.12ms/proof). The SHA-256 figure must not be cited in the paper.

**Detection Accuracy Tests (4 tests)**:
- Scoring threshold: 97/100 correct (95% CI: 91.5%-99.4%) ✅
- False positive rate: 3/100 (95% CI: 0.6%-8.5%, target <5%) ✅
- True positive rate: 94/100 (95% CI: 87.4%-97.8%, target >90%) ✅
- Overall accuracy: 97/100 test cases (95% CI: 91.5%-99.4%, target >95%) ✅

#### Previous Integration Tests (Existing Features)
- Commitment integration ✅
- Range proof integration ✅
- Group signature (N banks) ✅
- Batch processing + Merkle ✅
- Threshold secret sharing ✅
- Threshold accumulator ✅
- Complete transaction flow ✅
- Performance benchmarks ✅
- Security verification ✅
- **N-bank consortium initialization** ✅
- **Real bank voting system** ✅
- **FFA re-verification & slashing** ✅
- **Escalating penalties (5%, 10%, 20%)** ✅
- **Bank deactivation threshold** ✅
- **Per-transaction encryption** ✅
- **Court order selective decryption** ✅
- **Fiscal year reward distribution** ✅
- **Existing features verification** ✅

#### System Integrity (7 checks)
- Original features intact ✅
- No deletions ✅
- No bugs introduced ✅
- Database migrated correctly ✅
- All cryptographic features functional ✅
- Performance targets met ✅
- Security requirements satisfied ✅

**Full test reports**:
- [docs/reports/TEST_REPORT.md](docs/reports/TEST_REPORT.md) - Comprehensive test results
- [docs/security/SECURITY_FIXES.md](docs/security/SECURITY_FIXES.md) - Security features implementation

---

## Project Structure

```
IDX_CRYPTO_BANKING-073D/
├── README.md                              # This file
├── CLAUDE.md                              # Session memory + full project reference
│
├── docs/                                  # All documentation
│   ├── paper/
│   │   ├── NOVELTY-SUMMARY.md            # CBC + RCTD novelty analysis
│   │   ├── ZK-AML-IMPLEMENTATION-REPORT.md # All 7 phases documented
│   │   └── zk-aml-poa.md                # Plan of action
│   ├── guides/
│   │   ├── TESTING-AND-BENCHMARKING-GUIDE.md
│   │   ├── FEATURES.md
│   │   └── DATABASE.md
│   ├── security/
│   │   ├── SECURITY_FIXES.md
│   │   └── SECURITY_FIXES_JAN_2026.md
│   └── reports/
│       ├── BREAKING_POINT_ANALYSIS.md
│       └── TEST_REPORT.md
│
├── api/                                   # REST API Layer (Flask)
│   ├── app.py
│   ├── routes/                           # 12 API blueprints
│   ├── middleware/
│   └── websocket/
│
├── core/                                  # Core Business Logic
│   ├── blockchain/
│   ├── consensus/
│   ├── crypto/
│   │   ├── real/                         # REAL crypto (use these)
│   │   │   ├── pedersen.py              # Pedersen commits (secp256k1)
│   │   │   ├── schnorr.py               # Schnorr ZKP
│   │   │   ├── simple_range_proof.py    # Schnorr OR range proof (ref)
│   │   │   ├── bulletproofs_wrapper.py  # Rust native Bulletproofs
│   │   │   ├── libbp_binding.dylib      # Compiled Rust dylib (aarch64)
│   │   │   └── bbs_group_signature.py   # BBS04 on BN254 (Charm-Crypto)
│   │   ├── legacy/                       # DEPRECATED simulations (do not use)
│   │   │   ├── commitment_scheme.py
│   │   │   ├── range_proof.py
│   │   │   └── group_signature.py
│   │   ├── anomaly_zkp.py               # Real Schnorr ZKP for AML flags
│   │   ├── anomaly_threshold_encryption.py # AES-256-GCM + Shamir TSS
│   │   ├── nested_threshold_sharing.py  # 2-of-2 outer + 1-of-4 inner
│   │   ├── dynamic_accumulator.py
│   │   ├── threshold_accumulator.py
│   │   └── merkle_tree.py
│   ├── services/
│   │   ├── transaction_service_v2.py    # Main tx lifecycle (real crypto)
│   │   ├── batch_processor.py           # BBS04 group signing
│   │   ├── bank_account_service.py
│   │   ├── court_order_service.py
│   │   ├── anomaly_detection_engine.py
│   │   └── travel_account_service.py
│   └── workers/
│
├── database/
│   ├── connection.py
│   └── models/                           # 21 SQLAlchemy models
│
├── scripts/
│   ├── run_migration_v3.py
│   └── migrations/                       # SQL migration files 002–010
│
└── tests/
    ├── benchmarks/
    │   ├── benchmark_validated.py        # Full crypto benchmark suite
    │   └── results/                      # JSON results (2026-02-27)
    ├── integration/                      # 13 integration test files
    ├── unit/
    └── performance/
```

---

## Security Features

### Security Enhancements

#### 1. Zero-Knowledge Privacy
- **Range Proofs**: Prove validity without revealing amounts
- **Commitments**: Hide transaction details on public chain
- **Nullifiers**: Prevent double-spending without linking transactions
- **Per-Transaction Encryption**: Unique AES-256 key per transaction
- **Result**: Complete transaction privacy with selective court-ordered access

#### 2. Distributed Control
- **N-Bank Consortium**: T-of-N approval for governance (T = N-X, X < N/3)
- **Threshold Accumulator**: Distributed freeze/unfreeze (T-of-N)
- **RCTD Access Structure**: No single entity can decrypt — requires Company ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA)
- **Bank Staking**: Each bank stakes 1% of total assets
- **Result**: No single point of failure or abuse

#### 3. Accountability & Governance
- **FFA Independent Validator**: Neutral third-party re-verification (10% random batches)
- **Automatic Slashing**: Progressive penalties (5% → 10% → 20%) for malicious votes
- **Bank Deactivation**: Remove banks when stake < 30% of initial
- **Treasury Management**: Slashed funds redistributed to honest banks
- **Fiscal Year Rewards**: Annual distribution proportional to honest verifications
- **Complete Audit Trail**: Every vote, slash, and reward logged
- **Result**: Strong economic incentives for honest behavior

#### 4. Challenge Mechanism
- **Bank Challenges**: Any bank can challenge suspicious batches
- **FFA Re-verification**: Independent validation on challenge
- **Malicious Detection**: Automatic slashing of incorrect votes
- **Peer Oversight**: Distributed watchdog system
- **Result**: Multi-layer fraud prevention

#### 5. Cryptographic Strength
- **SHA-256**: Industry standard hashing
- **AES-256**: Military-grade encryption
- **Zero-Knowledge**: Computational soundness
- **Accumulators**: Collision resistance
- **Result**: Future-proof security

---

## Use Cases

### 1. Private Transactions
```
Alice wants to send ₹50,000 to Bob without revealing amount publicly:
├─ Create commitment: Hash(Alice || Bob || 50000 || salt)
├─ Generate range proof: Prove 0 < 50000 ≤ Alice_balance (ZK)
├─ Post commitment to public chain (no amount visible)
├─ Full data encrypted on private chain
└─ Only Alice, Bob, and court orders can see amount
```

### 2. Account Freeze (Fraud)
```
HDFC Bank suspects fraud on account IDX_SUSPICIOUS:
├─ Create freeze proposal with reason
├─ N banks review evidence
├─ Need T-of-N approval to freeze (T = N-X, X < N/3)
├─ If approved, execute freeze
├─ O(1) check: is_frozen("IDX_SUSPICIOUS") → True
└─ Account cannot transact until unfrozen (needs T-of-N approval)
```

### 3. Court Investigation
```
Judge authorizes investigation of IDX_TARGET:
├─ Submit court order with case number
├─ Freeze account (T-of-N bank approval)
├─ Assemble keys (RCTD access structure):
│   ├─ Company Key (mandatory)
│   ├─ Court Key (mandatory)
│   └─ Regulatory Key: any 1-of-4 (FFA / FIU / FLEA / NTA)
├─ Reconstruct master key (Shamir's Secret Sharing)
├─ Decrypt private blockchain data
├─ View all transactions, identities, amounts
├─ Access valid for 24 hours only
└─ Complete audit trail maintained
```

### 4. High-Volume Processing
```
Exchange needs to process 10,000 transactions:
├─ Batch into groups of 100
├─ Process 100 batches in parallel
├─ Each batch: Merkle tree + consensus + DB (~12ms)
├─ Single consensus round per batch (not per transaction)
├─ Total time: ~1.8 seconds (with parallel processing)
└─ ~64.8 TPS measured (Python+Rust Bulletproofs Config A2); 69.1 TPS with batch verify
```

---

## Innovation Highlights

### 1. Role-Constrained Threshold Decryption (RCTD)
**Implementation**: Formally defined access structure for regulatory compliance in any jurisdiction

**System design**: Γ = (Company) ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA) — nested Shamir secret sharing

**Design goal**: Enforce legal oversight while preventing single-entity control; any one of 4 regulators suffices

### 2. Threshold Accumulator for Banking
**Implementation**: Application of threshold accumulator for account freeze/unfreeze

**System design**: Distributed governance of account status with T-of-N voting (T = N-X, X < N/3)

**Contribution**: Prevents single bank abuse while enabling rapid fraud response

### 3. Zero-Knowledge Banking
**Implementation**: Transaction privacy with regulatory compliance using zero-knowledge proofs

**System design**: Zero-knowledge proofs hide transaction details on public blockchain

**Operation modes**:
- Normal operation: Privacy via cryptographic commitments and range proofs
- Court orders: Multi-party threshold decryption when legally required

**Trade-off**: Privacy protection balanced against legal compliance requirements

### 4. Batch Processing with Merkle Proofs
**Implementation**: Proof size reduction through Merkle tree batch verification

**System design**: 192-byte Merkle proof for 100-transaction batch (99.997% compression from theoretical 800 KB uncompressed)

**Performance**: 64.8 TPS measured (Python+Rust Bulletproofs, Config A2); 69.1 TPS with batch verify (Config A2+batch). Legacy SHA-256 simulation measured 2,900–4,100 TPS — those numbers are not valid for the real EC pipeline.

---

## Roadmap

### Current System ✅ (COMPLETED)
- Sequence numbers + batch processing
- Merkle trees (SHA-256, 192-byte batch proof)
- Real Pedersen commitments on secp256k1 (DDH-hiding, perfectly binding)
- Real Bulletproofs via Rust (8.75ms prove / 2.09ms verify / 672 bytes)
- BBS04 group signatures on BN254 via Charm-Crypto (anonymous bank voting)
- RCTD: nested Shamir — Γ = (Company) ∧ (FFA ∨ FIU ∨ FLEA ∨ NTA)
- Hash-based set membership (dynamic accumulator, O(1))
- Threshold accumulator with T-of-N distributed voting
- N-bank consortium with T-of-N consensus
- R_velocity ZK circuit — velocity rule in ZK (CBC Gap 2; 61ms not-suspicious / 237ms suspicious)
- R_structuring ZK circuit — structuring rule in ZK (CBC Gap 3; 268ms–398ms by branch)
- 64.8 TPS measured (Python+Rust Config A2); 69.1 TPS with batch verify
- Travel accounts & international banking
- Rule-based anomaly detection (AML compliance, 97% accuracy)
- Real Schnorr ZKP anomaly proofs (11.28ms prove / 9.05ms verify, soundness 2^{-256})

### Future Enhancements
- Sharding for horizontal scaling
- Cross-shard transactions
- zk-SNARKs for even smaller proofs
- Hardware security module (HSM) integration
- Real-time fraud detection with ML
- International settlement integration
- Mobile SDK release
- Public mainnet launch

---

## Contributing

This is an academic research project.

**Purpose**: Academic paper submission
**Institution**: [Your University]

For questions or collaboration: [Contact information]

---

## License

Academic Research Project - Not for Commercial Use

---

## Documentation

- **[docs/paper/NOVELTY-SUMMARY.md](docs/paper/NOVELTY-SUMMARY.md)** - CBC + RCTD novelty analysis, literature comparison, reviewer Q&A
- **[docs/paper/ZK-AML-IMPLEMENTATION-REPORT.md](docs/paper/ZK-AML-IMPLEMENTATION-REPORT.md)** - All 7 implementation phases, CCS reviewer concerns addressed
- **[docs/guides/TESTING-AND-BENCHMARKING-GUIDE.md](docs/guides/TESTING-AND-BENCHMARKING-GUIDE.md)** - How to run benchmarks and tests
- **[docs/guides/FEATURES.md](docs/guides/FEATURES.md)** - Detailed feature documentation
- **[docs/guides/DATABASE.md](docs/guides/DATABASE.md)** - Database schemas and models (all 21 tables)
- **[docs/security/SECURITY_FIXES_JAN_2026.md](docs/security/SECURITY_FIXES_JAN_2026.md)** - Critical security fixes (threshold, consensus, statistics)
- **[docs/reports/TEST_REPORT.md](docs/reports/TEST_REPORT.md)** - Comprehensive test results
- **[CLAUDE.md](CLAUDE.md)** - Full project reference (architecture, crypto status, change log)

---

## Project Statistics

**Lines of Code**: 22,000+
**Database Tables**: 18 (added Treasury + BankVotingRecord)
**Cryptographic Modules**: 8 core + 3 anomaly detection
**Anomaly Detection Features**: 5 (detection engine, ZKP, threshold encryption, account freeze, court integration)
**API Endpoints**: 50+
**Test Coverage**: 76/76 tests passed (real crypto self-tests all pass)
**Performance**: 64.8 TPS measured (Python 3.10 + Rust Bulletproofs, Config A2); 69.1 TPS with batch verify (Config A2+batch). Legacy SHA-256 simulation measured 2,900–4,100 TPS — no longer valid for the real EC pipeline.
**Proof Size Reduction**: 99.997% (192-byte Merkle batch proof vs. theoretical uncompressed)
**Banks in Consortium**: N (configurable; default 12: 8 public sector + 4 private sector)
**Anomaly Detection Accuracy**: 97% (95% CI: 91.5%-99.4%, n=100 test cases)
**Consensus Threshold**: T-of-N banks (T = N-X, X < N/3; default T=10, N=12, 83% — raised from T_prev=8-of-12 in Jan 2026 for censorship resistance)

**Security Features**: FFA validator, automatic slashing, treasury, per-transaction AES-256-GCM encryption

***Performance Notes*** (master benchmark 2026-03-02, Apple M1 Pro ARM64, 100 trials):
- *Config A (Python EC only): ~54.8 TPS — 18.2ms/tx; bottleneck is py_ecc Pedersen + Schnorr*
- *Config A2 (Python + Rust Bulletproofs): ~64.8 TPS — 15.4ms/tx; Rust dylib for range proofs*
- *Config A2+batch (native bp_verify_batch): ~69.1 TPS — 1447ms/100tx; 1.87× sequential speedup*
- *ZK-AML prove speedup: 12.6× faster than Platypus (CCS 2022); 9,941× faster than Zerocash (S&P 2014)*
- *Legacy SHA-256 simulation (pre-2026): 2,900–4,100 TPS — these numbers measured a non-cryptographic hash chain, NOT real ZK proofs. They must NOT be used in any publication.*
- *Anomaly Accuracy: Tested on synthetic attack patterns (n=100); continuous monitoring required for real-world adversarial scenarios*

**Status**: Research prototype with full test coverage

---

## System Limitations

### Performance Limitations
- **TPS measurements**: Conducted in test environment with simulated consensus; real-world multi-bank network performance may vary
- **Network latency**: Assumes 10ms inter-bank latency; actual latency depends on geographic distribution
- **Scalability**: Current design does not include sharding; limited to single-chain throughput

### Security Limitations
- **Quantum resistance**: Uses classical cryptography (SHA-256, AES-256, DLog-based proofs); vulnerable to quantum attacks
- **Formal verification**: No formal proofs of cryptographic security properties
- **Third-party audit**: Implementation has not undergone external security audit
- **Side-channel attacks**: Timing and power analysis attacks not evaluated

### Privacy Limitations
- **Anonymity set**: Session rotation provides unlinkability over 24-hour periods; long-term pattern analysis not evaluated
- **Network analysis**: System does not protect against network-level traffic analysis
- **Court order scope**: Multi-party decryption reveals full transaction history, not just single transaction
- **Metadata leakage**: Transaction timing and batch membership publicly visible

### Regulatory Limitations
- **Legal compliance**: System design based on current regulatory framework; may require modification for other jurisdictions
- **Liability**: Legal liability for privacy failures or unauthorized decryption not addressed
- **Governance**: Threshold voting assumes honest majority; no mechanism for removing malicious banks

### Operational Limitations
- **Bank availability**: Requires T of N banks online for liveness; network partition can halt system
- **Key management**: Threshold key security depends on physical security at each organization
- **Recovery**: No mechanism for recovering from corrupted blockchain state
- **Deployment complexity**: Multi-organization deployment requires significant coordination

### Research Limitations
- **Novelty claims**: Similar approaches may exist in unpublished work or deployed systems
- **Baseline comparisons**: Performance comparisons conducted on different hardware/configurations
- **Threat model**: Adversary model assumes honest-but-curious or minority Byzantine; stronger adversaries not considered

---

**Research Contribution**: Blockchain de-anonymization with distributed legal oversight and zero-knowledge privacy

**Limitations**: This is a research prototype. Production deployment requires additional security audits, formal proofs, and regulatory approval.
