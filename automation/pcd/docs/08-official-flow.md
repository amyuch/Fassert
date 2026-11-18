# Official riscv-formal case flow

Official cases are imported from a `ric3.toml` source list. The importer copies
only the declared verifier-facing surface, preserves relative subdirectories,
and leaves out `ric3proj/`, prior runs, `oracle/`, and helper proofs. A complete
proof package can then be bound to the imported case for an offline check.

## Import

The benchmark tree is external data for the artifact. Pass its directory to the
importer:

```sh
./pcd import-benchmark <benchmark-dir>/insn_addi picorv32_addi_official

# Multi-family tree: --family qualifies the generated case id.
./pcd import-benchmark <benchmark-dir>/reg nerv_reg --family nerv
```

The generated case has this shape:

```
cases/picorv32_addi_official/
  case.json
  input/rtl/{insn_addi.v,rvfi_insn_check.sv,picorv32.sv,wrapper.sv,tb.sv,defines.sv,rvfi_macros.vh}
  build/{ric3.toml,build.sh}
```

The target is the imported model's full checker surface. The template planner
uses the trusted `cill` backend by default, and every per-property verdict is a
`REPLAY` certificate; `cill` is not used as a diagnostic here.

## Offline packages

The artifact bundles official evidence for `addi`, `jal`, and `divu`. The
`beq` and `c_j` official cases are included as complete source cases in
`cases/` and in `suites/selected.json`; running them uses the normal build and
discharge flow.

| case | offline package | obligations | evidence |
|---|---|---|---|
| `picorv32_addi_official` | `evidence/picorv32_addi_official` | 38 | helper-model cill |
| `picorv32_jal_official` | `evidence/picorv32_jal_official` | 32 | helper-model cill |
| `picorv32_divu_official` | `evidence/picorv32_divu_official` | 54 | helper cill + checked quotient induction |

The packages carry the official RVFI property surface plus the helper facts that
close the non-inductive PC/result properties. Each package has
`acceptance: "complete"` and an empty target TCB. The official source hashes are
retained, and the helper build scripts use only naming labels for hierarchical
observation; they do not add logic, assumptions, or state.

## Suite binding

`suites/official_isa.json` binds the official offline cases to their evidence
packages:

```json
{
  "provenance": "official",
  "cases": [
    "picorv32_addi_official",
    "picorv32_jal_official",
    "picorv32_divu_official"
  ],
  "proof_packages": {
    "picorv32_addi_official": "evidence/picorv32_addi_official",
    "picorv32_jal_official": "evidence/picorv32_jal_official",
    "picorv32_divu_official": "evidence/picorv32_divu_official"
  }
}
```

`pcd bench` resolves package paths relative to the suite file, the PCD root, or
the current directory. With `provenance: "official"`, it also checks that the
official `spec`, `checker`, and `rtl` sources are byte-identical in the package.
The independent kernel check then validates the proof. A package rejection is
reported as `REJECT` with the kernel errors; it is never counted as an engine
result.

The offline suites set `provenance: "none"` because their helper models
intentionally use observation labels while the kernel checks the exact bound
proof. The kernel result, model hashes, and replay logs are still checked.

## Recheck

```sh
./pcd check --case evidence/picorv32_addi_official/case.json \
            --proof evidence/picorv32_addi_official/proof.json

./pcd bench suites/offline.json
./pcd bench suites/official_isa.json
```

`bench` writes fresh checks beside its result and never edits a frozen package.
The current accepted rows and bundled status are in
[`../RESULTS.md`](../RESULTS.md).
