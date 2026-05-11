# [DOC] IDX Registry API — the gated lookup service that maps an IDX pseudonym to a real identity.
# [DOC] This is the highest-privilege endpoint in the system: revealing IDX → real name.
# [DOC] Access requires a time-limited token issued by the company admin (via admin.py), NOT a user JWT.
# [DOC] Every lookup is logged to the access_audit_logs table — there is no anonymous access.

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
# [DOC] datetime used to update access_token.last_used_at on each successful use.
from datetime import datetime
import json

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] User ORM model — the source of real name and PAN card data.
from database.models.user import User
# [DOC] AccessToken — the row storing the UUID token and its permissions.
# [DOC] AccessAuditLog — immutable record of every lookup action.
# [DOC] AccessRole — enum of valid roles (CHARTERED_ACCOUNTANT, GOVERNMENT, COMPANY_ADMIN).
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
        # [DOC] Open a new DB session here (not passed in from require_auth) because
        # [DOC] this decorator replaces require_auth for registry endpoints.
        from database.connection import SessionLocal
        db = SessionLocal()

        try:
            # [DOC] Read the Authorization header — format must be "Bearer <uuid-token>".
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({
                    'success': False,
                    'error': 'Access token required. Use "Authorization: Bearer <token>" header.'
                }), 401

            # [DOC] Strip the "Bearer " prefix to get the raw UUID token string.
            token_str = auth_header.replace('Bearer ', '')

            # [DOC] Look up the token UUID in the access_tokens table.
            access_token = db.query(AccessToken).filter(
                AccessToken.token == token_str
            ).first()

            if not access_token:
                # [DOC] Unknown token — could be forged, expired and deleted, or simply wrong.
                return jsonify({
                    'success': False,
                    'error': 'Invalid access token'
                }), 401

            # [DOC] is_active is set to False when an admin revokes the token.
            if not access_token.is_active:
                return jsonify({
                    'success': False,
                    'error': 'Access token has been revoked'
                }), 401

            # [DOC] is_valid() checks that datetime.now() < expires_at.
            if not access_token.is_valid():
                return jsonify({
                    'success': False,
                    'error': 'Access token has expired'
                }), 401

            # [DOC] Only CA, Government, or Company Admin roles may query the IDX → real name mapping.
            if access_token.role not in [AccessRole.CHARTERED_ACCOUNTANT,
                                         AccessRole.GOVERNMENT,
                                         AccessRole.COMPANY_ADMIN]:
                return jsonify({
                    'success': False,
                    'error': 'Insufficient permissions'
                }), 403

            # [DOC] Touch last_used_at so admins can see when a token was most recently used.
            access_token.last_used_at = datetime.now()
            db.commit()

            # [DOC] Inject access_token and db as the first two positional arguments of the route.
            return f(access_token, db, *args, **kwargs)

        except Exception as e:
            db.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
        finally:
            # [DOC] Always close the DB session to release the connection back to the pool.
            db.close()

    return decorated_function


@idx_registry_bp.route('/lookup', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('idx_registry_lookup'))
@require_access_token  # [DOC] No @require_auth here — access_token takes the place of a JWT.
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

        # [DOC] scope is an optional JSON string stored on the token that restricts which IDXs can be looked up.
        # [DOC] Example scope: {"user_idx": "IDX_abc123"} means only that one IDX can be queried.
        if access_token.scope:
            try:
                scope = json.loads(access_token.scope)

                # [DOC] If the scope names a specific user and the requested IDX doesn't match, reject.
                if 'user_idx' in scope and scope['user_idx'] != target_idx:
                    return jsonify({
                        'success': False,
                        'error': 'Access token scope does not include this user'
                    }), 403
            except json.JSONDecodeError:
                pass  # [DOC] Malformed scope JSON is ignored — treat as no restriction.

        # [DOC] Find the user row whose idx column matches — this is the IDX Central Database lookup.
        user = db.query(User).filter(User.idx == target_idx).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # [DOC] Log BEFORE returning the data — the log must always exist even if the response fails after.
        audit_log = AccessAuditLog(
            access_token_id=access_token.id,
            accessed_by=access_token.granted_to,    # [DOC] Who made this lookup (e.g. "ABC Tax Consultants").
            action="LOOKUP_IDX_TO_NAME",
            target_idx=target_idx,                  # [DOC] Whose IDX was revealed — searchable in audit queries.
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

        # [DOC] Return the real identity — this is the only place in the system where IDX is linked to name.
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

        # [DOC] Ensure the input is a list and not a string or dict.
        if not isinstance(idxs, list):
            return jsonify({
                'success': False,
                'error': 'idxs must be an array'
            }), 400

        # [DOC] Cap at 100 to prevent extremely large queries that could degrade DB performance.
        if len(idxs) > 100:
            return jsonify({
                'success': False,
                'error': 'Maximum 100 IDXs per request'
            }), 400

        # [DOC] If the token is scoped to a single user, bulk lookup is not allowed
        # [DOC] (it would be odd — and potentially a scope bypass — to request many users with a single-user token).
        if access_token.scope:
            try:
                scope = json.loads(access_token.scope)
                if 'user_idx' in scope:
                    return jsonify({
                        'success': False,
                        'error': 'Bulk lookup not allowed with user-specific scope'
                    }), 403
            except json.JSONDecodeError:
                pass

        # [DOC] .in_() generates SQL IN (...) clause — fetches all matching users in one query.
        users = db.query(User).filter(User.idx.in_(idxs)).all()

        results = []
        for user in users:
            results.append({
                'idx': user.idx,
                'real_name': user.full_name,
                'pan_card': user.pan_card
            })

        # [DOC] Log the bulk lookup as a single audit entry (not one per IDX, to keep the log manageable).
        audit_log = AccessAuditLog(
            access_token_id=access_token.id,
            accessed_by=access_token.granted_to,
            action="BULK_LOOKUP_IDX_TO_NAME",
            target_idx=None,  # [DOC] Bulk operation: no single target IDX — use idx_count in details instead.
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
            'found_count': len(results),    # [DOC] May be less than requested_count if some IDXs were not found.
            'accessed_by': access_token.granted_to
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@idx_registry_bp.route('/verify-token', methods=['GET'])
@require_access_token  # [DOC] Also protected by require_access_token — the token validates itself.
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
        # [DOC] If we reach here, require_access_token already confirmed the token is valid.
        # [DOC] This endpoint just returns the token metadata so the CA/Gov portal can display it.
        return jsonify({
            'success': True,
            'token_info': {
                'role': access_token.role.value,
                'granted_to': access_token.granted_to,
                'granted_by': access_token.granted_by,
                'purpose': access_token.purpose,
                'granted_at': access_token.granted_at.isoformat(),
                'expires_at': access_token.expires_at.isoformat(),
                # [DOC] Deserialise scope back to a dict so the client gets structured JSON, not a raw string.
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
