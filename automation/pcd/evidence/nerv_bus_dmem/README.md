# nerv_bus_dmem offline evidence

- Case: [`cases/nerv_bus_dmem`](../../cases/nerv_bus_dmem)
- Function: `bus_dmem`
- Evidence class: exact-extension
- Kernel result: `proved`
- Obligations: 4

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/nerv_bus_dmem/case.json --proof evidence/nerv_bus_dmem/proof.json
```
