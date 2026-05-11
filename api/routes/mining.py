# [DOC] Mining API routes — HTTP endpoints that let authenticated users start/stop mining and query stats.
# [DOC] Mining here means participating in PoW block production; miners earn 0.5% of each transaction fee.
# [DOC] All endpoints are JWT-protected and rate-limited to prevent abuse.

"""
Mining Routes
Purpose: API endpoints for user mining

Endpoints:
- POST /api/mining/start - Start mining
- POST /api/mining/stop - Stop mining
- GET /api/mining/stats - Get mining statistics
- GET /api/mining/leaderboard - Top miners
- GET /api/mining/pool-status - Pool status
"""

# [DOC] Blueprint groups related routes under a common URL prefix (/api/mining) without polluting app.py.
from flask import Blueprint, request, jsonify
# [DOC] SessionLocal opens a new DB connection for the duration of a request.
from database.connection import SessionLocal
# [DOC] User ORM model — queried to confirm the miner exists before registering them.
from database.models.user import User
# [DOC] MinerStatistics ORM model — stores per-miner block counts, fees earned, hash rate, etc.
from database.models.miner import MinerStatistics
# [DOC] get_mining_pool() returns the singleton MiningPool that coordinates all miner threads.
from core.mining.mining_pool import get_mining_pool
# [DOC] require_auth decorator — validates JWT before the route handler runs.
from api.middleware.auth import require_auth
# [DOC] limiter.limit() applies per-endpoint call-rate enforcement; get_rate_limit() reads the limit from config.
from api.middleware.rate_limiter import limiter, get_rate_limit

# [DOC] Register all routes in this file under the /api/mining URL prefix.
mining_bp = Blueprint('mining', __name__, url_prefix='/api/mining')


@mining_bp.route('/start', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('mining_start'))  # [DOC] Lambda defers the settings lookup until app startup is complete.
@require_auth  # [DOC] Injects current_user and db into route kwargs after verifying JWT.
def start_mining():
    """
    Start mining for authenticated user

    Request:
    {
        "user_idx": "IDX_abc123..."  # From JWT token
    }

    Response:
    {
        "success": true,
        "message": "Mining started",
        "miner_idx": "IDX_abc123...",
        "pool_stats": {
            "active_miners": 5,
            "total_capacity": 100
        }
    }
    """
    try:
        # [DOC] require_auth sets request.user_idx from the decoded JWT payload.
        user_idx = request.user_idx

        # [DOC] Open a fresh DB session to verify the user actually exists.
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.idx == user_idx).first()

            if not user:
                # [DOC] JWT was valid but user row was deleted — return 404 (not 401, user was authenticated).
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 404

        finally:
            db.close()

        # [DOC] Get the single MiningPool instance (created on first call, reused thereafter).
        pool = get_mining_pool()

        # [DOC] register_miner() creates a MinerWorker thread for this IDX and adds it to the pool.
        success = pool.register_miner(user_idx)

        if not success:
            # [DOC] Returns False if the user is already registered or the pool has reached MAX_MINERS.
            return jsonify({
                'success': False,
                'error': 'Failed to register miner (already registered or pool full)'
            }), 400

        # [DOC] Report how many miners are currently active so the client can show pool utilisation.
        active_miners = pool.get_active_miners_count()

        return jsonify({
            'success': True,
            'message': 'Mining started successfully',
            'miner_idx': user_idx,
            'pool_stats': {
                'active_miners': active_miners,
                'total_capacity': 100  # [DOC] Hard-coded maximum; matches MAX_MINERS setting.
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start mining: {str(e)}'
        }), 500


@mining_bp.route('/stop', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('mining_stop'))
@require_auth
def stop_mining():
    """
    Stop mining for authenticated user

    Response:
    {
        "success": true,
        "message": "Mining stopped",
        "final_stats": {
            "total_blocks_mined": 5,
            "total_fees_earned": "250.00",
            "blocks_won": 5,
            "blocks_lost": 2
        }
    }
    """
    try:
        user_idx = request.user_idx

        pool = get_mining_pool()

        # [DOC] unregister_miner() stops the worker thread and sets is_active=False in the DB.
        success = pool.unregister_miner(user_idx)

        if not success:
            # [DOC] The user wasn't in the active miners dict — nothing to stop.
            return jsonify({
                'success': False,
                'error': 'Miner not registered'
            }), 400

        # [DOC] After stopping, fetch the final statistics row so the client can display a summary.
        db = SessionLocal()
        try:
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == user_idx
            ).first()

            # [DOC] to_dict() serialises the ORM row to a plain dict (safe for jsonify).
            final_stats = miner_stats.to_dict() if miner_stats else {}

        finally:
            db.close()

        return jsonify({
            'success': True,
            'message': 'Mining stopped successfully',
            'final_stats': final_stats
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to stop mining: {str(e)}'
        }), 500


@mining_bp.route('/stats', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('mining_stats'))
@require_auth
def get_stats():
    """
    Get mining statistics for authenticated user

    Response:
    {
        "success": true,
        "stats": {
            "user_idx": "IDX_abc123...",
            "total_blocks_mined": 10,
            "total_fees_earned": "500.00",
            "blocks_won": 10,
            "blocks_lost": 5,
            "win_rate": 66.67,
            "avg_mining_time_seconds": "45.23",
            "hash_rate_per_second": "12345.67",
            "is_active": true,
            "last_mined_at": "2025-12-26T10:30:00",
            "started_mining_at": "2025-12-25T09:00:00"
        }
    }
    """
    try:
        user_idx = request.user_idx

        db = SessionLocal()
        try:
            # [DOC] Filter to find the single statistics row belonging to this miner.
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == user_idx
            ).first()

            if not miner_stats:
                # [DOC] Row doesn't exist yet — user hasn't started mining at all.
                return jsonify({
                    'success': False,
                    'error': 'No mining statistics found',
                    'message': 'You haven\'t started mining yet'
                }), 404

            return jsonify({
                'success': True,
                'stats': miner_stats.to_dict()
            }), 200

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get stats: {str(e)}'
        }), 500


@mining_bp.route('/leaderboard', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('mining_stats'))
# [DOC] No @require_auth — leaderboard is public so anyone can see the top miners.
def get_leaderboard():
    """
    Get top miners leaderboard

    Query Parameters:
    - limit: Number of miners to return (default: 10, max: 100)
    - sort_by: Sort criterion ('blocks' or 'fees', default: 'blocks')

    Response:
    {
        "success": true,
        "leaderboard": [
            {
                "rank": 1,
                "user_idx": "IDX_abc123...",
                "total_blocks_mined": 100,
                "total_fees_earned": "5000.00",
                "win_rate": 75.5,
                "is_active": true
            },
            ...
        ],
        "total_miners": 50
    }
    """
    try:
        # [DOC] Clamp limit between 1 and 100 so clients can't dump the entire table.
        limit = min(int(request.args.get('limit', 10)), 100)
        sort_by = request.args.get('sort_by', 'blocks')

        db = SessionLocal()
        try:
            # [DOC] Two different class methods sort by different columns (blocks mined vs fees earned).
            if sort_by == 'fees':
                top_miners = MinerStatistics.get_by_fees_earned(db, limit=limit)
            else:
                top_miners = MinerStatistics.get_leaderboard(db, limit=limit)

            # [DOC] enumerate() gives us a 1-based rank index alongside each miner object.
            leaderboard = []
            for rank, miner in enumerate(top_miners, 1):
                stats = miner.to_dict()
                stats['rank'] = rank  # [DOC] Inject rank into the dict before returning.
                leaderboard.append(stats)

            # [DOC] .count() issues a SELECT COUNT(*) — shows total miners not just top-N.
            total_miners = db.query(MinerStatistics).count()

            return jsonify({
                'success': True,
                'leaderboard': leaderboard,
                'total_miners': total_miners,
                'sort_by': sort_by
            }), 200

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get leaderboard: {str(e)}'
        }), 500


@mining_bp.route('/pool-status', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('mining_stats'))
# [DOC] Also public — pool status doesn't reveal any sensitive user data.
def get_pool_status():
    """
    Get mining pool status

    Response:
    {
        "success": true,
        "pool": {
            "active_miners": 10,
            "max_capacity": 100,
            "utilization": 10.0,
            "is_running": true
        }
    }
    """
    try:
        pool = get_mining_pool()

        return jsonify({
            'success': True,
            'pool': {
                'active_miners': pool.get_active_miners_count(),
                'max_capacity': 100,
                # [DOC] Utilisation as a percentage: (active / max) * 100.
                'utilization': pool.get_active_miners_count() / 100 * 100,
                # [DOC] pool.running is True while the coordinator thread is alive.
                'is_running': pool.running
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get pool status: {str(e)}'
        }), 500


# Testing
if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(mining_bp)

    print("=== Mining Routes Test ===")
    print("\nAvailable endpoints:")
    print("  POST /api/mining/start")
    print("  POST /api/mining/stop")
    print("  GET /api/mining/stats")
    print("  GET /api/mining/leaderboard")
    print("  GET /api/mining/pool-status")
    print("\n✅ Mining routes created successfully!")
