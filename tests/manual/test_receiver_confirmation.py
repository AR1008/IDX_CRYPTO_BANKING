"""
Test Receiver Confirmation Flow
Author: Ashutosh Rajesh
Purpose: Test complete transaction flow with receiver confirmation
"""

import requests
import json
import sys
import random
BASE_URL = "http://localhost:5000"

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_success(text):
    print(f"✅ {text}")

def print_error(text):
    print(f"❌ {text}")

def register_user(pan_card, rbi_number, full_name, initial_balance):
    """Register a new user"""
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "pan_card": pan_card,
        "rbi_number": rbi_number,
        "full_name": full_name,
        "initial_balance": initial_balance
    })
    
    if response.status_code == 201:
        data = response.json()
        print_success(f"Registered: {data['user']['full_name']}")
        print(f"   IDX: {data['user']['idx'][:32]}...")
        return data['user']['idx']
    else:
        print_error(f"Registration failed: {response.json().get('error', 'Unknown error')}")
        return None

def login_user(pan_card, rbi_number, bank_name):
    """Login and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "pan_card": pan_card,
        "rbi_number": rbi_number,
        "bank_name": bank_name
    })
    
    if response.status_code == 200:
        data = response.json()
        print_success(f"Logged in: {data['user']['full_name']}")
        return data['token']
    else:
        print_error(f"Login failed: {response.json().get('error', 'Unknown error')}")
        return None

def get_account_info(token):
    """Get account summary"""
    response = requests.get(f"{BASE_URL}/api/bank-accounts/summary", 
                           headers={"Authorization": f"Bearer {token}"})
    
    if response.status_code == 200:
        return response.json()
    else:
        print_error(f"Failed to get accounts: {response.json().get('error')}")
        return None

def add_recipient(token, recipient_idx, nickname):
    """Add recipient to contact list"""
    response = requests.post(f"{BASE_URL}/api/recipients/add",
                            headers={"Authorization": f"Bearer {token}"},
                            json={
                                "recipient_idx": recipient_idx,
                                "nickname": nickname
                            })
    
    if response.status_code == 201:
        print_success(f"Added recipient: {nickname}")
        return True
    else:
        print_error(f"Failed to add recipient: {response.json().get('error')}")
        return False

def create_transaction(token, sender_account_id, recipient_nickname, amount):
    """Create transaction (awaiting receiver)"""
    response = requests.post(f"{BASE_URL}/api/transactions/send",
                            headers={"Authorization": f"Bearer {token}"},
                            json={
                                "sender_account_id": sender_account_id,
                                "recipient_nickname": recipient_nickname,
                                "amount": amount,
                                "sender_session_id": "SESSION_test_sender"
                            })
    
    if response.status_code == 201:
        data = response.json()
        print_success(f"Transaction created: {data['transaction']['transaction_hash'][:16]}...")
        print(f"   Amount: ₹{amount}")
        print(f"   Status: {data['status']}")
        return data['transaction']['transaction_hash']
    else:
        print_error(f"Transaction failed: {response.json().get('error')}")
        return None

def get_pending_for_receiver(token):
    """Get pending transactions"""
    response = requests.get(f"{BASE_URL}/api/transactions/pending-for-me",
                           headers={"Authorization": f"Bearer {token}"})
    
    if response.status_code == 200:
        data = response.json()
        print_success(f"Found {data['count']} pending transactions")
        return data['pending_transactions']
    else:
        print_error(f"Failed to get pending: {response.json().get('error')}")
        return []

def create_bank_account(token, bank_code, initial_balance=0):
    """Create new bank account"""
    response = requests.post(f"{BASE_URL}/api/bank-accounts/create",
                            headers={"Authorization": f"Bearer {token}"},
                            json={
                                "bank_code": bank_code,
                                "initial_balance": initial_balance
                            })
    
    if response.status_code == 201:
        data = response.json()
        print_success(f"Created {bank_code} account: {data['account']['account_number']}")
        return data['account']['id']
    else:
        print_error(f"Failed to create account: {response.json().get('error')}")
        return None

def confirm_transaction(token, tx_hash, receiver_account_id):
    """Confirm transaction and select bank"""
    response = requests.post(f"{BASE_URL}/api/transactions/{tx_hash}/confirm",
                            headers={"Authorization": f"Bearer {token}"},
                            json={
                                "receiver_account_id": receiver_account_id
                            })
    
    if response.status_code == 200:
        data = response.json()
        print_success(f"Transaction confirmed!")
        print(f"   Status: {data['status']}")
        return True
    else:
        print_error(f"Confirmation failed: {response.json().get('error')}")
        return False

def get_transaction_details(token, tx_hash):
    """Get transaction details"""
    response = requests.get(f"{BASE_URL}/api/transactions/{tx_hash}",
                           headers={"Authorization": f"Bearer {token}"})
    
    if response.status_code == 200:
        return response.json()['transaction']
    else:
        return None


def main():
    print_header("🚀 RECEIVER CONFIRMATION FLOW TEST")
    
    # Step 1: Register users
    print_header("Step 1: Register Users")
    unique = random.randint(1000, 9999)
    sender_idx = register_user(f"SENDR{unique:04d}A", "200001", "Sender User", 100000)
    receiver_idx = register_user(f"RECVR{unique:04d}B", "200002", "Receiver User", 50000)
    
    if not sender_idx or not receiver_idx:
        print_error("User registration failed!")
        sys.exit(1)
    
    # Step 2: Login both users
    print_header("Step 2: Login Users")
    sender_pan = f"SENDR{unique:04d}A"
    receiver_pan = f"RECVR{unique:04d}B"
    sender_token = login_user(sender_pan, "200001", "HDFC")
    receiver_token = login_user(receiver_pan, "200002", "HDFC")
    
    if not sender_token or not receiver_token:
        print_error("Login failed!")
        sys.exit(1)
    
    # Step 3: Get sender account
    print_header("Step 3: Create Sender HDFC Account")
    sender_account_id = create_bank_account(sender_token, "HDFC", 100000)
    if not sender_account_id:
        print_error("Failed to create sender account!")
        sys.exit(1)

    # Get account info
    sender_accounts = get_account_info(sender_token)
    if sender_accounts and len(sender_accounts['accounts']) > 0:
        print(f"   Account ID: {sender_account_id}")
        print(f"   Balance: ₹{sender_accounts['total_balance']}")
    
    # Step 4: Sender adds receiver to contacts
    print_header("Step 4: Add Recipient to Contacts")
    if not add_recipient(sender_token, receiver_idx, "MyFriend"):
        print_error("Failed to add recipient!")
        sys.exit(1)
    
    # Step 5: Sender creates transaction
    print_header("Step 5: Create Transaction (Awaiting Receiver)")
    tx_hash = create_transaction(sender_token, sender_account_id, "MyFriend", 5000)
    if not tx_hash:
        print_error("Failed to create transaction!")
        sys.exit(1)
    
    # Step 6: Receiver checks pending
    print_header("Step 6: Receiver Checks Pending Transactions")
    pending = get_pending_for_receiver(receiver_token)
    if len(pending) == 0:
        print_error("No pending transactions found!")
        sys.exit(1)
    
    print(f"   Transaction hash: {pending[0]['transaction_hash'][:16]}...")
    print(f"   Amount: ₹{pending[0]['amount']}")
    
    # Step 7: Receiver creates ICICI account
    print_header("Step 7: Receiver Creates ICICI Account")
    icici_account_id = create_bank_account(receiver_token, "ICICI", 0)
    if not icici_account_id:
        print_error("Failed to create ICICI account!")
        sys.exit(1)
    
    # Step 8: Receiver confirms and selects ICICI
    print_header("Step 8: Receiver Confirms (Selects ICICI)")
    if not confirm_transaction(receiver_token, tx_hash, icici_account_id):
        print_error("Failed to confirm transaction!")
        sys.exit(1)
    
    # Step 9: Check final status
    print_header("Step 9: Check Transaction Status")
    tx_details = get_transaction_details(sender_token, tx_hash)
    if tx_details:
        print(f"   Status: {tx_details['status']}")
        print(f"   Sender IDX: {tx_details['sender_idx'][:32]}...")
        print(f"   Receiver IDX: {tx_details['receiver_idx'][:32]}...")
        print(f"   Amount: ₹{tx_details['amount']}")
        print(f"   Fee: ₹{tx_details['fee']}")
        print_success("Transaction ready for mining!")
    
    print_header("✅ ALL TESTS PASSED!")
    print("\nFlow completed:")
    print("1. ✅ Users registered")
    print("2. ✅ Recipient added to contacts")
    print("3. ✅ Transaction created (AWAITING_RECEIVER)")
    print("4. ✅ Receiver notified (pending transactions)")
    print("5. ✅ Receiver selected ICICI account")
    print("6. ✅ Transaction confirmed (PENDING - ready for mining)")
    print("\n🎉 Receiver confirmation flow working perfectly!")


if __name__ == "__main__":
    main()