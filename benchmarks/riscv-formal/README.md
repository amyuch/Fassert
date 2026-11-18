# riscv-formal shared library

Canonical shared inputs for the `picorv32` and `serv`/`nerv` RTL cases:

- `insn/` — 70 riscv-formal instruction specs (`insn_*.v`);
- `rvfi_insn_check.sv` — reduced CIll instruction checker (rd/pc only);
- `rvfi_insn_check_mem.sv` — reduced memory-only checker;
- `rvfi_insn_check_origin.sv` — full-property RVFI checker used by
  `picorv32_fullcheck`;
- property-specific `rvfi_*_check.sv` checkers used by `serv`/`nerv`;
- `rvfi_macros.vh` — RVFI macros;
- `tb.sv` — standard testbench;
- `COPYING` — upstream license.

The reduced checkers are the CIll benchmark set, not the upstream riscv-formal
checks. The upstream sources are vendored at
`baselines/cill/deps/riscv-formal/checks/`; raw upstream checker files need the
benchmark's `defines.sv` include and single-channel adaptation before they can
be used by the materialized cases. `picorv32_fullcheck/` uses the adapted
full-property checker above.

The benchmark cases are materialized copies of these files, so this directory is
the source of truth when updating a checker or instruction spec. It contains all
70 instruction specs needed by the active and preserved picorv32 cases.
