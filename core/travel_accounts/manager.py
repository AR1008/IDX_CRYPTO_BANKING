# [DOC] FILE: core/travel_accounts/manager.py
# [DOC] STATUS: Stub / not yet implemented.
# [DOC]
# [DOC] PURPOSE (intended):
# [DOC]   Manage the full lifecycle of travel accounts — creation, activation,
# [DOC]   spending-limit enforcement, and closure.
# [DOC]
# [DOC] WHAT A TRAVEL ACCOUNT IS:
# [DOC]   A temporary sub-account a user opens when travelling abroad. It:
# [DOC]     - Is linked to a foreign bank via a SWIFT code.
# [DOC]     - Has a pre-funded balance in INR (converted to foreign currency on use).
# [DOC]     - Has a spending limit set at creation (e.g., ₹5,00,000 for 30 days).
# [DOC]     - Expires after a configured number of days (duration_days in the DB model).
# [DOC]     - Can be frozen by court order like any other account.
# [DOC]
# [DOC] INTENDED SPENDING-LIMIT ENFORCEMENT:
# [DOC]   Each debit from the travel account generates a Bulletproofs range proof:
# [DOC]     prove(amount, upper_bound=remaining_limit)
# [DOC]   The proof shows amount <= remaining_limit WITHOUT revealing the exact amount.
# [DOC]   Consortium banks verify the proof during the transaction consensus step.
# [DOC]   This is the same ZK range proof used for domestic transactions but with a
# [DOC]   tighter upper bound set by the travel account's configured spending limit.
# [DOC]
# [DOC] INTENDED API:
# [DOC]   TravelAccountManager.create(user_idx, bank_code, currency, duration_days, limit)
# [DOC]     → creates a TravelAccount ORM record, generates initial range proof parameters
# [DOC]   TravelAccountManager.activate(account_id)
# [DOC]     → marks account active; debit/credit become possible
# [DOC]   TravelAccountManager.debit(account_id, amount)
# [DOC]     → checks spending limit via range proof; updates balance; calls forex.py for
# [DOC]       INR → foreign currency conversion
# [DOC]   TravelAccountManager.close(account_id)
# [DOC]     → marks account inactive; remaining balance returned to home bank account
# [DOC]
# [DOC] WHY NOT YET IMPLEMENTED:
# [DOC]   Travel account flows depend on forex.py (also a stub) and require additional
# [DOC]   DB migrations for per-account spending-limit fields. Prioritised below the
# [DOC]   core ZK primitives needed for the CCS 2027 submission.
# [DOC]
# [DOC] TO IMPLEMENT:
# [DOC]   1. Create TravelAccountManager class (mirrors BankAccountService pattern).
# [DOC]   2. Import ForexService from core/travel_accounts/forex.py for conversions.
# [DOC]   3. Import bulletproofs_wrapper from core/crypto/real/ for spending-limit proofs.
# [DOC]   4. Use TravelAccount ORM model from database/models/travel_account.py.
# [DOC]   5. Add background worker to expire travel accounts past their duration_days.
