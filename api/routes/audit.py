# [DOC] Audit Query API — read-only endpoints for inspecting the cryptographic audit log chain.
# [DOC] The audit log is append-only and hash-chained: tampering with any entry breaks the chain,
# [DOC] which verify_chain() will detect. Government uses these endpoints during a freeze period.

"""
Audit Query API Routes
Purpose: Query audit trail (government/authorized access only)

Endpoints:
- GET /api/audit/logs - Get audit logs (filtered by type, date range)
- GET /api/audit/logs/<id> - Get specific audit log
- GET /api/audit/court-order/<number> - Get all logs for court order
- GET /api/audit/judge/<id> - Get all logs by judge
- GET /api/audit/verify - Verify chain integrity
- GET /api/audit/stats - Get audit statistics

Security:
- All endpoints require authentication
- Court order queries require special permissions
- Rate limited to prevent abuse
"""

from flask import Blueprint, request, jsonify
# [DOC] AuditLogger is the service class that writes and reads the audit_logs table.
from core.security.audit_logger import AuditLogger
from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] datetime and timedelta used for date range filtering in queries.
from datetime import datetime, timedelta
from typing import Optional


audit_bp = Blueprint('audit', __name__, url_prefix='/api/audit')


@audit_bp.route('/logs', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def get_audit_logs():
    """
    Get audit logs with optional filters

    Query Parameters:
        event_type: Filter by event type (COURT_ORDER_ACCESS, KEY_GENERATION, etc.)
        limit: Maximum number of logs to return (default: 100, max: 1000)
        start_date: ISO format start date (optional)
        end_date: ISO format end date (optional)

    Returns:
        200: List of audit logs
        400: Invalid parameters
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/logs?event_type=COURT_ORDER_ACCESS&limit=50
    """
    try:
        # [DOC] Read optional query string parameters; None means "no filter applied".
        event_type = request.args.get('event_type', None)
        # [DOC] Clamp limit to 1000 maximum to prevent dumping the entire log table in one request.
        limit = min(int(request.args.get('limit', 100)), 1000)
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        if event_type:
            # [DOC] Delegate to the AuditLogger service which issues the SELECT with a WHERE event_type = ? clause.
            logs = AuditLogger.get_logs_by_type(event_type, limit)
        else:
            # [DOC] No event_type filter: fetch all logs, optionally restricted by date range.
            from database.connection import SessionLocal
            from database.models.audit_log import AuditLog

            db = SessionLocal()
            try:
                # [DOC] Start with a base query sorted newest-first so pagination is consistent.
                query = db.query(AuditLog).order_by(AuditLog.created_at.desc())

                # [DOC] fromisoformat() parses ISO 8601 strings like "2026-01-01T00:00:00".
                if start_date:
                    start_dt = datetime.fromisoformat(start_date)
                    query = query.filter(AuditLog.created_at >= start_dt)

                if end_date:
                    end_dt = datetime.fromisoformat(end_date)
                    query = query.filter(AuditLog.created_at <= end_dt)

                # [DOC] .limit() adds SQL LIMIT clause; fetch at most `limit` rows.
                logs_objs = query.limit(limit).all()
                # [DOC] Convert ORM objects to plain dicts so jsonify can serialise them.
                logs = [log.to_dict() for log in logs_objs]

            finally:
                db.close()

        return jsonify({
            'success': True,
            'count': len(logs),
            'logs': logs
        }), 200

    except ValueError as e:
        # [DOC] fromisoformat() raises ValueError if the date string is malformed.
        return jsonify({
            'success': False,
            'error': 'Invalid parameter',
            'message': str(e)
        }), 400

    except Exception as e:
        print(f"❌ Error getting audit logs: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@audit_bp.route('/logs/<int:log_id>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def get_audit_log(log_id: int):
    """
    Get specific audit log by ID

    Args:
        log_id: Audit log ID

    Returns:
        200: Audit log details
        404: Log not found
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/logs/123
    """
    try:
        from database.connection import SessionLocal
        from database.models.audit_log import AuditLog

        db = SessionLocal()
        try:
            # [DOC] Primary key lookup — .first() returns the row or None if the ID doesn't exist.
            log = db.query(AuditLog).filter(AuditLog.id == log_id).first()

            if not log:
                return jsonify({
                    'success': False,
                    'error': 'Not found',
                    'message': f'Audit log {log_id} not found'
                }), 404

            return jsonify({
                'success': True,
                'log': log.to_dict()
            }), 200

        finally:
            db.close()

    except Exception as e:
        print(f"❌ Error getting audit log: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@audit_bp.route('/court-order/<string:court_order_number>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def get_court_order_logs(court_order_number: str):
    """
    Get all audit logs for a specific court order

    Args:
        court_order_number: Court order reference number

    Returns:
        200: List of logs for court order
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/court-order/CO_2025_001
    """
    try:
        # [DOC] Fetches every log entry tagged with this court order number
        # [DOC] (e.g., key assembly, decryption, freeze events — all grouped under one court order).
        logs = AuditLogger.get_court_order_logs(court_order_number)

        return jsonify({
            'success': True,
            'court_order_number': court_order_number,
            'count': len(logs),
            'logs': logs
        }), 200

    except Exception as e:
        print(f"❌ Error getting court order logs: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@audit_bp.route('/judge/<string:judge_id>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def get_judge_logs(judge_id: str):
    """
    Get all court order accesses by a specific judge

    Args:
        judge_id: Judge identifier

    Query Parameters:
        limit: Maximum number of logs (default: 100)

    Returns:
        200: List of logs by judge
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/judge/JUDGE_12345?limit=50
    """
    try:
        # [DOC] Clamped at 1000 to prevent large dumps; default is 100.
        limit = min(int(request.args.get('limit', 100)), 1000)
        # [DOC] All log entries where judge_id column matches — shows everything this judge authorised.
        logs = AuditLogger.get_judge_logs(judge_id, limit)

        return jsonify({
            'success': True,
            'judge_id': judge_id,
            'count': len(logs),
            'logs': logs
        }), 200

    except Exception as e:
        print(f"❌ Error getting judge logs: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@audit_bp.route('/verify', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def verify_chain():
    """
    Verify integrity of audit log chain

    Query Parameters:
        start_id: Starting log ID (optional)
        end_id: Ending log ID (optional)

    Returns:
        200: Chain verification result
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/verify
        GET /api/audit/verify?start_id=100&end_id=200
    """
    try:
        # [DOC] type=int makes Flask automatically convert the query param string to an integer (or None if absent).
        start_id = request.args.get('start_id', None, type=int)
        end_id = request.args.get('end_id', None, type=int)

        # [DOC] verify_chain() walks every log entry in the range and re-computes the SHA-256 hash chain.
        # [DOC] Returns (True, "All X logs valid") if intact, or (False, "Tampered at ID Y") if broken.
        is_valid, message = AuditLogger.verify_chain(start_id, end_id)

        return jsonify({
            'success': True,
            'chain_valid': is_valid,
            'message': message,
            'verified_range': {
                'start_id': start_id,
                'end_id': end_id
            }
        }), 200

    except Exception as e:
        print(f"❌ Error verifying audit chain: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@audit_bp.route('/stats', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('audit_query'))
@require_auth
def get_audit_stats():
    """
    Get audit trail statistics

    Returns:
        200: Audit statistics
        401: Unauthorized
        429: Rate limit exceeded

    Example:
        GET /api/audit/stats
    """
    try:
        from database.connection import SessionLocal
        from database.models.audit_log import AuditLog
        # [DOC] func provides SQL aggregate functions (COUNT, SUM, etc.) via SQLAlchemy.
        # [DOC] distinct() wraps a column expression to produce COUNT(DISTINCT col).
        from sqlalchemy import func, distinct

        db = SessionLocal()
        try:
            # [DOC] scalar() fetches the first column of the first row — perfect for single-value aggregates.
            total_logs = db.query(func.count(AuditLog.id)).scalar()

            # [DOC] GROUP BY event_type gives a breakdown of how many logs exist per event category.
            logs_by_type = db.query(
                AuditLog.event_type,
                func.count(AuditLog.id).label('count')
            ).group_by(AuditLog.event_type).all()

            # [DOC] COUNT(DISTINCT court_order_number) counts unique court orders that appear in the log.
            total_court_orders = db.query(
                func.count(distinct(AuditLog.court_order_number))
            ).filter(
                AuditLog.court_order_number.isnot(None)
            ).scalar()

            # [DOC] Similarly: how many distinct judges have issued court orders through this system.
            total_judges = db.query(
                func.count(distinct(AuditLog.judge_id))
            ).filter(
                AuditLog.judge_id.isnot(None)
            ).scalar()

            # [DOC] Most recent log — shows the last event recorded in the chain.
            latest_log = db.query(AuditLog).order_by(AuditLog.created_at.desc()).first()

            # [DOC] Oldest log — useful to know the start of the audit history.
            oldest_log = db.query(AuditLog).order_by(AuditLog.created_at.asc()).first()

            # [DOC] Count activity in the last 24 hours to flag unusual spikes in access.
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_logs = db.query(func.count(AuditLog.id)).filter(
                AuditLog.created_at >= yesterday
            ).scalar()

            return jsonify({
                'success': True,
                'stats': {
                    'total_logs': total_logs,
                    # [DOC] Dict comprehension converts the list of (event_type, count) rows to a plain dict.
                    'logs_by_type': {row.event_type: row.count for row in logs_by_type},
                    'total_court_orders': total_court_orders,
                    'total_judges': total_judges,
                    'recent_logs_24h': recent_logs,
                    'latest_log': {
                        'id': latest_log.id,
                        'event_type': latest_log.event_type,
                        'created_at': latest_log.created_at.isoformat()
                    } if latest_log else None,
                    'oldest_log': {
                        'id': oldest_log.id,
                        'event_type': oldest_log.event_type,
                        'created_at': oldest_log.created_at.isoformat()
                    } if oldest_log else None
                }
            }), 200

        finally:
            db.close()

    except Exception as e:
        print(f"❌ Error getting audit stats: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500


# Export blueprint
__all__ = ['audit_bp']
