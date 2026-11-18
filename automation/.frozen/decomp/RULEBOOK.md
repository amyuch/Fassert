# Rulebook — decisions that worked, and their status

Each rule: principle, rationale, soundness condition, evidence, failure mode.
Tags: **[E]** supported by checked evidence in this project; **[H]** hypothesis
about automation/generality, not yet demonstrated.

## R1. Cut at semantic boundaries — [E]

- **Principle:** separate the iterative engine from the architectural
  observation path; state operation-local contracts.
- **Rationale:** deep CPU-level properties are hard for IC3; operation-local
  minimal models were decisive.
- **Soundness:** the boundary link (`O6`/`O0`) must be checked; a cut is a proof
  obligation, not an assumption.
- **Evidence:** L4/M2/O6 links closed in minimal sandboxes after failing as deep
  properties; S17 observation chain.
- **Failure:** a cut that hides an unproved observation/latency link.

## R2. Match the proof method to the obligation — [E]

- **Principle:** do not force every obligation into bit-level induction or raw
  SMT-BV.
- **Rationale:** MUL's closure is algebraic (purified), DIV's is ordering/case
  reasoning, SERV's is a temporal summary; raw BV/SMT division/multiplication hit
  bit-blasting frontiers.
- **Soundness:** each backend's certificate must establish its exact lemma; the
  kernel composes them.
- **Evidence:** S1/S2 (poly), S13/S15 (ordering/interface), S5 (macro-step);
  W≥16 division timeout vs 12 ms interface proof.
- **Failure:** sending a wide arithmetic identity to bit-blasting (timeout).

## R3. Preserve reachability assumptions explicitly — [E]

- **Principle:** a relation true on reachable states may be false for arbitrary
  induction states; supply the manifold.
- **Rationale:** the carry-save update relation is false for arbitrary state;
  clean cross-state dependencies require the reachable manifold.
- **Soundness:** the manifold itself must be inductive/checked (O1/O2).
- **Evidence:** `acc'=acc+t` is `sat` for arbitrary state but the S7 manifold
  makes the product step valid; DIV invariant needed `divisor≠0`/manifold.
- **Failure:** asserting a reachable-only relation as a global invariant.

## R4. Terminal facts are their own obligations — [E]

- **Principle:** do not promote a last-step fact into a global invariant.
- **Rationale:** DIV's `dividend<N` holds at termination, not throughout; the
  global `d<2s` shape fails at odd `s`.
- **Soundness:** terminal fact `Δ` proved and consumed by `O4`.
- **Evidence:** S13 Δ1–Δ3; S30 last premise at `msk==1` + terminal at finish.
- **Failure:** extending a loop invariant blindly to the final iteration.

## R5. Derive interface summaries from actual transitions — [E]

- **Principle:** a plausible ghost relation is not evidence that the RTL
  implements it.
- **Rationale:** the shadow `h_a` was stale/arbitrary; the RTL operand latch was
  inductive.
- **Soundness:** ghost updates must be justified by the RTL transition; prefer
  the RTL's own signals when they suffice.
- **Evidence:** M2 shadow Not Inductive vs RTL latch proved; O6 RTL-derived links
  proved.
- **Failure:** ghosting the expected result and proving the ghost by construction.

## R6. Compose only checked facts — [E]

- **Principle:** the final theorem must follow from discharged dependencies.
- **Rationale:** hidden assumptions and missing algebraic laws are easy to miss.
- **Soundness:** kernel checks dependencies, guard coverage, and the final
  implication.
- **Evidence:** S2's negative test caught a missing zero law; explicit integration
  links.
- **Failure:** assuming the target (or an unchecked lemma) in the composition.

## R7. Respect sampling edges — [E]

- **Principle:** track old/new nonblocking values and `$past` boundaries.
- **Rationale:** finish-edge vs `pcpi_ready` values differ (the divider's else
  loop mutates `dividend` after finish); `$past` across reset and the start
  transition caused false/unknown results.
- **Soundness:** state the property at the cycle/edge where the RTL samples it.
- **Evidence:** S28 finish mux needed `$past`; S30 needed `!$past(h_start)`;
  reset-boundary fixes.
- **Failure:** mixing pre/post-edge values (spurious CEX or non-inductive).

## R8. Cut at the operation/local-model boundary — [E]

- **Principle:** re-express deep CPU properties operation-locally.
- **Rationale:** full-BTOR queries returned UNKNOWN; minimal sandboxes proved the
  same relations.
- **Soundness:** the local model must be tied to the RTL (O0/rtl_link) and the
  boundary link checked.
- **Evidence:** S24/S26/S30 after earlier full-BTOR UNKNOWNs.
- **Failure:** trusting a local proof without the boundary/RTL link.

## R9. Let the CTI choose the obligation's form — [E]

- **Principle:** treat a Not-Inductive/CEX as a **form** signal.
- **Rationale:** the same fact can be finish-only vs active-cycle, shadow vs RTL
  latch, `$past`-aligned or not.
- **Soundness:** changing form is legitimate only if the new obligation is the
  intended one and is checked.
- **Evidence:** MUL accumulator (active-cycle), M2 (RTL latch), DIV (finish-edge).
- **Failure:** retrying the same query with a larger timeout.

## R10. Reuse requires matching assumptions — [E]/[H]

- **Principle:** similar RTL is a reason to *try* reuse, not evidence.
- **Rationale:** a lemma is reusable only if model, width, guards, and transition
  relation match, and its assumptions are discharged in the new graph.
- **Soundness:** the kernel checks the reused lemma's assumptions at the new
  interface.
- **Evidence [E]:** the MUL PC structure did not transfer to DIV as a direct
  property; the boundary/stability structure did.
- **Hypothesis [H]:** that the flow can *systematically* decide reuse for new
  operations.

## R11. Separate abstract lemmas from RTL links — [E]

- **Principle:** a checked abstract arithmetic fact is not an RTL implementation
  link.
- **Rationale:** S13's Δ/quotient theorem is abstract; S30 establishes the RTL
  loop-state correspondence.
- **Soundness:** both must be checked and composed; neither substitutes for the
  other.
- **Evidence:** S13 vs S30; S1 vs S27.
- **Failure:** counting an abstract proof as an implementation proof.

## R12. A helper that proves nothing is not a lemma — [E]

- **Principle:** a recorded "lemma" must actually constrain the state; an
  assertion that is trivially true discharges nothing.
- **Rationale:** on 2026-10-22 the REM `h_dividend_update` lemma was recorded as
  proved while reading `assert(dividend == $past(dividend) || 1'b1)`. Every
  structural check (DAG closure, status, provenance) accepted it, because the
  defect is *inside* the helper, not in the graph.
- **Soundness:** kernel rule **K9** now scans committed helper sources for
  tautological assertions; the audit also re-derived and re-proved the real
  lemma (the isolated divider model proves it inductively).
- **Evidence [E]:** the incident itself; the repaired run
  (`btor:98dfa44b…`, 18/18 inductive) and the kernel's negative control
  `neutered_helper`.

## R13. Abstract arithmetic needs an explicit instantiation node — [E]

- **Principle:** an abstract lemma (e.g. `d == M % N`) belongs in the graph only
  together with the node that joins it to the RTL-side facts.
- **Rationale:** the REM graph had `rem_arith` assuming only `terminal`, so the
  arithmetic was connected to the RTL by nothing at all; the DIV graph had the
  same gap.
- **Soundness:** the graph now has a `role:"interface"` node whose premises are
  the RTL-side facts (entry, step, manifold, invariant, terminal, finish mux)
  and whose conclusion is the instantiation; the bridge (S19) is the checked
  artifact behind it, sha256-bound to the target (kernel **K8**).
- **Evidence [E]:** S19 B0-1…B0-4 (with a *sat* mis-scaled control), S18 [C]/[D].

## Negative rules (auditability)

1. Do not infer correctness from BMC-clean results alone.
2. Do not treat a model hash as proof of source-to-model equivalence.
3. Do not classify a solver timeout/UNKNOWN as a counterexample or as a proof.
4. Do not count a checked abstract arithmetic lemma as a checked RTL link.
5. Do not silently discard a counterexample by narrowing the operation boundary.
6. Do not let the planner (LLM) mark an obligation closed; only the kernel may.
7. Do not record a lemma whose assertion is vacuous (tautology) — kernel K9.
8. Do not place an abstract arithmetic lemma in a graph without an interface
   node that names the RTL-side facts it is instantiated on.
9. Do not describe a kernel acceptance as a proof: it is an L3 check; the
   closure claim lives at the level of its leaves (L1) or their checked
   composition (L2).

## Evidence vs hypothesis (summary)

**[E]:** R1–R9, R11–R13 (and R10's "similar RTL is not evidence" half).
**[H]:** the breadth of R10 (systematic reuse decisions); the LLM planner /
automation path; transfer to a *temporal* regime (SERV); scale beyond these
operations.

### Status of the REM transfer experiment (H-A4, REM part)

The REM transfer experiment has now been run **and audited** (2026-10-22):
- first attempt: accepted by the kernel but not proof-trusted (a vacuous helper
  and a missing interface node — see R12/R13);
- after repair: the divider facts are L1 (CIll 18/18 inductive on the isolated
  divider model, transfer recorded in the graph), the observation facts are L1
  on the full core, and `o_rd_wdata_match` is closed at **L2** by a checked
  composition (S18+S19).
- what is *not* claimed: that the root is CIll-inductive (it is not), or that
  the composition is a single unified proof run.

## Automation hypotheses (explicitly unproven)

- **H-A1:** a planner can infer cut points and obligation kinds from RTL+spec
  within a fixed budget.
- **H-A2:** reuse decisions can be validated by assumption matching, not manual
  curation.
- **H-A3:** the CTI/CEX feedback loop is sufficient to refine obligation form.
- **H-A4:** the approach transfers to a new semantic endpoint (REM) and a
  temporal regime (SERV).

These are tested by the planned REM/SERV transfer experiments, not assumed.
