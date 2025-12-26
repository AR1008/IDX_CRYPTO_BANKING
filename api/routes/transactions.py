"""
Transactions API Routes - V2 with Receiver Confirmation
Author: Ashutosh Rajesh
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
    Create transaction (sender initiates)
    
    Request body:
        {
            "sender_account_id": 2,
            "recipient_nickname": "Friend",
            "amount": 1000.00,
            "sender_session_id": "SESSION_..."
        }
    
    Returns:
        JSON: {success: true, transaction: {...}, status: "awaiting_receiver"}
    """
    try:
        data = request.get_json()
        
        # Validate
        required = ['sender_account_id', 'recipient_nickname', 'amount', 'sender_session_id']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
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
        
        # Create transaction
        service = TransactionServiceV2(db)
        transaction = service.create_transaction(
            sender_account_id=data['sender_account_id'],
            recipient_nickname=data['recipient_nickname'],
            amount=amount,
            sender_session_id=data['sender_session_id']
        )
        
        return jsonify({
            'success': True,
            'message': 'Transaction created. Awaiting receiver confirmation.',
            'transaction': transaction.to_dict(),
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
    Get transaction history for user
    
    Query params:
        limit: int (default: 50)
        offset: int (default: 0)
    
    Returns:
        JSON: {success: true, transactions: [...]}
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
        transactions = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()
        
        total = db.query(Transaction).filter(
            (Transaction.sender_idx == idx) | (Transaction.receiver_idx == idx)
        ).count()
        
        return jsonify({
            'success': True,
            'transactions': [tx.to_dict() for tx in transactions],
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