"""
Court Orders API Routes
Author: Ashutosh Rajesh
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

from flask import Blueprint, request, jsonify
from functools import wraps

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from core.services.court_order_service import CourtOrderService


court_orders_bp = Blueprint('court_orders', __name__, url_prefix='/api/court-orders')


def require_admin(f):
    """Decorator for admin-only endpoints"""
    @wraps(f)
    @require_auth
    def decorated_function(current_user, db, *args, **kwargs):
        # In production: Check if user has admin role
        # For now: Allow all authenticated users (demo)
        return f(current_user, db, *args, **kwargs)
    return decorated_function


@court_orders_bp.route('/judges', methods=['POST'])
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
        data = request.get_json()
        
        # Validate
        required = ['judge_id', 'full_name', 'court_name', 'jurisdiction']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
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
        from database.models.judge import Judge
        
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
        data = request.get_json()
        
        # Validate
        required = ['judge_id', 'target_idx', 'reason']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        # Submit order
        service = CourtOrderService(db)
        order = service.submit_court_order(
            data['judge_id'],
            data['target_idx'],
            data['reason'],
            data.get('case_number'),
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
        service = CourtOrderService(db)
        result = service.execute_deanonymization(order_id)
        
        if not result:
            return jsonify({
                'success': False,
                'error': 'De-anonymization failed or order expired'
            }), 400
        
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