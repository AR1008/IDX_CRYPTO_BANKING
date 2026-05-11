"""
Authentication Routes
Purpose: Login and registration endpoints

Endpoints:
- POST /api/auth/login - User login
- POST /api/auth/register - New user registration
"""

# [DOC] Decimal is used for monetary balances — avoids floating-point rounding errors
from decimal import Decimal
# [DOC] Blueprint groups these routes under a shared prefix; request provides HTTP request data; jsonify converts dicts to JSON responses
from flask import Blueprint, request, jsonify
# [DOC] IntegrityError is raised by SQLAlchemy when a UNIQUE constraint is violated (e.g. duplicate PAN card or IDX)
from sqlalchemy.exc import IntegrityError

# [DOC] SessionLocal creates a new database connection (session) for each request
from database.connection import SessionLocal
# [DOC] User is the ORM model for the users table — one row per registered person
from database.models.user import User
# [DOC] Session (aliased UserSession) is the ORM model for the rotating 24-hour session IDs (Layer 1 identity)
from database.models.session import Session as UserSession
# [DOC] IDXGenerator derives the permanent pseudonym IDX = SHA256(national_id + authority_id + APPLICATION_PEPPER)
from core.crypto.idx_generator import IDXGenerator
# [DOC] SessionIDGenerator creates a new time-stamped session ID: SESSION_{bank}_{SHA256(idx:bank:date)}
from core.crypto.session_id import SessionIDGenerator
# [DOC] AuthMiddleware contains generate_token() (creates JWT) and decode_token() (validates JWT)
from api.middleware.auth import AuthMiddleware
# [DOC] limiter enforces per-endpoint request rate limits; get_rate_limit fetches the configured rule from settings
from api.middleware.rate_limiter import limiter, get_rate_limit

# [DOC] All routes in this blueprint are served under /api/auth (e.g. /api/auth/login)
# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
# [DOC] Rate-limit registration to 10 requests per hour — prevents mass automated account creation
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
    # [DOC] Open a fresh DB session for this request; closed in the finally block regardless of success or failure
    db = SessionLocal()

    try:
        # [DOC] Parse the JSON body — pan_card and rbi_number together uniquely identify the person in the IDX scheme
        data = request.get_json()

        # [DOC] Check for each mandatory field and collect missing ones into a list for a helpful error message
        # Validate required fields
        required = ['pan_card', 'rbi_number', 'full_name']
        missing = [f for f in required if f not in data]

        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing fields: {", ".join(missing)}'
            }), 400

        # [DOC] Derive the IDX by hashing (pan_card + rbi_number + APPLICATION_PEPPER) — deterministic, so same inputs always give same IDX
        # Generate IDX
        idx = IDXGenerator.generate(data['pan_card'], data['rbi_number'])

        # [DOC] Build the User ORM object without querying first — the DB UNIQUE constraint prevents duplicates more efficiently
        # Create user (no pre-check - let database enforce uniqueness)
        user = User(
            idx=idx,
            pan_card=data['pan_card'],
            full_name=data['full_name'],
            # [DOC] Convert initial_balance to Decimal via str() to avoid float precision loss
            balance=Decimal(str(data.get('initial_balance', 0)))
        )

        db.add(user)
        # [DOC] db.commit() sends the INSERT to PostgreSQL; if idx or pan_card already exists it raises IntegrityError
        db.commit()  # This will raise IntegrityError if duplicate
        # [DOC] db.refresh(user) re-reads the row from the DB so auto-generated fields (e.g. created_at) are populated
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
        # [DOC] Rollback the failed transaction so the DB session is clean for subsequent requests
        db.rollback()
        # [DOC] Inspect the DB error message to give the caller a specific reason for the conflict
        # Check which constraint was violated
        error_msg = str(e.orig)

        if 'pan_card' in error_msg or 'users_pan_card_key' in error_msg:
            return jsonify({
                'success': False,
                'error': 'User with this PAN card already exists'
            }), 409
        elif 'idx' in error_msg or 'users_idx_key' in error_msg:
            # [DOC] IDX collision is cryptographically negligible but handled gracefully — user can retry
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
        # [DOC] Always close the session — returns the connection to the pool and prevents connection leaks
        db.close()


@auth_bp.route('/login', methods=['POST'])
# [DOC] Rate-limit logins to 20 per hour per IP — slows automated brute-force password attacks
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
    # [DOC] Open a new DB session for this login request
    db = SessionLocal()

    try:
        # [DOC] Parse the request body — pan_card + rbi_number recreate the IDX; bank_name identifies which bank session to use
        data = request.get_json()

        # [DOC] Validate all three required fields are present before doing any DB work
        # Validate required fields
        required = ['pan_card', 'rbi_number', 'bank_name']
        missing = [f for f in required if f not in data]

        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing fields: {", ".join(missing)}'
            }), 400

        # [DOC] Re-derive the IDX from the credentials — the IDX is never stored in plain text, only derived on demand
        # Generate IDX to find user
        idx = IDXGenerator.generate(data['pan_card'], data['rbi_number'])

        # [DOC] Look up the user by their derived IDX — if not found, return a generic "Invalid credentials" (no info leak)
        # Find user
        user = db.query(User).filter(User.idx == idx).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401

        # [DOC] Check if the user already has a non-expired active session for this bank — reuse it to avoid unnecessary rotation
        # Create or get session
        existing_session = db.query(UserSession).filter(
            UserSession.user_idx == user.idx,
            UserSession.bank_name == data['bank_name'],
            UserSession.is_active == True
        ).first()

        if existing_session and not existing_session.is_expired():
            # [DOC] Reuse the existing session — its 24h expiry clock is NOT reset, maintaining the rotation schedule
            # Use existing session
            session = existing_session
        else:
            # [DOC] Generate a fresh session ID: SESSION_{bank}_{SHA256(idx:bank:today's_date)}
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

        # [DOC] generate_token() signs a JWT containing the user's IDX and bank name; expires in JWT_EXPIRATION_MINUTES (15 min)
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
                # [DOC] The session_id is the Layer 1 public identifier — visible on the blockchain but not linked to real identity
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
        # [DOC] Close the DB session so the connection is returned to the pool
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
