# [DOC] JWT Authentication Middleware
# [DOC] Every protected Flask route calls @require_auth, which runs this code before the route handler.
# [DOC] Purpose: prove the caller is a logged-in user and identify which user they are.

"""
JWT Authentication Middleware
Purpose: Protect API endpoints with JWT tokens

Flow:
1. User logs in → Gets JWT token
2. User makes request with token in header
3. Middleware validates token
4. If valid → Allow request
5. If invalid → Return 401 Unauthorized
"""

# [DOC] functools.wraps preserves the original function name/docstring when we wrap it with a decorator.
from functools import wraps
# [DOC] Flask's request object holds the current HTTP request; jsonify converts dicts to JSON responses.
from flask import request, jsonify
# [DOC] PyJWT library: encodes and decodes JSON Web Tokens.
import jwt
# [DOC] datetime and timedelta are used to set and compute the token expiry timestamp.
from datetime import datetime, timedelta

# [DOC] settings holds all config values (JWT_SECRET_KEY, token expiry, etc.) from environment variables.
from config.settings import settings
# [DOC] SessionLocal creates a new database session (connection) for each request.
from database.connection import SessionLocal
# [DOC] User is the SQLAlchemy ORM model for the users table.
from database.models.user import User


class AuthMiddleware:
    """JWT authentication middleware"""

    @staticmethod
    def generate_token(user_idx: str, bank_name: str) -> str:
        """
        Generate JWT token for user

        Args:
            user_idx: User's permanent IDX
            bank_name: Bank user logged into

        Returns:
            JWT token string

        Example:
            >>> token = AuthMiddleware.generate_token("IDX_abc123", "HDFC")
            >>> print(token)
            "eyJ0eXAiOiJKV1QiLCJhbGc..."
        """
        # [DOC] The payload is the claims dict embedded in the token — anyone who decodes the token can read these.
        payload = {
            'user_idx': user_idx,       # [DOC] Permanent pseudonym — used to look up the user in the DB.
            'bank_name': bank_name,     # [DOC] Which bank this session is scoped to.
            'exp': datetime.utcnow() + timedelta(hours=24),  # [DOC] Token expires 24 hours from now; after this, verification fails automatically.
            'iat': datetime.utcnow()    # [DOC] "Issued at" timestamp — useful for auditing when the token was created.
        }

        # [DOC] jwt.encode() signs the payload with the secret key using HMAC-SHA256 (HS256).
        # [DOC] Only parties who know settings.JWT_SECRET_KEY can verify or forge a token.
        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm='HS256'
        )

        return token

    @staticmethod
    def verify_token(token: str) -> dict:
        """
        Verify JWT token

        Args:
            token: JWT token string

        Returns:
            dict: Decoded payload with user_idx, bank_name, exp, iat

        Raises:
            jwt.InvalidTokenError: If token invalid/expired

        Example:
            >>> payload = AuthMiddleware.verify_token(token)
            >>> print(payload['user_idx'])
            "IDX_abc123"
        """
        try:
            # [DOC] jwt.decode() verifies the HMAC signature and checks that 'exp' hasn't passed.
            # [DOC] If either check fails it raises an exception — we never get the payload back.
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=['HS256']   # [DOC] Whitelist only HS256; prevents algorithm-confusion attacks (e.g., alg=none).
            )
            return payload
        except jwt.ExpiredSignatureError:
            # [DOC] Token existed and was valid, but the 'exp' claim is in the past.
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError:
            # [DOC] Token is malformed, has a bad signature, or some other structural problem.
            raise jwt.InvalidTokenError("Invalid token")


def require_auth(f):
    """
    Decorator to protect endpoints with JWT authentication

    Usage:
        @app.route('/api/balance')
        @require_auth
        def get_balance(current_user, db):
            return jsonify({'balance': str(current_user.balance)})

    The decorator automatically adds:
        - current_user: User object from database
        - db: Database session

    Returns 401 if:
        - No Authorization header
        - Invalid token format
        - Token expired
        - User not found
    """
    # [DOC] @wraps(f) copies the wrapped function's __name__ and __doc__ so Flask routing and debugging work correctly.
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # [DOC] Every HTTP request must include: "Authorization: Bearer <token>".
        # [DOC] request.headers is a dict-like object of all HTTP headers sent by the client.
        auth_header = request.headers.get('Authorization')

        # [DOC] If the header is missing entirely, reject immediately with HTTP 401 Unauthorized.
        if not auth_header:
            return jsonify({
                'success': False,
                'error': 'No authorization header provided'
            }), 401

        # [DOC] The header format is "Bearer <token>"; split on space and grab the second part.
        try:
            token = auth_header.split(' ')[1]
        except IndexError:
            # [DOC] split(' ') returned only one element, meaning the header had no space — malformed format.
            return jsonify({
                'success': False,
                'error': 'Invalid authorization header format. Use: Bearer <token>'
            }), 401

        # [DOC] Ask AuthMiddleware to verify the token's signature and expiry.
        try:
            payload = AuthMiddleware.verify_token(token)
        except jwt.InvalidTokenError as e:
            # [DOC] Token was tampered with, expired, or otherwise invalid — do not allow the request.
            return jsonify({
                'success': False,
                'error': str(e)
            }), 401

        # [DOC] Open a DB session to confirm the user identified in the token still exists in the database.
        db = SessionLocal()
        try:
            # [DOC] Query the users table for a row whose idx matches what's in the token payload.
            user = db.query(User).filter(User.idx == payload['user_idx']).first()

            if not user:
                # [DOC] Token was valid but the user was deleted after the token was issued — reject.
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 401

            # [DOC] Inject current_user and db into the route function's keyword arguments.
            # [DOC] This lets every @require_auth route receive the authenticated user without re-querying.
            kwargs['current_user'] = user
            kwargs['db'] = db

            # [DOC] Call the actual route handler now that authentication is confirmed.
            return f(*args, **kwargs)

        finally:
            # [DOC] Always close the DB session — even if the route raised an exception — to release the connection.
            db.close()

    return decorated_function


# Testing
if __name__ == "__main__":
    print("=== JWT Auth Testing ===\n")

    from core.crypto.idx_generator import IDXGenerator

    # Test token generation
    test_idx = IDXGenerator.generate("TEST1234A", "100001")
    token = AuthMiddleware.generate_token(test_idx, "HDFC")

    print(f"Generated token: {token[:50]}...")

    # Test token verification
    try:
        payload = AuthMiddleware.verify_token(token)
        print(f"\n✅ Token verified!")
        print(f"User IDX: {payload['user_idx']}")
        print(f"Bank: {payload['bank_name']}")
        print(f"Expires: {datetime.fromtimestamp(payload['exp'])}")
    except jwt.InvalidTokenError as e:
        print(f"\n❌ Token verification failed: {e}")
