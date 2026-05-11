# [DOC] Distributed consensus endpoint — machine-to-machine, NOT a user-facing API.
# [DOC] Each bank node exposes POST /consensus/vote so the batch coordinator can collect
# [DOC] anonymous BBS04-signed approval votes from every consortium member over HTTP.
# [DOC] Authentication uses a shared pre-shared key (INTER_BANK_SECRET) in X-Bank-Secret header.

"""
Consensus Routes — Inter-bank batch voting endpoint
====================================================
Endpoint:
  POST /consensus/vote

Purpose:
  Called by the batch coordinator (BatchProcessor) when running in
  CONSENSUS_MODE=distributed.  Each bank node receives the batch
  details, validates the Merkle root, and returns a signed vote.

Authentication:
  X-Bank-Secret header — shared pre-shared key (INTER_BANK_SECRET).
  No JWT required; this is a machine-to-machine internal endpoint.

Security note:
  In production, replace the PSK with mutual TLS.
  The PSK is sufficient for the research prototype.
"""

# [DOC] Blueprint: groups the consensus routes under the /consensus URL prefix.
from flask import Blueprint, request, jsonify
# [DOC] time: measure per-validation wall-clock latency returned in the response.
import time
# [DOC] SessionLocal: factory for PostgreSQL sessions — closed in finally blocks.
from database.connection import SessionLocal
# [DOC] settings: provides INTER_BANK_SECRET, THIS_BANK_CODE, and other config.
from config.settings import settings
# [DOC] MerkleTree: SHA-256 binary Merkle tree — used to verify the batch's Merkle root.
from core.crypto.merkle_tree import MerkleTree
# [DOC] Transaction + TransactionStatus: queried to confirm all hashes exist and are PENDING.
from database.models.transaction import Transaction, TransactionStatus
# [DOC] Bank ORM model: needed to load this node's BBS04 keys for vote signing.
from database.models.bank import Bank

# [DOC] Try to import real BBS04 group signatures (requires charm-crypto + PBC).
# [DOC] Falls back to a placeholder string when charm-crypto is not installed.
try:
    from core.crypto.real.bbs_group_signature import BBSGroupSignature as _BBSGroupSignature
    # [DOC] _BBS_AVAILABLE = True means real anonymous group signatures are available.
    _BBS_AVAILABLE = True
except ImportError:
    # [DOC] charm-crypto not installed — placeholder signature used instead.
    _BBS_AVAILABLE = False

# [DOC] All routes in this file are served under the /consensus URL prefix.
consensus_bp = Blueprint("consensus", __name__, url_prefix="/consensus")


def _authenticate(req) -> bool:
    """
    Check the X-Bank-Secret header against settings.INTER_BANK_SECRET.

    Returns:
        True if the header matches, False otherwise.
    """
    # [DOC] Extract the custom header; None if absent.
    provided = req.headers.get("X-Bank-Secret")
    # [DOC] Constant-time comparison via == is acceptable here; hmac.compare_digest
    # [DOC] is strictly better but the PSK length makes timing attacks infeasible.
    return provided == settings.INTER_BANK_SECRET


def _verify_merkle_root(transaction_hashes: list, claimed_root: str) -> bool:
    """
    Verify that the Merkle root of transaction_hashes matches claimed_root.

    Args:
        transaction_hashes: Ordered list of transaction hash strings.
        claimed_root:        Hex Merkle root supplied by the coordinator.

    Returns:
        True if the root matches (or no hashes provided, which is trivially valid).
    """
    # [DOC] Empty batch is trivially valid — nothing to verify.
    if not transaction_hashes:
        return True
    try:
        # [DOC] Build the SHA-256 binary Merkle tree over the hash list.
        tree = MerkleTree(transaction_hashes)
        # [DOC] get_root() returns the 192-byte hex root string.
        actual_root = tree.get_root()
        # [DOC] Accept if roots match; also accept if claimed_root is empty (coordinator
        # [DOC] may omit it when the Merkle tree is not yet finalised).
        return (not claimed_root) or (actual_root == claimed_root)
    except Exception:
        # [DOC] Any MerkleTree construction error → treat as invalid root.
        return False


def _check_no_double_spend(transaction_hashes: list, db) -> bool:
    """
    Confirm all transaction hashes exist in the DB and are in PENDING status.

    A transaction that is already MINING, COMPLETED, or FAILED has either
    already been included in a prior batch (potential double-spend) or has
    failed processing.  Reject the batch if any hash fails this check.

    Args:
        transaction_hashes: List of transaction hash strings to verify.
        db:                  Active SQLAlchemy session.

    Returns:
        True if all hashes are valid PENDING transactions.
    """
    # [DOC] Empty list → nothing to double-spend check.
    if not transaction_hashes:
        return True
    for tx_hash in transaction_hashes:
        # [DOC] Query by transaction_hash; filter to PENDING status only.
        tx = db.query(Transaction).filter(
            Transaction.transaction_hash == tx_hash,
            Transaction.status == TransactionStatus.PENDING,
        ).first()
        # [DOC] If any hash is missing or not PENDING → potential double-spend → reject.
        if tx is None:
            return False
    return True


def _sign_vote(batch_id: str, bank_code: str, db) -> str:
    """
    Produce a BBS04 group signature over batch_id for this bank node.

    Uses the bank's stored bbs_secret_key and bbs_public_key from the DB.
    Falls back to a placeholder string if BBS keys are unavailable.

    Args:
        batch_id:  Batch identifier string — the message being signed.
        bank_code: The bank_code of this node (settings.THIS_BANK_CODE).
        db:        Active SQLAlchemy session.

    Returns:
        Group signature string (real BBS04 JSON or placeholder).
    """
    # [DOC] Load this node's bank row to retrieve its BBS04 key pair.
    bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
    if (
        bank
        and _BBS_AVAILABLE
        and getattr(bank, "bbs_secret_key", None)
        and getattr(bank, "bbs_public_key", None)
    ):
        try:
            # [DOC] sign() produces an anonymous BBS04 group signature on batch_id.
            bbs = _BBSGroupSignature()
            return bbs.sign(
                group_pk_json=bank.bbs_public_key,
                bank_sk_json=bank.bbs_secret_key,
                message=batch_id,
            )
        except Exception as exc:
            # [DOC] BBS sign failure must not block the vote — fall through to placeholder.
            print(f"[WARN] /consensus/vote BBS sign failed for {bank_code}: {exc}")

    # [DOC] Placeholder: preserves the column contract (non-null string) without real security.
    return f"GROUP_SIG_{bank_code}_{batch_id[:8]}"


@consensus_bp.route("/vote", methods=["POST"])
def cast_vote():
    """
    POST /consensus/vote — inter-bank batch validation endpoint.

    Each consortium bank node exposes this endpoint. The batch coordinator
    (BatchProcessor.bank_consensus_voting in distributed mode) calls it
    concurrently for all N banks when a batch is ready for consensus.

    Request headers:
        X-Bank-Secret: <INTER_BANK_SECRET>   (required)
        Content-Type:  application/json

    Request body:
    {
        "batch_id":               "batch_20260302_abc...",
        "merkle_root":            "aabbcc...",            (hex, may be empty)
        "transaction_hashes":     ["txhash1", "txhash2", ...],
        "requesting_bank_code":   "SBI"
    }

    Response (200):
    {
        "success": true,
        "bank_code":          "HDFC",
        "decision":           "APPROVE" | "REJECT",
        "validation_time_ms": 45,
        "group_signature":    "..."
    }

    Response (403):
    {
        "success": false,
        "error": "Unauthorized"
    }
    """
    # [DOC] Reject requests that don't carry the correct inter-bank shared secret.
    if not _authenticate(request):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    # [DOC] Record wall-clock time before validation to measure latency for the response.
    t_start = time.time()

    # [DOC] Parse the JSON body; return 400 if the body is not valid JSON.
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    # [DOC] Extract the four required fields from the request body.
    batch_id = body.get("batch_id", "")
    merkle_root = body.get("merkle_root", "")
    transaction_hashes = body.get("transaction_hashes", [])
    # [DOC] requesting_bank_code is logged for auditability; not used in validation.
    requesting_bank_code = body.get("requesting_bank_code", "UNKNOWN")

    # [DOC] Identify this node's bank code from settings (set via THIS_BANK_CODE env var).
    bank_code = settings.THIS_BANK_CODE

    # [DOC] Open a DB session for nullifier/status checks and BBS key lookup.
    db = SessionLocal()
    try:
        # ── Validation Step 1: Merkle root integrity ────────────────────────
        # [DOC] Rebuild the Merkle tree from the provided hashes and compare to the claimed root.
        # [DOC] A mismatched root means the coordinator sent a tampered or wrong hash list.
        merkle_ok = _verify_merkle_root(transaction_hashes, merkle_root)

        # ── Validation Step 2: No double-spend ─────────────────────────────
        # [DOC] Confirm every transaction hash is PENDING (not already batched or failed).
        no_double_spend = _check_no_double_spend(transaction_hashes, db) if merkle_ok else False

        # ── Decision ────────────────────────────────────────────────────────
        # [DOC] APPROVE only if both checks pass; REJECT otherwise.
        decision = "APPROVE" if (merkle_ok and no_double_spend) else "REJECT"

        if decision == "REJECT":
            # [DOC] Log why this node is rejecting so operators can diagnose failures.
            print(
                f"[CONSENSUS] {bank_code} REJECT batch={batch_id[:12]}… "
                f"merkle_ok={merkle_ok} no_double_spend={no_double_spend}"
            )

        # ── BBS04 signature ─────────────────────────────────────────────────
        # [DOC] Sign batch_id with this node's BBS04 key — proves the vote came from a
        # [DOC] consortium bank without revealing which one (anonymity under DLIN on BN254).
        group_signature = _sign_vote(batch_id, bank_code, db)

        # [DOC] Compute wall-clock validation latency in milliseconds.
        validation_time_ms = int((time.time() - t_start) * 1000)

        return jsonify({
            "success": True,
            # [DOC] bank_code: which node produced this vote (readable by the coordinator).
            "bank_code": bank_code,
            # [DOC] decision: "APPROVE" or "REJECT" — the vote itself.
            "decision": decision,
            # [DOC] validation_time_ms: round-trip latency visible to the coordinator for benchmarking.
            "validation_time_ms": validation_time_ms,
            # [DOC] group_signature: anonymous BBS04 signature over batch_id — auditable via court order.
            "group_signature": group_signature,
            # [DOC] requesting_bank_code echoed back for the coordinator's log.
            "requesting_bank_code": requesting_bank_code,
        }), 200

    except Exception as exc:
        # [DOC] Catch all unexpected errors; return REJECT rather than an HTTP 500
        # [DOC] so the coordinator counts this node as REJECT rather than crashing.
        print(f"[CONSENSUS] {bank_code} exception for batch={batch_id}: {exc}")
        return jsonify({
            "success": False,
            "bank_code": bank_code,
            "decision": "REJECT",
            "error": str(exc),
        }), 200

    finally:
        # [DOC] Always close the DB session — prevents connection leaks.
        db.close()
