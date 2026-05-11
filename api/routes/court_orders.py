"""
Court Orders API Routes
Purpose: Court order endpoints (admin/judge access)

Security:
- Admin authentication required
- Judge authorization verified
- All access logged
- Time-limited access

Endpoints:
- POST /api/court-orders/judges - Add authorized judge (admin)
- GET /api/court-orders/judges - List authorized judges
- POST /api/court-orders/submit - Submit court order
- GET /api/court-orders/{order_id} - Get order details
- POST /api/court-orders/{order_id}/execute - Execute de-anonymization
- GET /api/court-orders/audit-trail - View audit log
"""

# [DOC] Blueprint groups all court-order routes under a shared URL prefix; request provides HTTP body data; jsonify builds JSON responses
from flask import Blueprint, request, jsonify
# [DOC] wraps preserves the original function's name and docstring when a decorator wraps it — important for Flask route registration
from functools import wraps

# [DOC] require_auth checks the JWT Bearer token in the Authorization header and injects (current_user, db) into the route
from api.middleware.auth import require_auth
# [DOC] limiter enforces per-endpoint rate limits; get_rate_limit fetches the configured rule string from settings
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] CourtOrderService contains all business logic: filing orders, executing decryption, fetching audit logs
from core.services.court_order_service import CourtOrderService


# [DOC] Register all routes in this file under /api/court-orders
court_orders_bp = Blueprint('court_orders', __name__, url_prefix='/api/court-orders')


def require_admin(f):
    """Decorator for admin-only endpoints"""
    # [DOC] @wraps(f) copies f's __name__ and __doc__ onto the wrapper so Flask's route registry uses the correct function name
    @wraps(f)
    # [DOC] Applying require_auth here means every admin-only endpoint also requires a valid JWT — no unauthenticated admin access
    @require_auth
    def decorated_function(current_user, db, *args, **kwargs):
        # In production: Check if user has admin role
        # [DOC] Production: add a role check here (e.g. current_user.role == 'admin') before calling the actual function
        # For now: Allow all authenticated users (demo)
        return f(current_user, db, *args, **kwargs)
    return decorated_function


@court_orders_bp.route('/judges', methods=['POST'])
# [DOC] require_admin wraps require_auth — both decorators run in order; only authenticated admins can call this endpoint
@require_admin
def add_judge(current_user, db):
    """
    Add authorized judge (ADMIN ONLY)

    Request body:
        {
            "judge_id": "JID_2025_001",
            "full_name": "Justice Sharma",
            "court_name": "Delhi High Court",
            "jurisdiction": "Delhi"
        }

    Returns:
        JSON: {success: true, judge: {...}}
    """
    try:
        # [DOC] Parse the JSON request body into a Python dict
        data = request.get_json()

        # [DOC] All four fields are mandatory — missing any field rejects the request with HTTP 400
        # Validate
        required = ['judge_id', 'full_name', 'court_name', 'jurisdiction']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # [DOC] add_authorized_judge creates a Judge record in the database — only judges in this table can sign court orders
        # Add judge
        service = CourtOrderService(db)
        judge = service.add_authorized_judge(
            data['judge_id'],
            data['full_name'],
            data['court_name'],
            data['jurisdiction']
        )

        return jsonify({
            'success': True,
            'message': f'Judge {judge.full_name} authorized',
            'judge': judge.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('/judges', methods=['GET'])
@require_admin
def get_judges(current_user, db):
    """
    Get all authorized judges

    Returns:
        JSON: {success: true, judges: [...]}
    """
    try:
        # [DOC] Import Judge ORM model here (not at top) to avoid a circular import at module load time
        from database.models.judge import Judge

        # [DOC] Filter to only active judges — deactivated judges can no longer sign new court orders
        judges = db.query(Judge).filter(Judge.is_active == True).all()

        return jsonify({
            'success': True,
            'judges': [j.to_dict() for j in judges],
            'count': len(judges)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('/submit', methods=['POST'])
@require_admin
def submit_order(current_user, db):
    """
    Submit court order

    Request body:
        {
            "judge_id": "JID_2025_001",
            "target_idx": "IDX_abc123...",
            "reason": "Money laundering investigation",
            "case_number": "CASE_2025_456",
            "freeze_account": true
        }

    Returns:
        JSON: {success: true, order: {...}}
    """
    try:
        # [DOC] Parse the JSON body containing the judge ID, target IDX, and reason for the order
        data = request.get_json()

        # [DOC] judge_id, target_idx, and reason are mandatory — case_number and freeze_account are optional
        # Validate
        required = ['judge_id', 'target_idx', 'reason']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # [DOC] submit_court_order validates judge authorization, records the order, and optionally freezes the target account
        # Submit order
        service = CourtOrderService(db)
        order = service.submit_court_order(
            data['judge_id'],
            data['target_idx'],
            data['reason'],
            # [DOC] case_number is optional — defaults to None if not provided
            data.get('case_number'),
            # [DOC] freeze_account defaults to True — a court order almost always accompanies an account freeze
            data.get('freeze_account', True)
        )

        return jsonify({
            'success': True,
            'message': f'Court order {order.order_id} submitted',
            'order': order.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('/<string:order_id>', methods=['GET'])
@require_admin
def get_order(current_user, db, order_id):
    """
    Get court order details

    Returns:
        JSON: {success: true, order: {...}}
    """
    try:
        # [DOC] get_court_order looks up the CourtOrder record by its unique order_id string
        service = CourtOrderService(db)
        order = service.get_court_order(order_id)

        if not order:
            return jsonify({
                'success': False,
                'error': 'Court order not found'
            }), 404

        return jsonify({
            'success': True,
            'order': order.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('/<string:order_id>/execute', methods=['POST'])
@require_admin
def execute_order(current_user, db, order_id):
    """
    Execute de-anonymization

    Returns:
        JSON: {success: true, result: {...}}
    """
    try:
        # [DOC] execute_deanonymization assembles the Company key + one regulatory authority key share to decrypt the target transaction
        # [DOC] After decryption, both key shares are invalidated — they cannot be used again for any other transaction
        service = CourtOrderService(db)
        result = service.execute_deanonymization(order_id)

        if not result:
            return jsonify({
                'success': False,
                'error': 'De-anonymization failed or order expired'
            }), 400

        # [DOC] result contains the decrypted IDX of the target party — real identity lookup requires the IDX Central Database
        return jsonify({
            'success': True,
            'message': 'De-anonymization executed',
            'result': result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('', methods=['GET'])
@require_admin
def get_all_orders(current_user, db):
    """
    Get all court orders

    Returns:
        JSON: {success: true, orders: [...]}
    """
    try:
        # [DOC] get_all_court_orders returns every court order in the system — used by admins to monitor and audit activity
        service = CourtOrderService(db)
        orders = service.get_all_court_orders()

        return jsonify({
            'success': True,
            'orders': [o.to_dict() for o in orders],
            'count': len(orders)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@court_orders_bp.route('/audit-trail', methods=['GET'])
@require_admin
def get_audit_trail(current_user, db):
    """
    Get complete audit trail

    Returns:
        JSON: {success: true, audit_log: [...]}
    """
    try:
        # [DOC] get_audit_trail returns every access_audit_log entry — who accessed what, when, and with which key
        # [DOC] This log is append-only and cryptographically signed, providing tamper evidence for regulatory review
        service = CourtOrderService(db)
        audit_log = service.get_audit_trail()

        return jsonify({
            'success': True,
            'audit_log': audit_log,
            'count': len(audit_log)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
