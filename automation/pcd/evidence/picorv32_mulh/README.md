# picorv32_mulh offline evidence

- Case: [`cases/picorv32_mulh`](../../cases/picorv32_mulh)
- Function: `mulh`
- Evidence class: helper-model
- Kernel result: `proved`
- Obligations: 30

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_mulh/case.json --proof evidence/picorv32_mulh/proof.json
```
