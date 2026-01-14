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

from flask import Blueprint, request, jsonify
from decimal import Decimal

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from core.services.transaction_service_v2 import TransactionServiceV2
from core.services.bank_account_service import BankAccountService
from database.models.transaction import Transaction, TransactionStatus


transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')


@transactions_bp.route('/send', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('transaction_create'))
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
        data = request.get_json()

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

        # Must provide EITHER nickname OR idx
        if 'recipient_nickname' not in data and 'recipient_idx' not in data:
            return jsonify({
                'success': False,
                'error': 'Either recipient_nickname or recipient_idx is required'
            }), 400
        
        # INPUT VALIDATION: Type and range validation (code review recommendation)
        # Validate amount is numeric
        if not isinstance(data.get('amount'), (int, float, str)):
            return jsonify({
                'success': False,
                'error': 'Amount must be a number'
            }), 400

        try:
            amount = Decimal(str(data['amount']))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid amount format'
            }), 400

        # Validate amount is positive
        if amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Amount must be positive'
            }), 400

        # Validate maximum transaction limit (₹1 crore)
        MAX_TRANSACTION_AMOUNT = Decimal('10000000.00')  # ₹1 crore
        if amount > MAX_TRANSACTION_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount exceeds maximum transaction limit of ₹{MAX_TRANSACTION_AMOUNT:,.2f}'
            }), 400

        # Validate minimum transaction (prevent dust transactions)
        MIN_TRANSACTION_AMOUNT = Decimal('1.00')  # ₹1
        if amount < MIN_TRANSACTION_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount must be at least ₹{MIN_TRANSACTION_AMOUNT}'
            }), 400
        
        # Get recipient IDX (from nickname or direct IDX)
        from database.models.recipient import Recipient
        from database.models.session import Session

        recipient_idx = None
        if 'recipient_nickname' in data:
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

            recipient_idx = recipient.recipient_idx

        elif 'recipient_idx' in data:
            recipient_idx = data['recipient_idx']

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

        # Get current session IDs (internal mapping - users never see this)
        sender_session = db.query(Session).filter(
            Session.user_idx == current_user.idx,
            Session.bank_account_id == data['sender_account_id'],
            Session.is_active == True
        ).first()

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

        # Create transaction (using sessions internally but user provided IDX)
        service = TransactionServiceV2(db)
        transaction = service.create_transaction(
            sender_account_id=data['sender_account_id'],
            recipient_idx=recipient_idx,  # Changed from nickname to idx
            amount=amount,
            sender_session_id=sender_session.session_id,  # Mapped internally
            receiver_session_id=receiver_session.session_id  # Mapped internally
        )

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
        data = request.get_json()
        
        if not data.get('receiver_account_id'):
            return jsonify({
                'success': False,
                'error': 'receiver_account_id is required'
            }), 400
        
        # Verify receiver owns the account
        receiver_account = db.query(BankAccount).filter(
            BankAccount.id == data['receiver_account_id']
        ).first()
        
        if not receiver_account or receiver_account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Invalid receiver account'
            }), 400
        
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
        # Only allow users to view their own history
        if idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get transactions
        from database.models.recipient import Recipient
        from database.models.bank_account import BankAccount

        transactions = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()

        total = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).count()

        # Build user-friendly response (IDX level, not sessions)
        result = []
        for tx in transactions:
            # Determine direction
            if tx.sender_idx == idx:
                direction = "sent"
                counterparty_idx = tx.receiver_idx
                my_account_id = tx.sender_account_id
            else:
                direction = "received"
                counterparty_idx = tx.sender_idx
                my_account_id = tx.receiver_account_id

            # Look up nickname from recipients list
            recipient = db.query(Recipient).filter(
                Recipient.user_idx == idx,
                Recipient.recipient_idx == counterparty_idx
            ).first()

            counterparty_nickname = recipient.nickname if recipient else None

            # Get bank account details
            account = db.query(BankAccount).get(my_account_id) if my_account_id else None
            bank_account_str = f"{account.bank_code}-{account.account_number}" if account else None

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
        transaction = db.query(Transaction).filter(
            Transaction.transaction_hash == tx_hash
        ).first()
        
        if not transaction:
            return jsonify({
                'success': False,
                'error': 'Transaction not found'
            }), 404
        
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


# Add missing import at top of file
from database.models.bank_account import BankAccount