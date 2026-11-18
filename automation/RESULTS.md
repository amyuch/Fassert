# RESULTS: core and full benchmark tiers

This is a frozen result snapshot from before the v0.4 semantic composition
guard. Existing local evidence is preserved; its stored ACCEPT values do not
override current validation. Recheck packages with the current PCD kernel;
model-transfer and arithmetic-lifting gaps are now reported as incomplete.
See `pcd/docs/09-composition-guard.md`.

This report is the frozen, case-by-case record for the 30 core cases in
`benchmarks/testlist.csv` and the five full cases in
`benchmarks/testlist_full.csv`. It includes failures and timeouts, not only
accepted proofs.

Rows: **35 = 30 core + 5 full**. Primary artifact paths
are relative to the automation root. Every case was attempted; no row is
`NOT_RUN` or `ERROR`.

## Result classes

- `fresh-pcd`: a new PCD end-to-end run, including a fresh engine call and PCD kernel acceptance or rejection.
- `fresh-pcd-helper`: the same, with fresh helper assertions added as case inputs. Helper assertions are not counted as accepted design lemmas by themselves.
- `fresh-pcd-complete`: a fresh case-local complete PCD package, including a fresh engine run, a checked decomposition/induction, and PCD kernel acceptance. It is not a fresh core-full scan; the separate fresh core scan artifact is still named when one exists.
- `fresh-pcd-timeout`: the engine consumed its budget; no kernel acceptance exists.
- `fresh-env-check`: a fresh rIC3 check of an official core wrapper. The environment is a checker TCB, not a design fact. The primary active-pending rows use only the documented instruction-source constraint; seven restored rows use an explicit functional-only `instruction source + pending=0` TCB. PCD kernel acceptance was not run; this class can be REJECT (CEX or Not Inductive) or ACCEPT under a labeled TCB.
- `package-check`: a frozen full-tier package replayed through `./pcd bench` and its kernel. No fresh engine run is counted.
- `prior-pcd-complete`: a prior complete PCD package replayed and kernel-checked now. It is prior-package evidence, not a fresh core engine run; the original fresh REJECT/TIMEOUT artifact is preserved in the notes and in the prior-evidence section.
- `prior-proof-graph`: a prior decomp integration proof graph rechecked with `decomp/kernel.py`. It is not a fresh PCD run and may carry a labeled front-end TCB.
- `prior-experiment-inferred`: prior helper/model facts plus a checked arithmetic bridge, reused by analogy when no complete package exists. This is the weakest class; it is not a kernel-accepted complete proof.

## Summary

| tier | rows | result counts |
|---|---:|---|
| core | 30 | ACCEPT=28, REJECT=2 |
| full | 5 | ACCEPT=5 |

Evidence classes: `fresh-env-check`=8, `fresh-pcd`=3, `fresh-pcd-complete`=1, `fresh-pcd-helper`=15, `package-check`=5, `prior-experiment-inferred`=0, `prior-pcd-complete`=2, `prior-proof-graph`=1 (sum=35).

## Table

| case | verdict | evidence | kernel | engine | tcb | time_s | engine_s | tried | inv | attempts | primary artifact |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `picorv32/insn_auipc` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 241.66 | 239.29 | 1 | 20 | 6 | `pcd/runs/core_full/helpers/core_picorv32_insn_auipc/20261102T085028Z-core_picorv32_insn_auipc-14528d` |
| `picorv32/insn_bge` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 260.93 | 258.73 | 1 | 25 | 3 | `pcd/runs/core_full/helpers/core_picorv32_insn_bge/20261102T084620Z-core_picorv32_insn_bge-8e3a14` |
| `picorv32/insn_bgeu` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 260.38 | 258.3 | 1 | 25 | 2 | `pcd/runs/core_full/helpers/core_picorv32_insn_bgeu/20261102T085057Z-core_picorv32_insn_bgeu-9c0660` |
| `picorv32/insn_blt` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 263.19 | 261.22 | 1 | 25 | 2 | `pcd/runs/core_full/helpers/core_picorv32_insn_blt/20261102T085057Z-core_picorv32_insn_blt-da60c0` |
| `picorv32/insn_bne` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 262.09 | 260.1 | 1 | 25 | 2 | `pcd/runs/core_full/helpers/core_picorv32_insn_bne/20261102T085057Z-core_picorv32_insn_bne-dc5634` |
| `picorv32/insn_c_add` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 263.46 | 261.46 | 1 | 23 | 4 | `pcd/runs/core_full/helpers/core_picorv32_insn_c_add/20261102T084620Z-core_picorv32_insn_c_add-e3130c` |
| `picorv32/insn_div` | **ACCEPT** | `prior-proof-graph` | yes (decomp kernel) | no | 1 (O0_frontend) | - | - | 0 | 1 | 3 | `decomp/cases/div/proof_graph.json` |
| `picorv32/insn_jal` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 196.18 | 194.38 | 1 | 15 | 8 | `pcd/runs/core_full/helpers/core_picorv32_insn_jal/20261102T112240Z-core_picorv32_insn_jal-d3a2c6` |
| `picorv32/insn_jalr` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 216.26 | 214.29 | 1 | 17 | 4 | `pcd/runs/core_full/helpers/core_picorv32_insn_jalr/20261102T083704Z-core_picorv32_insn_jalr-f6c1b7` |
| `picorv32/insn_lui` | **ACCEPT** | `fresh-pcd` | yes | yes | 0 | 91.23 | 90.63 | 1 | 0 | 1 | `pcd/runs/core_full/scan/core_picorv32_insn_lui/20261102T082947Z-core_picorv32_insn_lui-7540e5` |
| `picorv32/insn_lw` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 187.94 | 186.51 | 1 | 15 | 3 | `pcd/runs/core_full/helpers/core_picorv32_insn_lw/20261102T112606Z-core_picorv32_insn_lw-b94a72` |
| `picorv32/insn_mulh` | **ACCEPT** | `prior-pcd-complete` | yes (PCD kernel) | no | 0 design (PCD root; no TCB) | - | - | 0 | 27 | 4 | `pcd/experiments/mulh_complete` |
| `picorv32/insn_rem` | **ACCEPT** | `prior-pcd-complete` | yes (PCD kernel) | no | 0 design (ISA rem model TCB) | - | - | 0 | 16 | 3 | `pcd/experiments/rem_complete` |
| `picorv32/insn_remu` | **ACCEPT** | `fresh-pcd-complete` | yes | yes | 0 design (ISA REMU model TCB) | 194.63 | 194.63 | 3 | 17 | 1 | `pcd/experiments/remu_complete` |
| `picorv32/insn_sltu` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 253.63 | 251.47 | 1 | 23 | 2 | `pcd/runs/core_full/helpers/core_picorv32_insn_sltu/20261102T085057Z-core_picorv32_insn_sltu-8d0aec` |
| `picorv32/insn_sw` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 196.8 | 195.36 | 1 | 17 | 3 | `pcd/runs/core_full/helpers/core_picorv32_insn_sw/20261102T112917Z-core_picorv32_insn_sw-ea33ce` |
| `picorv32/insn_xor` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 261.98 | 259.95 | 1 | 23 | 2 | `pcd/runs/core_full/helpers/core_picorv32_insn_xor/20261102T083335Z-core_picorv32_insn_xor-8f7873` |
| `serv/causal` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 91.42 | 90.82 | 1 | 1 | 2 | `pcd/runs/core_full/helpers/core_serv_causal/20261102T144938Z-core_serv_causal-5af04e` |
| `serv/pc_bwd` | **REJECT** | `fresh-pcd` | yes | yes | 0 | 86.07 | 85.46 | 1 | 0 | 1 | `pcd/runs/core_full/scan/core_serv_pc_bwd/20261102T083254Z-core_serv_pc_bwd-306649` |
| `serv/pc_fwd` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 102.66 | 102.16 | 1 | 3 | 2 | `pcd/runs/core_full/helpers/core_serv_pc_fwd/20261102T145113Z-core_serv_pc_fwd-f73988` |
| `nerv/bus_dmem` | **ACCEPT** | `fresh-pcd-helper` | yes | yes | 0 | 79.23 | 77.42 | 1 | 3 | 2 | `pcd/runs/core_full/helpers/core_nerv_bus_dmem/20261102T150031Z-core_nerv_bus_dmem-87e4fb` |
| `nerv/csrw_mstatus` | **ACCEPT** | `fresh-pcd` | yes | yes | 0 | 38.45 | 35.82 | 1 | 0 | 1 | `pcd/runs/core_full/scan/core_nerv_csrw_mstatus/20261102T083302Z-core_nerv_csrw_mstatus-1f1895` |
| `flute/ADDI` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 153 | 153 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/flute_addi` |
| `flute/BNE` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 129 | 129 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/flute_bne` |
| `flute/JAL` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 128 | 128 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/flute_jal` |
| `flute/SB` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 127 | 127 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/flute_sb` |
| `piccolo/ANDI` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 49 | 49 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/piccolo_andi` |
| `piccolo/BEQ` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 44 | 44 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/piccolo_beq` |
| `piccolo/JAL` | **ACCEPT** | `fresh-env-check` | no | yes | 1 (instruction source + pending=0) | 43 | 43 | 2 | 0 | 4 | `pcd/runs/core_full/env_pending0/piccolo_jal` |
| `piccolo/LB` | **REJECT** | `fresh-env-check` | no | yes | 1 (instruction-source BFM only) | - | - | 2 | 0 | 4 | `pcd/runs/core_full/env/piccolo_lb` |
| `official/picorv32_insn_addi` | **ACCEPT** | `package-check` | yes | no | 0 (package TCB list empty) | - | - | 0 | 1 | 1 | `pcd/experiments/official_suite/addi` |
| `official/picorv32_insn_beq` | **ACCEPT** | `package-check` | yes | no | 0 (package TCB list empty) | - | - | 0 | 1 | 1 | `pcd/experiments/official_suite/beq` |
| `official/picorv32_insn_c_j` | **ACCEPT** | `package-check` | yes | no | 0 (package TCB list empty) | - | - | 0 | 1 | 1 | `pcd/experiments/official_suite/c_j` |
| `official/picorv32_insn_jal` | **ACCEPT** | `package-check` | yes | no | 0 (package TCB list empty) | - | - | 0 | 1 | 1 | `pcd/experiments/official_suite/jal` |
| `official/picorv32_insn_mulh` | **ACCEPT** | `package-check` | yes | no | 0 (package TCB list empty) | - | - | 0 | 2 | 1 | `pcd/experiments/mulh_complete` |

## What was actually run

- The core diagnostic scan is in `pcd/runs/core_full/scan/`; fresh core scan/helper rows name their exact run directory. The REMU `fresh-pcd-complete` row names its package and separately preserves its core scan REJECT artifact.
- Helper trials are in `pcd/runs/core_full/helpers/`; the helper sources are in `pcd/experiments/core_full/helpers/` and the SERV/NERV closure cases in `pcd/experiments/serv_closure/` and `pcd/experiments/nerv_closure/`.
- The JAL, LW, and SW helper blocks are the previously accepted helper-only sets (15, 15, and 17 assertions); they were replayed as fresh case inputs, not reused as proof artifacts.
- Three arithmetic rows use prior-experiment evidence, explicitly labeled `prior-*`: DIV (`decomp/cases/div/proof_graph.json`), REM (`pcd/experiments/rem_complete`), and MULH (`pcd/experiments/mulh_complete`). The fresh core REJECT/TIMEOUT artifacts are named in each row and in the prior-evidence section.
- REMU is now a fresh case-local complete package (`pcd/experiments/remu_complete`), not inferred from the REM evidence. It proves all 17 helper facts plus the official PC assertion with cill, proves RD separately by a checked restoring-remainder induction, and is accepted by the PCD kernel with only the official ISA REMU model as TCB. The earlier 35-helper cill timeout is preserved as a diagnostic, and the separate fresh core scan REJECT is still named in the table.
- The eight Flute/Piccolo environment checks are frozen under `pcd/runs/core_full/env/`, each with `wrapper.v`, `helpers_env.sv`, `ric3.toml`, `check.log`, and `evidence.json`.
- The full-tier package check is `pcd/runs/core_full/_bench/20261102T082542Z-270d48.json`.
- The corrected single-issue `pc_bwd` checker experiment is `pcd/experiments/serv_closure/pc_bwd_fixed`; its kernel-accepted run is a checker-correction diagnostic, not an upgrade of the frozen `rvfi_pc_bwd_check` row.
- No prior baseline logs or result trees were used.

## Non-accepted cases

### `serv/pc_bwd` — REJECT

- Evidence: `fresh-pcd`; primary artifact: `pcd/runs/core_full/scan/core_serv_pc_bwd/20261102T083254Z-core_serv_pc_bwd-306649`.
- Attempts counted for this case: 1.
- Note: plain fresh PCD run (template planner); non-proof target/helper: o_pc_rdata; the frozen rvfi_pc_bwd_check is vacuous on a single-issue in-order core: it captures the order+1 pc_rdata after the checked order and has no future channel to inspect; the accepted pc_fwd row proves the equivalent past-facing PC link; a corrected past-facing checker variant is kernel-accepted at pcd/runs/core_full/experiments/core_serv_pc_bwd_fixed/20261103T020154Z-core_serv_pc_bwd_fixed-0be81f, but it is not used to upgrade this frozen-checker row.

### `piccolo/LB` — REJECT

- Evidence: `fresh-env-check`; primary artifact: `pcd/runs/core_full/env/piccolo_lb`.
- Attempts counted for this case: 4.
- Note: corrected fresh rIC3 check with only the documented instruction-source BFM assumption; CEX on normalassert under instruction-source-only BFM environment; trace is interrupt-sensitive and fails p147 (x31) with stale ILA load_data; secondary pending=0 functional-only check proves (env_pending0/piccolo_lb); PCD kernel was not run; the earlier interrupt-free/clean-start check was invalid and is not used; the earlier plain scan also rejected the unconstrained wrapper.


## Fresh complete decomposition: REMU

REMU is a fresh case-local complete package. It is not inferred from the REM
evidence and it is not a fresh core-full scan. The package proves the official PC
property in the same model as 17 REMU helper facts, proves RD separately by a
checked restoring-remainder induction, and is accepted by the PCD kernel with
only the official ISA REMU model as TCB. The prior `prior-experiment-inferred`
row is retired.

### `picorv32/insn_remu` — ACCEPT via `fresh-pcd-complete`

- Primary artifact: `pcd/experiments/remu_complete`; primary model: `btor:a8e22b973c42ca986d7a3bf14f6c1a90e0c59e9705b6e9422da0ae8fe0e11471`.
- Fresh engine: `ric3 cill check` proved all 18 properties inductive (official PC + 17 helpers) in 192 s, 3m14.631 s wall. Log: `pcd/experiments/remu_complete/evidence/rd/check.log`.
- Decomposition: `o_rd_wdata_match` is removed from the cill model and proved by a CHECKED `smt-induction` over the unsigned restoring divider; the root is a CHECKED composition of the replayed PC property and the induced RD property.
- Kernel: `cd pcd && ./pcd check --case experiments/remu_complete/case.json --proof experiments/remu_complete/proof.json` -> ACCEPT, no errors, `tcb_deps: ["isa_remu"]`; saved in `pcd/experiments/remu_complete/check.json`.
- Failure history: the earlier 35-helper cill run hit the 40-minute cap before an induction table and is preserved under `pcd/experiments/remu_complete/evidence/rd/diagnostics`. An intermediate 16-fact trial left `h_remu_div_k` Not Inductive; restoring `h_remu_msk_k` made the final 18-property set inductive.
- Separate fresh core scan: the core-full scan remains REJECT at `pcd/runs/core_full/scan/core_picorv32_insn_remu/20261102T083120Z-core_picorv32_insn_remu-750fe8`; this package is the later decomposed proof, not a relabeling of that scan.
- Secondary artifacts: `pcd/experiments/remu_complete/README.md`, `pcd/experiments/remu_complete/proof.json`, `pcd/experiments/remu_complete/case.json`, `pcd/experiments/remu_complete/manifest.json`, `pcd/experiments/remu_complete/evidence/rd/models/dut.btor`, `pcd/experiments/remu_complete/evidence/rd/input/rtl/helpers_remu.sv`.

## Prior-evidence arithmetic cases

These three core rows were resolved from prior experiments, at the user's direction.
They are not fresh core PCD engine results. The fresh REJECT/TIMEOUT artifact is
preserved for each case, and the evidence class states the strength of the prior
evidence. The full prior-evidence record is `pcd/experiments/core_full/prior_evidence/prior_evidence.json`.

### `picorv32/insn_div` — ACCEPT via `prior-proof-graph`

- Prior evidence artifact: `decomp/cases/div/proof_graph.json`; fresh core artifact: `pcd/runs/core_full/scan/core_picorv32_insn_div/20261102T082946Z-core_picorv32_insn_div-c51663` (fresh verdict: **REJECT**).
- TCB label: 1 (O0_frontend). Kernel included: yes (decomp kernel). Fresh engine run included: no.
- Prior evidence: Prior decomp integration graph root_div (o_rd_wdata_match) and root_pc (o_pc_wdata_match) are both PROVED_TRUSTED. The graph is checked by decomp/kernel.py now. It uses the prior full-core model btor:90040e379a309171d1566b434e3330830269dc8ab0691a7887d3b6da8ff484e1, not a fresh core build. It is integration-level evidence, not a fresh core PCD run, and it carries the O0_frontend front-end TCB.
- Fresh-result caveat: The fresh core PCD scan rejected o_pc_wdata_match and o_rd_wdata_match; a fresh helper trial timed out during inductiveness after a clean BMC. The fresh scan remains the primary record of what the fresh engine actually did.
- Validation: python3 decomp/kernel.py decomp/cases/div/proof_graph.json -> [ACCEPT] (log: prior_evidence/decomp_div.kernel.log)
- Secondary artifacts: `decomp/LEDGER.md`, `decomp/artifact_div_observation.json`, `decomp/artifact_div_rem_bridge.json`, `pcd/experiments/core_full/prior_evidence/decomp_div.kernel.log`.

### `picorv32/insn_mulh` — ACCEPT via `prior-pcd-complete`

- Prior evidence artifact: `pcd/experiments/mulh_complete`; fresh core artifact: `pcd/runs/core_full/scan/core_picorv32_insn_mulh/20261102T082947Z-core_picorv32_insn_mulh-ddabf2` (fresh verdict: **TIMEOUT**).
- TCB label: 0 design (PCD root; no TCB). Kernel included: yes (PCD kernel). Fresh engine run included: no.
- Prior evidence: Prior complete PCD package mulh_complete closes all official RVFI properties, including o_rd_wdata_match and o_pc_wdata_match, with no TCB. Its primary model is btor:40b64410510957ebafee13bc60053b7786d06be1250c07e68e3b0fd0d6a67169. The RTL and ISA spec match the core case byte-for-byte. The package's checker is a richer superset checker (sha256 c66f6f01...), not the core checker (sha256 2a15000e...), so this is package-level prior evidence, not a fresh core run with the core checker.
- Fresh-result caveat: The fresh core PCD scan exhausted its engine budget; a later helper trial rejected its own monitor before the target was closed. The fresh timeout remains the primary record of what the fresh engine actually did.
- Validation: cd pcd && ./pcd check --case experiments/mulh_complete/case.json --proof experiments/mulh_complete/proof.json -> ACCEPT (log: prior_evidence/mulh_complete.check.log)
- Secondary artifacts: `pcd/experiments/mulh_complete/proof.json`, `pcd/experiments/mulh_complete/check.json`, `pcd/experiments/mulh_complete/evidence/pc/check.log`, `pcd/experiments/mulh_complete/evidence/mon/check.log`, `pcd/experiments/mulh_complete/evidence/rd/check.log`, `pcd/experiments/core_full/prior_evidence/mulh_complete.check.log`.

### `picorv32/insn_rem` — ACCEPT via `prior-pcd-complete`

- Prior evidence artifact: `pcd/experiments/rem_complete`; fresh core artifact: `pcd/runs/core_full/scan/core_picorv32_insn_rem/20261102T083115Z-core_picorv32_insn_rem-b49d06` (fresh verdict: **REJECT**).
- TCB label: 0 design (ISA rem model TCB). Kernel included: yes (PCD kernel). Fresh engine run included: no.
- Prior evidence: Prior complete PCD package rem_complete closes both PC and RD with no design TCB; the only TCB dependency is the official ISA REM model. Its primary model is btor:cbe9c6db7d3e7d975e954b0a3bb70298209736d508da2391a41b9edc92791ef3. The checker and ISA spec match the core case byte-for-byte. The packaged RTL differs from the core RTL only by the generate-block label 'begin : pcd_div'; the tb carries the prior helper set. This is prior-package evidence, not a fresh core run.
- Fresh-result caveat: The fresh core PCD scan rejected o_pc_wdata_match and o_rd_wdata_match; a fresh helper trial timed out during inductiveness after a clean BMC. The fresh scan remains the primary record of what the fresh engine actually did.
- Validation: cd pcd && ./pcd check --case experiments/rem_complete/case.json --proof experiments/rem_complete/proof.json -> ACCEPT (log: prior_evidence/rem_complete.check.log)
- Secondary artifacts: `pcd/experiments/rem_complete/proof.json`, `pcd/experiments/rem_complete/evidence/rd/check.log`, `pcd/experiments/rem_complete/evidence/ops/check.log`, `pcd/experiments/core_full/prior_evidence/rem_complete.check.log`.

## Environment-TCB cases

These eight rows have two evidence layers. The active-pending, instruction-source-only
run is the primary check; an earlier helper added undocumented interrupt-free and
clean-start assumptions, so those earlier results are not used. The seven non-LB cases
are restored to ACCEPT only under an explicit functional-only `pending=0` TCB; LB remains
REJECT under the active-pending primary run. All eight also prove under `pending=0`:

- `flute/ADDI` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `flute/BNE` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `flute/JAL` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `flute/SB` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `piccolo/ANDI` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `piccolo/BEQ` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `piccolo/JAL` → **ACCEPT** — functional-only rIC3 proof with the documented instruction source and explicit pending=0 TCB; BMC clean and IC3 inductive; the active-pending instruction-source-only run was BMC-clean but Not Inductive; PCD kernel was not run; pending=0 is an explicit TCB, not a design fact; the earlier plain scan also rejected the unconstrained wrapper.
- `piccolo/LB` → **REJECT** — corrected fresh rIC3 check with only the documented instruction-source BFM assumption; CEX on normalassert under instruction-source-only BFM environment; trace is interrupt-sensitive and fails p147 (x31) with stale ILA load_data; secondary pending=0 functional-only check proves (env_pending0/piccolo_lb); PCD kernel was not run; the earlier interrupt-free/clean-start check was invalid and is not used; the earlier plain scan also rejected the unconstrained wrapper.

### LB functional-only check

The primary `piccolo/LB` row remains **REJECT**: the documented environment constrains only the instruction source, and under it cill finds a concrete CEX (not a CTI). Trace inspection shows the failure is `variable_map_assert__p147__` for `x31` at `__IEND__` with an interrupt taken; the design write matches the actual dmem response, while the ILA `load_data` is stale from the start cycle. So it is an interrupt-sensitive ILA/load-data observation artifact, not evidence of a bad LB datapath result.

A secondary check adds an explicit `interrupt_pending == 0` TCB (no clean-start assumption); it is BMC-clean and proves in 42 s. The evidence is `pcd/runs/core_full/env_pending0/piccolo_lb/`. All eight Flute/Piccolo cases prove under this functional-only TCB; the seven non-LB rows use it as their primary evidence, while LB keeps its active-pending CEX as primary.

## Full-tier package check

The five full cases were verified by replaying their frozen complete packages and
running the PCD kernel. `engine_included=no` is intentional: these are package
checks, not fresh planner/engine runs. The accepted packages are:

- `official/picorv32_insn_addi` → `pcd/experiments/official_suite/addi` (ACCEPT).
- `official/picorv32_insn_beq` → `pcd/experiments/official_suite/beq` (ACCEPT).
- `official/picorv32_insn_c_j` → `pcd/experiments/official_suite/c_j` (ACCEPT).
- `official/picorv32_insn_jal` → `pcd/experiments/official_suite/jal` (ACCEPT).
- `official/picorv32_insn_mulh` → `pcd/experiments/mulh_complete` (ACCEPT).

Important: the full `jal` and `mulh` packages are accepted here only as
frozen-package kernel checks. The fresh core `jal` row is also ACCEPT, but from
its own helper-instrumented PCD run, not from this package check. The core
`mulh` row is ACCEPT only through the same prior complete package, labeled
`prior-pcd-complete`; its fresh core scan remains TIMEOUT and is preserved in
the prior-evidence section. The package check does not replace that timeout.

## Reproduce

```sh
cd pcd
./pcd e2e experiments/core_full/cases/<case> --planner template --runs-dir runs/core_full/helpers --engine-seconds 420
./pcd bench --suite suites/core_full_full.json

# environment-TCB checks
cd runs/core_full/env/<case> && ric3 build && ric3 cill check
```

## Honesty limits

- A helper trial that rejects a helper assertion is not reported as a design counterexample.
- A timeout is not a proof and is not reported as an acceptance.
- The environment checks do not claim kernel acceptance.
- The full-tier rows do not claim fresh engine evidence.
- Rows labeled `prior-*` are not fresh core engine runs. They cite prior packages, graphs, or an explicit inference and preserve the fresh REJECT/TIMEOUT artifact. No current row uses `prior-experiment-inferred`; REMU moved to `fresh-pcd-complete`.
- The REMU `fresh-pcd-complete` row is a fresh case-local complete package, not a relabeling of the separate fresh core scan. That core scan remains REJECT and is preserved in the row and in this report.
- `RESULTS.csv` is the machine-readable source of truth; this Markdown is a human-readable view of the same rows.
- A checker-correction experiment is not reported as acceptance of the frozen checker; `serv/pc_bwd` remains REJECT for `rvfi_pc_bwd_check`.

