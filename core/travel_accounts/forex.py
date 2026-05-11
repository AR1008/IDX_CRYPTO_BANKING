# [DOC] FILE: core/travel_accounts/forex.py
# [DOC] STATUS: Stub / not yet implemented.
# [DOC]
# [DOC] PURPOSE (intended):
# [DOC]   Fetch and cache foreign-exchange rates for travel account transactions.
# [DOC]   When a user sends money from an Indian bank account into a travel account
# [DOC]   denominated in a foreign currency (USD, GBP, SGD, AED), the system needs
# [DOC]   an up-to-date INR → foreign currency conversion rate.
# [DOC]
# [DOC] INTENDED DESIGN:
# [DOC]   - Pull rates from an external API (e.g., RBI reference rates or a commercial
# [DOC]     forex feed) at startup and periodically refresh (e.g., every 15 minutes).
# [DOC]   - Cache rates in-process to avoid a network call per transaction.
# [DOC]   - Store historical rates in the forex_rates DB table so that past
# [DOC]     transactions can be audited at the rate that was in effect at the time.
# [DOC]   - Expose a single convert(amount_inr, target_currency) helper for use by
# [DOC]     core/travel_accounts/manager.py when debiting travel accounts.
# [DOC]
# [DOC] WHY NOT YET IMPLEMENTED:
# [DOC]   Travel account cross-border flows are a secondary feature; the core
# [DOC]   privacy primitives (Pedersen, Bulletproofs, BBS04) were prioritised for
# [DOC]   the CCS 2027 submission. This file is a placeholder so that the module
# [DOC]   structure is correct and imports do not fail.
# [DOC]
# [DOC] TO IMPLEMENT:
# [DOC]   1. Create a ForexService class with get_rate(currency_code) and
# [DOC]      convert(amount, from_currency, to_currency) methods.
# [DOC]   2. Use the forex_rates ORM model (database/models/forex_rates.py) to
# [DOC]      persist rates for audit purposes.
# [DOC]   3. Wire refresh into the background workers (core/workers/).
