"""
Rate Limiter Middleware
Purpose: Prevent abuse and DDoS attacks using Flask-Limiter

Features:
- Per-endpoint rate limits
- Redis-backed storage (distributed rate limiting)
- Automatic IP blocking after threshold
- Violation logging
- Custom error responses

Usage:
    from api.middleware.rate_limiter import limiter, init_rate_limiter

    # In app.py
    init_rate_limiter(app)

    # In routes
    @auth_bp.route('/register', methods=['POST'])
    @limiter.limit(settings.RATE_LIMITS['auth_register'])
    def register():
        ...
"""

from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config.settings import settings
from core.security.ip_blocker import IPBlocker
import time


# Global limiter instance
limiter = None


def get_request_identifier():
    """
    Get identifier for rate limiting

    Uses IP address as primary identifier.
    Can be extended to use user ID for authenticated requests.
    """
    # Get IP address
    ip = get_remote_address()

    # For authenticated requests, could use user ID instead
    # if hasattr(request, 'user_idx'):
    #     return request.user_idx

    return ip


def on_rate_limit_breach(limit_data):
    """
    Called when rate limit is exceeded

    Args:
        limit_data: Information about the limit that was breached

    Returns:
        JSON error response with 429 status
    """
    ip = get_remote_address()
    endpoint = request.endpoint or request.path
    user_agent = request.headers.get('User-Agent', 'Unknown')

    print(f"⚠️  Rate limit exceeded: {ip} → {endpoint}")

    # Log violation
    try:
        IPBlocker.log_violation(
            ip_address=ip,
            endpoint=endpoint,
            user_agent=user_agent,
            request_path=request.full_path
        )

        # Check if should auto-block
        IPBlocker.check_and_auto_block(ip)

    except Exception as e:
        print(f"❌ Error logging violation: {e}")

    # Calculate retry time
    retry_after = int(limit_data.reset_at - time.time())

    # Return error response
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded',
        'message': f'Too many requests. Please try again in {retry_after} seconds.',
        'retry_after': retry_after,
        'limit': str(limit_data.limit),
        'endpoint': endpoint
    }), 429


def check_ip_blocked():
    """
    Check if requesting IP is blocked

    Called before each request to reject blocked IPs.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return None

    ip = get_remote_address()

    # Check if IP is blocked
    if IPBlocker.is_blocked(ip):
        return jsonify({
            'success': False,
            'error': 'Access denied',
            'message': 'Your IP address has been blocked due to suspicious activity.'
        }), 403

    return None


def init_rate_limiter(app):
    """
    Initialize rate limiter with Flask app

    Args:
        app: Flask application instance
    """
    global limiter

    if not settings.RATE_LIMIT_ENABLED:
        print("⚠️  Rate limiting is DISABLED")
        # Create a no-op limiter
        limiter = Limiter(
            app=app,
            key_func=get_request_identifier,
            enabled=False
        )
        return limiter

    print("✅ Initializing rate limiter...")
    print(f"   Storage: {settings.RATE_LIMIT_STORAGE_URL}")
    print(f"   Default limit: {settings.RATE_LIMITS.get('default', 'N/A')}")

    # Initialize Flask-Limiter
    limiter = Limiter(
        app=app,
        key_func=get_request_identifier,
        storage_uri=settings.RATE_LIMIT_STORAGE_URL,
        default_limits=[settings.RATE_LIMITS.get('default', '1000 per hour')],
        headers_enabled=True,  # Return X-RateLimit-* headers
        on_breach=on_rate_limit_breach,
        storage_options={"socket_connect_timeout": 30}
    )

    # Register before_request handler to check blocked IPs
    @app.before_request
    def before_request_check_ip():
        return check_ip_blocked()

    print(f"✅ Rate limiter initialized successfully")

    return limiter


# Helper function to get rate limit for an endpoint
def get_rate_limit(endpoint_name: str) -> str:
    """
    Get rate limit string for an endpoint

    Args:
        endpoint_name: Name of endpoint (e.g., 'auth_register')

    Returns:
        Rate limit string (e.g., '10 per hour')
    """
    return settings.RATE_LIMITS.get(endpoint_name, settings.RATE_LIMITS.get('default', '1000 per hour'))


# Export limiter instance and init function
__all__ = ['limiter', 'init_rate_limiter', 'get_rate_limit']


# For testing
if __name__ == "__main__":
    from flask import Flask

    print("=== Rate Limiter Test ===\n")

    # Create test app
    app = Flask(__name__)

    # Initialize rate limiter
    init_rate_limiter(app)

    @app.route('/test')
    @limiter.limit("5 per minute")
    def test_route():
        return jsonify({'success': True, 'message': 'Test endpoint'})

    print("\n✅ Rate limiter middleware created successfully!")
    print("\nTo test:")
    print("1. Start the Flask app")
    print("2. Make 6+ requests to /test within 1 minute")
    print("3. 6th request should return 429 (rate limit exceeded)")
