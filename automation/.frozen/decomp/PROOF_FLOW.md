# Proof flow — spec-directed decomposition (stable method)

This is the reusable flow. It is a **planning + checking** discipline, not a
mandatory template: the planner chooses which obligations exist and how they
depend. Each step names its output and its acceptance check, so the hand-off is
machine-checkable.

## Step 0 — Target and trust boundary

Inputs: original assertion, spec semantics, reset assumptions, configuration,
source/model relationship.

Outputs:
- frozen target theorem (exact guards, e.g. `!reset && check && spec_valid ∧
  pc_valid ∧ ¬mem_fault ∧ ¬spec_trap`);
- model identity (BTOR sha256) and TCB statement (frontend, solvers);
- the claim level (partial vs total; operation vs architectural).

Acceptance: the target and its guards are fixed and recorded; no later step may
narrow them.

## Step 1 — Extract the operation and boundaries

Find: entry `E`, exit/termination `X` (distinct from the loop guard), internal
recurrence, live-in operands, internal state, and the architectural observation
point.

Outputs: operation-local transition model; candidate cut points; captured-input
shadows (e.g. `N=|b|`, `h_k` shift index) if needed.

Acceptance: `E`, `X`, the recurrence, and the observation point are stated over
real RTL signals with sampling edges (old vs new nonblocking values).

## Step 2 — Build the obligation dependency graph

Classify each obligation by **role/kind** and state its dependencies:

| role | example |
|---|---|
| reachable manifold | `msk==1<<h_k`, `divisor==N<<h_k`; `rd+rdx==acc` |
| update correspondence | `dividend' = dividend − (s≤d ? s : 0)` |
| algebraic certificate | `rs1·rs2 = t + 2·M(x,rs2)`; ring identity |
| terminal / ordering | `Term ⇒ dividend<N`; `s=N` premise |
| temporal summary | macro-step `done ⇒ result=a+b` |
| result selection | finish mux quotient vs dividend |
| operand identity | `rvfi_rs* == pcpi_rs*` at retirement |
| architectural observation | `pcpi_rd` → writeback → RVFI |
| RTL↔model link | operation state ⇔ abstract recurrence state |

Output: proof DAG (see schema), candidate contracts, explicit **unresolved
edges**.

Acceptance: every node has a role/kind, assumptions, and a proposed engine or
certificate form. Cyclic *same-state* dependencies among invariant conjuncts are
allowed (simultaneous induction); future-state assumptions are not.

## Step 3 — Propose and discharge local obligations

Discharge in this order (skip what is trivial):
1. reachability/manifold and update relations (transition reasoning);
2. semantic recurrence / arithmetic certificate (poly/word-level);
3. terminal facts, progress, temporal summary;
4. result selection, operand identity, architectural observation.

Output: individually checked lemmas with assumptions and evidence.

Acceptance: each certificate establishes its exact lemma under its stated
assumptions; BMC-clean is recorded as "not proved"; timeouts are not
counterexamples.

## Step 4 — Check composition and coverage

Check that the discharged lemmas imply the target:
- entry `A ∧ E ⇒ Φ`;
- preservation per guard class, with `T_enabled ⇒ ⋁_g T_g`;
- terminal `Φ ∧ X ∧ Δ ⇒ Post` (Δ proved, not assumed);
- observation `Post @ X ⇒ P @ observation`;
- dependency closure; every assumption discharged.

Output: a checked proof package, or a precise list of open obligations.

Acceptance (**kernel rules**, minimal trusted core):
1. artifact well-formedness (id, role, lemma, assumes, certificate, engine,
   model hash);
2. per-backend certificate establishes the lemma under the assumptions;
3. rule composition: antecedents/consequents match the contract; guard coverage
   holds; `A` discharged by the enclosing contract; `Δ` proved;
4. dependency closure; no unverified assumption; the target depends only on
   discharged nodes;
5. (K7, extended) a node proved on a non-primary model carries a `reuse` block
   whose `source_model` is that model and whose `assumption_match` records the
   matched dimensions (`model/width/guards/phase/transition`);
6. (K8) a target closed by composition binds the artifact of that composition
   run by sha256;
7. (K9) committed helper sources contain no tautological assertion — a neutered
   helper may not be recorded as a proved lemma.

Rules 5–7 were added after the 2026-10-22 audit, which found that the earlier
REM closure was accepted by the structural rules while resting on a vacuous
helper and on an abstract arithmetic lemma with no interface node.

The kernel is the **only** component allowed to declare a theorem closed. The
planner never does.

## Step 5 — Reproduce and report

Replay from a clean environment; validate artifact identities; record tool
versions/runtimes; report the theorem proved AND the remaining TCB.

Output: reproducible evidence (ledger + commands), not an interactive session.

## Contract (SPC) — the composition rule

```
C = (A, E, X, T_G, Φ=M∧C_rec∧Σ, ρ, Δ, Post, P)

O0 rtl_link     : T_G faithfully represents the RTL (frontend TCB / miter)
O1 entry        : A ∧ E            ⇒ Φ
O2 preservation : Φ ∧ T_g ∧ ¬X     ⇒ Φ'     for every guard g;
                  guard coverage: T_enabled ⇒ ⋁_g T_g
O3 progress     : (optional) well-founded ρ decreases on progress transitions
O4 finalization : Φ ∧ X ∧ Δ        ⇒ Post
O5 terminal     : Φ ∧ X            ⇒ Δ      (Δ may be a nested SPC lemma)
O6 observable   : Post @ X (checked latency/boundary) ⇒ P @ observation
O7 non-interf.  : (when needed) no conflicting operation interleaves
```

Partial correctness drops O3. `O5`/`O6` may be nested SPC instances; the rule is
closed under nesting.

## Obligation schema (machine-readable)

```json
{
  "id": "div_loop_invariant",
  "role": "manifold|update|algebra|terminal|temporal|select|operand|observe|rtl_link|compose",
  "kind": "inductive|poly|linear|guarded|ordering|macro_step|tcb",
  "lemma": "<SMT-LIB/internal expression>",
  "assumes": ["node_id", "..."],
  "certificate": {"format": "poly-identity|inductive-invariant|case-split|macro-step|linear-combo|tcb", "payload": "..."},
  "engine": "ric3-ic3|cil|z3|poly|...",
  "model_hash": "sha256:...",
  "result": "proved|bmc-clean|open|solver-limited|tcb",
  "evidence": "log path / runtime / command"
}
```

## Planner / engines / kernel roles

- **Planner (LLM):** proposes cuts, contract structure, roles/kinds, engines,
  and certificate candidates; may reuse prior lemmas only with explicit
  assumption matching. It never marks anything closed.
- **Engines:** transition invariants (IC3/CIll), algebra (poly/word-level),
  case splits/ordering (SMT), temporal summaries (induction).
- **Kernel:** validates artifacts, dependencies, guard coverage, and the final
  implication.
- **Refinement loop:** engine/CTI/CEX failures return to the planner as
  structured diagnostics (which lemma, which assumption, which stage).

## Worked DAGs

MUL:
```
manifold (S7) ─┬─> consecution ─┐
ring (S1/S2) ──┘                ├─> O4 finalization ─> observation (L1-L3) ─> P
endpoint (S1) ──────────────────┘         ▲
accumulator contract (S27) ───────────────┤
L4 dest identity + M2 operands (S24) ─────┘
PC boundary+stability (S25) ─> P_pc
```

DIV:
```
loop-state/update (S30) ─> loop invariant (S30) ─> last premise ─> terminal Δ (S13/S30)
terminal Δ + quotient theorem (S13) ─> finish mux (S28) ─> observation (S17) ─> P
signed interface (S15) + exceptional (S14) + branch (S16) ─┘
L4/M2 (S24) + PC (S26) ─> architectural links
```

## Failure handling

- Not inductive → select CTI; decide whether the **form** is wrong (finish-only
  vs active-cycle; shadow vs RTL latch; wrong sampling edge) or a supporting
  fact is missing.
- CEX → inspect the exact transition; never narrow the boundary to discard it.
- Timeout/UNKNOWN → not a counterexample; try a smaller/operation-local model or
  a better abstraction before increasing budgets.
