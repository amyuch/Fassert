# picorv32_add offline evidence

- Case: [`cases/picorv32_add`](../../cases/picorv32_add)
- Function: `add`
- Evidence class: exact
- Kernel result: `proved`
- Obligations: 6

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_add/case.json --proof evidence/picorv32_add/proof.json
```
