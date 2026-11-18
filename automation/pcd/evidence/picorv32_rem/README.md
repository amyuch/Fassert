# picorv32_rem offline evidence

- Case: [`cases/picorv32_rem`](../../cases/picorv32_rem)
- Function: `rem`
- Evidence class: corrected-contract
- Kernel result: `proved`
- Obligations: 48

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_rem/case.json --proof evidence/picorv32_rem/proof.json
```
