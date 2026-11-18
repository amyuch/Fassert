# PLAN — Spec-Directed Proof Decomposition for RTL vs. Functional Specs

> **Historical SPC/decomposition research log (S1–S24).** This is frozen with
> `automation/decomp/` for provenance and is not current acceptance policy.
> Current PCD documentation is in
> [`../pcd/docs/README.md`](../pcd/docs/README.md).

Working thesis:

> A specification-directed proof-decomposition method derives contracts connecting
> iterative RTL micro-architectures to their intended operations, separates
> implementation invariants from semantic and temporal obligations, and composes
> proofs discharged at different abstraction levels.

Goal: beat CIll where it is known to fail, by *decomposing* the proof so each
obligation is stated and discharged in the logic where it is tractable — instead
of generating more helper assertions and asking IC3's bit-level engine to prove
all of them.

---

## 0. Empirical motivation (what we already established)

CIll = `ric3 cill` over bit-level IC3 (SAT). Our own experiments on the real
`picorv32_pcpi_mul` (non-ALTOPS) reproduce the paper's limitation:

- **State-manifold invariants are cheap and inductive** under IC3:
  `rs1 == a >> k`, `rs2 == b << k`, latched counter, and
  carry-save ≡ normal accumulator (`rd + rdx == h_acc`).
  BMC 16 s; inductiveness ~3 min; all manifold helpers Inductive.
- **Any obligation mentioning the product** (`a*b`) blows up CIll:
  - 64-bit closed form: BMC/induction > 19 min (killed).
  - 32-bit low-product closed form: BMC timeout > 40 min.
- Reference: CIll cannot prove non-ALTOPS M; paper confirms (bit-blasting 32-bit
  multiplication; serv long latency).

**Key conclusion.** The bottleneck is not the absence of invariants; it is that
the semantic/arithmetic closure must be expressed and discharged at a different
level of abstraction than bit-level IC3.

Additional new data point (this plan's first probe):

- Even a **word-level SMT-BV solver (z3)** fails on the raw multiply identity
  `(a>>1)*(b<<1) == a*b − (a&1)*b`, because z3's BV solver bit-blasts:
  `8-bit: 0.12 s`, `16-bit: > 60 s timeout`. So "use SMT instead of SAT" is
  NOT sufficient by itself.
- The identity is a **polynomial ring identity**. Purifying the mult subterms
  into fresh atoms and providing the ring identities reduces the proof to
  *linear arithmetic + congruence* (cheap). This is the real lever: the method
  must synthesize the algebraic *certificate*, not ask a solver to rediscover it.

---

## 1. Problem statement

RTL transition system `M = (S, I, T)`, target safety property `P`.
Conventional task: `M ⊨ P`. We must build a decomposition that makes this
tractable *without changing its meaning*.

For an iterative operation, partition state into:

- `B` — boundary state: captured operands, architectural state, operation status;
- `Z` — internal micro-architectural state: shift registers, accumulator,
  carry bits, iteration counter.

Contract: `C = (Pre, Inv, Post, Term)`.

- `Pre`: conditions under which the operation begins.
- `Inv`: relations that must hold during execution.
- `Post`: specified result on completion.
- `Term`: completion conditions.

Research problem: derive `C` automatically, split it into tractable obligations,
and prove the pieces compose **soundly**.

---

## 2. Obligation roles (roles, not disjoint assertion sets)

| Role | Content | Target discipline |
|------|---------|-------------------|
| **A. Micro-architectural consistency** | shift tracking, operand capture/stability, counter updates, FSM one-hot, carry-save ≡ normal | bit-level induction (IC3) |
| **B. Semantic correspondence** | internal computation implements the spec operation (partial-product accumulator ↔ operands; representation ↔ architectural result) | word-level algebraic certificate + light checker |
| **C. Temporal correspondence** | reaches completion at the right time; entry→exit summary; iteration bounds | transition reasoning / bounded-loop analysis / macro-step summary |

Dependencies between obligations must be discovered (e.g., a counter invariant
feeds a temporal summary; the summary feeds semantic correspondence at
completion).

---

## 3. Algorithm stages

1. **Extract operation model** — relevant RTL region, entry/exit conditions,
   internal state, update equations; align with the spec expression.
   Output: transition model + candidate recurrences.
2. **Synthesize micro-architectural invariants** (role A) from state updates and
   dependencies.
3. **Construct semantic + temporal contracts** (roles B, C) from spec + recurrence
   (candidate relations; *not* yet proven).
4. **Build and discharge obligations** — initialization + consecution for A;
   algebraic certificate for B; summary proof for C. Refine on failure.
5. **Compose and validate** against the original property; justify every
   abstraction assumption; report unresolved obligations.

Stage 4 is the algorithmic heart; stages 1–3 say where contracts come from;
stage 5 says why the method is sound.

---

## 4. Soundness conditions (must be explicit)

Manifold invariant `J(B,Z)`:

- Initialization: `I(B,Z) ⇒ J(B,Z)`
- Consecution: `J(B,Z) ∧ T((B,Z),(B',Z')) ⇒ J(B',Z')`

Semantic correspondence with `F(A,B)` the spec result, `R(Z,A,B)` the relation:

- `R` established at entry and preserved by the recurrence (NOT assumed).
- Completion: `Complete(Z) ∧ J(B,Z) ∧ R(Z,A,B) ⇒ Result(Z) = F(A,B)`.

Temporal summary `Q(B_in, B_out)`:

- `Pre(B_in) ∧ LegalExecution(B_in, Z_in, B_out, Z_out) ⇒ Q(B_in, B_out)`.

Composition requirement: the final theorem must follow from the discharged
obligations + original `T`. **It is not sound to replace the RTL computation
with its spec result and treat that as established.** The interface between
engine-disciplines must carry a *proof object* (discharged lemma), not merely an
assertion re-expressed in bit-level logic (our CIll experiment is the
counterexample to the naive version).

---

## 5. Hybrid SAT + SMT — the purification lever

Naive dispatch ("bit-level for A, SMT-BV for B") does not work: z3 bit-blasts.

Concrete cooperation designs:

1. **Word-level IC3 (IC3-IA over BV)** — SAT for boolean structure; BV-theory
   solver for inductiveness. Needs word-level predicates (i.e., needs B).
2. **UF abstraction + CEGAR** — `mul(a,b)` as UF; prove system under abstraction;
   refine with the multiplier contract. Keeps control bit-level, arithmetic
   word-level.
3. **Lemma exchange / delayed bit-blasting** — bit engine derives A; word engine
   derives B as a word predicate; word-level IC3 proves C + end-to-end without
   bit-blasting.
4. **CHC as the spine** — contracts = Horn predicates over mixed theory
   (BV + UF + counters); decomposition = predicate choice; soundness = CHC model.
5. **Purified algebraic certificate (PROPOSED CORE)** — treat mult subterms as
   fresh atoms; carry ring identities (`rs1 = 2·x + bit`, `x = rs1>>1`,
   `bit = rs1&1`) as the certificate; the residual obligation is
   *linear arithmetic + congruence*, discharged by a lightweight checker.
   The method synthesizes the certificate (polynomial normalization over a
   commutative ring); it does not ask a solver to prove products.

The novelty is not IC3-IA / CHC / datapath abstraction per se, but
**automatic contract/predicate discovery from the pair (RTL recurrence,
functional spec)** + **principled routing of obligations to theories**.

---

## 6. Generality crux — choosing the cut

Cut points must be inferred, not hand-picked:

- Backward-slice from spec outputs to find the engine and its live-in boundary `B`.
- Find the recurrence fixed point (where `Term` holds) = semantic cut.
- Manifold = state components that are pure functions of `B` + counter
  (IC3-friendly).
- Semantic residue = what remains (needs word-level/algebraic closure).

Criterion: cut where state stops being a function of the boundary and starts
encoding the spec's computation.

---

## 7. Novelty positioning & falsifiers

Novelty to defend:

- Spec-directed automatic decomposition for ISA specs ↔ micro-architecture.
- Explicit obligation taxonomy + engine routing.
- Certificate-based sound composition (not "make CIll inductive").
- Unified handling of both CIll failure modes (bit-blasted arithmetic; long
  latency) as "semantic lifting of iterative RTL".

Falsifiers:

- B not provable even with the algebraic certificate (carry-save structure
  defeats normalization).
- Cut not inferable (manifold/semantic entangled) → per-case manual.
- Composition not certifiable without re-consulting the multiplier at bit level.

---

## 8. TODO (prioritized sequence — validate the semantic interface before generality)

Completed groundwork (evidence in §0/§10):
- [x] G1. Characterization: CIll manifold invariants inductive; product blows up.
- [x] G2. Solver frontier: z3-BV exponential (8b 0.12 s → 12b timeout).
- [x] G3. Purified certificate: consecution 0.001 s, width-independent.
- [x] G4. Polynomial normal form proves the ring identity syntactically.
- [x] G5. Completion endpoint: `rd == a·b`, `rdx == 0` at finish (W=8,16).

Prioritized next steps:

1. [x] **S1. Complete the manual end-to-end proof (P3d). DONE.**
       `automation/decomp/s1_compose.py`: machine-checks `A ∧ B ∧ C ∧ T ⇒ P`
       (`pcpi_rd == a·b`) for W = 8/16/32/64. All obligations discharged:
       - A (manifold) enters as `acc' == acc + t`, discharged by IC3/CIll (§0).
       - B: ring identity (0.02 ms) + purified consecution (0.7–1.2 ms).
       - C: exact carry-save endpoint `rs1=0 ∧ rdx=0` (0.37/7.2/68 ms at 8/16/32).
       - compose: linear resolution (≈0.5 ms).
       **Lesson:** the composition check is not ceremonial — the first run was
       `sat` because the certificate omitted the zero law `M(0,rs2)=0`. The
       independent checker (S2) must validate the *whole* certificate language,
       not just the one ring identity.

2. [x] **S2. Independent certificate checker. DONE.**
       `automation/decomp/s2_check_cert.py` re-implements the algebra (imports
       nothing from S1): validates every ring identity by exact normal form in
       `Z/2^W` (W=8/32/64) AND exhaustively over all operands at W=3/4/5, then
       re-checks the composition. Negative test (drop the zero law) is correctly
       rejected. → `CERTIFICATE VALIDATED`.

3. [x] **S3. Automate certificate synthesis for the same multiplier. DONE.**
       `automation/decomp/s3_synth_cert.py` extracts the recurrence from
       `picorv32_pcpi_mul` and the operator from the non-ALTOPS spec branch,
       derives the substitution map (`rs1→2x+bit`, `rs2→s`, `rs1'→x`,
       `rs2'→2s`, `t→bit·s`), synthesizes the one-step identity and UF axioms,
       and matches them to the hand-derived certificate (D-mul, shift-mul, zero).
       → `AUTOMATED CERTIFICATE MATCHES HAND-DERIVED`.

4. [x] **S4. Second arithmetic structure (DIV/REM). DONE — profile differs.**
       `automation/decomp/s4_div_analysis.py`. Invariant:
       `dividend + N·quotient == D`, residue `N·msk == divisor` (msk one-hot).
       Findings:
       - The DIV semantic step is cheap **even for raw BV** (≤0.3 ms, W=8/12/16),
         unlike MUL, because `N·quotient` has a *fixed* multiplier `N`; MUL is
         hard because *both* operands shift → genuinely different products.
       - The residue is a one-hot/shift fact, also cheap.
       - **The arithmetic is not DIV's obstacle.** Required certificate-language
         extensions: (1) guarded identities / case split on `divisor<=dividend`;
         (2) one-hot + variable-shift abstraction; (3) sign / two's-complement
         negation lemmas; (4) corner cases (b=0, MININT/−1); (5) termination/
         remainder *ordering* (`dividend<N` at msk=0 ⇒ quotient=⌊D/N⌋).
       → The language must be **extensible by obligation kind**, not one
         polynomial normalizer.

5. [x] **S5. Cut-point selection + temporal summaries. DONE.**
       `automation/decomp/s5_temporal.py` (SERV bit-serial ADD, W=1):
       - extracted recurrence (carry/adder from `serv_alu`, shift from
         `serv_bufreg`, counter from `serv_state`);
       - live-variable cut-point analysis: internal `Z={partial,carry,k}`,
         boundary `B={a,b,done,result}`; `carry,k` eliminated at exit;
       - macro-step summary `done ⇒ result=(a+b) mod 2^32`, proven by SMT
         induction with **no multiplication**:
         `Inv(k): partial+carry·2^k=(a mod 2^k)+(b mod 2^k)`
         (base/k→k+1/exit all `unsat`, ≤2.2 ms).
       → `TEMPORAL SUMMARY CERTIFIED`; latency abstracted, not unrolled.

6. [x] **S6. Proof-graph composition + routing; generality evaluation. DONE.**
       `automation/decomp/s6_proofgraph.py`: a router maps a structural
       descriptor to obligation kinds/engines; each proof is a DAG with edges =
       dependencies; nodes are discharged by the appropriate engine
       (POLY/LINEAR/SMT-BV/MACRO-STEP; manifold nodes carry the CIll evidence).
       Results:
       - **MUL**: closed (manifold→IC3; ring+consecution→POLY/LINEAR; endpoint;
         compose).
       - **DIV**: arithmetic closed (raw step, one-hot shift, guarded branches);
         **open** on sign / corner-case / ordering — localized to three named,
         engine-appropriate obligations (not a monolithic proof).
       - **SERV-ADD**: closed via macro-step temporal summary.
       → The decomposition closes MUL and SERV-ADD and *localizes* DIV's residual
         difficulty. DIV's hard part is semantics/control, not arithmetic —
         exactly the opposite of MUL.

7. [x] **S7. MUL manifold re-proved on RTL/BTOR (L1). DONE.**
       `s7_kernel_mul.py`: ric3 IC3 proves the 4 manifold properties over the
       actual BTOR; artifact `artifact_mul_manifold.json`. (Yosys inline SAT is
       too weak — do not use. Bitwuzla unavailable offline.)

8. [~] **S8. Minimal MUL SPC composition. PARTIAL.**
       `s8_mul_spc.py`: O1/O2 (S7) + B (S1/S2) + O5 endpoint (op-local) + O4
       checked; **O6 observable link open** (deep; needs op-local temporal
       summary). Verdict: "MUL SPC composition checked (op-model) — O6 open".

Recommended order from here:
   1. [ ] **O6 as an operation-local temporal summary** (nested SPC, S5
          machinery), closing the MUL package end-to-end on the op-model.
   2. [ ] **DIV Δ (terminal ordering)** as a first-class checked obligation;
          answer (i) expressiveness, (ii) auxiliary invariant, (iii) checker
          validation, (iv) what remains open (sign / b=0 / MININT).
   3. [ ] **Freeze the SPC artifact schema + kernel acceptance rules** (model
          identity, boundary, dependencies, guard coverage, explicit TCB).
   4. [ ] **LLM planner** (instantiate SPC; propose certificates; no new rules,
          no unchecked assumptions).

## 9. Extracted invariant (real `picorv32_pcpi_mul`) — reference

Captured operands `a,b` (extended per `instr_rs1_signed`/`instr_rs2_signed`);
`k` iterations; `rs1 = a>>k`, `rs2 = b<<k`; `acc = rd + rdx`.

- Manifold (role A): `rs1 == a>>k`, `rs2 == b<<k`, latched counter,
  and `rd + rdx == h_acc` (carry-save ≡ normal accumulator).
- Semantic (role B): `rd + rdx + rs1·rs2 == a·b`, equivalently the step identity
  `p' = p − t` with `p = rs1·rs2`, `p' = (rs1>>1)·(rs2<<1)`, `t = (rs1&1)·rs2`.
- Completion (role C): at `Term`, `rs1 = 0`, so `acc = a·b`; MUL result is
  `acc`'s low 32 bits (need `rdx` handling to expose `pcpi_rd = rd`).

## 10. Prototype results (validated)

Environment: only z3 available (`z3 5.1.0`); no cvc5/boolector/bitwuzla/sympy.

**P2 — bit-blasting frontier.** Raw z3-BV identity
`(a>>1)(b<<1) = a·b − (a&1)·b`:
8-bit 0.12 s, 10-bit 4.5 s, 12-bit timeout (>30 s), 14/16-bit timeout.
Exponential ⇒ SMT-BV does **not** solve the closure; it bit-blasts like IC3.

**P3b — purified algebraic certificate.** Treat mult subterms as atoms `M(·,·)`
and supply ring identities as the certificate:
`M(rs1,rs2) = 2·M(rs1>>1,rs2) + M(rs1&1,rs2)`, `M(rs1&1,rs2) = t`,
`M((rs1>>1),(rs2<<1)) = 2·M(rs1>>1,rs2)`.
Residual obligation is **linear/congruence**:
- 8-bit: `unsat` in **0.001 s**
- 32-bit: `unsat` in **0.001 s**
- 64-bit: `unsat` in **0.001 s**  ← width-independent (contrast raw BV).
Control (same goal, real BV multiply): 8-bit 0.38 s, 12/16-bit timeout.

**Certificate synthesis is syntactic.** A tiny commutative-polynomial
normal-form engine (mod 2^W) certifies `p − p' − t ≡ 0` exactly and instantly
(generators `x=rs1>>1`, `bit=rs1&1`, `s=rs2`; substitution `rs1 := 2x+bit`,
`rs2<<1 := 2s`). No solver search; the certificate is derived, not rediscovered.

Implication: **B can be discharged at word level cheaply — but only via a
purified algebraic certificate, not by handing `*` to a bit-blasting SMT solver.**

**P3c — completion / endpoint.** Simulating the exact carry-save datapath
(`STEPS_AT_ONCE=1`, `CARRY_CHAIN=4`, `N=W` iterations) over 5000 random operand
pairs at W=8 and W=16: at finish **`rd == a·b`**, **`rdx == 0`**, and
`(rd+rdx) == a·b` — always. So `pcpi_rd = rd` is exact; no `rd+rdx` correction
needed. The endpoint obligation is therefore `Term ⇒ (rs1=0 ∧ rdx=0)`, after
which `R` gives `rd = a·b` by linear resolution.

## 11. Trust boundary / soundness notes (leveled, important)

Do **not** collapse the pipeline into one "sound" verdict. Report levels:

| Level | What is established |
|---|---|
| Manifold properties re-proved | each listed property holds on reset-reachable states of the BTOR model (S7) |
| L1 re-check | an independent engine re-establishes the invariant facts (ric3 IC3) |
| SPC composition checked | kernel checks accepted facts + certificates imply the postcondition (S8, op-model) |
| RTL-to-model link checked | a miter/equivalence argument relates source RTL and model (still TCB) |

Notes:

- `acc' == acc + t` is **not valid for arbitrary state** (z3 `sat` at W=8/16/32;
  the 4-bit-group adder truncates a top carry). It holds on the **reachable
  manifold**, which S7 now re-proves on the BTOR (`h_carrysave`, `h_shift_*`).
- A SHA-256 BTOR hash establishes **artifact identity, not semantic
  equivalence** to the source RTL. The front-end remains an explicit TCB
  assumption (O0), to be replaced by a checked miter/equivalence later.
- Remaining connections that are *separate obligations or TCB assumptions*, not
  folded into one:
  1. arithmetic certificate applied to the same recurrence/bit widths as the model;
  2. endpoint argument matches the modeled state/boundary (op-local; S1);
  3. kernel checks dependencies/implications (S8);
  4. BTOR faithfully represents source RTL (TCB, O0).
- S1's endpoint is a **symbolic unrolling proof** (exhaustive for the fixed
  width), not sampling. The 5,000-pair run was the earlier exploratory `sim.py`.
- As a global BTOR property, the endpoint/retire link is **deep** (BMC >28
  cycles, IC3 unknown): it must be an operation-local temporal summary
  (nested SPC), not a monolithic CPU property. This is a finding, not a defect.
- Status wording: "manifold independently re-proved on BTOR" (S7) ≠ "MUL fully
  certified". "MUL SPC composition checked against BTOR (op-model)" (S8) is the
  justified phrase; O6 remains open.

## 12. DRAFT — Stratified Progress Contract (SPC) + kernel status

### 12.1 Contract

An operation contract is `C = (A, E, X, T_G, Φ, ρ, Δ, Post, P)` over an extended
(RTL + functional ghost) state, with

```
Φ = M ∧ C_rec ∧ Σ          (stratified; each stratum has its own backend/certificate)
```

`A` = entry assumptions (discharged by the enclosing system invariant `G`);
`E`/`X` = operation entry/exit; `T_G` = RTL transition + ghost updates;
`ρ` = well-founded ranking; `Δ` = terminal side-facts; `Post`/`P` = operation
postcondition / observable property.

### 12.2 Obligations (the single rule; O5/O6 may be nested SPC instances)

```
O0 rtl_link     : T_G faithfully represents the RTL (front-end trust or checked
                  miter); ghosts are functional and do not affect observables
O1 entry        : A(s) ∧ E(s)                 ⇒ Φ(s)
O2 preservation : Φ(s) ∧ T_g(s,s') ∧ ¬X(s)    ⇒ Φ(s')   for every guard class g,
                  guard coverage:  T_enabled(s,s') ⇒ ⋁_g T_g(s,s')
                  (classes need not be disjoint; their union must cover every
                   enabled transition relevant to the proof, incl. stalls and
                   exceptional branches)
O3 progress     : Φ(s) ∧ ¬X(s) ∧ T_g(s,s') ⇒ (ρ(s'),ρ(s)) ∈ ≺  (progress
                  transitions; phase-aware lexicographic ρ; checked fairness F
                  only for environment waits)
O4 finalization : Φ(s) ∧ X(s) ∧ Δ(s)          ⇒ Post(s)
O5 terminal     : Φ(s) ∧ X(s)                 ⇒ Δ(s)     (Δ may be a nested SPC lemma)
O6 observable   : Post @ X (via checked latency/boundary relation) ⇒ P @ observation
O7 non-interf.  : operation execution does not interleave with a conflicting one
```

Prediction: MUL = `M∧C` (trivial Δ, retire-path O6); DIV = `M∧C` with nontrivial
`Δ` (ordering) + sign/corner guarded/terminal lemmas; SERV = `M∧Σ` with
phase-aware ranking. The residual non-uniformity is *which stratum/lemma is
hard*, not a different rule.

### 12.3 Claim level (decided)

- **Default: partial functional correctness** for all three cases
  (O1,O2,O4,O5,O6; no O3).
- **Separate progress theorems** where the core is self-timed (MUL, DIV);
  serv-style environment waits require an explicit, checked fairness premise.

### 12.4 Kernel / RTL-link (decided)

- Use **RTL/BTOR directly**; the Yosys/Slang front-end is in the TCB.
- Kernel is a small trusted checker with backend-neutral proof artifacts;
  per-backend acceptance rules; L1 (independent re-check) first, design for
  L2 (proof-log checking) later.

### 12.5 Kernel prototype status (S7 — MUL manifold certified)

Setup: kernel sandbox `.../t3/kernel_mul`; reset-sequence harness
`kernel_top.sv`; front-end Yosys/Slang → BTOR (`--allow-genblk-reference`,
front-end in TCB); SAT backend **ric3** (not Yosys inline SAT).

- Yosys `sat -tempinduct` is too weak here: it diverges (k=1…13) on the manifold
  package. *Do not use it as the SAT backend.*
- **ric3 IC3 proves each manifold property independently over the actual BTOR**
  (safety from reset, no trust in CIll's helper selection):

  | property | engine | time |
  |---|---|---|
  | `h_carrysave` | ric3-ic3 | 7.6 s |
  | `h_counter` | ric3-ic3 | 1.0 s |
  | `h_shift_rs1` | ric3-ic3 | 40.9 s |
  | `h_shift_rs2` | ric3-ic3 | 93.3 s |

  `ric3 check ... kind` also proves `h_shift_rs2` (depth 64).
- Artifact: `automation/decomp/s7_kernel_mul.py` →
  `artifact_mul_manifold.json` with BTOR sha256, per-property status/time, engine,
  and TCB. Verdict: **MANIFOLD CERTIFIED (ric3 IC3, RTL/BTOR)**.
- Individual safety proofs establish each fact on all reachable states; this is
  the L1 re-check of O1/O2. (The earlier "property ≠ invariant" concern was an
  artifact of Yosys's weak engine; ric3's IC3 finds its own strengthening.)
- **Bitwuzla is unavailable offline** (network unreachable; not installed), so
  `wl-kind`/`wl-bmc` cannot run. SMT remains z3. If Bitwuzla becomes available,
  retry the DIΣ/V word-level experiments with `wl-kind`.
- Next kernel steps: (i) consume the artifact in the SPC composition (O4/O6),
  (ii) DIV Δ (ordering) as the next language test, (iii) LLM instantiation
  protocol.

### 12.6 S8 — MUL proof package status (op-model)

`automation/decomp/s8_mul_spc.py` assembles the package and records per-node
status; nothing is upgraded beyond what was checked.

| node | status | evidence |
|---|---|---|
| O0 rtl_link | TCB | front-end; BTOR hash `e0693b18…` (identity, not equivalence) |
| O1/O2 manifold | proved | S7: ric3 IC3 over BTOR (4 props, 1.0–93.3 s) |
| B ring | proved | `Z/2^W` poly normal form (0.04 ms) |
| B consecution | proved | purified-linear (1.35 ms, assumes manifold) |
| O5 Δ endpoint | proved (op-local) | symbolic unroll of carry-save loop (64 ms) |
| O4 finalization | proved | linear (0.57 ms) |
| O6 observable link | **open** | deep: BMC >28 cycles, IC3 unknown |

Verdict artifact: `artifact_mul_spc.json` =
**"MUL SPC composition checked (op-model) — O6 open"**.

O6 finding: the writeback→RVFI link is shallow *within* the window but deep in
reach of the operation (~32+ cycles). It must be an **operation-local temporal
summary** (nested SPC), exactly the S5 machinery, not a global CPU safety query.

### 12.7 S9 — O6 nested temporal summary (RTL-derived)

`automation/decomp/s9_mul_o6.py`. The writeback→retire correspondence is built
from the **actual RTL 1-step/combinational transitions**, not a ghost of the
expected result:

| link | RTL fact | status |
|---|---|---|
| L1 ready capture | `reg_out <= pcpi_int_rd` at PCPI ready | **proved** (0.75 s) |
| L2 writeback mux | `cpuregs_wrdata == reg_out` (fetch, store, !branch, !stalu) | **proved** (0.62 s) |
| L3 RVFI latch | `rvfi_rd_wdata == latched_rd ? cpuregs_wrdata : 0` after MUL write | **proved** (0.79 s) |
| L4 rd address | `latched_rd == dbg_insn_opcode[11:7]` (MUL write) | **open** (BMC clean; IC3 unknown) |

Composition (z3): `Post ∧ L1–L3 ∧ L4 ⇒ rvfi_rd_wdata == spec_rd_wdata`
= **unsat** (checked).

Verdict (`artifact_mul_o6.json`):
**"O6 data correspondence proved from RTL transition; rd-address OPEN"**.

Important: the earlier "deep" O6 was a *ghost shadow* over a long window
(BMC >28, IC3 unknown). The correct formulation — the RTL's own 1-step
transition equations — proves in **<1 s each**. This is the concrete payoff of
"derive the summary from T, not the expected result."

L4 is the checker's address-match obligation and is factored out explicitly
rather than assumed silently.

### 12.8 S10 — MUL-to-RVFI integration (M1–M5)

`automation/decomp/s10_mul_rvfi.py`; artifact `artifact_mul_rvfi.json`.
Sources inspected: `insn_mul.v` (spec), `rvfi_insn_check.sv` (guards),
`picorv32.sv` (`rvfi_pc_wdata = dbg_insn_addr`; `rvfi_rs{1,2}_rdata` latches).

M1 guards (exact):
`!reset && check && spec_valid ∧ pc_valid ∧ ¬mem_fault ∧ ¬spec_trap`;
`spec_rd_wdata = insn_rd ? rvfi_rs1_rdata*rvfi_rs2_rdata : 0`;
`spec_pc_wdata = rvfi_pc_rdata+4`; `spec_trap=!misa_ok` (=0 here, no CSR_MISA).

| step | result |
|---|---|
| M2 arithmetic→spec | symbolic composition **unsat (checked)**; operand links M2 BMC-clean, unproved |
| M3 data observation | O6 L1–L3 **proved**; L4 **open**; symbolic composition **checked** |
| M4 PC correspondence | symbolic composition **checked**; `h_pc_corr` BMC-clean, unproved |
| M5 final assertions | see outcomes |

Outcomes (O0 front-end TCB explicit for both):
- **`o_rd_wdata_match`: OPEN** (needs L4 rd-address + M2 operand links)
- **`o_pc_wdata_match`: OPEN** (symbolic composition checked; `h_pc_corr` unproved)

Key point: L4, M2 operand links, and `h_pc_corr` are **true but deep** (BMC clean
to depth ~21; reaching a MUL retire needs ~32+ cycles). Like O6, they must be
operation-local temporal summaries (nested SPC), not global IC3 queries. The
symbolic integration itself is complete and checked; only the RTL links remain.

#### S10b–d — bounded operation-local link experiment (ric3)

Rather than deep retire queries, use operation-boundary relations + stability
(consecutive in-operation cycles), then compose.

| link | formulation | result |
|---|---|---|
| M2 operand entry | `reg_op1==dbg_rs1val ∧ reg_op2==dbg_rs2val` at PCPI waiting | **proved (UNSAT)** |
| PC boundary | `next_pc == dbg_insn_addr+4` at MUL entry | **proved (UNSAT)** |
| PC stability | `next_pc`, `dbg_insn_addr` unchanged across consecutive op cycles | **proved (UNSAT)** |
| L4 destination stability | `latched_rd` unchanged across consecutive op cycles | **proved (UNSAT)** |
| L4 destination identity | `latched_rd == dbg_insn_opcode[11:7]` at ld_rs1 / waiting / post-decode | **FALSE (CEX depth 2)** |

Interpretation:

- **`o_pc_wdata_match`**: PC boundary + stability are proved; composing with the
  RTL latch equations (`rvfi_pc_rdata <= dbg_insn_addr`,
  `rvfi_pc_wdata = dbg_insn_addr`, `dbg_insn_addr <= next_pc` at launch) gives
  `rvfi_pc_wdata == rvfi_pc_rdata+4 = spec_pc_wdata`. **CLOSED at integration
  level** (O0 front-end TCB explicit).
- **M2 operand link**: the internal operands equal the RVFI operands at the
  operation boundary — **proved**. This completes the arithmetic↔instruction
  operand correspondence.
- **L4 destination identity**: the tried sampling boundaries are wrong; the
  relation needs an *instruction-identity ghost captured at decode*
  (`decoded_rd`/`dbg_insn_opcode` at `decoder_trigger`), then stability to the
  writeback. Per the bounded stopping rule, we **stop and revisit L4** rather
  than assume it.
- **`o_rd_wdata_match`**: **OPEN** (needs L4). Data chain L1–L3 and M2 operands
  are proved; only destination identity remains.

Milestones (kept separate): operation correctness = yes; architectural PC
correctness = **yes (integration, O0 TCB)**; architectural data correctness =
**open on L4**.

#### S11 — bounded L4 decode-identity ghost (stopped per rule)

Ghost `h_insn_rd` captures `decoded_rd` at `decoder_trigger` (metadata, not the
writeback value; non-circular).

| obligation | result |
|---|---|
| E decode capture = decoded dest | defined by ghost update (extended T) |
| `latched_rd == h_insn_rd` during op (identity/preservation) | **proved (UNSAT)** |
| `dbg_insn_opcode[11:7]` stable across op cycles | **proved (UNSAT)** |
| `dbg_insn_opcode[11:7] == h_insn_rd` after decode | **FALSE (CEX depth 2)** |

The depth-2 CEX is a first-decode transition (symbolic first instruction after
reset): the opcode association does not hold there. Per the strict stopping
rule, we do **not** exclude the counterexample-producing transition or weaken
the contract. **L4 remains OPEN**; destination identity/preservation is proved,
the opcode↔ghost link is not.

Decision: proceed to **DIV Δ** with L4 carried as a named open limitation.

#### S11b — L4 step-2 (decode→latched_rd assignment), stopped

Focused one-step attempt at the RTL assignment, not the opcode-stability sample:

| relation | result |
|---|---|
| `latched_rd == $past(decoded_rd)` after `decoder_trigger` | **FALSE (SAT)** |
| `dbg_insn_opcode[11:7] == decoded_rd` at `decoder_trigger` | **FALSE (SAT)** |

Reason (from RTL): `decoded_rd` is a **registered decode-phase value** assigned
from `mem_rdata_latched[11:7]` (plus compressed/illegal remaps), while
`dbg_insn_opcode` is a different pipeline signal. The decode↔destination
association therefore requires modeling the fetch/decode pipeline stages, not a
one-step relation. Per the strict rule, **L4 remains OPEN**; the earlier
destination-identity/stability facts (`latched_rd==h_insn_rd`,
`latched_rd` stable) stand, but do not close the opcode link.
MUL status unchanged: `o_pc` closed; `o_rd` open on L4.

#### S12 — DIV Δ preliminary probe (terminal ordering)

Divider step (unsigned): `if (divisor <= dividend) dividend -= divisor;`
`divisor >>= 1; quotient_msk >>= 1;` with `divisor = N·msk` (one-hot, S4) and
`msk: 2^31 → 0`.

Probe results (`z3`, integer model):

| candidate | result |
|---|---|
| `dividend < 2·divisor` preserved across steps | **no** (cex `divisor=1,dividend=0` → next divisor 0) |
| `dividend <= 2·divisor` preserved | **no** (cex `divisor=1,dividend=2`) |
| last step `divisor=N`: `dividend' < N` | **yes** (`unsat`) |

Interpretation: the ordering is **not a global loop invariant** of that shape;
it is a **terminal-step fact**. At the terminal transition `msk=1` (so
`divisor=N`), the conditional guarantees `dividend' < N`, and the next cycle is
`Term` (`msk=0`). So Δ is exactly the O5 category:

```
Term ∧ (prev msk=1, divisor=N) ⇒ dividend < N
```

discharged from the manifold `divisor = N·msk` (S4) plus the single terminal
transition — **not** from the polynomial recurrence C. This is a promising
framework-expressiveness result; the next step is to make it a checked,
first-class terminal obligation and connect it to `quotient = floor(D/N)`.

#### S13 — DIV Δ checked (first-class terminal obligation) + quotient theorem

`automation/decomp/s13_div_delta.py`:

| obligation | formulation | result |
|---|---|---|
| Δ1 manifold | `N·msk == divisor` (one-hot; reused S4) | **PASS** (0.76 ms) |
| Δ2 invariant | `dividend < 2·divisor` preserved while `msk>1` (divisor even) | **PASS** (1.17 ms) |
| Δ2 terminal step | at `divisor=N`: `dividend' < N` | **PASS** (1.61 ms) |
| Δ3 alignment | `Term ∧ prev(msk=1) ⇒ dividend<N` | **PASS** (1.24 ms) |
| **Δ** | terminal ordering | **CLOSED (conditional on manifold)** |
| Quotient theorem | `M==d+N*q ∧ 0≤d<N ∧ N>0 ⇒ q=M/N ∧ d=M%N` | **PASS** (25.6 ms) |

Key: the parity/one-hot from Δ1 (`msk>1 ⇒ divisor` even) is exactly what makes
the terminal step valid. Δ is a terminal-step fact, not a global invariant, and
was verified against the exact final-step guard (the `divisor<=dividend`
conditional), not substituted by an invariant.

Separate (NOT claimed): signed division (`outsign`, two's complement) **OPEN**;
division by zero (`b=0`) **OPEN**; `MININT/-1` **OPEN**.

MUL status unchanged: `o_pc_wdata_match` closed at integration level;
`o_rd_wdata_match` open on L4.

### 12.9 S11 — operation-local SPC for the three integration links (NEGATIVE)

Attempted the classified nested summaries for L4 / M2 / PC:
- capture metadata at `mul_start` (rd, operands, pc);
- preserve through the operation (`h_op_*_hold`);
- relate at retirement (`h_op_*_exit`);
- 12 facts total.

Result: **all 12 CEX (SAT)**, first at **depth 2**; tightening the capture/hold
to `instr_trap ∧ h_is_mul` did **not** fix `h_op_rd_hold`.

Interpretation (per the bounded-stopping rule): the chosen entry boundary /
instruction-identity association is **insufficient**; this ghost formulation
does not establish that the captured metadata belongs to the retired MUL. It
must be **re-contracted**, e.g.:
- capture at the actual decode/latch point (`latched_rd`/`rvfi_insn`) rather
  than at `mul_start`;
- state an explicit instruction-identity invariant tying `rvfi_insn`,
  `latched_rd`, and the active operation;
- handle reset/spurious-start and non-MUL PCPI paths explicitly.

What still stands (unchanged): S1/S2 arithmetic, S5 temporal summary, S7
manifold re-proof, S8 op-model composition, and S9 **O6 data chain L1–L3
(proved)**. The three RTL integration links (L4, M2 operands, `h_pc_corr`)
remain **OPEN**, now with a concrete negative result showing the naive nested
summary is unsound. No claim of closing MUL is made.

## 13. Experiment log

- 2026-10-16 — CIll behavior on picorv32 real mul (see §0).
- 2026-10-16 — z3-BV identity probe: bit-blasting frontier ≈ 10–12 bit.
- 2026-10-16 — purified consecution: 0.001 s @ 8/32/64 bit (width-independent).
- 2026-10-16 — polynomial normal-form certificate: `p − p' − t ≡ 0` proved syntactically.
- 2026-10-16 — **S1 end-to-end composition certified** (`automation/decomp/s1_compose.py`):
  ring identity 0.02 ms; purified consecution 0.7–1.2 ms; endpoint 0.37/7.2/68 ms
  (W=8/16/32); final resolution ~0.5 ms. First attempt failed (`sat`) due to a
  missing zero law in the certificate — confirms the need for S2 (independent
  checker of the full certificate language).
- 2026-10-16 — **S2 independent checker** (`s2_check_cert.py`): exact `Z/2^W`
  normal form + exhaustive W=3/4/5; negative test caught. `CERTIFICATE VALIDATED`.
- 2026-10-16 — **S3 automated synthesis** (`s3_synth_cert.py`): recurrence + spec
  extraction → substitution map → UF axioms; matches hand-derived exactly.
- 2026-10-16 — **S4 DIV/REM** (`s4_div_analysis.py`): DIV arithmetic cheap even
  raw (fixed multiplier); obstacles are guarded conditions, sign/corner cases,
  and remainder *ordering*. Certificate language must be extensible by kind.
- 2026-10-16 — **S5 temporal summary** (`s5_temporal.py`): SERV bit-serial ADD
  macro-step `done ⇒ result=a+b mod 2^32` proven by induction (no multiply,
  ≤2.2 ms); cut-point analysis eliminates carry/counter at the boundary.
- 2026-10-16 — **S6 proof graph + router** (`s6_proofgraph.py`): MUL closed,
  SERV-ADD closed, DIV arithmetic closed with sign/corner/ordering localized as
  open obligations routed to case-splitting SMT.

### 12.10 S14 — DIV signed / exceptional cases (kept distinct)

`automation/decomp/s14_div_signed.py`. RISC-V non-ALTOPS spec semantics vs the
RTL magnitude-division + sign correction.

| case | check | result |
|---|---|---|
| b=0 DIV | RTL all-ones == spec | **PASS** (0.25 ms) |
| b=0 REM | sign-corrected \|a\| == a | **PASS** (45.9 ms) |
| MININT/-1 DIV | outsign=0, q=MININT | **PASS** (0.33 ms) |
| MININT/-1 REM | r=0, outsign=1 → 0 | **PASS** (0.29 ms) |
| signed DIV sign-adjust | BV, W=8/12 | **PASS** (0.2 s / 6.5 s) |
| signed REM sign-adjust | BV, W=8/12 | **PASS** (0.4 s / 25.8 s) |
| signed DIV/REM | BV, W≥16 | **OPEN / solver-limited** (division bit-blast frontier) |

Status distinction preserved:
- **Exceptional cases b=0 and MININT/-1: checked** (direct, distinct).
- **Signed sign adjustment: proved at W=8/12**; W≥16 hits z3's bit-blasted
  division frontier (same solver limitation as the paper's bit-level point, not
  a logical gap in the decomposition).
- **Full 32-bit signed semantics** is reduced to: unsigned theorem (S13) +
  sign case analysis (`sign(a) xor sign(b)` for quotient, `sign(a)` for
  remainder) + the two exceptional-case lemmas. The W=32 BV check is
  solver-limited; the structural reduction is the checked contribution.
- Not yet claimed: composition of all signed/exceptional branches into the
  original instruction-level `spec_rd_wdata` with full guards.

### 12.11 S15 — signed DIV/REM via the verified unsigned interface

`automation/decomp/s15_div_signed_interface.py`.

Reformulation: consume the S13 unsigned result as an interface

```
A=|a|, B=|b|, B>0, A = q0*B + r0, 0 <= r0 < B
Q = (sign(a) xor sign(b)) ? -q0 : q0
R = sign(a) ? -r0 : r0
```

with **no division/remainder operators in the query** (only the interface
product and sign cases).

| obligation | result |
|---|---|
| signed quotient/remainder characterization | **PASS** 11.9 ms (width-independent) |
| quotient sign branches (4 cases) | **PASS** (0.6–9 ms each) |
| remainder sign branches (2 cases) | **PASS** (~5 ms each) |
| guard coverage (exceptional ∪ normal) | **PASS** 0.74 ms |
| exceptional b=0 / MININT,-1 | reused S14 (checked) |
| signed → instruction composition | **OPEN** (branch selection + observation) |

**Diagnosis confirmed (hypothesis A):** the W≥16 blockage was the bit-blasted
division operator, not the sign logic. Controlled baseline on the old query:
W=16 DIV eventually closed at **65.4 s**; REM was **unknown at 180 s**.
The interface formulation closes the same sign reasoning in **~12 ms**, and is
width-independent (Int).

Status distinction preserved: the unsigned interface is the S13 result; the
signed sign correction is proved *against that interface*; the full
signed→instruction claim (branch selection, result register, architectural
observation) remains open.

### 12.12 S16 — DIV branch selection (checked)

`automation/decomp/s16_div_branch_selection.py`.

Semantic point: `picorv32_pcpi_div` has **no explicit b=0 / MININT,-1 branch**.
It always runs the magnitude loop; exceptional results are consequences of
magnitude values (S14) plus the sign/source selection checked here.

| dispatch obligation | result |
|---|---|
| decode: div/rem funct3 → exactly one mode (100/101/110/111) | **PASS** 1.7 ms |
| finish source: quotient for DIV(U) xor dividend for REM(U) | **PASS** 0.6 ms |
| sign convention: div parity(&\|b\|), rem sign(a), unsigned 0 | **PASS** 1.1 ms |
| exceptional dispatch: b=0 / MININT,-1 sign selection | **PASS** 1.4 ms |

Branch → arithmetic mapping (each branch's arithmetic is already checked):
- DIV normal → S15 signed quotient (via unsigned interface)
- DIVU normal → S13 unsigned quotient
- REM normal → S15 signed remainder
- REMU normal → S13 unsigned remainder
- b=0 / MININT,-1 → S14 exceptional lemmas + this sign mux

**BRANCH SELECTION: CHECKED.**
Next: **architectural observation** (result → `spec_rd_wdata`) — a pipeline-level
link of the same class as MUL L4; keep open until modeled.

### 12.13 S17 — DIV architectural observation (checked data chain)

`automation/decomp/s17_div_observation.py`; artifact
`artifact_div_observation.json`. Real (non-ALTOPS) `picorv32_pcpi_div`.

| RTL link | result (ric3 IC3) |
|---|---|
| mux: `pcpi_div_ready ∧ ¬pcpi_mul_ready ⇒ pcpi_int_rd==pcpi_div_rd` | **proved** 1.8 s |
| L1 ready capture: `reg_out==pcpi_int_rd` | **proved** 1.5 s |
| L2 writeback mux: `cpuregs_wrdata==reg_out` | **proved** 1.6 s |
| L3 RVFI latch: `rvfi_rd_wdata==latched_rd ? cpuregs_wrdata : 0` | **proved** 1.9 s |

Important guard: with `ENABLE_FAST_MUL(1)`, the MUL source has priority in
`pcpi_int_rd`, so the mux link needs `¬pcpi_mul_ready` (a real RTL fact, caught
by the first attempt returning unknown/false).

Composition (z3): arithmetic interface (S13–S16) + mux + L1–L3 + L4
⇒ `rvfi_rd_wdata == spec_rd_wdata` = **unsat (checked)**.

Status:
- **DIV observation data chain: PROVED on the RTL.**
- **Destination identity L4: OPEN** (same class as MUL L4; pipeline decode link).
- Arithmetic interface: S13–S16 (unsigned/signed/exceptional/branch).
- **DIV architectural data: OPEN on L4** (data path is proved; the remaining gap
  is the shared destination-identity pipeline link).

This is now the *same single open link* for both MUL and DIV: the decode→rail
destination identity. It is the natural next target for a pipeline-level
correspondence model.

### 12.14 S18 — pipeline destination-identity model (partial)

Starting point correction: `latched_rd <= decoded_rd` is in the **`cpu_state_fetch`**
block (not `decoder_trigger`), and `decoded_rd <= mem_rdata_latched[11:7]` at
`mem_do_rinst && mem_done`.

Proved stage relations (ric3 IC3 over the real MUL BTOR):

| stage relation | result |
|---|---|
| P1 decode: 32-bit instruction → `decoded_rd == mem_rdata_latched[11:7]` | **proved (UNSAT)** |
| P2 fetch latch: prev state fetch → `latched_rd == $past(decoded_rd)` | **proved (UNSAT)** |
| P3 operation: at ld_rs1/instr_trap/MUL → `dbg_insn_rd == latched_rd` | **proved (UNSAT)** |
| P4 operation: `dbg_insn_opcode[11:7] == dbg_insn_rd` | **FALSE (CEX depth 2)** |

Interpretation: the destination latch (P2) and the pipeline RD (P3) are solid.
The missing piece is relating the *instruction word* `dbg_insn_opcode` to
`dbg_insn_rd` at the retirement stage. `dbg_insn_opcode` is a combinational mux
over three debug stages:

- default      `q_insn_opcode`   (`q_*` = previous cycle's `dbg_*`)
- pseudo-trig  `cached_insn_opcode` (`cached_*` set at `decoder_trigger_q`)
- else (dbg_next) `next_insn_opcode`/`decoded_*`

So P4 must be stated per stage, not at ld_rs1. The q/cached paths preserve the
instruction→rd relation; the `next` path is the one that can differ by a cycle.

Next sub-obligations (to discuss):
  (a) `cached_insn_opcode[11:7] == cached_insn_rd` at the cache update.
  (b) `q_insn_opcode[11:7] == q_insn_rd` (q-stage preservation).
  (c) at the RVFI writeback, the selected stage gives
      `dbg_insn_opcode[11:7] == latched_rd` (using P2/P3 + (a)/(b)).
Then L4 = `rvfi_rd_addr == rvfi_insn[11:7]` follows from the RVFI latch.

#### S19 — per-stage (a)/(b) results

RTL timing: `next_insn_opcode`/`mem_rdata_q <= mem_rdata_latched` at `mem_xfer`;
`decoded_rd <= mem_rdata_latched[11:7]` at `mem_do_rinst && mem_done`;
`cached_*` at `decoder_trigger_q`; `q_* <= dbg_*` every cycle.
`mem_xfer` and `mem_done` can occur in different cycles (prefetch/compressed paths).

| stage obligation | result |
|---|---|
| (b) q-stage preservation: prev dbg relation ⇒ `q_insn_opcode[11:7]==q_insn_rd` | **proved (UNSAT)** |
| (a) cached: `cached_insn_opcode[11:7]==cached_insn_rd` for 32-bit cached | **FALSE (SAT)** |

(a) fails globally because `next_insn_opcode` (captured at `mem_xfer`) and
`decoded_rd` (captured at `mem_do_rinst && mem_done`) can refer to different
cycles/words (prefetch / compressed high-word paths). An alignment guard or the
q-path is needed; do **not** assume the cached stage is selected at RVFI.

Next: determine the actual stage selected at the RVFI writeback
(`dbg_next`, `decoder_pseudo_trigger_q`, default `q`) and prove (a) only for that
path with the correct alignment, or use (b) if the q stage is selected.

#### S20/S21 — retirement stage selection + q-path decomposition

Timing: `rvfi_valid`, `rvfi_insn`, `rvfi_rd_addr` are registered; at the
`rvfi_valid` cycle the relevant latch edge is the previous cycle (`$past`).

Stage selectors at MUL retirement (proved over the real BTOR):
- `decoder_pseudo_trigger_q` = **false** ⇒ cached path not selected (**UNSAT**).
- `dbg_next` = **false** ⇒ next path not selected (**UNSAT**).
⇒ **the default q path is selected**: `dbg_insn_opcode = q_insn_opcode`,
`dbg_insn_rd = q_insn_rd` at the latch edge.

Proved stage facts now available:
- P1 decode: 32-bit → `decoded_rd == mem_rdata_latched[11:7]` (**UNSAT**)
- P2 fetch latch: `latched_rd == $past(decoded_rd)` (**UNSAT**)
- P3 operation: `dbg_insn_rd == latched_rd` (**UNSAT**)
- (b) q preservation: prev dbg relation ⇒ `q_insn_opcode[11:7]==q_insn_rd` (**UNSAT**)

Still open (all **UNKNOWN**, not counterexampled):
- direct target `rvfi_rd_addr == rvfi_insn[11:7]` at `rvfi_valid` (MUL);
- observation-point q relations `$past(q_insn_rd)==$past(latched_rd)` and
  `$past(q_insn_opcode[11:7])==$past(q_insn_rd)`;
- `$past(cpuregs_write)` at the latch edge.

Interpretation: the stage selection is now **proved** (q path), and the q-stage
relation is proved, but the full-CPU BTOR is solver-limited for the
observation-point `$past` composition. This is the same class of limitation as
the earlier W≥16 division: the logical decomposition is in place; the remaining
step needs a smaller/word-level engine or an operation-local pipeline model.

Do NOT change the architectural property. Next options:
  (i) operation-local pipeline model (q stage + RVFI latch) proved with SMT/z3
      using P1–P3 and (b) as lemmas;
  (ii) a word-level engine for the observation composition;
  (iii) keep L4 open with this precise status.

#### S24 — CTI-guided breakthrough: L4 is INDUCTIVE; M2 latch proved

Using the minimal-sandbox + CIll workflow (as suggested), the earlier
full-BTOR Unknowns resolve:

| property (minimal sandbox, real RTL) | CIll result |
|---|---|
| **L4 MUL**: `rvfi_rd_addr == rvfi_insn[11:7]` at `rvfi_valid` (MUL) | **inductive; proof succeeded** (27 s) |
| **L4 DIV**: same with `h_is_div` (real divider) | **inductive; proof succeeded** (31 s) |
| **M2 RTL operand latch**: `rvfi_rs{1,2}_rdata == $past(dbg_rs{1,2}val_valid ? dbg_rs{1,2}val : 0)` | **inductive; proof succeeded** (20 s) |
| M2 shadow form `rvfi_rs1_rdata == h_a` | **Not Inductive** (CTI shows stale/arbitrary shadow) |
| operand stability across wait (`dbg_rs1val`) | **FALSE at the entry transition** |

Key lessons:
- The full-property Unknowns were bloated-BTOR/solver artifacts, not false
  properties. **L4 is proved** for both MUL and DIV.
- M2 must use the RTL operand latch (`dbg_rs*val`), **not** the shadow `h_a`.
- The stability CEX is real but localized: a preceding register-file writeback
  changes `cpuregs_rs1` at the operation entry, and `dbg_rs1val` re-captures one
  cycle later. After the entry settles, the operand is stable; the multiplier's
  capture (`mul_start`) sees the settled value.

Remaining M2 sub-obligation: an entry-boundary invariant tying the multiplier's
captured operand (`mul_start`) to the RVFI operand (`dbg_rs*val`) after the
register-file settles. This is now a small, precisely located obligation.

Net: destination identity (L4) is CLOSED for MUL and DIV; operand latch is
proved; the only M2 gap is the entry-settle correspondence.

### 12.15 S25 — FINAL architectural data status (MUL and DIV closed)

CTI-guided minimal-sandbox proofs (real RTL, CIll):

| link | evidence |
|---|---|
| L4 MUL `rvfi_rd_addr==rvfi_insn[11:7]` | inductive, proof succeeded (27 s) |
| L4 DIV (same with `h_is_div`) | inductive, proof succeeded (31 s) |
| M2 MUL operand retirement `rvfi_rs{1,2}_rdata==$past(pcpi_rs{1,2})` | inductive, proof succeeded (59 s) |
| M2 DIV operand retirement | inductive, proof succeeded (64 s) |
| M2 start correspondence `pcpi_rs*==dbg_rs*val` at `mul_start` (PCPI path) | inductive |
| M2 RTL operand latch `rvfi_rs*_rdata==$past(dbg_rs*val)` | inductive |

**Outcomes (O0 front-end TCB explicit):**
- **MUL `o_rd_wdata_match`: CLOSED** — arithmetic (S1/S2) + data chain
  (O6 L1–L3) + operand correspondence (M2) + destination identity (L4).
- **MUL `o_pc_wdata_match`: CLOSED** — PC boundary + stability + RTL latch.
- **DIV architectural data: CLOSED** — S13–S16 + observation links (S17) +
  operand correspondence (M2) + destination identity (L4).

Notes:
- The earlier full-BTOR "UNKNOWN" results were bloated-model/solver artifacts;
  the minimal-sandbox CIll proofs establish the architectural links.
- The `dbg_rs1val` stability CEX on non-retiring paths is real but irrelevant to
  the retirement claim; the retirement correspondence is proved directly.
- Remaining honest caveats: O0 front-end trust; the MUL arithmetic/M2 interfaces
  are matched at the operation boundary; DIV signed/exceptional are as scoped.

### 12.16 S26 — DIV PC correspondence (closed)

DIV-specific query (real divider, CIll minimal sandbox):

| obligation | result |
|---|---|
| `h_div_pc_rel`: at DIV entry `next_pc == dbg_insn_addr+4` | **inductive** |
| `h_div_next_pc_stable`, `h_div_dbg_addr_stable` | **inductive** |
| (all three together) | **proof succeeded** (27 s) |

Composed with the RTL latch (`rvfi_pc_rdata <= dbg_insn_addr`,
`rvfi_pc_wdata = dbg_insn_addr = next_pc` at retire) this gives
`rvfi_pc_wdata == rvfi_pc_rdata+4 == spec_pc_wdata`.
**DIV `o_pc_wdata_match`: CLOSED** (same structure as MUL; O0 TCB explicit).

Note: the *direct* `h_div_pc` (`rvfi_pc_wdata == rvfi_pc_rdata+4` at
`rvfi_valid`) was Not Inductive (BMC-clean) — the CTI showed illegal/abstract
`cpu_state` encodings. Reusing the boundary+stability structure is what worked.
This confirms: similar RTL is a reason to reuse the structure, not evidence the
property is already proved.

Next: (2) close the RTL-to-arithmetic-model link (miter/operation contract).

### 12.17 S27 — RTL-to-model accumulator contract (MUL) closed

Operation-local miter (`/tmp/opencode/cill/t3/mul_contract`): instantiate the
real `picorv32_pcpi_mul` and a **plain shift-add accumulator** over the RTL's own
shift registers:

```
m_acc <= (mul_waiting ? 0 : m_acc + (rs1[0] ? rs2 : 0))
```

Contract: on active cycles `rd + rdx == m_acc`.

| form | result |
|---|---|
| finish-only (`mul_finish ⇒ rd+rdx==m_acc`) | BMC-clean, **Not Inductive** (CTI: arbitrary carry-save state) |
| active-cycle (`!mul_waiting ⇒ rd+rdx==m_acc`) | **inductive, proof succeeded** (16 s) |

This closes the RTL datapath ↔ recurrence link:
- shift registers track captured operands (S7 manifold), and
- the carry-save accumulator equals the plain shift-add model (this contract),
so the RTL datapath implements the recurrence whose closure S1/S2 prove equals
`a*b` at completion.

CTI-guided again: the finish-only form needed the reachable-manifold invariant;
the active-cycle form is the inductive one.

Next: the analogous DIV operation contract, then reproducibility consolidation.

### 12.18 S28 — DIV operation contract (real divider); partial

Operation-local miter (`/tmp/opencode/cill/t3/div_contract`) on the real
`picorv32_pcpi_div`.

| contract | result |
|---|---|
| finish mux `pcpi_rd == outsign ? -quotient : quotient` (DIV/DIVU) | **inductive** |
| finish mux `pcpi_rd == outsign ? -dividend : dividend` (REM/REMU) | **inductive** |
| last-iteration update (finish dividend = f(prev dividend, prev divisor)) | **inductive** |
| loop invariant `dividend < 2·divisor` (`divisor≠0`, 64-bit `2·divisor`) | BMC-clean; **Not Inductive** (fluctuates) |
| terminal ordering `dividend < N` at finish | BMC-clean; **Not Inductive** |

Notes:
- Sampling-edge bug found and fixed: after the finish edge the divider's
  `else` loop still updates `dividend`, so the finish-mux/ordering must use the
  **finish-edge** values (`$past`), not the `pcpi_ready`-cycle values.
- 63-bit `2·divisor` overflow at `N=2^31` was fixed with a 64-bit comparison.
- The terminal ordering is *proved abstractly* in S13; the RTL-side inductive
  proof is solver/CIll-unstable. Finish mux + last-update ARE inductive on the
  RTL.

Status: DIV RTL finish selection/last-update **closed**; RTL-side loop invariant
/terminal ordering **open (BMC-clean, abstract S13 proof exists)**.

### 12.19 S29 — Reproducibility consolidation

See `automation/decomp/README.md` (single documented flow) and
`automation/decomp/reproduce.sh`. It records, per obligation: command, inputs
(+sha256 where available), engine, runtime, assumptions/TCB, and status
(proved / BMC-clean-unproved / open / solver-limited). The focused CIll runs are
reported as focused checks, **not** as one unified full-checker run.

### 12.20 S30 — DIV RTL-to-abstract-state correspondence CLOSED

Sandbox `/tmp/opencode/cill/t3/div_loop` (real non-ALTOPS `picorv32_pcpi_div`),
shift-index manifold + captured `N=|b|`:

| obligation | result (CIll IC3) |
|---|---|
| loop-state `msk == 1<<h_k`, `divisor == N<<h_k` (`running ∧ msk≠0`) | **inductive** |
| updates `divisor>>1`, `msk>>1`, `h_k-1`, `dividend`, `quotient` | **inductive** |
| invariant `dividend < 2·divisor` (`msk>1`, `divisor≠0`, 64-bit) | **inductive** |
| last premise `dividend < 2·divisor` at `msk==1` (= `2N`) | **inductive** |
| terminal ordering `dividend < N` at finish (`running ∧ msk==0`) | **inductive** |
| all together (10 properties) | **proof succeeded** (140 s) |

Key corrections (all CTI-guided):
- use a **shift-index shadow** `h_k` (no 32×32 multiply);
- guard the loop phase `running ∧ msk≠0`, exclude the **start** transition from
  the update (`!$past(h_start)` ⇒ load, not shift);
- `b=0` guard (`divisor≠0`/`h_N≠0`) on invariant/terminal;
- preserve S13's split: invariant for `msk>1`, inherited premise at `msk==1`,
  terminal step at the finish boundary; use 64-bit `2·divisor`.

**This closes the DIV RTL-to-arithmetic-model link.** Combined with S28
finish muxes, S13 quotient theorem, S15 signed correction, S14 exceptional
cases, S16 branch selection, S17 observation, and L4/M2:
**DIV architectural data and PC are closed at the integration level** (O0 TCB).

### 12.21 — DIV milestone closure

| milestone | status |
|---|---|
| DIV RTL loop-state + update correspondence | **closed** |
| DIV RTL loop invariant + terminal ordering | **closed** |
| DIV RTL↔abstract arithmetic chain | **closed** |
| DIV finish mux / signed / exceptional / observation | closed/checked |
