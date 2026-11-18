# PCD workbench

PCD is a proof-carrying decomposition workbench for hardware properties. A case
freezes the target and the verifier-facing inputs. A proof package records local
certificates, replay bindings, model transfers, helper hygiene, coverage, and a
checked root composition. The kernel is the only component that can accept a
target; planners and engines only produce proposals and evidence.

This artifact contains the current flow, current documentation, a flat selection
of 24 proved cases, and 12 self-contained offline evidence packages. Twelve
cases run through `./pcd check` without an engine. The other twelve are complete
source cases for the normal build and discharge flow. The current proved-row
table is in [`RESULTS.md`](RESULTS.md).

## Install

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Optional wide-multiplier portfolio backend:

```sh
pip install -r requirements-optional.txt
```

The core install needs Python 3.10+, `jsonschema`, `referencing`, `z3-solver`,
and `PyYAML`. Building or replaying models also needs the external tools named by
the case build recipe, normally Yosys and rIC3.

## Quick start

```sh
# Check the framework and bundled examples.
./pcd selftest

# Recheck all 12 offline evidence packages without an engine.
./pcd bench suites/offline.json

# Recheck one package.
./pcd check --case evidence/picorv32_mul/case.json \
            --proof evidence/picorv32_mul/proof.json

# Check the official offline packages, including source provenance.
./pcd bench suites/official_isa.json

# Build, discharge, and check a source case.
./pcd e2e picorv32_add
```

`./pcd check` is the offline path: it validates schemas, certificates, model
hashes, replay logs, helper bindings, coverage, and the root implication. It
does not call an engine. `./pcd e2e` builds a model, runs the selected backend,
and then calls the same kernel.

## Offline evidence

Each directory under [`evidence/`](evidence) contains:

```
case.json     frozen case contract
proof.json    proof graph and certificates
models/       referenced BTOR models
logs/         proof-bound replay logs
case/ input/  helper assertions and source inputs needed by the check
check.json    kernel result
README.md     case, evidence class, and recheck command
```

The 12 offline cases are:

| case | function | evidence |
|---|---|---|
| `picorv32_add` | add | exact |
| `picorv32_mul` | mul | exact |
| `picorv32_remu` | remu | exact |
| `picorv32_mulh` | mulh | helper-model |
| `picorv32_div` | div | corrected contract |
| `picorv32_rem` | rem | corrected contract |
| `picorv32_divu_official` | divu | official RTL + checked quotient induction |
| `picorv32_sw` | sw | exact |
| `nerv_reg` | reg | exact observer extension |
| `nerv_bus_dmem` | bus_dmem | exact observer extension |
| `picorv32_addi_official` | addi | helper-model |
| `picorv32_jal_official` | jal | helper-model |

## Selected cases

[`cases/`](cases) contains 24 flat cases. The offline 12 above are paired with
their evidence packages. The remaining 12 are:

```text
picorv32_beq_official    picorv32_c_j_official
picorv32_auipc           picorv32_bne
picorv32_jalr            picorv32_lui
picorv32_lw              picorv32_sltu
picorv32_xor             serv_causal
serv_pc_fwd              nerv_csrw_mstatus
```

They are complete source packages in `suites/selected.json` and use the normal
`e2e` flow. See [`cases/README.md`](cases/README.md).

## Suites

| suite | contents | offline? |
|---|---|---|
| `suites/offline.json` | 12 evidence packages | yes |
| `suites/official_isa.json` | 3 official evidence packages with source-provenance checks | yes |
| `suites/selected.json` | all 24 selected cases | 12 offline, 12 source |

`bench` resolves `proof_packages` relative to the suite, the PCD root, or the
current directory. A suite sets `provenance: "official"` when it must preserve
official `spec`, `checker`, and `rtl` source hashes byte-for-byte; offline helper
packages set `provenance: "none"` and rely on the exact bound kernel check.

## Layout

```
pcd/
  pcd                  one-click wrapper
  bin/pcd              CLI entry point
  kernel/              disposition and kernel checks
  checkers/            certificate, projection, SMT, and composition checkers
  pipeline/            build, sketch, plan, discharge, check, replay, bench
  schema/              JSON schemas for case, obligation, proof, and diagnostics
  common/              vendored shared identity/IO helpers
  cases/               24 selected flat case packages
  evidence/            12 self-contained offline proof packages
  examples/            small offline composition and solver-bridge examples
  suites/              offline, official, and selected suites
  docs/                current flow documentation
  tests/               unit and integration tests
  RESULTS.md           current proved-row table and bundle mapping
```

## Proof model

- A case freezes the target, guards, model identity, and build recipe.
- A proof is a DAG of model-bound obligations. Every premise resolves to a
  named guarantee.
- Local evidence is a checked certificate or a hash-bound replay of an engine
  verdict. `BMC_CLEAN`, `UNKNOWN`, timeouts, and CTIs are not premises.
- A fact on a different model needs a checked projection or transfer.
- A complete root is a checked composition. Design TCBs, assumption helpers,
  unresolved premises, and structural root acceptance are rejected.
- The final `proved` / `needs_check` / `reject` disposition is computed from the
  obligation ledger; it is never read from a stored status field.

The relative-soundness argument is in [`docs/00-theorem.md`](docs/00-theorem.md).
Acceptance rules are in [`docs/03-rules.md`](docs/03-rules.md). Arithmetic
lifting patterns are in
[`docs/11-arithmetic-lifting.md`](docs/11-arithmetic-lifting.md).

## Artifact scope

The artifact is the flow, the current docs, the selected cases, and the offline
evidence. It does not include research logs, prior matrices, prior run
directories, build caches, or oracle material. The `.gitignore` keeps those
local-only paths out of the published tree. The full local development matrix is
kept outside the artifact; `RESULTS.md` is the 37/49 proved-row view and the
24-case bundle map.

## Tests

```sh
./pcd selftest
python3 -m unittest discover -s tests -v
```

The test suite covers schemas, the kernel, certificates, composition, blind
audit behavior, the decomposition planner, the solver bridge, and the offline
suite runner.
