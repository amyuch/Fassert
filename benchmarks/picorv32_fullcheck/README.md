# picorv32 full-check benchmarks

Full-property counterpart to `../picorv32` (43 active cases) and
`../picorv32_full` (30 preserved cases). The case set is exactly the 73 rows in
`../picorv32/manifest.csv`. The RTL, harness, instruction specs, `defines.sv`,
`ric3.toml` and `run.sh` are unchanged; only the checker is different.

| family | instruction cases | load/store cases |
|---|---|---|
| `picorv32/` | `rvfi_insn_check.sv` (2 asserts: rd/pc) | `rvfi_insn_check_mem.sv` (1 assert: mem addr) |
| `picorv32_fullcheck/` | `rvfi_insn_check_origin.sv` (20 asserts) | same full checker |

The full checker adds the checks that the reduced CIll checker drops:

- `rvfi_rd_addr`, `rvfi_rs1_addr`, `rvfi_rs2_addr` and operand data;
- `rvfi_mem_addr`, `rvfi_mem_rmask`, `rvfi_mem_wmask` and byte data;
- `rvfi_trap` and memory-fault reporting;
- CSR `misa` read masks (when enabled).

It does not add the upstream PMA-map/covers/multi-channel wrapper logic; it is
the self-contained full-property adaptation shipped in
`../riscv-formal/rvfi_insn_check_origin.sv`. For the upstream Makefile flow use
`../../baselines/cill/deps/riscv-formal/cores/picorv32`.

## Build

```sh
cd insn_add
./run.sh
```

As in the original family, `run.sh` runs `ric3 build` and prints the BTOR
sha256. With the current tree the full checker produces **15 bad / 5
constraints** per case, versus **2 bad / 4 constraints** for the reduced
instruction checker and **1 bad / 4 constraints** for the memory-only checker.
Those counts make the two families easy to tell apart in a report.

## Regenerate

```sh
python3 make_fullcheck_cases.py          # rewrite all 73 case dirs
python3 make_fullcheck_cases.py --check  # dry run
```

The script reads `../picorv32/manifest.csv` for the source locations and copies
only the files listed in each `ric3.toml` (plus `run.sh` and `.gitignore`), then
overwrites `rvfi_insn_check.sv` with
`../riscv-formal/rvfi_insn_check_origin.sv`.

`picorv32_full` is the preserved *case set*; `picorv32_fullcheck` is the full
*property checker* over both case sets. They are not the same thing.
