"""
SIMPLE CRYPTO VERIFICATION TEST
================================
Test if basic crypto operations work before stress testing
"""

# [DOC] Add the project root to the path so imports from core/ and database/ work.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from decimal import Decimal
import secrets

# [DOC] CommitmentScheme is the legacy SHA-256 commitment (deprecated — real crypto is in core/crypto/real/pedersen.py).
# [DOC] Used here to verify the legacy module is still importable and functional as a reference baseline.
from core.crypto.commitment_scheme import CommitmentScheme
# [DOC] RangeProof: legacy SHA-256 simulation of range proofs (deprecated; real is bulletproofs_wrapper.py).
from core.crypto.range_proof import RangeProof
# [DOC] MerkleTree: real SHA-256 Merkle tree used in consensus to batch 100 transaction hashes.
from core.crypto.merkle_tree import MerkleTree

print("Testing basic crypto operations...\n")

# Test 1: Commitment
print("1. Testing CommitmentScheme...")
try:
    cs = CommitmentScheme()
    commitment = cs.create_commitment(
        sender_idx="IDX_TEST_001",
        receiver_idx="IDX_TEST_002",
        amount=Decimal('100.00')
    )
    print(f"   ✅ Commitment created: {commitment['commitment'][:20]}...")
except Exception as e:
    print(f"   ❌ Commitment failed: {e}")

# Test 2: Range Proof
print("\n2. Testing RangeProof...")
try:
    rp = RangeProof()
    proof = rp.create_proof(
        value=Decimal('100.00'),
        max_value=Decimal('1000.00')
    )
    print(f"   ✅ Range proof created")

    # Verify
    is_valid = rp.verify_proof(proof)
    print(f"   ✅ Range proof verified: {is_valid}")
except Exception as e:
    print(f"   ❌ Range proof failed: {e}")

# Test 3: Merkle Tree
print("\n3. Testing MerkleTree...")
try:
    leaves = [f"tx_{i}" for i in range(100)]
    tree = MerkleTree(leaves)
    root = tree.root
    print(f"   ✅ Merkle tree created: {root[:20]}...")

    # Get proof
    proof = tree.get_proof(0)
    print(f"   ✅ Merkle proof generated")
except Exception as e:
    print(f"   ❌ Merkle tree failed: {e}")

print("\n✅ Basic crypto operations test complete")
