# Test Data Generation Scripts

Comprehensive scripts for generating realistic test data and stress testing the IDX Crypto Banking system.

## 📁 Scripts Overview

| Script | Purpose | Estimated Time |
|--------|---------|----------------|
| `generate_banks.py` | Generate consortium and foreign banks | ~1-2 min for 1000 banks |
| `generate_users.py` | Generate users with bank accounts | ~5-10 min for 10,000 users |
| `generate_transactions.py` | Generate realistic transactions | ~10-20 min for 10,000 transactions |
| `stress_test_enhanced.py` | Comprehensive stress testing | ~5 min for full suite |

---

## 🏦 1. Generate Banks

Create consortium (Indian) and foreign banks for the system.

### Usage

```bash
# Generate 1000 consortium banks
python scripts/testing/generate_banks.py --type consortium --count 1000

# Generate 500 foreign banks
python scripts/testing/generate_banks.py --type foreign --count 500

# Generate both types
python scripts/testing/generate_banks.py --type all --consortium 1000 --foreign 500
```

### Output

- **Consortium banks**: Realistic Indian bank names (e.g., "Maharashtra State Bank", "National Bank of Karnataka")
- **Foreign banks**: Real banks from US, UK, Singapore, UAE (e.g., "JPMorgan Chase", "HSBC", "DBS Bank")
- **Stake amounts**: Random between ₹50M - ₹500M
- **Bank codes**: Sequential (CBANK00001, CBANK00002, etc.)

### Example Output

```
🏦 Generating 1000 consortium banks...
  ✅ Created 100/1000 banks...
  ✅ Created 200/1000 banks...
  ...
✅ Consortium banks created: 1000

🌍 Generating 500 foreign banks...
  ✅ Created 50/500 foreign banks...
  ...
✅ Foreign banks created: 500
```

---

## 👥 2. Generate Users

Create users with bank accounts and optional travel accounts.

### Prerequisites

- Must have banks in database (run `generate_banks.py` first)

### Usage

```bash
# Generate 10,000 users
python scripts/testing/generate_users.py --count 10000

# Generate 1,000 users, 100 with travel accounts
python scripts/testing/generate_users.py --count 1000 --with-travel 100
```

### Features

- **Realistic names**: Indian first + last names (e.g., "Aarav Sharma", "Priya Patel")
- **Valid PAN cards**: Format AAAAA9999A (e.g., "RAJP1234K")
- **IDX generation**: Using IDXGenerator with PAN + RBI number
- **Bank accounts**: 1-3 accounts per user with random balances (₹1K - ₹10L)
- **Travel accounts**: Optional foreign bank accounts

### Example Output

```
👥 Generating 10000 users...
   (including 100 with travel accounts)
📊 Found 1000 consortium banks in database
📊 Found 500 foreign banks in database
  ✅ Created 500/10000 users...
  ✅ Created 1000/10000 users...
  ...
✅ Users created: 10000
✅ Bank accounts created: 18543
✅ Travel accounts created: 100
```

---

## 💸 3. Generate Transactions

Create realistic transaction patterns for testing.

### Prerequisites

- Must have users and bank accounts in database

### Usage

```bash
# Generate 10,000 transactions (80% domestic, 20% travel)
python scripts/testing/generate_transactions.py --count 10000

# Generate 5,000 burst transactions
python scripts/testing/generate_transactions.py --count 5000 --pattern burst

# Generate 1,000 transactions (90% domestic, 10% travel)
python scripts/testing/generate_transactions.py --count 1000 --domestic-ratio 0.9
```

### Features

- **Realistic amounts**: Distribution weighted toward small transactions
  - 60% small (₹100 - ₹5K)
  - 30% medium (₹5K - ₹50K)
  - 9% large (₹50K - ₹5L)
  - 1% very large (₹5L - ₹50L)

- **Transaction types**:
  - Domestic (Indian → Indian)
  - Travel deposits (Indian → Foreign travel account)

- **Patterns**:
  - `random`: No delays (max speed)
  - `burst`: Random short pauses (realistic)
  - `steady`: Fixed 0.1s delay (controlled)

### Example Output

```
💸 Generating 10000 transactions...
   Pattern: random
   Domestic ratio: 80%
📊 Found 10000 users with 18543 bank accounts
  ✅ Created 500/10000 transactions...
  ✅ Created 1000/10000 transactions...
  ...
✅ Domestic transactions created: 8012
✅ Travel transactions created: 1988
```

---

## 🧪 4. Stress Test Suite

Comprehensive testing of all implemented features.

### Prerequisites

- API server running (`python api/app.py`)
- Database populated with test data

### Usage

```bash
# Run all tests
python scripts/testing/stress_test_enhanced.py --all

# Run specific test
python scripts/testing/stress_test_enhanced.py --test concurrent-registration

# Run with verbose output
python scripts/testing/stress_test_enhanced.py --all --verbose
```

### Tests Included

#### Test 1: Concurrent User Registration
- **Purpose**: Validates race condition bug fix
- **Method**: 100 concurrent registrations with same PAN
- **Expected**: 1 success (201), 99 conflicts (409), 0 errors (500)

#### Test 2: Rate Limiting
- **Purpose**: Validates DDoS protection
- **Method**: Rapid requests to registration endpoint
- **Expected**: Some 429 (Too Many Requests) responses

#### Test 3: Audit Chain Integrity
- **Purpose**: Validates tamper-proof audit trail
- **Method**: Calls `/api/audit/verify` endpoint
- **Expected**: Chain valid = true

### Example Output

```
============================================================
  ENHANCED STRESS TEST SUITE
============================================================
Started at: 2025-12-26 10:30:00
API Base URL: http://localhost:5000

============================================================
  Test 1: Concurrent User Registration (100 users)
============================================================

Attempting 100 concurrent registrations...
Expected: 1 success (201), 99 conflicts (409), 0 errors (500)

📊 Results:
   201 Created: 1
   409 Conflict: 99
   400 Bad Request: 0
   500 Server Error: 0
   Other: 0
   Time: 2.45s

✅ PASSED

============================================================
  Test 2: Rate Limiting (50 requests)
============================================================

Sending 50 requests to /api/auth/register...
Expected: Some 429 (Too Many Requests) responses

📊 Results:
   200 OK: 0
   201 Created: 10
   409 Conflict: 25
   429 Rate Limited: 15
   500 Server Error: 0
   Time: 5.12s

✅ PASSED

============================================================
  Test 3: Audit Chain Integrity
============================================================

Verifying audit log chain integrity...

📊 Results:
   Chain valid: True
   Message: Chain verified: 1523 logs intact

✅ PASSED

============================================================
  TEST SUMMARY
============================================================
✅ PASS  concurrent_registration
✅ PASS  rate_limiting
✅ PASS  audit_chain_integrity

Total: 3/3 passed
Finished at: 2025-12-26 10:35:00
```

---

## 📖 Complete Workflow Example

Here's a complete workflow to generate test data and run stress tests:

```bash
# Step 1: Generate banks (1000 consortium, 500 foreign)
python scripts/testing/generate_banks.py --type all --consortium 1000 --foreign 500

# Step 2: Generate users (10,000 users, 100 with travel accounts)
python scripts/testing/generate_users.py --count 10000 --with-travel 100

# Step 3: Generate transactions (10,000 transactions, 80% domestic)
python scripts/testing/generate_transactions.py --count 10000 --domestic-ratio 0.8

# Step 4: Start API server (in another terminal)
python api/app.py

# Step 5: Run stress tests
python scripts/testing/stress_test_enhanced.py --all --verbose
```

### Expected Execution Time

- **Banks**: ~2 minutes
- **Users**: ~10 minutes
- **Transactions**: ~15 minutes
- **Stress tests**: ~5 minutes
- **Total**: ~32 minutes for full setup and testing

---

## 🎯 Performance Targets

### After running test data generation:

- **Users**: 10,000+ users
- **Bank accounts**: 15,000+ accounts (1-3 per user)
- **Travel accounts**: 100+ accounts
- **Transactions**: 10,000+ transactions
- **Consortium banks**: 1,000+ banks
- **Foreign banks**: 500+ banks

### Stress test targets:

- **Concurrent registration**: 0% error rate (was 100% before fix)
- **Rate limiting**: Active (some 429 responses)
- **Audit chain**: 100% integrity
- **Transaction throughput**: 10+ TPS (when implemented)
- **Mining competition**: Multiple miners compete successfully

---

## 🔍 Troubleshooting

### Error: "No banks found in database"
```bash
# Solution: Generate banks first
python scripts/testing/generate_banks.py --type consortium --count 100
```

### Error: "No users found in database"
```bash
# Solution: Generate users first
python scripts/testing/generate_users.py --count 1000
```

### Error: "Connection refused" (stress tests)
```bash
# Solution: Start API server
python api/app.py
```

### Error: "Insufficient balance" (transactions)
```bash
# Solution: Users may have spent their initial balance. Generate more users or reset database.
```

---

## 📊 Database Verification

Check generated data in database:

```sql
-- Check banks
SELECT COUNT(*) FROM consortium_banks;
SELECT COUNT(*) FROM foreign_banks;

-- Check users and accounts
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM bank_accounts;
SELECT COUNT(*) FROM travel_accounts;

-- Check transactions
SELECT COUNT(*) FROM transactions;
SELECT transaction_type, COUNT(*) FROM transactions GROUP BY transaction_type;

-- Check balances
SELECT SUM(balance) FROM bank_accounts;
SELECT AVG(balance) FROM bank_accounts;
```

---

## 🚀 Advanced Usage

### Custom Distribution

Generate specific user/bank ratios:

```bash
# Many banks, few users (test bank selection)
python scripts/testing/generate_banks.py --type consortium --count 5000
python scripts/testing/generate_users.py --count 1000

# Few banks, many users (test load on banks)
python scripts/testing/generate_banks.py --type consortium --count 10
python scripts/testing/generate_users.py --count 10000
```

### Transaction Patterns

Test different scenarios:

```bash
# High-value transactions (stress test SAR alerts - Priority 6)
python scripts/testing/generate_transactions.py --count 100 --pattern steady

# Burst traffic (stress test rate limiting)
python scripts/testing/generate_transactions.py --count 5000 --pattern burst

# Steady stream (test system stability)
python scripts/testing/generate_transactions.py --count 10000 --pattern steady
```

---

## 📝 Notes

- All scripts use progress indicators for long-running operations
- Error handling includes rollback to prevent partial data
- First 5 errors are displayed for debugging
- All times are estimates and vary based on hardware
- Scripts can be run multiple times (will create more data)
- Use `--help` flag on any script for detailed usage

---

**Created**: December 26, 2025
**Part of**: Priority 7 - Test Data Generation
