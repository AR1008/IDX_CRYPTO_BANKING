# IDX Crypto Banking - Deployment Guide
## Production Deployment & System Architecture

**Author:** Ashutosh Rajesh
**Date:** December 29, 2025

---

## 🎯 System Overview

### Three-Layer Identity Architecture
1. **Session IDs** - Daily rotating, blockchain only, completely hidden
2. **IDX** - Permanent identifier for accounting/transactions
3. **Real Name** - Restricted database, company-controlled access

### Company-Controlled Access Management
- Company has master access to entire IDX registry
- Government/CAs get time-limited access via tokens
- All access automatically logged to tamper-proof audit trail
- Tokens auto-expire with background worker

### Enhanced User Experience
- Users add recipients by IDX with nickname
- 30-minute fraud prevention waiting period
- Transaction history shows IDX + nicknames (never sessions)
- Statement generation with digital signatures for CA verification

---

## 📋 Table of Contents

1. [Database Setup](#database-setup)
2. [API Endpoints Reference](#api-endpoints-reference)
3. [Access Control Workflows](#access-control-workflows)
4. [Testing Guide](#testing-guide)
5. [Production Deployment](#production-deployment)
6. [Security Considerations](#security-considerations)
7. [Troubleshooting](#troubleshooting)

---

## 🗄️ Database Setup

### Step 1: Create Database Tables

```bash
# Option 1: Using Python (recommended)
cd /path/to/idx_crypto_banking
python3 -m database.models.access_control

# Option 2: Using MySQL directly (if MySQL is running)
mysql -u root idx_crypto_banking < scripts/migrations/006_access_control_and_recipients.sql
```

### Step 2: Verify Tables Created

```bash
python3 << 'EOF'
from database.connection import SessionLocal, engine
from database.models.access_control import AccessToken, AccessAuditLog
from sqlalchemy import inspect

db = SessionLocal()
inspector = inspect(engine)

print("✅ Tables in database:")
for table_name in inspector.get_table_names():
    if table_name in ['access_tokens', 'access_audit_logs']:
        print(f"   - {table_name}")
        columns = inspector.get_columns(table_name)
        print(f"     Columns: {len(columns)}")

db.close()
EOF
```

### Step 3: Set Company Admin IDXs

In your `.env` file or environment:

```bash
# Set company admin IDXs (comma-separated)
COMPANY_ADMIN_IDXS=IDX_9ada28aeb18c59f7b4b2f12ca64e79d85b1e8f9d3c4a5b6e7f8a9b0c1d2e3f4a5,IDX_ADMIN
```

---

## 🔌 API Endpoints Reference

### 1. Admin API (Company Only)

**Base URL:** `/api/admin`

#### Grant Access to CA/Government

```bash
POST /api/admin/access/grant
Authorization: Bearer <admin_jwt>
Content-Type: application/json

{
  "granted_to": "ABC Tax Consultants Pvt Ltd",
  "role": "chartered_accountant",  # or "government"
  "purpose": "Tax season FY 2025-26",
  "duration_days": 7,
  "scope": {
    "user_idx": "IDX_abc123..."  # Optional: limit to specific user
  }
}

Response:
{
  "success": true,
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "role": "chartered_accountant",
  "granted_to": "ABC Tax Consultants Pvt Ltd",
  "expires_at": "2026-01-03T14:30:00Z",
  "access_url": "https://idx-banking.com/ca-portal?token=...",
  "duration_days": 7
}
```

#### Revoke Access

```bash
POST /api/admin/access/revoke
Authorization: Bearer <admin_jwt>
Content-Type: application/json

{
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "Tax season ended"
}
```

#### List Active Tokens

```bash
GET /api/admin/access/tokens?active_only=true&role=chartered_accountant
Authorization: Bearer <admin_jwt>

Response:
{
  "success": true,
  "tokens": [
    {
      "id": 1,
      "token": "550e8400-...",
      "role": "chartered_accountant",
      "granted_to": "ABC Tax Consultants",
      "expires_at": "2026-01-03T14:30:00Z",
      "is_active": true,
      "is_valid": true
    }
  ],
  "count": 1
}
```

#### View Audit Logs

```bash
GET /api/admin/access/audit?limit=100&action=LOOKUP_IDX_TO_NAME
Authorization: Bearer <admin_jwt>

Response:
{
  "success": true,
  "logs": [
    {
      "id": 1,
      "accessed_by": "ABC Tax Consultants",
      "action": "LOOKUP_IDX_TO_NAME",
      "target_idx": "IDX_abc123...",
      "accessed_at": "2025-12-27T10:30:00Z",
      "ip_address": "203.0.113.45"
    }
  ],
  "total": 150
}
```

---

### 2. IDX Registry API (CA/Government)

**Base URL:** `/api/idx-registry`

#### Lookup IDX → Real Name

```bash
POST /api/idx-registry/lookup
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "idx": "IDX_9ada28aeb18c59f7b4b2f12ca64e79d85b1e8f9d3c4a5b6e7f8a9b0c1d2e3f4a5"
}

Response:
{
  "success": true,
  "idx": "IDX_9ada28aeb...",
  "real_name": "Rajesh Kumar",
  "pan_card": "RAJSH1234K",
  "lookup_allowed": true,
  "accessed_by": "ABC Tax Consultants Pvt Ltd",
  "access_purpose": "Tax season FY 2025-26"
}
```

#### Bulk Lookup (up to 100 IDXs)

```bash
POST /api/idx-registry/bulk
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "idxs": [
    "IDX_9ada28aeb...",
    "IDX_1f498a455...",
    "IDX_7c3e9b2d1..."
  ]
}

Response:
{
  "success": true,
  "results": [
    {"idx": "IDX_9ada28aeb...", "real_name": "Rajesh Kumar", "pan_card": "RAJSH1234K"},
    {"idx": "IDX_1f498a455...", "real_name": "Priya Sharma", "pan_card": "PRIYA5678M"}
  ],
  "requested_count": 3,
  "found_count": 2
}
```

#### Verify Access Token

```bash
GET /api/idx-registry/verify-token
Authorization: Bearer <access_token>

Response:
{
  "success": true,
  "token_info": {
    "role": "chartered_accountant",
    "granted_to": "ABC Tax Consultants",
    "purpose": "Tax season FY 2025-26",
    "expires_at": "2026-01-03T14:30:00Z",
    "is_valid": true
  }
}
```

---

### 3. Statements API (Users)

**Base URL:** `/api/statements`

#### Generate Statement

```bash
POST /api/statements/generate
Authorization: Bearer <user_jwt>
Content-Type: application/json

{
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "format": "csv"
}

Response:
{
  "success": true,
  "statement_id": "stmt_550e8400-...",
  "download_url": "/api/statements/download/stmt_550e8400-...",
  "format": "csv",
  "expires_at": "2025-12-28T15:00:00Z",
  "signature": "a3f5c9e2b1d4f6a8c0e2b4d6f8a0c2e4b6d8f0a2c4e6b8d0f2a4c6e8b0d2f4a6",
  "signature_verification": "Use /api/statements/verify to verify authenticity"
}
```

#### Download Statement

```bash
GET /api/statements/download/stmt_550e8400-...
Authorization: Bearer <user_jwt>

Response: CSV file download
```

#### Verify Statement (Public - for CAs)

```bash
POST /api/statements/verify
Content-Type: application/json

{
  "user_idx": "IDX_9ada28aeb...",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "content": "<CSV content>",
  "signature": "a3f5c9e2b1d4f6a8c0e2b4d6f8a0c2e4b6d8f0a2c4e6b8d0f2a4c6e8b0d2f4a6"
}

Response:
{
  "success": true,
  "is_valid": true,
  "message": "Statement signature is valid"
}
```

---

### 4. Recipients API (Enhanced)

**Base URL:** `/api/recipients`

#### Add Recipient (30-minute waiting period)

```bash
POST /api/recipients/add
Authorization: Bearer <user_jwt>
Content-Type: application/json

{
  "recipient_idx": "IDX_1f498a455b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9",
  "nickname": "Mom"
}

Response:
{
  "success": true,
  "recipient": {
    "id": 1,
    "nickname": "Mom",
    "recipient_idx": "IDX_1f498a455...",
    "can_transact": false,
    "can_transact_in_seconds": 1800,
    "can_transact_in_minutes": 30
  },
  "message": "Recipient 'Mom' added. You can send money in 30 minutes (fraud prevention waiting period)."
}
```

#### List Recipients

```bash
GET /api/recipients
Authorization: Bearer <user_jwt>

Response:
{
  "success": true,
  "recipients": [
    {
      "id": 1,
      "nickname": "Mom",
      "recipient_idx": "IDX_1f498a455...",
      "can_transact": true,
      "is_active": true
    }
  ]
}
```

---

### 5. Transactions API (Updated)

**Base URL:** `/api/transactions`

#### Send Money (Using Nickname or IDX)

```bash
POST /api/transactions/send
Authorization: Bearer <user_jwt>
Content-Type: application/json

{
  "sender_account_id": 2,
  "recipient_nickname": "Mom",  # Option 1: Use nickname
  # OR "recipient_idx": "IDX_...",  # Option 2: Direct IDX
  "amount": 1000.00
}

Response:
{
  "success": true,
  "message": "Transaction created. Awaiting receiver confirmation.",
  "transaction": {
    "transaction_hash": "abc123...",
    "recipient_idx": "IDX_1f498a455...",
    "amount": "1000.00",
    "fee": "15.00",
    "total": "1015.00",
    "status": "awaiting_receiver"
  }
}
```

#### Get Transaction History (IDX Level)

```bash
GET /api/transactions/history/IDX_9ada28aeb...?limit=50&offset=0
Authorization: Bearer <user_jwt>

Response:
{
  "success": true,
  "transactions": [
    {
      "transaction_hash": "abc123...",
      "direction": "sent",
      "counterparty_idx": "IDX_1f498a455...",
      "counterparty_nickname": "Mom",
      "amount": "1000.00",
      "fee": "15.00",
      "net_amount": "1015.00",
      "bank_account": "HDFC-12345678901234",
      "status": "completed",
      "date": "2025-12-27T15:00:00Z"
    }
  ],
  "total": 1
}
```

---

## 🔐 Access Control Workflows

### Workflow 1: Tax Season - CA Access

```bash
# Step 1: Company grants CA access (7 days)
curl -X POST http://localhost:5000/api/admin/access/grant \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "granted_to": "ABC Tax Consultants Pvt Ltd",
    "role": "chartered_accountant",
    "purpose": "Tax season FY 2025-26",
    "duration_days": 7
  }'

# Response: { "token": "550e8400-...", ... }

# Step 2: CA uses token to lookup client
curl -X POST http://localhost:5000/api/idx-registry/lookup \
  -H "Authorization: Bearer 550e8400-..." \
  -H "Content-Type: application/json" \
  -d '{"idx": "IDX_9ada28aeb..."}'

# Response: { "real_name": "Rajesh Kumar", ... }

# Step 3: CA verifies client statement
# (Client provides CSV + signature)
curl -X POST http://localhost:5000/api/statements/verify \
  -H "Content-Type: application/json" \
  -d '{
    "user_idx": "IDX_9ada28aeb...",
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "content": "<CSV>",
    "signature": "a3f5c9e2..."
  }'

# Step 4: Token expires automatically after 7 days
# Background worker revokes it
```

### Workflow 2: Government Investigation

```bash
# Step 1: Company grants government access with scope
curl -X POST http://localhost:5000/api/admin/access/grant \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "granted_to": "Income Tax Department - Delhi",
    "role": "government",
    "purpose": "Investigation case #2025/IT/1234",
    "duration_days": 30,
    "scope": {
      "user_idx": "IDX_9ada28aeb..."
    }
  }'

# Step 2: Government verifies token
curl -X GET http://localhost:5000/api/idx-registry/verify-token \
  -H "Authorization: Bearer <gov_token>"

# Step 3: Government looks up specific user
curl -X POST http://localhost:5000/api/idx-registry/lookup \
  -H "Authorization: Bearer <gov_token>" \
  -H "Content-Type: application/json" \
  -d '{"idx": "IDX_9ada28aeb..."}'

# Step 4: Company monitors audit logs
curl -X GET http://localhost:5000/api/admin/access/audit \
  -H "Authorization: Bearer <admin_jwt>"
```

### Workflow 3: Auto-Revoke Expired Tokens

```bash
# Run background worker (cron job - every hour)
0 * * * * cd /path/to/idx_crypto_banking && python3 -m core.workers.token_expiry_worker

# Or manually
python3 -m core.workers.token_expiry_worker

# Output:
# ==================================================
# ACCESS TOKEN EXPIRY WORKER
# ==================================================
# ✅ Auto-revoked 3 expired token(s)
# ⚠️  2 token(s) expiring in next 24 hours
# ==================================================
```

---

## 🧪 Testing Guide

### Test 1: Access Control Flow

```bash
# Create test script
cat > test_access_control.py << 'EOF'
from database.connection import SessionLocal
from database.models.access_control import AccessToken, AccessRole
from datetime import datetime, timedelta
import uuid

db = SessionLocal()

# Create CA token
token = AccessToken(
    token=str(uuid.uuid4()),
    role=AccessRole.CHARTERED_ACCOUNTANT,
    granted_to="Test CA Firm",
    granted_by="ADMIN_TEST",
    purpose="Testing",
    expires_at=datetime.now() + timedelta(hours=1)
)
db.add(token)
db.commit()

print(f"✅ Created test token: {token.token}")
print(f"   Valid: {token.is_valid()}")
print(f"   Expires: {token.expires_at}")

db.close()
EOF

python3 test_access_control.py
```

### Test 2: 30-Minute Waiting Period

```bash
# Test recipient waiting period
cat > test_recipient_waiting.py << 'EOF'
from database.connection import SessionLocal
from database.models.recipient import Recipient
from database.models.user import User
from datetime import datetime

db = SessionLocal()

# Get test users
user1 = db.query(User).first()
user2 = db.query(User).offset(1).first()

# Add recipient
recipient = Recipient(
    user_idx=user1.idx,
    recipient_idx=user2.idx,
    nickname="Test Recipient"
)
db.add(recipient)
db.commit()

print(f"✅ Added recipient: {recipient.nickname}")
print(f"   Can transact: {recipient.can_transact()}")

if not recipient.can_transact():
    remaining = recipient.time_until_can_transact()
    print(f"   Wait time: {int(remaining.total_seconds() / 60)} minutes")

db.close()
EOF

python3 test_recipient_waiting.py
```

### Test 3: Statement Generation

```bash
# Start server
python3 api/app.py &

# Wait for server to start
sleep 5

# Login
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"pan_card":"TESTK1234A","rbi_number":"100001","bank_name":"HDFC"}' \
  | jq -r '.token')

# Generate statement
curl -X POST http://localhost:5000/api/statements/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "format": "csv"
  }' | jq

# Stop server
pkill -f "python3 api/app.py"
```

---

## 🚀 Production Deployment

### Environment Variables

```bash
# .env file
# Database
DATABASE_URL=mysql://user:pass@localhost/idx_crypto_banking

# Security Keys (CRITICAL - Generate unique values!)
SECRET_KEY=<generate_with_openssl_rand_hex_32>
JWT_SECRET_KEY=<generate_with_openssl_rand_hex_32>
APPLICATION_PEPPER=<generate_with_openssl_rand_hex_32>
RBI_MASTER_KEY_HALF=<generate_with_openssl_rand_hex_32>

# Company Admins (comma-separated IDXs)
COMPANY_ADMIN_IDXS=IDX_actual_admin_idx_here,IDX_another_admin

# CORS Origins
CORS_ORIGINS=https://idx-banking.com,https://ca-portal.idx-banking.com

# Frontend URL (for CA portal links)
FRONTEND_URL=https://idx-banking.com
```

### Cron Jobs

```bash
# Add to crontab: crontab -e

# Auto-revoke expired tokens (every hour)
0 * * * * cd /path/to/idx_crypto_banking && /usr/bin/python3 -m core.workers.token_expiry_worker >> /var/log/idx_token_expiry.log 2>&1

# Rotate sessions (every hour)
0 * * * * cd /path/to/idx_crypto_banking && /usr/bin/python3 -m core.session.rotation >> /var/log/idx_session_rotation.log 2>&1
```

### Systemd Service

```bash
# /etc/systemd/system/idx-banking.service
[Unit]
Description=IDX Crypto Banking API
After=network.target mysql.service

[Service]
Type=simple
User=idx-banking
WorkingDirectory=/opt/idx_crypto_banking
Environment="PYTHONPATH=/opt/idx_crypto_banking"
ExecStart=/usr/bin/python3 api/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name api.idx-banking.com;

    ssl_certificate /etc/letsencrypt/live/idx-banking.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/idx-banking.com/privkey.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io {
        proxy_pass http://localhost:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 🔒 Security Considerations

### 1. Access Token Security

- **Generate Strong Tokens:** Use UUID v4 for unpredictability
- **Short Expiry:** CAs max 30 days, Government max 90 days
- **Scope Restrictions:** Limit tokens to specific users when possible
- **Regular Audits:** Review access logs weekly

### 2. Admin Access Protection

```python
# In production, add additional checks
def require_company_admin(f):
    @wraps(f)
    def decorated(current_user, db, *args, **kwargs):
        # Check 1: IDX in admin list
        if current_user.idx not in settings.COMPANY_ADMIN_IDXS:
            return jsonify({'error': 'Unauthorized'}), 403

        # Check 2: MFA verification (TODO)
        # Check 3: IP whitelist (TODO)

        return f(current_user, db, *args, **kwargs)
    return decorated
```

### 3. Rate Limiting

```python
# Update config/rate_limits.py
RATE_LIMITS = {
    'admin_access_grant': '5 per hour',  # Strict limit
    'idx_registry_lookup': '100 per hour',
    'idx_registry_bulk': '10 per hour'
}
```

### 4. Audit Log Retention

```sql
-- Keep audit logs for 7 years (regulatory requirement)
-- Add to cron: backup audit logs monthly
0 0 1 * * mysqldump idx_crypto_banking access_audit_logs > /backup/audit_$(date +\%Y\%m).sql
```

---

## 🐛 Troubleshooting

### Issue 1: "Access token required" Error

**Symptom:**
```json
{"success": false, "error": "Access token required"}
```

**Solution:**
```bash
# Check Authorization header format
curl -H "Authorization: Bearer <token>"  # ✅ Correct
curl -H "Authorization: <token>"         # ❌ Wrong
```

### Issue 2: Token Expired

**Symptom:**
```json
{"success": false, "error": "Access token has expired"}
```

**Solution:**
```bash
# Check token expiry
curl -X GET http://localhost:5000/api/idx-registry/verify-token \
  -H "Authorization: Bearer <token>"

# Request new token from company admin
```

### Issue 3: 30-Minute Waiting Period

**Symptom:**
```json
{"error": "Waiting period not complete. You can send money in 25 minutes."}
```

**Solution:**
```bash
# This is EXPECTED behavior for fraud prevention
# Wait 30 minutes after adding recipient
# Check remaining time:
curl -X GET http://localhost:5000/api/recipients \
  -H "Authorization: Bearer <token>"
```

### Issue 4: "Insufficient permissions" Error

**Symptom:**
```json
{"success": false, "error": "Insufficient permissions"}
```

**Solution:**
```bash
# Check token role
curl -X GET http://localhost:5000/api/idx-registry/verify-token \
  -H "Authorization: Bearer <token>"

# Only CA/Government/Company roles can access registry
```

---

## 📊 Monitoring & Alerts

### Key Metrics to Monitor

1. **Access Token Usage**
   - Active tokens count
   - Tokens expiring in next 24 hours
   - Failed authentication attempts

2. **Audit Log Growth**
   - Lookups per hour
   - Unusual access patterns
   - Bulk lookup frequency

3. **Recipient Additions**
   - New recipients per day
   - Waiting period bypasses (should be 0)

### Sample Monitoring Script

```bash
#!/bin/bash
# monitoring.sh - Run every 5 minutes

# Check for tokens expiring soon
EXPIRING=$(python3 << 'EOF'
from database.connection import SessionLocal
from database.models.access_control import AccessToken
from datetime import datetime, timedelta

db = SessionLocal()
count = db.query(AccessToken).filter(
    AccessToken.is_active == True,
    AccessToken.expires_at < datetime.now() + timedelta(hours=24)
).count()
print(count)
db.close()
EOF
)

if [ "$EXPIRING" -gt 0 ]; then
    echo "⚠️  WARNING: $EXPIRING tokens expiring in next 24 hours"
    # Send alert to admin
fi
```

---

## ✅ Post-Deployment Checklist

- [ ] Database migration completed successfully
- [ ] All new blueprints registered in app.py
- [ ] Company admin IDXs configured in environment
- [ ] Background workers running (cron jobs)
- [ ] SSL certificates installed
- [ ] Nginx reverse proxy configured
- [ ] Rate limits configured
- [ ] Audit log backup scheduled
- [ ] Monitoring alerts configured
- [ ] Security keys rotated from defaults
- [ ] Test all API endpoints
- [ ] Verify token expiry workflow
- [ ] Test 30-minute waiting period
- [ ] Verify statement generation & verification

---

## 📞 Support & Documentation

- **API Docs:** http://localhost:5000/ (see endpoints list)
- **Source Code:** See `NEW_FEATURES_IMPLEMENTATION_GUIDE.md`
- **Security Model:** See database model docstrings
- **Architecture:** Three-layer identity (Session → IDX → Real Name)

---

**Deployment Complete! 🎉**

Your IDX Crypto Banking system now has:
- ✅ Three-layer identity privacy
- ✅ Company-controlled access management
- ✅ 30-minute fraud prevention
- ✅ Statement generation with signatures
- ✅ Complete audit trail
- ✅ Auto-expiring access tokens

**Next Steps:**
1. Test all workflows end-to-end
2. Configure monitoring & alerts
3. Train company admins on access grant/revoke
4. Document CA onboarding process
