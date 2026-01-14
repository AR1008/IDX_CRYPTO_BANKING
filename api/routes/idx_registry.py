"""
IDX Registry API Routes
Purpose: Company-controlled access to IDX → Real Name mapping

SECURITY MODEL:
- Company has master access to entire registry
- Government/CAs get time-limited access (via access tokens)
- All lookups logged to tamper-proof audit trail
- Tokens can be restricted by scope (specific users only)

Access Flow:
1. Company grants access token to CA/Gov (via Admin API)
2. CA/Gov uses token to lookup IDX → Real Name
3. All lookups logged
4. Token expires automatically

Endpoints:
- POST /api/idx-registry/lookup - Lookup IDX → Real Name (requires access token)
- GET /api/idx-registry/bulk - Bulk lookup for multiple IDXs (requires access token)
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from database.models.user import User
from database.models.access_control import AccessToken, AccessAuditLog, AccessRole


idx_registry_bp = Blueprint('idx_registry', __name__, url_prefix='/api/idx-registry')


def require_access_token(f):
    """
    Decorator to require valid access token for registry access

    Checks:
    - Token exists and is valid
    - Token is active
    - Token has not expired
    - Token role is CA or Government

    Passes:
    - access_token: AccessToken object
    - db: Database session
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get database session from request context
        from database.connection import SessionLocal
        db = SessionLocal()

        try:
            # Get token from header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({
                    'success': False,
                    'error': 'Access token required. Use "Authorization: Bearer <token>" header.'
                }), 401

            token_str = auth_header.replace('Bearer ', '')

            # Find token in database
            access_token = db.query(AccessToken).filter(
                AccessToken.token == token_str
            ).first()

            if not access_token:
                return jsonify({
                    'success': False,
                    'error': 'Invalid access token'
                }), 401

            # Check if active
            if not access_token.is_active:
                return jsonify({
                    'success': False,
                    'error': 'Access token has been revoked'
                }), 401

            # Check if expired
            if not access_token.is_valid():
                return jsonify({
                    'success': False,
                    'error': 'Access token has expired'
                }), 401

            # Check role (only CA and Government can access registry)
            if access_token.role not in [AccessRole.CHARTERED_ACCOUNTANT,
                                         AccessRole.GOVERNMENT,
                                         AccessRole.COMPANY_ADMIN]:
                return jsonify({
                    'success': False,
                    'error': 'Insufficient permissions'
                }), 403

            # Update last used timestamp
            access_token.last_used_at = datetime.now()
            db.commit()

            # Call the actual function with token and db
            return f(access_token, db, *args, **kwargs)

        except Exception as e:
            db.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
        finally:
            db.close()

    return decorated_function


@idx_registry_bp.route('/lookup', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('idx_registry_lookup'))
@require_access_token
def lookup_idx(access_token, db):
    """
    Lookup IDX → Real Name (requires access token)

    Request body:
        {
            "idx": "IDX_abc123..."
        }

    Returns:
        JSON: {
            success: true,
            idx: "IDX_abc123...",
            real_name: "Rajesh Kumar",
            pan_card: "RAJSH1234K",
            lookup_allowed: true
        }

    Security:
    - Requires valid access token (granted by company)
    - Checks scope restrictions (if token limited to specific users)
    - Logs all lookups to audit trail
    """
    try:
        data = request.get_json()

        if not data.get('idx'):
            return jsonify({
                'success': False,
                'error': 'idx is required'
            }), 400

        target_idx = data['idx']

        # Check scope restrictions
        if access_token.scope:
            try:
                scope = json.loads(access_token.scope)

                # If scope limits to specific user
                if 'user_idx' in scope and scope['user_idx'] != target_idx:
                    return jsonify({
                        'success': False,
                        'error': 'Access token scope does not include this user'
                    }), 403
            except json.JSONDecodeError:
                pass  # Ignore invalid scope JSON

        # Lookup user
        user = db.query(User).filter(User.idx == target_idx).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Log the lookup
        audit_log = AccessAuditLog(
            access_token_id=access_token.id,
            accessed_by=access_token.granted_to,
            action="LOOKUP_IDX_TO_NAME",
            target_idx=target_idx,
            details=json.dumps({
                'real_name': user.full_name,
                'pan_card': user.pan_card,
                'token_role': access_token.role.value
            }),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.add(audit_log)
        db.commit()

        # Return mapping
        return jsonify({
            'success': True,
            'idx': target_idx,
            'real_name': user.full_name,
            'pan_card': user.pan_card,
            'lookup_allowed': True,
            'accessed_by': access_token.granted_to,
            'access_purpose': access_token.purpose
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@idx_registry_bp.route('/bulk', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('idx_registry_bulk'))
@require_access_token
def bulk_lookup_idx(access_token, db):
    """
    Bulk lookup multiple IDXs → Real Names

    Request body:
        {
            "idxs": ["IDX_abc123...", "IDX_def456...", ...]
        }

    Returns:
        JSON: {
            success: true,
            results: [
                {idx, real_name, pan_card},
                ...
            ],
            count: 2
        }

    Limits:
    - Max 100 IDXs per request
    - All lookups logged
    """
    try:
        data = request.get_json()

        if not data.get('idxs'):
            return jsonify({
                'success': False,
                'error': 'idxs array is required'
            }), 400

        idxs = data['idxs']

        # Validate is array
        if not isinstance(idxs, list):
            return jsonify({
                'success': False,
                'error': 'idxs must be an array'
            }), 400

        # Limit to 100 per request
        if len(idxs) > 100:
            return jsonify({
                'success': False,
                'error': 'Maximum 100 IDXs per request'
            }), 400

        # Check scope restrictions
        if access_token.scope:
            try:
                scope = json.loads(access_token.scope)

                # If scope limits to specific user, reject bulk
                if 'user_idx' in scope:
                    return jsonify({
                        'success': False,
                        'error': 'Bulk lookup not allowed with user-specific scope'
                    }), 403
            except json.JSONDecodeError:
                pass

        # Lookup all users
        users = db.query(User).filter(User.idx.in_(idxs)).all()

        # Build results
        results = []
        for user in users:
            results.append({
                'idx': user.idx,
                'real_name': user.full_name,
                'pan_card': user.pan_card
            })

        # Log bulk lookup
        audit_log = AccessAuditLog(
            access_token_id=access_token.id,
            accessed_by=access_token.granted_to,
            action="BULK_LOOKUP_IDX_TO_NAME",
            target_idx=None,  # Bulk operation
            details=json.dumps({
                'idx_count': len(idxs),
                'found_count': len(results),
                'token_role': access_token.role.value
            }),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.add(audit_log)
        db.commit()

        return jsonify({
            'success': True,
            'results': results,
            'requested_count': len(idxs),
            'found_count': len(results),
            'accessed_by': access_token.granted_to
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@idx_registry_bp.route('/verify-token', methods=['GET'])
@require_access_token
def verify_token(access_token, db):
    """
    Verify access token is valid and get token info

    Returns:
        JSON: {
            success: true,
            token_info: {
                role,
                granted_to,
                purpose,
                expires_at,
                scope
            }
        }
    """
    try:
        return jsonify({
            'success': True,
            'token_info': {
                'role': access_token.role.value,
                'granted_to': access_token.granted_to,
                'granted_by': access_token.granted_by,
                'purpose': access_token.purpose,
                'granted_at': access_token.granted_at.isoformat(),
                'expires_at': access_token.expires_at.isoformat(),
                'scope': json.loads(access_token.scope) if access_token.scope else None,
                'is_valid': access_token.is_valid(),
                'last_used_at': access_token.last_used_at.isoformat() if access_token.last_used_at else None
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
