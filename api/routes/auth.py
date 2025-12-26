"""
Authentication Routes
Author: Ashutosh Rajesh
Purpose: Login and registration endpoints

Endpoints:
- POST /api/auth/login - User login
- POST /api/auth/register - New user registration
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from database.connection import SessionLocal
from database.models.user import User
from database.models.session import Session as UserSession
from core.crypto.idx_generator import IDXGenerator
from core.crypto.session_id import SessionIDGenerator
from api.middleware.auth import AuthMiddleware
from api.middleware.rate_limiter import limiter, get_rate_limit

# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('auth_register'))
def register():
    """
    Register new user
    
    Request:
    {
        "pan_card": "ABCDE1234F",
        "rbi_number": "123456",
        "full_name": "John Doe",
        "initial_balance": 10000.00
    }
    
    Response:
    {
        "success": true,
        "user": {
            "idx": "IDX_abc123...",
            "full_name": "John Doe",
            "balance": "10000.00"
        }
    }
    """
    db = SessionLocal()
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['pan_card', 'rbi_number', 'full_name']
        missing = [f for f in required if f not in data]
        
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing fields: {", ".join(missing)}'
            }), 400

        # Generate IDX
        idx = IDXGenerator.generate(data['pan_card'], data['rbi_number'])

        # Create user (no pre-check - let database enforce uniqueness)
        user = User(
            idx=idx,
            pan_card=data['pan_card'],
            full_name=data['full_name'],
            balance=Decimal(str(data.get('initial_balance', 0)))
        )

        db.add(user)
        db.commit()  # This will raise IntegrityError if duplicate
        db.refresh(user)

        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'user': {
                'idx': user.idx,
                'full_name': user.full_name,
                'balance': str(user.balance)
            }
        }), 201

    except IntegrityError as e:
        db.rollback()
        # Check which constraint was violated
        error_msg = str(e.orig)

        if 'pan_card' in error_msg or 'users_pan_card_key' in error_msg:
            return jsonify({
                'success': False,
                'error': 'User with this PAN card already exists'
            }), 409
        elif 'idx' in error_msg or 'users_idx_key' in error_msg:
            return jsonify({
                'success': False,
                'error': 'IDX collision detected (extremely rare - please retry)'
            }), 409
        else:
            return jsonify({
                'success': False,
                'error': 'Database constraint violation'
            }), 409

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': f'Registration failed: {str(e)}'
        }), 500
        
    finally:
        db.close()


@auth_bp.route('/login', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('auth_login'))
def login():
    """
    User login
    
    Request:
    {
        "pan_card": "ABCDE1234F",
        "rbi_number": "123456",
        "bank_name": "HDFC"
    }
    
    Response:
    {
        "success": true,
        "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "user": {
            "idx": "IDX_abc123...",
            "full_name": "John Doe",
            "balance": "10000.00"
        },
        "session": {
            "session_id": "SESSION_xyz...",
            "expires_at": "2025-12-23T10:00:00"
        }
    }
    """
    db = SessionLocal()
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['pan_card', 'rbi_number', 'bank_name']
        missing = [f for f in required if f not in data]
        
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing fields: {", ".join(missing)}'
            }), 400
        
        # Generate IDX to find user
        idx = IDXGenerator.generate(data['pan_card'], data['rbi_number'])
        
        # Find user
        user = db.query(User).filter(User.idx == idx).first()
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401
        
        # Create or get session
        existing_session = db.query(UserSession).filter(
            UserSession.user_idx == user.idx,
            UserSession.bank_name == data['bank_name'],
            UserSession.is_active == True
        ).first()
        
        if existing_session and not existing_session.is_expired():
            # Use existing session
            session = existing_session
        else:
            # Create new session
            sess_id, expiry = SessionIDGenerator.generate(user.idx, data['bank_name'])
            session = UserSession(
                session_id=sess_id,
                user_idx=user.idx,
                bank_name=data['bank_name'],
                expires_at=expiry
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        
        # Generate JWT token
        token = AuthMiddleware.generate_token(user.idx, data['bank_name'])
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': {
                'idx': user.idx,
                'full_name': user.full_name,
                'balance': str(user.balance)
            },
            'session': {
                'session_id': session.session_id,
                'bank_name': session.bank_name,
                'expires_at': session.expires_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        }), 500
        
    finally:
        db.close()


# Testing
if __name__ == "__main__":
    from flask import Flask
    
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    
    print("=== Auth Routes Testing ===")
    print("Starting Flask server on http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  POST /api/auth/register")
    print("  POST /api/auth/login")
    print("\nTest with curl:")
    print('  curl -X POST http://localhost:5000/api/auth/register \\')
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"pan_card":"TEST1234A","rbi_number":"100001","full_name":"Test User","initial_balance":10000}\'')
    
    app.run(debug=True, port=5000)