"""
Database Validator and Cleanup Script
Purpose: Validate database integrity, identify mismatches, and clean up inconsistencies

Features:
1. Validate all foreign key relationships
2. Identify orphaned records
3. Find session/account mismatches
4. Check data integrity (PAN format, IDX format, balances)
5. Clean up expired sessions
6. Generate comprehensive validation report

Usage:
    python3 scripts/database_validator.py --check     # Check only, no changes
    python3 scripts/database_validator.py --clean     # Clean up issues
    python3 scripts/database_validator.py --report    # Generate detailed report
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal
from database.models.user import User
from database.models.bank import Bank
from database.models.bank_account import BankAccount
from database.models.session import Session
from database.models.transaction import Transaction
from database.models.recipient import Recipient
from sqlalchemy import func


class DatabaseValidator:
    """Comprehensive database validation and cleanup"""

    def __init__(self):
        self.db = SessionLocal()
        self.issues = []
        self.warnings = []
        self.stats = {}

    def __del__(self):
        self.db.close()

    def log_issue(self, category: str, severity: str, message: str, data: dict = None):
        """Log an issue found during validation"""
        self.issues.append({
            'category': category,
            'severity': severity,  # 'critical', 'warning', 'info'
            'message': message,
            'data': data or {},
            'timestamp': datetime.now().isoformat()
        })

    def validate_pan_format(self) -> int:
        """
        Validate PAN card format for all users
        Format: 5 letters + 4 digits + 1 letter (e.g., ABCDE1234F)
        """
        print("\n[1/12] Validating PAN card formats...")

        pan_pattern = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
        invalid_count = 0

        users = self.db.query(User).all()
        for user in users:
            if not pan_pattern.match(user.pan_card):
                invalid_count += 1
                self.log_issue(
                    category='PAN_FORMAT',
                    severity='critical',
                    message=f"Invalid PAN format for user {user.full_name}",
                    data={
                        'user_id': user.id,
                        'idx': user.idx,
                        'pan_card': user.pan_card,
                        'expected_format': '5 letters + 4 digits + 1 letter'
                    }
                )

        print(f"  ✅ Validated {len(users)} users, found {invalid_count} invalid PANs")
        self.stats['total_users'] = len(users)
        self.stats['invalid_pans'] = invalid_count
        return invalid_count

    def validate_idx_format(self) -> int:
        """
        Validate IDX format for all users
        Format: IDX_ + 64 hex characters
        """
        print("\n[2/12] Validating IDX formats...")

        idx_pattern = re.compile(r'^IDX_[a-f0-9]{64}$')
        invalid_count = 0

        users = self.db.query(User).all()
        for user in users:
            if not idx_pattern.match(user.idx):
                invalid_count += 1
                self.log_issue(
                    category='IDX_FORMAT',
                    severity='critical',
                    message=f"Invalid IDX format for user {user.full_name}",
                    data={
                        'user_id': user.id,
                        'idx': user.idx,
                        'length': len(user.idx),
                        'expected_format': 'IDX_ + 64 hex characters'
                    }
                )

        print(f"  ✅ Validated {len(users)} IDXs, found {invalid_count} invalid")
        self.stats['invalid_idxs'] = invalid_count
        return invalid_count

    def validate_balances(self) -> int:
        """Validate all balances are non-negative"""
        print("\n[3/12] Validating balances...")

        negative_count = 0

        # Check user balances
        users_with_negative = self.db.query(User).filter(User.balance < 0).all()
        for user in users_with_negative:
            negative_count += 1
            self.log_issue(
                category='NEGATIVE_BALANCE',
                severity='critical',
                message=f"User has negative balance: {user.full_name}",
                data={
                    'user_id': user.id,
                    'idx': user.idx,
                    'balance': str(user.balance)
                }
            )

        # Check bank account balances
        accounts_with_negative = self.db.query(BankAccount).filter(BankAccount.balance < 0).all()
        for account in accounts_with_negative:
            negative_count += 1
            self.log_issue(
                category='NEGATIVE_BALANCE',
                severity='critical',
                message=f"Bank account has negative balance",
                data={
                    'account_id': account.id,
                    'user_idx': account.user_idx,
                    'bank_code': account.bank_code,
                    'balance': str(account.balance)
                }
            )

        print(f"  ✅ Checked balances, found {negative_count} negative balances")
        self.stats['negative_balances'] = negative_count
        return negative_count

    def validate_sessions(self) -> Dict[str, int]:
        """Validate session integrity"""
        print("\n[4/12] Validating sessions...")

        issues = {
            'expired_active': 0,
            'orphaned': 0,
            'invalid_bank_account': 0
        }

        sessions = self.db.query(Session).all()

        for session in sessions:
            # Check if expired but still marked active
            if session.is_active and session.is_expired():
                issues['expired_active'] += 1
                self.log_issue(
                    category='SESSION_EXPIRED',
                    severity='warning',
                    message=f"Session is expired but still active",
                    data={
                        'session_id': session.session_id,
                        'user_idx': session.user_idx,
                        'bank_name': session.bank_name,
                        'expires_at': session.expires_at.isoformat(),
                        'expired_hours_ago': abs(session.time_remaining().total_seconds() / 3600)
                    }
                )

            # Check if user exists
            user = self.db.query(User).filter(User.idx == session.user_idx).first()
            if not user:
                issues['orphaned'] += 1
                self.log_issue(
                    category='ORPHANED_SESSION',
                    severity='critical',
                    message=f"Session belongs to non-existent user",
                    data={
                        'session_id': session.session_id,
                        'user_idx': session.user_idx
                    }
                )

            # Check if bank account exists
            if session.bank_account_id:
                account = self.db.query(BankAccount).filter(BankAccount.id == session.bank_account_id).first()
                if not account:
                    issues['invalid_bank_account'] += 1
                    self.log_issue(
                        category='INVALID_BANK_ACCOUNT',
                        severity='warning',
                        message=f"Session references non-existent bank account",
                        data={
                            'session_id': session.session_id,
                            'bank_account_id': session.bank_account_id
                        }
                    )

        print(f"  ✅ Validated {len(sessions)} sessions")
        print(f"     - Expired but active: {issues['expired_active']}")
        print(f"     - Orphaned: {issues['orphaned']}")
        print(f"     - Invalid bank account: {issues['invalid_bank_account']}")

        self.stats['total_sessions'] = len(sessions)
        self.stats['session_issues'] = issues
        return issues

    def validate_bank_accounts(self) -> Dict[str, int]:
        """Validate bank account integrity"""
        print("\n[5/12] Validating bank accounts...")

        issues = {
            'orphaned': 0,
            'invalid_bank_code': 0,
            'duplicate_account_numbers': 0
        }

        accounts = self.db.query(BankAccount).all()
        valid_bank_codes = [b.bank_code for b in self.db.query(Bank).all()]

        for account in accounts:
            # Check if user exists
            user = self.db.query(User).filter(User.idx == account.user_idx).first()
            if not user:
                issues['orphaned'] += 1
                self.log_issue(
                    category='ORPHANED_ACCOUNT',
                    severity='critical',
                    message=f"Bank account belongs to non-existent user",
                    data={
                        'account_id': account.id,
                        'user_idx': account.user_idx,
                        'bank_code': account.bank_code
                    }
                )

            # Check if bank code is valid
            if account.bank_code not in valid_bank_codes:
                issues['invalid_bank_code'] += 1
                self.log_issue(
                    category='INVALID_BANK_CODE',
                    severity='warning',
                    message=f"Bank account has invalid bank code",
                    data={
                        'account_id': account.id,
                        'bank_code': account.bank_code,
                        'valid_codes': valid_bank_codes
                    }
                )

        # Check for duplicate account numbers
        from sqlalchemy import func
        duplicates = self.db.query(
            BankAccount.account_number,
            func.count(BankAccount.id)
        ).group_by(BankAccount.account_number).having(func.count(BankAccount.id) > 1).all()

        for acc_num, count in duplicates:
            issues['duplicate_account_numbers'] += count - 1
            self.log_issue(
                category='DUPLICATE_ACCOUNT_NUMBER',
                severity='critical',
                message=f"Duplicate account number found",
                data={
                    'account_number': acc_num,
                    'count': count
                }
            )

        print(f"  ✅ Validated {len(accounts)} bank accounts")
        print(f"     - Orphaned: {issues['orphaned']}")
        print(f"     - Invalid bank codes: {issues['invalid_bank_code']}")
        print(f"     - Duplicate account numbers: {issues['duplicate_account_numbers']}")

        self.stats['total_bank_accounts'] = len(accounts)
        self.stats['bank_account_issues'] = issues
        return issues

    def validate_transactions(self) -> Dict[str, int]:
        """Validate transaction integrity"""
        print("\n[6/12] Validating transactions...")

        issues = {
            'orphaned_sender': 0,
            'orphaned_receiver': 0,
            'invalid_amounts': 0,
            'invalid_status': 0
        }

        transactions = self.db.query(Transaction).all()

        for tx in transactions:
            # Check if sender exists
            sender = self.db.query(User).filter(User.idx == tx.sender_idx).first()
            if not sender:
                issues['orphaned_sender'] += 1
                self.log_issue(
                    category='ORPHANED_TRANSACTION',
                    severity='critical',
                    message=f"Transaction has non-existent sender",
                    data={
                        'transaction_id': tx.id,
                        'transaction_hash': tx.transaction_hash,
                        'sender_idx': tx.sender_idx
                    }
                )

            # Check if receiver exists
            receiver = self.db.query(User).filter(User.idx == tx.receiver_idx).first()
            if not receiver:
                issues['orphaned_receiver'] += 1
                self.log_issue(
                    category='ORPHANED_TRANSACTION',
                    severity='critical',
                    message=f"Transaction has non-existent receiver",
                    data={
                        'transaction_id': tx.id,
                        'transaction_hash': tx.transaction_hash,
                        'receiver_idx': tx.receiver_idx
                    }
                )

            # Check if amounts are valid
            if tx.amount <= 0:
                issues['invalid_amounts'] += 1
                self.log_issue(
                    category='INVALID_AMOUNT',
                    severity='critical',
                    message=f"Transaction has invalid amount",
                    data={
                        'transaction_id': tx.id,
                        'amount': str(tx.amount)
                    }
                )

        print(f"  ✅ Validated {len(transactions)} transactions")
        print(f"     - Orphaned senders: {issues['orphaned_sender']}")
        print(f"     - Orphaned receivers: {issues['orphaned_receiver']}")
        print(f"     - Invalid amounts: {issues['invalid_amounts']}")

        self.stats['total_transactions'] = len(transactions)
        self.stats['transaction_issues'] = issues
        return issues

    def validate_recipients(self) -> Dict[str, int]:
        """Validate recipient relationships"""
        print("\n[7/12] Validating recipients...")

        issues = {
            'orphaned_owner': 0,
            'orphaned_recipient': 0,
            'invalid_sessions': 0
        }

        recipients = self.db.query(Recipient).all()

        for recipient in recipients:
            # Check if owner exists
            owner = self.db.query(User).filter(User.idx == recipient.user_idx).first()
            if not owner:
                issues['orphaned_owner'] += 1
                self.log_issue(
                    category='ORPHANED_RECIPIENT',
                    severity='critical',
                    message=f"Recipient has non-existent owner",
                    data={
                        'recipient_id': recipient.id,
                        'owner_idx': recipient.user_idx,
                        'nickname': recipient.nickname
                    }
                )

            # Check if recipient user exists
            recipient_user = self.db.query(User).filter(User.idx == recipient.recipient_idx).first()
            if not recipient_user:
                issues['orphaned_recipient'] += 1
                self.log_issue(
                    category='ORPHANED_RECIPIENT',
                    severity='critical',
                    message=f"Recipient points to non-existent user",
                    data={
                        'recipient_id': recipient.id,
                        'recipient_idx': recipient.recipient_idx,
                        'nickname': recipient.nickname
                    }
                )

        print(f"  ✅ Validated {len(recipients)} recipients")
        print(f"     - Orphaned owners: {issues['orphaned_owner']}")
        print(f"     - Orphaned recipients: {issues['orphaned_recipient']}")

        self.stats['total_recipients'] = len(recipients)
        self.stats['recipient_issues'] = issues
        return issues

    def find_session_account_mismatches(self) -> List[Dict]:
        """Find sessions that don't have matching bank accounts"""
        print("\n[8/12] Finding session-account mismatches...")

        mismatches = []
        sessions = self.db.query(Session).filter(Session.is_active == True).all()

        for session in sessions:
            # Look for matching bank account
            account = self.db.query(BankAccount).filter(
                BankAccount.user_idx == session.user_idx,
                BankAccount.bank_code == session.bank_name,
                BankAccount.is_active == True
            ).first()

            if not account:
                mismatches.append({
                    'session_id': session.session_id,
                    'user_idx': session.user_idx,
                    'bank_name': session.bank_name,
                    'expires_at': session.expires_at.isoformat()
                })
                self.log_issue(
                    category='SESSION_ACCOUNT_MISMATCH',
                    severity='warning',
                    message=f"Active session has no matching bank account",
                    data={
                        'session_id': session.session_id,
                        'user_idx': session.user_idx,
                        'bank_name': session.bank_name
                    }
                )

        print(f"  ✅ Found {len(mismatches)} session-account mismatches")
        self.stats['session_account_mismatches'] = len(mismatches)
        return mismatches

    def check_consortium_banks(self) -> Dict[str, int]:
        """Validate 12 consortium banks"""
        print("\n[9/12] Validating consortium banks...")

        banks = self.db.query(Bank).all()
        active_banks = self.db.query(Bank).filter(Bank.is_active == True).all()

        expected_banks = ['SBI', 'PNB', 'BOB', 'CANARA', 'UNION', 'INDIAN', 'CENTRAL', 'UCO',
                         'HDFC', 'ICICI', 'AXIS', 'KOTAK']

        bank_codes = [b.bank_code for b in banks]
        missing_banks = [b for b in expected_banks if b not in bank_codes]

        if missing_banks:
            self.log_issue(
                category='MISSING_BANKS',
                severity='critical',
                message=f"Missing consortium banks",
                data={
                    'missing_banks': missing_banks,
                    'total_banks': len(banks),
                    'expected': 12
                }
            )

        print(f"  ✅ Found {len(banks)} banks ({len(active_banks)} active)")
        if missing_banks:
            print(f"  ⚠️  Missing: {', '.join(missing_banks)}")

        self.stats['total_banks'] = len(banks)
        self.stats['active_banks'] = len(active_banks)
        self.stats['missing_banks'] = len(missing_banks)
        return {'total': len(banks), 'active': len(active_banks), 'missing': len(missing_banks)}

    def validate_foreign_keys(self) -> int:
        """Validate all foreign key relationships"""
        print("\n[10/12] Validating foreign key relationships...")

        fk_issues = 0

        # This is already partially covered by other validations
        # but we'll add specific checks here

        # Check bank_accounts.user_idx -> users.idx
        orphaned_accounts = self.db.query(BankAccount).filter(
            ~BankAccount.user_idx.in_(self.db.query(User.idx))
        ).count()

        if orphaned_accounts > 0:
            fk_issues += orphaned_accounts
            self.log_issue(
                category='FK_VIOLATION',
                severity='critical',
                message=f"{orphaned_accounts} bank accounts with invalid user_idx",
                data={'count': orphaned_accounts}
            )

        # Check sessions.user_idx -> users.idx
        orphaned_sessions = self.db.query(Session).filter(
            ~Session.user_idx.in_(self.db.query(User.idx))
        ).count()

        if orphaned_sessions > 0:
            fk_issues += orphaned_sessions
            self.log_issue(
                category='FK_VIOLATION',
                severity='critical',
                message=f"{orphaned_sessions} sessions with invalid user_idx",
                data={'count': orphaned_sessions}
            )

        print(f"  ✅ Foreign key validation complete, found {fk_issues} violations")
        self.stats['fk_violations'] = fk_issues
        return fk_issues

    def check_database_size(self) -> Dict[str, int]:
        """Get database statistics"""
        print("\n[11/12] Collecting database statistics...")

        stats = {
            'users': self.db.query(User).count(),
            'banks': self.db.query(Bank).count(),
            'bank_accounts': self.db.query(BankAccount).count(),
            'sessions': self.db.query(Session).count(),
            'active_sessions': self.db.query(Session).filter(Session.is_active == True).count(),
            'transactions': self.db.query(Transaction).count(),
            'recipients': self.db.query(Recipient).count()
        }

        print(f"  📊 Database Statistics:")
        for key, value in stats.items():
            print(f"     - {key}: {value:,}")

        self.stats['table_counts'] = stats
        return stats

    def generate_report(self) -> str:
        """Generate comprehensive validation report"""
        print("\n[12/12] Generating validation report...")

        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DATABASE VALIDATION REPORT")
        report_lines.append(f"Generated: {datetime.now().isoformat()}")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Summary
        report_lines.append("SUMMARY")
        report_lines.append("-" * 80)
        total_issues = len([i for i in self.issues if i['severity'] == 'critical'])
        total_warnings = len([i for i in self.issues if i['severity'] == 'warning'])
        report_lines.append(f"Critical Issues: {total_issues}")
        report_lines.append(f"Warnings: {total_warnings}")
        report_lines.append(f"Total Checks: {len(self.issues)}")
        report_lines.append("")

        # Database Stats
        if 'table_counts' in self.stats:
            report_lines.append("DATABASE STATISTICS")
            report_lines.append("-" * 80)
            for key, value in self.stats['table_counts'].items():
                report_lines.append(f"{key.replace('_', ' ').title()}: {value:,}")
            report_lines.append("")

        # Issues by category
        if self.issues:
            report_lines.append("ISSUES BY CATEGORY")
            report_lines.append("-" * 80)

            categories = {}
            for issue in self.issues:
                cat = issue['category']
                if cat not in categories:
                    categories[cat] = {'critical': 0, 'warning': 0, 'info': 0}
                categories[cat][issue['severity']] += 1

            for category, counts in sorted(categories.items()):
                total = sum(counts.values())
                report_lines.append(f"\n{category}: {total} issues")
                if counts['critical'] > 0:
                    report_lines.append(f"  Critical: {counts['critical']}")
                if counts['warning'] > 0:
                    report_lines.append(f"  Warnings: {counts['warning']}")
                if counts['info'] > 0:
                    report_lines.append(f"  Info: {counts['info']}")
            report_lines.append("")

        # Detailed issues
        critical_issues = [i for i in self.issues if i['severity'] == 'critical']
        if critical_issues:
            report_lines.append("CRITICAL ISSUES (Details)")
            report_lines.append("-" * 80)
            for issue in critical_issues[:20]:  # Limit to first 20
                report_lines.append(f"\n[{issue['category']}]")
                report_lines.append(f"  {issue['message']}")
                if issue['data']:
                    for key, value in issue['data'].items():
                        report_lines.append(f"    {key}: {value}")
            if len(critical_issues) > 20:
                report_lines.append(f"\n... and {len(critical_issues) - 20} more critical issues")
            report_lines.append("")

        # Recommendations
        report_lines.append("RECOMMENDATIONS")
        report_lines.append("-" * 80)
        if total_issues > 0:
            report_lines.append("⚠️  CRITICAL: Database has integrity issues that need immediate attention")
            report_lines.append("   Run with --clean flag to automatically fix common issues")
        if total_warnings > 0:
            report_lines.append("ℹ️  WARNINGS: Some non-critical issues found")
            report_lines.append("   Review warnings and decide if action is needed")
        if total_issues == 0 and total_warnings == 0:
            report_lines.append("✅ Database integrity is EXCELLENT - No issues found!")

        report_lines.append("")
        report_lines.append("=" * 80)

        report = "\n".join(report_lines)

        # Save to file
        report_file = f"database_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)

        print(f"  ✅ Report saved to: {report_file}")

        return report

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions"""
        print("\n🧹 Cleaning up expired sessions...")

        expired_sessions = self.db.query(Session).filter(
            Session.expires_at < datetime.now()
        ).all()

        count = len(expired_sessions)

        for session in expired_sessions:
            self.db.delete(session)

        self.db.commit()

        print(f"  ✅ Removed {count} expired sessions")
        return count

    def cleanup_orphaned_records(self) -> Dict[str, int]:
        """Remove orphaned records"""
        print("\n🧹 Cleaning up orphaned records...")

        counts = {
            'sessions': 0,
            'bank_accounts': 0,
            'recipients': 0
        }

        # Orphaned sessions
        orphaned_sessions = self.db.query(Session).filter(
            ~Session.user_idx.in_(self.db.query(User.idx))
        ).all()

        for session in orphaned_sessions:
            self.db.delete(session)
            counts['sessions'] += 1

        # Orphaned bank accounts
        orphaned_accounts = self.db.query(BankAccount).filter(
            ~BankAccount.user_idx.in_(self.db.query(User.idx))
        ).all()

        for account in orphaned_accounts:
            self.db.delete(account)
            counts['bank_accounts'] += 1

        # Orphaned recipients
        orphaned_recipients = self.db.query(Recipient).filter(
            ~Recipient.user_idx.in_(self.db.query(User.idx))
        ).all()

        for recipient in orphaned_recipients:
            self.db.delete(recipient)
            counts['recipients'] += 1

        self.db.commit()

        print(f"  ✅ Removed {counts['sessions']} orphaned sessions")
        print(f"  ✅ Removed {counts['bank_accounts']} orphaned bank accounts")
        print(f"  ✅ Removed {counts['recipients']} orphaned recipients")

        return counts

    def run_full_validation(self, cleanup=False):
        """Run all validation checks"""
        print("\n" + "=" * 80)
        print("DATABASE VALIDATION AND CLEANUP")
        print("=" * 80)

        # Run all validations
        self.validate_pan_format()
        self.validate_idx_format()
        self.validate_balances()
        self.validate_sessions()
        self.validate_bank_accounts()
        self.validate_transactions()
        self.validate_recipients()
        self.find_session_account_mismatches()
        self.check_consortium_banks()
        self.validate_foreign_keys()
        self.check_database_size()

        # Generate report
        report = self.generate_report()

        # Cleanup if requested
        if cleanup:
            print("\n" + "=" * 80)
            print("RUNNING CLEANUP")
            print("=" * 80)
            self.cleanup_expired_sessions()
            self.cleanup_orphaned_records()
            print("\n✅ Cleanup complete!")

        # Print summary
        print("\n" + "=" * 80)
        print("VALIDATION COMPLETE")
        print("=" * 80)

        critical = len([i for i in self.issues if i['severity'] == 'critical'])
        warnings = len([i for i in self.issues if i['severity'] == 'warning'])

        if critical > 0:
            print(f"⚠️  Found {critical} CRITICAL issues")
        if warnings > 0:
            print(f"ℹ️  Found {warnings} warnings")
        if critical == 0 and warnings == 0:
            print("✅ Database is in EXCELLENT condition!")

        return report


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate and clean database')
    parser.add_argument('--check', action='store_true', help='Check only (no changes)')
    parser.add_argument('--clean', action='store_true', help='Clean up issues')
    parser.add_argument('--report', action='store_true', help='Generate detailed report')

    args = parser.parse_args()

    # Default to check mode if no args
    if not any([args.check, args.clean, args.report]):
        args.check = True

    validator = DatabaseValidator()

    if args.clean:
        validator.run_full_validation(cleanup=True)
    else:
        validator.run_full_validation(cleanup=False)


if __name__ == "__main__":
    main()
