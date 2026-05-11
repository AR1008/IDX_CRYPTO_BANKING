# [DOC] Travel Accounts API — lets users create a temporary, spending-capped foreign account for a trip.
# [DOC] Funds are transferred from a domestic bank account, converted at the current forex rate,
# [DOC] and the ZK system enforces the per-trip spending limit without revealing the amount publicly.

"""
Travel Accounts API Routes
Purpose: API endpoints for international travel accounts

Endpoints:
- GET /api/travel/foreign-banks - List available foreign banks
- GET /api/travel/forex-rates - Get forex rates
- POST /api/travel/create - Create travel account
- GET /api/travel/accounts - Get user's travel accounts
- GET /api/travel/accounts/{id} - Get travel account details
- POST /api/travel/accounts/{id}/close - Close travel account
"""

# [DOC] Blueprint groups routes under /api/travel prefix.
from flask import Blueprint, request, jsonify
# [DOC] Decimal is used for all monetary arithmetic — avoids the floating-point rounding errors of float.
from decimal import Decimal
# [DOC] datetime and timedelta are used to check cache freshness.
from datetime import datetime, timedelta
# [DOC] Optional / Tuple / List are type hints — they document what types variables hold.
from typing import Optional, Tuple, List

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
# [DOC] TravelAccountService handles all business logic for travel accounts (creation, closing, etc.).
from core.services.travel_account_service import TravelAccountService


travel_accounts_bp = Blueprint('travel_accounts', __name__, url_prefix='/api/travel')


# [DOC] In-memory cache for forex rates — avoids a DB query on every rate-check request.
# [DOC] Forex rates change infrequently (banks update them 1–4 times daily), so caching for 1 hour is safe.
class ForexRateCache:
    """Simple time-based cache for forex rates"""

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache

        Args:
            ttl_seconds: Time to live in seconds (default: 1 hour)
        """
        # [DOC] ttl_seconds controls how long we serve stale data before going back to the DB.
        self.ttl_seconds = ttl_seconds
        # [DOC] _cache stores a tuple of (timestamp_when_cached, list_of_ForexRate_objects).
        # [DOC] Optional[Tuple[...]] means it can be None (empty cache) or the tuple.
        self._cache: Optional[Tuple[datetime, List]] = None

    def get(self, db) -> Optional[List]:
        """
        Get cached forex rates if still valid

        Args:
            db: Database session

        Returns:
            List of ForexRate objects if cache valid, None otherwise
        """
        # [DOC] None means we've never cached or the cache was explicitly invalidated.
        if self._cache is None:
            return None

        cached_time, cached_rates = self._cache

        # [DOC] If more than ttl_seconds have passed since we cached, the data is stale — discard it.
        if datetime.utcnow() - cached_time > timedelta(seconds=self.ttl_seconds):
            self._cache = None
            return None

        # [DOC] Cache is still fresh — return the stored list without hitting the DB.
        return cached_rates

    def set(self, rates: List) -> None:
        """
        Cache forex rates with current timestamp

        Args:
            rates: List of ForexRate objects to cache
        """
        # [DOC] Store (now, rates) so get() can later compute how old the cache is.
        self._cache = (datetime.utcnow(), rates)

    def invalidate(self) -> None:
        """Invalidate cache (force refresh on next request)"""
        # [DOC] Setting to None makes get() return None, triggering a fresh DB query next call.
        self._cache = None


# [DOC] Module-level singleton cache — shared across all requests to this process.
_forex_rate_cache = ForexRateCache(ttl_seconds=3600)


@travel_accounts_bp.route('/foreign-banks', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_foreign_banks(current_user, db):
    """
    Get list of foreign banks

    Returns:
        JSON: {success: true, banks: [...]}
    """
    try:
        # [DOC] Import inside function to avoid circular imports at module load time.
        from database.models.foreign_bank import ForeignBank

        # [DOC] Filter to only active foreign banks (is_active=True); inactive ones are delisted.
        banks = db.query(ForeignBank).filter(ForeignBank.is_active == True).all()

        return jsonify({
            'success': True,
            'banks': [b.to_dict() for b in banks],
            'count': len(banks)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@travel_accounts_bp.route('/forex-rates', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_forex_rates(current_user, db):
    """
    Get forex rates (with caching)

    PERFORMANCE OPTIMIZATION: Forex rates are cached for 1 hour to reduce database queries

    Query params:
        from_currency: Source currency (optional)
        to_currency: Target currency (optional)
        force_refresh: Force cache refresh (optional, default: false)

    Returns:
        JSON: {success: true, rates: [...], cached: bool}
    """
    try:
        from database.models.forex_rate import ForexRate

        # [DOC] ?force_refresh=true bypasses the cache — useful when an admin has just updated rates.
        force_refresh = request.args.get('force_refresh', '').lower() == 'true'

        # [DOC] If force_refresh is requested, skip the cache check entirely (pass None explicitly).
        cached_rates = None if force_refresh else _forex_rate_cache.get(db)
        from_cache = False

        if cached_rates is not None:
            # [DOC] Serve from memory — no DB query needed.
            rates = cached_rates
            from_cache = True
        else:
            # [DOC] Cache miss: query the DB for all active forex rates.
            query = db.query(ForexRate).filter(ForexRate.is_active == True)
            rates = query.all()
            # [DOC] Populate the cache so the next request within 1 hour won't hit the DB.
            _forex_rate_cache.set(rates)

        # [DOC] Apply optional currency filters on the already-fetched list (cheaper than adding WHERE clauses).
        from_curr = request.args.get('from_currency')
        to_curr = request.args.get('to_currency')

        filtered_rates = rates
        if from_curr:
            # [DOC] List comprehension filters in-memory — works on both cached and fresh results.
            filtered_rates = [r for r in filtered_rates if r.from_currency == from_curr]
        if to_curr:
            filtered_rates = [r for r in filtered_rates if r.to_currency == to_curr]

        return jsonify({
            'success': True,
            'rates': [r.to_dict() for r in filtered_rates],
            'count': len(filtered_rates),
            'cached': from_cache,  # [DOC] Tells the client whether this came from cache or DB.
            'cache_age_seconds': (
                # [DOC] Compute how many seconds ago the cache was populated (only if cache exists).
                int((datetime.utcnow() - _forex_rate_cache._cache[0]).total_seconds())
                if _forex_rate_cache._cache else 0
            )
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@travel_accounts_bp.route('/create', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('transaction_create'))
@require_auth
def create_travel_account(current_user, db):
    """
    Create travel account

    Request body:
        {
            "source_account_id": 1,
            "foreign_bank_code": "CITI_USA",
            "inr_amount": 100000,
            "duration_days": 30
        }

    Returns:
        JSON: {success: true, travel_account: {...}}
    """
    try:
        data = request.get_json()

        # [DOC] Check that all mandatory fields are present before doing any type conversion.
        required = ['source_account_id', 'foreign_bank_code', 'inr_amount']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # [DOC] Reject non-numeric types early before attempting Decimal conversion.
        if not isinstance(data.get('inr_amount'), (int, float, str)):
            return jsonify({
                'success': False,
                'error': 'Amount must be a number'
            }), 400

        try:
            # [DOC] Convert via str() first so Decimal handles both int and float inputs correctly.
            # [DOC] e.g. Decimal(str(1.005)) = Decimal('1.005'), but Decimal(1.005) may give floating-point noise.
            inr_amount = Decimal(str(data['inr_amount']))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid amount format'
            }), 400

        # [DOC] Business rule: amount must be a positive number.
        if inr_amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Amount must be positive'
            }), 400

        # [DOC] Business rule: travel account maximum deposit is ₹1 crore (10,000,000).
        MAX_DEPOSIT_AMOUNT = Decimal('10000000.00')
        if inr_amount > MAX_DEPOSIT_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount exceeds maximum deposit limit of ₹{MAX_DEPOSIT_AMOUNT:,.2f}'
            }), 400

        # [DOC] Business rule: minimum deposit is ₹1,000 — below this forex conversion isn't worthwhile.
        MIN_DEPOSIT_AMOUNT = Decimal('1000.00')
        if inr_amount < MIN_DEPOSIT_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Travel account deposits must be at least ₹{MIN_DEPOSIT_AMOUNT}'
            }), 400

        # [DOC] Delegate actual creation (forex conversion, ZK limit commitment, DB writes) to the service layer.
        service = TravelAccountService(db)
        travel_account = service.create_travel_account(
             current_user.idx,
            data['source_account_id'],
            data['foreign_bank_code'],
            inr_amount,
            data.get('duration_days', 30)  # [DOC] Default trip duration is 30 days if not specified.
        )

        return jsonify({
            'success': True,
            'message': 'Travel account created',
            'travel_account': travel_account.to_dict()
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


@travel_accounts_bp.route('/accounts', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_travel_accounts(current_user, db):
    """
    Get user's travel accounts

    Returns:
        JSON: {success: true, accounts: [...]}
    """
    try:
        service = TravelAccountService(db)
        # [DOC] get_user_travel_accounts() returns all travel accounts belonging to this IDX.
        accounts = service.get_user_travel_accounts(current_user.idx)

        return jsonify({
            'success': True,
            'accounts': [acc.to_dict() for acc in accounts],
            'count': len(accounts)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@travel_accounts_bp.route('/accounts/<int:account_id>', methods=['GET'])
@limiter.limit(lambda: get_rate_limit('transaction_status'))
@require_auth
def get_travel_account(current_user, db, account_id):
    """
    Get travel account details

    Returns:
        JSON: {success: true, account: {...}}
    """
    try:
        service = TravelAccountService(db)
        account = service.get_travel_account(account_id)

        if not account:
            return jsonify({
                'success': False,
                'error': 'Travel account not found'
            }), 404

        # [DOC] Ownership check: user A must not be able to read user B's travel account details.
        if account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403   # [DOC] 403 Forbidden (authenticated but not authorised for this resource).

        return jsonify({
            'success': True,
            'account': account.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@travel_accounts_bp.route('/accounts/<int:account_id>/close', methods=['POST'])
@limiter.limit(lambda: get_rate_limit('transaction_create'))
@require_auth
def close_travel_account(current_user, db, account_id):
    """
    Close travel account

    Request body:
        {
            "reason": "Trip completed"
        }

    Returns:
        JSON: {success: true, result: {...}}
    """
    try:
        # [DOC] or {} ensures data is always a dict even if the client sends no body.
        data = request.get_json() or {}

        # [DOC] Re-fetch and ownership-check before closing, in case account_id was guessed.
        service = TravelAccountService(db)
        account = service.get_travel_account(account_id)

        if not account:
            return jsonify({
                'success': False,
                'error': 'Travel account not found'
            }), 404

        if account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403

        # [DOC] close_travel_account() converts remaining foreign balance back to INR and credits it.
        result = service.close_travel_account(
            account_id,
            data.get('reason', 'Trip completed')  # [DOC] Default reason if client doesn't provide one.
        )

        return jsonify({
            'success': True,
            'message': 'Travel account closed',
            'result': result
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
