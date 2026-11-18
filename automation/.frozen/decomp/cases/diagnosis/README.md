# Diagnosis case set (Layer A validation)

Purpose: test whether the workflow can use a **real proof failure** to select a
strategy and produce a justified repair — not merely validate hand-built proof
graphs. These are retrospective, pre-registered feasibility cases, not a
generality result.

## Controls

1. **Preserve the initial failure**: save the bad config, command, tool version,
   model id, log, and CTI/CEX before applying the repair.
2. **Pre-register** the diagnosis, expected strategy, evidence tests, and
   competing explanations before replaying the bad config (records below).
3. **Fixed budget** per case; no silent retries.
4. **Independent validation**: the repair outcome is decided by the engine/kernel;
   the planner cannot close it. Replay never upgrades `PROVED_TRUSTED`.

## Record schema

```json
{
  "case_id": "D1",
  "target_obligation": "...",
  "initial_engine": "...",
  "bad_config": "path/description",
  "failure_artifact": "log/CTI path",
  "diagnosis_hypothesis": {
    "failure_type": "unreachable_cti|representation|uncovered_branch|temporal|sampling|false_premise",
    "evidence_tests": ["..."],
    "competing": ["..."]
  },
  "selected_strategy": "S1|S2|S3|S5|A0|S4",
  "repair_hypothesis": "...",
  "new_obligations": ["..."],
  "proof_outcome": "PENDING|PROVED_TRUSTED|BMC_CLEAN|UNKNOWN|COUNTEREXAMPLE",
  "kernel_outcome": "PENDING|ACCEPT|REJECT|NOT_APPLICABLE",
  "budget": "...",
  "provenance": "..."
}
```

A case is successful only if (a) the diagnosis is supported by the recorded
evidence, (b) the repair addresses the diagnosed cause, and (c) the outcome is
reported honestly (a failed repair is a valid result).

## Cases (pre-registered)

- **D1** — `mul_contract` finish-only accumulator assertion: unreachable CTI
  (arbitrary carry-save state at finish) → S1 (active-cycle invariant).
- **D2** — raw bit-vector arithmetic frontier → S3 (purification / interface);
  no RTL needed.
- **D3** — DIV PCPI mux without the `!pcpi_mul_ready` priority guard →
  uncovered branch → S2 (case/guard + coverage).
- **D6** — DIV finish mux sampled at `pcpi_ready` instead of the finish edge →
  false/mis-timed premise → A0 (replay/restate); plus the S2 missing-zero-law
  negative test.

Deferred: **D5** (abstraction refinement) — no reproducible in-project example;
do not include until we run one (or borrow NeuroAbs explicitly as external).
D4 (temporal) to follow after D1–D3/D6.

## Operational evidence (distinguishing the failure type)

- unreachable CTI: the bad obligation is BMC-clean but Not Inductive, and the
  CTI uses a state excluded by a reachable manifold/phase; the repair is an
  invariant/phase fact.
- representation: the same obligation closes in another representation; the raw
  query hits a theory frontier (timeout/unknown).
- uncovered branch: the counterexample takes a transition/guard not covered;
  the repair adds an explicit exhaustive guard.
- sampling: the bad form compares values from the wrong cycle/edge; the fix uses
  the correct `$past`/finish-edge values; a CEX appears in the bad form.
- false premise: an assumption is refuted by a concrete trace/negative test; it
  is rejected rather than used to close the root.
