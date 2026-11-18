# picorv32_mul offline evidence

- Case: [`cases/picorv32_mul`](../../cases/picorv32_mul)
- Function: `mul`
- Evidence class: exact
- Kernel result: `proved`
- Obligations: 32

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_mul/case.json --proof evidence/picorv32_mul/proof.json
```
