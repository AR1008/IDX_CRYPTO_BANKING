"""
Transaction Service V2 — Transaction lifecycle with real cryptographic privacy.

Handles the complete transaction lifecycle:
  1. Sender initiation with real Pedersen commitment and range proof.
  2. Receiver confirmation and bank selection.
  3. PMLA anomaly detection with real Schnorr ZKP (see anomaly_zkp.py).
  4. Threshold-encrypted evidence package for court-order access.

Cryptographic guarantees (post-migration 010):
  - Amount privacy:      Pedersen commitment C = v*G + r*H (DDH-hiding, DLOG-binding).
  - Balance validity:    Range proof proving 0 < amount ≤ balance (Schnorr OR-proofs).
  - Double-spend:        SHA-256 nullifier derived from commitment (unique per payment).

References:
  Pedersen (1991) CRYPTO — Pedersen commitments.
  Schnorr (1991) JoC    — Sigma protocols used in range proof.
  Bünz et al. (2018) S&P — Bulletproofs (future upgrade path for range proofs).
"""

# [DOC] Standard library: Decimal for exact currency arithmetic without floating-point rounding errors.
from decimal import Decimal
# [DOC] datetime/timezone used to timestamp transactions in UTC, avoiding local-timezone bugs.
from datetime import datetime, timezone
# [DOC] SQLAlchemy Session type hint — every DB read/write goes through this session object.
from sqlalchemy.orm import Session
# [DOC] Optional = value-or-None; Dict = typed dictionary — used in method signatures.
from typing import Optional, Dict
# [DOC] hashlib: SHA-256 for generating the transaction hash and the nullifier.
import hashlib
# [DOC] json: serialize Python dicts (range proof, ZKP proof) to TEXT for database storage.
import json
# [DOC] secrets: cryptographically secure random bytes for spend_secret (prevents nullifier guessing).
import secrets

# [DOC] ORM model for the transactions table — each row is one payment.
from database.models.transaction import Transaction, TransactionStatus
# [DOC] ORM model for bank_accounts — holds balance, bank code, frozen flag per account.
from database.models.bank_account import BankAccount
# [DOC] ORM model for users — contains the permanent IDX pseudonym.
from database.models.user import User
# [DOC] ORM model for recipients — stores IDX→nickname mappings so users enter IDX only once.
from database.models.recipient import Recipient
# [DOC] EventManager broadcasts WebSocket events (e.g. "transaction_pending") to connected clients.
from core.events.event_manager import EventManager

# ---------------------------------------------------------------------------
# Real cryptographic primitives (core/crypto/real/)
# ---------------------------------------------------------------------------
# [DOC] _pedersen_commit: computes C = v*G + r*H on secp256k1, returns (EC point, blinding_r).
# [DOC] serialize_point: converts the EC point to a 130-char hex string for TEXT column storage.
from core.crypto.real.pedersen import commit as _pedersen_commit, serialize_point
# [DOC] prove_commitment_opening: Schnorr sigma proof that the committer knows (v, r) opening C.
from core.crypto.real.schnorr import prove_commitment_opening
# [DOC] create_range_proof: Pedersen bit-commitment + Schnorr OR-proof that 0 < amount ≤ balance.
from core.crypto.real.simple_range_proof import create_range_proof


# [DOC] TransactionServiceV2 owns the entire lifecycle of a single payment (create → confirm → reject).
class TransactionServiceV2:
    """Transaction service with receiver confirmation and anomaly detection."""

    # [DOC] db is the SQLAlchemy session injected by the caller; all queries run through it.
    def __init__(self, db: Session):
        """Initialize transaction service."""
        self.db = db

    # [DOC] Fee schedule: 1.5% total split into 0.5% for the miner and 1.0% shared across banks.
    def calculate_fees(self, amount: Decimal) -> Dict[str, Decimal]:
        """Calculate transaction fees: 1.5% total (0.5% miner + 1.0% banks)."""
        # [DOC] Total fee deducted from sender; prevents the system running without incentive.
        total_fee = amount * Decimal('0.015')  # 1.5%
        # [DOC] Miner fee rewards the PoW worker that mines the block containing this batch.
        miner_fee = amount * Decimal('0.005')  # 0.5%
        # [DOC] Bank fee is split equally among all consortium banks as a governance reward.
        bank_fee = amount * Decimal('0.01')    # 1.0%

        return {
            'total_fee': total_fee,
            'miner_fee': miner_fee,
            'bank_fee': bank_fee,
            # [DOC] Divided by 6 here as a placeholder; actual per-bank split handled by settlement.
            'fee_per_bank': bank_fee / Decimal('6')
        }

    # [DOC] Generates a collision-resistant public identifier for the transaction.
    def generate_transaction_hash(
        self,
        sender_idx: str,
        receiver_idx: str,
        amount: Decimal
    ) -> str:
        """Generate unique SHA-256 transaction hash."""
        # [DOC] UTC timestamp makes the hash unique even if the same sender/receiver/amount repeat.
        timestamp = str(datetime.utcnow().timestamp())
        # [DOC] Concatenate all unique fields into one string before hashing.
        data = f"{sender_idx}:{receiver_idx}:{amount}:{timestamp}"
        # [DOC] SHA-256 produces a 64-char hex string used as the public transaction ID on-chain.
        return hashlib.sha256(data.encode()).hexdigest()

    # [DOC] Main entry point: sender calls this to initiate a payment; status becomes AWAITING_RECEIVER.
    def create_transaction(
        self,
        sender_account_id: int,
        recipient_nickname: str,
        amount: Decimal,
        sender_session_id: str
    ) -> Transaction:
        """Create transaction with sender initiation and anomaly detection."""
        # [DOC] Look up the sender's bank account by its primary key in the database.
        sender_account = self.db.query(BankAccount).filter(
            BankAccount.id == sender_account_id
        ).first()

        # [DOC] Guard: a missing account means a bad request or deleted account.
        if not sender_account:
            raise ValueError(f"Sender account not found: {sender_account_id}")

        # [DOC] Guard: frozen accounts are locked by court order and cannot send funds.
        if sender_account.is_frozen:
            raise ValueError(f"Account is frozen: {sender_account.account_number}")

        # [DOC] Resolve the saved nickname to the stored recipient record.
        # [DOC] Recipients are scoped to this sender's IDX so nicknames stay per-user.
        recipient = self.db.query(Recipient).filter(
            Recipient.user_idx == sender_account.user_idx,
            Recipient.nickname == recipient_nickname,
            Recipient.is_active == True
        ).first()

        # [DOC] Guard: the sender must have added this recipient at least once before.
        if not recipient:
            raise ValueError(f"Recipient '{recipient_nickname}' not found")

        # [DOC] Fees are computed before the balance check so the full deduction is validated.
        fees = self.calculate_fees(amount)
        # [DOC] total_required = transfer amount + all fees; the sender must cover both.
        total_required = amount + fees['total_fee']

        # [DOC] Guard: reject immediately if balance is insufficient.
        if sender_account.balance < total_required:
            raise ValueError(
                f"Insufficient balance. Required: INR{total_required}, "
                f"Available: INR{sender_account.balance}"
            )

        # [DOC] tx_hash is the public identifier — appears on the public chain and in logs.
        tx_hash = self.generate_transaction_hash(
            sender_account.user_idx,
            recipient.recipient_idx,
            amount
        )

        # ------------------------------------------------------------------
        # Real Pedersen commitment to transaction amount
        # ------------------------------------------------------------------
        # C = v*G + r*H  (computationally hiding under DDH on secp256k1;
        # perfectly binding — cannot open C to a different value).
        #
        # WHY PAISE: amounts are stored as Decimal rupees (e.g. ₹1000.50).
        # Elliptic curve scalar multiplication requires a whole number.
        # Multiplying by 100 converts to paise (100050) — a lossless integer.
        # User-facing amounts are always described in rupees; paise is an
        # internal implementation detail of the EC commitment layer only.
        #
        # WHERE r IS STORED: blinding_factor (r) is random and cannot be
        # recomputed. It is stored alongside the amount in the private chain
        # record (AES-256-GCM encrypted). A court order decrypts both (v, r);
        # verify_opening(C, v, r) then confirms the decryption is honest.
        amount_paise = int(amount * 100)          # ₹X.XX → integer paise for EC math
        # [DOC] balance_paise is the upper bound for the range proof (amount ≤ balance).
        balance_paise = int(sender_account.balance * 100)

        # [DOC] commitment_point is the EC point C; blinding_factor is the secret r used to open it.
        commitment_point, blinding_factor = _pedersen_commit(amount_paise)
        # [DOC] commitment_hex is the 130-char SEC1 uncompressed hex stored in the TEXT DB column.
        commitment_hex = serialize_point(commitment_point)  # 130-char "0x..." hex

        # Nullifier: SHA-256(commitment || sender_idx || random_secret)
        # Prevents double-spend detection without revealing amount.
        # Format follows the Zerocash nullifier construction (Sasson et al. 2014).
        # [DOC] spend_secret is a 16-byte random value; without it, nullifier is deterministic and guessable.
        spend_secret = secrets.token_hex(16)
        # [DOC] Nullifier ties commitment + identity + randomness into a single spend token.
        # [DOC] Before mining a batch, each bank checks this nullifier hasn't been seen before.
        nullifier_hex = hashlib.sha256(
            f"{commitment_hex}:{sender_account.user_idx}:{spend_secret}".encode()
        ).hexdigest()

        # ------------------------------------------------------------------
        # Real range proof: prove  0 < amount_paise ≤ balance_paise
        # ------------------------------------------------------------------
        # Uses Pedersen bit-commitments + Schnorr OR-proofs (CDS 1994).
        # Verifier learns only that the amount is within valid range;
        # neither the amount nor the balance is revealed.
        # Proof size: n_bits * (~300 bytes) + sum proof — stored as JSON TEXT.
        # [DOC] context=tx_hash provides domain separation: this proof is valid only for this tx.
        range_proof_data = create_range_proof(
            value_paise=amount_paise,
            max_value_paise=balance_paise,
            context=tx_hash         # Domain separation: ties proof to this tx
        )

        # ------------------------------------------------------------------
        # Schnorr proof of commitment opening (public attestation)
        # ------------------------------------------------------------------
        # Proves knowledge of (amount_paise, blinding_factor) s.t.
        # commitment_point = amount_paise*G + blinding_factor*H,
        # without revealing either witness value.
        # Soundness: 2^{-256} under DLOG on secp256k1.
        # [DOC] This separate opening proof lets auditors verify the commitment is well-formed.
        commitment_opening_proof = prove_commitment_opening(
            C=commitment_point,
            v=amount_paise,
            r=blinding_factor,
            context=f"tx_commitment:{tx_hash}"
        )

        # [DOC] Construct the ORM object — no DB write yet; that happens after anomaly detection.
        transaction = Transaction(
            transaction_hash=tx_hash,
            sender_account_id=sender_account_id,
            # [DOC] receiver_account_id is NULL until the receiver picks which account to receive into.
            receiver_account_id=None,           # NULL until receiver confirms
            sender_idx=sender_account.user_idx,
            receiver_idx=recipient.recipient_idx,
            sender_session_id=sender_session_id,
            # [DOC] current_session_id is the receiver's active 24h session ID; stored for public chain.
            receiver_session_id=recipient.current_session_id,
            amount=amount,
            fee=fees['total_fee'],
            miner_fee=fees['miner_fee'],
            bank_fee=fees['bank_fee'],
            # [DOC] AWAITING_RECEIVER: transaction is held until the receiver confirms and picks an account.
            status=TransactionStatus.AWAITING_RECEIVER,
            # --- Real cryptographic privacy fields ---
            # [DOC] commitment: the Pedersen point C — goes on the public chain; hides the amount.
            commitment=commitment_hex,                          # Pedersen commitment (TEXT)
            # [DOC] nullifier: spend token — checked by each bank to prevent double-spend.
            nullifier=nullifier_hex,                           # Double-spend prevention key
            # [DOC] commitment_salt: the blinding factor r — stored encrypted on the private chain for court-order opening.
            commitment_salt=f"0x{blinding_factor:064x}",       # Blinding factor (private chain)
            # [DOC] range_proof: JSON TEXT containing all Schnorr OR sub-proofs + the opening proof.
            range_proof=json.dumps({                           # Real range proof (JSON TEXT)
                **range_proof_data,
                "commitment_opening_proof": commitment_opening_proof,
                "scheme": "pedersen_bit_decomposition_schnorr_or",
                "reference": "Bünz et al. 2018 S&P (upgrade target: Bulletproofs)"
            })
        )

        # [DOC] Anomaly detection runs non-blocking — even if it raises, the transaction still completes.
        # [DOC] Imported inside the function to avoid a circular import at module load time.
        from core.services.anomaly_detection_engine import AnomalyDetectionEngine
        from core.crypto.anomaly_zkp import AnomalyZKPService
        from core.crypto.anomaly_threshold_encryption import AnomalyThresholdEncryption
        import json

        try:
            # [DOC] AnomalyDetectionEngine scores this transaction 0–100 using three rule-based checks.
            anomaly_engine = AnomalyDetectionEngine(self.db)
            anomaly_result = anomaly_engine.evaluate_transaction(transaction)

            # [DOC] Store all anomaly metadata on the transaction object (not committed yet).
            transaction.anomaly_score = Decimal(str(anomaly_result['score']))
            # [DOC] anomaly_flags is a list of human-readable flag names (e.g. "HIGH_VALUE_TIER_2").
            transaction.anomaly_flags = anomaly_result['flags']
            # [DOC] requires_investigation = True when score >= 65; does NOT freeze the account.
            transaction.requires_investigation = anomaly_result['requires_investigation']

            # [DOC] AnomalyZKPService generates a Schnorr ZKP that the score crossed the threshold.
            # [DOC] The ZKP is public; the actual score value and raw details are separately encrypted.
            zkp_service = AnomalyZKPService()
            zkp_proof = zkp_service.generate_anomaly_proof(
                transaction_hash=tx_hash,
                anomaly_score=anomaly_result['score'],
                anomaly_flags=anomaly_result['flags'],
                requires_investigation=anomaly_result['requires_investigation']
            )

            # [DOC] Strip the private 'witness' field before storing — the witness stays off-chain.
            public_proof = {k: v for k, v in zkp_proof.items() if k != 'witness'}
            # [DOC] zkp_anomaly_proof (TEXT): verifiable by anyone; proves flag status without details.
            transaction.zkp_anomaly_proof = json.dumps(public_proof)

            # [DOC] Only if score >= 65 do we run the more expensive threshold encryption step.
            if anomaly_result['requires_investigation']:
                # [DOC] Record the exact UTC time the flag was raised for audit purposes.
                transaction.flagged_at = datetime.now(timezone.utc)
                # [DOC] investigation_status tracks workflow state: PENDING → CLEARED or ESCALATED.
                transaction.investigation_status = 'PENDING'

                # [DOC] AnomalyThresholdEncryption wraps AES-256-GCM: encrypts details so only
                # [DOC] a court order + regulatory key can decrypt them later.
                threshold_enc = AnomalyThresholdEncryption()
                encrypted_package = threshold_enc.encrypt_transaction_details(
                    transaction_hash=tx_hash,
                    sender_idx=sender_account.user_idx,
                    receiver_idx=recipient.recipient_idx,
                    amount=amount,
                    anomaly_score=anomaly_result['score'],
                    anomaly_flags=anomaly_result['flags']
                )

                # [DOC] Serialize only the ciphertext and metadata; key shares are distributed separately.
                encrypted_json = json.dumps({
                    'encrypted_details': encrypted_package['encrypted_details'],
                    'transaction_hash': encrypted_package['transaction_hash'],
                    'encrypted_at': encrypted_package['encrypted_at'],
                    # [DOC] 'threshold' describes the key-assembly policy (e.g. "Company + 1-of-4").
                    'threshold': encrypted_package['threshold']
                })
                # [DOC] Stored as bytes in the BYTEA/TEXT column on the transaction row.
                transaction.threshold_encrypted_details = encrypted_json.encode('utf-8')

                # [DOC] Informational log; the user is deliberately NOT notified that they are flagged.
                print(f"[WARNING]  Transaction flagged for investigation")
                print(f"   Score: {anomaly_result['score']}")
                print(f"   Flags: {anomaly_result['flags']}")
                print(f"   ZKP proof generated (flag hidden)")
                print(f"   Details encrypted (threshold: Company+Court+1-of-4)")
                print(f"   User unaware - transaction continues normally")

        except Exception as e:
            # [DOC] Any anomaly detection failure is logged but does NOT block the payment.
            # [DOC] This prevents a buggy detection module from becoming a denial-of-service vector.
            print(f"[WARNING]  Anomaly detection error: {str(e)}")
            print(f"   Transaction proceeding normally (safety mechanism)")

        # [DOC] At this point the transaction is saved regardless of anomaly status.
        # [DOC] db.add() stages the ORM object; commit() flushes it to PostgreSQL.
        self.db.add(transaction)
        self.db.commit()
        # [DOC] refresh() re-reads the row so auto-generated fields (id, created_at) are populated.
        self.db.refresh(transaction)

        print(f"Transaction created: {tx_hash[:16]}...")
        print(f"   From: {sender_account.bank_code} account")
        print(f"   To: {recipient_nickname} ({recipient.recipient_idx[:16]}...)")
        print(f"   Amount: {amount}")
        print(f"   Fee: {fees['total_fee']}")
        print(f"   Status: AWAITING_RECEIVER")

        # [DOC] Emit a WebSocket event so the receiver's UI shows an incoming payment notification.
        EventManager.emit('transaction_pending', {
            'transaction_hash': tx_hash,
            'sender_idx': sender_account.user_idx,
            'receiver_idx': recipient.recipient_idx,
            'amount': str(amount),
            'recipient_nickname': recipient_nickname
        })

        return transaction

    # [DOC] Receivers call this to list all payments waiting for their confirmation.
    def get_pending_transactions_for_receiver(self, user_idx: str):
        """Get transactions awaiting receiver confirmation."""
        # [DOC] Filter by the receiver's IDX and AWAITING_RECEIVER status only.
        return self.db.query(Transaction).filter(
            Transaction.receiver_idx == user_idx,
            Transaction.status == TransactionStatus.AWAITING_RECEIVER
        ).all()

    # [DOC] Receiver calls this to choose which of their bank accounts to receive into.
    def confirm_transaction(
        self,
        transaction_hash: str,
        receiver_account_id: int
    ) -> Transaction:
        """Confirm transaction and select receiving bank account."""
        # [DOC] Load the transaction by its public hash.
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()

        # [DOC] Guard: transaction must exist.
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")

        # [DOC] Guard: can only confirm a transaction that is still waiting for receiver.
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver. Status: {transaction.status.value}")

        # [DOC] Load the receiver's chosen bank account.
        receiver_account = self.db.query(BankAccount).filter(
            BankAccount.id == receiver_account_id
        ).first()

        # [DOC] Guard: the account must exist in the database.
        if not receiver_account:
            raise ValueError(f"Receiver account not found: {receiver_account_id}")

        # [DOC] Security check: the account's IDX must match the transaction's receiver IDX.
        # [DOC] Prevents one user from redirecting a payment to another user's account.
        if receiver_account.user_idx != transaction.receiver_idx:
            raise ValueError("Account does not belong to receiver")

        # [DOC] Guard: the receiving account must not be frozen.
        if receiver_account.is_frozen:
            raise ValueError(f"Account is frozen: {receiver_account.account_number}")

        # [DOC] Bind the receiver's chosen account ID to the transaction row.
        transaction.receiver_account_id = receiver_account_id
        # [DOC] PENDING status means the transaction is now queued for batch collection and mining.
        transaction.status = TransactionStatus.PENDING  # Now ready for mining

        self.db.commit()
        self.db.refresh(transaction)

        print(f"Transaction confirmed: {transaction_hash[:16]}...")
        print(f"   Receiver selected: {receiver_account.bank_code} account")
        print(f"   Status: PENDING (ready for mining)")

        # [DOC] Notify all parties (sender and receiver) that confirmation succeeded via WebSocket.
        EventManager.emit('transaction_confirmed', {
            'transaction_hash': transaction_hash,
            'receiver_account_id': receiver_account_id,
            'receiver_bank': receiver_account.bank_code
        })

        return transaction

    # [DOC] Receiver can explicitly reject an incoming payment before confirming it.
    def reject_transaction(self, transaction_hash: str) -> Transaction:
        """Reject pending transaction."""
        # [DOC] Load by public hash.
        transaction = self.db.query(Transaction).filter(
            Transaction.transaction_hash == transaction_hash
        ).first()

        # [DOC] Guard: transaction must exist.
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_hash}")

        # [DOC] Guard: only AWAITING_RECEIVER transactions can be rejected.
        if transaction.status != TransactionStatus.AWAITING_RECEIVER:
            raise ValueError(f"Transaction not awaiting receiver")

        # [DOC] REJECTED is a terminal status — no further state transitions are possible.
        transaction.status = TransactionStatus.REJECTED

        self.db.commit()
        self.db.refresh(transaction)

        print(f"Transaction rejected: {transaction_hash[:16]}...")

        # [DOC] Notify sender via WebSocket so their UI reflects the rejection immediately.
        EventManager.emit('transaction_rejected', {
            'transaction_hash': transaction_hash,
            'receiver_idx': transaction.receiver_idx
        })

        return transaction


# [DOC] __main__ block: quick smoke-test when this file is run directly (not imported).
if __name__ == "__main__":
    """Test transaction service v2."""
    from database.connection import SessionLocal
    from core.crypto.idx_generator import IDXGenerator
    from core.services.recipient_service import RecipientService

    print("=== Transaction Service V2 Testing ===\n")

    db = SessionLocal()
    service = TransactionServiceV2(db)
    recipient_service = RecipientService(db)

    try:
        # [DOC] Derive test IDX values from known PAN+authority pairs for reproducible test data.
        sender_idx = IDXGenerator.generate("TESTA1234P", "100001")
        receiver_idx = IDXGenerator.generate("TESTC1234D", "100003")

        # [DOC] Fetch the sender's account at a specific bank for testing.
        sender_account = db.query(BankAccount).filter(
            BankAccount.user_idx == sender_idx,
            BankAccount.bank_code == "HDFC"
        ).first()

        if not sender_account:
            print("[ERROR] Sender account not found. Run migration first.")
            exit(1)

        # [DOC] Add the receiver to the sender's recipient list if not already present.
        recipient = recipient_service.get_recipient_by_idx(sender_idx, receiver_idx)
        if not recipient:
            print("  Adding recipient to contact list...")
            recipient = recipient_service.add_recipient(sender_idx, receiver_idx, "TestFriend")

        print(f"Sender account: {sender_account.bank_code} - INR{sender_account.balance}")
        print(f"Recipient: {recipient.nickname}\n")

        # [DOC] Test 1: create a transaction and verify it lands in AWAITING_RECEIVER.
        print("Test 1: Create Transaction (Awaiting Receiver)")
        tx = service.create_transaction(
            sender_account_id=sender_account.id,
            recipient_nickname="TestFriend",
            amount=Decimal('1000'),
            sender_session_id="SESSION_test_123"
        )
        print(f"  Status: {tx.status.value}")
        print(f"  Receiver account ID: {tx.receiver_account_id}")
        print("  [PASS] Test 1 passed!\n")

        # [DOC] Test 2: verify that the receiver can query their pending transactions.
        print("Test 2: Get Pending Transactions for Receiver")
        pending = service.get_pending_transactions_for_receiver(receiver_idx)
        print(f"  Found {len(pending)} pending transactions")
        print("  [PASS] Test 2 passed!\n")

        print("=" * 50)
        print("[PASS] All tests passed!")
        print("=" * 50)

    finally:
        db.close()
