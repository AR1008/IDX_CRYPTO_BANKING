"""
LEGACY — SHA-256 Simulation Modules (NOT wired into production pipeline)
=========================================================================
These modules existed before 2026-02-21 and used SHA-256 hashing to
simulate cryptographic properties that SHA-256 does not actually provide.
They are kept for reference and to document what was replaced.

Real replacements (wired into transaction pipeline):
  commitment_scheme.py  →  core/crypto/real/pedersen.py
  range_proof.py        →  core/crypto/real/bulletproofs_wrapper.py
  group_signature.py    →  core/crypto/real/bbs_group_signature.py

DO NOT import these modules in any production code.
"""

# [DOC] This __init__.py intentionally contains NO imports and exports
# [DOC] NO symbols. Its sole purpose is to make the legacy/ directory a
# [DOC] Python package so that the deprecation docstring above is the
# [DOC] first thing a developer sees when they navigate here.
# [DOC]
# [DOC] If you arrived here looking for a working commitment scheme,
# [DOC] range proof, or group signature, use the real implementations:
# [DOC]
# [DOC]   Pedersen commitments (secp256k1, IND-CPA hiding, perfectly binding):
# [DOC]     from core.crypto.real.pedersen import PedersenCommitment
# [DOC]
# [DOC]   Bulletproofs range proofs (Rust dalek v4, Ristretto255, 8.76ms prove):
# [DOC]     from core.crypto.real.bulletproofs_wrapper import BulletproofsWrapper
# [DOC]
# [DOC]   BBS04 group signatures (Charm-Crypto, BN254 pairing):
# [DOC]     from core.crypto.real.bbs_group_signature import BBSGroupSignature
# [DOC]
# [DOC] WHY ARE THE LEGACY MODULES KEPT AT ALL?
# [DOC]   1. Academic paper comparison: the paper must describe what was
# [DOC]      replaced and why; these files provide concrete evidence.
# [DOC]   2. Regression tests: a few old unit tests import these classes.
# [DOC]      Removing them would break the test suite until those tests
# [DOC]      are updated to use the real implementations.
# [DOC]   3. Reviewer traceability: CCS 2027 reviewers can diff the old
# [DOC]      and new implementations to verify the claims in Section 4.
