# picorv32_divu_official offline evidence

- Case: [`cases/picorv32_divu_official`](../../cases/picorv32_divu_official)
- Function: `divu`
- Evidence class: original-RTL PC/RD
- Kernel result: `proved`
- Obligations: 54

This package contains the frozen case, proof, referenced models, proof-bound
replay logs, and the checked result. It is self-contained for an offline kernel
check; no engine or rebuild is used.

```sh
./pcd check --case evidence/picorv32_divu_official/case.json --proof evidence/picorv32_divu_official/proof.json
```
