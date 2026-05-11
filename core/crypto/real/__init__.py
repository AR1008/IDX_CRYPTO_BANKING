"""
Real Cryptographic Primitives Package
======================================
This package contains REAL cryptographic implementations using elliptic curve
arithmetic on secp256k1. These replace the SHA-256 simulations in the parent
directory for production use and honest academic evaluation.

Modules:
  pedersen.py       - Real Pedersen commitments (C = v*G + r*H, computationally hiding,
                      perfectly binding, homomorphic under DDH assumption)
  schnorr.py        - Real Schnorr sigma protocols (proof of discrete log, proof of
                      commitment opening — honest-verifier ZK under DLOG assumption,
                      non-interactive via Fiat-Shamir in ROM)
  simple_range.py   - Real (but simplified) range proof using Pedersen bit-commitments
                      + Schnorr OR-proofs for each bit. Honest, not Bulletproofs-speed.

Dependency: py_ecc >= 6.0.0  (pip install py_ecc)
"""
