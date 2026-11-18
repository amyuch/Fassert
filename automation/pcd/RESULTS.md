# Results

The artifact bundles **24** cases: **12** with self-contained offline evidence and **12** complete source cases for the normal build and discharge flow.

The `bundle` column is descriptive, not a requirement:

- `offline`: the case has a self-contained evidence package under `evidence/`; `./pcd bench suites/offline.json` rechecks it without an engine.

- `source`: the case is included with complete inputs and a build recipe; it runs through the normal `e2e` flow.

- `—`: the row is an alternate model or smoke duplicate that is not bundled in the artifact.


Alternate rows are retained in this table because the table is a row view, not a function view. The 24 bundled cases are the artifact view; the full local development matrix stays outside the artifact.


| row | family | function | exact status | evidence | obligations | bundle |
|---|---|---|---|---|---|---|
| `nerv_reg` | nerv | reg | proved | exact-extension | 6 | [offline](evidence/nerv_reg/README.md) |
| `picorv32_add_smoke` | picorv32 | add | proved | exact | 6 | — |
| `picorv32_addi_smoke` | picorv32 | addi | proved | exact + official-helper | 38 | — |
| `picorv32_beq_smoke` | picorv32 | beq | proved | exact + official-helper | 43 | — |
| `picorv32_c_j_smoke` | picorv32 | c_j | proved | exact + official-helper | 21 | — |
| `picorv32_mul_smoke` | picorv32 | mul | needs_check | exact (other model) | 32 | — |
| `picorv32_sra` | picorv32 | sra | proved | exact | - | — |
| `nerv_bus_dmem` | nerv | bus_dmem | proved | exact-extension | 4 | [offline](evidence/nerv_bus_dmem/README.md) |
| `nerv_csrw_mstatus` | nerv | csrw_mstatus | proved | exact | - | [source](cases/nerv_csrw_mstatus/case.json) |
| `picorv32_auipc` | picorv32 | auipc | proved | exact | - | [source](cases/picorv32_auipc/case.json) |
| `picorv32_bge` | picorv32 | bge | proved | exact | - | — |
| `picorv32_bgeu` | picorv32 | bgeu | proved | exact | - | — |
| `picorv32_blt` | picorv32 | blt | proved | exact | - | — |
| `picorv32_bne` | picorv32 | bne | proved | exact | - | [source](cases/picorv32_bne/case.json) |
| `picorv32_c_add` | picorv32 | c_add | proved | exact | - | — |
| `picorv32_div` | picorv32 | div | needs_check | corrected-contract | 54 | [offline](evidence/picorv32_div/README.md) |
| `picorv32_jal` | picorv32 | jal | proved | exact + official-helper | 32 | — |
| `picorv32_jalr` | picorv32 | jalr | proved | exact | - | [source](cases/picorv32_jalr/case.json) |
| `picorv32_lui` | picorv32 | lui | proved | exact | - | [source](cases/picorv32_lui/case.json) |
| `picorv32_lw` | picorv32 | lw | proved | exact | - | [source](cases/picorv32_lw/case.json) |
| `picorv32_mulh` | picorv32 | mulh | needs_check | helper-model | 30 | [offline](evidence/picorv32_mulh/README.md) |
| `picorv32_rem_core` | picorv32 | rem | needs_check | corrected-contract | 48 | — |
| `picorv32_remu` | picorv32 | remu | proved | exact | 80 | [offline](evidence/picorv32_remu/README.md) |
| `picorv32_sltu` | picorv32 | sltu | proved | exact | - | [source](cases/picorv32_sltu/case.json) |
| `picorv32_sw` | picorv32 | sw | proved | exact (clean package) | 4 | [offline](evidence/picorv32_sw/README.md) |
| `picorv32_xor` | picorv32 | xor | proved | exact | - | [source](cases/picorv32_xor/case.json) |
| `serv_causal` | serv | causal | proved | exact | - | [source](cases/serv_causal/case.json) |
| `serv_pc_fwd` | serv | pc_fwd | proved | exact | - | [source](cases/serv_pc_fwd/case.json) |
| `picorv32_addi_official` | picorv32 | addi | needs_check | helper-model | 38 | [offline](evidence/picorv32_addi_official/README.md) |
| `picorv32_beq_official` | picorv32 | beq | needs_check | helper-model | 43 | [source](cases/picorv32_beq_official/case.json) |
| `picorv32_c_j_official` | picorv32 | c_j | needs_check | helper-model | 21 | [source](cases/picorv32_c_j_official/case.json) |
| `picorv32_divu_official` | picorv32 | divu | proved | original-RTL PC/RD | 54 | [offline](evidence/picorv32_divu_official/README.md) |
| `picorv32_jal_official` | picorv32 | jal | needs_check | helper-model | 32 | [offline](evidence/picorv32_jal_official/README.md) |
| `picorv32_mulh_official` | picorv32 | mulh | needs_check | helper-model + cill caveat | 31 | — |
| `picorv32_add` | picorv32 | add | proved | exact | 6 | [offline](evidence/picorv32_add/README.md) |
| `picorv32_mul` | picorv32 | mul | proved | exact | 32 | [offline](evidence/picorv32_mul/README.md) |
| `picorv32_rem` | picorv32 | rem | proved | corrected-contract | 48 | [offline](evidence/picorv32_rem/README.md) |

Every row listed above is functionally `proved`; the `exact status` column is
the separate exactness axis. It can be `needs_check` where the functional contract
is corrected or a helper/transfer residual remains, while the architectural
contract is still discharged.

## Notes

- `picorv32_div` and `picorv32_rem` are the exact-input corrected-contract packages; the corresponding core rows with the original contract remain open and are not bundled.

- `picorv32_remu` and `picorv32_mulh` use the exact row evidence; `picorv32_mulh` carries six K7 warnings for non-primary nodes outside the target derivation, as recorded in its `check.json`.

- `picorv32_divu_official` retains the original official RTL and closes the PC/RD gap with a checked quotient induction. The helper-model official rows are represented by `picorv32_addi_official` and `picorv32_jal_official`.

- `picorv32_add`, `picorv32_mul`, `picorv32_remu`, and `picorv32_sw` are exact packages. `nerv_reg` and `nerv_bus_dmem` are exact observer extensions.

- The source bundle includes official `beq`/`c_j`, core branches, loads, jumps, and SERV/NERV cases. Those cases use the normal build and discharge path.


See [`README.md`](README.md) for the offline commands and [`docs/`](docs/) for the flow documentation.
