# picorv32_div offline evidence

- Case: [`cases/picorv32_div`](../../cases/picorv32_div)
- Function: `div`
- Evidence class: corrected-contract
- Kernel result: `proved`
- Obligations: 54

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_div/case.json --proof evidence/picorv32_div/proof.json
```
