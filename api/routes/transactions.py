"""
Transactions API Routes - V2 with Receiver Confirmation
Purpose: Transaction endpoints with receiver flow

New Flow Endpoints:
- POST /api/transactions/send - Create transaction (awaiting receiver)
- GET /api/transactions/pending-for-me - Get transactions awaiting my confirmation
- POST /api/transactions/{hash}/confirm - Confirm and select bank
- POST /api/transactions/{hash}/reject - Reject transaction
- GET /api/transactions/history/{idx} - Transaction history (existing)
"""

# [DOC] Blueprint groups related routes into one module; request holds incoming HTTP data; jsonify builds JSON responses
from flask import Blueprint, request, jsonify
# [DOC] Decimal is used for money amounts — Python floats have rounding errors, Decimal does not
from decimal import Decimal

# [DOC] require_auth is a decorator that checks the JWT token in the Authorization header before the route runs
from api.middleware.auth import require_auth
# [DOC] limiter applies per-endpoint rate limits; get_rate_limit fetches the string rule from settings
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] TransactionServiceV2 contains all business logic for creating, confirming, and rejecting transactions
from core.services.transaction_service_v2 import TransactionServiceV2
# [DOC] BankAccountService handles bank-account-level operations (ownership checks, account lookups)
from core.services.bank_account_service import BankAccountService
# [DOC] Transaction is the ORM model; TransactionStatus is the enum of possible states (PENDING, COMPLETED, etc.)
from database.models.transaction import Transaction, TransactionStatus


# [DOC] Blueprint registers all transaction routes under the /api/transactions URL prefix
transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')


@transactions_bp.route('/send', methods=['POST'])
# [DOC] limiter.limit applies the rate rule defined in settings for 'transaction_create' (e.g. "100 per hour")
@limiter.limit(lambda: get_rate_limit('transaction_create'))
# [DOC] require_auth injects (current_user, db) into the function — current_user is the authenticated User ORM object
@require_auth
def send_transaction(current_user, db):
    """
    Create transaction (sender initiates) - NEW: Uses nickname or IDX

    Request body:
        {
            "sender_account_id": 2,
            "recipient_nickname": "Mom",  # Option 1: Use saved nickname
            # OR
            "recipient_idx": "IDX_...",   # Option 2: Direct IDX
            "amount": 1000.00
        }

    Returns:
        JSON: {success: true, transaction: {...}, status: "awaiting_receiver"}

    NOTE: Session IDs are handled internally - users NEVER see them
    """
    try:
        # [DOC] request.get_json() parses the HTTP body as JSON and returns a Python dict
        data = request.get_json()

        # [DOC] Reject the request immediately if required fields are missing — fail fast, don't proceed with bad data
        # Validate required fields
        if 'sender_account_id' not in data:
            return jsonify({
                'success': False,
                'error': 'sender_account_id is required'
            }), 400

        if 'amount' not in data:
            return jsonify({
                'success': False,
                'error': 'amount is required'
            }), 400

        # [DOC] The API accepts EITHER a saved nickname OR a raw IDX — one must be present or the request is rejected
        # Must provide EITHER nickname OR idx
        if 'recipient_nickname' not in data and 'recipient_idx' not in data:
            return jsonify({
                'success': False,
                'error': 'Either recipient_nickname or recipient_idx is required'
            }), 400

        # [DOC] Validate that the amount field is a recognisable numeric type before converting it
        # INPUT VALIDATION: Type and range validation (code review recommendation)
        # Validate amount is numeric
        if not isinstance(data.get('amount'), (int, float, str)):
            return jsonify({
                'success': False,
                'error': 'Amount must be a number'
            }), 400

        try:
            # [DOC] Convert to string first, then to Decimal — avoids float precision loss (e.g. 10.1 → 10.09999...)
            amount = Decimal(str(data['amount']))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid amount format'
            }), 400

        # [DOC] Reject zero and negative amounts — a transfer must move real positive value
        # Validate amount is positive
        if amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Amount must be positive'
            }), 400

        # [DOC] Cap at ₹1 crore per transaction — limits blast radius of fraud and matches common banking policy
        # Validate maximum transaction limit (₹1 crore)
        MAX_TRANSACTION_AMOUNT = Decimal('10000000.00')  # ₹1 crore
        if amount > MAX_TRANSACTION_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount exceeds maximum transaction limit of ₹{MAX_TRANSACTION_AMOUNT:,.2f}'
            }), 400

        # [DOC] Reject tiny "dust" transactions (below ₹1) — prevents flooding the system with valueless entries
        # Validate minimum transaction (prevent dust transactions)
        MIN_TRANSACTION_AMOUNT = Decimal('1.00')  # ₹1
        if amount < MIN_TRANSACTION_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount must be at least ₹{MIN_TRANSACTION_AMOUNT}'
            }), 400

        # [DOC] Resolve the recipient IDX — either look it up by nickname or use the IDX provided directly
        # Get recipient IDX (from nickname or direct IDX)
        from database.models.recipient import Recipient
        from database.models.session import Session

        recipient_idx = None
        if 'recipient_nickname' in data:
            # [DOC] Query the Recipient table for a row belonging to this user with the given nickname
            # Look up recipient by nickname
            recipient = db.query(Recipient).filter(
                Recipient.user_idx == current_user.idx,
                Recipient.nickname == data['recipient_nickname']
            ).first()

            if not recipient:
                return jsonify({
                    'success': False,
                    'error': f"Recipient '{data['recipient_nickname']}' not found in your contacts"
                }), 404

            # [DOC] can_transact() enforces a 30-minute waiting period after a recipient is first added — anti-fraud measure
            # Check 30-minute waiting period
            if not recipient.can_transact():
                remaining = recipient.time_until_can_transact()
                return jsonify({
                    'success': False,
                    'error': 'Waiting period not complete. You can send money to this recipient in {:.0f} minutes.'.format(
                        remaining.total_seconds() / 60
                    ),
                    'can_transact_in_seconds': int(remaining.total_seconds()),
                    'can_transact_in_minutes': int(remaining.total_seconds() / 60)
                }), 403

            # [DOC] Extract the permanent IDX from the recipient record — this is what the system routes money to
            recipient_idx = recipient.recipient_idx

        elif 'recipient_idx' in data:
            # [DOC] Caller provided the IDX directly — use it as-is (no nickname lookup needed)
            recipient_idx = data['recipient_idx']

        # [DOC] Verify the sender_account_id actually belongs to the authenticated user — prevents sending from others' accounts
        # Verify sender owns the account
        account_service = BankAccountService(db)
        sender_account = db.query(BankAccount).filter(
            BankAccount.id == data['sender_account_id']
        ).first()

        if not sender_account or sender_account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Invalid sender account'
            }), 400

        # [DOC] Look up the sender's active 24-hour session ID for this specific bank account
        # [DOC] Session IDs rotate every 24h; the system always resolves the current one internally — users never manage this
        # Get current session IDs (internal mapping - users never see this)
        sender_session = db.query(Session).filter(
            Session.user_idx == current_user.idx,
            Session.bank_account_id == data['sender_account_id'],
            Session.is_active == True
        ).first()

        # [DOC] Look up the receiver's current active session — needed to record the public-chain session ID for the transaction
        receiver_session = db.query(Session).filter(
            Session.user_idx == recipient_idx,
            Session.is_active == True
        ).first()

        if not sender_session:
            return jsonify({
                'success': False,
                'error': 'Sender session not found. Please try again.'
            }), 500

        if not receiver_session:
            return jsonify({
                'success': False,
                'error': 'Receiver session not found. Recipient may need to log in.'
            }), 500

        # [DOC] create_transaction calls the full crypto pipeline: Pedersen commitment, Bulletproof range proof, anomaly scoring
        # [DOC] Status after this call is AWAITING_RECEIVER — the transaction waits for the receiver to confirm and pick a bank
        # Create transaction (using sessions internally but user provided IDX)
        service = TransactionServiceV2(db)
        transaction = service.create_transaction(
            sender_account_id=data['sender_account_id'],
            recipient_idx=recipient_idx,  # Changed from nickname to idx
            amount=amount,
            sender_session_id=sender_session.session_id,  # Mapped internally
            receiver_session_id=receiver_session.session_id  # Mapped internally
        )

        # [DOC] Return the transaction hash (not session IDs) — the hash is what the receiver uses to confirm
        return jsonify({
            'success': True,
            'message': 'Transaction created. Awaiting receiver confirmation.',
            'transaction': {
                'transaction_hash': transaction.transaction_hash,
                'recipient_idx': recipient_idx,  # Show IDX, not session
                'amount': str(transaction.amount),
                'fee': str(transaction.fee),
                'total': str(transaction.amount + transaction.fee),
                'status': transaction.status.value,
                'created_at': transaction.created_at.isoformat()
            },
            'status': 'awaiting_receiver'
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/pending-for-me', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_pending_for_me(current_user, db):
    """
    Get transactions awaiting my confirmation

    Returns:
        JSON: {
            success: true,
            pending_transactions: [
                {
                    transaction_hash,
                    amount,
                    sender_idx,
                    created_at,
                    ...
                }
            ]
        }
    """
    try:
        # [DOC] get_pending_transactions_for_receiver queries all transactions in AWAITING_RECEIVER status targeted at this user's IDX
        service = TransactionServiceV2(db)
        transactions = service.get_pending_transactions_for_receiver(current_user.idx)

        return jsonify({
            'success': True,
            'pending_transactions': [tx.to_dict() for tx in transactions],
            'count': len(transactions)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/<string:tx_hash>/confirm', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('transaction_confirm'))
@require_auth
def confirm_transaction(current_user, db, tx_hash):
    """
    Confirm transaction and select receiving bank

    Request body:
        {
            "receiver_account_id": 4
        }

    Returns:
        JSON: {success: true, transaction: {...}, status: "pending"}
    """
    try:
        # [DOC] Parse the JSON body to get the receiver_account_id chosen by the receiver
        data = request.get_json()

        if not data.get('receiver_account_id'):
            return jsonify({
                'success': False,
                'error': 'receiver_account_id is required'
            }), 400

        # [DOC] Verify the chosen account actually belongs to the authenticated receiver — prevents routing funds to another user's account
        # Verify receiver owns the account
        receiver_account = db.query(BankAccount).filter(
            BankAccount.id == data['receiver_account_id']
        ).first()

        if not receiver_account or receiver_account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Invalid receiver account'
            }), 400

        # [DOC] confirm_transaction updates the transaction status to PENDING and records the chosen receiver bank account
        # [DOC] After this, the transaction enters batch collection (waits for 100 transactions to form a batch)
        # Confirm transaction
        service = TransactionServiceV2(db)
        transaction = service.confirm_transaction(
            tx_hash,
            data['receiver_account_id']
        )

        return jsonify({
            'success': True,
            'message': f'Transaction confirmed. Receiving in {receiver_account.bank_code} account.',
            'transaction': transaction.to_dict(),
            'status': 'pending'
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/<string:tx_hash>/reject', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('transaction_confirm'))
@require_auth
def reject_transaction(current_user, db, tx_hash):
    """
    Reject transaction

    Returns:
        JSON: {success: true, message: "Transaction rejected"}
    """
    try:
        # [DOC] reject_transaction marks the transaction as REJECTED — no funds move and no block is created
        service = TransactionServiceV2(db)
        transaction = service.reject_transaction(tx_hash)

        return jsonify({
            'success': True,
            'message': 'Transaction rejected',
            'transaction': transaction.to_dict()
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/history/<string:idx>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_transaction_history(current_user, db, idx):
    """
    Get transaction history for user (IDX-level, user-friendly)

    Query params:
        limit: int (default: 50)
        offset: int (default: 0)

    Returns:
        JSON: {
            success: true,
            transactions: [
                {
                    transaction_hash,
                    direction: "sent" | "received",
                    counterparty_idx: "IDX_...",
                    counterparty_nickname: "Mom" | null,
                    amount: "10000.00",
                    fee: "150.00",
                    net_amount: "10150.00" (sent) or "10000.00" (received),
                    bank_account: "HDFC-12345678901234",
                    status: "completed",
                    date: "2025-12-27T15:00:00Z"
                }
            ]
        }

    NOTE: Session IDs are NEVER shown to users (privacy protection)
    """
    try:
        # [DOC] Enforce that a user can only request their own history — IDX in URL must match authenticated user's IDX
        # Only allow users to view their own history
        if idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        # [DOC] limit and offset implement pagination — default page size 50 keeps response payloads manageable
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get transactions
        from database.models.recipient import Recipient
        from database.models.bank_account import BankAccount

        # [DOC] OR filter: include transactions where this IDX appears as either sender OR receiver
        transactions = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()

        # [DOC] A separate COUNT query gives the total (for the client to compute page count) without fetching all rows
        total = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).count()

        # [DOC] Build a user-friendly list: determine direction, resolve nickname, calculate net amount
        # Build user-friendly response (IDX level, not sessions)
        result = []
        for tx in transactions:
            # [DOC] If this IDX is the sender, direction="sent" and the counterparty is the receiver, and vice versa
            # Determine direction
            if tx.sender_idx == idx:
                direction = "sent"
                counterparty_idx = tx.receiver_idx
                my_account_id = tx.sender_account_id
            else:
                direction = "received"
                counterparty_idx = tx.sender_idx
                my_account_id = tx.receiver_account_id

            # [DOC] Look up whether this counterparty IDX is saved as a named contact — returns None if not in contacts
            # Look up nickname from recipients list
            recipient = db.query(Recipient).filter(
                Recipient.user_idx == idx,
                Recipient.recipient_idx == counterparty_idx
            ).first()

            counterparty_nickname = recipient.nickname if recipient else None

            # [DOC] Format the bank account as "BANKCODE-AccountNumber" for display
            # Get bank account details
            account = db.query(BankAccount).get(my_account_id) if my_account_id else None
            bank_account_str = f"{account.bank_code}-{account.account_number}" if account else None

            # [DOC] Sender pays amount + fee; receiver receives amount (fee is already deducted from sender's side)
            # Calculate net amount (including fee for sender)
            if direction == "sent":
                net_amount = tx.amount + tx.fee
            else:
                net_amount = tx.amount  # Receiver doesn't pay fee

            result.append({
                'transaction_hash': tx.transaction_hash,
                'direction': direction,
                'counterparty_idx': counterparty_idx,
                'counterparty_nickname': counterparty_nickname,
                'amount': str(tx.amount),
                'fee': str(tx.fee) if direction == "sent" else "0.00",
                'net_amount': str(net_amount),
                'bank_account': bank_account_str,
                'status': tx.status.value,
                'date': tx.created_at.isoformat(),
                'completed_at': tx.completed_at.isoformat() if tx.completed_at else None
            })

        return jsonify({
            'success': True,
            'transactions': result,
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/<string:tx_hash>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_transaction_details(current_user, db, tx_hash):
    """
    Get transaction details

    Returns:
        JSON: {success: true, transaction: {...}}
    """
    try:
        # [DOC] Look up the transaction by its unique SHA-256 hash string
        transaction = db.query(Transaction).filter(
            Transaction.transaction_hash == tx_hash
        ).first()

        if not transaction:
            return jsonify({
                'success': False,
                'error': 'Transaction not found'
            }), 404

        # [DOC] Only the sender or receiver of this specific transaction may view its details — anyone else gets 403
        # Only allow sender or receiver to view
        if transaction.sender_idx != current_user.idx and transaction.receiver_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        return jsonify({
            'success': True,
            'transaction': transaction.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@transactions_bp.route('/pending', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_pending_transactions(current_user, db):
    """
    Get all pending transactions (for mining worker)

    Returns:
        JSON: {success: true, pending_transactions: [...]}
    """
    try:
        # [DOC] Fetch all PENDING transactions ordered by creation time (oldest first) — the mining worker processes them in order
        transactions = db.query(Transaction).filter(
            Transaction.status == TransactionStatus.PENDING
        ).order_by(Transaction.created_at).all()

        return jsonify({
            'success': True,
            'count': len(transactions),
            'pending_transactions': [tx.to_dict() for tx in transactions]
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# [DOC] BankAccount import placed at the bottom to avoid a circular import with the blueprint definition above
# Add missing import at top of file
from database.models.bank_account import BankAccount
