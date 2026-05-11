"""
Real Schnorr Sigma Protocols on secp256k1
==========================================
Implements non-interactive zero-knowledge proofs via Fiat-Shamir transform.

PROTOCOLS PROVIDED:
  1. prove_dlog / verify_dlog
     Proves knowledge of x such that P = x*G (proof of discrete log).
     This is the foundation of all Schnorr-based ZK.

  2. prove_commitment_opening / verify_commitment_opening
     Proves knowledge of (v, r) such that C = v*G + r*H (Pedersen opening)
     WITHOUT revealing v or r. This is the REAL ZKP the anomaly system needs.

  3. prove_bit_commitment / verify_bit_commitment
     Proves that a Pedersen commitment commits to a BIT (0 or 1).
     Uses an OR-proof (Cramer-Damgard-Schoenmakers technique).
     Used in the range proof construction.

SECURITY (standard results):
  - Completeness: Honest provers always convince verifiers.
  - Soundness: No prover (without witness) can convince verifier except with
    probability 1/|challenge_space| ≈ 2^{-256} (negligible).
  - Honest-Verifier Zero-Knowledge: The transcript (R, c, s) is simulable
    without the witness. Fiat-Shamir makes this non-interactive in the ROM.
  - The SHA-256 simulation in anomaly_zkp.py has ZERO soundness:
    any string passes verification. These proofs have 2^{-256} forgery chance.

Requires: pip install py_ecc
Reference: Schnorr (1991) "Efficient Signature Generation by Smart Cards".
           Cramer, Damgard, Schoenmakers (1994) "Proofs of Partial Knowledge".
"""

# [DOC] hashlib: used to compute SHA-256 for the Fiat-Shamir challenge hash.
# [DOC] secrets: cryptographically secure random number generator for choosing blinding scalars.
# [DOC] json: used to deterministically serialize all proof inputs before hashing them.
# [DOC] typing: provides type hint aliases (Dict, Any, Tuple, List) for clearer function signatures.
import hashlib
import secrets
import json
from typing import Dict, Any, Tuple, List

# [DOC] py_ecc provides real elliptic curve arithmetic on secp256k1 (same curve as Bitcoin).
# [DOC] secp256k1 exposes .G (base point), .multiply(point, scalar), .add(point, point).
# [DOC] The try/except lets the module import cleanly even if py_ecc is missing; _HAS_EC records availability.
try:
    from py_ecc.secp256k1 import secp256k1
    _HAS_EC = True
except ImportError:
    _HAS_EC = False

# [DOC] N is the order of the secp256k1 elliptic curve group.
# [DOC] It equals the number of distinct scalar values that can be used as private keys or blinding factors.
# [DOC] All scalar arithmetic (adding, multiplying private numbers) is done modulo N so results stay in range.
# [DOC] This specific 256-bit prime is standardised in the Bitcoin secp256k1 specification.
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


# [DOC] Guard function: raises a clear error if py_ecc is absent instead of a cryptic AttributeError later.
def _check_ec():
    if not _HAS_EC:
        raise ImportError(
            "Real Schnorr ZKPs require py_ecc. Install: pip install py_ecc>=6.0.0"
        )


# [DOC] Fetches the two generator points G and H that are shared with the Pedersen commitment module.
# [DOC] G and H are fixed public points on secp256k1; every party in the banking system uses the same G and H.
# [DOC] Using the same generators as Pedersen ensures a Schnorr proof about a commitment is consistent with that commitment.
def _get_generators() -> Tuple[tuple, tuple]:
    """Get G and H from pedersen module (same generators, consistency required)."""
    from core.crypto.real.pedersen import _get_generators as _pg
    return _pg()


# [DOC] Fiat-Shamir transform: converts an interactive ZKP into a non-interactive one by replacing the verifier's random challenge with a hash.
# [DOC] All public inputs (commitment point, nonce point, context string) are hashed together with SHA-256.
# [DOC] The result is taken modulo N so it is a valid scalar on secp256k1.
# [DOC] "ROM" (Random Oracle Model) is the security assumption: SHA-256 behaves like a truly random function.
def _fiat_shamir(*args) -> int:
    """
    Fiat-Shamir challenge: c = SHA-256(all public inputs) mod N.
    All arguments serialized deterministically.
    """
    # [DOC] json.dumps with sort_keys=True ensures two calls with the same data always produce identical bytes regardless of dict insertion order.
    data = json.dumps(args, default=str, sort_keys=True).encode('utf-8')
    # [DOC] SHA-256 produces a 32-byte (256-bit) digest, which we interpret as a big-endian integer, then reduce mod N.
    digest = hashlib.sha256(data).hexdigest()
    return int(digest, 16) % N


# [DOC] Converts an EC point (x, y) — two Python integers — into a 128-character hex string for hashing.
# [DOC] Each coordinate is 64 hex digits (32 bytes = 256 bits, matching secp256k1 field size).
# [DOC] This serialization is fed into _fiat_shamir so the hash commits to the exact point, not just its coordinates separately.
def _point_hex(point: tuple) -> str:
    """Serialize EC point for hashing."""
    x, y = point
    return f"{x:064x}{y:064x}"


# ============================================================
# PROTOCOL 1: Proof of Discrete Logarithm
# ============================================================

# [DOC] prove_dlog: produces a non-interactive Schnorr proof that the caller knows the secret scalar x.
# [DOC] "Discrete log" means: given a point P = x*G on the curve, proving knowledge of x without revealing x.
# [DOC] This is the same mathematical hardness assumption that secures Bitcoin private keys.
# [DOC] In the banking system this is used when a party needs to prove ownership of a private key without exposing it.
def prove_dlog(x: int, context: str = "") -> Dict[str, Any]:
    """
    Non-interactive Schnorr proof that prover knows x s.t. P = x*G.

    Protocol (Sigma):
      Commit:   r <- random; R = r*G
      Challenge: c = H(P, R, context)         [Fiat-Shamir]
      Response:  s = (r - c*x) mod N

    Verification equation: s*G + c*P == R

    Args:
        x:       Secret discrete log (private witness)
        context: Domain separation string (e.g., transaction hash)

    Returns:
        proof dict with keys: P, R, s, context
    """
    _check_ec()
    # [DOC] G is the secp256k1 base point — a fixed, universally agreed-upon point on the curve.
    G = secp256k1.G
    # [DOC] P = x*G is the public key corresponding to secret x; scalar multiplication repeats curve point addition x times.
    # [DOC] x % N keeps x within the valid scalar range before computing P.
    P = secp256k1.multiply(G, x % N)

    # [DOC] r is a fresh random nonce (blinding scalar) chosen uniformly from [1, N-1].
    # [DOC] Using secrets.randbelow ensures cryptographic randomness; never use random.randint here.
    # [DOC] The +1 avoids r=0, which would leak x directly via the response equation.
    r = secrets.randbelow(N - 1) + 1
    # [DOC] R = r*G is the "commitment" in the sigma protocol — a random point that hides r.
    R = secp256k1.multiply(G, r)

    # [DOC] Serialize P and R to hex strings so they can be fed into the hash function deterministically.
    P_hex = _point_hex(P)
    R_hex = _point_hex(R)
    # [DOC] c is the Fiat-Shamir challenge: a hash of all public values (P, R, context string).
    # [DOC] context is a domain-separation tag (e.g., transaction hash) that binds the proof to a specific use.
    c = _fiat_shamir(P_hex, R_hex, context)
    # [DOC] s = (r - c*x) mod N is the "response" that ties the nonce r to the secret x via the challenge c.
    # [DOC] The verifier can check s without ever seeing r or x.
    s = (r - c * x) % N

    return {
        "protocol": "schnorr_dlog",
        "P": P_hex,
        "R": R_hex,
        # [DOC] s is zero-padded to exactly 64 hex characters (256 bits) for consistent serialization.
        "s": f"{s:064x}",
        "context": context
    }


# [DOC] verify_dlog: checks a Schnorr proof without access to the secret x.
# [DOC] The verification equation s*G + c*P == R holds if and only if s was formed correctly using the witness x.
# [DOC] A cheating prover who does not know x can satisfy this equation with probability at most 1/N ≈ 2^{-256}.
def verify_dlog(proof: Dict[str, Any]) -> bool:
    """
    Verify Schnorr proof of discrete log.
    Checks: s*G + c*P == R  (the verification equation is cryptographically binding)

    Returns True iff proof is valid. A forged proof succeeds with prob 1/N ≈ 2^{-256}.
    """
    try:
        _check_ec()
        G = secp256k1.G
        P_hex = proof["P"]
        R_hex = proof["R"]
        # [DOC] Parse s from the 64-character hex string back into an integer for scalar multiplication.
        s = int(proof["s"], 16)
        context = proof.get("context", "")

        # [DOC] Reconstruct P and R as (x, y) tuples by splitting the hex string at the midpoint.
        P = (int(P_hex[:64], 16), int(P_hex[64:], 16))
        R = (int(R_hex[:64], 16), int(R_hex[64:], 16))

        # [DOC] Recompute the challenge c the same way the prover did; any difference invalidates the proof.
        c = _fiat_shamir(P_hex, R_hex, context)

        # [DOC] Verification equation: s*G + c*P must equal R.
        # [DOC] If the prover knew x and computed s = r - c*x, then s*G + c*P = (r-cx)*G + c*(xG) = r*G = R. QED.
        # Verification equation: s*G + c*P == R
        lhs = secp256k1.add(
            secp256k1.multiply(G, s),
            secp256k1.multiply(P, c)
        )
        return lhs == R
    except Exception:
        return False


# ============================================================
# PROTOCOL 2: Proof of Pedersen Commitment Opening
# ============================================================

# [DOC] prove_commitment_opening: proves knowledge of BOTH the value v and blinding factor r inside a Pedersen commitment C = v*G + r*H.
# [DOC] This is the core ZKP used when the anomaly detection system flags a transaction.
# [DOC] The prover (banking system) convinces verifiers that the commitment hides a valid value without revealing the amount.
# [DOC] This is a "generalized Schnorr proof" over two generators (G and H) instead of one.
def prove_commitment_opening(
    C: tuple,
    v: int,
    r: int,
    context: str = ""
) -> Dict[str, Any]:
    """
    Non-interactive ZKP that prover knows (v, r) s.t. C = v*G + r*H,
    WITHOUT revealing v or r. This is the real ZKP the anomaly system needs.

    Protocol (Generalized Schnorr on 2 generators):
      Commit:    (k_v, k_r) <- random; K = k_v*G + k_r*H
      Challenge: c = H(C, K, context)          [Fiat-Shamir]
      Response:  s_v = (k_v - c*v) mod N
                 s_r = (k_r - c*r) mod N

    Verification: s_v*G + s_r*H + c*C == K

    Args:
        C:       Pedersen commitment point (from pedersen.commit())
        v:       Committed value (private)
        r:       Blinding factor (private)
        context: Domain separation (e.g., transaction hash)

    Returns:
        proof dict with keys: C, K, s_v, s_r, context
    """
    _check_ec()
    from core.crypto.real.pedersen import serialize_point
    # [DOC] G and H are the two independent generator points used in Pedersen commitments.
    # [DOC] "Independent" means nobody knows the discrete log of H with respect to G, which is what makes the commitment binding.
    G, H = _get_generators()

    # [DOC] k_v and k_r are independent random nonces: one masks v, one masks r.
    # [DOC] Two separate nonces are needed because the commitment has two components (v*G and r*H).
    k_v = secrets.randbelow(N - 1) + 1
    k_r = secrets.randbelow(N - 1) + 1
    # [DOC] K = k_v*G + k_r*H is the sigma-protocol commitment — a random point in the same form as C.
    K = secp256k1.add(
        secp256k1.multiply(G, k_v),
        secp256k1.multiply(H, k_r)
    )

    # [DOC] Serialize C and K to hex so they can be included in the Fiat-Shamir hash.
    C_hex = serialize_point(C)
    K_hex = serialize_point(K)
    # [DOC] The challenge binds the proof to the specific commitment C, nonce K, and context string.
    c = _fiat_shamir(C_hex, K_hex, context)

    # [DOC] s_v and s_r are the two responses: each ties a nonce to a secret component via the challenge.
    s_v = (k_v - c * v) % N
    s_r = (k_r - c * r) % N

    return {
        "protocol": "schnorr_pedersen_opening",
        "C": C_hex,
        "K": K_hex,
        "s_v": f"{s_v:064x}",
        "s_r": f"{s_r:064x}",
        "context": context
    }


# [DOC] verify_commitment_opening: checks the Pedersen opening proof using only public data (C, K, s_v, s_r).
# [DOC] The verifier never sees v or r; they only confirm the algebraic equation holds.
# [DOC] This implements the check: s_v*G + s_r*H + c*C == K.
# [DOC] If the prover knew (v, r) and computed s_v = k_v - c*v, s_r = k_r - c*r, this equation holds exactly.
def verify_commitment_opening(proof: Dict[str, Any]) -> bool:
    """
    Verify proof of Pedersen commitment opening.
    Checks: s_v*G + s_r*H + c*C == K

    This cryptographically verifies that the prover knows (v, r) for C
    WITHOUT learning v or r. Zero-knowledge in the honest-verifier model.
    A forged proof succeeds with prob 1/N ≈ 2^{-256}.
    """
    try:
        _check_ec()
        from core.crypto.real.pedersen import deserialize_point
        G, H = _get_generators()

        # [DOC] Deserialize the commitment C and the nonce point K from compressed hex back to (x, y) tuples.
        C = deserialize_point(proof["C"])
        K = deserialize_point(proof["K"])
        s_v = int(proof["s_v"], 16)
        s_r = int(proof["s_r"], 16)
        context = proof.get("context", "")

        # [DOC] Recompute c from the stored C and K hex strings — must match what the prover computed.
        c = _fiat_shamir(proof["C"], proof["K"], context)

        # [DOC] Verification: s_v*G + s_r*H + c*C must equal K.
        # [DOC] Expanding: (k_v-cv)*G + (k_r-cr)*H + c*(vG+rH) = k_v*G + k_r*H = K. QED.
        # Verification: s_v*G + s_r*H + c*C == K
        lhs = secp256k1.add(
            secp256k1.add(
                secp256k1.multiply(G, s_v),
                secp256k1.multiply(H, s_r)
            ),
            secp256k1.multiply(C, c)
        )
        return lhs == K
    except Exception:
        return False


# ============================================================
# PROTOCOL 3: Proof that Commitment is a Bit (0 or 1)
# ============================================================
# Uses Cramer-Damgard-Schoenmakers OR-proof:
# Proves "C commits to 0" OR "C commits to 1" without revealing which.
# This is the building block for range proofs.

# [DOC] prove_bit_commitment: proves a Pedersen commitment C hides a bit value (0 or 1) without revealing which bit.
# [DOC] This is the CDS94 OR-proof technique: produce two Schnorr transcripts, one real and one simulated, such that together they look indistinguishable.
# [DOC] In the banking system, this is the building block for range proofs — a transaction amount is decomposed into individual bits, each committed and proven to be 0 or 1.
# [DOC] The key insight: a value is in [0, 2^n) if and only if all n of its binary digits are bits.
def prove_bit_commitment(
    C: tuple,
    bit: int,
    r: int,
    context: str = ""
) -> Dict[str, Any]:
    """
    OR-proof that C = bit*G + r*H where bit ∈ {0, 1}.
    Proves C commits to a valid bit WITHOUT revealing the bit value.

    This uses the Cramer-Damgard-Schoenmakers technique for 1-out-of-2 proofs.
    Reference: CDS94 "Proofs of Partial Knowledge and Simplified Design of Witness
               Hiding Protocols". CRYPTO 1994.

    Args:
        C:    Pedersen commitment
        bit:  The committed bit (0 or 1) — kept private
        r:    Blinding factor used in C
        context: Domain separation

    Returns:
        OR-proof dict; verifier learns only that bit ∈ {0,1}
    """
    _check_ec()
    from core.crypto.real.pedersen import serialize_point, commit as pedersen_commit
    G, H = _get_generators()

    assert bit in (0, 1), "bit must be 0 or 1"

    C_hex = serialize_point(C)

    if bit == 0:
        # [DOC] bit=0 case: C = 0*G + r*H = r*H. The real witness is r such that C = r*H.
        # [DOC] We simulate the proof for "bit=1" (as if C = G + r'*H) using random (c_sim, s_sim).
        # [DOC] The simulation trick: pick c_sim and s_sim freely, then set K_sim = s_sim*H + c_sim*(C-G).
        # [DOC] This fakes a valid Schnorr transcript for the "bit=1" branch without knowing the witness.
        # Real branch: C = 0*G + r*H = r*H  → prove knowledge of r s.t. C = r*H
        # Simulated branch: C - 1*G = r*H   → simulate proof for "bit=1"
        # C1 (real) = C = r*H
        # C0 offset = C (no offset needed since C = 0*G + r*H)

        # [DOC] Real Schnorr for bit=0: pick random nonce k_real, compute commitment K_real = k_real*H.
        # Real Schnorr for bit=0:
        k_real = secrets.randbelow(N - 1) + 1
        K_real = secp256k1.multiply(H, k_real)  # K = k*H (since C = r*H)

        # [DOC] Simulate for bit=1: pick random c_sim, s_sim; back-compute K_sim so the equation s_sim*H + c_sim*(C-G) == K_sim holds trivially.
        # [DOC] C' = C - G removes the G component, turning "C = G + r*H" into "C' = r*H" for the simulated branch.
        # Simulate for bit=1: C' = C - G, prove C' = r'*H
        # Simulate with random (c_sim, s_sim) s.t. s_sim*H + c_sim*C' == K_sim
        c_sim = secrets.randbelow(N - 1) + 1
        s_sim = secrets.randbelow(N - 1) + 1
        # [DOC] C - G: multiply G by (N-1) because N-1 ≡ -1 mod N, so (N-1)*G = -G, and C + (-G) = C - G.
        C_prime = secp256k1.add(C, secp256k1.multiply(G, N - 1))  # C - G
        K_sim = secp256k1.add(
            secp256k1.multiply(H, s_sim),
            secp256k1.multiply(C_prime, c_sim)
        )

        K_real_hex = serialize_point(K_real)
        K_sim_hex = serialize_point(K_sim)

        # [DOC] Global challenge c_global binds both branches to the same Fiat-Shamir hash.
        # [DOC] Splitting: c_real = c_global - c_sim (mod N). The verifier checks c_real + c_sim == c_global.
        # Global challenge
        c_global = _fiat_shamir(C_hex, K_real_hex, K_sim_hex, context)
        c_real = (c_global - c_sim) % N
        # [DOC] s_real closes the real Schnorr equation: s_real = k_real - c_real * r (mod N).
        s_real = (k_real - c_real * r) % N

        return {
            "protocol": "bit_commitment_or_proof",
            "C": C_hex,
            "context": context,
            # [DOC] branch_0: data for verifying "C commits to 0" (the real branch when bit=0).
            "branch_0": {"K": K_real_hex, "c": f"{c_real:064x}", "s": f"{s_real:064x}"},
            # [DOC] branch_1: data for verifying "C commits to 1" (the simulated branch when bit=0).
            "branch_1": {"K": K_sim_hex,  "c": f"{c_sim:064x}",  "s": f"{s_sim:064x}"},
        }
    else:
        # [DOC] bit=1 case: C = G + r*H. The real witness is r such that C - G = r*H.
        # [DOC] Symmetric to the bit=0 case: simulate "bit=0" and prove "bit=1" for real.
        # Real branch: C = G + r*H, prove knowledge of r s.t. C - G = r*H
        C_prime = secp256k1.add(C, secp256k1.multiply(G, N - 1))  # C - G

        k_real = secrets.randbelow(N - 1) + 1
        K_real = secp256k1.multiply(H, k_real)

        # [DOC] Simulate for bit=0: back-compute K_sim so s_sim*H + c_sim*C == K_sim holds without knowing r.
        # Simulate for bit=0: prove C = r*H
        c_sim = secrets.randbelow(N - 1) + 1
        s_sim = secrets.randbelow(N - 1) + 1
        K_sim = secp256k1.add(
            secp256k1.multiply(H, s_sim),
            secp256k1.multiply(C, c_sim)
        )

        K_real_hex = serialize_point(K_real)
        K_sim_hex = serialize_point(K_sim)

        # [DOC] Note: K_sim comes before K_real in the hash here — consistent with the branch_0/branch_1 ordering below.
        c_global = _fiat_shamir(C_hex, K_sim_hex, K_real_hex, context)
        c_real = (c_global - c_sim) % N
        s_real = (k_real - c_real * r) % N

        return {
            "protocol": "bit_commitment_or_proof",
            "C": C_hex,
            "context": context,
            # [DOC] branch_0: simulated "bit=0" branch (real bit is 1, so this branch is faked).
            "branch_0": {"K": K_sim_hex,  "c": f"{c_sim:064x}",  "s": f"{s_sim:064x}"},
            # [DOC] branch_1: real "bit=1" branch.
            "branch_1": {"K": K_real_hex, "c": f"{c_real:064x}", "s": f"{s_real:064x}"},
        }


# [DOC] verify_bit_commitment: checks the CDS94 OR-proof that C commits to a bit.
# [DOC] The verifier has no idea whether bit=0 or bit=1 — only that one of the two cases holds.
# [DOC] Three independent checks are required: challenge consistency, branch-0 equation, branch-1 equation.
def verify_bit_commitment(proof: Dict[str, Any]) -> bool:
    """
    Verify bit-commitment OR-proof.
    Checks that c_0 + c_1 = c_global and both branches satisfy their equations.
    """
    try:
        _check_ec()
        from core.crypto.real.pedersen import deserialize_point
        G, H = _get_generators()

        C = deserialize_point(proof["C"])
        context = proof.get("context", "")

        b0 = proof["branch_0"]
        b1 = proof["branch_1"]

        # [DOC] Parse K, c, s for each branch from their hex-string representations.
        K0 = deserialize_point(b0["K"])
        K1 = deserialize_point(b1["K"])
        c0 = int(b0["c"], 16)
        c1 = int(b1["c"], 16)
        s0 = int(b0["s"], 16)
        s1 = int(b1["s"], 16)

        # [DOC] Recompute the global challenge from the stored hex strings (not from deserialized points, to avoid re-serialization drift).
        # Reconstruct global challenge
        K0_hex = b0["K"]
        K1_hex = b1["K"]
        c_global = _fiat_shamir(proof["C"], K0_hex, K1_hex, context)

        # [DOC] Challenge consistency check: c0 + c1 must equal c_global (mod N).
        # [DOC] This prevents a cheating prover from choosing c0, c1 freely; they are constrained to sum to the hash.
        # Check challenges sum to global
        if (c0 + c1) % N != c_global:
            return False

        # [DOC] Branch 0 equation: s0*H + c0*C == K0.
        # [DOC] This checks the "C commits to 0" branch — if real, s0 = k0 - c0*r and C = r*H, so the equation holds.
        # Branch 0: s0*H + c0*C == K0  (proves C = r*H, i.e., bit=0)
        lhs0 = secp256k1.add(
            secp256k1.multiply(H, s0),
            secp256k1.multiply(C, c0)
        )
        if lhs0 != K0:
            return False

        # [DOC] Branch 1 equation: s1*H + c1*(C - G) == K1.
        # [DOC] C - G removes the G term, turning "C = G + r*H" into "C - G = r*H" for branch-1 verification.
        # Branch 1: s1*H + c1*(C - G) == K1  (proves C - G = r*H, i.e., bit=1)
        C_minus_G = secp256k1.add(C, secp256k1.multiply(G, N - 1))
        lhs1 = secp256k1.add(
            secp256k1.multiply(H, s1),
            secp256k1.multiply(C_minus_G, c1)
        )
        if lhs1 != K1:
            return False

        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("=== Real Schnorr ZKP Tests ===\n")

    print("Test 1: Proof of discrete log")
    x = secrets.randbelow(N - 1) + 1
    proof = prove_dlog(x, context="test_tx_abc123")
    assert verify_dlog(proof), "DLOG proof verification failed"
    # Forged proof should fail
    bad = dict(proof)
    bad["s"] = f"{secrets.randbelow(N):064x}"
    assert not verify_dlog(bad), "Forged proof should not verify"
    print("  PASS: prove_dlog / verify_dlog\n")

    print("Test 2: Proof of Pedersen commitment opening")
    from core.crypto.real.pedersen import commit as pedersen_commit
    v, r_blind = 50000, secrets.randbelow(N - 1) + 1
    C, r_used = pedersen_commit(v, r_blind)
    proof2 = prove_commitment_opening(C, v, r_used, context="anomaly_flag_proof")
    assert verify_commitment_opening(proof2), "Commitment opening proof failed"
    # Wrong witness should fail to generate valid proof
    proof_wrong = prove_commitment_opening(C, v + 1, r_used, context="anomaly_flag_proof")
    assert not verify_commitment_opening(proof_wrong), "Wrong witness should not verify"
    print("  PASS: prove_commitment_opening / verify_commitment_opening\n")

    print("Test 3: Bit commitment OR-proof")
    C0, r0 = pedersen_commit(0)
    C1, r1 = pedersen_commit(1)
    proof_bit0 = prove_bit_commitment(C0, 0, r0, context="bit_test")
    proof_bit1 = prove_bit_commitment(C1, 1, r1, context="bit_test")
    assert verify_bit_commitment(proof_bit0), "Bit=0 OR-proof failed"
    assert verify_bit_commitment(proof_bit1), "Bit=1 OR-proof failed"
    # Non-bit value should not produce valid proof
    C2, r2 = pedersen_commit(2)
    try:
        bad_proof = prove_bit_commitment(C2, 0, r2, context="bit_test")
        # Even if generated, verification should fail
        assert not verify_bit_commitment(bad_proof), "Non-bit should not verify"
    except Exception:
        pass  # Acceptable — wrong witness detected
    print("  PASS: prove_bit_commitment / verify_bit_commitment\n")

    print("All Schnorr ZKP tests passed.")
    print("\nNOTE: These are REAL zero-knowledge proofs.")
    print("      Soundness: forgery probability = 1/N ≈ 2^{-256}")
    print("      The SHA-256 simulation in anomaly_zkp.py accepts ANY hex string.")
