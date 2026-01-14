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

from flask import Blueprint, request, jsonify
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from api.middleware.auth import require_auth
from api.middleware.rate_limiter import limiter, get_rate_limit
from core.services.travel_account_service import TravelAccountService


travel_accounts_bp = Blueprint('travel_accounts', __name__, url_prefix='/api/travel')


# PERFORMANCE OPTIMIZATION: In-memory cache for forex rates (code review recommendation)
# Forex rates don't change frequently, so caching reduces database queries by ~95%
class ForexRateCache:
    """Simple time-based cache for forex rates"""

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache

        Args:
            ttl_seconds: Time to live in seconds (default: 1 hour)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Optional[Tuple[datetime, List]] = None

    def get(self, db) -> Optional[List]:
        """
        Get cached forex rates if still valid

        Args:
            db: Database session

        Returns:
            List of ForexRate objects if cache valid, None otherwise
        """
        if self._cache is None:
            return None

        cached_time, cached_rates = self._cache

        # Check if cache expired
        if datetime.utcnow() - cached_time > timedelta(seconds=self.ttl_seconds):
            self._cache = None
            return None

        return cached_rates

    def set(self, rates: List) -> None:
        """
        Cache forex rates with current timestamp

        Args:
            rates: List of ForexRate objects to cache
        """
        self._cache = (datetime.utcnow(), rates)

    def invalidate(self) -> None:
        """Invalidate cache (force refresh on next request)"""
        self._cache = None


# Create cache instance (1 hour TTL)
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
        from database.models.foreign_bank import ForeignBank
        
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

        # Check if force refresh requested
        force_refresh = request.args.get('force_refresh', '').lower() == 'true'

        # Try to get from cache (if not forcing refresh)
        cached_rates = None if force_refresh else _forex_rate_cache.get(db)
        from_cache = False

        if cached_rates is not None:
            # Use cached rates
            rates = cached_rates
            from_cache = True
        else:
            # Fetch from database
            query = db.query(ForexRate).filter(ForexRate.is_active == True)
            rates = query.all()

            # Cache the results
            _forex_rate_cache.set(rates)

        # Apply filters (from_currency, to_currency) to cached or fresh results
        from_curr = request.args.get('from_currency')
        to_curr = request.args.get('to_currency')

        filtered_rates = rates
        if from_curr:
            filtered_rates = [r for r in filtered_rates if r.from_currency == from_curr]
        if to_curr:
            filtered_rates = [r for r in filtered_rates if r.to_currency == to_curr]

        return jsonify({
            'success': True,
            'rates': [r.to_dict() for r in filtered_rates],
            'count': len(filtered_rates),
            'cached': from_cache,
            'cache_age_seconds': (
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
        
        # Validate
        required = ['source_account_id', 'foreign_bank_code', 'inr_amount']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400

        # INPUT VALIDATION: Type and range validation for amount (code review recommendation)
        if not isinstance(data.get('inr_amount'), (int, float, str)):
            return jsonify({
                'success': False,
                'error': 'Amount must be a number'
            }), 400

        try:
            inr_amount = Decimal(str(data['inr_amount']))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid amount format'
            }), 400

        # Validate amount is positive
        if inr_amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Amount must be positive'
            }), 400

        # Validate maximum deposit (₹1 crore)
        MAX_DEPOSIT_AMOUNT = Decimal('10000000.00')  # ₹1 crore
        if inr_amount > MAX_DEPOSIT_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Amount exceeds maximum deposit limit of ₹{MAX_DEPOSIT_AMOUNT:,.2f}'
            }), 400

        # Validate minimum deposit (₹1000)
        MIN_DEPOSIT_AMOUNT = Decimal('1000.00')  # ₹1000
        if inr_amount < MIN_DEPOSIT_AMOUNT:
            return jsonify({
                'success': False,
                'error': f'Travel account deposits must be at least ₹{MIN_DEPOSIT_AMOUNT}'
            }), 400

        # Create travel account
        service = TravelAccountService(db)
        travel_account = service.create_travel_account(
             current_user.idx,
            data['source_account_id'],
            data['foreign_bank_code'],
            inr_amount,
            data.get('duration_days', 30)
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
        
        # Check ownership
        if account.user_idx != current_user.idx:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
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
        data = request.get_json() or {}
        
        # Verify ownership
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
        
        # Close account
        result = service.close_travel_account(
            account_id,
            data.get('reason', 'Trip completed')
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