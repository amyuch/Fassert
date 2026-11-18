# Benchmark categories and test lists

This file is the inventory behind the curated lists.  It separates **design
cases**, **checker variants**, and **legacy material**, then gives the reduced
and full-property suites used for routine work.

Default recommendation: `smoke` for a quick regression, `core` for routine
changes, `extended` before a release, and `full` when the official/full-property
contract matters.  The 104-case active corpus is rarely needed as one run.

## What counts as a case

| kind | directories | role | in curated lists |
|---|---:|---|---|
| Active design cases | 104 | the CIll benchmark corpus | 101 non-ALT OPS, via tiers |
| Preserved picorv32 | 30 | unselected full-corpus cases, reduced checker | no |
| picorv32 fullcheck | 73 | the same 73 picorv32 designs with the full checker | no; `full` uses official PCD imports |
| Official PCD imports | 6 | clean fullcheck imports under `automation/pcd` | 5 in `testlist_full.csv` |
| `test4neuroabs` | 99 + 99 | legacy NeuroAbs corpus and its fullcheck variant | no (excluded) |
| `riscv-formal` | library | shared instruction specs and RVFI checkers | n/a |

`picorv32_fullcheck` is a **checker variant**, not 73 additional designs.  The
active picorv32 family is 43 cases; adding the 30 preserved cases gives the 73
designs that `picorv32_fullcheck` re-checks with the full property set.

`benchmarks/picorv32_full/` is the **preserved reduced corpus**.  It is not the
full-property suite and is not in the curated lists.

## Active corpus: 104 cases

| family | cases | categories | property style |
|---|---:|---|---|
| `picorv32` | 43 | alu 13, branch 6, compressed 5, divrem 6, jump 2, load 2, mul 5, store 2, upper 2 | rvfi instruction / memory checkers |
| `serv` | 4 | causal 1, pc 2, register 1 | property-specific rvfi checkers |
| `nerv` | 25 | bus 4, causal 1, csr-ill 2, csr-read 4, csr-write 9, illegal 1, pc 2, register 1, unique 1 | property-specific rvfi checkers |
| `flute` | 17 | alu 4, logic 5, shift 1, branch 4, jump 1, store 2 | ILA `normalassert` |
| `piccolo` | 15 | alu 3, logic 4, upper 2, branch 2, jump 1, load 1, store 2 | ILA `normalassert` |

The three picorv32 `_altops` variants remain in the active corpus but are
excluded from `testlist.csv`; they exercise the same add/sub datapath.  The
reduced list therefore has 40 picorv32 cases and 101 cases total.

`insn_xor` and `insn_sra` were promoted from the preserved corpus to active
picorv32 cases for the core suite.

The `flute` `*_new` cases are experimental AIG variants; the extended list keeps
them, and the core list uses the non-`_new` cases.

## The 40-case core suite

| family | cases | composition |
|---|---:|---|
| `picorv32` | 23 | mixed ALU, branch/jump, word-memory, compressed, upper, and logic cases |
| `serv` | 4 | `causal`, `pc_bwd`, `pc_fwd`, `reg` |
| `nerv` | 3 | `reg`, `csrw_mstatus`, `bus_dmem` |
| `flute` | 5 | `ADD`, `ADDI`, `BNE`, `JAL`, `SB` |
| `piccolo` | 5 | `ADD`, `ANDI`, `BEQ`, `JAL`, `LB` |

The 23 picorv32 cases are:

```text
smoke: add      addi     mul      beq      c_j      sra
core:  mulh     div      rem      remu     bge      jal
       bne      bgeu     blt      jalr     lw       sw
       sltu     lui      auipc    c_add    xor
```

Only `div` is kept from the div/divu pair; `divu` stays out of the core.  The
set keeps add, mul, rem, compare/branch, jump, word-memory, compressed, upper,
and logic/shift coverage.

Smoke contains `add/addi`, `mul`, `beq`, `c_j`, and `sra`; core adds `mulh`,
`div`, `rem/remu`, `bge/bgeu`, `blt`, `jal/jalr`, `bne`, `lw/sw`, `sltu`,
`lui/auipc`, `c_add`, and `xor`.  This keeps the official/reused `beq`, `c_j`,
and `jal` cases in the reduced suite.

`flute` and `piccolo` overlap on two cases (`ADD`, `JAL`) and have three
different cases each: flute adds `ADDI`, `BNE`, `SB`; piccolo adds `ANDI`,
`BEQ`, `LB`.

### Coverage notes

* **serv** is small enough that all four properties are in the core suite.
* **nerv** splits into instruction/trap, CSR read/counter, CSR write, PC/order,
  register, and bus behavior.  The 3-case selection is `reg`, `csrw_mstatus`,
  and `bus_dmem`; the extended list keeps all 25.
* **flute** uses `ADD`/`ADDI` plus `BNE`, `JAL`, and `SB`; the extended list
  keeps every instruction and every `_new` variant.
* **piccolo** uses `ADD`, `ANDI`, `BEQ`, `JAL`, and `LB`; the extended list
  keeps all 15 instructions.

## Test-list tiers

`testlist.csv` contains the 101 non-ALT OPS active cases with columns
`tier,family,case,category,semantics,checker,path,note`.
`testlist_full.csv` uses the same columns.  The `checker` column names the
canonical checker source; each materialized reduced case stores its checker as
`rvfi_insn_check.sv` (or the family-specific `rvfi_*_check.sv`).  The `tier`
column is cumulative:

| tier | rows in CSV | cases run | purpose |
|---|---:|---:|---|
| `smoke` | 10 | 10 | family-related quick regression |
| `core` | 30 | 40 | smoke + the 40-case core suite |
| `extended` | 61 | 101 | every non-ALT OPS active case |
| `full` | 5 | 5 | official PCD full-property imports |
| `all` | — | 106 | extended + full |

The smoke suite is:

```text
picorv32  insn_add, insn_addi, insn_mul, insn_beq, insn_c_j, insn_sra
serv      reg
nerv      reg
flute     ADD
piccolo   ADD
```

The core additions are `picorv32` `mulh`, `div`, `rem/remu`, `bge/bgeu`, `blt`,
`bne`, `jal/jalr`, `lw/sw`, `sltu`, `lui/auipc`, `c_add`, and `xor`;
`serv/causal`, `serv/pc_bwd`, `serv/pc_fwd`; `nerv/csrw_mstatus`,
`nerv/bus_dmem`; `flute/ADDI`, `flute/BNE`, `flute/JAL`, `flute/SB`; and
`piccolo/ANDI`, `piccolo/BEQ`, `piccolo/JAL`, `piccolo/LB`.

`testlist_full.csv` is separate: mixing reduced and full-property checkers in
one suite would make the counts incomparable.  It contains five official PCD /
riscv-formal fullcheck imports:

```text
insn_addi, insn_beq, insn_c_j, insn_jal, insn_mulh
```

All five also appear in the 23-case picorv32 set.  The PCD official suite has a
sixth case, `insn_divu`, which can be swapped in if needed.  These cases use
`automation/pcd/cases/official/<case>/build/build.sh`, not a benchmark
`run.sh`.

`test4neuroabs/` and `test4neuroabs/fullcheck/` are excluded.  `picorv32_full/`
is excluded from the default list; use `picorv32/manifest.csv` if the preserved
set is needed.  `automation/pcd/suites/official_isa.json` is the source of the
official/full list.

## Run and regenerate

```sh
cd benchmarks

python3 run_testlist.py --tier smoke          # 10 cases
python3 run_testlist.py --tier core --jobs 4  # 40 cases
python3 run_testlist.py --tier extended       # 101 cases
python3 run_testlist.py --tier full           # 5 full-property cases
python3 run_testlist.py --tier all            # 106 cases

python3 run_testlist.py --tier smoke --dry-run
python3 make_testlist.py --check
python3 make_testlist.py                     # rewrite both CSV files
```

`run_testlist.py` invokes each reduced case's `./run.sh` (`ric3 build` plus a
model hash) and each official case's `build/build.sh`.  It is a build/readiness
suite; proof overlays and certificates live in `automation/decomp/`.
