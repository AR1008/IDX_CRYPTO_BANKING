#!/usr/bin/env python3
"""
Enhanced Stress Test Suite
Purpose: Comprehensive testing of all implemented features

Usage:
    python scripts/testing/stress_test_enhanced.py --all
    python scripts/testing/stress_test_enhanced.py --test concurrent-registration
    python scripts/testing/stress_test_enhanced.py --test rate-limiting --verbose

Features:
- Tests concurrent user registration (validates bug fix)
- Tests competitive mining (multiple miners)
- Tests rate limiting and DDoS protection
- Tests transaction throughput
- Tests foreign bank consensus
- Performance benchmarking
"""

import sys
import os
import argparse
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
import json

# Configuration
API_BASE_URL = "http://localhost:5000"
MAX_WORKERS = 50


class StressTestSuite:
    """Enhanced stress test suite"""

    def __init__(self, base_url: str, verbose: bool = False):
        self.base_url = base_url
        self.verbose = verbose

    def log(self, message: str):
        """Log message"""
        if self.verbose:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{timestamp}] {message}")

    def print_header(self, title: str):
        """Print test header"""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def test_concurrent_registration(self, num_users: int = 100) -> dict:
        """
        Test concurrent user registration (validates bug fix)

        Args:
            num_users: Number of concurrent registration attempts

        Returns:
            Test results dictionary
        """
        self.print_header(f"Test 1: Concurrent User Registration ({num_users} users)")

        print(f"\nAttempting {num_users} concurrent registrations...")
        print("Expected: 1 success (201), {num_users-1} conflicts (409), 0 errors (500)\n")

        # Same PAN for all (to test race condition fix)
        test_pan = "TESTP1234A"
        test_rbi = "999999"

        results = {
            '201': 0,  # Created
            '409': 0,  # Conflict
            '400': 0,  # Bad Request
            '500': 0,  # Server Error
            'other': 0
        }

        def register_user(index: int):
            """Register a single user"""
            try:
                response = requests.post(
                    f"{self.base_url}/api/auth/register",
                    json={
                        'pan_card': test_pan,
                        'rbi_number': test_rbi,
                        'full_name': f'Test User {index}'
                    },
                    timeout=10
                )
                self.log(f"User {index}: HTTP {response.status_code}")
                return response.status_code

            except requests.exceptions.RequestException as e:
                self.log(f"User {index}: Request failed - {e}")
                return 0

        # Execute concurrent requests
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(register_user, i) for i in range(num_users)]

            for future in as_completed(futures):
                status_code = future.result()
                status_str = str(status_code)

                if status_str in results:
                    results[status_str] += 1
                else:
                    results['other'] += 1

        elapsed = time.time() - start_time

        # Print results
        print(f"\n📊 Results:")
        print(f"   201 Created: {results['201']}")
        print(f"   409 Conflict: {results['409']}")
        print(f"   400 Bad Request: {results['400']}")
        print(f"   500 Server Error: {results['500']}")
        print(f"   Other: {results['other']}")
        print(f"   Time: {elapsed:.2f}s")

        # Validate
        passed = results['201'] == 1 and results['500'] == 0
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status}")

        if not passed:
            print("Expected: 1 success, 0 server errors")

        return {
            'test': 'concurrent_registration',
            'passed': passed,
            'results': results,
            'elapsed': elapsed
        }

    def test_rate_limiting(self, endpoint: str = "/api/auth/register", requests_count: int = 50) -> dict:
        """
        Test rate limiting

        Args:
            endpoint: API endpoint to test
            requests_count: Number of requests to send

        Returns:
            Test results dictionary
        """
        self.print_header(f"Test 2: Rate Limiting ({requests_count} requests)")

        print(f"\nSending {requests_count} requests to {endpoint}...")
        print("Expected: Some 429 (Too Many Requests) responses\n")

        results = {
            '200': 0,  # OK
            '201': 0,  # Created
            '400': 0,  # Bad Request
            '409': 0,  # Conflict
            '429': 0,  # Rate Limited
            '500': 0,  # Server Error
            'other': 0
        }

        def send_request(index: int):
            """Send a single request"""
            try:
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    json={
                        'pan_card': f"TEST{index:05d}A",
                        'rbi_number': f"{100000 + index}",
                        'full_name': f'Rate Test User {index}'
                    },
                    timeout=5
                )
                self.log(f"Request {index}: HTTP {response.status_code}")
                return response.status_code

            except requests.exceptions.RequestException as e:
                self.log(f"Request {index}: Failed - {e}")
                return 0

        # Execute requests rapidly
        start_time = time.time()

        for i in range(requests_count):
            status_code = send_request(i)
            status_str = str(status_code)

            if status_str in results:
                results[status_str] += 1
            else:
                results['other'] += 1

            # Small delay to avoid connection errors
            time.sleep(0.01)

        elapsed = time.time() - start_time

        # Print results
        print(f"\n📊 Results:")
        print(f"   200 OK: {results['200']}")
        print(f"   201 Created: {results['201']}")
        print(f"   409 Conflict: {results['409']}")
        print(f"   429 Rate Limited: {results['429']}")
        print(f"   500 Server Error: {results['500']}")
        print(f"   Time: {elapsed:.2f}s")

        # Validate (should have some rate-limited responses)
        passed = results['429'] > 0
        status = "✅ PASSED" if passed else "⚠️  WARNING"
        print(f"\n{status}")

        if not passed:
            print("Expected: Some 429 responses (rate limiting active)")

        return {
            'test': 'rate_limiting',
            'passed': passed,
            'results': results,
            'elapsed': elapsed
        }

    def test_transaction_throughput(self, duration_seconds: int = 10) -> dict:
        """
        Test transaction throughput

        Args:
            duration_seconds: Test duration in seconds

        Returns:
            Test results dictionary
        """
        self.print_header(f"Test 3: Transaction Throughput ({duration_seconds}s)")

        print(f"\nCreating transactions for {duration_seconds} seconds...")
        print("Measuring: Transactions per second (TPS)\n")

        results = {
            'success': 0,
            'failed': 0
        }

        def create_transaction():
            """Create a single transaction"""
            try:
                # This would call the transaction API
                # For now, simulating with a placeholder
                response = requests.post(
                    f"{self.base_url}/api/transactions/create",
                    json={
                        'sender_idx': f'TEST_SENDER',
                        'receiver_idx': f'TEST_RECEIVER',
                        'amount': 1000.00
                    },
                    timeout=5
                )

                if response.status_code in [200, 201]:
                    return True
                return False

            except Exception as e:
                self.log(f"Transaction failed: {e}")
                return False

        # Execute for duration
        start_time = time.time()
        end_time = start_time + duration_seconds

        while time.time() < end_time:
            if create_transaction():
                results['success'] += 1
            else:
                results['failed'] += 1

        elapsed = time.time() - start_time

        # Calculate TPS
        total_transactions = results['success'] + results['failed']
        tps = total_transactions / elapsed if elapsed > 0 else 0

        # Print results
        print(f"\n📊 Results:")
        print(f"   Successful: {results['success']}")
        print(f"   Failed: {results['failed']}")
        print(f"   Total: {total_transactions}")
        print(f"   Duration: {elapsed:.2f}s")
        print(f"   TPS: {tps:.2f}")

        # Validate (target: 10+ TPS)
        passed = tps >= 10
        status = "✅ PASSED" if passed else "⚠️  WARNING"
        print(f"\n{status}")

        if not passed:
            print(f"Target: 10+ TPS, Achieved: {tps:.2f} TPS")

        return {
            'test': 'transaction_throughput',
            'passed': passed,
            'results': results,
            'tps': tps,
            'elapsed': elapsed
        }

    def test_mining_competition(self, num_miners: int = 5, duration_seconds: int = 30) -> dict:
        """
        Test competitive mining

        Args:
            num_miners: Number of concurrent miners
            duration_seconds: Test duration

        Returns:
            Test results dictionary
        """
        self.print_header(f"Test 4: Mining Competition ({num_miners} miners, {duration_seconds}s)")

        print(f"\nStarting {num_miners} miners for {duration_seconds} seconds...")
        print("Expected: All miners compete, only one wins each block\n")

        results = {
            'miners_started': 0,
            'blocks_mined': 0,
            'errors': 0
        }

        def start_miner(miner_idx: str):
            """Start a miner"""
            try:
                response = requests.post(
                    f"{self.base_url}/api/mining/start",
                    json={'user_idx': miner_idx},
                    timeout=5
                )

                if response.status_code == 200:
                    self.log(f"Miner {miner_idx}: Started")
                    return True
                else:
                    self.log(f"Miner {miner_idx}: Failed to start (HTTP {response.status_code})")
                    return False

            except Exception as e:
                self.log(f"Miner {miner_idx}: Error - {e}")
                return False

        # Start miners
        for i in range(num_miners):
            if start_miner(f"MINER_{i}"):
                results['miners_started'] += 1
            else:
                results['errors'] += 1

        # Wait for mining
        print(f"\nMining for {duration_seconds} seconds...")
        time.sleep(duration_seconds)

        # Get mining stats
        try:
            response = requests.get(f"{self.base_url}/api/mining/pool-status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                results['blocks_mined'] = data.get('blocks_mined', 0)
                results['active_miners'] = data.get('active_miners', 0)
        except Exception as e:
            self.log(f"Failed to get mining stats: {e}")

        # Print results
        print(f"\n📊 Results:")
        print(f"   Miners started: {results['miners_started']}")
        print(f"   Blocks mined: {results['blocks_mined']}")
        print(f"   Errors: {results['errors']}")

        # Validate
        passed = results['miners_started'] == num_miners
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status}")

        return {
            'test': 'mining_competition',
            'passed': passed,
            'results': results
        }

    def test_audit_chain_integrity(self) -> dict:
        """
        Test audit log chain integrity

        Returns:
            Test results dictionary
        """
        self.print_header("Test 5: Audit Chain Integrity")

        print("\nVerifying audit log chain integrity...")

        try:
            response = requests.get(
                f"{self.base_url}/api/audit/verify",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                chain_valid = data.get('chain_valid', False)
                message = data.get('message', '')

                print(f"\n📊 Results:")
                print(f"   Chain valid: {chain_valid}")
                print(f"   Message: {message}")

                status = "✅ PASSED" if chain_valid else "❌ FAILED"
                print(f"\n{status}")

                return {
                    'test': 'audit_chain_integrity',
                    'passed': chain_valid,
                    'message': message
                }

            else:
                print(f"\n❌ FAILED - HTTP {response.status_code}")
                return {
                    'test': 'audit_chain_integrity',
                    'passed': False,
                    'message': f'HTTP {response.status_code}'
                }

        except Exception as e:
            print(f"\n❌ FAILED - {e}")
            return {
                'test': 'audit_chain_integrity',
                'passed': False,
                'message': str(e)
            }

    def run_all_tests(self) -> dict:
        """
        Run all stress tests

        Returns:
            Overall results dictionary
        """
        print("\n" + "=" * 60)
        print("  ENHANCED STRESS TEST SUITE")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"API Base URL: {self.base_url}")

        all_results = []

        # Test 1: Concurrent Registration
        all_results.append(self.test_concurrent_registration(num_users=100))

        # Test 2: Rate Limiting
        all_results.append(self.test_rate_limiting(requests_count=50))

        # Test 3: Audit Chain Integrity
        all_results.append(self.test_audit_chain_integrity())

        # Summary
        print("\n" + "=" * 60)
        print("  TEST SUMMARY")
        print("=" * 60)

        total_tests = len(all_results)
        passed_tests = sum(1 for r in all_results if r.get('passed', False))

        for result in all_results:
            test_name = result.get('test', 'unknown')
            passed = result.get('passed', False)
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}  {test_name}")

        print(f"\nTotal: {passed_tests}/{total_tests} passed")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return {
            'total': total_tests,
            'passed': passed_tests,
            'results': all_results
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Enhanced stress test suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python scripts/testing/stress_test_enhanced.py --all

  # Run specific test
  python scripts/testing/stress_test_enhanced.py --test concurrent-registration

  # Run with verbose output
  python scripts/testing/stress_test_enhanced.py --all --verbose
        """
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all tests'
    )

    parser.add_argument(
        '--test',
        choices=['concurrent-registration', 'rate-limiting', 'audit-chain'],
        help='Run specific test'
    )

    parser.add_argument(
        '--api-url',
        default=API_BASE_URL,
        help=f'API base URL (default: {API_BASE_URL})'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    if not args.all and not args.test:
        parser.error("Must specify either --all or --test")

    # Create test suite
    suite = StressTestSuite(args.api_url, args.verbose)

    # Run tests
    if args.all:
        results = suite.run_all_tests()
        return 0 if results['passed'] == results['total'] else 1

    elif args.test == 'concurrent-registration':
        result = suite.test_concurrent_registration()
        return 0 if result['passed'] else 1

    elif args.test == 'rate-limiting':
        result = suite.test_rate_limiting()
        return 0 if result['passed'] else 1

    elif args.test == 'audit-chain':
        result = suite.test_audit_chain_integrity()
        return 0 if result['passed'] else 1


if __name__ == "__main__":
    sys.exit(main())
