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

# [DOC] Blueprint groups these routes under a shared URL prefix; request provides HTTP body data; jsonify builds JSON responses
from flask import Blueprint, request, jsonify
# [DOC] Decimal is used for monetary amounts — avoids the floating-point rounding errors that floats introduce
from decimal import Decimal

# [DOC] require_auth validates the JWT Bearer token and injects (current_user, db) into every decorated route
from api.middleware.auth import require_auth
# [DOC] BankAccountService encapsulates all business logic for creating, listing, and freezing bank accounts
from core.services.bank_account_service import BankAccountService


# [DOC] All routes in this blueprint are served under /api/bank-accounts
bank_accounts_bp = Blueprint('bank_accounts', __name__, url_prefix='/api/bank-accounts')


@bank_accounts_bp.route('', methods=['GET'])
# [DOC] require_auth runs before the handler and rejects unauthenticated requests with HTTP 401
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
        # [DOC] get_user_accounts queries every BankAccount row where user_idx matches the authenticated user's IDX
        service = BankAccountService(db)
        accounts = service.get_user_accounts(current_user.idx)

        # [DOC] to_dict() on each account serialises the ORM object to a plain dict that jsonify can render
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
        # [DOC] get_account_summary computes the sum of all account balances and returns a dict with total + per-account list
        service = BankAccountService(db)
        summary = service.get_account_summary(current_user.idx)

        # [DOC] **summary unpacks the dict returned by get_account_summary into the top-level JSON response
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
        # [DOC] Parse the JSON body to get the bank code and optional initial balance
        data = request.get_json()

        # [DOC] bank_code is mandatory — it identifies which consortium bank hosts this account (e.g. "HDFC", "SBI")
        # Validate
        if not data.get('bank_code'):
            return jsonify({
                'success': False,
                'error': 'bank_code is required'
            }), 400

        # [DOC] Normalise to uppercase so "hdfc" and "HDFC" both map to the same consortium bank record
        bank_code = data['bank_code'].upper()
        # [DOC] Default initial_balance to 0 if not provided; convert via str() before Decimal to avoid float rounding
        initial_balance = Decimal(str(data.get('initial_balance', 0)))

        # [DOC] create_account creates a BankAccount ORM row and generates the initial 24-hour session ID for this account
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
        # [DOC] get_account_by_bank finds the account row for this user + bank combination; returns None if not found
        service = BankAccountService(db)
        # [DOC] upper() normalises the URL parameter so /HDFC and /hdfc behave identically
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
        # [DOC] reason is optional — if not provided defaults to "Administrative action" for audit log clarity
        data = request.get_json()
        reason = data.get('reason', 'Administrative action')

        # [DOC] freeze_account sets is_frozen=True on the BankAccount row and logs the reason in freeze_records
        service = BankAccountService(db)
        account = service.freeze_account(account_id, reason)

        return jsonify({
            'success': True,
            'message': f'Account {account.account_number} frozen',
            'account': account.to_dict()
        }), 200

    except ValueError as e:
        # [DOC] ValueError is raised by freeze_account if the account_id does not exist — return 404
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
        # [DOC] unfreeze_account sets is_frozen=False and records the unfreeze event in freeze_records for audit purposes
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
