# test4neuroabs full-property variant

`fullcheck/` is a self-contained, full-property parallel tree for the 99
`test4neuroabs` cases. It is generated from the existing cases; the source
`nerv/`, `serv/` and `picorv32/` trees are left untouched.

```
fullcheck/
  nerv/<case>/          25 cases
  serv/<case>/           4 cases
  picorv32/<case>/      70 cases (38 active + 32 preserved/compressed)
  manifest.csv          checker and bad/constraint/init counts for all 99
```

## Checker overrides

The reduced CIll checkers are replaced where the full property set differs:

| cases | checker | change |
|---|---|---|
| `picorv32/*` (70) | `rvfi_insn_check.sv` | `../riscv-formal/rvfi_insn_check_origin.sv`, 20 asserts instead of 2 for instruction cases or 1 for `lw`/`sw` |
| `nerv/reg`, `serv/reg` | `rvfi_reg_check.sv` | upstream `baselines/cill/deps/riscv-formal/checks/rvfi_reg_check.sv`; restores the `assume` and `rvfi_order < insn_order` behaviour |
| `nerv/pc_bwd`, `serv/pc_bwd` | `rvfi_pc_bwd_check.sv` | upstream `rvfi_pc_bwd_check.sv`; same restoration |
| all other nerv/serv cases (25) | unchanged | already match the upstream assert/assume counts |

The upstream checkers are prefixed with `` `default_nettype none `` and
`` `include "defines.sv" `` so they work with the materialized read order. The
picorv32 checker is the in-tree full adaptation (20 asserts, single channel, no
PMA map/covers); raw upstream `rvfi_insn_check.sv` does not compile through the
benchmark harness because it does not include `defines.sv`.

## Expected counts (BTOR2, post-reset)

`gen_btor.ys` is copied unchanged, so every case keeps the reset-initialising
`sim ... -w` writeback. The counts below are from `problem.btor2`:

| cases | checker | bad | constraints | init |
|---|---|---:|---:|---:|
| 62 picorv32 cases | full insn | 15 | 2 | 75 |
| 8 mul/div/rem picorv32 cases | full insn | 15 | 2 | 76 |
| `nerv/reg` | full reg | 2 | 3 | 57 |
| `serv/reg` | full reg | 2 | 7 | 20 |
| `nerv/pc_bwd` | full pc_bwd | 1 | 3 | 56 |
| `serv/pc_bwd` | full pc_bwd | 1 | 7 | 19 |
| 25 other nerv/serv cases | as source | unchanged | unchanged | unchanged |

For comparison, the source `picorv32` tree has 2 bad / 1 constraint for
instruction cases and 1 bad / 1 constraint for memory cases; the source
`nerv/reg` is 2/1, `serv/reg` 2/5, `nerv/pc_bwd` 1/1 and `serv/pc_bwd` 1/5.
The full reg/pc_bwd checkers keep the same asserts but add the upstream
assumptions, hence the higher constraint counts.

`manifest.csv` records `family,case,checker,bad,constraint,init` for every
generated case. The 25 `as-source` cases reproduce the source `problem.btor2`
byte-for-byte.

## Build

```sh
cd fullcheck/picorv32/insn_add
./run.sh
```

`run.sh` runs `gen_btor.ys` and `gen_aiger.ys`, exactly as in the source tree.
The canonical artifact for reset-initialised checks is `problem.btor2`. The
generator creates only `problem.btor2` by default; pass `--aiger` or run
`./run.sh` to create the legacy zero-initialised `problem.aig`.

## Regenerate

```sh
cd benchmarks/test4neuroabs

python3 make_fullcheck_cases.py --check          # list the 99 cases
python3 make_fullcheck_cases.py --jobs 8         # BTOR2 only
python3 make_fullcheck_cases.py --jobs 8 --aiger # also AIGER
```

The generator copies only source files (`*.sv`, `*.v`, `*.vh`, `gen_*.ys`,
`run.sh`, `description.txt`, the NeuroAbs `wrapper.v`/`wrapper_constant.v`,
and `design_pp.v`/`preprocess.sh` where needed). It skips CEGAR/NeuroAbs
artifacts (`iter/`, `wrapper_abstract*`, `wrapper_noassert.v`,
`picorv32_input*`, `map.txt`, logs, parsers, etc.).

## Scope

The `fullcheck/` tree is a property-strength variant of the legacy
`test4neuroabs` corpus, not part of the active `benchmarks/` family set. Use
`../../picorv32_fullcheck/` for the full-property picorv32 benchmark family
without the NeuroAbs entry points.
