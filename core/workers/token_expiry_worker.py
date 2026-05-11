# [DOC] Token Expiry Worker — a standalone script (or cron job) that cleans up expired access tokens.
# [DOC] Access tokens (granted to CAs and government) have a fixed lifespan (7–90 days).
# [DOC] This script enforces that lifespan even if the admin forgets to manually revoke them.
# [DOC] Run: python3 -m core.workers.token_expiry_worker  OR via cron every hour.

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
# [DOC] pathlib.Path is used to find the project root and add it to sys.path so imports work correctly.
from pathlib import Path

# [DOC] Compute the absolute path to the project root (two levels up from this file).
project_root = Path(__file__).parent.parent.parent
# [DOC] Insert at position 0 so our project modules take precedence over installed packages.
sys.path.insert(0, str(project_root))

from database.connection import SessionLocal
# [DOC] AccessToken: the row we set is_active=False on; AccessAuditLog: the immutable record we write.
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
        # [DOC] "now" is the reference timestamp — tokens with expires_at < now are overdue.
        now = datetime.now()

        # [DOC] Query: is_active=True (not already revoked) AND expires_at < now (past their deadline).
        expired_tokens = db.query(AccessToken).filter(
            AccessToken.is_active == True,
            AccessToken.expires_at < now
        ).all()

        revoked_count = 0

        for token in expired_tokens:
            # [DOC] Deactivate the token — future API calls using this UUID will be rejected.
            token.is_active = False
            token.revoked_at = now
            token.revoked_by = "SYSTEM_AUTO_REVOKE"  # [DOC] Distinguishes automatic revocations from admin-initiated ones.

            # [DOC] Write an audit log entry for every auto-revocation so there's a paper trail.
            audit_log = AccessAuditLog(
                access_token_id=token.id,
                accessed_by="SYSTEM",                # [DOC] "SYSTEM" actor indicates no human initiated this.
                action="AUTO_REVOKE_EXPIRED_TOKEN",
                target_idx=None,                     # [DOC] No target IDX — this is a housekeeping action, not a lookup.
                details=json.dumps({
                    'granted_to': token.granted_to,
                    'role': token.role.value,
                    'expired_at': token.expires_at.isoformat(),
                    'auto_revoked_at': now.isoformat()
                }),
                ip_address="127.0.0.1"  # [DOC] Localhost indicates the action came from the server process itself.
            )
            db.add(audit_log)

            revoked_count += 1

            print(f"✅ Auto-revoked token for {token.granted_to} "
                  f"(expired at {token.expires_at.isoformat()})")

        # [DOC] Commit all revocations and their audit logs in a single transaction.
        db.commit()

        return revoked_count

    except Exception as e:
        print(f"❌ Error revoking expired tokens: {e}")
        # [DOC] Rollback on error — partial revocations could leave the DB in an inconsistent state.
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
        # [DOC] cutoff = now + hours: tokens expiring between now and this timestamp are "expiring soon".
        cutoff = now + timedelta(hours=hours)

        # [DOC] Query: active AND not yet expired (> now) AND expiring before the cutoff.
        expiring_soon = db.query(AccessToken).filter(
            AccessToken.is_active == True,
            AccessToken.expires_at > now,   # [DOC] Still valid right now.
            AccessToken.expires_at < cutoff  # [DOC] But will expire within the warning window.
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
        # [DOC] Total ever issued (includes revoked and expired rows — we never delete them).
        total_tokens = db.query(AccessToken).count()
        # [DOC] Tokens where is_active=True (may still be expired if the worker hasn't run yet).
        active_tokens = db.query(AccessToken).filter(
            AccessToken.is_active == True
        ).count()

        now = datetime.now()
        # [DOC] Truly valid tokens: active AND not yet expired.
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
        # [DOC] Revoked/expired = everything that is no longer active.
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

    # [DOC] Print current state before making changes — useful for audit logs and dashboards.
    print_token_stats()

    print("Checking for expired tokens...\n")
    revoked = revoke_expired_tokens()

    if revoked > 0:
        print(f"\n✅ Auto-revoked {revoked} expired token(s)")
    else:
        print("\n✅ No expired tokens found")

    # [DOC] Warn about tokens expiring in the next 24 hours so admins can notify the affected CAs/Gov.
    print("\nChecking for tokens expiring in next 24 hours...\n")
    expiring = get_expiring_soon_tokens(hours=24)

    if expiring:
        print(f"⚠️  {len(expiring)} token(s) expiring soon:")
        for token in expiring:
            # [DOC] Compute human-readable time remaining for each token.
            time_left = token.expires_at - datetime.now()
            hours_left = int(time_left.total_seconds() / 3600)
            print(f"   - {token.granted_to} ({token.role.value}) - "
                  f"expires in {hours_left} hours")
    else:
        print("✅ No tokens expiring in next 24 hours")

    # [DOC] Print stats again after revocation so the change is visible in one run's output.
    print("\n" + "=" * 50)
    print("FINAL STATISTICS")
    print("=" * 50)
    print_token_stats()

    print(f"Completed at: {datetime.now().isoformat()}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
