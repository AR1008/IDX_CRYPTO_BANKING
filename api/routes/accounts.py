"""
Accounts Routes
Purpose: User account information endpoints

Endpoints:
- GET /api/accounts/balance - Get current balance (protected)
- GET /api/accounts/info - Get user info (protected)
"""

# [DOC] Blueprint groups related routes under a URL prefix; jsonify converts Python dicts to HTTP JSON responses
from flask import Blueprint, jsonify

# [DOC] require_auth is a decorator that validates the JWT Bearer token and injects (current_user, db) into the route handler
from api.middleware.auth import require_auth

# [DOC] All routes in this blueprint are served under /api/accounts (e.g. /api/accounts/balance)
# Create Blueprint
accounts_bp = Blueprint('accounts', __name__, url_prefix='/api/accounts')


@accounts_bp.route('/balance', methods=['GET'])
# [DOC] require_auth runs before the handler — rejects requests with missing or expired JWT tokens
@require_auth
def get_balance(current_user, db):
    """
    Get user's current balance

    Headers:
        Authorization: Bearer <token>

    Response:
    {
        "success": true,
        "balance": "10000.00",
        "user_idx": "IDX_abc123..."
    }
    """
    # [DOC] current_user is the authenticated User ORM object injected by require_auth — no DB query needed here
    # [DOC] str(current_user.balance) converts the Decimal balance to a plain string for JSON (JSON has no Decimal type)
    return jsonify({
        'success': True,
        'balance': str(current_user.balance),
        # [DOC] Return the IDX (permanent pseudonym), not the real identity — consistent with the three-layer privacy model
        'user_idx': current_user.idx,
        'full_name': current_user.full_name
    }), 200


@accounts_bp.route('/info', methods=['GET'])
# [DOC] require_auth validates the JWT and loads the user from the database before this function runs
@require_auth
def get_user_info(current_user, db):
    """
    Get complete user information

    Headers:
        Authorization: Bearer <token>

    Response:
    {
        "success": true,
        "user": {
            "idx": "IDX_abc123...",
            "full_name": "John Doe",
            "balance": "10000.00",
            "created_at": "2025-12-22T10:00:00"
        }
    }
    """
    return jsonify({
        'success': True,
        'user': {
            # [DOC] idx is the Layer 2 permanent pseudonym — safe to expose to the authenticated user themselves
            'idx': current_user.idx,
            'full_name': current_user.full_name,
            # [DOC] pan_card is the national ID stored in this record — only visible to the account owner via their own JWT
            'pan_card': current_user.pan_card,
            # [DOC] Decimal balance serialised as string to avoid JSON floating-point precision issues
            'balance': str(current_user.balance),
            # [DOC] isoformat() renders the datetime as an ISO 8601 string (e.g. "2025-12-22T10:00:00") — timezone-safe format
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None
        }
    }), 200


# Testing
if __name__ == "__main__":
    from flask import Flask
    from api.routes.auth import auth_bp

    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    app.register_blueprint(accounts_bp)

    print("=== Accounts Routes Testing ===")
    print("1. First register: POST /api/auth/register")
    print("2. Then login: POST /api/auth/login")
    print("3. Use token to access:")
    print("   GET /api/accounts/balance")
    print("   GET /api/accounts/info")

    app.run(debug=True, port=5000)
