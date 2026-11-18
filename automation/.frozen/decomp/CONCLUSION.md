# Conclusion — spec-directed proof decomposition (MUL/DIV consolidation)

## Central conclusion

> Iterative RTL verification can be made more tractable by decomposing an
> architectural correctness property into proof obligations aligned with the
> structure of the implementation and the semantics of the operation.
> Reachable-state relations are established by transition-system reasoning;
> arithmetic relations by appropriate algebraic certificates; terminal facts and
> temporal summaries capture completion behavior; and operation-local contracts
> connect these results to architectural observations. In the MUL and DIV cases
> the dominant proof difficulty varied by operation, while the **composition
> discipline** remained reusable.

This claim is made **within the stated trust boundary and methodology** (§5):
focused checks over minimal sandboxes, a trusted frontend, and trusted solver
results. It is not a claim of one certified source-level run.

## Three contributions (in order)

1. **A composition discipline.** Contracts `(A,E,X,T_G,Φ=M∧C∧Σ,ρ,Δ,Post,P)` and
   a dependency graph such that discharged local facts imply the target without
   silently assuming it (SPC; `PROOF_FLOW.md`). The independent certificate
   checker caught a real defect (a missing zero law), demonstrating the value of
   checking the composition rather than the solver's success message.
2. **Semantic lifting through heterogeneous obligations.** Arithmetic
   identities, reachable-state manifolds, terminal/ordering facts, and temporal
   summaries are *not* forced into one bit-level invariant engine. Evidence:
   MUL's purified algebra vs DIV's ordering/case reasoning vs SERV's macro-step.
3. **A path toward automated proof planning (prototype / research direction).**
   The structural decisions (where to cut, which obligation kind, which
   certificate form) were repeatedly the deciding factor and were discovered via
   CTIs, not templates. This motivates an LLM planner over a certifying kernel.
   **This is a hypothesis, not yet an established result.**

## Evidence map

### MUL (`picorv32`, real non-ALTOPS `pcpi_mul`)
- **Operation arithmetic:** purified algebraic certificate (S1/S2), width-
  independent; ring identity checked independently; endpoint by symbolic unroll.
- **Reachable manifold:** 4 facts independently re-proved on the BTOR (S7).
- **RTL↔recurrence:** active-cycle accumulator contract `rd+rdx==plain shift-add`
  is inductive (S27).
- **Observation/data:** O6 L1–L3 proved (S9); operand correspondence and
  destination identity proved in minimal sandboxes (S24).
- **PC:** boundary+stability+RTL latch (S25).
- **Outcome:** `o_rd_wdata_match` and `o_pc_wdata_match` **closed at the
  integration level** (O0 TCB).

### DIV (`picorv32`, real non-ALTOPS `pcpi_div`)
- **Terminal ordering Δ:** manifold, invariant, terminal step, alignment (S13);
  preserved as a *terminal* fact, not a global invariant.
- **Unsigned quotient/remainder theorem:** checked (S13).
- **Signed / exceptional / branch:** sign-adjust via the unsigned interface
  (S15, width-independent); `b=0` and `MININT/-1` distinct (S14); branch
  selection (S16).
- **RTL↔abstract state:** shift-index manifold, update correspondence, loop
  invariant, last premise, terminal ordering — all inductive (S30).
- **Observation / PC / destination / operands:** S17, S26, S24.
- **Outcome:** DIV architectural data and `o_pc_wdata_match` **closed at the
  integration level** (O0 TCB).
- **Limit:** signed DIV at W≥16 is solver-limited; S15's interface proof is the
  width-independent result.

### SERV bit-serial ADD
- **Temporal summary:** macro-step `done ⇒ result=a+b` proved by induction without
  latency unrolling (S5). Demonstrates the *temporal* obligation kind; not a full
  architectural closure.

### REM (`picorv32`, real non-ALTOPS `pcpi_div`, remainder path)
- **Audit finding (2026-10-22):** the earlier REM closure was *not*
  proof-trusted — the recorded step lemma was a tautology
  (`assert(dividend == $past(dividend) || 1'b1)`), and the graph had no
  interface node joining the arithmetic to the RTL. Both are repaired; the
  lesson is that a kernel checking only DAG closure cannot detect a
  semantically inert lemma (hence kernel rule K9).
- **Divider facts (re-proved):** entry values, the real step update, the
  shift-index manifold `divisor==N<<k` / `msk==1<<k`, the invariant, the last
  premise, the terminal bound and the finish-edge stability — **18/18
  inductive** on the isolated divider model (189 s), plus the finish mux
  (quotient vs dividend path, selected by the decode).
- **Bridge (S19):** the aligned trial `D==N*msk` preserves `d+N*q==M` (z3, with
  a *sat* mis-scaled control so the check has teeth); entry+terminal give
  `d==M%N`, `q==M/N`; the writeback value equals the architectural result for
  signed/unsigned REM and DIV, including `rs2==0` and `MININT/-1`.
- **Transfer:** the isolated model contains the identical divider text and
  over-approximates the environment, so its inductive facts hold in the full
  core; recorded per node in `reuse` blocks (kernel K7).
- **Outcome:** the observation facts are L1 (`PROVED_TRUSTED`); `o_rd_wdata_match`
  is closed **at L2 by a checked composition** (S18+S19 artifacts, sha256-bound
  to the graph). It is *not* CIll-inductive and is not claimed to be.

## The methodological finding

The most transferable lesson is not a catalogue of invariants; it is that the
**obligation form is discovered, not templated**:
- finish-only vs active-cycle invariant (MUL accumulator, DIV invariant);
- shadow/ghost vs the RTL's own latch (MUL operands);
- sampling edges (finish-edge vs `pcpi_ready`; `$past` across reset);
- shift-index vs multiply (DIV manifold);
- operation-local minimal sandboxes vs deep CPU-level properties.

In every case the deciding signal was a CIll **CTI/CEX**, used as a *design*
signal (change the form) rather than a timeout to retry.

## What is NOT claimed

- Not a fully certified source-level proof: the Yosys/Slang→BTOR frontend is
  trusted, and solver results are not proof-log checked (L2).
- Not a unified full-checker run: the evidence is focused checks; this is stated
  in every artifact.
- Not general automation: the MUL/DIV decompositions were guided manually; the
  planner is a research direction.
- Not that the DIV/REM roots are inductive: `o_rd_wdata_match` is closed by a
  checked composition of L1 leaves (L2); CIll reports *Not Inductive* on the
  full core and that verdict is not overridden.
- Not that a kernel acceptance is a proof: kernel checks are L3 (structure,
  provenance, artifact binding). A composition is only as strong as its leaves.

## Next research direction (hypothesis)

A planner (LLM) proposes cuts, contract structure, obligation kinds, and
certificate candidates; a **minimal certifying kernel** accepts/rejects each
obligation and the final composition; a refinement loop feeds structured
CTI/CEX/engine failures back. The first clean transfer test is **REM
(non-ALTOPS)**, followed by a SERV temporal case. See `PROOF_FLOW.md` and
`RULEBOOK.md`.
