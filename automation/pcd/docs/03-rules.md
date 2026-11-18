# PCD rules

Complete acceptance is the default. These rules state soundness conditions and
failure modes; the kernel enforces them. Discovery heuristics live in
[`07-hard-case-playbook.md`](07-hard-case-playbook.md) and arithmetic patterns
in [`11-arithmetic-lifting.md`](11-arithmetic-lifting.md). They are advisory:
they suggest proof shapes and cuts, but they never override this document or the
kernel.

Tags:

- `[P]` principle or protocol invariant; enforced by the kernel or harness.
- `[H]` hypothesis; needs an experiment.

Each rule names its soundness condition and its failure mode.

---

## R1. Cut at semantic boundaries — [P]

- **Principle:** separate the iterative/engine part from the observation path;
  state operation-local contracts.
- **Soundness:** the boundary link is an obligation (`interface`/`observe`), not
  an assumption. A cut is a proof obligation.
- **Failure:** a cut that hides an unproved observation, latency, or transfer
  link.

## R2. Match the proof method to the obligation — [P]

- **Principle:** do not force every obligation into bit-level induction or raw
  bit-vector SMT.
- **Soundness:** each backend's certificate establishes its exact statement; the
  kernel composes them.
- **Failure:** sending a wide arithmetic identity to bit-blasting and calling a
  timeout a result.

## R3. Preserve reachability assumptions explicitly — [P]

- **Principle:** a relation true on reachable states may be false for arbitrary
  induction states; supply the manifold/phase.
- **Soundness:** the manifold/phase fact is itself inductive or checked.
- **Failure:** asserting a reachable-only relation as a global invariant.

## R4. Terminal facts are their own obligations — [P]

- **Principle:** do not promote a last-step fact into a global invariant.
- **Soundness:** the terminal fact is proved and consumed by finalization.
- **Failure:** extending a loop invariant blindly to the final iteration.

## R5. Derive interface summaries from actual transitions — [P]

- **Principle:** a plausible ghost relation is not evidence that the model
  implements it.
- **Soundness:** ghost updates are justified by the model transition; prefer the
  model's own signals when they suffice.
- **Failure:** ghosting the expected result and proving the ghost by
  construction.

## R6. Compose only checked facts — [P]

- **Principle:** the final theorem must follow from discharged dependencies.
- **Soundness:** the kernel checks dependency closure, guarantee matching,
  coverage, and the root implication.
- **Failure:** assuming the target, or an unchecked/diagnostic lemma.

## R7. Respect sampling edges — [P]

- **Principle:** track old/new nonblocking values and `$past` boundaries.
- **Soundness:** state the property at the cycle/edge where the model samples
  it; the phase is explicit.
- **Failure:** mixing pre/post-edge values, producing a spurious CEX or a
  non-inductive obligation.

## R8. Cut at the operation/local-model boundary — [P]

- **Principle:** re-express deep properties operation-locally when the full
  model makes them intractable.
- **Soundness:** the local model must be tied to the original model
  (`rtl_link`/`transfer`) and the boundary link checked.
- **Failure:** trusting a local proof without the transfer/RTL link.

## R9. Let the CTI choose the obligation's form — [P]

- **Principle:** treat Not-Inductive/CEX as a **form** signal.
- **Soundness:** changing form is legitimate only if the new obligation is the
  intended one and is checked.
- **Failure:** retrying the same query with a larger timeout.

## R10. Reuse requires matching assumptions — [P][H]

- **Principle:** similar structure is a reason to try, not evidence.
- **Soundness:** model, width, guards, phase, and transition relation match; the
  reused lemma's assumptions are discharged at the new interface; the transfer is
  an explicit, `CHECKED` node and its certificate is bound to the transfer
  formula. Complete mode rejects an unproved or `STRUCTURAL` transfer and does not
  treat the source model as a design TCB.
- **Failure:** copying a lemma between models because the RTL "looks the same",
  or replacing the transfer with an identity implication without documenting the
  shared model/mapping argument.
- **`[H]`:** that reuse decisions can be made systematic rather than curated.

## R11. Separate abstract lemmas from model links — [P]

- **Principle:** a checked abstract arithmetic fact is not an implementation
  link.
- **Soundness:** both the abstract lemma and the instantiation/interface node
  are checked and composed; neither substitutes for the other.
- **Failure:** counting an abstract proof as an implementation proof.

## R12. A helper that proves nothing is not a lemma — [P]

- **Principle:** a recorded lemma must constrain the state. A tautology, a
  satisfiable-but-never-constraining assertion, or an unreferenced assertion
  discharges nothing.
- **Soundness:** K9 locates cited assertions and checks non-vacuity where
  possible; regex hygiene is a fallback.
- **Failure:** a structural kernel accepts a vacuous helper because the defect
  is inside the helper, not in the DAG.

## R13. Abstract arithmetic needs an explicit instantiation node — [P]

- **Principle:** an abstract lemma belongs in the graph only with the node that
  joins it to the model-side facts.
- **Soundness:** the instantiation node's premises are the model-side facts; its
  conclusion is the abstract fact instantiated at the model's values; the
  certificate binds the bridge.
- **Failure:** an arithmetic node that assumes only "terminal" and is connected
  to the RTL by nothing.

## R14. Proposals are not verdicts — [P]

- **Principle:** a planner may propose an obligation, a status guess, a
  certificate shape, or a reuse decision. It may not set a final status.
- **Soundness:** every verdict references a backend/checker run id; proposal
  records and verdict records are separate; K10 rejects proof files that carry
  planner status as evidence.
- **Failure:** an LLM says "proved" and the graph records it.

## R15. Bind evidence to runs and artifacts — [P]

- **Principle:** a `REPLAY` verdict names model hash, command, tool version, and
  log hash; a `CHECKED` certificate names its checker and payload/artifact hash.
- **Soundness:** K2 validates the binding and regenerates `CHECKED` SMT/poly
  evidence from the named guarantee formula; K8 verifies artifacts per node, not
  only at the root.
- **Failure:** a free-text `evidence` string, an unbound artifact, or an
  arbitrary unsat SMT script substituted for the obligation.

## R16. Coverage is a certificate — [P]

- **Principle:** "all guards covered" is a proof obligation over the guard
  partition, not a boolean flag.
- **Soundness:** K5 checks the partition is exhaustive and the coverage
  certificate is valid.
- **Failure:** a branch is added but the coverage fact is copied from the old
  partition.

## R17. The framework is case-agnostic — [P]

- **Principle:** cases are data; backends are plugins.
- **Soundness:** no case name or case-specific condition in framework source; a
  new case is data-only; a new obligation kind is a plugin + tests.
- **Failure:** a "general" flow that special-cases MUL/REM.

## R18. Blind evaluation for planner claims — [P]

- **Principle:** a claim about planning ability requires a blind run.
- **Soundness:** the planner process runs under filesystem isolation with the
  oracle and prior runs hidden; context and proposals are hashed; leakage is
  audited; commands are resolved from a trusted backend catalog, not from the
  proposal.
- **Failure:** "the planner found it" after a human copied a lemma from a prior
  graph, or after a proposal executed an arbitrary command.

---

## R19. Cuts and helpers are obligations — [P]

- **Principle:** a cut contract is a pattern over checked facts, and a helper is
  an obligation with a role, not a free premise.
- **Soundness:** K11 requires each cut's `entry`, `step`, `exit`, and `link`
  facts to be declared premises; a guarded cut needs a matching checked coverage
  node. A monitor helper must use the primary model and be `REPLAY`/`CHECKED`;
  a submodel helper needs a reuse/transfer obligation. In complete mode every
  helper assertion must be named, declared, and bound to a proved node whose
  certificate names that exact assertion; every helper assumption must be bound
  to a proved lemma or official TCB in a target closure. Assumption helpers and
  assumption cuts are rejected.
- **Failure:** a cut with an undeclared observation link, a helper that is
  actually an assumption, an undeclared helper assertion, or a TCB helper
  silently counted as checked evidence.

## R20. Diagnostics inform form, never premises — [P]

- **Principle:** a CTI is evidence about why a candidate failed, not a fact about
  the system.
- **Soundness:** CTI records carry `evidence: "DIAGNOSTIC"`, `proof: false`; the
  kernel never consumes them; a later iteration binds them into a new frozen
  context as diagnostics only. A timeout, missing artifact, or `UNKNOWN` is not a
  CTI; a CTI is not a counterexample proof.
- **Failure:** adding a CTI signal as a helper premise, or promoting a selected
  trace to a lemma.

## R21. Complete acceptance is the default — [P]

- **Principle:** a final accepted result must completely prove the target
  assertion, not merely compose checked links over design trust boundaries.
- **Soundness:** complete mode requires `acceptance: "complete"` in the case and
  proof plus `metadata.completeness: "complete"`. The target root must be
  `CHECKED`, `target.tcb` must be empty, and every reachable node must have
  `CHECKED`/`REPLAY` evidence with verdict `proved`. Only official
  `frontend`/`engine`/`checker`/`isa_model` TCBs are permitted; design TCBs,
  assumption-helper TCBs, assumption cuts, `STRUCTURAL` roots, `OPEN`/`UNKNOWN`
  verdicts, and missing-artifact overrides are rejected. Every named helper
  assertion must be declared and bound to a proved node whose certificate names
  that assertion; every helper assumption must be bound to a proved lemma or
  official TCB in a target closure.
- **Failure:** calling a target proved because every leaf is "checked" while the
  graph hides a design TCB, an unlisted helper assumption, a timeout, or a
  structural implication.

## R22. Check model and arithmetic boundaries — [P]

- **Principle:** a proof on one model is applicable to another only through a
  checked relation over their actual semantics and environment constraints.
- **Soundness:** K13 requires model-bound structural projection certificates
  for cross-model premises. Source initialization, updates, constraints and
  property meaning must be preserved. Required target properties are frozen in
  the case. A source engine proof retains its REPLAY assurance through a
  CHECKED projection. A `free_map` is an untrusted proposal: the checker
  re-normalizes every bit with `Model.bits` and verifies the property,
  initialization, transitions, and source constraints. Non-free atoms use
  one-to-one same-width whole-atom maps. Free atoms may share a destination
  bit, but one source bit may not be forced to multiple independent
  destination bits. Arithmetic facts and imported assumptions require the
  model-bound certificates and explicit discharge edges of R23.
- **Failure:** treating `P => P` as evidence of RTL refinement, changing the
  model or time interpretation behind a Boolean name, or using an unverified
  integer recurrence to close a hardware assertion. See [`09-composition-guard.md`](09-composition-guard.md).

## R23. Arithmetic and solver imports share model semantics — [P]

- **Principle:** changing a solver or representation does not change the
  theorem's variables, word semantics, sampling or assumptions.
- **Soundness:** `btor-smt` regenerates actual initialization, transitions and
  constraints. Typed predicates explicitly bind current/next model nodes and
  BV/Int conversions. Every strengthening invariant is established and
  preserved. A constraint used by another model must be implied by a proved
  state fact on the original model; a future-only theorem or a proof under the
  restricted model cannot discharge it. The kernel checks all dependencies
  and rejects cycles. See [`10-solver-bridge.md`](10-solver-bridge.md).
- **Failure:** supplying a convenient recurrence instead of checking the RTL
  transition, treating modular addition as integer addition without its side
  conditions, or importing a proved formula as a different hardware assumption.

## R24. Final accept is computed from the obligation ledger — [P]

- **Principle:** `proved`, `needs_check`, and `reject` are judgments about the
  package, not fields supplied by the package or the planner.
- **Soundness:** `kernel/disposition.py` derives a target-closure obligation
  ledger and computes the status. `proved` requires every required obligation to
  be discharged under the explicit TCB. A missing obligation is
  `needs_check` with a residual; invalid or refuted evidence is `reject`. Every
  checker error must be attached to an obligation, or it becomes a fatal
  package-level defect. See [`00-theorem.md`](00-theorem.md).
- **Failure:** storing `"status": "proved"` in a proof, treating a timeout or an
  unproved helper assumption as success, or hiding a stray error outside the
  target closure.

---

## Negative rules (auditability)

1. Do not infer correctness from `BMC_CLEAN` alone.
2. Do not treat a model hash as proof of source-to-model equivalence.
3. Do not classify a timeout/`UNKNOWN` as a counterexample or a proof.
4. Do not count a checked abstract lemma as a checked model link.
5. Do not silently discard a counterexample by narrowing the target.
6. Do not let the planner mark an obligation closed; only the kernel may.
7. Do not record a vacuous lemma (K9).
8. Do not place an abstract lemma in a graph without an instantiation node.
9. Do not describe a structural kernel acceptance as a proof.
10. Do not trust a `free_map` because it was proposed by the planner; the
    checker must reconstruct every bit relationship with `Model.bits`.
11. Do not put a case-specific shortcut in framework code.
12. Do not use a prior decomposition in a blind run.
13. Do not upgrade `REPLAY` to `CHECKED` without a checker run.
14. Do not consume a CTI/`UNKNOWN` as evidence, a premise, or a lemma.
15. Do not present an unproved helper assumption as checked composition.
16. Do not bind a diagnostics context that is not diagnostic-only or whose hash
    no longer matches.
17. Do not accept a design TCB, an assumption-helper TCB, an assumption cut, or
    a missing-artifact override as a complete proof.
18. Do not accept `OPEN`, `UNKNOWN`, `BMC_CLEAN`, a timeout, or `STRUCTURAL`
    composition as a complete verdict.
19. Do not read a stored status tag; only the computed disposition can say
    `proved`.
20. Do not count `needs_check` as an accept or as a counterexample.
