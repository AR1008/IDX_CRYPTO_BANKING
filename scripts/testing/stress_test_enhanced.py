#!/usr/bin/env python3
# [DOC] FILE: scripts/testing/stress_test_enhanced.py
# [DOC] PURPOSE: Fire many HTTP requests at the live API server concurrently
# [DOC]   to verify system stability, measure throughput, and confirm rate-limiting works.
# [DOC]
# [DOC] PRE-REQUISITE: API server must be running on API_BASE_URL (default: localhost:5000).
# [DOC]   Start it with: python3 -m api.app
# [DOC]
# [DOC] TESTS:
# [DOC]   1. concurrent_registration — 100 threads all try to register the SAME PAN card.
# [DOC]      Expected: exactly 1 HTTP 201 (first writer wins), the rest get 409 Conflict.
# [DOC]      Zero HTTP 500 means the race-condition fix (DB-level unique constraint) is working.
# [DOC]   2. rate_limiting — 50 sequential requests to /api/auth/register.
# [DOC]      Expected: at least 1 HTTP 429 Too Many Requests; confirms Flask-Limiter is active.
# [DOC]   3. audit_chain_integrity — single GET to /api/audit/verify.
# [DOC]      Expected: chain_valid=True; all audit log hashes are consistent.
# [DOC]
# [DOC] USAGE:
# [DOC]   python scripts/testing/stress_test_enhanced.py --all
# [DOC]   python scripts/testing/stress_test_enhanced.py --test concurrent-registration --verbose
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

# [DOC] sys/os: standard path manipulation
import sys
import os
# [DOC] argparse: parse --all, --test, --api-url, --verbose flags
import argparse
# [DOC] time: measure elapsed wall-clock time for throughput calculations
import time
# [DOC] requests: HTTP client used to call the live API server
import requests
# [DOC] ThreadPoolExecutor: concurrent thread pool for the registration stress test
# [DOC] as_completed: iterator that yields futures as they finish (not in submission order)
from concurrent.futures import ThreadPoolExecutor, as_completed
# [DOC] datetime: timestamp in progress headers
from datetime import datetime
# [DOC] Decimal: for monetary amounts in throughput test (not yet used, imported for future)
from decimal import Decimal
# [DOC] json: parse API response bodies
import json

# [DOC] API_BASE_URL: where the Flask server is listening; overridable via --api-url
API_BASE_URL = "http://localhost:5000"
# [DOC] MAX_WORKERS: maximum concurrent HTTP threads in the thread pool
MAX_WORKERS = 50


class StressTestSuite:
    # [DOC] Stateful test suite — stores base_url and verbose flag; each test returns a result dict.
    """Enhanced stress test suite"""

    def __init__(self, base_url: str, verbose: bool = False):
        # [DOC] base_url: HTTP base URL of the API (e.g., "http://localhost:5000")
        # [DOC] verbose: if True, print per-request timestamps and status codes
        self.base_url = base_url
        self.verbose = verbose

    def log(self, message: str):
        # [DOC] Print timestamped debug message only when --verbose is active.
        # [DOC]   Format: "[HH:MM:SS.mmm] message"
        """Log message"""
        if self.verbose:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{timestamp}] {message}")

    def print_header(self, title: str):
        # [DOC] Print a visual separator and test title for readability in terminal output.
        """Print test header"""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def test_concurrent_registration(self, num_users: int = 100) -> dict:
        # [DOC] Submit `num_users` concurrent POST /api/auth/register requests,
        # [DOC]   all with the SAME PAN card (test_pan) and RBI number (test_rbi).
        # [DOC]
        # [DOC] WHY THIS TEST EXISTS:
        # [DOC]   An earlier bug allowed two threads to both pass the "user exists?" check
        # [DOC]   before either inserted, resulting in a DB unique-constraint violation (HTTP 500).
        # [DOC]   The fix: rely on the DB unique index rather than application-level checks.
        # [DOC]   Expected outcome: exactly 1 HTTP 201, N-1 HTTP 409, 0 HTTP 500.
        # [DOC]
        # [DOC] IMPLEMENTATION:
        # [DOC]   ThreadPoolExecutor with MAX_WORKERS threads; all futures launched simultaneously;
        # [DOC]   as_completed() collects results; status codes tallied in `results` dict.
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

        # [DOC] Same PAN for all requests — this is the race condition scenario
        test_pan = "TESTP1234A"
        test_rbi = "999999"

        # [DOC] Result counters keyed by HTTP status code string
        results = {
            '201': 0,  # Created
            '409': 0,  # Conflict
            '400': 0,  # Bad Request
            '500': 0,  # Server Error
            'other': 0
        }

        def register_user(index: int):
            # [DOC] Inner function: make one registration HTTP POST and return the status code.
            # [DOC]   timeout=10 avoids hanging forever if the server is unresponsive.
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
                # [DOC] Network errors (connection refused, timeout) are returned as status code 0
                self.log(f"User {index}: Request failed - {e}")
                return 0

        # [DOC] Record start time to measure total elapsed seconds
        start_time = time.time()

        # [DOC] Launch all num_users futures simultaneously into the thread pool
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(register_user, i) for i in range(num_users)]

            # [DOC] as_completed() yields each future as it finishes (order is non-deterministic)
            for future in as_completed(futures):
                status_code = future.result()
                status_str = str(status_code)

                # [DOC] Bucket the status into one of the known categories, or 'other'
                if status_str in results:
                    results[status_str] += 1
                else:
                    results['other'] += 1

        elapsed = time.time() - start_time

        print(f"\n📊 Results:")
        print(f"   201 Created: {results['201']}")
        print(f"   409 Conflict: {results['409']}")
        print(f"   400 Bad Request: {results['400']}")
        print(f"   500 Server Error: {results['500']}")
        print(f"   Other: {results['other']}")
        print(f"   Time: {elapsed:.2f}s")

        # [DOC] PASS criteria: exactly 1 successful creation, zero server errors
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
        # [DOC] Send `requests_count` HTTP POSTs in rapid succession (10ms apart) to a single endpoint.
        # [DOC]   Flask-Limiter should respond with HTTP 429 after the configured threshold is hit.
        # [DOC] Unlike test 1, this runs sequentially (not concurrently) to hit the per-IP rate limit.
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
            '200': 0,
            '201': 0,
            '400': 0,
            '409': 0,
            '429': 0,  # [DOC] Rate-limited responses — the key metric for this test
            '500': 0,
            'other': 0
        }

        def send_request(index: int):
            # [DOC] Each request uses a unique (fake) PAN so it does not hit 409 Conflict.
            # [DOC]   We want to hit the rate limiter, not the duplicate-PAN check.
            """Send a single request"""
            try:
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    json={
                        'pan_card': f"TEST{index:05d}A",  # [DOC] Unique PAN per request
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

        start_time = time.time()

        # [DOC] Sequential loop — intentionally not concurrent so rate limit accumulates on one IP
        for i in range(requests_count):
            status_code = send_request(i)
            status_str = str(status_code)

            if status_str in results:
                results[status_str] += 1
            else:
                results['other'] += 1

            # [DOC] 10ms gap prevents connection errors from overwhelming the server,
            # [DOC]   while still being fast enough to trigger the rate limiter.
            time.sleep(0.01)

        elapsed = time.time() - start_time

        print(f"\n📊 Results:")
        print(f"   200 OK: {results['200']}")
        print(f"   201 Created: {results['201']}")
        print(f"   409 Conflict: {results['409']}")
        print(f"   429 Rate Limited: {results['429']}")
        print(f"   500 Server Error: {results['500']}")
        print(f"   Time: {elapsed:.2f}s")

        # [DOC] PASS criteria: at least one 429 response confirms rate limiting is active
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
        # [DOC] Hammer POST /api/transactions/create for `duration_seconds` seconds
        # [DOC]   and compute TPS = total_requests / elapsed_seconds.
        # [DOC] NOTE: This test uses placeholder sender/receiver IDX values.
        # [DOC]   In a real environment these would be pre-created test user IDX values.
        # [DOC] PASS criteria: TPS >= 10 (system can handle at least 10 txns/sec single-threaded).
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
            # [DOC] Attempt a single transaction API call; return True on HTTP 200/201.
            """Create a single transaction"""
            try:
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

        # [DOC] Run until the wall clock exceeds start + duration_seconds
        start_time = time.time()
        end_time = start_time + duration_seconds

        while time.time() < end_time:
            if create_transaction():
                results['success'] += 1
            else:
                results['failed'] += 1

        elapsed = time.time() - start_time

        # [DOC] TPS = (success + failed) / elapsed — includes failed attempts in the rate
        total_transactions = results['success'] + results['failed']
        tps = total_transactions / elapsed if elapsed > 0 else 0

        print(f"\n📊 Results:")
        print(f"   Successful: {results['success']}")
        print(f"   Failed: {results['failed']}")
        print(f"   Total: {total_transactions}")
        print(f"   Duration: {elapsed:.2f}s")
        print(f"   TPS: {tps:.2f}")

        # [DOC] PASS criteria: >= 10 TPS (single-threaded baseline)
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
        # [DOC] Start `num_miners` concurrent mining processes via the API, wait
        # [DOC]   `duration_seconds`, then query the mining pool status.
        # [DOC] PASS criteria: all `num_miners` miners were started successfully (HTTP 200).
        # [DOC] NOTE: Only one miner wins each block (PoW winner-takes-all); this test
        # [DOC]   verifies that concurrent miners do not crash the server.
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
            # [DOC] POST to /api/mining/start to register a miner with a given IDX.
            # [DOC]   Returns True if the server accepted the request (HTTP 200).
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

        # [DOC] Launch all miners sequentially (they run as server-side background tasks)
        for i in range(num_miners):
            if start_miner(f"MINER_{i}"):
                results['miners_started'] += 1
            else:
                results['errors'] += 1

        # [DOC] Let the miners run for the configured duration then check results
        print(f"\nMining for {duration_seconds} seconds...")
        time.sleep(duration_seconds)

        # [DOC] Query the mining pool status endpoint for aggregate stats
        try:
            response = requests.get(f"{self.base_url}/api/mining/pool-status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                results['blocks_mined'] = data.get('blocks_mined', 0)
                results['active_miners'] = data.get('active_miners', 0)
        except Exception as e:
            self.log(f"Failed to get mining stats: {e}")

        print(f"\n📊 Results:")
        print(f"   Miners started: {results['miners_started']}")
        print(f"   Blocks mined: {results['blocks_mined']}")
        print(f"   Errors: {results['errors']}")

        # [DOC] PASS criteria: all requested miners were successfully started
        passed = results['miners_started'] == num_miners
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status}")

        return {
            'test': 'mining_competition',
            'passed': passed,
            'results': results
        }

    def test_audit_chain_integrity(self) -> dict:
        # [DOC] Call GET /api/audit/verify to confirm that the audit log hash chain
        # [DOC]   is internally consistent (each log entry hashes the previous entry's hash).
        # [DOC] PASS criteria: response contains chain_valid=True.
        # [DOC] If chain_valid=False, an audit log entry has been tampered with.
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
        # [DOC] Run the default test battery: concurrent registration, rate limiting,
        # [DOC]   and audit chain integrity. (Transaction throughput and mining competition
        # [DOC]   are heavier tests that are run individually via --test.)
        # [DOC] Returns a summary dict with total/passed counts and the individual result list.
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

        # [DOC] Test 1: concurrent registration — must not produce HTTP 500
        all_results.append(self.test_concurrent_registration(num_users=100))

        # [DOC] Test 2: rate limiting — must produce at least one HTTP 429
        all_results.append(self.test_rate_limiting(requests_count=50))

        # [DOC] Test 3: audit chain — hash chain must be intact
        all_results.append(self.test_audit_chain_integrity())

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
    # [DOC] Entry point: parse CLI flags and dispatch to the appropriate test(s).
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

    # [DOC] --all: run the full default test battery
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all tests'
    )

    # [DOC] --test: run a single named test instead of the full battery
    parser.add_argument(
        '--test',
        choices=['concurrent-registration', 'rate-limiting', 'audit-chain'],
        help='Run specific test'
    )

    # [DOC] --api-url: override the server URL (useful for testing a staging server)
    parser.add_argument(
        '--api-url',
        default=API_BASE_URL,
        help=f'API base URL (default: {API_BASE_URL})'
    )

    # [DOC] --verbose: print per-request timestamps and status codes
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # [DOC] Require either --all or --test; running neither is a user error
    if not args.all and not args.test:
        parser.error("Must specify either --all or --test")

    suite = StressTestSuite(args.api_url, args.verbose)

    # [DOC] Dispatch: --all runs all tests; --test runs the single named test
    if args.all:
        results = suite.run_all_tests()
        # [DOC] Exit 0 if every test passed; 1 if any failed
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
