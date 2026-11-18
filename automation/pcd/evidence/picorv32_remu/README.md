# picorv32_remu offline evidence

- Case: [`cases/picorv32_remu`](../../cases/picorv32_remu)
- Function: `remu`
- Evidence class: exact
- Kernel result: `proved`
- Obligations: 80

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_remu/case.json --proof evidence/picorv32_remu/proof.json
```
