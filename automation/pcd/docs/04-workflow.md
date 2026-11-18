# PCD workflow

The checker path supports model-bound SMT predicates and explicit constraint
discharge ([`10-solver-bridge.md`](10-solver-bridge.md)). The primary-model
planner/discharge seam can construct `btor-smt` obligations; multi-model
packages use construction scripts and the same offline kernel. Bridge-solver
query time is recorded separately from hardware-engine time, and checker-only
e2e runs do not claim a hardware-engine call.

Complete acceptance is the default: a target must have a `CHECKED` root, no
direct target TCB, and only official `frontend`/`engine`/`checker`/`isa_model`
TCBs deeper in the graph. Design TCBs, assumption helpers/cuts,
`OPEN`/`UNKNOWN`/`BMC_CLEAN`, and `STRUCTURAL` roots are rejected.

---

## 1. Three layers, one authority boundary

- **A. Construction** — diagnose, propose cuts/obligations/certificates, select
  engines, reuse. Heuristic, incomplete, budgeted. May be manual, template, or
  LLM.
- **B. Validation** — certificate checkers, replay binding, kernel rules,
  composition. Formal and offline.
- **C. Orchestration** — build models, stage cases, run engines, capture
  artifacts, report, replay, audit.

Only **B** may close a target. **A** never writes a status. **C** moves data and
records what happened.

```
case package
   │
   ▼
[build] ──► model (hash) ──► [sketch] ──► context
                                            │
                                            ▼
                                         [planner] ──► proposals (frozen)
                                            │
                                            ▼
[discharge] ──► engines/checkers ──► obligations + evidence
                                            │
                                            ▼
[check] ──► kernel K1–K13 ──► ACCEPT / REJECT + computed levels
                                            │
                                            ▼
[report] / [replay] / [audit]
```

---

## 2. Assurance levels

### 2.1 Leaf evidence

| value | meaning | who can produce it |
|---|---|---|
| `TCB` | explicit trusted boundary | declaration only |
| `REPLAY` | engine verdict bound to model+command+tool+log and deterministically replayable | runner/backend |
| `CHECKED` | independent checker validated a certificate for the exact obligation | checker |

Engine verdicts (`proved`, `bmc_clean`, `unknown`, `cex`, `error`) are recorded
separately. `BMC_CLEAN`, `UNKNOWN`, and `CEX` are never premises.

### 2.2 Composition

| value | meaning |
|---|---|
| `STRUCTURAL` | DAG closure, coverage, provenance, and guarantee-name matching only; not a complete root |
| `CHECKED` | the root implication is checked over the named guarantees |

### 2.3 Claim

A root claim is `(minimum leaf evidence, composition)`.

- A required node that is `TCB` must be listed in the target's `tcb` and is
  reported, not silently absorbed.
- A node proved on a non-primary model needs a checked `transfer` node.
- A complete root requires `CHECKED` composition.

The reporter computes the level. A human or planner cannot set it.

---

## 3. Run modes and anti-cheat

Case policy is one of:

| mode | oracle access | counts as a planner result? |
|---|---|---|
| `dev` | allowed | no |
| `blind` | forbidden | yes, if the audit passes |

A run whose audit fails is `invalid` and counts as no result.

A blind run:

1. stages only `cases/<case>/input/` and `build/` (no `oracle/`);
2. hashes the planner context before any engine call;
3. freezes and hashes the proposals before discharge;
4. runs build/planner/engine subprocesses under `bwrap` with the workspace and
   `/tmp` hidden and only the current run directory bound read-write; the audit
   checks the recorded `sandboxed` bit on the build and every engine call;
5. has no human edit/hint between context and verdict;
6. is scanned for oracle identifiers in context and proposals;
7. binds the proof to the frozen proposals and checks the planner against
   `run_policy.planner` when the case declares one;
8. is reported with mode, audit result, and run id.

Blind build, planner, and engine processes are also isolated at the OS level
with `bwrap`. The wrapper hides the workspace (including source cases, `oracle/`,
and prior runs) and `/tmp`, then binds only the current run directory
read-write. The LLM planner receives network access; build and engine
processes do not. If the case requests a blind run and `bwrap` is unavailable,
the pipeline fails closed rather than silently running unsandboxed. This is a
strong local isolation layer, not a substitute for a container or separate
account when the threat model includes a hostile kernel or compromised bwrap.

Planner proposals also do not carry executable authority. They select an engine
and backend from the trusted catalog frozen into the context; the runner
resolves the command. A proposal-supplied command is accepted only when it
exactly matches the trusted resolution, and unknown engines/backends fail
closed.

Because the workspace is hidden, an external LLM planner executable must be
installed outside the workspace or staged into the current run directory. This
is a deliberate isolation constraint, not a planner API requirement.

Reuse across cases is allowed only through the explicit `reuse`/`transfer`
mechanism. A prior result may be imported as a development hypothesis, but in a
blind run it is unavailable and must be re-derived or re-classified.

---

## 4. Records

Every run writes an immutable record:

```
runs/<run-id>/
  run.json          # mode, case, planner, versions, budget, start/end
  context.json      # exactly what the planner saw (hash)
  proposals.json    # frozen proposals (hash)
  discharge.json    # engine calls: command, cwd, model hash, log hash, verdict, time
  proof.json        # obligations + certificates
  diagnostics.json  # optional CTIs; diagnostic-only, never evidence
  diagnostics/      # optional copied CTI/VCD/state artifacts
  diagnostics-context.json  # optional prior diagnostic bound into context
  check.json        # kernel report + computed levels
  audit.json        # blindness, frozen artifacts, schema
  report.md
```

Artifacts are content-addressed (or hash-referenced) and never edited in place.
A changed artifact creates a new run.

---

## 5. CLI

The one-click path is `pcd e2e`. All commands fail closed: a missing artifact,
unbound evidence, open premise, or blind-mode violation is a non-zero exit with
an explicit reason.

```
pcd import-benchmark <benchmark-dir> <case-dir> [--mode blind|dev]
pcd build <case>
pcd sketch <case> --run-dir <run>
pcd plan <case> --planner manual|template|llm --run-dir <run>
pcd discharge <case> --run-dir <run>
pcd check --case <case> --proof <proof>   # offline: schema + kernel + checkers
pcd replay <case> --run-dir <run>         # online: rebuild + re-run, refresh REPLAY
pcd e2e <case> --planner <p> [--cti]      # build -> sketch -> plan -> discharge -> check -> report
pcd cti <case> --run-dir <run>            # trusted cill diagnostic; never a proof
pcd e2e <case> --planner <p> --diagnostics-context <diagnostics.json>
pcd report <case> --run-dir <run>
pcd bench <suite>
pcd audit <case> --run-dir <run>
pcd selftest
```

`init` is reserved but not implemented; create a case by copying the `cases/`
layout. The template planner defaults to the timeout-safe `ric3 portfolio`
backend; a case can select another trusted backend with
`run_policy.template_backend` (for example `cill`, which checks the whole model
once and reports each property's inductiveness).

`check` is the offline proof-carrying path: it must not call an engine.
Only `discharge` and `replay` call engines and produce `REPLAY` evidence.
`cti` and `e2e --cti` call the trusted `ric3 cill` diagnostic but produce only
diagnostic records; CTIs are never premises. A later iteration may bind a prior
`diagnostics.json` into a new frozen context with `--diagnostics-context`, but
the audit still requires it to remain diagnostic-only and hash-bound.

---

## 6. Case lifecycle

1. **Package**: `case.yaml`, `input/`, `build/`, and (separately) `oracle/`.
   `input/` contains only what a verifier would legitimately receive; any prior
   contract/helper/proof is `oracle/`. For an existing riscv-formal benchmark,
   `pcd import-benchmark` creates this layout from the files named by the
   benchmark's `ric3.toml`; it does not import `ric3proj/`, runs, oracles, or
   helper proofs.
2. **Pre-register**: target, claim scope, budget, expected failure class, run
   mode, planner.
3. **Build**: deterministic model build; record hash and recipe.
4. **Sketch**: structural summary of the input model (no oracle).
5. **Plan**: proposals, frozen and hashed.
6. **Discharge**: engine/checker calls under budget; structured diagnostics.
7. **Check**: kernel + checkers; computed levels. An optional CTI diagnostic can
   run after discharge and before the audit; it never changes the proof.
8. **Refine (optional)**: a new frozen context may bind the diagnostic; the
   planner must emit new proposals, and the previous run remains immutable.
9. **Report/score**: report first; score against the oracle only after the run.
10. **Replay**: separate, clean-environment reproduction.
11. **Archive**: run record; no in-place edits.

---

## 7. Planner experiment protocol

1. Pre-register the case, planner/version, budget, expected failure class, and
   metrics.
2. Stage blind; hash context.
3. Planner emits proposals; freeze/hash.
4. Discharge; record every engine call.
5. Kernel check; compute levels.
6. Score against `oracle/` after the run.
7. Audit leakage and vacuity.
8. Publish the run (or mark `dev`/`invalid`).

Baselines: bare engine on a fixed model, CIll, lemma-augmented PDR (if
available), template planner, manual planner. Budgets are per run and reported.

Metrics (kept separate, not merged into one leaderboard):

- closed targets;
- `CHECKED` vs `REPLAY` leaves;
- accepted/rejected proposals;
- iterations;
- engine time and planner time/cost;
- audit result and replay success.

---

## 8. Implementation scope

The current implementation includes schemas, the kernel and checkers, the
template and decomposition planners, engine discharge, replay, the blind
harness, the offline `check` path, the suite runner, and reporting. Arithmetic
lifting patterns are documented in
[`11-arithmetic-lifting.md`](11-arithmetic-lifting.md); remaining gaps are
reported as residuals rather than accepted claims.

## 9. Definition of done

For an obligation:

- typed statement and phase;
- named premises and guarantees;
- `CHECKED` certificate or `REPLAY` binding;
- one negative control that must be rejected;
- non-vacuity where possible;
- model + recipe + tool versions + command + log/artifact hash.

For a case:

- pre-registration before the run;
- one command rebuilds and re-discharges;
- computed claim level;
- open obligations and TCB reported;
- no hand-edited status.

For a rule/backend:

- one incident or failure mode;
- one positive and one negative test;
- a doc entry;
- no expansion of the claim beyond what the check establishes.

---

## 10. Reporting

The report is a matrix, not a narrative:

| target | leaf evidence | composition | TCB | open obligations | replay |
|---|---|---|---|---|---|
| `root_a` | `REPLAY` | `CHECKED` | front-end | — | pass |
| `root_b` | `CHECKED` | `STRUCTURAL` | — | `bridge` | pass |

Every report states the computed status, evidence class, composition mode, TCB,
and residual. A prior claim becomes `CHECKED` only after a checker run in the
current flow.
