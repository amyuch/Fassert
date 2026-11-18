# General rules for decomposing non-inductive properties

Scope: **any** transition system `M=(S,I,T)` and a target property `P` that is
not inductive. It is not specific to arithmetic, instructions, or PicoRV32.
MUL/DIV/SERV are *instantiations*, cited only as evidence.

## 1. The general problem

`P` is non-inductive: there are CTIs (states satisfying the helpers/P but with a
successor violating P). The job is to find a finite set of **discharged
obligations** whose checked composition implies `P`, without assuming `P`.

Two distinct questions:
- **Soundness/composition:** how do local, checked facts imply `P`? This can be
  made formal and machine-checked.
- **Discovery:** which cuts, representations, and lemmas to use. This is search;
  it is not complete, and is where heuristics/LLM/CEGIS live.

## 2. The formal core: proof-carrying decomposition (PCD)

A decomposition is a DAG `G=(V,E)` where each node `v` is

```
v = (lemma_v, assumes_v, kind_v, certificate_v, engine_v, model_id)
```

and `E` records which obligations are *assumed* by which. The root is `P`.
The kernel checks:

```
(K1) well-formedness: lemma/certificate/engine/model id present
(K2) local soundness: certificate_v establishes lemma_v under assumes_v
(K3) dependency closure: every assume is discharged (or is an explicit TCB leaf)
(K4) composition: the root implication follows from the discharged nodes
(K5) coverage: where the rule requires a case split / guard partition, it is
     exhaustive; initialization/preservation premises are present
```

If K1–K5 hold, `M ⊨ P` relative to the TCB (model link, solver soundness, or
checked proof logs). **This is the formal flow.** It is domain-independent; only
K2's backends change.

Permitted cycles: simultaneous inductive invariants may depend on each other at
the *same* state (conjunction-of-invariants); no future-state assumptions.

## 3. Why a property is non-inductive (failure taxonomy → tactic)

Diagnose the CTI/CEX first; the failure type determines the decomposition.

| Failure type | Symptom | General tactic |
|---|---|---|
| **Unreachable CTI** | CTI uses a state not reachable from `I` | invariant strengthening / reachability manifold (IC3, CHC, Houdini/ICE) |
| **Representation mismatch** | true but hard/unnatural in current logic | change representation + refinement (abstract/word-level/purify/index) |
| **Uncovered case/branch** | CTI takes an unprotected control path | case/guard decomposition; coverage obligation |
| **Cross-component dependency** | local facts need a neighbor's guarantee | assume-guarantee / compositional contracts |
| **Temporal/transient** | fact holds only at exit/eventually, not throughout | temporal decomposition: terminal facts, ranking, macro-step |
| **Wide arithmetic/quantifier** | bit-blasting/quantifier blowup | theory certificate (poly, IA), purification, symbolic index |
| **Sampling/quantification error** | wrong cycle/edge/quantifier in the statement | restate lemma at the correct time/quantification |
| **Composition gap** | local proofs exist but do not imply P | add the interface/observation lemma; check dependencies/coverage |

MUL: wide arithmetic → certificate; reachable carry-save → manifold.
DIV: terminal ordering → temporal/terminal; wide multiply → shift index;
signed/exceptional → case decomposition.
SERV: long temporal chain → macro-step summary.

## 4. General flow

0. **Formalize**: target `P` + guards, model id, claim level, TCB.
1. **Diagnose**: obtain CTI/CEX; classify by §3; record the relevant state/
   transition and the missing support.
2. **Choose strategy + cut**: pick from §3; choose a cut (component/time/
   representation) that makes the residual obligation easy. Every cut is an
   interface obligation, not an assumption.
3. **Propose obligations**: assign roles/kinds, assumptions, candidate
   certificates, engines (see §5).
4. **Discharge**: check each obligation with the right backend; keep
   "checked" vs "BMC-clean" vs "unknown" distinct.
5. **Compose**: run K1–K5; reject open dependencies.
6. **Refine**: feed structured failures (CTI/CEX/engine) back to step 2/3;
   iterate within a budget.
7. **Report**: theorem, TCB, statuses, rejected candidates, replay evidence.

## 5. Obligation roles (general)

| role | meaning | typical backend |
|---|---|---|
| reachability/invariant | over-approx of reachable states; inductive | IC3/PDR/k-induction, CHC/ICE/Houdini |
| refinement/representation | relate concrete and abstract state; lift `P` | miter/equivalence, SMT, simulation relation |
| functional/spec correspondence | implementation's computation matches the spec function | SMT (BV/IA/arrays), algebraic/poly, recurrence induction |
| temporal/summary | entry→exit relation, macro-step, eventual/terminal | temporal induction, acceleration, ranking |
| interface/glue | observation, assume-guarantee, non-interference | SMT, checked implication |
| composition/coverage | guard partition, dependency closure | kernel + SMT |

## 6. General rules

Tags: **[E]** evidence-backed (in this project or standard practice);
**[H]** hypothesis in need of experiment.

**R-G1. State the theorem and trust boundary first — [E]**
Freeze the exact property, guards, model identity, claim level. Never let a
later translation narrow it.

**R-G2. Diagnose before decomposing — [E]**
A CTI/CEX tells you *which* failure type you have. Do not retry the same query
with a bigger timeout.

**R-G3. Cut at semantic/structural boundaries; every cut is a checked interface — [E]**
Decompose into components/time-windows/representations. Each cut introduces an
assume-guarantee obligation; a cut is not an assumption.

**R-G4. Stratify by theory and route each obligation to the right engine — [E]**
Do not force invariants, arithmetic, temporal facts, and glue into one engine.
The same fact can be easy in one logic and intractable in another.

**R-G5. Separate invariant facts from reachable-only and transient facts — [E]**
"True in all reachable states", "true at exit", and "eventually true" are
different obligations. Supply the reachability/phase support explicitly.

**R-G6. Choose the representation where the obligation is easy, and prove the refinement — [E]**
Purify arithmetic; introduce a symbolic index instead of unrolling; use an
auxiliary representation (carry-save↔plain); abstract a subcomponent. The
representation change is itself a checked obligation.

**R-G7. Respect time and quantification — [E]**
State each lemma at the correct cycle/edge (old vs new values, `$past`
boundaries) and for the correct quantifier (all reachable / at entry / at exit /
eventually). Most "false" lemmas are mis-timed or mis-quantified.

**R-G8. Compose only checked facts, with explicit coverage — [E]**
Dependencies, guard partitions, and assumptions must be discharged; the kernel is
the only authority. This is what prevents a decomposition from "moving the
difficulty" or hiding it.

**R-G9. Treat non-inductiveness as a design signal — [E]**
Change the form (invariant vs terminal, shadow vs RTL signal, representation,
cut), not just the budget.

**R-G10. Reuse requires assumption matching — [E]/[H]**
Similar structure is a reason to try, not evidence. Match model, width, guards,
transition relation, and discharge the reused lemma's assumptions. *[H]: fully
systematic reuse decisions.*

**R-G11. Report status honestly — [E]**
`proved` / `BMC-clean` / `unknown` / `CEX` / `TCB` are different. A hash is
identity, not equivalence; a timeout is neither proof nor counterexample.

**R-G12. Planner proposes, kernel disposes; search under budget — [H]**
Discovery (cuts, representations, lemmas) can be LLM/CEGIS-driven; soundness
cannot. The loop is propose→check→diagnose→refine.

## 7. Formal vs heuristic

**Formalizable (sound, domain-independent):**
- PCD soundness and K1–K5.
- Per-backend certificate checking (if the backend's acceptance rule is defined).
- Coverage/dependency conditions.
- Status taxonomy.

**Heuristic/incomplete (research):**
- Choosing the cut and representation.
- Synthesizing the invariant/lemma (ICE/CHC/SyGuS are sound only when the
  candidate is given; completeness is not guaranteed).
- Routing to engines.
- Reuse decisions.
- Budget/portfolio policy.

**Not formal without extra work:**
- Model↔RTL equivalence (frontend or miter obligation).
- Solver proof-log validation (DRAT/LRAT etc.).

## 8. Tooling worth building (general)

| tool | purpose | input → output | status |
|---|---|---|---|
| **T1 Diagnoser** | classify CTI/CEX by failure type | trace + obligations → failure class + relevant state/transition | prototype (manual CTI reading) |
| **T2 Obligation schema + proof-graph store** | machine-readable contracts/DAG | obligations → schema/DAG | started (`PROOF_FLOW.md`) |
| **T3 Kernel** | K1–K5; only closer of theorems | DAG + artifacts → accepted/rejected | prototype (scripts) |
| **T4 Engine router** | map role/kind → backend + certificate format | obligation → engine | hand-written router (S6) |
| **T5 Representation synthesizer** | purification, indexing, abstraction, ghosts | recurrence/spec → candidate representation + refinement obligation | manual; automatable |
| **T6 Cut finder** | dependency slicing, loop/counter detection, boundary inference | RTL + spec → cut candidates | manual; automatable |
| **T7 Invariant synthesizer** | ICE/CHC/Houdini/SyGuS candidates | transition + CTIs → candidate invariants | not built |
| **T8 CTI-guided refiner** | turn failures into form changes | CTI + graph → suggested edits | manual; automatable |
| **T9 Certificate checkers** | independent poly/BV/induction/temporal checkers; later proof logs | certificate → accept/reject | poly checker built (S2) |
| **T10 Portfolio harness** | budgets, parallel engines, normalized statuses, replay | case manifest → report | partial (`reproduce.sh`) |

The highest-leverage are T2/T3 (make composition real), T1/T8 (make the CTI a
design signal), and T5/T6 (automate the choices that decided MUL/DIV). T7 is
valuable but orthogonal; T9 (proof logs) is a separate certification effort.

## 9. Relationship to prior methods

PCD is a *proof-engineering* wrapper, not a new decision procedure. It borrows
from IC3/PDR, CEGAR/datapath abstraction, CHC/ICE, SyGuS, assume-guarantee, and
temporal summarization. The intended distinction is:
- **spec-directed** cutting and representation choice from (RTL, spec);
- an **explicit, checked composition** of heterogeneous certificates;
- **CTI-driven obligation-form refinement**;
- honest status/TCB discipline.

None of these individually is novel; the combination and the empirical
failure-mode map are the contribution to test.

## 10. Open questions / evaluation

- Does the failure-type taxonomy predict the right tactic on new cases?
- Can cut/representation choice be automated (T5/T6) enough to beat a fixed
  router, with the kernel unchanged?
- Does REM transfer validate reuse-with-assumption-matching (R-G10)?
- Does a SERV temporal case validate the temporal role and R-G5/R-G7?
- Can proof-log checking (T9/L2) be added without redesigning the kernel?
- Does the planner reduce effort vs the fixed router under an identical budget?
