# PCD smoke summary

This is a frozen snapshot from before the v0.4 semantic composition guard.
Current acceptance requires rechecking the packages; the old multi-model
ACCEPT rows are not evidence that their composition boundaries pass K13.
See `pcd/docs/09-composition-guard.md`. The recorded times and engine evidence
below have not been replaced.

Fresh PCD end-to-end runs. The engine is run again for every attempt; prior
case logs are not staged. The MUL row is a multi-model package assembled
from fresh submodel runs; the builder still emits one primary model. Helper
assertions are case inputs and are counted across the proof's models/sets.

## Definitions

- `verdict`: final PCD result (`ACCEPT`, `REJECT`, `TIMEOUT`, `ERROR`).
- `time_s`: sum of recorded wall time over all attempts, including build, sketch, plan, engine, kernel, and report.
- `tried`: distinct engine invocations over all attempts. A multi-set proof counts each cill/z3/structural invocation.
- `engine_s`: sum of `bmc_time + ind_time` from each `cill/statistic.ron`; wall time is used and labeled when a statistic is missing. Sets may run concurrently, so a multi-model row can have `engine_s > time_s`.
- `engine_over_total`: `engine_s / time_s`; values above 1 indicate concurrent engine sets.
- `inv`: helper assertions bound across the final proof's models/sets (`h_*`/`p_*` or helper source files).
- `engine_included`: whether the row includes a fresh engine run (`yes`) or is package-only (`no`).
- `tcb`: distinct TCB dependencies reachable from the final root. Official `isa_model`/tool TCBs count; complete acceptance forbids design TCBs.

## Table

| case | verdict | time_s | tried | engine_s | engine_over_total | inv | engine_included | tcb |
|---|---|---:|---:|---:|---:|---:|---|---:|
| `picorv32/insn_add` | ACCEPT | 505.17 | 2 | 501.00 | 0.992 | 23 | yes | 0 |
| `picorv32/insn_addi` | ACCEPT | 260.49 | 1 | 258.60 | 0.993 | 21 | yes | 0 |
| `picorv32/insn_beq` | ACCEPT | 270.68 | 1 | 268.16 | 0.991 | 26 | yes | 0 |
| `picorv32/insn_c_j` | ACCEPT | 206.97 | 2 | 206.01 | 0.995 | 4 | yes | 0 |
| `picorv32/insn_mul` | ACCEPT | 795.57 | 16 | 1251.21 | 1.573 | 47 | yes | 1 |
| `picorv32/insn_sra` | ACCEPT | 256.03 | 2 | 253.08 | 0.989 | 23 | yes | 0 |
| `serv/reg` | ACCEPT | 452.16 | 6 | 252.59 | 0.559 | 4 | yes | 1 |
| `nerv/reg` | ACCEPT | 242.23 | 2 | 237.61 | 0.981 | 5 | yes | 0 |
| `flute/ADD` | ACCEPT | 374.32 | 2 | 341.94 | 0.913 | 0 | yes | 1 |
| `piccolo/ADD` | ACCEPT | 135.27 | 2 | 129.50 | 0.957 | 0 | yes | 1 |

## Per-attempt detail

### `picorv32/insn_add`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T040742Z-smoke_picorv32_insn_add-7c213d` | REJECT | 246.09 | 244.11 | 1 | 22 | 0 | `statistic.ron` |
| `20261101T041641Z-smoke_picorv32_insn_add-58830d` | ACCEPT | 259.07 | 256.89 | 1 | 23 | 0 | `statistic.ron` |

### `picorv32/insn_addi`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T040259Z-smoke_picorv32_insn_addi-5c241a` | ACCEPT | 260.49 | 258.60 | 1 | 21 | 0 | `statistic.ron` |

### `picorv32/insn_beq`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T042556Z-smoke_picorv32_insn_beq-347868` | ACCEPT | 270.68 | 268.16 | 1 | 26 | 0 | `statistic.ron` |

### `picorv32/insn_c_j`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T035656Z-smoke_picorv32_insn_c_j-cf15d7` | REJECT | 91.86 | 91.39 | 1 | 0 | 0 | `statistic.ron` |
| `20261101T040042Z-smoke_picorv32_insn_c_j-8038b4` | ACCEPT | 115.11 | 114.62 | 1 | 4 | 0 | `statistic.ron` |

### `picorv32/insn_mul`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T043042Z-smoke_picorv32_insn_mul-56b2b2` | ERROR | 0.39 | 0.00 | 0 | 0 | 0 | `-` |
| `20261101T043106Z-smoke_picorv32_insn_mul-c9bffe` | REJECT | 10.48 | 9.48 | 1 | 20 | 0 | `statistic.ron` |
| `20261101T043129Z-smoke_picorv32_insn_mul-d9268f` | REJECT | 4.87 | 3.94 | 1 | 20 | 0 | `statistic.ron` |
| `20261101T043154Z-smoke_picorv32_insn_mul-aa9c4a` | REJECT | 4.57 | 3.57 | 1 | 20 | 0 | `statistic.ron` |
| `20261101T043221Z-smoke_picorv32_insn_mul-ddb854` | REJECT | 4.54 | 3.58 | 1 | 20 | 0 | `statistic.ron` |
| `20261101T043235Z-smoke_picorv32_insn_mul-c2d54b` | REJECT | 6.33 | 5.44 | 1 | 19 | 0 | `statistic.ron` |
| `20261101T043252Z-smoke_picorv32_insn_mul-12b559` | REJECT | 4.27 | 3.29 | 1 | 15 | 0 | `statistic.ron` |
| `20261101T044229Z-smoke_picorv32_insn_mul-af3e7f` | REJECT | 94.12 | 92.91 | 1 | 0 | 0 | `statistic.ron` |
| `20261101T073600Z-mul-fresh` | ACCEPT | 666.00 | 1129.00 | 9 | 47 | 1 | `cill/statistic.ron,z3,rtlil-checker` |

### `picorv32/insn_sra`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T042104Z-smoke_picorv32_insn_sra-d6d540` | ERROR | 0.36 | 0.00 | 0 | 0 | 0 | `-` |
| `20261101T042110Z-smoke_picorv32_insn_sra-d1ab3b` | REJECT | 4.12 | 3.70 | 1 | 23 | 0 | `statistic.ron` |
| `20261101T042129Z-smoke_picorv32_insn_sra-daea2c` | ACCEPT | 251.55 | 249.38 | 1 | 23 | 0 | `statistic.ron` |

### `serv/reg`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T043316Z-smoke_serv_reg-fad33a` | REJECT | 92.16 | 91.59 | 1 | 0 | 0 | `statistic.ron` |
| `20261102T031600Z-serv-decomp` | ACCEPT | 360.00 | 161.00 | 5 | 4 | 1 | `log` |

### `nerv/reg`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T043451Z-smoke_nerv_reg-8a3f9d` | REJECT | 112.30 | 110.71 | 1 | 0 | 0 | `statistic.ron` |
| `20261101T070706Z-smoke_nerv_reg-01ed98` | ACCEPT | 129.93 | 126.90 | 1 | 5 | 0 | `statistic.ron` |

### `flute/ADD`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T043648Z-smoke_flute_add-35c652` | REJECT | 224.32 | 209.81 | 1 | 0 | 0 | `statistic.ron` |
| `20261101T092900Z-flute-env` | ACCEPT | 150.00 | 132.13 | 1 | 0 | 1 | `cill/statistic.ron` |

### `piccolo/ADD`

| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |
|---|---|---:|---:|---:|---:|---:|---|
| `20261101T044051Z-smoke_piccolo_add-c5fd49` | REJECT | 87.27 | 86.32 | 1 | 0 | 0 | `statistic.ron` |
| `20261101T093137Z-piccolo-env` | ACCEPT | 48.00 | 43.18 | 1 | 0 | 1 | `cill/statistic.ron` |

