# picorv32_full

Preserved picorv32 cases that are not in the active benchmark set. They are
complete, materialized cases and each one still has its own `ric3.toml` and
`run.sh`; they are simply excluded from the active 43-case corpus.

The authoritative list, including groups, semantics, and reasons for the active
selection, is `../picorv32/manifest.csv`.

This directory mainly contains:

- remaining ALU logical/shift variants (`or`/`ori`, `xori`, `srl`/`srli`,
  `srai`); `xor` and `sra` were promoted to the active corpus;
- compressed-instruction variants not chosen as representatives
  (`c_addi`, `c_*`, `c_jr`, …);
- halfword and unsigned-byte memory variants (`lbu`, `lh`, `lhu`, `sh`).

Run a preserved case directly if needed:

```sh
cd insn_or
./run.sh
```

These cases use the same reduced CIll checker as `../picorv32`. The
full-property counterpart for every preserved case is in
`../picorv32_fullcheck/<case>/`.
