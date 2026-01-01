"""
Admin API Routes
Purpose: Company-controlled access management

SECURITY MODEL:
- Only COMPANY admins can access these endpoints
- Company controls ALL access (master access)
- Government/CAs get time-limited access
- All access automatically logged

Endpoints:
- POST /api/admin/access/grant - Grant CA/Gov access
- POST /api/admin/access/revoke - Revoke access
- GET /api/admin/access/tokens - List active tokens
- GET /api/admin/access/audit - View access audit log
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import json

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from database.models.access_control import AccessToken, AccessRole, AccessAuditLog


admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def require_company_admin(f):
    """
    Decorator to require company admin authentication

    In production: Check JWT role claim
    For now: Check if user has admin flag
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(current_user, db, *args, **kwargs):
        # TODO: In production, check JWT claims or admin table
        # For now, check if user has specific admin IDX
        from config.settings import settings

        # Company admin IDXs (set in environment)
        admin_idxs = getattr(settings, 'COMPANY_ADMIN_IDXS', [])

        if current_user.idx not in admin_idxs and current_user.idx != 'IDX_ADMIN':
            return jsonify({
                'success': False,
                'error': 'Unauthorized. Company admin access required.'
            }), 403

        return f(current_user, db, *args, **kwargs)

    return decorated_function


@admin_bp.route('/access/grant', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('admin_access_grant'))
@require_auth
@require_company_admin
def grant_access(current_user, db):
    """
    Grant time-limited access to Government/CA

    Request body:
        {
            "granted_to": "ABC Tax Consultants Pvt Ltd",
            "role": "chartered_accountant",  # or "government"
            "purpose": "Tax season FY 2025-26",
            "duration_days": 7,
            "scope": {  # Optional restrictions
                "user_idx": "IDX_abc123..."  # Limit to specific user
            }
        }

    Returns:
        JSON: {
            success: true,
            token: "uuid...",
            expires_at: "2026-01-03T14:30:00Z",
            access_url: "https://..."
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ['granted_to', 'role', 'purpose']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # Validate role
        role_str = data['role']
        try:
            role = AccessRole(role_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Invalid role. Must be one of: {[r.value for r in AccessRole]}'
            }), 400

        # Get duration (default 7 days)
        duration_days = data.get('duration_days', 7)

        # Validate duration limits
        if role == AccessRole.CHARTERED_ACCOUNTANT:
            max_days = 30  # CAs get max 30 days
        elif role == AccessRole.GOVERNMENT:
            max_days = 90  # Government gets max 90 days
        else:
            max_days = 7

        if duration_days > max_days:
            return jsonify({
                'success': False,
                'error': f'Duration cannot exceed {max_days} days for role {role.value}'
            }), 400

        # Create access token
        token = AccessToken(
            token=str(uuid.uuid4()),
            role=role,
            granted_to=data['granted_to'],
            granted_by=current_user.idx,
            purpose=data['purpose'],
            scope=json.dumps(data.get('scope')) if data.get('scope') else None,
            expires_at=datetime.now() + timedelta(days=duration_days)
        )

        db.add(token)
        db.commit()

        # Log the grant
        audit_log = AccessAuditLog(
            access_token_id=token.id,
            accessed_by=current_user.idx,
            action="GRANT_ACCESS",
            details=json.dumps({
                'granted_to': data['granted_to'],
                'role': role.value,
                'duration_days': duration_days,
                'purpose': data['purpose']
            }),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.add(audit_log)
        db.commit()

        # Build access URL (for CA portal)
        from config.settings import settings
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://idx-banking.com')
        access_url = f"{frontend_url}/ca-portal?token={token.token}"

        return jsonify({
            'success': True,
            'token': token.token,
            'role': role.value,
            'granted_to': data['granted_to'],
            'expires_at': token.expires_at.isoformat(),
            'access_url': access_url,
            'duration_days': duration_days
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


@admin_bp.route('/access/revoke', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('admin_access_revoke'))
@require_auth
@require_company_admin
def revoke_access(current_user, db):
    """
    Revoke access token

    Request body:
        {
            "token": "uuid...",
            "reason": "Tax season ended"
        }

    Returns:
        JSON: {success: true, revoked_at: "..."}
    """
    try:
        data = request.get_json()

        if 'token' not in data:
            return jsonify({
                'success': False,
                'error': 'token is required'
            }), 400

        # Find token
        token = db.query(AccessToken).filter(
            AccessToken.token == data['token']
        ).first()

        if not token:
            return jsonify({
                'success': False,
                'error': 'Token not found'
            }), 404

        # Revoke
        token.is_active = False
        token.revoked_at = datetime.now()
        token.revoked_by = current_user.idx
        db.commit()

        # Log the revocation
        audit_log = AccessAuditLog(
            access_token_id=token.id,
            accessed_by=current_user.idx,
            action="REVOKE_ACCESS",
            details=json.dumps({
                'granted_to': token.granted_to,
                'reason': data.get('reason', 'Not specified')
            }),
            ip_address=request.remote_addr
        )
        db.add(audit_log)
        db.commit()

        return jsonify({
            'success': True,
            'revoked_at': token.revoked_at.isoformat(),
            'reason': data.get('reason')
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/access/tokens', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('admin_access_list'))
@require_auth
@require_company_admin
def list_tokens(current_user, db):
    """
    List all access tokens

    Query params:
        active_only: bool (default: true)
        role: string (filter by role)

    Returns:
        JSON: {success: true, tokens: [...]}
    """
    try:
        # Build query
        query = db.query(AccessToken)

        # Filter by active status
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        if active_only:
            query = query.filter(AccessToken.is_active == True)

        # Filter by role
        if 'role' in request.args:
            try:
                role = AccessRole(request.args['role'])
                query = query.filter(AccessToken.role == role)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid role'
                }), 400

        # Execute query
        tokens = query.order_by(AccessToken.granted_at.desc()).all()

        return jsonify({
            'success': True,
            'tokens': [token.to_dict() for token in tokens],
            'count': len(tokens)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/access/audit', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('admin_access_audit'))
@require_auth
@require_company_admin
def get_audit_logs(current_user, db):
    """
    Get access audit logs

    Query params:
        limit: int (default: 100)
        offset: int (default: 0)
        action: string (filter by action)
        target_idx: string (filter by target user)

    Returns:
        JSON: {success: true, logs: [...]}
    """
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        # Build query
        query = db.query(AccessAuditLog)

        # Filter by action
        if 'action' in request.args:
            query = query.filter(AccessAuditLog.action == request.args['action'])

        # Filter by target
        if 'target_idx' in request.args:
            query = query.filter(AccessAuditLog.target_idx == request.args['target_idx'])

        # Get total count
        total = query.count()

        # Execute query with pagination
        logs = query.order_by(
            AccessAuditLog.accessed_at.desc()
        ).limit(limit).offset(offset).all()

        return jsonify({
            'success': True,
            'logs': [log.to_dict() for log in logs],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
