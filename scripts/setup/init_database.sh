#!/usr/bin/env bash
# [DOC] init_database.sh — One-shot database bootstrap script.
# [DOC] Run this once on a fresh machine (or a fresh PostgreSQL install)
# [DOC] before starting the API server for the first time.
# [DOC]
# [DOC] What it does, in order:
# [DOC]   1. Creates the idx_banking PostgreSQL database if it does not exist.
# [DOC]   2. Runs migration scripts 002-009 via run_migration_v3.py.
# [DOC]   3. Runs migration 010 via run_migration_010.py (real crypto fields).
# [DOC]
# [DOC] Prerequisites:
# [DOC]   - PostgreSQL 14+ must be running and the current OS user must have
# [DOC]     createdb privileges (i.e., `psql -l` works without a password).
# [DOC]   - The Python virtual environment venv310 must already exist.
# [DOC]     Run install_dependencies.sh first if it does not.
# [DOC]
# [DOC] Usage:
# [DOC]   bash scripts/setup/init_database.sh
# [DOC]
# [DOC] Safe to re-run: createdb exits with a warning (not an error) when
# [DOC] the database already exists, and all migration steps are idempotent.

# [DOC] set -e: exit immediately if any command returns a non-zero exit code.
# [DOC] This prevents later steps from running against a broken state —
# [DOC] e.g., if createdb fails we do not want to run migrations against
# [DOC] the wrong database.
set -e

# [DOC] Resolve the repository root directory from the location of this
# [DOC] script so the script works regardless of which directory the user
# [DOC] runs it from. SCRIPT_DIR is the directory containing this file;
# [DOC] PROJECT_ROOT is two levels up (scripts/setup/ -> project root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "============================================"
echo " IDX Crypto Banking — Database Initialisation"
echo "============================================"
echo "Project root: ${PROJECT_ROOT}"
echo ""

# [DOC] Step 1: Create the database.
# [DOC] `createdb idx_banking` issues a CREATE DATABASE SQL command via
# [DOC] the local PostgreSQL socket. If the database already exists,
# [DOC] createdb prints a warning and exits 0, so set -e does not abort.
# [DOC] The database name idx_banking is hard-coded here and must match
# [DOC] the DATABASE_URL in config/settings.py.
echo "Step 1: Creating PostgreSQL database idx_banking ..."
createdb idx_banking 2>/dev/null || echo "  (database already exists — skipping)"
echo "  OK"
echo ""

# [DOC] Step 2: Activate the Python 3.10 virtual environment.
# [DOC] venv310 was created with: python3.10 -m venv venv310
# [DOC] It contains all pip packages from requirements.txt plus the
# [DOC] charm-crypto-framework 0.62 installed from JHUISI source.
# [DOC] Sourcing the activate script prepends venv310/bin to PATH so
# [DOC] subsequent `python3` calls use the venv interpreter.
echo "Step 2: Activating Python virtual environment venv310 ..."
# shellcheck source=/dev/null
source "${PROJECT_ROOT}/venv310/bin/activate"
echo "  Python: $(python3 --version)"
echo ""

# [DOC] Step 3: Run migrations 002-009.
# [DOC] run_migration_v3.py uses SQLAlchemy to:
# [DOC]   a) Create all ORM-defined tables that do not yet exist.
# [DOC]   b) Add the V3.0 columns (commitment, nullifier, range_proof, etc.).
# [DOC]   c) Back-fill sequence_number for any pre-existing transaction rows.
# [DOC]   d) Create the required B-tree indexes.
# [DOC] It exits with code 1 on any failure, which triggers set -e to abort.
echo "Step 3: Running migrations 002-009 (run_migration_v3.py) ..."
cd "${PROJECT_ROOT}"
python3 scripts/run_migration_v3.py
echo ""

# [DOC] Step 4: Run migration 010 — real cryptographic field expansion.
# [DOC] This widens commitment/nullifier/commitment_salt from VARCHAR(66)
# [DOC] to TEXT (required for Pedersen EC point hex strings) and adds the
# [DOC] bbs_secret_key / bbs_public_key columns to consortium_banks.
# [DOC] Must run AFTER run_migration_v3.py because migration 010 alters
# [DOC] columns that v3 created.
echo "Step 4: Running migration 010 (run_migration_010.py) ..."
python3 scripts/run_migration_010.py
echo ""

echo "============================================"
echo " Database initialisation complete."
echo ""
echo " Next steps:"
echo "   python3 -c \"from database.connection import SessionLocal; \\"
echo "     from core.services.bank_account_service import BankAccountService; \\"
echo "     db=SessionLocal(); BankAccountService(db).setup_consortium_banks(); db.close()\""
echo "   python3 -m api.app          # Terminal 1: API server on :5000"
echo "   python3 core/workers/mining_worker.py  # Terminal 2: mining daemon"
echo "============================================"
