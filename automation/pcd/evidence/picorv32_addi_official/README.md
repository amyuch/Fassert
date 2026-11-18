# picorv32_addi_official offline evidence

- Case: [`cases/picorv32_addi_official`](../../cases/picorv32_addi_official)
- Function: `addi`
- Evidence class: helper-model
- Kernel result: `proved`
- Obligations: 38

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_addi_official/case.json --proof evidence/picorv32_addi_official/proof.json
```
