# Fassert

Fassert is a formal-verification artifact for RISC-V cores against
riscv-formal/RVFI properties. It is built around **PCD** (proof-carrying
decomposition), a kernel-checked proof workbench for constructing, replaying,
and composing formal proof obligations.

## Repository layout

| Path | Contents |
|---|---|
| `automation/` | PCD workbench, proof infrastructure, cases, and the current result ledger |
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

The result ledger at `automation/RESULTS_FULL.csv` records the full
experimental matrix; rows for families outside this checkout are retained for
provenance, not for local reproduction.

## Results

The current functional and exact-status tables are:

- `automation/RESULTS_FULL.csv`
- `automation/RESULTS_FULL.md`

Only a kernel-computed `proved` status is an acceptance. `needs_check` is an
open obligation ledger, not a partial proof. The detailed rules are in
`automation/pcd/docs/`.

## Reproduce

From the repository root:

```sh
cd automation/pcd

# Offline kernel, checker, pipeline, and package tests.
./pcd selftest

# Check the bundled real-ADD composition example.
./pcd compose \
  --case examples/composition_add/case.json \
  --proof examples/composition_add/proof.json
```

The current reproof matrix can be regenerated with:

```sh
cd automation/pcd
python3 experiments/formal_reproof/run.py \
  --out experiments/formal_reproof/results-$(date -u +%Y%m%d) \
  --timeout 45 \
  --max-candidates 5
```

## Baselines

Baseline directories contain the baseline code, patches, and experiment
drivers only. Upstream dependencies such as rIC3, Yosys, Yosys-Slang, and
PyVerilog are fetched or pinned separately; build trees, run logs, and result
trees are not part of the artifact.

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
