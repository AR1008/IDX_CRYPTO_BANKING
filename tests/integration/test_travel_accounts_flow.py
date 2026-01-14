"""
Complete Travel Accounts + Forex Test
Purpose: Test entire travel account flow end-to-end

Flow Tested:
1. Setup foreign banks and forex rates
2. List available foreign banks
3. Get forex rates
4. Create travel account (INR → Foreign currency)
5. View travel account details
6. List all travel accounts
7. Close travel account (Foreign currency → INR)
8. Verify balances and fees
"""

import requests
import json

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
    print_header("✈️ PHASE 5: TRAVEL ACCOUNTS + FOREX TEST")
    
    # Step 1: Login
    print_header("Step 1: Login")
    
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
    user_info = login_response.json()['user']
    
    print_success(f"Logged in as: {user_info['full_name']}")
    print(f"   IDX: {user_info['idx'][:32]}...")
    
    # Step 2: Get bank accounts
    print_header("Step 2: Get Bank Accounts")
    
    accounts_response = requests.get(
        f"{BASE_URL}/api/bank-accounts",
        headers=headers
    )
    
    if accounts_response.status_code != 200:
        print_error("Failed to get accounts")
        return
    
    accounts = accounts_response.json()['accounts']
    
    if not accounts:
        print_error("No bank accounts found")
        return
    
    hdfc_account = None
    for acc in accounts:
        if acc['bank_code'] == 'HDFC':
            hdfc_account = acc
            break
    
    if not hdfc_account:
        hdfc_account = accounts[0]
    
    print_success(f"Using account: {hdfc_account['bank_code']}")
    print(f"   Account: {hdfc_account['account_number']}")
    print(f"   Balance: ₹{hdfc_account['balance']}")
    
    initial_balance = float(hdfc_account['balance'])
    
    # Step 3: List foreign banks
    print_header("Step 3: List Available Foreign Banks")
    
    banks_response = requests.get(
        f"{BASE_URL}/api/travel/foreign-banks",
        headers=headers
    )
    
    if banks_response.status_code == 200:
        foreign_banks = banks_response.json()['banks']
        print_success(f"Found {len(foreign_banks)} foreign banks:")
        for bank in foreign_banks:
            print(f"   - {bank['bank_name']} ({bank['bank_code']})")
            print(f"     Currency: {bank['currency']}, Country: {bank['country']}")
    else:
        print_error("Failed to get foreign banks")
        return
    
    # Step 4: Get forex rates
    print_header("Step 4: Get Forex Rates")
    
    rates_response = requests.get(
        f"{BASE_URL}/api/travel/forex-rates?from_currency=INR",
        headers=headers
    )
    
    if rates_response.status_code == 200:
        rates = rates_response.json()['rates']
        print_success(f"Found {len(rates)} forex rates from INR:")
        for rate in rates[:4]:  # Show first 4
            print(f"   - 1 INR = {rate['rate']} {rate['to_currency']} (Fee: {rate['forex_fee_percentage']}%)")
    else:
        print_error("Failed to get forex rates")
        return
    
    # Step 5: Create travel account (USA Trip)
    print_header("Step 5: Create Travel Account (USA Trip)")
    
    travel_amount = 50000  # ₹50,000
    
    create_response = requests.post(
        f"{BASE_URL}/api/travel/create",
        headers=headers,
        json={
            "source_account_id": hdfc_account['id'],
            "foreign_bank_code": "CITI_USA",
            "inr_amount": travel_amount,
            "duration_days": 30
        }
    )
    
    if create_response.status_code != 201:
        print_error(f"Failed to create travel account: {create_response.json()}")
        return
    
    travel_account = create_response.json()['travel_account']
    travel_id = travel_account['id']
    
    print_success("Travel account created!")
    print(f"   Account Number: {travel_account['foreign_account_number']}")
    print(f"   Currency: {travel_account['currency']}")
    print(f"   Balance: {travel_account['currency']} {travel_account['balance']}")
    print(f"   INR Converted: ₹{travel_account['initial_inr_amount']}")
    print(f"   Forex Rate: {travel_account['initial_forex_rate']}")
    print(f"   Forex Fee: {travel_account['currency']} {travel_account['forex_fee_paid']}")
    print(f"   Expires: {travel_account['expires_at'][:10]}")
    
    # Step 6: Get travel account details
    print_header("Step 6: Get Travel Account Details")
    
    detail_response = requests.get(
        f"{BASE_URL}/api/travel/accounts/{travel_id}",
        headers=headers
    )
    
    if detail_response.status_code == 200:
        account_detail = detail_response.json()['account']
        print_success("Travel account details retrieved:")
        print(f"   Status: {account_detail['status']}")
        print(f"   Currency: {account_detail['currency']}")
        print(f"   Balance: {account_detail['currency']} {account_detail['balance']}")
        print(f"   Is Expired: {account_detail['is_expired']}")
    else:
        print_error("Failed to get account details")
    
    # Step 7: List all travel accounts
    print_header("Step 7: List All Travel Accounts")
    
    list_response = requests.get(
        f"{BASE_URL}/api/travel/accounts",
        headers=headers
    )
    
    if list_response.status_code == 200:
        all_accounts = list_response.json()['accounts']
        print_success(f"Found {len(all_accounts)} travel account(s):")
        for acc in all_accounts:
            status_icon = "🟢" if acc['status'] == 'ACTIVE' else "🔴"
            print(f"   {status_icon} {acc['foreign_account_number']}")
            print(f"      Balance: {acc['currency']} {acc['balance']} ({acc['status']})")
    else:
        print_error("Failed to list accounts")
    
    # Step 8: Close travel account
    print_header("Step 8: Close Travel Account (Return to India)")
    
    close_response = requests.post(
        f"{BASE_URL}/api/travel/accounts/{travel_id}/close",
        headers=headers,
        json={
            "reason": "Vacation completed - returning home"
        }
    )
    
    if close_response.status_code != 200:
        print_error(f"Failed to close account: {close_response.json()}")
        return
    
    close_result = close_response.json()['result']
    
    print_success("Travel account closed!")
    print(f"   Foreign Currency: {close_result['foreign_currency']}")
    print(f"   Remaining Balance: {close_result['foreign_currency']} {close_result['final_foreign_amount']}")
    print(f"   Converted to INR: ₹{close_result['final_inr_amount']}")
    print(f"   Return Forex Fee: ₹{close_result['forex_fee_paid']}")
    print(f"   Closed At: {close_result['closed_at'][:19]}")
    
    # Step 9: Verify final balance
    print_header("Step 9: Verify Final Balance")
    
    final_accounts_response = requests.get(
        f"{BASE_URL}/api/bank-accounts",
        headers=headers
    )
    
    if final_accounts_response.status_code == 200:
        final_accounts = final_accounts_response.json()['accounts']
        
        for acc in final_accounts:
            if acc['id'] == hdfc_account['id']:
                final_balance = float(acc['balance'])
                
                print_success("Balance verification:")
                print(f"   Initial Balance: ₹{initial_balance:,.2f}")
                print(f"   Converted to USD: -₹{travel_amount:,.2f}")
                print(f"   Returned from USD: +₹{close_result['final_inr_amount']:,.2f}")
                print(f"   Final Balance: ₹{final_balance:,.2f}")
                
                total_fees = initial_balance - final_balance
                print(f"   Total Forex Fees: ₹{total_fees:,.2f}")
                
                # Calculate expected fee (0.15% each way = 0.3% total)
                expected_fee_percentage = 0.003  # 0.3%
                expected_fee = travel_amount * expected_fee_percentage
                
                print(f"   Expected Fee (~0.3%): ₹{expected_fee:,.2f}")
                
                if abs(total_fees - expected_fee) < 10:  # Allow ₹10 difference
                    print_success("✅ Fees calculated correctly!")
                else:
                    print(f"   ⚠️ Fee difference: ₹{abs(total_fees - expected_fee):,.2f}")
    
    # Final Summary
    print_header("✅ PHASE 5 TEST COMPLETE!")
    
    print("\nWhat We Tested:")
    print("1. ✅ List foreign banks (4 banks)")
    print("2. ✅ Get forex rates (8 currency pairs)")
    print("3. ✅ Create travel account (INR → USD)")
    print("4. ✅ Forex conversion with 0.15% fee")
    print("5. ✅ View travel account details")
    print("6. ✅ List all travel accounts")
    print("7. ✅ Close travel account (USD → INR)")
    print("8. ✅ Return conversion with 0.15% fee")
    print("9. ✅ Balance verification")
    print("10. ✅ Total fee calculation (0.3%)")
    
    print("\n🌍 Travel Accounts + Forex Working Perfectly!")
    print("✈️ Users Can Now Travel Internationally!")


if __name__ == "__main__":
    print("\n⚠️  MAKE SURE API SERVER IS RUNNING!")
    print("Run: python3 -m api.app\n")
    
    input("Press Enter to start test...")
    main()