"""
Statement API Routes
Purpose: Generate and download transaction statements

Endpoints:
- POST /api/statements/generate - Generate statement (CSV)
- GET /api/statements/download/{statement_id} - Download generated statement
- POST /api/statements/verify - Verify statement signature
"""

# [DOC] Blueprint groups these routes under a URL prefix; request provides HTTP data; jsonify returns JSON; send_file streams a file download
from flask import Blueprint, request, jsonify, send_file
# [DOC] datetime is used to parse ISO date strings and calculate expiry times; timedelta adds durations
from datetime import datetime, timedelta
# [DOC] Decimal is imported but not used directly here — present for potential future amount handling
from decimal import Decimal
# [DOC] io.BytesIO creates an in-memory byte stream so CSV content can be sent as a file download without writing to disk
import io
# [DOC] hashlib provides SHA-256 for signature verification
import hashlib
# [DOC] uuid.uuid4() generates a random unique ID for each generated statement
import uuid
# [DOC] os and tempfile are imported but not actively used — likely left from an earlier disk-based implementation
import os
import tempfile

# [DOC] require_auth validates the JWT Bearer token and injects (current_user, db) into the route handler
from api.middleware.auth import require_auth
# [DOC] limiter enforces per-endpoint rate limits; get_rate_limit fetches the rule string from settings
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] StatementService generates CSV content, computes signatures, and verifies statement integrity
from core.services.statement_service import StatementService


# [DOC] All routes in this blueprint are served under /api/statements
statements_bp = Blueprint('statements', __name__, url_prefix='/api/statements')

# [DOC] _statement_storage is an in-memory dict: statement_id → {user_idx, content, signature, expires_at, ...}
# [DOC] Production replacement: store in Redis (with TTL) or S3 (with lifecycle rules) so statements survive server restarts
# Temporary storage for generated statements (in-memory for now)
# Production: Use Redis or S3 with expiry
_statement_storage = {}


@statements_bp.route('/generate', methods=['POST'])
# [DOC] Rate-limit statement generation using the 'statement_generate' rule from settings
@limiter.limit(lambda: get_rate_limit('statement_generate'))
# [DOC] require_auth ensures only the authenticated user can request their own statement
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
        # [DOC] Parse the JSON body to get date range and format preferences
        data = request.get_json()

        # [DOC] Both start_date and end_date are required — without both the date range is undefined
        # Validate required fields
        if 'start_date' not in data or 'end_date' not in data:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date are required'
            }), 400

        # [DOC] fromisoformat() parses "YYYY-MM-DD" (and "YYYY-MM-DDTHH:MM:SS") into a Python datetime object
        # Parse dates
        try:
            start_date = datetime.fromisoformat(data['start_date'])
            end_date = datetime.fromisoformat(data['end_date'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format. Use ISO format: YYYY-MM-DD'
            }), 400

        # [DOC] start_date must be earlier than end_date — a reversed range produces zero or negative results
        # Validate date range
        if start_date > end_date:
            return jsonify({
                'success': False,
                'error': 'start_date must be before end_date'
            }), 400

        # [DOC] Cap the range at 365 days — prevents accidentally requesting multi-year data dumps that overload the DB
        # Limit to 1 year range
        if (end_date - start_date).days > 365:
            return jsonify({
                'success': False,
                'error': 'Date range cannot exceed 1 year'
            }), 400

        # [DOC] Default format is CSV; PDF is listed as a future option but not yet implemented
        # Get format (default CSV)
        format_type = data.get('format', 'csv').lower()
        if format_type not in ['csv', 'pdf']:
            return jsonify({
                'success': False,
                'error': 'Format must be "csv" or "pdf"'
            }), 400

        if format_type == 'pdf':
            # [DOC] Return HTTP 501 Not Implemented — honest signal that PDF is planned but not ready
            return jsonify({
                'success': False,
                'error': 'PDF format not yet implemented. Use "csv" for now.'
            }), 501

        # [DOC] generate_csv_statement queries the transaction history and formats it as a CSV string with a HMAC signature appended
        # Generate statement
        service = StatementService(db)

        csv_content, signature = service.generate_csv_statement(
            current_user.idx,
            start_date,
            end_date,
            include_signature=True
        )

        # [DOC] get_statement_metadata returns summary info: transaction count, total sent, total received, date range
        metadata = service.get_statement_metadata(
            current_user.idx,
            start_date,
            end_date
        )

        # [DOC] uuid4() creates a random 128-bit ID — used as the key in _statement_storage and in the download URL
        # Generate statement ID
        statement_id = str(uuid.uuid4())

        # [DOC] The statement is stored for 24 hours — after that it is cleaned up and the user must regenerate
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

        # [DOC] Return the statement_id and a ready-to-use download_url — the client can GET that URL to stream the file
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
# [DOC] Rate-limit downloads separately from generation to prevent bulk scraping of statement data
@limiter.limit(lambda: get_rate_limit('statement_download'))
@require_auth
def download_statement(current_user, db, statement_id):
    """
    Download generated statement

    Returns:
        File download (CSV)
    """
    try:
        # [DOC] Look up the statement by its UUID — return 404 if it was never generated or already deleted
        # Check if statement exists
        if statement_id not in _statement_storage:
            return jsonify({
                'success': False,
                'error': 'Statement not found or expired'
            }), 404

        statement = _statement_storage[statement_id]

        # [DOC] Verify the requesting user owns this statement — prevents one user downloading another's statement via a guessed UUID
        # Verify ownership
        if statement['user_idx'] != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        # [DOC] Check if the 24-hour window has passed; if so, remove the stale entry and tell the client to regenerate
        # Check expiry
        if datetime.now() > statement['expires_at']:
            # Clean up expired statement
            del _statement_storage[statement_id]
            return jsonify({
                'success': False,
                'error': 'Statement expired. Please generate a new one.'
            }), 410

        # [DOC] Build a descriptive filename from the statement's date range so the downloaded file is self-documenting
        # Prepare file for download
        content = statement['content']
        filename = f"statement_{statement['metadata']['period']['start']}_to_{statement['metadata']['period']['end']}.csv"

        # [DOC] io.BytesIO wraps the CSV string (encoded as UTF-8 bytes) in a file-like object — no disk write required
        # Create in-memory file
        file_obj = io.BytesIO(content.encode('utf-8'))
        # [DOC] seek(0) resets the read position to the start — Flask reads from the current position, so this is required
        file_obj.seek(0)

        # [DOC] send_file streams the BytesIO object as an HTTP download with Content-Disposition: attachment
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
# [DOC] Rate-limit verification; this endpoint is public (no @require_auth) so CAs can verify statements without a login token
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
        # [DOC] Parse the JSON body — includes the IDX, date range, raw CSV content, and the HMAC signature to verify
        data = request.get_json()

        # [DOC] All five fields are required — verifying without any one of them is meaningless
        # Validate required fields
        required = ['user_idx', 'start_date', 'end_date', 'content', 'signature']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # [DOC] Parse the date strings back to datetime objects so StatementService can regenerate the expected signature
        # Parse dates
        try:
            start_date = datetime.fromisoformat(data['start_date'])
            end_date = datetime.fromisoformat(data['end_date'])
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format'
            }), 400

        # [DOC] Open a fresh DB session for the verification query — closed in the finally block
        # Verify signature
        db = SessionLocal()
        try:
            service = StatementService(db)

            # [DOC] verify_statement_signature recomputes the expected HMAC over content+IDX+dates and compares to the provided signature
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
                # [DOC] Human-readable message clarifies whether the CSV data was unmodified since generation
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
        # [DOC] Collect the IDs of all statements whose expires_at timestamp is in the past
        expired_ids = [
            sid for sid, stmt in _statement_storage.items()
            if now > stmt['expires_at']
        ]

        # [DOC] Delete each expired entry from the in-memory dict — frees memory and prevents stale data serving
        for sid in expired_ids:
            del _statement_storage[sid]

        return jsonify({
            'success': True,
            'cleaned_up': len(expired_ids),
            # [DOC] remaining tells the caller how many statements are still valid and stored in memory
            'remaining': len(_statement_storage)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# [DOC] SessionLocal is imported at the bottom (not the top) to avoid a circular import with the blueprint definition
# Add missing import
from database.connection import SessionLocal
