# PCD scope

This document fixes the purpose, boundaries, and acceptance surface of the
proof-carrying decomposition workbench. The kernel is the final authority; the
documents under `docs/` define the current method and rules.

## Purpose

PCD makes a hardware proof compositional and checkable:

- a case freezes the target, guard, observation point, model identity, and
  verifier-facing inputs;
- a planner proposes cuts, obligations, certificates, and engine routing;
- engines and checkers produce local evidence;
- the kernel validates dependencies, guarantees, coverage, transfers, helper
  hygiene, and the root implication;
- the final disposition is computed from the obligation ledger.

The workbench is case-agnostic. Cases are data. New cases should not require
changes to framework source; new obligation kinds are plugins plus tests.

## In scope

- Synchronous bit-vector transition systems and their model-bound properties.
- Engine replay evidence through the trusted backend catalog.
- Polynomial, SMT-implication, SMT-induction, miter, witness, and projection
  certificates.
- Checked model transfers for non-primary facts.
- Helper models and observers when every helper assertion is bound to a proved
  node and every helper assumption is discharged or exposed as an official TCB.
- Blind-run isolation, hashed context and proposals, and leakage audit.
- Offline rechecking of proof packages without an engine.
- Imported official riscv-formal cases and source-provenance checks.

## Out of scope

- Proving a design correct by assuming the target.
- Accepting `BMC_CLEAN`, `UNKNOWN`, a timeout, or a CTI as evidence.
- Design TCBs, assumption helpers, assumption cuts, missing-artifact overrides,
  or `STRUCTURAL` roots in a complete claim.
- Arbitrary relational refinement, asynchronous stuttering, arrays, or
  liveness/hyperproperties.
- Automatic discovery of every invariant or arithmetic lift.
- Source-to-gate equivalence beyond the declared front-end TCB.
- Treating a model hash as semantic equivalence.

## Trust boundary

A `proved` result is relative to:

- the frontend translation from RTL to BTOR2;
- rIC3/BMC verdicts and their replay logs;
- Z3 and the canonical SMT/polynomial encodings;
- the model/certificate parsers, expression semantics, composition checker, and
  disposition implementation.

The kernel does not trust a planner, a stored status field, a model name, a
helper file, a prior acceptance tag, or an engine's prose. Official TCB kinds are
`frontend`, `engine`, `checker`, and `isa_model`. A TCB may not be a direct
target premise in complete mode.

## Case boundary

A case contains only verifier-facing inputs:

```
case.json
input/
build/
```

Prior contracts, helper proofs, proof graphs, and prior runs belong in `oracle/`
and are never staged. The blind audit hides the workspace, the source case tree,
prior runs, and oracle material, then binds only the current run directory.

## Evidence boundary

An offline evidence package contains the frozen case and proof, the referenced
models, proof-bound logs, helper/assertion files needed by the checkers, the
kernel result, and a recheck note. It is self-contained for `./pcd check`; it is
not a rebuild recipe and does not claim a fresh engine run.

## Acceptance boundary

A complete target has:

- a `CHECKED` root composition;
- no direct target TCB;
- only official TCB kinds deeper in the graph;
- no design TCB, assumption helper/cut, `OPEN`/`UNKNOWN` premise, or
  `STRUCTURAL` root;
- every named model and artifact bound by hash;
- every helper assertion bound to a proved node and every helper assumption
  discharged on the target cone;
- every required target property bound to a proved destination property.

A missing required obligation is `needs_check`, not an accept. Invalid or
refuted evidence is `reject`. See
[`docs/00-theorem.md`](docs/00-theorem.md) and
[`docs/03-rules.md`](docs/03-rules.md).

## Current artifact

The published tree contains the flow, current documentation, 24 selected flat
cases, and 12 self-contained offline evidence packages. Research logs, prior run
directories, build caches, the full development matrix, and oracle material are
local-only and excluded from the artifact. Current results are in
[`RESULTS.md`](RESULTS.md).
