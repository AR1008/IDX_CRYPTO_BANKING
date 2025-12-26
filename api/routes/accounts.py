"""
Accounts Routes
Author: Ashutosh Rajesh
Purpose: User account information endpoints

Endpoints:
- GET /api/accounts/balance - Get current balance (protected)
- GET /api/accounts/info - Get user info (protected)
"""

from flask import Blueprint, jsonify

from api.middleware.auth import require_auth

# Create Blueprint
accounts_bp = Blueprint('accounts', __name__, url_prefix='/api/accounts')


@accounts_bp.route('/balance', methods=['GET'])
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
    return jsonify({
        'success': True,
        'balance': str(current_user.balance),
        'user_idx': current_user.idx,
        'full_name': current_user.full_name
    }), 200


@accounts_bp.route('/info', methods=['GET'])
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
            'idx': current_user.idx,
            'full_name': current_user.full_name,
            'pan_card': current_user.pan_card,
            'balance': str(current_user.balance),
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