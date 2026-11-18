# Judgement.md - Quick Acceleration Strategy Decision

This document summarizes static heuristics for deciding between monolithic IC3/PDR, CIll-style helper lemmas, and NeuroAbs/ILA abstractions. It also gives concrete formulas and notes on which signals are cheaply computable with rIC3/Z3.

## TL;DR
- **COI is not enough.** A small COI can still be intractable if the invariant complexity or temporal depth is high. A large COI can be tractable if it is easily decomposable.
- **Helpers and abstractions are cuts, not complexity reducers.** They only pay off if they create a narrow, cheap to justify cut that removes the *actual* bottleneck.
- **Evaluate statically.** Don't wait for a timeout to decide. Estimate the cost of the split before running the prover.
- **Decidability != feasibility.** For finite state BTOR2 safety properties, an answer always exists with unlimited time. However, the proof can be astronomically large, require exponential memory, or be bottlenecked by an incomplete refinement loop.

## Mathematical Conclusion: Why These Metrics Dominate

Let the concrete transition system be \(S\) with latch set \(L\), transition \(\delta\), bad \(B\). Let \(T\) be the time to prove safety of \(B\) by IC3/PDR (up to solver constants).

IC3 builds an inductive invariant \(I\) with \(Init \subseteq I\), \(I \wedge T \implies I'\), \(I \cap Bad = \emptyset\). The work is dominated by:
- **SAT query cost**: each frame/query is solved over the unrolled/relational formula restricted to the cone of influence of \(B, I\)-clauses, and constraints. Bit-blasting COI gives \(W_{COI} \propto |\text{AIG/CNF of } (T|_{COI} \wedge \neg B)\)| (clause/variable counts, depth, reconvergence). This is exponential in the worst case but in practice tracks query difficulty well.
- **Number of frames/depth**: IC3 often needs depth \(D_{seq}\) related to the "induction depth" of the necessary invariant. This grows with counter-like behavior, long chains, and deep ILA histories. Each additional frame multiplies queries and can require stronger generalization.
- **Invariant complexity / generalization**: The minimal inductive invariant can be large (exponential in state bits in the worst case). The number of PDR queries and the cost of clause generalization scale with the *semantic complexity* \(I_{prop}\) of the miter (arithmetic width, muxes, case splits, frame conditions). Two properties with identical COI can demand invariants of very different size/shape.

For a helper lemma \(H\) splitting the proof \(P \implies H \implies Bad\), let \(S\) be the separator/interface between the subgraph proving \(H\) and the residual. Then
$$
C_{monolithic}(P) \gtrsim f(W_{COI}(P), D_{seq}(P), I_{prop}(P)), \quad
C_{helper}(P,H) = C_{lemma}(H) + C_{residual}(P\mid H) + C_{interface}(S) + C_{refine}.
$$
This is analogous to graph/circuit cutting: total cost is roughly (cost of left) + (cost of right) + (interface cost). A helper pays off iff it finds a cut with \(C_{helper} < C_{monolithic}\).

**Key consequence:** \(W_{COI}, D_{seq}, I_{prop}\) dominate because they capture (1) per-query formula size, (2) temporal depth/frames, and (3) the invariant search space. Interface width \(C_{interface}\) appears explicitly in the split cost and is often the deciding factor when invariants remain coupled across the cut.

## When To Use Which Strategy

| Strategy | When It Will Help | When It Will Fail | Static Signals To Look For |
| :-- | :-- | :-- | :-- |
| **CIll-style helper lemmas** | The property factors across pipeline stages with a small interface (e.g PC, ALU result, register write data). The helper is local and inductive. | The property requires a global frame condition, couples operands and PC, or relies on signed comparisons/overflow. The helper ends up just as hard to prove as the original property. | Small interface width, \(C_{lemma} \ll C_{monolithic}\), high separability of the miter, and a residual with a drastically simpler invariant. |
| **NeuroAbs/ILA Abstractions** | Short ILA history relative to what's needed, a narrow interface between ILA and RTL, and the abstraction is precise for the property. | Very long temporal history (e.g Flute), wide interfaces, constant refinement adding RTL details back, or the hard relation lives below the ILA. | ILA depth, ratio of ILA state to RTL COI state, interface width, and projected refinement cost. |
| **Monolithic IC3** | No narrow separator exists, the invariant is global but the COI is small, or any cut would create an interface that is wider than the problem itself. | Large COI, long recurrence depth, and a complex property miter with no obvious decomposition. | No good cut found via graph analysis, \(E \le 1\) for all proposed splits, and high \(I_{prop}\) with no modularity. |

## Static Evaluation Metrics

Use the cost model below to compute a score before execution. All of these can be computed from the COI, bit-blasted circuit, and property miter.

| Term | What To Measure | How To Compute Statically |
| :-- | :-- | :-- |
| $W_{COI}$ | Size of the proof object per query | Bit-blasted AIG/CNF size, clause count, clause length distribution, fanout, depth, reconvergence. |
| $D_{seq}$ | Temporal hardness | Latch dependency SCCs, largest SCC size, counter detection, reset->property distance, ILA history depth, fraction of state in cycles. |
| $I_{prop}$ | Invariant complexity | Property miter op-mix (add/sub/mul/comparators), mux count, case splits, frame condition width, number of unconstrained symbolic inputs, DNF size of the bad. |
| $C_{cut}$ | Cost of decomposition | For a proposed helper/abstraction, compute $C_{lemma}$, $C_{residual}$, $C_{interface}$ (separator width), and estimated $C_{refine}$ (spurious CEX density). |

### Formulas To Use

- **Estimated monolithic cost:**
  $$
  C_{monolithic} \approx W_{COI} \times (1 + D_{seq}) \times (1 + I_{prop})
  $$

- **Estimated cost with a helper/abstraction:**
  $$
  C_{helper} \approx C_{lemma} + C_{residual} + C_{interface} + C_{refine}
  $$

- **Effectiveness:**
  $$
  E = \frac{C_{monolithic}}{C_{helper}}
  $$
  - $E \gg 1$: Strong candidate, should accelerate.
  - $E \approx 1$: Neutral, likely overhead.
  - $E < 1$: Overhead, avoid. Try a different cut or go monolithic.

## Quick Decision Checklist

Before committing to a long run, verify the following:

- [ ] **Find the bottleneck:** Is the case hard due to width ($W_{COI}$), depth ($D_{seq}$), or invariant complexity ($I_{prop}$)? Your split *must* target this, not a different dimension.
- [ ] **Check for a separator:** Is there a cut with a small interface? If the graph is highly connected with no narrow separator, decomposition is unlikely to work.
- [ ] **Prove the lemma cheaply:** Estimate $C_{lemma}$, if it's comparable to $C_{monolithic}$, drop it. A helper that needs its own global invariant is not a win.
- [ ] **Inspect the residual:** After assuming the helper, does $C_{residual}$ drop in the dominant term? The picorv32 sweep is a perfect example of this, if invariant complexity stays the same, time will too.
- [ ] **Account for refinement:** For abstractions, estimate how much of the RTL will be pulled back on average. If refinement converges to the concrete model, $C_{refine}$ will dominate.
- [ ] **Calibrate to the family:** Never use a global threshold. Calibrate $E$ against solved cases within the same family (e.g RVFI vs ILA) using leave-one-design-out. Timeout cases should be treated as censored data, not just large times.

## Can These Be Computed Statically and Quickly With rIC3 or Z3?

Short answer: **Partly.** Many terms are cheap from BTOR2 + rIC3's existing passes; others need small custom extraction; a few are hard to estimate perfectly without solving.

| Metric | rIC3 | Z3 | Feasibility | Notes |
| :-- | :-- | :-- | :-- | :-- |
| COI registers/bits (word-level) | **Yes** - `coi_dump` uses `WlTransys::coi_refine` (same as `ric3 check`) | Possible via term traversal, but easier to use rIC3's frontend | **Trivial (seconds)** | We already have this. |
| Bit-blasted AIG/CNF size ($W_{COI}$) | **Yes** - rIC3 does bitblast + lower to CNF (`bitblast_to_ts`). Can dump CNF/AIG or count clauses/vars. | Can do bitblasting/encode, but rIC3's pipeline is closer to the actual prover | **Cheap (seconds)** | Best to measure on the COI-restricted bitblasted system (same as what the solver sees). |
| Latch dep graph, SCCs, counters ($D_{seq}$) | **Yes** - traverse `next`, `init` on word/bit level. Can do on `WlTransys` before/after COI. | Easy on parsed BTOR2/terms | **Trivial** | Counters are pattern matches on `next = latch ± const/ite`. |
| Reset->bad distance / recurrence depth | **Yes** - BMC-like unrolling up to small bound or reachability in latch graph (structural). | Possible with small unrolls or just graph distance | **Trivial** | Structural upper bound; actual induction depth may differ. |
| Property miter op-mix, muxes, case splits ($I_{prop}$) | **Yes** - walk bad/constraints in COI (term DAG) and count ops by sort/width. | Can do on terms/AST | **Trivial** | This is a big missing piece for the picorv32 instruction sweep. |
| Separator/interface width / cut discovery | **Partly** - can use latch dep graph + min-cut (Stoer–Wagner/MaxFlow). rIC3 doesn't expose this directly. | Possible, but overkill. Use networkx/igraph or simple flow on small graphs | **Cheap for typical designs** | Graph is on latches/registers (often 10^2 - 10^4 nodes); max flow is fast enough. |
| $C_{lemma}, C_{residual}$ for a proposed helper | **Yes** - clone COI, add helper as assumption/constraint or split into two problems, run `coi_dump`/bitblast stats on each. | Can encode, but need to match rIC3's model | **Cheap if few candidates** | This is the most accurate static split estimate. |
| $C_{refine}$ / spurious CEX density (abstractions) | **Hard** - needs CEGAR simulation. Can approximate with random/symbolic simulation over abstract model vs concrete COI cone, or count must-be-precise bits | Can do bounded sim, but imprecise | **Moderately expensive / approximate** | Static approximation is rough; best is a quick BMC sweep on the abstract model to find how many CEXs go spurious. |
| Minimal inductive invariant size | **Impossible statically** - undecidable in general to predict; only bounds/exponential | Not feasible | **Not possible** | The whole point: predict difficulty, not the invariant itself. |

**Pragmatic plan:** use `coi_dump` for COI + register lists/groups, add a small script to extract $W_{COI}$ (AIG/CNF counts) from rIC3's bitblast or by running rIC3 with tracing, compute $D_{seq}$/$I_{prop}$ from the term DAG/BTOR2, do graph cuts to get separator width, and estimate $E$ per proposed split. For the cill/picorv32 cases, $I_{prop}$ (op-mix + frame condition width) is likely the key to explaining the time spread despite identical COI.

## Important Notes About Termination

- **Semantically decidable:** For fixed-width BTOR2 (finite state safety), every property has a definitive pass or fail. With unlimited time and a sound, complete procedure (e.g a correct implementation of IC3/PDR), it *will* terminate.
- **Practically infeasible:** Unlimited time does not imply unlimited memory, and the shortest proof can be exponential in state bits. This is why we need to predict difficulty, not just decidability.
- **Not all tools are complete:** BMC-only, unsound preprocessing, incomplete abstractions with no fair refinement, or helpers that are assumed and not proven can all fail to terminate even for finite state safety properties.
- **Liveness is different:** IC3 is not complete for liveness/LTL, so the "always pass/fail" guarantee only applies to safety properties in these benchmarks.

**Rule of thumb:** Treat acceleration as *proof splitting optimization*, not *problem simplification*. If you cannot statically find a better cut than the original problem, going monolithic is the correct and often faster choice.
