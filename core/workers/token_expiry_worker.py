"""
Access Token Expiry Worker
Purpose: Automatically revoke expired access tokens

Runs periodically (cron job) to:
1. Find all expired but still active tokens
2. Mark them as revoked
3. Log the auto-revocation

Usage:
    # Run manually
    python3 -m core.workers.token_expiry_worker

    # Or as cron job (every hour)
    0 * * * * cd /path/to/project && python3 -m core.workers.token_expiry_worker

Security:
- Ensures expired tokens cannot be used (defense in depth)
- Provides clean audit trail of auto-revocations
- Helps admins monitor token lifecycle
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from database.connection import SessionLocal
from database.models.access_control import AccessToken, AccessAuditLog
import json


def revoke_expired_tokens():
    """
    Find and revoke all expired access tokens

    Returns:
        int: Number of tokens revoked
    """
    db = SessionLocal()

    try:
        # Find all tokens that are:
        # 1. Still marked as active
        # 2. But have expired
        now = datetime.now()

        expired_tokens = db.query(AccessToken).filter(
            AccessToken.is_active == True,
            AccessToken.expires_at < now
        ).all()

        revoked_count = 0

        for token in expired_tokens:
            # Mark as revoked
            token.is_active = False
            token.revoked_at = now
            token.revoked_by = "SYSTEM_AUTO_REVOKE"

            # Log the auto-revocation
            audit_log = AccessAuditLog(
                access_token_id=token.id,
                accessed_by="SYSTEM",
                action="AUTO_REVOKE_EXPIRED_TOKEN",
                target_idx=None,
                details=json.dumps({
                    'granted_to': token.granted_to,
                    'role': token.role.value,
                    'expired_at': token.expires_at.isoformat(),
                    'auto_revoked_at': now.isoformat()
                }),
                ip_address="127.0.0.1"
            )
            db.add(audit_log)

            revoked_count += 1

            print(f"✅ Auto-revoked token for {token.granted_to} "
                  f"(expired at {token.expires_at.isoformat()})")

        db.commit()

        return revoked_count

    except Exception as e:
        print(f"❌ Error revoking expired tokens: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def get_expiring_soon_tokens(hours=24):
    """
    Get tokens expiring within specified hours

    Args:
        hours (int): Number of hours to look ahead

    Returns:
        list: Tokens expiring soon
    """
    db = SessionLocal()

    try:
        from datetime import timedelta

        now = datetime.now()
        cutoff = now + timedelta(hours=hours)

        expiring_soon = db.query(AccessToken).filter(
            AccessToken.is_active == True,
            AccessToken.expires_at > now,
            AccessToken.expires_at < cutoff
        ).all()

        return expiring_soon

    finally:
        db.close()


def print_token_stats():
    """
    Print statistics about access tokens
    """
    db = SessionLocal()

    try:
        total_tokens = db.query(AccessToken).count()
        active_tokens = db.query(AccessToken).filter(
            AccessToken.is_active == True
        ).count()

        # Count valid (active + not expired)
        now = datetime.now()
        valid_tokens = db.query(AccessToken).filter(
            AccessToken.is_active == True,
            AccessToken.expires_at > now
        ).count()

        print("\n" + "=" * 50)
        print("ACCESS TOKEN STATISTICS")
        print("=" * 50)
        print(f"Total tokens issued: {total_tokens}")
        print(f"Active tokens: {active_tokens}")
        print(f"Valid tokens (active + not expired): {valid_tokens}")
        print(f"Revoked/Expired tokens: {total_tokens - active_tokens}")
        print("=" * 50 + "\n")

    finally:
        db.close()


def main():
    """
    Main worker function

    Run this periodically via cron job
    """
    print("\n" + "=" * 50)
    print("ACCESS TOKEN EXPIRY WORKER")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}\n")

    # Print current stats
    print_token_stats()

    # Revoke expired tokens
    print("Checking for expired tokens...\n")
    revoked = revoke_expired_tokens()

    if revoked > 0:
        print(f"\n✅ Auto-revoked {revoked} expired token(s)")
    else:
        print("\n✅ No expired tokens found")

    # Show tokens expiring soon
    print("\nChecking for tokens expiring in next 24 hours...\n")
    expiring = get_expiring_soon_tokens(hours=24)

    if expiring:
        print(f"⚠️  {len(expiring)} token(s) expiring soon:")
        for token in expiring:
            time_left = token.expires_at - datetime.now()
            hours_left = int(time_left.total_seconds() / 3600)
            print(f"   - {token.granted_to} ({token.role.value}) - "
                  f"expires in {hours_left} hours")
    else:
        print("✅ No tokens expiring in next 24 hours")

    # Print updated stats
    print("\n" + "=" * 50)
    print("FINAL STATISTICS")
    print("=" * 50)
    print_token_stats()

    print(f"Completed at: {datetime.now().isoformat()}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
