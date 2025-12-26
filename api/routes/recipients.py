"""
Recipients API Routes
Author: Ashutosh Rajesh
Purpose: Manage user's recipient list

Endpoints:
- GET /api/recipients - Get all recipients
- POST /api/recipients/add - Add new recipient
- GET /api/recipients/{nickname} - Get recipient by nickname
- PUT /api/recipients/{id}/nickname - Update nickname
- DELETE /api/recipients/{id} - Remove recipient
"""

from flask import Blueprint, request, jsonify

from api.middleware.auth import require_auth
from core.services.recipient_service import RecipientService


recipients_bp = Blueprint('recipients', __name__, url_prefix='/api/recipients')


@recipients_bp.route('', methods=['GET'])
@require_auth
def get_all_recipients(current_user, db):
    """
    Get all recipients for user
    
    Returns:
        JSON: {
            success: true,
            recipients: [
                {nickname, recipient_idx, session_id, expires_at},
                ...
            ]
        }
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
@require_auth
def add_recipient(current_user, db):
    """
    Add new recipient to contact list
    
    Request body:
        {
            "recipient_idx": "IDX_abc123...",
            "nickname": "Mom"
        }
    
    Returns:
        JSON: {success: true, recipient: {...}}
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
        
        return jsonify({
            'success': True,
            'message': f'Recipient "{nickname}" added successfully',
            'recipient': recipient.to_dict()
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


@recipients_bp.route('/<string:nickname>', methods=['GET'])
@require_auth
def get_recipient_by_nickname(current_user, db, nickname):
    """
    Get recipient by nickname
    
    URL: /api/recipients/Mom
    
    Returns:
        JSON: {success: true, recipient: {...}}
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