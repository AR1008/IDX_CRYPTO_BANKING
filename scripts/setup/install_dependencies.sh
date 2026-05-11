#!/usr/bin/env bash
# [DOC] install_dependencies.sh — Install all Python dependencies into venv310.
# [DOC]
# [DOC] This script handles the two-phase dependency installation:
# [DOC]   Phase 1: Standard pip packages from requirements.txt (79 packages).
# [DOC]   Phase 2: charm-crypto-framework 0.62 from JHUISI GitHub source.
# [DOC]            This package is NOT on PyPI. It implements BBS04 group
# [DOC]            signatures over BN254 pairing groups (used for anonymous
# [DOC]            consortium bank voting). It requires GMP, PBC, and OpenSSL
# [DOC]            C libraries on the host system.
# [DOC]
# [DOC] Prerequisites (macOS):
# [DOC]   brew install gmp pbc openssl python@3.10
# [DOC]
# [DOC] Prerequisites (Ubuntu/Debian):
# [DOC]   sudo apt-get install python3.10 python3.10-dev libgmp-dev libpbc-dev libssl-dev
# [DOC]
# [DOC] Usage:
# [DOC]   bash scripts/setup/install_dependencies.sh
# [DOC]
# [DOC] After this script completes, activate the environment with:
# [DOC]   source venv310/bin/activate

# [DOC] set -e: abort immediately on any non-zero exit code so a failed pip
# [DOC] install does not silently leave a broken environment.
set -e

# [DOC] Resolve the project root directory from this script's location so the
# [DOC] script works regardless of which directory the user runs it from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "============================================"
echo " IDX Crypto Banking — Dependency Installation"
echo "============================================"
echo "Project root: ${PROJECT_ROOT}"
echo ""

# [DOC] Step 1: Create the Python 3.10 virtual environment if it does not
# [DOC] already exist. Python 3.10.19 is required because charm-crypto 0.62
# [DOC] uses C extension APIs that are compatible with CPython 3.10 but have
# [DOC] not been ported to 3.11+ at the time of writing (2026-02-28).
# [DOC] The environment is placed at project_root/venv310/.
echo "Step 1: Creating Python 3.10 virtual environment (venv310) ..."
if [ ! -d "${PROJECT_ROOT}/venv310" ]; then
    python3.10 -m venv "${PROJECT_ROOT}/venv310"
    echo "  Created venv310"
else
    echo "  venv310 already exists — skipping creation"
fi
echo ""

# [DOC] Step 2: Activate the virtual environment so that pip and python3
# [DOC] below refer to the venv versions, not the system Python.
echo "Step 2: Activating venv310 ..."
# shellcheck source=/dev/null
source "${PROJECT_ROOT}/venv310/bin/activate"
echo "  Python: $(python3 --version)"
echo "  pip:    $(pip --version)"
echo ""

# [DOC] Step 3: Upgrade pip inside the venv to avoid outdated resolver
# [DOC] behaviour. Older pip versions mishandle dependency conflicts and
# [DOC] may produce broken environments silently.
echo "Step 3: Upgrading pip ..."
pip install --upgrade pip
echo ""

# [DOC] Step 4: Install all 79 standard packages listed in requirements.txt.
# [DOC] Key packages include:
# [DOC]   flask, flask-socketio    — REST API + WebSocket server
# [DOC]   sqlalchemy               — ORM for PostgreSQL
# [DOC]   pycryptodome             — AES-256-GCM encryption
# [DOC]   py_ecc                   — Elliptic curve arithmetic (secp256k1,
# [DOC]                              BN128) used by pedersen.py and schnorr.py
# [DOC]   pyjwt                    — JWT authentication tokens
# [DOC]   flask-limiter            — Rate limiting middleware
# [DOC]   psycopg2-binary          — PostgreSQL driver for SQLAlchemy
echo "Step 4: Installing standard packages from requirements.txt ..."
pip install -r "${PROJECT_ROOT}/requirements.txt"
echo ""

# [DOC] Step 5: Install charm-crypto-framework from JHUISI GitHub source.
# [DOC]
# [DOC] WHY NOT PyPI? The charm package on PyPI is unmaintained and does
# [DOC] not include the BBS04 group signature scheme used by this project.
# [DOC] The JHUISI fork (Johns Hopkins University Information Security
# [DOC] Institute) is the actively maintained research version.
# [DOC]
# [DOC] WHY IS THIS NEEDED? BBS04 group signatures allow each consortium
# [DOC] bank to vote anonymously on transaction batches. The signature proves
# [DOC] a legitimate member voted without revealing which bank, until the
# [DOC] regulatory authority opens it during a slashing dispute.
# [DOC]
# [DOC] IMPORTANT: charm-crypto requires native C libraries at compile time:
# [DOC]   libgmp    — GNU Multiple Precision arithmetic (large integers)
# [DOC]   libpbc    — Stanford Pairing-Based Cryptography library (BN254)
# [DOC]   libssl    — OpenSSL (hash functions)
# [DOC] If any of these are missing, the pip install will fail with a C
# [DOC] compiler error. Install them with your OS package manager first.
echo "Step 5: Installing charm-crypto-framework 0.62 from JHUISI source ..."
echo "  NOTE: This requires GMP, PBC, and OpenSSL C libraries."
echo "  macOS:  brew install gmp pbc openssl"
echo "  Ubuntu: sudo apt-get install libgmp-dev libpbc-dev libssl-dev"
echo ""
pip install git+https://github.com/JHUISI/charm.git@dev
echo ""

# [DOC] Step 6: Verify that the two most critical non-PyPI components can
# [DOC] be imported successfully. A failed import here means either the
# [DOC] C extension did not compile or a native library is missing from
# [DOC] the runtime linker path (LD_LIBRARY_PATH / DYLD_LIBRARY_PATH).
echo "Step 6: Verifying critical imports ..."
python3 -c "from charm.toolbox.pairinggroup import PairingGroup; print('  charm-crypto OK')"
python3 -c "from py_ecc.secp256k1 import secp256k1; print('  py_ecc OK')"
python3 -c "from Crypto.Cipher import AES; print('  pycryptodome OK')"
echo ""

echo "============================================"
echo " All dependencies installed successfully."
echo ""
echo " Activate the environment before running any code:"
echo "   source venv310/bin/activate"
echo ""
echo " Then initialise the database:"
echo "   bash scripts/setup/init_database.sh"
echo "============================================"
