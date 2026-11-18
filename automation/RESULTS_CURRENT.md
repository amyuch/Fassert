# Current PCD functional results

Date: 2026-11-10

This is the detailed functional-status table. It is generated from
`RESULTS_CURRENT.csv`; the exact-input status is preserved alongside the
functional verdict. The latest saved full exact matrix is
`pcd/experiments/formal_reproof/results-20261106-clean-exact-all/results.json`
(28 proved / 20 needs_check / 1 reject); the 2026-11-10 `smoke_serv_reg`
fixed-index proof updates that row to exact proved, so the current matrix is
29 proved / 19 needs_check / 1 reject. The earlier
`results-20261106-current/results.json` is the 24/24/1 snapshot. The strict
helper ledger is
`pcd/experiments/formal_reproof/results-20261106-helper-dev/results.json`.

## Policy

- A function is **proved** only with a kernel `status == "proved"`.
- `helper-model`, `exact-extension`, and `corrected-contract` evidence can prove
  the function, but the evidence class is always shown. The exact-input row is
  still tracked separately.
- A nonempty TCB is **not** counted. `needs_check` is not acceptance. `reject`
  is a counterexample.
- Official full-surface completeness is listed separately from the function
  verdict.

## Counts

| view | total | proved | open |
|---|---:|---:|---:|
| distinct functions | 41 | 30 | 11 |
| case rows | 49 | 38 | 11 |
| strict exact-input matrix (reference) | 49 | 29 | 19 needs_check + 1 reject |

Family summary:

| family | functions | proved | open | case rows | rows proved | rows open |
|---|---:|---:|---:|---:|---:|---:|
| `picorv32` | 24 | 24 | 0 | 32 | 32 | 0 |
| `nerv` | 3 | 3 | 0 | 3 | 3 | 0 |
| `serv` | 4 | 3 | 1 | 4 | 3 | 1 |
| `flute` | 5 | 0 | 5 | 5 | 0 | 5 |
| `piccolo` | 5 | 0 | 5 | 5 | 0 | 5 |
| **total** | **41** | **30** | **11** | **49** | **38** | **11** |

## Function table

The `obligations` column is the kernel obligation count of the cited functional
package where it is known. `-` means the exact package is the evidence and the
count was not separately extracted for this table.

### picorv32

| function | verdict | evidence | obligations | package | note |
|---|---|---|---:|---|---|
| `auipc` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_auipc` | exact input; no TCB |
| `bge` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_bge` | exact input; no TCB |
| `bgeu` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_bgeu` | exact input; no TCB |
| `blt` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_blt` | exact input; no TCB |
| `bne` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_bne` | exact input; no TCB |
| `c_add` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_c_add` | exact input; no TCB |
| `jal` | **proved** | `exact + official-helper` | 32 | `pcd/experiments/formal_reproof/official-jal-helper-dev-20261106` | core row exact; official helper proves full 15-property surface (32) |
| `jalr` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_jalr` | exact input; no TCB |
| `lui` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_lui` | exact input; no TCB |
| `lw` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_lw` | exact input; no TCB |
| `sltu` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_sltu` | exact input; no TCB |
| `xor` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_picorv32_insn_xor` | exact input; no TCB |
| `add` | **proved** | `exact` | 6 | `pcd/experiments/formal_reproof/generated-20261104/add` | smoke row exact; custom add package is 6 obligations |
| `addi` | **proved** | `exact + official-helper` | 38 | `pcd/experiments/formal_reproof/official-addi-helper-smt-dev-20261106` | smoke row exact; official helper proves full 15-property surface (38) |
| `beq` | **proved** | `exact + official-helper` | 43 | `pcd/experiments/formal_reproof/official-beq-helper-dev-20261106` | smoke row exact; official helper proves full 15-property surface (43) |
| `c_j` | **proved** | `exact + official-helper` | 21 | `pcd/experiments/formal_reproof/official-c_j-helper-dev-20261106` | smoke row exact; official helper proves full 15-property surface (21) |
| `sra` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/smoke_picorv32_insn_sra` | smoke model exact |
| `mul` | **proved** | `exact` | 32 | `pcd/experiments/formal_reproof/generated-20261104/mul` | exact arithmetic MUL; model-bound SMT |
| `mulh` | **proved** | `helper-model` | 30 | `pcd/experiments/formal_reproof/results-20261106-helper-dev/mulh-smt-dev` | 15-property helper model (13 monitor + 2 official); no TCB; full official surface cill-caveat 31 |
| `div` | **proved** | `corrected-contract` | 54 | `pcd/experiments/formal_reproof/div-signed-dev-20261106` | original core DIV row open; corrected signed-quotient model, no TCB |
| `divu` | **proved** | `original-RTL PC/RD` | 54 | `pcd/experiments/formal_reproof/divu-original-dev-20261106` | original unsigned insn_divu.v; target is PC/RD only; 4 official memory props are not in the target and remain a surface obligation |
| `rem` | **proved** | `corrected-contract` | 48 | `pcd/experiments/formal_reproof/rem-original-20261105` | exact cases/rem package (corrected build-time urem->srem); core exact row open |
| `remu` | **proved** | `exact` | 80 | `pcd/experiments/formal_reproof/remu-original-20261105` | exact core input; unsigned original contract; no TCB |
| `sw` | **proved** | `exact (clean package)` | - | `pcd/experiments/case_binding_eval/historical-20261104/23-20261102T112917Z-core_picorv32_insn_sw-ea33ce/clean` | clean exact package selected by clean-exact-all; no TCB; stored `check.json` is a stale failed projection, the matrix recheck is authoritative; helper 20 package is separate |

### nerv

| function | verdict | evidence | obligations | package | note |
|---|---|---|---:|---|---|
| `bus_dmem` | **proved** | `exact-extension` | 4 | `pcd/experiments/nerv_closure/runs/core_nerv_bus_dmem/20261106T134600Z-core_nerv_bus_dmem-exact-extension` | clean model byte-identical prefix; 276-state identity projection; no TCB |
| `csrw_mstatus` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_nerv_csrw_mstatus` | exact input; no TCB |
| `reg` | **proved** | `exact-extension` | 6 | `pcd/runs/smoke/smoke_nerv_reg/20261106T0940Z-nerv-exact-extension` | exact observer extension; 171 mapped states; no TCB; original inputs unchanged |

### serv

| function | verdict | evidence | obligations | package | note |
|---|---|---|---:|---|---|
| `causal` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_serv_causal` | exact input; no TCB |
| `pc_fwd` | **proved** | `exact` | - | `pcd/experiments/formal_reproof/generated-20261104/core_serv_pc_fwd` | exact input; no TCB |
| `pc_bwd` | **open** | `frozen reject / corrected diagnostic` | - | `pcd/runs/core_full/scan/core_serv_pc_bwd/20261102T083254Z-core_serv_pc_bwd-306649` | frozen checker vacuous on single-issue core; corrected pc_bwd_fixed accepted diagnostic; row not upgraded |
| `reg` | **proved** | `exact-extension` | 197 obligations / 96 replay / 98 transfers | `pcd/runs/smoke/smoke_serv_reg/20261106T163122Z-serv-exact-observer` | exact fixed-index observer extension; 96 one-property replays; kernel status proved; no TCB |

### flute

| function | verdict | evidence | obligations | package | note |
|---|---|---|---:|---|---|
| `addi` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/flute_addi` | instruction-source + pending=0 TCB; not kernel accepted |
| `bne` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/flute_bne` | instruction-source + pending=0 TCB; not kernel accepted |
| `jal` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/flute_jal` | instruction-source + pending=0 TCB; not kernel accepted |
| `sb` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/flute_sb` | instruction-source + pending=0 TCB; not kernel accepted |
| `add` | **open** | `tcb/needs_check` | - | `pcd/runs/smoke/smoke_flute_add/20261101T092900Z-flute-env` | bench_env assumption; no kernel acceptance |

### piccolo

| function | verdict | evidence | obligations | package | note |
|---|---|---|---:|---|---|
| `andi` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/piccolo_andi` | instruction-source + pending=0 TCB; not kernel accepted |
| `beq` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/piccolo_beq` | instruction-source + pending=0 TCB; not kernel accepted |
| `jal` | **open** | `tcb-only` | - | `pcd/runs/core_full/env_pending0/piccolo_jal` | instruction-source + pending=0 TCB; not kernel accepted |
| `lb` | **open** | `reject + tcb` | - | `pcd/runs/core_full/env/piccolo_lb` | counterexample on the available package; instruction-source BFM TCB |
| `add` | **open** | `tcb/needs_check` | - | `pcd/runs/smoke/smoke_piccolo_add/20261101T093137Z-piccolo-env` | bench_env assumption; no kernel acceptance |

## Exact-input to functional delta

These 9 rows are `needs_check` in the latest exact-input matrix
(`results-20261106-clean-exact-all`) but functionally proved by a helper,
corrected-contract, or alternate exact package.

| case | exact status | functional verdict | evidence |
|---|---|---|---|
| `smoke_picorv32_insn_mul` | needs_check | proved (function; exact row remains open) | `mul` exact (32) |
| `core_picorv32_insn_div` | needs_check | proved | corrected-contract (54) |
| `core_picorv32_insn_mulh` | needs_check | proved | helper-model (30) |
| `core_picorv32_insn_rem` | needs_check | proved | corrected-contract (48) |
| `official/picorv32_insn_addi` | needs_check | proved | helper-model full surface (38) |
| `official/picorv32_insn_beq` | needs_check | proved | helper-model full surface (43) |
| `official/picorv32_insn_c_j` | needs_check | proved | helper-model full surface (21) |
| `official/picorv32_insn_jal` | needs_check | proved | helper-model full surface (32) |
| `official/picorv32_insn_mulh` | needs_check | proved (PC/RD; full surface cill-only 31) | helper-model / cill caveat |

The current exact-input matrix is **29 proved / 19 needs_check / 1 reject**
after the 2026-11-10 serv fixed-index proof; the saved matrix JSON remains the
prior 28/20/1 snapshot. The 11 case rows that remain functionally open are the
11 open functions above: `20 - 9 = 11`. The `core_piccolo_lb` reject is one of
them.

## Remaining obligations

| family | function | remaining obligation |
|---|---|---|
| `serv` | `pc_bwd` | `node.transfer.o_pc_rdata`; frozen checker is vacuous on a single-issue core. The `pc_bwd_fixed` repaired checker is kernel-accepted, no TCB, but is diagnostic only. |
| `flute` | `addi`, `bne`, `jal`, `sb` | `node.property.normalassert`, `node.root`; TCB `instruction source + pending=0`. |
| `flute` | `add` | `helper.assume.bench_env`. |
| `piccolo` | `andi`, `beq`, `jal` | `node.property.normalassert`, `node.root`; TCB `instruction source + pending=0`. |
| `piccolo` | `lb` | `node.property.normalassert`, `node.root`; engine counterexample; instruction-source BFM TCB. |
| `piccolo` | `add` | `helper.assume.bench_env`. |

### Surface-only residuals

| case | residual |
|---|---|
| `official/picorv32_insn_divu` | `o_mem_addr_match`, `o_mem_rdata_eq_wdata_i`, `o_mem_rmask_set_i`, `o_mem_wdata_match_i` |
| `official/picorv32_insn_mulh` | the same four memory properties on the strict arithmetic-SMT surface; the full 15-property surface exists only as the cill-only caveat (31 obligations) |
| `smoke/picorv32_insn_mul` | the smoke exact row is `needs_check`; the function is proved by the exact `mul` package (32) |

## Corrected and caveated packages

| package | kernel | obligations | class |
|---|---|---:|---|
| `div-signed-dev-20261106` | proved | 54 | corrected signed DIV; original core row open |
| `divu-original-dev-20261106` | proved | 54 | original unsigned DIVU RTL; PC/RD only |
| `rem-signed-dev-20261105` | proved | 47 | corrected signed REM |
| `rem-original-20261105` | proved | 48 | exact `cases/rem`; corrected build-time `urem`→`srem` |
| `remu-original-20261105` | proved | 80 | exact core REMU; unsigned original contract |
| `rem-qsum-dev-20261105` | needs_check | 42 | not accepted |
| `core-mulh-cill-dev-20261106` | proved | 31 | full official MULH surface, cill-only caveat |

### Stale stored checks

- The `clean/check.json` stored with the SW clean package records an old failed
  projection (state 278). The latest `results-20261106-clean-exact-all` recheck
  of the package proof is `proved` with no residual; the matrix recheck is the
  current verdict.
- `results-20261106-current/` is the earlier 24/24/1 matrix. It is kept as
  history, not as the latest total.

## Reproduce

```sh
# Earlier reconciled matrix (24/24/1)
python3 pcd/experiments/formal_reproof/reconcile_current.py

# Latest full exact matrix (28/20/1) is stored at
# pcd/experiments/formal_reproof/results-20261106-clean-exact-all/
# and is regenerated by experiments/formal_reproof/run.py per its README.

# MULH strict helper result
python3 pcd/experiments/formal_reproof/check_one.py \
  pcd/experiments/formal_reproof/results-20261106-helper-dev/mulh-smt-dev/case.json \
  pcd/experiments/formal_reproof/results-20261106-helper-dev/mulh-smt-dev/proof.json
```

The `RESULTS_CURRENT.csv` file is the authoritative row-by-row table. It keeps
both `exact_status` and `functional_status`, so the strict matrix and the
functional view cannot drift apart silently.
