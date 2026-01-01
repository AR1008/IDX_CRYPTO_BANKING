"""
Statement API Routes
Purpose: Generate and download transaction statements

Endpoints:
- POST /api/statements/generate - Generate statement (CSV)
- GET /api/statements/download/{statement_id} - Download generated statement
- POST /api/statements/verify - Verify statement signature
"""

from flask import Blueprint, request, jsonify, send_file
from datetime import datetime, timedelta
from decimal import Decimal
import io
import hashlib
import uuid
import os
import tempfile

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from core.services.statement_service import StatementService


statements_bp = Blueprint('statements', __name__, url_prefix='/api/statements')

# Temporary storage for generated statements (in-memory for now)
# Production: Use Redis or S3 with expiry
_statement_storage = {}


@statements_bp.route('/generate', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('statement_generate'))
@require_auth
def generate_statement(current_user, db):
    """
    Generate transaction statement

    Request body:
        {
            "format": "csv",  # or "pdf" (future)
            "start_date": "2025-01-01",
            "end_date": "2025-12-31"
        }

    Returns:
        JSON: {
            success: true,
            statement_id: "uuid...",
            download_url: "/api/statements/download/uuid...",
            signature: "sha256...",
            metadata: {...},
            expires_at: "2025-12-28T15:00:00Z"  # 24 hours from now
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if 'start_date' not in data or 'end_date' not in data:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date are required'
            }), 400

        # Parse dates
        try:
            start_date = datetime.fromisoformat(data['start_date'])
            end_date = datetime.fromisoformat(data['end_date'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format. Use ISO format: YYYY-MM-DD'
            }), 400

        # Validate date range
        if start_date > end_date:
            return jsonify({
                'success': False,
                'error': 'start_date must be before end_date'
            }), 400

        # Limit to 1 year range
        if (end_date - start_date).days > 365:
            return jsonify({
                'success': False,
                'error': 'Date range cannot exceed 1 year'
            }), 400

        # Get format (default CSV)
        format_type = data.get('format', 'csv').lower()
        if format_type not in ['csv', 'pdf']:
            return jsonify({
                'success': False,
                'error': 'Format must be "csv" or "pdf"'
            }), 400

        if format_type == 'pdf':
            return jsonify({
                'success': False,
                'error': 'PDF format not yet implemented. Use "csv" for now.'
            }), 501

        # Generate statement
        service = StatementService(db)

        csv_content, signature = service.generate_csv_statement(
            current_user.idx,
            start_date,
            end_date,
            include_signature=True
        )

        metadata = service.get_statement_metadata(
            current_user.idx,
            start_date,
            end_date
        )

        # Generate statement ID
        statement_id = str(uuid.uuid4())

        # Store temporarily (24-hour expiry)
        expires_at = datetime.now() + timedelta(hours=24)
        _statement_storage[statement_id] = {
            'user_idx': current_user.idx,
            'content': csv_content,
            'signature': signature,
            'metadata': metadata,
            'format': format_type,
            'expires_at': expires_at,
            'created_at': datetime.now()
        }

        return jsonify({
            'success': True,
            'statement_id': statement_id,
            'download_url': f"/api/statements/download/{statement_id}",
            'signature': signature,
            'metadata': metadata,
            'expires_at': expires_at.isoformat()
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


@statements_bp.route('/download/<string:statement_id>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('statement_download'))
@require_auth
def download_statement(current_user, db, statement_id):
    """
    Download generated statement

    Returns:
        File download (CSV)
    """
    try:
        # Check if statement exists
        if statement_id not in _statement_storage:
            return jsonify({
                'success': False,
                'error': 'Statement not found or expired'
            }), 404

        statement = _statement_storage[statement_id]

        # Verify ownership
        if statement['user_idx'] != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        # Check expiry
        if datetime.now() > statement['expires_at']:
            # Clean up expired statement
            del _statement_storage[statement_id]
            return jsonify({
                'success': False,
                'error': 'Statement expired. Please generate a new one.'
            }), 410

        # Prepare file for download
        content = statement['content']
        filename = f"statement_{statement['metadata']['period']['start']}_to_{statement['metadata']['period']['end']}.csv"

        # Create in-memory file
        file_obj = io.BytesIO(content.encode('utf-8'))
        file_obj.seek(0)

        return send_file(
            file_obj,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/verify', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('statement_verify'))
def verify_statement():
    """
    Verify statement signature (public endpoint for CAs)

    Request body:
        {
            "user_idx": "IDX_...",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "content": "Date,Counterparty...",
            "signature": "abc123..."
        }

    Returns:
        JSON: {
            success: true,
            valid: true,
            verified_at: "2025-12-27T15:00:00Z"
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ['user_idx', 'start_date', 'end_date', 'content', 'signature']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # Parse dates
        try:
            start_date = datetime.fromisoformat(data['start_date'])
            end_date = datetime.fromisoformat(data['end_date'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format'
            }), 400

        # Verify signature
        db = SessionLocal()
        try:
            service = StatementService(db)

            is_valid = service.verify_statement_signature(
                data['user_idx'],
                start_date,
                end_date,
                data['content'],
                data['signature']
            )

            return jsonify({
                'success': True,
                'valid': is_valid,
                'verified_at': datetime.now().isoformat(),
                'message': 'Signature is valid' if is_valid else 'Signature is invalid or tampered'
            }), 200

        finally:
            db.close()

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/cleanup', methods=['POST'])
def cleanup_expired_statements():
    """
    Cleanup expired statements (internal/cron endpoint)

    Returns:
        JSON: {success: true, cleaned_up: 5}
    """
    try:
        now = datetime.now()
        expired_ids = [
            sid for sid, stmt in _statement_storage.items()
            if now > stmt['expires_at']
        ]

        for sid in expired_ids:
            del _statement_storage[sid]

        return jsonify({
            'success': True,
            'cleaned_up': len(expired_ids),
            'remaining': len(_statement_storage)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Add missing import
from database.connection import SessionLocal
