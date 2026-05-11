# ZK-AML: Complete Plan of Action for ACM CCS Submission

## Part 1 — Honest Verification of Your Current State

### What you correctly identified

Your self-assessment is accurate. Here is what each warning means against the state of the art:

**commitment_scheme.py (SHA-256 hash, not Pedersen):** Platypus uses Pedersen commitments (unconditionally hiding, computationally binding under DLOG) for account state commitments. PayOff inherits this. Androulaki et al. (2024) uses Pedersen commitments for token representations. Your SHA-256 hash commitment is binding but not hiding in the algebraic sense — it cannot be opened to different values, but it also cannot be used inside a zero-knowledge proof circuit because it has no homomorphic structure. This is the single most critical gap because everything downstream (range proofs, ZK proofs of compliance) depends on algebraically structured commitments.

**range_proof.py (zero soundness):** Platypus enforces balance non-negativity and holding limits inside Groth16 circuits. PayOff does the same. Your range proof has no mathematical soundness guarantee, meaning a malicious prover could claim any balance. At CCS, reviewers will immediately check whether your range proofs reduce to a known hard problem. They don't currently.

**group_signature.py (no ring structure, no anonymity, no unforgeability):** Androulaki et al. (2024) uses BBS+ signatures with formal EUF-CMA security and Pointcheval-Sanders blind signatures for anonymous credential issuance. Platypus achieves unlinkability through ZK-SNARKs over signed state commitments (different approach, same privacy goal). Your group signature provides none of these properties. For your architecture, you probably don't need group signatures at all — you need either (a) anonymous credentials (BBS+ style) if you go the Androulaki route, or (b) ZK-SNARKs over signed commitments if you go the Platypus route.

**anomaly_zkp.py (66-char verifier bug, no real ZK):** The bug you found (and honestly documented) is symptomatic of a deeper issue: the ZKP system doesn't use a proper proof system. At CCS level, the minimum bar is either a SNARK (Groth16, PLONK) or a Sigma protocol (Schnorr, Fiat-Shamir transformed) with a formal proof of soundness and zero-knowledge. Your anomaly detection ZKP needs to be either (a) a proper Sigma protocol proving knowledge of a witness satisfying your AML predicate, or (b) compiled into a circuit for a general-purpose proof system.

**Escrow layer (threshold-shared symmetric XOR key):** This is what the reviewer explicitly flagged. The Androulaki et al. (2023) framework uses threshold cryptography (specifically, threshold issuance of credentials and threshold signing among central bank entities) based on discrete-log assumptions. PayOff and Androulaki (2024) use EC-ElGamal (IND-CPA under DDH) with verifiable encryption for auditor access. Your XOR-based threshold sharing of a symmetric key has no semantic security — an attacker who learns any share gains partial information about the key. ElGamal threshold decryption, by contrast, is semantically secure under DDH even if t-1 of n shares are compromised.

### Verdict on your 4000 TPS benchmark

This number needs to be discarded entirely. Platypus achieves 80K-150K TPS with a centralized bank verifying Groth16 proofs. PayOff achieves ~5000 TPS for the central bank component. But these are with real cryptographic operations (Groth16 verification takes ~3ms; Pedersen commitment operations are sub-millisecond). Your 4000 TPS with SHA-256 hashes is measuring network/database throughput, not cryptographic throughput. Once you implement real crypto, expect 50-200 TPS for a distributed multi-node deployment, which is honest and publishable if you explain the tradeoff clearly.

---

## Part 2 — Verification of Your Proposed Phases

Your 6-phase plan is directionally correct. Here is my assessment of each:

**Phase 1 (Replace SHA-256 with Bulletproofs + LSAG):** Partially correct. Bulletproofs are the right replacement for range proofs specifically (they prove v ∈ [0, 2^n) without trusted setup). But you also need Pedersen commitments as the foundation (Bulletproofs operate over Pedersen commitments natively). LSAG ring signatures are appropriate IF your architecture needs sender anonymity within a set — but consider whether your architecture actually calls for ring signatures or whether anonymous credentials (BBS+) are more appropriate. Platypus doesn't use ring signatures; it uses ZK-SNARKs. PayOff doesn't either. Androulaki (2024) uses BBS+ and Pointcheval-Sanders. Ring signatures would be a different design choice that you'd need to justify. Recommendation: Use Pedersen commitments + Bulletproofs. For anonymity, choose either ZK-SNARKs (Platypus approach) or BBS+ anonymous credentials (Androulaki approach). If you specifically want ring signatures for your AML compliance layer (proving membership in a "compliant set" without revealing which member), that could be novel — but you need to justify it.

**Phase 2 (Compliance-Binding Commitment / CBC):** This is your strongest novelty claim and it checks out. No existing CBDC paper defines a formal cryptographic primitive that simultaneously binds a transaction to both its value AND its AML compliance status in zero knowledge. Platypus enforces regulation (holding/receiving limits) inside the ZK-SNARK circuit but treats it as an application-level rule, not as a standalone primitive. PayOff does the same. Androulaki (2024) uses verifiable encryption for auditor de-anonymization but doesn't formalize a "compliance commitment" as a primitive. If you define CBC with formal syntax (KeyGen, Commit, Prove, Verify, Open), define security properties (Rule-Privacy, Compliance-Soundness, Non-Frameability), and prove it secure under standard assumptions, this would be a genuine contribution. This is real.

**Phase 3 (Role-Constrained Threshold Decryption / RCTD):** This is weaker than CBC as a novelty claim but still potentially publishable as a building block. Threshold ElGamal is well-studied (Desmedt-Frankel, Shoup). What would be novel is formalizing the role constraint — that different decryption participants have different policy-level roles (central bank auditor vs. law enforcement vs. compliance officer) and the threshold structure is heterogeneous (e.g., need 2-of-3 auditors AND 1-of-2 law enforcement). If you simply implement standard threshold ElGamal, CCS reviewers will say "this is textbook." If you formalize role-based access control integrated into the threshold structure with a proper security definition, that's different. Recommendation: Position RCTD as a supporting contribution, not a primary one. CBC should be your anchor.

**Phase 4 (Game-based security proofs):** Essential. Every CCS paper in this space has formal security proofs. Platypus proves transaction indistinguishability via a hybrid argument over 9 game transitions. Androulaki (2024) proves security by reduction to PS signature unforgeability, BBS+ unforgeability, Pedersen binding, and ZK soundness. You need at minimum: (1) a proof that CBC satisfies Rule-Privacy under DDH, (2) a proof that CBC satisfies Compliance-Soundness under DLOG, (3) a proof that RCTD satisfies semantic security under DDH, (4) a system-level proof that your full protocol provides transaction indistinguishability. Collaborating with a cryptography professor is strongly recommended.

**Phase 5 (12-node AWS deployment):** Good but needs framing. Platypus and PayOff benchmark with a single centralized bank node. Androulaki (2023) benchmarks with Hyperledger Fabric across multiple nodes. Your multi-node deployment is interesting IF your architecture is genuinely distributed (not just replicated). If you're running consensus across 12 nodes, compare against the Androulaki (2023) framework's TPS numbers. If you're running a single logical bank across regions, compare against Platypus/PayOff. Be clear about what the 12 nodes represent architecturally.

**Phase 6 (Paper rewrite):** The structure is right. Two pages of related work, formal definitions, real proofs, honest benchmarks. Title "ZK-AML" is good. My suggestion: the paper should be structured as (1) define CBC primitive, (2) define RCTD as supporting primitive, (3) construct the ZK-AML protocol using CBC + RCTD, (4) prove security, (5) implement and benchmark, (6) compare against Platypus/PayOff/Androulaki.

### Timeline assessment

Your 15-18 month estimate targeting CCS 2027 is realistic. CCS 2026 is extremely risky unless you already have strong implementation skills in elliptic curve cryptography and can move through Phases 1-3 in 6 months.

---

## Part 3 — Refined Plan of Action

### Guiding Principles

1. CBC (Compliance-Binding Commitment) is your anchor contribution. Everything else supports it.
2. Honest benchmarks on real cryptography, even if slow, beat inflated numbers on simulated crypto.
3. Every claim must be backed by either a formal proof or an experimental measurement. No hand-waving.
4. Position clearly against Platypus, PayOff, Androulaki (2024), and Androulaki (2023). Show you know the landscape and explain why your approach fills a specific gap.
5. Your paper is your brainchild — the architecture, the compliance-binding idea, the role-constrained threshold concept. The tools help you execute it rigorously.

---

### PHASE 0: Foundation & Literature Positioning (Weeks 1-3)

**Goal:** Lock down your contribution statement and architecture before writing any code.

**Tasks:**

0.1. Write a 1-page contribution statement answering: "What can ZK-AML do that Platypus, PayOff, and the Androulaki systems cannot?" The answer should be: "ZK-AML introduces the first formal cryptographic primitive (CBC) that allows a CBDC user to prove AML compliance of a transaction in zero knowledge without revealing the transaction details or the specific AML rule being satisfied. Existing systems (Platypus, PayOff) enforce compliance rules inside ZK circuits as application logic but do not define compliance verification as a reusable, composable primitive with its own security definitions."

0.2. Draft a related work section (2 pages). Structure it as:
- Privacy-preserving CBDCs: Platypus (CCS 2022), PayOff (2024), Androulaki et al. (2024), Androulaki et al. (2023)
- Compliance and regulation in CBDCs: Allen et al. (2020), plus ECB digital euro reports
- ZK proofs for financial compliance: Zcash (Sasson et al.), ZKP applications in AML (search for recent work)
- Threshold cryptography in financial systems: Desmedt-Frankel, Shoup's practical threshold signatures
For each, state clearly what they achieve and what they don't (i.e., none defines a formal compliance primitive).

0.3. Define your system architecture diagram. Show the following participants and how they interact: Users, Central Bank (issuer), Settlement Engine (possibly distributed), Compliance Auditor(s), and the role RCTD plays in distributing audit authority. Map this against the Androulaki (2023) framework's Figure 1 to show architectural alignment.

0.4. Choose your anonymity approach and justify it:
- Option A: ZK-SNARKs over signed state commitments (Platypus approach) — higher TPS, simpler to reason about, requires trusted setup (or use PLONK for universal setup)
- Option B: Anonymous credentials with BBS+ (Androulaki 2024 approach) — no trusted setup, composable, but more complex protocol
- Option C: Ring signatures (LSAG) — provides sender anonymity within a set, novel in CBDC context if combined with CBC, but you need to justify why this is better than Options A/B
Recommendation: Option A or B. Only choose C if you have a clear argument for why ring-based anonymity specifically benefits compliance proofs.

**Deliverable:** A 3-5 page design document containing your contribution statement, related work outline, architecture diagram, and anonymity approach justification. This is your north star.

---

### PHASE 1: Cryptographic Foundation (Months 1-3)

**Goal:** Replace all placeholder crypto with real implementations.

#### 1A. Pedersen Commitments (Week 1-2)

Replace SHA-256 commitment with Pedersen commitments on an elliptic curve.

Implementation approach:
- Use the `py_ecc` library (you already added it to requirements.txt) for BN128 or BLS12-381 curve operations
- Pedersen commitment: `C = g^v · h^r` where g, h are generators with unknown discrete log relation, v is the value, r is random blinding factor
- Implement: `KeyGen(1^λ) → (g, h)`, `Commit(v, r) → C`, `Open(C, v, r) → {0,1}`
- Verify: hiding (unconditional — for any C, any v' there exists r' such that C = g^v' · h^r'), binding (computational — under DLOG, cannot find (v,r) ≠ (v',r') opening to same C)
- Critical: the homomorphic property `Commit(v1,r1) · Commit(v2,r2) = Commit(v1+v2, r1+r2)` is what makes Bulletproofs work. Test this property explicitly.

What to test:
- Binding: verify that you cannot open a commitment to two different values
- Homomorphic addition: verify that `C1 * C2` opens to `v1 + v2`
- Performance: measure commitment creation time (should be < 1ms)

#### 1B. Bulletproofs Range Proofs (Weeks 3-8)

Replace your placeholder range proof with real Bulletproofs.

Implementation approach:
- Option 1 (recommended): Use a Rust Bulletproofs library (dalek-cryptography/bulletproofs) via Python ctypes/cffi bindings. This gives you production-grade performance.
- Option 2: Use a pure Python implementation for prototyping (slower but simpler to debug). The `fastbulletproofs` Python package exists but verify its correctness.
- Bulletproofs prove that a committed value v lies in [0, 2^n) without revealing v, with proof size O(log n) and no trusted setup.

What to implement:
- `RangeProve(v, r, n) → π` where C = Commit(v,r) and π proves v ∈ [0, 2^n)
- `RangeVerify(C, π, n) → {0,1}`
- Aggregated range proofs: prove that multiple committed values are all in range simultaneously (Bulletproofs support this natively, and it's important for batch transaction verification)

What to test:
- Soundness: verify that proving v = -1 (or v > 2^n) fails
- Performance: measure prove time and verify time for n = 32 (32-bit range) and n = 64
- Proof size: should be ~700 bytes for a single 64-bit range proof

#### 1C. Signature Scheme (Weeks 5-8)

Choose and implement the signature scheme for your architecture.

If you chose Option A (SNARK-based anonymity like Platypus):
- Implement EdDSA or BLS signatures for the central bank to sign state commitments
- The anonymity comes from the ZK proof hiding the signature, not from the signature itself

If you chose Option B (anonymous credentials like Androulaki 2024):
- Implement BBS+ signatures: `Sign(sk, (m1,...,mn)) → σ`, `Verify(pk, (m1,...,mn), σ) → {0,1}`
- Implement zero-knowledge proof of knowledge of a BBS+ signature (this is what gives you anonymous credentials)
- This is substantially more complex but gives you composable anonymous credentials

If you chose Option C (ring signatures):
- Implement LSAG (Linkable Spontaneous Anonymous Group signatures)
- LSAG gives sender anonymity within a ring plus linkability for double-spend detection
- Prove unforgeability and anonymity under DLOG

**Deliverable:** Working implementations of Pedersen commitments, Bulletproofs range proofs, and your chosen signature scheme, all with unit tests verifying the security properties.

---

### PHASE 2: CBC Primitive — Your Core Contribution (Months 3-6)

**Goal:** Define, implement, and prove secure the Compliance-Binding Commitment primitive.

#### 2A. Formal Definition (Weeks 1-2)

Write the formal definition of CBC. This is the most important section of your paper. It must be precise enough that another cryptographer could implement it from the definition alone.

**Syntax (algorithms):**

```
CBC.Setup(1^λ, R) → pp
  Input: security parameter λ, set of compliance rules R = {R_1, ..., R_k}
  Output: public parameters pp (including commitment keys, CRS if needed)

CBC.Commit(pp, v, aux, r) → (C, st)
  Input: public parameters, transaction value v, auxiliary data aux 
         (sender identity, receiver identity, cumulative amounts, etc.), 
         randomness r
  Output: commitment C, secret state st

CBC.ProveCompliance(pp, C, st, R_i) → π
  Input: public parameters, commitment C, secret state st, rule R_i ∈ R
  Output: zero-knowledge proof π that the committed transaction 
          satisfies rule R_i

CBC.VerifyCompliance(pp, C, π, R_i) → {0,1}
  Input: public parameters, commitment C, proof π, rule R_i
  Output: accept/reject

CBC.Open(pp, C, st) → (v, aux) or ⊥
  Input: public parameters, commitment C, secret state st
  Output: opening (v, aux) if valid, failure otherwise
```

**Compliance rules R to support (based on AML/CFT requirements from Allen et al.):**
- R_threshold: transaction value v ≤ threshold T (e.g., reporting threshold of $10,000)
- R_cumulative: sender's cumulative daily/weekly amount ≤ limit L
- R_holding: recipient's post-transaction balance ≤ holding limit H
- R_sanctioned: sender/receiver not on sanctioned entity list (this requires commitment to identity with ZK proof of non-membership)

#### 2B. Security Definitions (Week 3)

Define three security properties with formal games:

**Rule-Privacy:** No PPT adversary can determine which compliance rule R_i was satisfied by observing (C, π), beyond what is leaked by the verification result. Formally: for any two rules R_i, R_j that the committed transaction satisfies, the proofs π_i and π_j are computationally indistinguishable. This is what makes CBC novel — in Platypus, the regulator knows which rule is being enforced because the circuit is specific to the rule. In CBC, the compliance proof hides the rule.

**Compliance-Soundness:** No PPT adversary can produce (C, π) such that VerifyCompliance accepts but the committed transaction actually violates rule R_i. Formally: given pp, adversary outputs (C, π, R_i); then Compliance-Soundness requires that if VerifyCompliance(pp, C, π, R_i) = 1, then Open(C) yields (v, aux) satisfying R_i, except with negligible probability. Reduce to DLOG or the soundness of underlying ZK system.

**Non-Frameability:** No coalition of parties (including the central bank and auditors) can produce a valid-looking compliance proof for a transaction that a specific honest user did not authorize. This protects users from being framed as having made non-compliant transactions. Reduce to unforgeability of the signature scheme.

#### 2C. Construction (Weeks 4-6)

Build CBC from standard primitives:

The core idea:
1. Use a Pedersen commitment `C = g^v · h^r` to commit to the transaction value
2. Extend to a multi-attribute commitment: `C = g_0^v · g_1^{id_s} · g_2^{id_r} · g_3^{cum} · h^r` where id_s is the sender identifier, id_r is receiver identifier, cum is cumulative amount
3. For each compliance rule R_i, define an NP relation: R_threshold is the relation `{(C; v,r) : C = g^v · h^r ∧ v ≤ T}`
4. Use Bulletproofs (for range proofs on value) or Sigma protocols (for algebraic relations) to prove compliance
5. For Rule-Privacy: use a "universal" proof that shows "there exists some R_i ∈ R such that the committed transaction satisfies R_i" without revealing which one. This can be done via a disjunctive Sigma protocol (OR-proof) or by committing to the rule index and proving it within the ZK circuit.

Implementation path:
- Week 4: Implement the multi-attribute Pedersen commitment
- Week 5: Implement Sigma protocols for each rule relation (prove v ≤ T using Bulletproofs; prove non-membership using accumulator or Merkle proof inside ZK)
- Week 6: Implement the disjunctive proof for Rule-Privacy (OR of Sigma protocols, or select the appropriate technique)

#### 2D. Implementation and Testing (Weeks 7-8)

- Unit tests for each algorithm
- Correctness: honest prover always verifies
- Soundness: malicious prover (violating rule) fails verification
- Rule-Privacy: given two proofs for different rules on the same transaction, a distinguisher cannot tell which is which (test empirically by checking proof distributions)
- Performance benchmarks: time for Commit, ProveCompliance, VerifyCompliance, and proof sizes for each rule type

**Deliverable:** Formal definition (LaTeX), implementation (Python with Rust backend for Bulletproofs), security proofs (drafts for Rule-Privacy and Compliance-Soundness), and benchmark results.

---

### PHASE 3: RCTD — Supporting Contribution (Months 5-7)

**Goal:** Define and implement Role-Constrained Threshold Decryption.

#### 3A. Formal Definition (Weeks 1-2)

**What makes RCTD different from standard threshold decryption:**
Standard threshold decryption: any t-of-n parties can decrypt. All parties are equivalent.
RCTD: parties have roles (R1 = central bank auditors, R2 = law enforcement, R3 = compliance officers). Decryption requires satisfying a policy like "2-of-3 from R1 AND 1-of-2 from R2." This maps directly to real-world CBDC governance where different authorities have different access rights.

**Syntax:**

```
RCTD.Setup(1^λ, P) → (pk, {sk_i}_{i∈[n]})
  Input: security parameter, access policy P (e.g., "2-of-3 from Role_A 
         AND 1-of-2 from Role_B")
  Output: public key pk, secret key shares sk_i for each participant i 
          with assigned role

RCTD.Encrypt(pk, m) → ct
  Input: public key, plaintext (transaction details for auditing)
  Output: ciphertext

RCTD.PartialDecrypt(sk_i, ct) → d_i
  Input: participant i's key share, ciphertext
  Output: partial decryption share

RCTD.Combine({d_i}_{i∈S}, ct, P) → m or ⊥
  Input: set of partial decryptions from subset S, ciphertext, policy P
  Output: plaintext if S satisfies P, failure otherwise
```

#### 3B. Construction (Weeks 3-5)

- Use EC-ElGamal as the base encryption (IND-CPA under DDH, homomorphic)
- For key sharing: use Shamir's secret sharing within each role group, then combine via a secret-sharing scheme that encodes the access policy (e.g., monotone span programs or nested threshold)
- This is more complex than standard Shamir because the threshold structure is heterogeneous, but the underlying math is well-established
- Add verifiable decryption: each partial decryptor proves (via a Schnorr-like proof) that their partial decryption is correct, preventing malicious partial decryptions

#### 3C. Security Proof (Week 6)

- Prove semantic security: if the policy is not satisfied, the ciphertext reveals nothing about the plaintext, under DDH
- Prove robustness: a malicious minority within any role group cannot prevent decryption or produce incorrect decryptions (follows from verifiable decryption)
- Reduce to DDH + DLOG

#### 3D. Integration with CBC (Weeks 7-8)

Show how CBC and RCTD compose:
1. User creates CBC commitment C and compliance proof π
2. User also encrypts the opening information (v, aux) under the RCTD public key: ct = RCTD.Encrypt(pk, (v, aux))
3. Central bank verifies π (compliance check in ZK — no one learns transaction details)
4. If an audit is triggered, authorized parties satisfying the RCTD policy can decrypt ct to learn (v, aux)
5. This is analogous to the verifiable encryption approach in Androulaki (2024), but with the role-constraint adding governance granularity

**Deliverable:** Formal definition (LaTeX), implementation, security proofs, integration with CBC demonstrated in code.

---

### PHASE 4: Security Proofs (Months 7-9)

**Goal:** Produce publication-quality game-based security proofs.

#### What CCS expects

Look at how Platypus structures its proofs:
- Define a Transaction Indistinguishability game (Definition 5.2 in the paper)
- Prove via hybrid argument: construct a sequence of games T_0^0, T_0^1, ..., T_0^9 where consecutive games differ in one step
- Each step reduces to the security of one primitive (PRF, commitment hiding, ZK zero-knowledge, encryption CPA-security)
- Conclude by triangle inequality

Your proofs should follow this structure:

#### 4A. Prove CBC Security (Weeks 1-4)

**Theorem 1 (Rule-Privacy):** "If the commitment scheme is hiding, and the ZK proof system is zero-knowledge, then CBC satisfies Rule-Privacy."

Proof sketch:
- Game 0: Real compliance proof for rule R_i
- Game 1: Replace the ZK proof with a simulated proof (indistinguishable by ZK zero-knowledge property)
- Game 2: Replace the commitment opening with a random value (indistinguishable by commitment hiding)
- Since Game 2 is independent of which rule R_i was used, Rule-Privacy follows

**Theorem 2 (Compliance-Soundness):** "If the commitment scheme is binding, and the ZK proof system is sound, then CBC satisfies Compliance-Soundness."

Proof sketch:
- Assume adversary produces (C, π) that verifies but the committed transaction violates R_i
- By soundness of the ZK proof, extract witness (v, aux, r) such that C opens to (v, aux) and R_i(v, aux) = 1
- By binding of commitment, C cannot open to a different (v', aux') where R_i(v', aux') = 0
- Contradiction

**Theorem 3 (Non-Frameability):** "If the signature scheme is EUF-CMA secure, then CBC satisfies Non-Frameability."

#### 4B. Prove RCTD Security (Weeks 3-4)

Reduce to DDH and DLOG. This is more standard and follows existing threshold ElGamal proofs with the addition of handling the role-based policy.

#### 4C. System-level Security (Weeks 5-8)

**Theorem 4 (Transaction Indistinguishability):** "The ZK-AML protocol provides transaction indistinguishability."

Follow Platypus's hybrid argument approach adapted to your architecture. This is the hardest proof and benefits the most from a cryptographer collaborator.

**Strong recommendation:** Find a cryptography professor or PhD student to collaborate with on this phase. Offer co-authorship. CCS reviewers are experts and will catch hand-wavy proofs instantly. The proofs for Platypus were written by researchers at ETH Zurich with deep ZK expertise. You don't need to be at that level, but you need someone who can verify your reductions.

**Deliverable:** Complete LaTeX writeup of all four theorems with full proofs.

---

### PHASE 5: System Implementation & Benchmarking (Months 9-12)

**Goal:** Build a working prototype and produce honest benchmarks.

#### 5A. System Architecture (Weeks 1-2)

Implement the full protocol:
- User wallet: creates transactions, generates CBC commitments, produces compliance proofs, encrypts audit data via RCTD
- Central bank / settlement engine: verifies ZK proofs, checks for double-spending (serial numbers), signs new state commitments
- Auditor nodes: participate in RCTD decryption when authorized

#### 5B. Deployment (Weeks 3-6)

Deploy across AWS regions:
- Minimum 3 regions (e.g., us-east-1, eu-west-1, ap-southeast-1)
- Run 3-4 nodes per region for a total of 9-12 nodes
- Use PBFT or Raft consensus among settlement engine nodes (if distributed)
- Measure: end-to-end transaction latency, TPS at settlement engine, proof generation time at client, proof verification time at bank, RCTD partial decryption time

#### 5C. Benchmarking (Weeks 5-8)

Produce a benchmarking table like this:

| Operation | Time | Notes |
|-----------|------|-------|
| CBC.Commit | X ms | Pedersen multi-attribute commitment |
| CBC.ProveCompliance (R_threshold) | X ms | Bulletproof range proof |
| CBC.ProveCompliance (R_cumulative) | X ms | Bulletproof + Sigma protocol |
| CBC.VerifyCompliance | X ms | |
| RCTD.Encrypt | X ms | EC-ElGamal |
| RCTD.PartialDecrypt | X ms | Per participant |
| RCTD.Combine (2-of-3 + 1-of-2) | X ms | |
| End-to-end transaction (single node) | X ms | |
| End-to-end transaction (12 nodes, 3 regions) | X ms | |
| System TPS (single node) | X TPS | |
| System TPS (12 nodes) | X TPS | |
| Proof size | X bytes | |

Compare honestly against:
- Platypus: 80K-150K TPS (centralized, Groth16)
- PayOff: ~5000 TPS central bank, 0.3s payment creation
- Androulaki (2024): <400ms payment authorization on smart card
- Androulaki (2023): 80K-150K+ TPS on Hyperledger Fabric

Your TPS will likely be lower. That is fine. Frame it as: "ZK-AML trades peak throughput for formal compliance guarantees and role-based audit governance that existing systems do not provide."

**Deliverable:** Deployed system, benchmark results, comparison table.

---

### PHASE 6: Paper Writing (Months 12-15)

**Goal:** Write a CCS-quality paper.

#### Paper structure (targeting 18 pages CCS format)

1. **Introduction (1.5 pages):** Motivation (CBDC needs privacy AND compliance), gap (no formal compliance primitive exists), contributions (CBC, RCTD, ZK-AML protocol, implementation).

2. **Related Work (2 pages):** Structured comparison against Platypus, PayOff, Androulaki (2024), Androulaki (2023), Allen et al. (2020). Use a comparison table showing which system has: formal compliance primitive (only you), role-based threshold audit (only you), offline payments (PayOff, Androulaki 2024), privacy-preserving regulation (Platypus, you), distributed settlement (Androulaki 2023, you).

3. **System Overview (1.5 pages):** Architecture diagram, participants, trust assumptions, threat model. Map clearly against the framework in Androulaki (2023) Section 2.

4. **Preliminaries (1 page):** Pedersen commitments, Bulletproofs, your chosen signature scheme, ElGamal encryption. State definitions precisely. Cite Androulaki (2024) Appendix B as a model for how to write this section.

5. **Compliance-Binding Commitments (3 pages):** Formal definition (syntax), security definitions (Rule-Privacy, Compliance-Soundness, Non-Frameability), construction, security proofs.

6. **Role-Constrained Threshold Decryption (2 pages):** Formal definition, construction from threshold ElGamal, security proof.

7. **The ZK-AML Protocol (2 pages):** Full protocol description showing how CBC + RCTD compose into the complete payment system. Transaction flow, compliance verification flow, audit flow.

8. **Security Analysis (2 pages):** System-level transaction indistinguishability proof. Reference the CBC and RCTD proofs from earlier sections.

9. **Implementation and Evaluation (2 pages):** Benchmark results, comparison table, deployment details, honest discussion of performance tradeoffs.

10. **Conclusion (0.5 pages)**

#### Writing tips for CCS

- Every definition must have formal syntax (algorithms with inputs/outputs)
- Every security property must have a game-based definition
- Every theorem must have a proof (at least a proof sketch in the main body; full proofs can go in appendix)
- The related work section must demonstrate deep familiarity with all cited papers — do not just list them, compare them on specific technical dimensions
- Be honest about limitations: if your TPS is lower, say so and explain why
- Use the same notation conventions as the papers you cite (this helps reviewers)

**Deliverable:** Complete paper in CCS format, ready for submission.

---

## Part 4 — Novelty Protection & Academic Integrity

### Your genuine novel contributions

1. **CBC (Compliance-Binding Commitment):** First formal cryptographic primitive for proving AML compliance in zero knowledge. No existing CBDC paper defines this as a standalone primitive.

2. **Rule-Privacy property:** The idea that the compliance proof hides not just the transaction but also which compliance rule is being satisfied. Platypus doesn't have this — in Platypus, the regulation mechanism is a fixed circuit visible to the verifier.

3. **RCTD with heterogeneous role-based access:** Going beyond standard threshold to encode real-world governance structures.

4. **Composition of CBC + RCTD:** Showing how these primitives compose into a complete CBDC protocol with formal end-to-end security.

### What is NOT novel (do not claim)

- Privacy-preserving CBDC transactions (Platypus, PayOff already do this)
- Threshold cryptography for distributed trust in CBDC (Androulaki 2023 already discusses this)
- Offline payments (PayOff and Androulaki 2024 already have this)
- Using ZK proofs for compliance enforcement (Platypus already does this as application logic)

### Academic integrity with AI assistance

Your situation is standard: you conceived the architecture, identified the compliance-as-primitive gap, and designed the CBC concept. Using AI tools for literature review, implementation guidance, and writing feedback is normal academic practice — it's no different from using a literature search engine, a code library, or a writing center. What matters is:

- The intellectual contribution (CBC, RCTD, the architecture) is yours
- The security proofs are correct (get human expert verification)
- The implementation works and benchmarks are honest
- The paper writing reflects your understanding (you should be able to defend every claim in a Q&A)

When asked about AI use in submission, be straightforward: "I used AI tools for literature review assistance and implementation debugging, similar to using search engines and code documentation." Most CCS authors use Copilot, ChatGPT, etc. for writing and coding assistance. The contribution is the idea and the rigor, not the typing.

---

## Part 5 — Complete Timeline Summary

| Phase | Duration | Months | Key Deliverable |
|-------|----------|--------|----------------|
| 0: Foundation & Positioning | 3 weeks | 1 | Design document, contribution statement, related work outline |
| 1: Crypto Foundation | 3 months | 1-3 | Pedersen commitments, Bulletproofs, signature scheme (all working) |
| 2: CBC Primitive | 3 months | 3-6 | Formal definition, implementation, draft security proofs |
| 3: RCTD Primitive | 2.5 months | 5-7 | Formal definition, implementation, integration with CBC |
| 4: Security Proofs | 2.5 months | 7-9 | All four theorems with complete proofs |
| 5: System & Benchmarks | 3 months | 9-12 | Deployed system, honest benchmark results |
| 6: Paper Writing | 3 months | 12-15 | Complete CCS-format paper |

Note: Phases 2-3 overlap intentionally (RCTD development starts while CBC implementation is being finalized). Phases 4-5 also overlap (security proofs can be written while the system is being deployed).

**Target: ACM CCS 2027 (submission ~April/May 2027)**

If you move exceptionally fast on Phases 0-3 (finishing by month 6), you could attempt CCS 2026 (submission ~April/May 2026), but this leaves only ~2 months from now for Phases 0-3, which is unrealistic unless you already have elliptic curve implementation experience.

---

## Part 6 — Immediate Next Steps (This Week)

1. **Read Platypus Sections 3-5 carefully.** Understand how they construct transactions, enforce regulation, and prove security. Your paper must demonstrate you understand this system deeply.

2. **Read Androulaki (2024) Appendix B.** This is a masterclass in how to write cryptographic preliminaries for a CBDC paper. Model your preliminaries section after it.

3. **Set up py_ecc and verify Pedersen commitments work.** Write a 50-line script that creates a Pedersen commitment, verifies it opens correctly, and demonstrates the homomorphic property. This is your "hello world" for the real crypto stack.

4. **Write your 1-page contribution statement.** Pin it above your desk. Every decision you make for the next 15 months should serve this statement.

5. **Start reaching out to cryptography professors.** You need a collaborator for Phase 4. Start the conversation early. Offer co-authorship. Look for researchers who work on threshold cryptography or ZK proofs for compliance — they'll find CBC interesting.
