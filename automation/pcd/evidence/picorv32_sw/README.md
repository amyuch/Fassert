# picorv32_sw offline evidence

- Case: [`cases/picorv32_sw`](../../cases/picorv32_sw)
- Function: `sw`
- Evidence class: exact (clean package)
- Kernel result: `proved`
- Obligations: 4

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_sw/case.json --proof evidence/picorv32_sw/proof.json
```
