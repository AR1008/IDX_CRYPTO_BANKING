"""
Flask Application Factory
Purpose: Flask app with WebSocket support
"""

# [DOC] Flask is the web framework; jsonify converts Python dicts to HTTP JSON responses
from flask import Flask, jsonify
# [DOC] CORS (Cross-Origin Resource Sharing) allows browser JavaScript from other domains to call this API
from flask_cors import CORS
# [DOC] settings holds all configuration values (DB URL, secret keys, allowed origins, etc.)
from config.settings import settings
# [DOC] start_session_rotation launches the background thread that rotates 24-hour session IDs automatically
from core.session.rotation import start_session_rotation
# [DOC] init_websocket attaches Flask-SocketIO to the Flask app, enabling real-time push notifications over WebSocket
from api.websocket.manager import init_websocket
# [DOC] start_mining_worker launches the background thread that polls for approved batches and mines them every 10 seconds
from core.workers.mining_worker import start_mining_worker
# [DOC] IDXGenerator derives a user's permanent pseudonym (IDX) from their national ID + authority ID + pepper
from core.crypto.idx_generator import IDXGenerator
# [DOC] init_rate_limiter wires Flask-Limiter into the app for per-endpoint request throttling
from api.middleware.rate_limiter import init_rate_limiter
# [DOC] start_mining_pool initialises the pool of pre-warmed fork workers used for parallel Bulletproof batch verification
from core.mining.mining_pool import start_mining_pool


def create_app():
    """Create Flask application"""
    # [DOC] Flask(__name__) creates the WSGI application object; __name__ tells Flask where to find templates/static files
    app = Flask(__name__)

    # [DOC] JSON_SORT_KEYS=False keeps dict keys in insertion order in API responses — makes debugging easier
    # Config
    app.config['JSON_SORT_KEYS'] = False
    # [DOC] JSONIFY_PRETTYPRINT_REGULAR=True adds indentation to JSON responses — readable in browsers and curl
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    # [DOC] SECRET_KEY is used by Flask for signing session cookies and other internal security operations
    app.config['SECRET_KEY'] = settings.SECRET_KEY

    # [DOC] CORS restricts which browser origins can send cross-origin requests — only origins in settings.CORS_ORIGINS are allowed
    # [DOC] The r"/*" pattern applies CORS headers to every route in the application
    # [DOC] max_age=3600 tells browsers to cache the preflight OPTIONS response for 1 hour (reduces extra HTTP round-trips)
    # CORS - Restrict to configured origins (SECURITY FIX)
    CORS(app, resources={
        r"/*": {
            "origins": settings.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "max_age": 3600
        }
    })

    # [DOC] Rate limiter MUST be initialized before blueprints are imported — blueprints reference the limiter object at import time
    # Initialize rate limiter (DDoS protection) - MUST BE BEFORE route imports
    init_rate_limiter(app)

    # [DOC] Each blueprint groups related routes into a separate module; importing them here (after limiter init) avoids circular imports
    # Import blueprints AFTER rate limiter is initialized (FIX: prevents limiter=None error)
    from api.routes.transactions import transactions_bp
    from api.routes.auth import auth_bp
    from api.routes.accounts import accounts_bp
    from api.routes.bank_accounts import bank_accounts_bp
    from api.routes.recipients import recipients_bp
    from api.routes.court_orders import court_orders_bp
    from api.routes.travel_accounts import travel_accounts_bp
    from api.routes.mining import mining_bp
    from api.routes.audit import audit_bp
    from api.routes.statements import statements_bp
    from api.routes.admin import admin_bp
    from api.routes.idx_registry import idx_registry_bp
    # [DOC] consensus_bp: inter-bank machine-to-machine voting endpoint (POST /consensus/vote).
    # [DOC] Only active in CONSENSUS_MODE=distributed; harmless but unused in CONSENSUS_MODE=local.
    from api.routes.consensus import consensus_bp

    # [DOC] register_blueprint tells Flask to attach each blueprint's routes to the app under its url_prefix
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(bank_accounts_bp)
    app.register_blueprint(recipients_bp)
    app.register_blueprint(court_orders_bp)
    app.register_blueprint(travel_accounts_bp)
    app.register_blueprint(mining_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(statements_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(idx_registry_bp)
    # [DOC] consensus_bp is always registered; it is only called by peers in CONSENSUS_MODE=distributed.
    app.register_blueprint(consensus_bp)

    # [DOC] start_mining_pool pre-warms a pool of worker processes for parallel Bulletproof batch verification
    # Start mining pool
    start_mining_pool()
    # [DOC] /health returns 200 OK with {"status": "healthy"} — used by load balancers and monitoring to check the server is alive
    # Health check
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy'}), 200

    # [DOC] /test-event is a developer debug endpoint — it pushes a test WebSocket event to every currently connected browser client
    # Test event endpoint
    @app.route('/test-event', methods=['GET'])
    def test_event():
        from api.websocket.manager import manager

        if manager:
            # [DOC] Flatten all per-user socket ID lists into one flat list of active connection IDs
            # Get all connected sids
            all_sids = [sid for sids in manager.users.values() for sid in sids]

            # [DOC] Emit the 'test_event' message to each individual socket session ID (one per browser tab)
            # Emit test event to each
            for sid in all_sids:
                manager.socketio.emit('test_event', {
                    'message': 'Manual test event',
                    'timestamp': str(__import__('datetime').datetime.now())
                }, to=sid)

            return jsonify({
                'success': True,
                'users': len(manager.users),
                'connections': len(all_sids),
                'emitted_to': len(all_sids)
            })

        return jsonify({'success': False, 'error': 'No manager'}), 500

    # [DOC] GET / returns a human-readable API directory — useful for developers discovering the available endpoints
    # Root
    @app.route('/', methods=['GET'])
    def root():
        return jsonify({
            'service': 'IDX Crypto Banking',
            'version': '2.0.0',
            'description': 'Privacy-Preserving Crypto Banking with Three-Layer Identity',
            'endpoints': {
                'auth': 'POST /api/auth/login',
                'balance': 'GET /api/accounts/balance',
                'send': 'POST /api/transactions/send',
                'recipients': 'GET /api/recipients',
                'statements': 'POST /api/statements/generate',
                'admin_access': 'POST /api/admin/access/grant',
                'idx_registry': 'POST /api/idx-registry/lookup',
                'test': 'GET /test-event',
                'websocket': 'ws://localhost:5000'
            },
            'security': {
                'identity_layers': ['Session (Blockchain)', 'IDX (Accounting)', 'Real Name (Restricted)'],
                'access_control': 'Company-controlled with time-limited tokens',
                'audit_trail': 'All access logged'
            }
        }), 200

    # [DOC] 404 handler returns a JSON error body instead of Flask's default HTML page — keeps the API consistent
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    # [DOC] 500 handler catches unhandled exceptions and returns a clean JSON error to the client
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': 'Internal error'}), 500

    return app


def init_miner():
    """Initialize background miner"""
    # [DOC] Open a new database session dedicated to the miner setup — closed in the finally block
    from database.connection import SessionLocal
    from database.models.user import User
    from decimal import Decimal

    db = SessionLocal()
    try:
        # [DOC] Derive a stable IDX for the system miner account using a fixed national ID and authority ID
        miner_idx = IDXGenerator.generate("MINER1234A", "999999")
        # [DOC] Check whether a miner user already exists — avoids creating duplicates on restart
        miner = db.query(User).filter(User.idx == miner_idx).first()

        if not miner:
            # [DOC] Create the miner user record with zero initial balance — fees earned from mining add to this balance
            miner = User(
                idx=miner_idx,
                pan_card="MINER1234A",
                full_name="Background Miner",
                balance=Decimal('0.00')
            )
            db.add(miner)
            db.commit()

        # [DOC] start_mining_worker launches a daemon thread that wakes every 10 seconds and mines any approved batches
        start_mining_worker(miner_idx, interval=10)
        print("✅ Mining worker started")
        # [DOC] start_session_rotation launches a daemon thread that wakes every hour and rotates any expired 24-hour session IDs
        # Start session rotation worker (check every hour)
        start_session_rotation(interval=3600)
        print("✅ Session rotation worker started")

    finally:
        # [DOC] Always close the DB session — prevents connection leaks even if an exception was raised above
        db.close()


if __name__ == '__main__':
    # [DOC] create_app() builds the Flask application with all blueprints and middleware registered
    app = create_app()
    # [DOC] init_websocket(app) wraps the Flask app with Flask-SocketIO, enabling ws:// connections on the same port
    socketio = init_websocket(app)

    # [DOC] init_miner() creates the miner account and starts the two background daemon threads (miner + session rotator)
    init_miner()

    print("=" * 60)
    print("🚀 IDX Crypto Banking - Full Stack")
    print("=" * 60)
    print("\n📍 HTTP API: http://localhost:5000")
    print("📍 WebSocket: ws://localhost:5000")
    print("\n📋 Quick Test:")
    print("  1. Open: tests/manual/websocket_client.html")
    print("  2. Login: curl -X POST http://localhost:5000/api/auth/login \\")
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"pan_card":"TESTK1234A","rbi_number":"100001","bank_name":"HDFC"}\'')
    print("  3. Paste token in browser, click Connect")
    print("  4. Test: curl http://localhost:5000/test-event")
    print("\n" + "=" * 60)
    print("Press CTRL+C to stop")
    print("=" * 60 + "\n")

    # [DOC] socketio.run() starts the combined HTTP + WebSocket server; allow_unsafe_werkzeug=True is required in dev mode with SocketIO
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
