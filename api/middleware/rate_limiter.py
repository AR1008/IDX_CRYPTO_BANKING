# [DOC] Rate Limiter Middleware
# [DOC] Protects every API endpoint from being called too many times in a short window.
# [DOC] Two layers of defence: Flask-Limiter (per-window counter) + IPBlocker (persistent DB ban).

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

# [DOC] Flask's request gives us the current request; jsonify converts a dict to a JSON HTTP response.
from flask import request, jsonify
# [DOC] Flask-Limiter provides the @limiter.limit() decorator and the counting logic.
from flask_limiter import Limiter
# [DOC] get_remote_address is a helper that extracts the client's IP from the request.
from flask_limiter.util import get_remote_address
# [DOC] settings holds RATE_LIMIT_ENABLED, RATE_LIMIT_STORAGE_URL, and the RATE_LIMITS dict.
from config.settings import settings
# [DOC] IPBlocker writes to the blocked_ips table and bans repeat offenders at the DB level.
from core.security.ip_blocker import IPBlocker
# [DOC] time.time() returns the current Unix timestamp (seconds since epoch), used to compute retry-after.
import time


# [DOC] A global variable so every route module can import the same limiter instance.
# [DOC] Initialised as a no-op so import order doesn't matter — real limiter is installed by init_rate_limiter().
class NoOpLimiter:
    """No-op limiter for when rate limiting is disabled or not yet initialized"""
    def limit(self, *args, **kwargs):
        """Decorator that does nothing"""
        # [DOC] Returns the function unchanged — effectively bypasses rate limiting.
        def decorator(f):
            return f
        return decorator

# [DOC] Module-level singleton; replaced by the real Limiter object when init_rate_limiter() is called.
limiter = NoOpLimiter()


def get_request_identifier():
    """
    Get identifier for rate limiting

    Uses IP address as primary identifier.
    Can be extended to use user ID for authenticated requests.
    """
    # [DOC] get_remote_address() reads REMOTE_ADDR (or X-Forwarded-For if behind a proxy).
    ip = get_remote_address()

    # For authenticated requests, could use user ID instead
    # if hasattr(request, 'user_idx'):
    #     return request.user_idx

    # [DOC] Returning the IP means every IP gets its own counter bucket.
    return ip


def on_rate_limit_breach(limit_data):
    """
    Called when rate limit is exceeded

    Args:
        limit_data: Information about the limit that was breached

    Returns:
        JSON error response with 429 status
    """
    # [DOC] Read the offending IP and the endpoint name for logging.
    ip = get_remote_address()
    endpoint = request.endpoint or request.path
    user_agent = request.headers.get('User-Agent', 'Unknown')

    print(f"⚠️  Rate limit exceeded: {ip} → {endpoint}")

    # [DOC] Log the violation to the rate_limit_violations table so we can count repeat offenders.
    try:
        IPBlocker.log_violation(
            ip_address=ip,
            endpoint=endpoint,
            user_agent=user_agent,
            request_path=request.full_path
        )

        # [DOC] If this IP has accumulated enough violations, permanently block it in the DB.
        IPBlocker.check_and_auto_block(ip)

    except Exception as e:
        print(f"❌ Error logging violation: {e}")

    # [DOC] limit_data.reset_at is the Unix timestamp when the window resets; subtract now to get seconds left.
    retry_after = int(limit_data.reset_at - time.time())

    # [DOC] HTTP 429 = "Too Many Requests"; include Retry-After seconds so the client knows when to retry.
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
    # [DOC] If rate limiting is globally disabled (e.g. in test environment), skip this check.
    if not settings.RATE_LIMIT_ENABLED:
        return None

    ip = get_remote_address()

    # [DOC] Query the blocked_ips table; if the row exists and hasn't expired, return 403 Forbidden.
    if IPBlocker.is_blocked(ip):
        return jsonify({
            'success': False,
            'error': 'Access denied',
            'message': 'Your IP address has been blocked due to suspicious activity.'
        }), 403

    # [DOC] Returning None tells Flask to continue processing the request normally.
    return None


def init_rate_limiter(app):
    """
    Initialize rate limiter with Flask app

    Args:
        app: Flask application instance
    """
    # [DOC] The global keyword lets us replace the module-level NoOpLimiter with the real Limiter.
    global limiter

    # [DOC] If rate limiting is turned off in config, install a disabled Limiter (still satisfies imports).
    if not settings.RATE_LIMIT_ENABLED:
        print("⚠️  Rate limiting is DISABLED")
        limiter = Limiter(
            app=app,
            key_func=get_request_identifier,
            enabled=False   # [DOC] enabled=False makes every @limiter.limit() decorator a no-op.
        )
        return limiter

    print("✅ Initializing rate limiter...")
    print(f"   Storage: {settings.RATE_LIMIT_STORAGE_URL}")
    print(f"   Default limit: {settings.RATE_LIMITS.get('default', 'N/A')}")

    # [DOC] Create the real Limiter; storage_uri points to Redis (or memory:// for dev).
    # [DOC] Redis allows multiple API server instances to share the same counters.
    limiter = Limiter(
        app=app,
        key_func=get_request_identifier,           # [DOC] Use IP as the bucket key.
        storage_uri=settings.RATE_LIMIT_STORAGE_URL,
        default_limits=[settings.RATE_LIMITS.get('default', '1000 per hour')],  # [DOC] Fallback limit for any route without an explicit @limiter.limit().
        headers_enabled=True,                      # [DOC] Adds X-RateLimit-Limit/Remaining/Reset headers to every response.
        on_breach=on_rate_limit_breach,            # [DOC] Call our custom handler (instead of Flask-Limiter's default) when a limit is hit.
        storage_options={"socket_connect_timeout": 30}  # [DOC] Give Redis 30 seconds to connect before giving up.
    )

    # [DOC] @app.before_request runs our function before every single route handler — ideal for IP blocking.
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
    # [DOC] Look up the endpoint-specific limit; fall back to the global default if not found.
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
