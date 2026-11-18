# Workflow — three layers

This document separates three layers that are related but must not be conflated:

- **A. Proof development** — what to try next when a proof fails.
- **B. Soundness framework** — why the resulting proof implies the original.
- **C. Automation architecture** — who proposes, who discharges, who validates.

The two pillars are: **construction** (heuristic, incomplete) and
**validation** (formal, checkable). Only the kernel (Layer B/C) may declare a
theorem closed.

---

# A. Proof development (diagnosis-guided)

## A0. Cheap diagnostics first (not a proof)

Purpose: find a genuine counterexample and validate assumptions/traces before
investing in a decomposition.

- simulation / random tests, shallow BMC (`rIC3 --bmc-kissat`), bounded
  k-induction;
- **trace replay** and PREUNSAT checks to classify real vs spurious
  counterexamples and to validate premises.

`BMC_CLEAN` is diagnostic only. S0 should be cheap and may be skipped or
shortened; it is not a mandatory long stage.

## A1. Diagnosis-guided portfolio (not a fixed ladder)

1. cheap diagnostics (A0);
2. one baseline attempt (default: IC3/k-induction on the target);
3. **diagnose** the failure (A3) and select a strategy by evidence;
4. optionally run a **small portfolio of competing strategies** under a fixed
   budget;
5. refine; return to the relevant strategy, not the start.

## A2. Strategies (complementary, not a hierarchy)

| id | strategy | what it changes |
|---|---|---|
| S1 | invariant strengthening | add reachable-state invariants/contracts (tightens the over-approximation; must still contain `Reach`) |
| S2 | decomposition / contracts | cut at components/time windows; assume-guarantee; operation-local contracts |
| S3 | representation / theory certificate | purify arithmetic, symbolic index, datapath representation; prove the refinement |
| S4 | model abstraction + refinement | over-approximate the model, prove the soundness gate, CEGAR spurious CEXs |
| S5 | temporal summary / ranking | macro-step, acceleration, progress/termination |

**Corrected distinction (important).**
- An inductive invariant `J` has `I⇒J`, `J∧T⇒J'`, hence `J ⊇ Reach`: it is an
  **over-approximation of `Reach`**. *Strengthening* conjoins facts, making the
  over-approximation **tighter** (closer to `Reach`); it may exclude *unreachable*
  states, never reachable ones.
- *Model abstraction* transforms the model to `M#` with an over-approximation
  relation; `M# ⊨ P#` implies `M ⊨ P`, and abstract CEXs may be spurious
  (CEGAR).
- They are complementary, **not exact opposites**. A helper used as an
  assumption must be a *checked invariant* (contain `Reach`); abstraction must
  not invalidate a proved helper.

## A3. Failure taxonomy → strategy (operational)

| failure | next action |
|---|---|
| unreachable CTI | S1 (invariant/manifold) |
| representation mismatch | S3 |
| uncovered branch | S2 (case/guard + coverage) |
| cross-component dependency | S2 (assume-guarantee) |
| temporal/transient | S5 |
| wide arithmetic/quantifier | S3 (certificate/purify/index) |
| sampling/quantification error | restate scope/temporal interpretation |
| composition gap | interface lemma (S2/S4) |
| abstraction too coarse / spurious CEX | S4 refine (COI/interpolant) or A0 replay |
| false premise / assumption | A0 replay/PREUNSAT; repair statement |
| real counterexample | stop: property false or target wrong |

Refinement returns to the *relevant* stage, based on the failure type.

## A4. Budgets

Each strategy gets a budget. Do not retry the same query with a larger timeout
without a diagnosis. Portfolio outcomes are normalized to the assurance levels
(§B2).

---

# B. Soundness framework

## B1. Scope

Initial formal guarantee:
- **safety** over `M=(S,I,T)`;
- **partial operation-local functional correctness**: entered under `E`, if the
  operation reaches `X`, the result is correct;
- **total correctness** adds an explicit progress/ranking obligation (and
  fairness where needed). A finite implication DAG does not by itself establish
  termination.

Outside this scope (liveness, hyperproperties, concurrency) requires explicit
additional rules.

## B2. Assurance levels

| status | meaning |
|---|---|
| `PROVED_CHECKED` | a specified, independently checked certificate establishes the obligation |
| `PROVED_TRUSTED` | a trusted engine reports proof under documented semantics |
| `BMC_CLEAN` | no CEX within the bound (diagnostic, not proof) |
| `UNKNOWN` | neither proof nor CEX |
| `COUNTEREXAMPLE` | CEX produced (and replayed/validated) |
| `TCB_ASSUMPTION` | explicit trusted boundary |

A BTOR proof does not establish source-RTL correctness without the RTL→BTOR
link. `BMC_CLEAN`/`UNKNOWN` are never premises for a closed theorem.

## B3. Contracts

Each obligation specifies: `scope`, `assumptions`, `guarantee`,
`temporal interpretation` (current/next/prev/entry/exit/eventually),
`dependencies`, `status`, `provenance` (engine, certificate, model id,
runtime). Every cut or abstraction introduces an obligation.

## B4. Proof-carrying decomposition (PCD) and kernel

A DAG `G=(V,E)`; each node is a lemma with assumptions and a certificate/engine.
The kernel checks:

```
K1 well-formedness (id/role/lemma/scope/assumes/status/engine/model)
K2 local soundness: for supported backends, re-run the check and parse a
   defined result; for independent certificates, check the certificate.
   Unsupported engines may only claim PROVED_TRUSTED.
K3 dependency closure: every assume exists and is discharged (no BMC_CLEAN/
   UNKNOWN/COUNTEREXAMPLE as a premise); allowed same-state simultaneous groups.
K4 abstraction gate (only when S4 used): abstract over-approximates concrete.
K5 coverage: guard partitions exhaustive; init/preservation/entry-exit premises
   present where required.
K6 root composition: the target follows from the discharged nodes at the target
   scope. Only the kernel closes the root.
K7 status/provenance: statuses valid; no upgrades; reuse assumption-match
   recorded; model ids present.
```

The kernel is intentionally smaller than the planner. Independent certificate
checking and temporal proof rules are extensions; the kernel must not claim
more than its checks establish (recording an engine name/log is not independent
validation).

## B5. Reuse rule

A lemma may be reused only if model, width, guards, phase, and transition
relation match, and its assumptions are discharged in the new graph. Similar
structure is a reason to try, not evidence.

---

# C. Automation architecture

- **Planner (LLM):** proposes cuts, contracts/abstractions, obligation kinds,
  engines, and certificate candidates; records reuse decisions. Never closes.
- **Engines:** IC3/k-induction, cheap BMC, theory/algebra, SMT case splits,
  temporal induction, abstraction gate/CEGAR.
- **Kernel:** K1–K7; the only closer.
- **Refinement loop:** structured failures (CTI/CEX/engine status) → planner;
  returns to the relevant layer-A stage.
- **Reporter:** DAG, assurance levels, TCB, runtimes, unresolved obligations.

Evaluation matrix: fixed strategy vs planner (same budget); CIll baseline.
Metrics: closed properties, rejected candidates, unresolved obligations,
planning/engine time, clean-replay success. Measure soundness (bad graphs
rejected), transfer (REM with justified reuse), automation (effort reduction),
as separate outcomes.

---

# D. Development order

1. Freeze the ledger with the six assurance levels (historical markers).
2. **T-E2E**: minimal kernel + MUL/DIV reference graphs; accept valid
   compositions, reject missing assumption / uncovered guard / disconnected
   lemma / status upgrade / unsound abstraction / reuse mismatch.
3. Small CTI/CEX diagnosis case set (failure type → strategy → fix → outcome).
4. REM (non-ALTOPS) held-out transfer, pre-registered; abstraction only if
   needed.
5. Comparative evaluation; then SERV temporal case.
