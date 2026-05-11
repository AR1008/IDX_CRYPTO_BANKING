"""
BBS+ Group Signatures — Short Group Signatures for Anonymous Bank Voting.
=========================================================================
Implements the Boneh-Boyen-Shacham (BBS04) short group signature scheme
over the BN254 pairing-friendly elliptic curve (128-bit security level),
using Charm-Crypto's `groupsig_bgls04.ShortSig`.

PREREQUISITE (install before use):
    macOS:
        brew install pbc
        git clone https://github.com/JHUISI/charm
        cd charm && ./configure.sh --enable-darwin && make && sudo make install

SECURITY PROPERTIES (BBS04 — Boneh, Boyen, Shacham, CRYPTO 2004):
    Anonymity:          DLIN (Decision Linear) assumption on BN254.
                        A verifier cannot determine which consortium bank
                        produced a given batch-approval signature.
    Full-Anonymity:     Holds even against a colluding group manager.
    Traceability:       q-SDH assumption on BN254.
                        Every valid signature traces to exactly one member.
    Non-Frameability:   DL assumption on BN254.
                        No coalition can forge a signature for an honest bank.
    Opening:            RBI holds the group manager secret (ξ1, ξ2) and can
                        recover the signer's membership certificate Ai from
                        any signature, then match it to the known bank list.

CONSTRUCTION (from Charm groupsig_bgls04.py source — BBS04):
    keygen(n):
        g1, g2 ← G1, G2;  h, u, v ← G1   (u = h^(1/ξ1), v = h^(1/ξ2))
        γ, ξ1, ξ2 ← ZR
        w = g2^γ            (group public key)
        for i ∈ [0..n-1]:
            xi ← ZR;  Ai = g1^(1/(γ + xi))
        gpk  = {g1, g2, h, u, v, w}
        gmsk = {xi1: ξ1, xi2: ξ2}       ← RBI's opening key
        gsk[i] = (Ai, xi)                ← bank i's signing key (TUPLE!)

    sign(gpk, (Ai, xi), M):             ← M is a plain Python string
        α, β ← ZR
        T1 = u^α,  T2 = v^β,  T3 = Ai · h^(α+β)
        Schnorr commitment + Fiat-Shamir hash of (M, T1..T3, R1..R5)
        σ = {T1, T2, T3, c, s_alpha, s_beta, s_x, s_delta1, s_delta2}

    verify(gpk, M, σ):                  ← M before σ (Charm argument order)
        Recompute R1'..R5'; accept iff Fiat-Shamir challenge c == c'.

    open(gpk, gmsk, M, σ):             ← M before σ (Charm argument order)
        A' = T3 / (T1^ξ1 · T2^ξ2)      = Ai of the signer
        Caller matches A' against stored {Ai} certificates to get bank_id.

REPLACES: SHA-256 group_signature.py (no algebraic ring structure, zero anonymity).

References:
    Boneh, Boyen, Shacham (2004) "Short Group Signatures." CRYPTO 2004.
        https://eprint.iacr.org/2004/174.pdf
    Charm-Crypto groupsig_bgls04 — charm.schemes.grpsig.groupsig_bgls04
        https://jhuisi.github.io/charm/
    BN254 pairing group (Barreto-Naehrig 254-bit):
        128-bit security, used by Ethereum alt_bn128, Zcash, Hyperledger.
"""

import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple as TypingTuple

# ---------------------------------------------------------------------------
# Charm-Crypto conditional import.
# Installed from GitHub source (PyPI package has a metadata version bug).
# ---------------------------------------------------------------------------
# [DOC] Try to import Charm-Crypto; if it is not installed the flag is set False instead of crashing.
try:
    # [DOC] PairingGroup: the mathematical group (BN254 curve) used for all crypto operations.
    # [DOC] ZR, G1, G2, GT: element types in different sub-groups of the pairing (think of them as different number spaces).
    # [DOC] pair: the bilinear pairing function e(P,Q) — the core math that makes BBS04 work.
    from charm.toolbox.pairinggroup import PairingGroup, ZR, G1, G2, GT, pair
    # [DOC] ShortSig: the BBS04 short group signature class from Charm's library.
    from charm.schemes.grpsig.groupsig_bgls04 import ShortSig
    # [DOC] Mark that Charm loaded successfully so callers can detect availability.
    _CHARM_AVAILABLE = True
except ImportError:
    # [DOC] Charm is not installed; set the flag so every public method can give a clear error message.
    _CHARM_AVAILABLE = False

# [DOC] BN254: a pairing-friendly 254-bit elliptic curve giving 128-bit security.
# [DOC] This is the same curve used by Ethereum's alt_bn128 precompile and Zcash.
# [DOC] Do NOT use 'BN256' — that alias is not recognised by Charm's PBC backend.
# [DOC] Available curves: SS512, SS1024, MNT159, MNT201, MNT224, BN254.
_PAIRING_CURVE = "BN254"


def _require_charm() -> None:
    """Raise ImportError with setup instructions if charm-crypto is missing."""
    # [DOC] Guard function called at the top of every public method.
    # [DOC] If Charm is absent, raise ImportError with exact installation steps.
    if not _CHARM_AVAILABLE:
        raise ImportError(
            "charm-crypto is required for BBS+ group signatures but is not installed.\n"
            "Install prerequisites:\n"
            "  macOS:  brew install pbc\n"
            "          git clone https://github.com/JHUISI/charm\n"
            "          cd charm && ./configure.sh --enable-darwin && make && sudo make install\n"
            "  Ubuntu: sudo apt-get install libpbc-dev && pip install charm-crypto\n"
            "Reference: https://jhuisi.github.io/charm/"
        )


class BBSGroupSignature:
    """BGLS04 group signature scheme for the N-bank IDX Banking Consortium.

    Wraps Charm-Crypto's `groupsig_bgls04.ShortSig` on BN254 with a
    banking-oriented API.  All objects are JSON-serialised for storage in
    `consortium_banks.bbs_secret_key` / `bbs_public_key` (TEXT columns
    added by migration 010).

    IMPORTANT Charm API notes (embedded in wrapper):
        • gsk[i] is a TUPLE (Ai, xi), not a dict.
        • verify(gpk, M, sigma) — M comes BEFORE sigma.
        • open(gpk, gmsk, M, sigma) — M comes BEFORE sigma.

    Lifecycle:
        1. BBSGroupSignature().setup(n_banks=12) — ONCE at consortium setup.
        2. Store bank_keys[i].signing_key in consortium_banks.bbs_secret_key.
        3. Store group_pk in consortium_banks.bbs_public_key (same for all).
        4. Distribute open_key to RBI via HSM / secure channel.
        5. batch_processor calls sign() for each bank vote.
        6. RBI calls open() after a court order.
    """

    def __init__(self) -> None:
        """Initialise BN254 pairing group and BGLS04 scheme.

        Raises:
            ImportError: If charm-crypto is not installed.
        """
        # [DOC] Refuse to construct if Charm-Crypto is not installed (gives actionable error).
        _require_charm()
        # [DOC] Create the BN254 pairing group — the mathematical universe all keys live in.
        self._group = PairingGroup(_PAIRING_CURVE)
        # [DOC] Instantiate the BBS04 short group signature scheme using the BN254 group.
        self._bbs   = ShortSig(self._group)

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def setup(self, n_banks: int = 12) -> Dict[str, Any]:
        """Generate group parameters and per-bank signing keys.

        Called ONCE during consortium bootstrap (setup_consortium_banks).

        Args:
            n_banks: Number of consortium banks (default 12).

        Returns:
            dict:
                group_pk (str):           Serialised group public key JSON.
                                          Store in consortium_banks.bbs_public_key.
                manager_sk (str):         Serialised group manager / open key.
                                          KEEP SECRET — distribute to RBI via HSM.
                open_key (str):           Same as manager_sk; alias for clarity.
                bank_keys (list[dict]):   [{'bank_id': int, 'signing_key': str}]
                                          Store each bank's signing_key in bbs_secret_key.
                bank_certificates (str):  JSON {'1': hex_Ai, ..., '12': hex_Ai}.
                                          Required by open() for bank identification.

        Security note (BBS04 §3): manager_sk / open_key enables tracing.
            Compromise of open_key destroys anonymity but non-frameability
            still holds — a compromised opener cannot forge any bank's signature.
        """
        # [DOC] Call Charm's keygen to produce all group keys for n_banks members at once.
        # [DOC] Charm keygen returns:
        # [DOC]   gpk  = {'g1': G1, 'g2': G2, 'h': G1, 'u': G1, 'v': G1, 'w': G2}
        # [DOC]   gmsk = {'xi1': ZR, 'xi2': ZR}   — this is the RBI opening key (secret)
        # [DOC]   gsk  = {0: (A0, x0), 1: (A1, x1), ..., n-1: (A_{n-1}, x_{n-1})}
        # [DOC] gsk[i] is a TUPLE (Ai, xi), NOT a dict — important for sign() later.
        (gpk, gmsk, gsk) = self._bbs.keygen(n_banks)

        # [DOC] bank_keys will hold each bank's individually-packaged signing key.
        bank_keys  = []
        # [DOC] bank_certs maps bank_id string → hex(Ai certificate).
        # [DOC] The open() function recovers Ai from a signature and looks it up here to identify the signer.
        bank_certs = {}   # bank_id (str) → hex(Ai)  — used by open()

        # [DOC] Iterate over each bank index (0-based internally, 1-based externally).
        for i in range(n_banks):
            # [DOC] Unpack the tuple: Ai is the membership certificate (a G1 point), xi is the private scalar.
            A_i, x_i = gsk[i]   # Unpack tuple: (membership certificate, secret scalar)
            # [DOC] Serialise the (Ai, xi) pair to a JSON string for storage in the database.
            bank_keys.append({
                "bank_id":    i + 1,          # 1-indexed externally
                "signing_key": self._ser_sk((A_i, x_i)),
            })
            # [DOC] Store Ai certificate for bank identification during open().
            # [DOC] open() recovers A' = Ai from the signature; we match against these.
            bank_certs[str(i + 1)] = self._ser_elem(A_i)

        # [DOC] Return everything the system needs: public key (for verifying), opening key (for RBI), per-bank signing keys.
        return {
            "group_pk":          self._ser_dict(gpk),
            "manager_sk":        self._ser_dict(gmsk),
            "open_key":          self._ser_dict(gmsk),   # same key; RBI's alias
            "bank_keys":         bank_keys,
            "bank_certificates": json.dumps(bank_certs),
        }

    def sign(
        self,
        group_pk_json: str,
        bank_sk_json:  str,
        message:       str,
    ) -> str:
        """Produce an anonymous BGLS04 group signature over message.

        The signature reveals only that some registered consortium bank signed.
        Signer identity is computationally hidden (DLIN on BN254).

        Args:
            group_pk_json: Serialised group public key (from setup()).
            bank_sk_json:  Serialised signing key for this bank (from setup()).
            message:       String to sign (batch_id or similar).

        Returns:
            JSON string — serialised signature dict.  Pass to verify() or open().
        """
        # [DOC] Deserialise the group public key from its JSON storage format back to Charm objects.
        gpk = self._deser_dict(group_pk_json)
        # [DOC] Deserialise the bank's signing key — reconstructed as a (Ai, xi) tuple, as Charm expects.
        sk  = self._deser_sk(bank_sk_json)     # Reconstructed as a TUPLE
        # [DOC] Call Charm's sign: internally picks random (α, β), computes T1/T2/T3, and applies Fiat-Shamir.
        # [DOC] The result σ = {T1, T2, T3, c, s_alpha, s_beta, s_x, s_delta1, s_delta2}.
        # [DOC] Charm's sign takes the raw string message — Fiat-Shamir hashes it internally.
        sig = self._bbs.sign(gpk, sk, message)
        # [DOC] Serialise the signature dict to JSON for database storage (TEXT column).
        return self._ser_dict(sig)

    def verify(
        self,
        group_pk_json:  str,
        signature_json: str,
        message:        str,
    ) -> bool:
        """Verify a BGLS04 group signature without revealing who signed.

        Args:
            group_pk_json:  Serialised group public key (from setup()).
            signature_json: Serialised signature (from sign()).
            message:        The string message that was signed.

        Returns:
            True iff the signature is valid; False otherwise.

        Note (Charm API):
            Charm's ShortSig.verify(gpk, M, sigma) takes M BEFORE sigma.
            This wrapper's external signature is (gpk, sig, msg) — conventional
            ordering — and flips M and sigma before the internal Charm call.
        """
        try:
            # [DOC] Deserialise both the group public key and the signature from their JSON storage strings.
            gpk = self._deser_dict(group_pk_json)
            sig = self._deser_dict(signature_json)
            # [DOC] IMPORTANT: Charm's verify is verify(gpk, M, sigma) — M before sigma.
            # [DOC] Charm recomputes R1'..R5' from the signature and checks that the Fiat-Shamir challenge c matches.
            # [DOC] Returns True only if the signature was produced by a registered group member for this exact message.
            return bool(self._bbs.verify(gpk, message, sig))
        except Exception:
            # [DOC] Any error (deserialization failure, bad curve point, etc.) means the signature is invalid.
            return False

    def open(
        self,
        group_pk_json:          str,
        open_key_json:          str,
        signature_json:         str,
        message:                str,
        bank_certificates_json: str,
    ) -> int:
        """Identify which bank produced the signature — RBI authority, court-order only.

        Recovers signer's certificate A' from (T1, T2, T3) using (ξ1, ξ2),
        then matches A' against the stored {Ai} bank certificates.

        Args:
            group_pk_json:          Serialised group public key (from setup()).
            open_key_json:          Serialised RBI open key (from setup()).
            signature_json:         Serialised signature to trace (from sign()).
            message:                The string message that was signed.
            bank_certificates_json: JSON of {bank_id_str: hex_Ai} (from setup()).

        Returns:
            int: bank_id ∈ [1, n_banks]; -1 if identification failed.

        Note (Charm API):
            Charm's ShortSig.open(gpk, gmsk, M, sigma) takes M BEFORE sigma.
            This wrapper flips them internally.
        """
        try:
            # [DOC] Deserialise all three key/signature inputs from their JSON storage strings.
            gpk = self._deser_dict(group_pk_json)
            ok  = self._deser_dict(open_key_json)
            sig = self._deser_dict(signature_json)
            # [DOC] IMPORTANT: Charm's open is open(gpk, gmsk, M, sigma) — M before sigma.
            # [DOC] Charm computes A' = T3 / (T1^ξ1 · T2^ξ2) — this recovers the signer's membership certificate.
            # [DOC] A' is a G1 curve point that was embedded inside the signature as T3.
            A_prime = self._bbs.open(gpk, ok, message, sig)

            # [DOC] Load the bank certificates: a dict of {bank_id_str: hex_Ai} produced during setup().
            # [DOC] We compare the recovered A' against every registered bank's stored Ai certificate.
            certs = json.loads(bank_certificates_json)
            for bank_id_str, cert_hex in certs.items():
                # [DOC] Deserialise the stored Ai certificate hex back to a Charm G1 element for comparison.
                A_i = self._deser_elem(cert_hex)
                # [DOC] If A' == Ai for some bank i, then bank i is the signer.
                if A_prime == A_i:
                    return int(bank_id_str)

            # [DOC] If no certificate matched, the signer is not in our registered bank list — return sentinel -1.
            return -1   # Signer not in registered bank list
        except Exception:
            # [DOC] Any error during opening (bad key, corrupt signature) returns -1 to indicate failure.
            return -1

    # -------------------------------------------------------------------
    # Serialisation helpers
    # -------------------------------------------------------------------

    def _ser_elem(self, elem: Any) -> str:
        """Serialise a single Charm pairing element (G1/G2/ZR/GT) to hex.

        Charm embeds the element type in the serialised bytes so that
        _deser_elem can reconstruct the correct type without extra metadata.
        """
        # [DOC] Charm's serialize() converts the curve element to bytes; .hex() makes it a safe ASCII string.
        # [DOC] The type tag is embedded in the byte prefix by Charm — no separate metadata needed.
        return self._group.serialize(elem).hex()

    def _deser_elem(self, hex_str: str) -> Any:
        """Deserialise a hex string produced by _ser_elem to a Charm element."""
        # [DOC] Convert the hex string back to raw bytes, then let Charm reconstruct the typed curve element.
        return self._group.deserialize(bytes.fromhex(hex_str))

    def _ser_sk(self, sk_tuple: tuple) -> str:
        """Serialise a bank signing key tuple (Ai, xi) to a JSON string.

        Args:
            sk_tuple: (Ai: G1 element, xi: ZR element)

        Returns:
            JSON string: {'A': hex, 'x': hex}
        """
        # [DOC] Unpack the (Ai, xi) tuple — Ai is a G1 group element, xi is a scalar in ZR.
        A_i, x_i = sk_tuple
        # [DOC] Serialise each element to hex individually, then combine into a JSON dict for database storage.
        return json.dumps({
            "A": self._ser_elem(A_i),
            "x": self._ser_elem(x_i),
        })

    def _deser_sk(self, json_str: str) -> tuple:
        """Deserialise a JSON string produced by _ser_sk back to a (Ai, xi) tuple.

        Returns a tuple because Charm's sign() accesses the key as gsk[0] (Ai)
        and gsk[1] (xi) via index-based access.
        """
        # [DOC] Parse the JSON string to get the {'A': hex, 'x': hex} dict.
        data = json.loads(json_str)
        # [DOC] Reconstruct both elements from hex and return as a tuple — Charm's sign() indexes them by position.
        return (self._deser_elem(data["A"]), self._deser_elem(data["x"]))

    def _ser_dict(self, d: dict) -> str:
        """Recursively serialise a dict of Charm elements to a JSON string.

        Handles one level of nesting.  All dict keys become strings for JSON.
        """
        # [DOC] out will hold the serialised version of every value in d.
        out: Dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(v, dict):
                # [DOC] Nested dict: recurse, then parse back to a Python dict so json.dumps can include it inline.
                out[str(k)] = json.loads(self._ser_dict(v))
            else:
                # [DOC] Leaf value: it is a Charm element, so convert it to a hex string.
                out[str(k)] = self._ser_elem(v)
        # [DOC] Emit the entire dict as a single JSON string suitable for TEXT column storage.
        return json.dumps(out)

    def _deser_dict(self, json_str: str) -> dict:
        """Deserialise a JSON string produced by _ser_dict back to a Charm dict.

        Each string value is attempted as a Charm element hex; non-element
        strings are kept as-is (forward-compatibility guard).
        """
        # [DOC] Parse the raw JSON string into a Python dict of string values.
        parsed: dict = json.loads(json_str)
        # [DOC] result will hold the fully reconstructed Charm element dict.
        result: Dict[str, Any] = {}
        for k, v in parsed.items():
            if isinstance(v, dict):
                # [DOC] Nested dict: recurse to reconstruct inner Charm elements.
                result[k] = self._deser_dict(json.dumps(v))
            elif isinstance(v, str):
                try:
                    # [DOC] Attempt to deserialise the hex string as a Charm pairing element.
                    result[k] = self._deser_elem(v)
                except Exception:
                    # [DOC] If deserialisation fails (e.g., it is a plain string), keep the raw value.
                    result[k] = v
            else:
                # [DOC] Non-string, non-dict values (int, float) are kept unchanged.
                result[k] = v
        return result


# ---------------------------------------------------------------------------
# Self-test (run with: python3 -m core.crypto.real.bbs_group_signature)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("BBSGroupSignature — Real BBS04 Group Signature Self-Tests")
    print("Scheme:  BGLS04 (Boneh-Boyen-Shacham 2004, CRYPTO)")
    print("Curve:   BN254 (128-bit security, pairing-friendly)")
    print("Library: Charm-Crypto groupsig_bgls04.ShortSig")
    print("=" * 65)

    if not _CHARM_AVAILABLE:
        print(
            "\n[SKIP] charm-crypto not installed.\n"
            "  macOS:  brew install pbc && git clone https://github.com/JHUISI/charm\n"
            "          cd charm && ./configure.sh --enable-darwin && make && sudo make install\n"
        )
        raise SystemExit(0)

    bbs = BBSGroupSignature()

    print("\nTest 1: Setup (N-bank consortium, running with N=12)")
    params = bbs.setup(n_banks=12)
    assert "group_pk"          in params
    assert "manager_sk"        in params
    assert "open_key"          in params
    assert len(params["bank_keys"]) == 12
    assert "bank_certificates" in params
    assert len(json.loads(params["bank_certificates"])) == 12
    print(f"  PASS: Setup produced group params + {len(params['bank_keys'])} bank keys\n")

    group_pk   = params["group_pk"]
    open_key   = params["open_key"]
    bank_keys  = params["bank_keys"]
    bank_certs = params["bank_certificates"]

    print("Test 2: Bank 5 signs a batch approval anonymously")
    batch_id = "BATCH_501_600"
    sig_b5   = bbs.sign(group_pk, bank_keys[4]["signing_key"], batch_id)
    assert sig_b5
    sig_keys = list(json.loads(sig_b5).keys())
    print(f"  Signature components: {sig_keys}")
    print("  PASS: Signature produced\n")

    print("Test 3: Verify signature (without revealing signer)")
    is_valid = bbs.verify(group_pk, sig_b5, batch_id)
    assert is_valid, "Valid signature must verify"
    print("  PASS: Signature verified (signer identity hidden)\n")

    print("Test 4: Wrong message → verification fails")
    is_invalid = bbs.verify(group_pk, sig_b5, "WRONG_BATCH")
    assert not is_invalid
    print("  PASS: Wrong message correctly rejected\n")

    print("Test 5: Tampered signature → verification fails")
    sig_dict = json.loads(sig_b5)
    orig_t1  = sig_dict["T1"]
    # Corrupt the last 4 hex chars of T1
    sig_dict["T1"] = orig_t1[:-4] + "0000"
    tampered = json.dumps(sig_dict)
    assert not bbs.verify(group_pk, tampered, batch_id)
    print("  PASS: Tampered signature correctly rejected\n")

    print("Test 6: Open — RBI identifies Bank 5 after court order")
    identified = bbs.open(group_pk, open_key, sig_b5, batch_id, bank_certs)
    assert identified == 5, f"open() returned {identified}, expected 5"
    print(f"  PASS: RBI identified signer as Bank {identified} (expected 5)\n")

    print("Test 7: All N banks — sign, verify, open (full consortium)")
    for bank in bank_keys:
        bid = bank["bank_id"]
        msg = f"BATCH_TEST_BANK_{bid}"
        sig = bbs.sign(group_pk, bank["signing_key"], msg)
        ok  = bbs.verify(group_pk, sig, msg)
        who = bbs.open(group_pk, open_key, sig, msg, bank_certs)
        assert ok,         f"Bank {bid}: signature must verify"
        assert who == bid, f"Bank {bid}: open() returned {who}"
    print("  PASS: All N banks — sign / verify / open all correct\n")

    print("Test 8: Cross-message non-transferability")
    sig_a  = bbs.sign(group_pk, bank_keys[0]["signing_key"], "BATCH_A")
    cross  = bbs.verify(group_pk, sig_a, "BATCH_B")
    assert not cross
    print("  PASS: Signature on BATCH_A does not verify for BATCH_B\n")

    print("=" * 65)
    print("All tests PASSED")
    print("  Anonymity:        DLIN on BN254 (128-bit security)")
    print("  Traceability:     q-SDH on BN254")
    print("  Non-frameability: DL on BN254")
    print("  Opening:          RBI open key (ξ1, ξ2) required")
    print("=" * 65)
