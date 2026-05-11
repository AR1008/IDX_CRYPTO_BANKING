# [DOC] Admin API — company-only endpoints for granting/revoking time-limited access to CAs and government.
# [DOC] Access is controlled by the company (IDX Corp); no one can self-grant access to the IDX registry.
# [DOC] Every grant and revocation is logged to the access_audit_logs table for accountability.

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
# [DOC] timezone-aware datetime avoids bugs when comparing times across DST boundaries.
from datetime import datetime, timedelta, timezone
# [DOC] Decimal for monetary amounts — prevents float rounding errors.
from decimal import Decimal
# [DOC] uuid generates cryptographically random UUIDs used as opaque access tokens.
import uuid
# [DOC] json serialises Python dicts to strings for storage in the scope/details columns.
import json

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] AccessToken stores the token UUID and metadata; AccessRole is the enum of allowed roles;
# [DOC] AccessAuditLog is the immutable record of every grant/revoke/use action.
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
        # [DOC] Read the list of admin IDXs from settings (set via COMPANY_ADMIN_IDXS env var).
        from config.settings import settings

        admin_idxs = getattr(settings, 'COMPANY_ADMIN_IDXS', [])

        # [DOC] Reject if the authenticated user's IDX is neither in the admin list nor the special IDX_ADMIN literal.
        if current_user.idx not in admin_idxs and current_user.idx != 'IDX_ADMIN':
            return jsonify({
                'success': False,
                'error': 'Unauthorized. Company admin access required.'
            }), 403   # [DOC] 403 = authenticated but not authorised (correct role missing).

        # [DOC] User passed the admin check — call the actual route handler.
        return f(current_user, db, *args, **kwargs)

    return decorated_function


@admin_bp.route('/access/grant', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('admin_access_grant'))
@require_auth          # [DOC] First verify JWT is valid and extract current_user.
@require_company_admin # [DOC] Then verify current_user is a company admin.
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

        # [DOC] Validate mandatory fields before creating any DB rows.
        required = ['granted_to', 'role', 'purpose']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # [DOC] AccessRole is a Python Enum; calling AccessRole(value) raises ValueError on unknown values.
        role_str = data['role']
        try:
            role = AccessRole(role_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Invalid role. Must be one of: {[r.value for r in AccessRole]}'
            }), 400

        # [DOC] CAs get max 30 days; government gets max 90 days; anything else gets 7 days.
        duration_days = data.get('duration_days', 7)

        if role == AccessRole.CHARTERED_ACCOUNTANT:
            max_days = 30
        elif role == AccessRole.GOVERNMENT:
            max_days = 90
        else:
            max_days = 7

        if duration_days > max_days:
            return jsonify({
                'success': False,
                'error': f'Duration cannot exceed {max_days} days for role {role.value}'
            }), 400

        # [DOC] uuid4() generates a random 128-bit token — effectively unguessable.
        # [DOC] scope is stored as a JSON string so flexible restriction objects can be serialised.
        token = AccessToken(
            token=str(uuid.uuid4()),
            role=role,
            granted_to=data['granted_to'],
            granted_by=current_user.idx,         # [DOC] Record which admin performed the grant (accountability).
            purpose=data['purpose'],
            scope=json.dumps(data.get('scope')) if data.get('scope') else None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=duration_days)  # [DOC] Absolute expiry timestamp.
        )

        db.add(token)
        db.commit()  # [DOC] Flush to DB so token.id is assigned before creating the audit log.

        # [DOC] Immediately log the grant action — every access management action is audited.
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
            ip_address=request.remote_addr,           # [DOC] Record the admin's IP for traceability.
            user_agent=request.headers.get('User-Agent')
        )
        db.add(audit_log)
        db.commit()

        # [DOC] Build the portal URL the CA/Gov will use to access the IDX registry.
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

        # [DOC] Lookup the token row by its UUID string.
        token = db.query(AccessToken).filter(
            AccessToken.token == data['token']
        ).first()

        if not token:
            return jsonify({
                'success': False,
                'error': 'Token not found'
            }), 404

        # [DOC] Set is_active=False and record when/who revoked it — the row is NOT deleted (audit trail).
        token.is_active = False
        token.revoked_at = datetime.now(timezone.utc)
        token.revoked_by = current_user.idx
        db.commit()

        # [DOC] Log the revocation event for the audit trail.
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
        query = db.query(AccessToken)

        # [DOC] By default only show active tokens; pass ?active_only=false to see revoked ones too.
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        if active_only:
            query = query.filter(AccessToken.is_active == True)

        # [DOC] Optional role filter — admin can list only CA tokens or only government tokens.
        if 'role' in request.args:
            try:
                role = AccessRole(request.args['role'])
                query = query.filter(AccessToken.role == role)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid role'
                }), 400

        # [DOC] Order newest-first so the admin sees the most recently granted tokens at the top.
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
        # [DOC] Pagination: limit controls page size; offset skips that many rows from the start.
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        query = db.query(AccessAuditLog)

        # [DOC] Filter by action type (e.g. "GRANT_ACCESS", "REVOKE_ACCESS", "LOOKUP_IDX_TO_NAME").
        if 'action' in request.args:
            query = query.filter(AccessAuditLog.action == request.args['action'])

        # [DOC] Filter by the IDX of the user whose data was accessed — useful for investigating a specific user.
        if 'target_idx' in request.args:
            query = query.filter(AccessAuditLog.target_idx == request.args['target_idx'])

        # [DOC] Count total matching rows before applying pagination so the client can compute page count.
        total = query.count()

        # [DOC] .order_by(desc).limit(n).offset(m) = SQL ORDER BY ... DESC LIMIT n OFFSET m.
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
