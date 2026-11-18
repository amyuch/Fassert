# PCD method

This document describes the target, cut, obligation, and hand-off method. The
planner chooses which obligations exist and how they depend; the kernel checks
the result.

Complete acceptance requires a complete proof of the target: `CHECKED` root, no
direct target TCB, only official TCB kinds deeper, and no assumption
helpers/cuts or `OPEN`/`UNKNOWN` premises. See [`03-rules.md`](03-rules.md).

This is a planning + checking discipline, not a mandatory template. Each step
names its output and its acceptance check, so the hand-off is machine-checkable.

---

## Step 0 — Target and trust boundary

Inputs: target property, spec semantics, reset assumptions, configuration,
harness, source/model relationship.

Outputs:

- a frozen target theorem with exact guards and claim scope (partial vs total,
  leaf vs architectural);
- model identity (`kind`, `sha256`, build recipe) and a TCB statement
  (front-end, solver, unmodeled environment);
- the observation/boundary point.

Acceptance: the target and its guards are recorded and hashed. No later step may
narrow them to make the proof easier.

---

## Step 1 — Extract the operation/model and its boundaries

Find:

- entry `E`, exit/termination `X` (distinct from the loop guard);
- internal recurrence and live-in operands;
- internal state and the architectural observation point;
- candidate cut points and captured-input shadows (e.g. a counter, a symbolic
  index, a shifted operand).

Outputs: an operation-local transition model, phases, candidate cuts, and an
observation point.

Acceptance: `E`, `X`, the recurrence, and the observation point are stated over
real model signals with sampling edges (old vs new values). Every assumption on
the environment is named.

---

## Step 2 — Build the obligation dependency graph

Classify each obligation by role and kind, and state its `requires`/`provides`
guarantees.

General roles:

| role | meaning | typical backend |
|---|---|---|
| `invariant` | over-approximation of reachable states; inductive | IC3/PDR/k-induction, CHC |
| `update` | next-state correspondence for a state component | transition reasoning |
| `algebra` | arithmetic/spec identity | poly, SMT, word-level certificate |
| `terminal` | fact true at exit, not globally | ordering/terminal reasoning |
| `temporal` | entry→exit summary, macro-step, eventual/terminal | temporal induction, acceleration |
| `select` | result selection / mux correspondence | SMT, engine |
| `operand` | operand/destination identity at the boundary | SMT, engine |
| `observe` | result reaches the architectural observation point | SMT, engine |
| `rtl_link` | front-end/model correspondence | TCB or miter |
| `transfer` | reuse/refinement between models | miter, relation certificate |
| `abstraction_gate` | over-approximation is sound | miter, relation certificate |
| `coverage` | guard partition is exhaustive | SMT, kernel |
| `interface` | joins abstract facts to model facts | SMT over guarantees |
| `compose` | root composition | kernel + SMT |
| `tcb` | explicit trusted boundary | TCB |

Output: a proof DAG with explicit unresolved edges and candidate contracts.

Acceptance: every node has a role, kind, phase, model, assumptions, and a
proposed certificate form or engine. Cyclic same-state dependencies are allowed;
future-state assumptions are not.

---

## Step 3 — Propose and discharge local obligations

Discharge in this order (skip what is trivial):

1. reachability/manifold and update relations (transition reasoning);
2. semantic recurrence / arithmetic certificate (poly, word-level, interface);
3. terminal facts, progress, temporal summary;
4. result selection, operand identity, architectural observation;
5. coverage and transfer/interface obligations.

Output: individually checked or replay-bound lemmas with evidence.

Acceptance:

- a `CHECKED` certificate establishes the exact statement under the stated
  assumptions;
- a `REPLAY` binding reproduces the exact engine verdict on the exact model;
- `BMC_CLEAN` is recorded as diagnostic only;
- timeouts are neither proofs nor counterexamples.

---

## Step 4 — Check composition and coverage

Check that the discharged lemmas imply the target:

- entry: `A ∧ E ⇒ Φ`;
- preservation per guard class, with `T_enabled ⇒ ⋁_g T_g`;
- terminal: `Φ ∧ X ∧ Δ ⇒ Post` (Δ proved, not assumed);
- observation: `Post @ X ⇒ P @ observation`;
- dependency closure: every assumption discharged;
- guarantee matching: every premise resolves to an exported guarantee;
- transfer: non-primary models have a checked transfer node.

Output: an accepted proof package or a precise list of open obligations.

Acceptance (kernel rules; see [`04-workflow.md`](04-workflow.md) and
[`00-theorem.md`](00-theorem.md)):

1. schema and reference well-formedness;
2. local evidence: checked certificate or replay binding; no free-text evidence;
3. dependency closure; no diagnostic/unknown/CEX premise;
4. transfer/abstraction gate when models differ;
5. coverage certificate;
6. guarantee matching and a checked root implication;
7. provenance, model registry, reuse match, no level upgrade;
8. per-node artifact binding;
9. non-vacuity/helper hygiene;
10. proposal/verdict separation.

The kernel is the only component allowed to declare a target closed. The planner
never does.

---

## Step 5 — Replay and report

Replay from a clean environment; validate model and artifact identities; record
tool versions, runtimes, budgets, and the reason a run stopped.

Output: reproducible evidence (run record + proof package + report), not an
interactive session.

Report:

- the target proved, with `(evidence, composition)` level;
- the TCB;
- open obligations and rejected candidates;
- the residual and the evidence class for each target.

---

## The SPC contract (composition rule)

For an iterative operation, the composition rule is a Stratified Progress
Contract:

```
C = (A, E, X, T_G, Φ = M ∧ C_rec ∧ Σ, ρ, Δ, Post, P)

O0 rtl_link     : T_G faithfully represents the model (front-end TCB / miter)
O1 entry        : A ∧ E            ⇒ Φ
O2 preservation : Φ ∧ T_g ∧ ¬X     ⇒ Φ'     for every guard g
                  guard coverage: T_enabled ⇒ ⋁_g T_g
O3 progress     : (optional) well-founded ρ decreases on progress transitions
O4 finalization : Φ ∧ X ∧ Δ        ⇒ Post
O5 terminal     : Φ ∧ X            ⇒ Δ      (Δ may be a nested SPC lemma)
O6 observable   : Post @ X         ⇒ P @ observation
O7 non-interf.  : (when needed) no conflicting operation interleaves
```

Partial correctness drops O3. `O5`/`O6` may be nested SPC instances; the rule is
closed under nesting. The contract is a *template for obligations*, not a proof
by itself: every obligation must be discharged and checked.

---

## Failure taxonomy → tactic

Diagnose the CTI/CEX first; the failure type selects the decomposition.

| failure | symptom | tactic |
|---|---|---|
| unreachable CTI | CTI uses an unreachable state | invariant strengthening, phase/manifold fact |
| representation mismatch | true but unnatural in the current logic | representation change + refinement |
| uncovered branch | CTI takes an unprotected path | case/guard decomposition + coverage |
| cross-component dependency | local facts need a neighbor's guarantee | assume-guarantee / interface |
| temporal/transient | holds only at exit/eventually | terminal facts, macro-step, ranking |
| wide arithmetic/quantifier | bit-blasting/quantifier blowup | theory certificate, purification, symbolic index |
| sampling/quantification error | wrong cycle/edge/quantifier | restate at the correct time/phase |
| composition gap | local proofs exist but do not imply P | add interface/observation lemma; check guarantees |
| real counterexample | property false or target wrong | stop; repair statement or design |

Strategies:

| id | strategy | what changes |
|---|---|---|
| S1 | invariant strengthening | add reachable-state invariants/contracts |
| S2 | decomposition / contracts | cut at components, time windows, operations; assume-guarantee |
| S3 | representation / theory certificate | purify, index, abstract datapath; prove refinement |
| S4 | model abstraction + refinement | over-approximate, prove gate, CEGAR |
| S5 | temporal summary / ranking | macro-step, acceleration, progress/termination |

Refinement returns to the relevant step, not necessarily the start.

---

## Roles: planner, engines, kernel

- **Planner (untrusted):** proposes cuts, contract structure, roles/kinds,
  engines, certificate candidates, and reuse; records rationale. Never closes.
- **Runner:** executes proposals under budget; records every engine call.
- **Engines:** transition invariants (IC3/PDR/CIll), algebra (poly/word-level),
  case splits/ordering (SMT), temporal summaries (induction).
- **Kernel:** validates artifacts, dependencies, coverage, transfer, and the
  final implication.
- **Reporter:** computes levels, TCB, and open items.

A failure returns to the planner as a structured diagnostic (which obligation,
which assumption, which phase, which transition), not as a timeout to retry.

---

## Worked DAG shapes

These are shapes, not claims about any particular case.

**Iterative arithmetic:**

```
manifold ─┬─> step correspondence ─┐
algebra  ─┘                        ├─> finalization ─> observation ─> P
terminal ──────────────────────────┘
interface/instantiation ───────────┘
```

**Long-latency / bit-serial:**

```
phase/counter ─> macro-step summary ─> completion at exit ─> observation ─> P
```

**Observation/interface chain:**

```
result fact ─> select/mux ─> capture ─> writeback ─> architectural latch ─> P
```

**Transfer:**

```
source-model lemma ─> transfer obligation ─> target-model lemma
```

If any node in these shapes is only `REPLAY` or `TCB`, the root claim says so.
