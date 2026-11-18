# picorv32 benchmarks

43 active riscv-formal instruction cases: 40 selected from the original 70-case
corpus plus 3 ALTOPS variants. The 30 unselected original cases live in
`../picorv32_full/`, and `manifest.csv` is the single list of active vs
preserved cases.

Each case directory contains:

```text
insn_<case>.v        instruction spec
rvfi_insn_check.sv   reduced CIll checker (full-property: ../picorv32_fullcheck)
rvfi_macros.vh       RVFI macros
picorv32.sv          core RTL
wrapper.sv           harness
tb.sv                testbench
defines.sv           case defines
ric3.toml            CIll input
run.sh               build + model hash
```

The memory cases use `rvfi_insn_check_mem.sv` as the content of
`rvfi_insn_check.sv`; the filename in `ric3.toml` stays the same.

These are the reduced CIll checkers: the normal instruction checker asserts only
`rvfi_rd_wdata` and `rvfi_pc_wdata`, and the memory checker only
`rvfi_mem_addr`. For the full-property counterpart use `../picorv32_fullcheck/`.

## Active set

The active cases are chosen by family/coverage rather than by taking a prefix
of the alphabet. In particular they preserve:

- five ALU register/immediate pairs: `add`/`addi`, `and`/`andi`,
  `sll`/`slli`, `slt`/`slti`, `sltu`/`sltiu`;
- subtraction (`sub`) plus compressed ALU/load/store/jump representatives:
  `c_add`, `c_sub`, `c_lw`, `c_sw`, `c_j`;
- branches, jumps, and word/byte load/store pairs;
- logic/shift diversity from promoted `xor` and `sra` cases;
- all eight MUL/DIV/REM base cases as **non-ALTOPS** cases:
  `mul`, `mulh`, `mulhu`, `mulhsu`, `div`, `divu`, `rem`, `remu`;
- three **ALTOPS** representatives: `mul_altops`, `div_altops`, `rem_altops`.

`insn_mul_altops` uses the serial multiplier (`ENABLE_MUL`) because the fast
multiplier has no ALTOPS path. The non-ALTOPS MUL cases use the canonical
fast-multiplier wrapper. DIV/REM ALTOPS is selected by the `defines.sv` macro
and needs no wrapper change.

See `manifest.csv` for the exact list. Its columns are `case`, `active`,
`group`, `semantics`, `location`, and `note`; `semantics` is `normal`,
`nonaltops`, or `altops`. To print only the active cases:

```sh
awk -F, 'NR > 1 && $2 == "yes" { print $1 }' manifest.csv
```

## Build

```sh
cd insn_add
./run.sh
```

The family-level `picorv32.sv` and `wrapper.sv` are canonical copies, and
`../riscv-formal/` is the canonical spec/checker library. `insn_mul_altops` is
the only active case with a case-local wrapper override (serial multiplier).
Cases are materialized so they can be built without following symlinks.

Proof-specific overlays (for example the `insn_rem` divider overlays) are under
`automation/decomp/cases/`.
