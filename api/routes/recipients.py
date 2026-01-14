"""
Recipients API Routes - IDX-Based (Session IDs Hidden)
Purpose: Manage user's recipient list

Security Model:
- Users add recipients by IDX only (not session IDs)
- 30-minute waiting period before first transaction (fraud prevention)
- Session IDs managed internally, NEVER shown to users

Endpoints:
- GET /api/recipients - Get all recipients
- POST /api/recipients/add - Add new recipient (30-min waiting period)
- GET /api/recipients/{nickname} - Get recipient by nickname
- PUT /api/recipients/{id}/nickname - Update nickname
- DELETE /api/recipients/{id} - Remove recipient
"""

from flask import Blueprint, request, jsonify

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from core.services.recipient_service import RecipientService


recipients_bp = Blueprint('recipients', __name__, url_prefix='/api/recipients')


@recipients_bp.route('', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('recipient_list'))
@require_auth
def get_all_recipients(current_user, db):
    """
    Get all recipients for user (IDX only, sessions hidden)

    Returns:
        JSON: {
            success: true,
            recipients: [
                {
                    id,
                    nickname,
                    recipient_idx,
                    can_transact,
                    can_transact_in_minutes (if waiting)
                },
                ...
            ]
        }

    NOTE: Session IDs are NEVER returned to users
    """
    try:
        service = RecipientService(db)
        recipients = service.get_user_recipients(current_user.idx)
        
        return jsonify({
            'success': True,
            'recipients': [r.to_dict() for r in recipients]
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@recipients_bp.route('/add', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('recipient_add'))
@require_auth
def add_recipient(current_user, db):
    """
    Add new recipient to contact list (IDX only)

    Request body:
        {
            "recipient_idx": "IDX_abc123...",
            "nickname": "Mom"
        }

    Returns:
        JSON: {
            success: true,
            recipient: {
                id,
                nickname,
                recipient_idx,
                can_transact: false,
                can_transact_in_minutes: 30
            },
            message: "30-minute waiting period in effect"
        }

    Security:
    - 30-minute waiting period before first transaction (fraud prevention)
    - Session IDs NEVER shown to users (managed internally)
    """
    try:
        data = request.get_json()

        # Validate
        if not data.get('recipient_idx'):
            return jsonify({
                'success': False,
                'error': 'recipient_idx is required'
            }), 400

        if not data.get('nickname'):
            return jsonify({
                'success': False,
                'error': 'nickname is required'
            }), 400

        recipient_idx = data['recipient_idx']
        nickname = data['nickname']

        # Add recipient
        service = RecipientService(db)
        recipient = service.add_recipient(
            current_user.idx,
            recipient_idx,
            nickname
        )

        # Build response with waiting period info
        response = {
            'success': True,
            'recipient': recipient.to_dict(),  # Sessions hidden by default
        }

        # Add waiting period message
        if not recipient.can_transact():
            remaining = recipient.time_until_can_transact()
            minutes = int(remaining.total_seconds() / 60)
            response['message'] = f'Recipient "{nickname}" added. You can send money in {minutes} minutes (fraud prevention waiting period).'
        else:
            response['message'] = f'Recipient "{nickname}" added successfully.'

        return jsonify(response), 201

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


@recipients_bp.route('/<string:nickname>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('recipient_get'))
@require_auth
def get_recipient_by_nickname(current_user, db, nickname):
    """
    Get recipient by nickname (IDX only, sessions hidden)

    URL: /api/recipients/Mom

    Returns:
        JSON: {
            success: true,
            recipient: {
                id,
                nickname,
                recipient_idx,
                can_transact
            }
        }
    """
    try:
        service = RecipientService(db)
        recipient = service.get_recipient_by_nickname(current_user.idx, nickname)
        
        if not recipient:
            return jsonify({
                'success': False,
                'error': f'Recipient "{nickname}" not found'
            }), 404
        
        return jsonify({
            'success': True,
            'recipient': recipient.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@recipients_bp.route('/<int:recipient_id>/nickname', methods=['PUT'])
@limiter.limit(lambda: get_rate_limit('recipient_update'))
@require_auth
def update_nickname(current_user, db, recipient_id):
    """
    Update recipient's nickname
    
    Request body:
        {
            "new_nickname": "Mother"
        }
    
    Returns:
        JSON: {success: true, recipient: {...}}
    """
    try:
        data = request.get_json()
        
        if not data.get('new_nickname'):
            return jsonify({
                'success': False,
                'error': 'new_nickname is required'
            }), 400
        
        service = RecipientService(db)
        recipient = service.update_nickname(recipient_id, data['new_nickname'])
        
        return jsonify({
            'success': True,
            'message': 'Nickname updated successfully',
            'recipient': recipient.to_dict()
        }), 200
        
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


@recipients_bp.route('/<int:recipient_id>', methods=['DELETE'])
@limiter.limit(lambda: get_rate_limit('recipient_delete'))
@require_auth
def remove_recipient(current_user, db, recipient_id):
    """
    Remove recipient from contact list
    
    Returns:
        JSON: {success: true, message: "..."}
    """
    try:
        service = RecipientService(db)
        service.remove_recipient(recipient_id)
        
        return jsonify({
            'success': True,
            'message': 'Recipient removed successfully'
        }), 200
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500