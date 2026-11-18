# nerv_reg offline evidence

- Case: [`cases/nerv_reg`](../../cases/nerv_reg)
- Function: `reg`
- Evidence class: exact-extension
- Kernel result: `proved`
- Obligations: 6

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/nerv_reg/case.json --proof evidence/nerv_reg/proof.json
```
