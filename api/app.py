"""
Flask Application Factory
Author: Ashutosh Rajesh
Purpose: Flask app with WebSocket support
"""

from flask import Flask, jsonify
from flask_cors import CORS
from config.settings import settings
from core.session.rotation import start_session_rotation
from api.websocket.manager import init_websocket
from core.workers.mining_worker import start_mining_worker
from core.crypto.idx_generator import IDXGenerator
from api.middleware.rate_limiter import init_rate_limiter
from core.mining.mining_pool import start_mining_pool


def create_app():
    """Create Flask application"""
    app = Flask(__name__)

    # Config
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    app.config['SECRET_KEY'] = settings.SECRET_KEY

    # CORS - Restrict to configured origins (SECURITY FIX)
    CORS(app, resources={
        r"/*": {
            "origins": settings.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "max_age": 3600
        }
    })

    # Initialize rate limiter (DDoS protection) - MUST BE BEFORE route imports
    init_rate_limiter(app)

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

    # Start mining pool
    start_mining_pool()
    # Health check
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy'}), 200
    
    # Test event endpoint
    @app.route('/test-event', methods=['GET'])
    def test_event():
        from api.websocket.manager import manager
        
        if manager:
            # Get all connected sids
            all_sids = [sid for sids in manager.users.values() for sid in sids]
            
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
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': 'Internal error'}), 500
    
    return app


def init_miner():
    """Initialize background miner"""
    from database.connection import SessionLocal
    from database.models.user import User
    from decimal import Decimal
    
    db = SessionLocal()
    try:
        miner_idx = IDXGenerator.generate("MINER1234A", "999999")
        miner = db.query(User).filter(User.idx == miner_idx).first()
        
        if not miner:
            miner = User(
                idx=miner_idx,
                pan_card="MINER1234A",
                full_name="Background Miner",
                balance=Decimal('0.00')
            )
            db.add(miner)
            db.commit()
        
        start_mining_worker(miner_idx, interval=10)
        print("✅ Mining worker started")
        # Start session rotation worker (check every hour)
        start_session_rotation(interval=3600)  
        print("✅ Session rotation worker started")  
        
    finally:
        db.close()


if __name__ == '__main__':
    app = create_app()
    socketio = init_websocket(app)
    
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
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)