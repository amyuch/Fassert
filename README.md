# Fassert

Fassert is a formal-verification artifact for RISC-V cores against
riscv-formal/RVFI properties. It is built around **PCD** (proof-carrying
decomposition), a kernel-checked proof workbench for constructing, replaying,
and composing formal proof obligations.

## Repository layout

| Path | Contents |
|---|---|
| `automation/` | PCD workbench, proof infrastructure, and cases |
| `baselines/` | Baseline implementations and experiment drivers, without run logs or result trees |
| `benchmarks/` | RISC-V/RVFI benchmark cases and the shared riscv-formal inputs |

The active proof framework is under `automation/pcd/`. See
`automation/pcd/README.md` and `automation/pcd/docs/README.md` for the
acceptance rules and command reference.

## Scope

The published benchmark snapshot covers:

- Picorv32 instruction and full-property cases;
- SERV and NERV properties;
- the shared `riscv-formal` instruction specifications and RVFI checkers;
- the corresponding NeuroAbs-format case sources where they are part of the
  benchmark set.

## Dependencies

Core Python dependencies are listed in the root `requirements.txt`:
`jsonschema`, `referencing`, `z3-solver`, and `PyYAML` (Python 3.10+). Install
them from the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Model building and replay also require the external tools named by each case
build recipe, normally Yosys and rIC3. Baseline-specific Python extras remain
in `baselines/*/requirements.txt`.

## Results

The PCD case table is in `automation/pcd/RESULTS.md`. Result ledgers generated
by experiments are local outputs and are not bundled.

Only a kernel-computed `proved` status is an acceptance. `needs_check` is an
open obligation ledger, not a partial proof. The detailed rules are in
`automation/pcd/docs/`.

## Reproduce

From the repository root:

```sh
cd automation/pcd

# Offline kernel, checker, pipeline, and package tests.
./pcd selftest

# Recheck all bundled offline evidence packages.
./pcd bench suites/offline.json

# Check the bundled real-ADD composition example.
./pcd compose \
  --case examples/composition_add/case.json \
  --proof examples/composition_add/proof.json
```

Source-case end-to-end runs use the external engines named by the case build
recipe.

## Baselines

Baseline directories contain the baseline code, patches, and experiment
drivers only. Upstream dependencies such as rIC3, Yosys, Yosys-Slang, and
PyVerilog are fetched or pinned separately; build trees, run logs, and result
trees are not part of the artifact. Install the shared core Python dependencies
from the root `requirements.txt`; baseline-specific extras are listed in each
baseline's own `requirements.txt`.

## Trust boundary

Acceptance is computed by the PCD kernel from the obligation ledger, not from
stored status labels. Frozen evidence is bound by model hashes, log hashes,
manifests, and replay records. The trusted computing base consists of the
frontend translation, engine verdicts, SMT checkers, parsers, and the official
ISA models; design TCBs are rejected in complete mode.

## Licenses

Each component retains its upstream license and notices. See the corresponding
baseline and benchmark directories before redistributing or reusing their
sources.
