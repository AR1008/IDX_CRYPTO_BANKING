#!/usr/bin/env python3
"""
Test Concurrent Registration Fix
Purpose: Verify the race condition bug fix in user registration

Test Scenario:
- 100 threads try to register the SAME user simultaneously
- Expected Result:
  - 1 success (201 Created)
  - 99 conflicts (409 Conflict)
  - 0 errors (500 Internal Server Error)

Before fix: 100% error rate (IntegrityError exceptions)
After fix: 0% error rate (graceful 409 Conflict responses)
"""

# [DOC] requests: HTTP client used to call the running Flask API server at localhost:5000
import requests
# [DOC] threading: provides Thread primitives; ThreadPoolExecutor is used for concurrency control
import threading
# [DOC] ThreadPoolExecutor/as_completed: runs 100 registration requests in parallel with up to 50 workers
from concurrent.futures import ThreadPoolExecutor, as_completed
# [DOC] Counter: counts occurrences of each HTTP status code in the results list
from collections import Counter
# [DOC] time: measures total wall-clock time for the concurrent test run
import time

# [DOC] BASE_URL: the API server must be running before this script is executed
BASE_URL = "http://localhost:5000"

def test_concurrent_registration_same_user():
    # [DOC] test_concurrent_registration_same_user: proves the race condition fix works —
    # [DOC] 100 threads hitting the same PAN card must produce exactly 1 success and 99 conflicts
    """
    Test concurrent registration of the SAME user
    This tests the race condition fix
    """
    print("\n" + "="*70)
    print("🧪 Testing Concurrent Registration Fix (SAME User)")
    print("="*70)
    print("Scenario: 100 threads registering the same user simultaneously")
    print("Expected: 1 success (201), 99 conflicts (409), 0 errors (500)\n")

    results = {
        'status_codes': [],
        'response_times': [],
        'errors': []
    }

    # Same PAN for all requests (this is the race condition scenario)
    test_pan = "RACE00001A"
    test_rbi = "999001"

    def register_user(thread_id):
        # [DOC] register_user: each thread attempts to POST /api/auth/register with the same PAN card
        # [DOC] exactly one should succeed (201); all others should receive a 409 Conflict
        """Attempt to register user"""
        try:
            start_time = time.time()
            # [DOC] POST /api/auth/register — creates a new user; must handle concurrent identical requests gracefully
            response = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "pan_card": test_pan,
                    "rbi_number": test_rbi,
                    "full_name": "Race Condition Test User",
                    "initial_balance": 10000
                },
                timeout=10
            )
            duration = (time.time() - start_time) * 1000  # ms

            results['status_codes'].append(response.status_code)
            results['response_times'].append(duration)

            return {
                'thread_id': thread_id,
                'status': response.status_code,
                'duration': duration,
                'response': response.json() if response.headers.get('content-type') == 'application/json' else None
            }

        except Exception as e:
            results['errors'].append(str(e))
            return {
                'thread_id': thread_id,
                'status': 'ERROR',
                'error': str(e)
            }

    # Execute 100 concurrent registrations
    print("⏳ Executing 100 concurrent registration requests...")
    start_time = time.time()

    # [DOC] ThreadPoolExecutor(max_workers=50): runs 50 threads in parallel to simulate concurrent load
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(register_user, i) for i in range(100)]
        thread_results = [future.result() for future in as_completed(futures)]

    total_time = time.time() - start_time

    # Analyze results
    status_counter = Counter(results['status_codes'])

    print(f"\n✅ Test completed in {total_time:.2f} seconds\n")

    print("📊 Results:")
    print("-" * 70)
    print(f"  Total Requests:     100")
    print(f"  201 (Created):      {status_counter.get(201, 0)}")
    print(f"  409 (Conflict):     {status_counter.get(409, 0)}")
    print(f"  500 (Error):        {status_counter.get(500, 0)}")
    print(f"  Other Status Codes: {sum(v for k, v in status_counter.items() if k not in [201, 409, 500])}")
    print(f"  Exceptions:         {len(results['errors'])}")
    print()

    if results['response_times']:
        avg_response = sum(results['response_times']) / len(results['response_times'])
        min_response = min(results['response_times'])
        max_response = max(results['response_times'])

        print("⏱️  Response Times:")
        print("-" * 70)
        print(f"  Average: {avg_response:.2f}ms")
        print(f"  Min:     {min_response:.2f}ms")
        print(f"  Max:     {max_response:.2f}ms")
        print()

    # Verify expectations
    print("🔍 Verification:")
    print("-" * 70)

    success_count = status_counter.get(201, 0)
    conflict_count = status_counter.get(409, 0)
    error_count = status_counter.get(500, 0)
    exception_count = len(results['errors'])

    checks = {
        # [DOC] "Exactly 1 success": the DB unique constraint must allow only one winner thread
        "Exactly 1 success (201)": success_count == 1,
        # [DOC] "Exactly 99 conflicts": all losing threads must receive graceful 409 (not 500)
        "Exactly 99 conflicts (409)": conflict_count == 99,
        # [DOC] "Zero errors": no 500 responses means no unhandled IntegrityErrors — the fix works
        "Zero errors (500)": error_count == 0,
        # [DOC] "Zero exceptions": no network-level exceptions (requests.exceptions.*)
        "Zero exceptions": exception_count == 0
    }

    all_passed = True
    for check, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check}")
        if not passed:
            all_passed = False

    print()

    if all_passed:
        print("🎉 " + "="*66)
        print("🎉 ALL TESTS PASSED! Race condition bug is FIXED!")
        print("🎉 " + "="*66)
        return True
    else:
        print("❌ " + "="*66)
        print("❌ TESTS FAILED! Race condition still exists or other issues")
        print("❌ " + "="*66)

        # Print sample error responses for debugging
        if error_count > 0:
            print("\n🔍 Sample Error Responses:")
            error_responses = [r for r in thread_results if r.get('status') == 500][:3]
            for i, resp in enumerate(error_responses, 1):
                print(f"\n  Error {i}:")
                print(f"    Thread ID: {resp.get('thread_id')}")
                print(f"    Response: {resp.get('response')}")

        if exception_count > 0:
            print("\n🔍 Sample Exceptions:")
            for i, error in enumerate(results['errors'][:3], 1):
                print(f"  Exception {i}: {error}")

        return False


def test_concurrent_registration_different_users():
    # [DOC] test_concurrent_registration_different_users: proves that 100 genuinely distinct users
    # [DOC] can all be registered concurrently with no conflicts or errors — baseline sanity check
    """
    Test concurrent registration of DIFFERENT users
    This should all succeed (no conflicts)
    """
    print("\n" + "="*70)
    print("🧪 Testing Concurrent Registration (DIFFERENT Users)")
    print("="*70)
    print("Scenario: 100 threads registering different users simultaneously")
    print("Expected: 100 successes (201), 0 conflicts, 0 errors\n")

    results = {
        'status_codes': [],
        'response_times': []
    }

    def register_user(user_id):
        # [DOC] register_user: each thread uses a unique PAN card derived from user_id to avoid conflicts
        """Attempt to register unique user"""
        try:
            start_time = time.time()
            # [DOC] POST /api/auth/register — each of the 100 users has a unique PAN, so all must succeed
            response = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "pan_card": f"USER{user_id:05d}A",
                    "rbi_number": f"{200000 + user_id}",
                    "full_name": f"Test User {user_id}",
                    "initial_balance": 10000
                },
                timeout=10
            )
            duration = (time.time() - start_time) * 1000  # ms

            results['status_codes'].append(response.status_code)
            results['response_times'].append(duration)

            return response.status_code

        except Exception as e:
            results['status_codes'].append(500)  # Count exceptions as errors
            return 500

    # Execute 100 concurrent registrations
    print("⏳ Executing 100 concurrent registration requests...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(register_user, i) for i in range(100)]
        thread_results = [future.result() for future in as_completed(futures)]

    total_time = time.time() - start_time

    # Analyze results
    status_counter = Counter(results['status_codes'])

    print(f"\n✅ Test completed in {total_time:.2f} seconds\n")

    print("📊 Results:")
    print("-" * 70)
    print(f"  Total Requests: 100")
    print(f"  201 (Created):  {status_counter.get(201, 0)}")
    print(f"  409 (Conflict): {status_counter.get(409, 0)}")
    print(f"  500 (Error):    {status_counter.get(500, 0)}")
    print()

    if results['response_times']:
        avg_response = sum(results['response_times']) / len(results['response_times'])
        print(f"  Average Response Time: {avg_response:.2f}ms")
        print()

    # Verify expectations
    success_count = status_counter.get(201, 0)
    error_count = status_counter.get(500, 0)

    if success_count == 100 and error_count == 0:
        # [DOC] assert 100 successes: all distinct users must be created without any errors
        print("✅ PASS: All different users registered successfully!")
        return True
    else:
        print(f"❌ FAIL: Expected 100 successes, got {success_count}")
        return False


if __name__ == "__main__":
    print("\n" + "🚀 "*35)
    print("CONCURRENT REGISTRATION TEST SUITE")
    print("🚀 "*35 + "\n")

    print("Testing the fix for the concurrent user creation bug")
    print("(Previously: 100% error rate on concurrent registrations)\n")

    # Check if server is running
    try:
        # [DOC] GET /health — verifies the API server is up before running the concurrent tests
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✅ Server is running at {BASE_URL}\n")
    except requests.exceptions.ConnectionError:
        print(f"❌ ERROR: Server is not running at {BASE_URL}")
        print(f"   Please start the server first: python api/app.py")
        exit(1)

    # Run tests
    test1_passed = test_concurrent_registration_same_user()
    test2_passed = test_concurrent_registration_different_users()

    # Final summary
    print("\n" + "="*70)
    print("📋 FINAL SUMMARY")
    print("="*70)
    print(f"  Test 1 (Same User):      {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"  Test 2 (Different Users): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print("="*70)

    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! The concurrent registration bug is FIXED! 🎉\n")
        exit(0)
    else:
        print("\n❌ SOME TESTS FAILED. Please review the results above.\n")
        exit(1)
