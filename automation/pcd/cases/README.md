# PCD case packages

Each directory is a data-only case package:

```
<case>/
  case.json       frozen statement, targets, budgets, build recipe, run mode
  input/          verifier-facing inputs (RTL, spec, checker, harness)
  build/          deterministic build recipe and tool configuration
  oracle/         optional prior decomposition; never staged by the pipeline
```

The artifact ships a flat selection of 24 proved cases. `picorv32_*` names are
unified across the arithmetic, core, and official families; `*_official` marks
an imported riscv-formal case. Twelve cases have self-contained offline evidence
in [`../evidence`](../evidence). The other twelve are complete source cases that
use the normal build and discharge flow.

## Offline evidence

```text
picorv32_add             picorv32_mul
picorv32_remu            picorv32_mulh
picorv32_div             picorv32_rem
picorv32_divu_official   picorv32_sw
nerv_reg                 nerv_bus_dmem
picorv32_addi_official   picorv32_jal_official
```

Run them without an engine:

```sh
./pcd bench suites/offline.json
```

## Source cases

```text
picorv32_beq_official    picorv32_c_j_official
picorv32_auipc           picorv32_bne
picorv32_jalr            picorv32_lui
picorv32_lw              picorv32_sltu
picorv32_xor             serv_causal
serv_pc_fwd              nerv_csrw_mstatus
```

These are complete packages with inputs and build recipes. The normal
`./pcd e2e <case>` path builds the model, discharges obligations, and checks the
result. They are also listed in `suites/selected.json`.

For `blind` cases, `run_policy.planner` is the pre-registered planner. The audit
fails if the proof was produced by a different planner; edit the case policy
before running a different planner, or omit the field if the case is not
planner-specific.

The current proved-row table and bundle mapping are in
[`../RESULTS.md`](../RESULTS.md).
