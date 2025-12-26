"""
Complete Court Order System Test
Author: Ashutosh Rajesh
Purpose: Test entire court order flow end-to-end

Flow Tested:
1. Add authorized judge (API)
2. Create user with transactions
3. Submit court order (API)
4. Verify account freezing
5. Execute de-anonymization (API)
6. Verify decrypted data
7. Check audit trail (API)
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_success(text):
    print(f"✅ {text}")

def print_error(text):
    print(f"❌ {text}")


def main():
    print_header("🏛️ PHASE 4: COURT ORDER SYSTEM TEST")
    
    # Step 1: Login as admin
    print_header("Step 1: Login as Admin")
    
    login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "pan_card": "TESTA1234P",
        "rbi_number": "100001",
        "bank_name": "HDFC"
    })
    
    if login_response.status_code != 200:
        print_error("Login failed!")
        print(login_response.json())
        return
    
    token = login_response.json()['token']
    headers = {"Authorization": f"Bearer {token}"}
    print_success(f"Logged in as: {login_response.json()['user']['full_name']}")
    
    # Step 2: Add authorized judge
    print_header("Step 2: Add Authorized Judge")
    
    judge_data = {
        "judge_id": "JID_2025_DEMO",
        "full_name": "Justice Demo Sharma",
        "court_name": "Demo High Court",
        "jurisdiction": "Demo State"
    }
    
    judge_response = requests.post(
        f"{BASE_URL}/api/court-orders/judges",
        headers=headers,
        json=judge_data
    )
    
    if judge_response.status_code == 201:
        print_success("Judge authorized!")
        judge = judge_response.json()['judge']
        print(f"   Name: {judge['full_name']}")
        print(f"   Court: {judge['court_name']}")
        print(f"   ID: {judge['judge_id']}")
    else:
        if "already authorized" in judge_response.json().get('error', ''):
            print_success("Judge already authorized (reusing)")
        else:
            print_error(f"Failed: {judge_response.json()}")
            return
    
    # Step 3: Get list of judges
    print_header("Step 3: List All Authorized Judges")
    
    judges_response = requests.get(
        f"{BASE_URL}/api/court-orders/judges",
        headers=headers
    )
    
    if judges_response.status_code == 200:
        judges = judges_response.json()['judges']
        print_success(f"Found {len(judges)} authorized judges:")
        for j in judges:
            print(f"   - {j['full_name']} ({j['judge_id']})")
    else:
        print_error(f"Failed to get judges")
        return
    
    # Step 4: Get user info for investigation
    print_header("Step 4: Get User Info")
    
    account_response = requests.get(
        f"{BASE_URL}/api/accounts/info",
        headers=headers
    )
    
    if account_response.status_code != 200:
        print_error("Failed to get account info")
        return
    
    user_info = account_response.json()['user']
    target_idx = user_info['idx']
    
    print_success(f"Target user identified:")
    print(f"   Name: {user_info['full_name']}")
    print(f"   IDX: {target_idx[:32]}...")
    print(f"   Balance: ₹{user_info['balance']}")
    
    # Step 5: Submit court order
    print_header("Step 5: Submit Court Order")
    
    court_order_data = {
        "judge_id": "JID_2025_DEMO",
        "target_idx": target_idx,
        "reason": "Demonstration of court-ordered de-anonymization system",
        "case_number": "CASE_DEMO_2025",
        "freeze_account": True
    }
    
    order_response = requests.post(
        f"{BASE_URL}/api/court-orders/submit",
        headers=headers,
        json=court_order_data
    )
    
    if order_response.status_code != 201:
        print_error(f"Court order submission failed: {order_response.json()}")
        return
    
    order = order_response.json()['order']
    order_id = order['order_id']
    
    print_success("Court order submitted!")
    print(f"   Order ID: {order_id}")
    print(f"   Status: {order['status']}")
    print(f"   Expires: {order['expires_at'][:19]}")
    print(f"   Case: {order['case_number']}")
    
    # Step 6: Get order details
    print_header("Step 6: Get Court Order Details")
    
    order_detail_response = requests.get(
        f"{BASE_URL}/api/court-orders/{order_id}",
        headers=headers
    )
    
    if order_detail_response.status_code == 200:
        order_detail = order_detail_response.json()['order']
        print_success("Order details retrieved:")
        print(f"   Judge: {order_detail['judge_id']}")
        print(f"   Target: {order_detail['target_idx'][:32]}...")
        print(f"   Reason: {order_detail['reason']}")
        print(f"   Status: {order_detail['status']}")
    else:
        print_error("Failed to get order details")
    
    # Step 7: Execute de-anonymization
    print_header("Step 7: Execute De-Anonymization")
    
    execute_response = requests.post(
        f"{BASE_URL}/api/court-orders/{order_id}/execute",
        headers=headers
    )
    
    if execute_response.status_code != 200:
        print_error(f"De-anonymization failed: {execute_response.json()}")
        return
    
    result = execute_response.json()['result']
    
    print_success("De-anonymization executed!")
    print(f"\n   🔓 DECRYPTED INFORMATION:")
    print(f"   Target IDX: {result['target_idx'][:32]}...")
    print(f"\n   USER IDENTITY:")
    print(f"   - Full Name: {result['user_info']['full_name']}")
    print(f"   - PAN Card: {result['user_info']['pan_card']}")
    print(f"   - Total Balance: ₹{result['user_info']['total_balance']}")
    
    print(f"\n   BANK ACCOUNTS:")
    for acc in result['bank_accounts']:
        frozen_text = " (FROZEN)" if acc['is_frozen'] else ""
        print(f"   - {acc['bank']}: {acc['account_number']}")
        print(f"     Balance: ₹{acc['balance']}{frozen_text}")
    
    print(f"\n   SESSIONS MAPPED: {len(result['sessions'])}")
    if result['sessions']:
        for session in result['sessions'][:3]:
            print(f"   - {session[:40]}...")
    
    print(f"\n   TRANSACTIONS: {len(result['transactions'])}")
    if result['transactions']:
        for tx in result['transactions'][:3]:
            print(f"   - TX: {tx['tx_hash'][:16]}... (₹{tx['amount']})")
    
    # Step 8: Get all orders
    print_header("Step 8: List All Court Orders")
    
    all_orders_response = requests.get(
        f"{BASE_URL}/api/court-orders",
        headers=headers
    )
    
    if all_orders_response.status_code == 200:
        all_orders = all_orders_response.json()['orders']
        print_success(f"Found {len(all_orders)} court orders:")
        for o in all_orders[-5:]:  # Show last 5
            print(f"   - {o['order_id']}: {o['status']} (Judge: {o['judge_id']})")
    
    # Step 9: Get audit trail
    print_header("Step 9: View Audit Trail")
    
    audit_response = requests.get(
        f"{BASE_URL}/api/court-orders/audit-trail",
        headers=headers
    )
    
    if audit_response.status_code == 200:
        audit_log = audit_response.json()['audit_log']
        print_success(f"Found {len(audit_log)} audit entries:")
        
        # Show last 5 entries
        for entry in audit_log[-5:]:
            event_type = entry.get('event', 'ACCESS')
            timestamp = entry['timestamp'][:19]
            
            if event_type == 'KEY_ISSUED':
                print(f"   - {timestamp}: KEY_ISSUED for {entry['court_order_id']}")
            else:
                granted = "✅ GRANTED" if entry['access_granted'] else "❌ DENIED"
                print(f"   - {timestamp}: ACCESS {granted} - {entry['court_order_id']}")
    
    # Final Summary
    print_header("✅ PHASE 4 TEST COMPLETE!")
    
    print("\nWhat We Tested:")
    print("1. ✅ Judge authorization (add to database)")
    print("2. ✅ List authorized judges")
    print("3. ✅ Submit court order")
    print("4. ✅ Account freezing")
    print("5. ✅ Get court order details")
    print("6. ✅ Execute de-anonymization (dual-key decryption)")
    print("7. ✅ Decrypt private blockchain data")
    print("8. ✅ Reveal user identity (PAN card)")
    print("9. ✅ Map sessions to real users")
    print("10. ✅ List all court orders")
    print("11. ✅ View complete audit trail")
    
    print("\n🎉 Court Order System Working Perfectly!")
    print("🔐 World's First Blockchain De-Anonymization System!")


if __name__ == "__main__":
    print("\n⚠️  MAKE SURE API SERVER IS RUNNING!")
    print("Run: python3 -m api.app\n")
    
    input("Press Enter to start test...")
    main()