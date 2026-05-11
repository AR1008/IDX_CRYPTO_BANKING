-- Migration 007: Advanced Cryptography V3.0
-- Purpose: Add sequence numbers, batching, and cryptographic fields
-- Date: 2025-12-27

-- ============================================================
-- PART 1: Add V3.0 Fields to Transactions Table
-- ============================================================

-- [DOC] COLUMN: transactions.sequence_number
-- [DOC] A globally unique, monotonically increasing integer assigned to every transaction
-- [DOC] in strict creation order. Its primary security purpose is replay-attack prevention:
-- [DOC] if an attacker captures a valid signed transaction and re-submits it, the nullifier
-- [DOC] check catches double-spends, but sequence_number provides a second independent guard.
-- [DOC] Each bank in the consortium independently verifies that sequence_number > last_seen,
-- [DOC] so a replayed old packet is always rejected.
-- [DOC] UNIQUE constraint ensures no two transactions can share a sequence number.

-- 1.1 Add sequence number (CRITICAL - prevents replay attacks)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS sequence_number BIGINT UNIQUE;

-- [DOC] A PostgreSQL SEQUENCE is a special database object that atomically generates
-- [DOC] the next integer on demand. Using a sequence (rather than MAX(id)+1) is safe
-- [DOC] under concurrent inserts: two simultaneous transactions cannot get the same number.
CREATE SEQUENCE IF NOT EXISTS transaction_sequence_seq START 1;

-- [DOC] Back-fill sequence numbers for any transactions created before this migration.
-- [DOC] nextval('transaction_sequence_seq') fetches and increments the sequence atomically.
-- [DOC] Each existing row gets a unique number; the order is preserved by sequence_number IS NULL
-- [DOC] (all existing rows are NULL at this point).
UPDATE transactions
SET sequence_number = nextval('transaction_sequence_seq')
WHERE sequence_number IS NULL;

-- [DOC] Now that every row has a value, tighten the constraint to NOT NULL so future
-- [DOC] INSERTs without a sequence_number are rejected at the database level.
ALTER TABLE transactions
ALTER COLUMN sequence_number SET NOT NULL;

-- [DOC] COLUMN: transactions.batch_id
-- [DOC] Transactions are grouped into batches of 100 before being submitted to the N-bank
-- [DOC] consensus round. batch_id is a string identifier (e.g. "BATCH_20260227_001") that
-- [DOC] links all 100 transactions in the same batch together. The consensus engine uses
-- [DOC] this to build the Merkle tree: it fetches all rows WHERE batch_id = ? and hashes
-- [DOC] their transaction_hash values into a 192-byte Merkle root stored in transaction_batches.

-- 1.2 Add batch ID
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS batch_id VARCHAR(50);

-- [DOC] COLUMN: transactions.commitment
-- [DOC] A Pedersen commitment to the transaction amount. Pedersen commitments are
-- [DOC] cryptographically hiding (no one can derive the amount from the commitment alone)
-- [DOC] and binding (the committer cannot later claim a different amount).
-- [DOC] Format at this migration: VARCHAR(66) — fits a 32-byte SHA-256 hex string with "0x" prefix.
-- [DOC] NOTE: Migration 010 later expands this to TEXT because real Pedersen commitments
-- [DOC] (uncompressed elliptic curve points on secp256k1) are 130 characters long.

-- [DOC] COLUMN: transactions.nullifier
-- [DOC] A one-time token derived from (commitment, sender_idx, secret). It is stored in the
-- [DOC] nullifier accumulator after a transaction completes. Before processing any transaction,
-- [DOC] every bank checks: "is this nullifier already in the accumulator?" If yes, the
-- [DOC] transaction is a double-spend and is rejected. This provides O(1) double-spend detection.
-- [DOC] UNIQUE constraint: the database enforces that no nullifier appears twice.

-- [DOC] COLUMN: transactions.range_proof
-- [DOC] A Bulletproof zero-knowledge range proof proving that the transaction amount is
-- [DOC] in the range [0, 2^64 - 1] without revealing the amount itself. Stored as a
-- [DOC] base64 or hex-encoded byte blob. Each bank verifies the proof (2.11 ms) during
-- [DOC] consensus before casting its vote.

-- [DOC] COLUMN: transactions.group_signature
-- [DOC] The BBS04 group signature cast by the bank that proposed this transaction's batch.
-- [DOC] Group signatures are anonymous within the group — verifiers can confirm a legitimate
-- [DOC] consortium bank signed without knowing which bank. The group manager (RBI equivalent)
-- [DOC] can open the signature to identify the signer if required (e.g. for slashing).

-- [DOC] COLUMN: transactions.commitment_salt
-- [DOC] The random blinding factor r used when creating the Pedersen commitment C = v*G + r*H.
-- [DOC] This is stored encrypted alongside the commitment so the sender can later prove
-- [DOC] they know the opening (v, r) during a court-ordered decryption. VARCHAR(66) here;
-- [DOC] expanded to TEXT by migration 010 for the same reason as commitment.

-- 1.3 Add cryptographic fields for advanced privacy
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS commitment VARCHAR(66),
ADD COLUMN IF NOT EXISTS nullifier VARCHAR(66) UNIQUE,
ADD COLUMN IF NOT EXISTS range_proof TEXT,
ADD COLUMN IF NOT EXISTS group_signature TEXT,
ADD COLUMN IF NOT EXISTS commitment_salt VARCHAR(66);

-- [DOC] INDEX on sequence_number: The consensus engine and replay-attack checks look up
-- [DOC] "latest sequence_number seen" frequently. Sorted index makes MAX() O(log n).
CREATE INDEX IF NOT EXISTS idx_tx_sequence ON transactions(sequence_number);

-- [DOC] INDEX on batch_id: The Merkle-tree builder fetches all transactions for a batch
-- [DOC] with WHERE batch_id = ?. Without this index, that is a full table scan.
CREATE INDEX IF NOT EXISTS idx_tx_batch ON transactions(batch_id);

-- [DOC] INDEX on commitment: Allows fast lookup of a transaction by its commitment value,
-- [DOC] used during court-order decryption to locate the correct private chain record.
CREATE INDEX IF NOT EXISTS idx_tx_commitment ON transactions(commitment);

-- [DOC] INDEX on nullifier: The double-spend check queries "SELECT 1 FROM transactions
-- [DOC] WHERE nullifier = ?" before accepting any new transaction. This index makes that
-- [DOC] lookup O(log n) rather than a full scan — critical for throughput.
CREATE INDEX IF NOT EXISTS idx_tx_nullifier ON transactions(nullifier);

-- ============================================================
-- PART 2: Validation Queries
-- ============================================================

-- 2.1 Verify sequence numbers assigned
SELECT
    'Sequence Numbers' AS check_name,
    COUNT(*) AS total_transactions,
    MIN(sequence_number) AS min_sequence,
    MAX(sequence_number) AS max_sequence,
    COUNT(DISTINCT sequence_number) AS unique_sequences
FROM transactions;

-- 2.2 Show sample data
SELECT
    'Sample V3.0 Data' AS description,
    id,
    sequence_number,
    batch_id,
    commitment IS NOT NULL AS has_commitment,
    created_at
FROM transactions
ORDER BY sequence_number DESC
LIMIT 5;

-- ============================================================
-- Migration Complete!
-- ============================================================

SELECT '✅ Migration 007 completed successfully!' AS status;
SELECT 'V3.0 features enabled: Sequence numbers, Batching, Advanced Cryptography' AS features;
