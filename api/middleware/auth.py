"""
JWT Authentication Middleware
Author: Ashutosh Rajesh
Purpose: Protect API endpoints with JWT tokens

Flow:
1. User logs in → Gets JWT token
2. User makes request with token in header
3. Middleware validates token
4. If valid → Allow request
5. If invalid → Return 401 Unauthorized
"""

from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

from config.settings import settings
from database.connection import SessionLocal
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
        payload = {
            'user_idx': user_idx,
            'bank_name': bank_name,
            'exp': datetime.utcnow() + timedelta(hours=24),
            'iat': datetime.utcnow()
        }
        
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
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=['HS256']
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError:
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({
                'success': False,
                'error': 'No authorization header provided'
            }), 401
        
        # Extract token (format: "Bearer <token>")
        try:
            token = auth_header.split(' ')[1]
        except IndexError:
            return jsonify({
                'success': False,
                'error': 'Invalid authorization header format. Use: Bearer <token>'
            }), 401
        
        # Verify token
        try:
            payload = AuthMiddleware.verify_token(token)
        except jwt.InvalidTokenError as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 401
        
        # Get user from database
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.idx == payload['user_idx']).first()
            
            if not user:
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 401
            
            # Add user and db to kwargs
            kwargs['current_user'] = user
            kwargs['db'] = db
            
            return f(*args, **kwargs)
            
        finally:
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