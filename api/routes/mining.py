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

from flask import Blueprint, request, jsonify
from database.connection import SessionLocal
from database.models.user import User
from database.models.miner import MinerStatistics
from core.mining.mining_pool import get_mining_pool
from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit

# Create Blueprint
mining_bp = Blueprint('mining', __name__, url_prefix='/api/mining')


@mining_bp.route('/start', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('mining_start'))
@require_auth
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
        # Get user from request context (set by @require_auth)
        user_idx = request.user_idx

        # Verify user exists
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.idx == user_idx).first()

            if not user:
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 404

        finally:
            db.close()

        # Get mining pool
        pool = get_mining_pool()

        # Register miner
        success = pool.register_miner(user_idx)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to register miner (already registered or pool full)'
            }), 400

        # Get pool stats
        active_miners = pool.get_active_miners_count()

        return jsonify({
            'success': True,
            'message': 'Mining started successfully',
            'miner_idx': user_idx,
            'pool_stats': {
                'active_miners': active_miners,
                'total_capacity': 100
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

        # Get mining pool
        pool = get_mining_pool()

        # Unregister miner
        success = pool.unregister_miner(user_idx)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Miner not registered'
            }), 400

        # Get final stats
        db = SessionLocal()
        try:
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == user_idx
            ).first()

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
            miner_stats = db.query(MinerStatistics).filter(
                MinerStatistics.user_idx == user_idx
            ).first()

            if not miner_stats:
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
        # Get query parameters
        limit = min(int(request.args.get('limit', 10)), 100)
        sort_by = request.args.get('sort_by', 'blocks')

        db = SessionLocal()
        try:
            # Get top miners
            if sort_by == 'fees':
                top_miners = MinerStatistics.get_by_fees_earned(db, limit=limit)
            else:
                top_miners = MinerStatistics.get_leaderboard(db, limit=limit)

            # Format leaderboard
            leaderboard = []
            for rank, miner in enumerate(top_miners, 1):
                stats = miner.to_dict()
                stats['rank'] = rank
                leaderboard.append(stats)

            # Get total count
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
                'utilization': pool.get_active_miners_count() / 100 * 100,
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
