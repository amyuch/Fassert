# PCD principles

This document states *why* the framework is shaped the way it is; the
operational flow is in [`02-method.md`](02-method.md) and
[`04-workflow.md`](04-workflow.md). Complete acceptance is the default: no
design TCBs, no assumption helpers/cuts, no `OPEN`/`UNKNOWN` premises, and a
`CHECKED` root.

---

## 1. The problem

Given a transition system `M = (S, I, T)` and a target safety property `P` that
is not inductive, find a finite set of discharged obligations whose checked
composition implies `P`, without assuming `P`.

There are two different questions, and they must not be conflated:

- **Soundness / composition.** How do local, checked facts imply `P`? This can
  be made formal and machine-checked. It is the kernel's job.
- **Discovery.** Which cuts, representations, invariants, and certificate forms
  to use. This is search. It is incomplete, budgeted, and belongs to the
  planner.

A PCD implementation is useful only if it keeps these questions separate.

---

## 2. Decomposition

A decomposition is a DAG `G = (V, E)`. Each node is

```
v = (statement, requires, provides, certificate, model)
```

- `requires` names guarantees supplied by other nodes (not merely node ids).
- `provides` names the guarantees this node exports.
- `certificate` is either independently checkable, replay-bound to an engine
  run, or an explicit TCB leaf.
- `model` is an immutable model identity.

The root is the target. The kernel is the only component allowed to close it.

The DAG may contain cycles only for simultaneous invariants at the same state
and phase. A future-state assumption is never allowed.

---

## 3. Principles

### P1. State the theorem and trust boundary first

Freeze the exact target, guards, claim scope (partial/total, leaf/root), model
identity, and TCB before decomposing. No later step may narrow the target to
make it provable.

### P2. Diagnose before decomposing

A CTI or CEX identifies the failure type. Do not retry the same query with a
larger timeout. The failure type selects the tactic.

### P3. Cut at semantic or structural boundaries; every cut is an obligation

Decompose by component, time window, representation, or operation boundary. Each
cut introduces an interface or transfer obligation. A cut is not an assumption.

### P4. Stratify by theory and route each obligation to the right backend

Do not force invariants, arithmetic, temporal facts, and glue into one engine.
The same fact can be easy in one logic and intractable in another. Routing is by
`(role, kind, logic, size)`, never by case name.

### P5. Separate invariant, reachable-only, and transient facts

"True in all reachable states", "true at entry", "true at exit", and "eventually
true" are different obligations. The phase must be explicit.

### P6. Choose the representation where the obligation is easy, and prove the refinement

Purify arithmetic, introduce a symbolic index, use an auxiliary representation,
or abstract a subcomponent. The representation change is itself a checked
obligation, not a syntactic convenience.

### P7. Respect time and quantification

State each lemma at the correct cycle/edge (old vs new values, `$past`
boundaries) and for the correct quantifier (all reachable, at entry, at exit,
eventually). Most "false" lemmas are mis-timed or mis-quantified.

### P8. Compose only checked facts, with explicit coverage

Dependencies, guard partitions, and assumptions must be discharged. The kernel
is the only authority. This is what prevents a decomposition from moving the
difficulty into an unchecked premise.

### P9. Treat non-inductiveness as a design signal

Change the form (invariant vs terminal, ghost vs RTL signal, representation,
cut), not just the budget. A Not-Inductive verdict is evidence about the shape
of the obligation.

### P10. Reuse requires assumption matching

Similar structure is a reason to try, not evidence. Match model, width, guards,
phase, and transition relation; discharge the reused lemma's assumptions at the
new interface; make the transfer an explicit obligation.

### P11. Report evidence and composition separately

An engine verdict, an independently checked certificate, and a structural DAG
acceptance are different things. A root claim is a pair
`(leaf evidence, composition mode)`, computed from the DAG, never asserted.

### P12. Planner proposes, kernel disposes; search under budget

The planner may propose cuts, obligations, certificate forms, engines, and
reuse. It never writes a status. Discovery is bounded; every run records its
budget and the reason it stopped.

### P13. Blind evaluation for planner claims

If the claim is about planning ability, the planner must not see prior
decompositions, helper contracts, or proof graphs. The harness enforces this by
filesystem isolation, a hashed context, frozen proposals, and a leakage audit.
Development runs may use the oracle; they are marked `dev` and are not results.

### P14. Artifacts are immutable and replayable

Every engine verdict is bound to a model hash, command, tool version, and log
hash. Every certificate is bound to an artifact hash. Replay is a separate
operation that refreshes `REPLAY` evidence; it never silently upgrades a claim.

### P15. The framework is case-agnostic

Cases are data. No framework source may contain a case name or a case-specific
condition. A new case should be addable without changing `pcd/`; a new
obligation kind should be addable as a plugin plus tests.

### P16. A helper that proves nothing is not a lemma

A recorded lemma must constrain the state. A tautology, a
satisfiable-but-never-constraining assertion, or an assertion not reachable from
the graph discharges nothing. Non-vacuity is checked where the certificate
language permits; regex hygiene is only a fallback.

---

## 4. Formal vs heuristic

**Formalizable, sound, domain-independent:**

- PCD soundness and the kernel rules.
- Per-format certificate checking.
- Guarantee matching and coverage conditions.
- The evidence/composition lattice.
- Run provenance and replay identity.

**Heuristic, incomplete, research:**

- Choosing the cut and representation.
- Synthesizing invariants and lemmas.
- Routing to engines.
- Reuse decisions.
- Budget/portfolio policy.
- Planner proposals.

**Not formal without extra work:**

- Model ↔ RTL equivalence (front-end or miter).
- Solver proof-log validation.
- Full source-level semantics of the spec.

---

## 5. Evidence and hypothesis

Every rule or claim in the framework carries one of:

| tag | meaning |
|---|---|
| `[P]` | principle or design invariant; enforced by the kernel/protocol |
| `[H]` | hypothesis about automation, generality, or transfer; needs an experiment |

A prior result re-enters the flow only as `REPLAY` (if replayable), `CHECKED`
(if a checker exists), or `UNREPRODUCED`.

---

## 6. Non-goals

- Not a new decision procedure.
- Not a guarantee that every obligation is independently checkable.
- Not liveness, hyperproperties, concurrency, multi-clock, or full
  source-to-gate equivalence.
- Not a case-specific collection of scripts.
- Not a replacement for a case's oracle material.
