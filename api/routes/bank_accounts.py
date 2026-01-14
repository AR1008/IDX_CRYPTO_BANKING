"""
Bank Accounts API Routes
Purpose: Manage user's multiple bank accounts

Endpoints:
- GET /api/bank-accounts - Get all user's accounts (homepage)
- GET /api/bank-accounts/summary - Account summary with total balance
- POST /api/bank-accounts/create - Create new bank account
- GET /api/bank-accounts/{bank_code} - Get specific bank account
- POST /api/bank-accounts/{account_id}/freeze - Freeze account (admin)
- POST /api/bank-accounts/{account_id}/unfreeze - Unfreeze account (admin)
"""

from flask import Blueprint, request, jsonify
from decimal import Decimal

from api.middleware.auth import require_auth
from core.services.bank_account_service import BankAccountService


bank_accounts_bp = Blueprint('bank_accounts', __name__, url_prefix='/api/bank-accounts')


@bank_accounts_bp.route('', methods=['GET'])
@require_auth
def get_all_accounts(current_user, db):
    """
    Get all bank accounts for logged-in user (HOMEPAGE)
    
    Returns:
        JSON: {
            success: true,
            accounts: [
                {bank_code, account_number, balance, is_frozen},
                ...
            ]
        }
    """
    try:
        service = BankAccountService(db)
        accounts = service.get_user_accounts(current_user.idx)
        
        return jsonify({
            'success': True,
            'accounts': [acc.to_dict() for acc in accounts]
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bank_accounts_bp.route('/summary', methods=['GET'])
@require_auth
def get_account_summary(current_user, db):
    """
    Get account summary (HOMEPAGE OVERVIEW)
    
    Returns:
        JSON: {
            success: true,
            total_balance: "85000.00",
            accounts: [...],
            account_count: 3
        }
    """
    try:
        service = BankAccountService(db)
        summary = service.get_account_summary(current_user.idx)
        
        return jsonify({
            'success': True,
            **summary
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bank_accounts_bp.route('/create', methods=['POST'])
@require_auth
def create_account(current_user, db):
    """
    Create new bank account
    
    Request body:
        {
            "bank_code": "ICICI",
            "initial_balance": 10000.00  (optional)
        }
    
    Returns:
        JSON: {success: true, account: {...}}
    """
    try:
        data = request.get_json()
        
        # Validate
        if not data.get('bank_code'):
            return jsonify({
                'success': False,
                'error': 'bank_code is required'
            }), 400
        
        bank_code = data['bank_code'].upper()
        initial_balance = Decimal(str(data.get('initial_balance', 0)))
        
        # Create account
        service = BankAccountService(db)
        account = service.create_account(
            current_user.idx,
            bank_code,
            initial_balance
        )
        
        return jsonify({
            'success': True,
            'message': f'{bank_code} account created successfully',
            'account': account.to_dict()
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


@bank_accounts_bp.route('/<string:bank_code>', methods=['GET'])
@require_auth
def get_account_by_bank(current_user, db, bank_code):
    """
    Get specific bank account
    
    URL: /api/bank-accounts/HDFC
    
    Returns:
        JSON: {success: true, account: {...}}
    """
    try:
        service = BankAccountService(db)
        account = service.get_account_by_bank(current_user.idx, bank_code.upper())
        
        if not account:
            return jsonify({
                'success': False,
                'error': f'No {bank_code} account found'
            }), 404
        
        return jsonify({
            'success': True,
            'account': account.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bank_accounts_bp.route('/<int:account_id>/freeze', methods=['POST'])
@require_auth
def freeze_account(current_user, db, account_id):
    """
    Freeze account (ADMIN/COURT ORDER)
    
    Request body:
        {
            "reason": "Court order #12345"
        }
    
    Returns:
        JSON: {success: true, account: {...}}
    """
    try:
        data = request.get_json()
        reason = data.get('reason', 'Administrative action')
        
        service = BankAccountService(db)
        account = service.freeze_account(account_id, reason)
        
        return jsonify({
            'success': True,
            'message': f'Account {account.account_number} frozen',
            'account': account.to_dict()
        }), 200
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bank_accounts_bp.route('/<int:account_id>/unfreeze', methods=['POST'])
@require_auth
def unfreeze_account(current_user, db, account_id):
    """
    Unfreeze account
    
    Returns:
        JSON: {success: true, account: {...}}
    """
    try:
        service = BankAccountService(db)
        account = service.unfreeze_account(account_id)
        
        return jsonify({
            'success': True,
            'message': f'Account {account.account_number} unfrozen',
            'account': account.to_dict()
        }), 200
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500