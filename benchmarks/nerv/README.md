# nerv benchmarks

25 self-contained cases covering instruction, CSR, PC, and bus behavior,
including:

`bus_dmem`, `bus_dmem_fault`, `bus_imem`, `bus_imem_fault`, `causal`,
`csr_ill_f11`, `csr_ill_fff`, `csrc_const_custom_ro`,
`csrc_inc_mhpmcounter5`, `csrc_upcnt_mcycle`, `csrc_upcnt_minstret`,
`csrw_custom`, `csrw_custom_ro`, `csrw_mcycle`, `csrw_mhpmcounter5`,
`csrw_mhpmevent3`, `csrw_mhpmevent5`, `csrw_mhpmevent9`, `csrw_minstret`,
`csrw_mstatus`, `ill`, `pc_bwd`, `pc_fwd`, `reg`, `unique`.

Each case has its own `nerv.sv`, `wrapper.sv`, `tb.sv`, `defines.sv`, checker,
`rvfi_macros.vh`, and `ric3.toml`. The family-level `nerv.sv` and `wrapper.sv`
are canonical snapshots, and `../riscv-formal/` is the canonical checker/macro
library.

```sh
cd bus_dmem
./run.sh
```

The 21 cases added during the self-contained migration came from the full
`cill_exp/nerv` source tree; the two `boilerplate*` generators are templates and
were not added to `benchmarks/`.
