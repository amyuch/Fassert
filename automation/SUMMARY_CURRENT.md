# Current PCD functional proof status

Date: 2026-11-07

This snapshot answers the functional question: **is the instruction/feature
proved?** It replaces the exact-input-only headline of the 2026-11-06 snapshot.
Exact original-file hashes are no longer required for the functional verdict;
the evidence class is recorded explicitly. The strict exact-input matrix is
still preserved as a reference and as `exact_status` in
`RESULTS_CURRENT.csv` and
`pcd/experiments/formal_reproof/results-20261106-clean-exact-all/results.json`
(28 proved / 20 needs_check / 1 reject). The earlier
`results-20261106-current/results.json` is the 24/24/1 snapshot.

## Headline

**Function view: 29 of 41 functions proved; 12 open.**

- `picorv32`: 24 / 24 proved.
- `nerv`: 3 / 3 proved.
- `serv`: 2 / 4 proved. Open: `pc_bwd`, `reg`.
- `flute`: 0 / 5 proved.
- `piccolo`: 0 / 5 proved.

**Case-row view: 37 of 49 rows functionally proved; 12 open.** The 12 open rows
are exactly the 12 open flute/piccolo/SERV functions. The other eight rows are
alternate models of functions that are already proved.

**Strict exact-input matrix (reference only): 28 proved / 20 needs_check / 1
reject (49).** There are 9 exact-input `needs_check` rows whose function is
proved by helper, corrected-contract, or exact-extension evidence. That gives
`28 + 9 = 37` functionally proved rows and `21 - 9 = 12` functionally open
rows.

## Acceptance boundary

- A function is counted **proved** only when a kernel check returns
  `status == "proved"` for a package that binds that function. There is no
  partial credit for `needs_check`.
- A helper-based model is acceptable for the functional claim. The helper is a
  proof-only monitor/extension; the design RTL, spec, and checker are not
  weakened. The exact-input row is still tracked separately.
- A corrected-contract package counts for the function when the original
  frontend lowering was wrong, but it is labelled **corrected-contract**, not
  original-contract proof.
- A proof with a nonempty TCB is **not** counted. This is why the flute and
  piccolo fresh-environment checks and the SERV `reg` decomposition remain open.
- Arithmetic uses model-bound SMT (`btor-smt`, CVC5/Z3/Bitwuzla), never ric3.
  ric3/cill is used for control/retirement facts and the MULH full-surface
  caveat is labelled.
- Official full-surface completeness is tracked separately from the function
  verdict. A PC/RD proof can prove the instruction function while leaving the
  four official memory properties open.

### Evidence classes

| class | counted? | meaning |
|---|---|---|
| `exact` | yes | Original input set unchanged; kernel proved. |
| `helper-model` | yes (function) | Proof-only monitor/helper assertions or a proof-local helper extension; design RTL unchanged. The exact-input row stays separately recorded. |
| `exact-extension` | yes | Clean model is a byte-identical prefix; observer states/assertions are appended; a checked projection transfers the target back to the clean model. Original input set unchanged. |
| `corrected-contract` | yes (corrected function) | Corrects the original frontend/spec to match the RTL's actual signed/unsigned semantics. Not an original-contract proof. |
| `original-RTL PC/RD` | yes for the function, no for the full official surface | Original RTL is retained; only PC/RD retirement is proved. |
| `TCB` | no | Fresh-environment or decomposition proof with a nonempty TCB. |
| `needs_check` | no | Open obligation. |
| `reject` | no | Counterexample. |

Two helper patterns are kept distinct:

- **`exact-extension`** appends observer states/assertions to a byte-identical
  prefix of the clean model and transfers the target back by a checked
  projection. The original model is covered, so this can upgrade the exact
  matrix (as it does for NERV).
- **`helper-model`** proves the function on a helper-augmented model with
  proof-only monitor assertions. The design RTL is unchanged, but the exact
  input file set is not the same. The function verdict is accepted under this
  policy; the exact-input row is explicitly **not** upgraded. MULH and the
  official ADDI/BEQ/C_J/JAL packages are in this class.

## Family summary

| family | functions | proved | open | open functions |
|---|---:|---:|---:|---|
| `picorv32` | 24 | 24 | 0 | — |
| `nerv` | 3 | 3 | 0 | — |
| `serv` | 4 | 2 | 2 | `pc_bwd`, `reg` |
| `flute` | 5 | 0 | 5 | `addi`, `bne`, `jal`, `sb`, `add` |
| `piccolo` | 5 | 0 | 5 | `andi`, `beq`, `jal`, `lb`, `add` |
| **total** | **41** | **29** | **12** | |

Case rows: `picorv32` 32/32, `nerv` 3/3, `serv` 2/4, `flute` 0/5,
`piccolo` 0/5; total 37/49 functionally proved, 12 open.

## What changed in this snapshot

### MULH helper model is now strict-proved

`core/core_picorv32_insn_mulh` is proved by
`results-20261106-helper-dev/mulh-smt-dev` with **30 obligations**, no residual,
no fatal errors, and no TCB. The primary model carries 15 properties (13 helper
monitor assertions plus the two official PC/RD targets); all 13 helper
assertions are in the root closure. `check.json` and `check-recheck.json` agree.

The helper file has 0 `assume`, 0 `force`/`release`, and no writes to
`wrapper.uut.*`; it adds shadow-monitor `always` blocks only. The `tb.sv` diff
is include-only and the `picorv32.sv` diff is a generate-block label only.

The full fifteen-property **official** MULH surface is a separate
`cill_only_caveats` result: `core-mulh-cill-dev-20261106`, 31 obligations,
fourteen checked bit-level projections plus a cill RD replay. It is not
arithmetic-SMT and is not counted as a strict official-surface proof.

### NERV is closed

- `core/core_nerv_bus_dmem`: **exact-extension**, 4 obligations, no TCB. The
  clean BTOR is a byte-identical prefix; the target is proved on an observer
  extension and transferred back by a 276-state identity projection.
- `smoke/smoke_nerv_reg`: **exact-extension**, 6 obligations, no TCB. The
  original input set is unchanged; 171 states are mapped by the two checked
  transfers.
- `core/core_nerv_csrw_mstatus`: **exact**, no TCB.

Both NERV exact-extension packages are selected by the latest
`results-20261106-clean-exact-all` matrix; they close the NERV bus/d-memory and
register rows in that matrix.

### DIV/REM corrections are recorded, not hidden

- `core/core_picorv32_insn_div`: **corrected-contract**, 54 obligations, no TCB.
  The package proves the corrected signed-quotient model. The original core DIV
  row remains open in the exact matrix.
- `core/core_picorv32_insn_rem`: **corrected-contract**, 48 obligations, no TCB.
  `rem-original-20261105` is exact-input for `cases/rem` and uses the documented
  build-time `urem`→`srem` correction. The core exact-input row remains open.
- `official/picorv32_insn_divu`: **original-RTL PC/RD**, 54 obligations, no TCB.
  It keeps the original unsigned `insn_divu.v` and proves
  `o_pc_wdata_match`/`o_rd_wdata_match`. The latest exact matrix selects this
  package and reports the DIVU row as proved; the package target is PC/RD only,
  so the four official memory properties are not in the target and remain a
  surface obligation.
- `core/core_picorv32_insn_remu`: **exact**, 80 obligations, no TCB. This is the
  unsigned original contract and closes the core REMU row.

Corrections are not silent: each corrected package records the correction in
`generation.json` and proves a model-bound link lemma (`link.spec_eq` for the
DIV/REM signed correction; REMU uses `link.spec_def` as a definition lemma)
relating the original expression to the corrected absolute-value/sign formula.
These are discharged external facts, not assumptions.

### Official helper surface

The four official control/ALU rows now have full fifteen-property helper
packages: ADDI 38, BEQ 43, C_J 21, JAL 32 obligations. ADDI's RD addition is
model-bound SMT; the other three use cill for the full surface with the
architectural RD result (zero for BEQ/C_J, PC+4 for JAL) treated as a
control/retirement fact. All are kernel `proved` with no residual and no TCB.

### Helper ledger

`pcd/experiments/formal_reproof/results-20261106-helper-dev/results.json`:

**6 proved / 0 needs_check / 0 reject (6)**.

| case | package | obligations |
|---|---|---:|
| `official/picorv32_insn_addi` | `official-addi-helper-smt-dev-20261106` | 38 |
| `official/picorv32_insn_beq` | `official-beq-helper-dev-20261106` | 43 |
| `official/picorv32_insn_c_j` | `official-c_j-helper-dev-20261106` | 21 |
| `official/picorv32_insn_jal` | `official-jal-helper-dev-20261106` | 32 |
| `core/core_picorv32_insn_sw` | `core-sw-helper-dev-20261106` | 20 |
| `core/core_picorv32_insn_mulh` | `results-20261106-helper-dev/mulh-smt-dev` | 30 |

## Open functions and remaining obligations

| family | function | exact status | why open | remaining obligations |
|---|---|---|---|---|
| `serv` | `pc_bwd` | `needs_check` (frozen row historically REJECT) | The frozen `rvfi_pc_bwd_check` captures the next order on a single-issue core, so the target is vacuous/unreachable. The repaired `pc_bwd_fixed` checker is kernel-accepted but is a diagnostic and does not upgrade the frozen row. | `node.transfer.o_pc_rdata` |
| `serv` | `reg` | `needs_check` | The decomposition is kernel-accepted but has a `bench_env` TCB. | 4 helper assertions, 5 engine obligations, TCB `bench_env` |
| `flute` | `addi`, `bne`, `jal`, `sb` | `needs_check` | Fresh-environment checks only; TCB `instruction source + pending=0`; no kernel acceptance of the frozen case. | `node.property.normalassert`, `node.root` |
| `flute` | `add` | `needs_check` | `bench_env` helper assumption. | `helper.assume.bench_env` |
| `piccolo` | `andi`, `beq`, `jal` | `needs_check` | Fresh-environment checks only; TCB `instruction source + pending=0`; no kernel acceptance. | `node.property.normalassert`, `node.root` |
| `piccolo` | `lb` | `reject` | Engine counterexample on the available package; instruction-source BFM TCB. | `node.property.normalassert`, `node.root` |
| `piccolo` | `add` | `needs_check` | `bench_env` helper assumption. | `helper.assume.bench_env` |

### Surface-only residuals (function proved, official surface not complete)

| case | function verdict | residual |
|---|---|---|
| `official/picorv32_insn_divu` | proved (PC/RD) | `o_mem_addr_match`, `o_mem_rdata_eq_wdata_i`, `o_mem_rmask_set_i`, `o_mem_wdata_match_i` |
| `official/picorv32_insn_mulh` | proved (helper PC/RD; full surface cill-only 31) | the same four memory properties remain open on the strict arithmetic-SMT surface |
| `smoke/smoke_picorv32_insn_mul` | proved by `mul` (exact, 32) | the smoke exact row itself is `needs_check`; it is an alternate model, not a separate function |

## Exact-input matrix reference

The latest full matrix (`results-20261106-clean-exact-all`) contains **49 cases:
28 proved, 20 needs_check, 1 reject**. The 9 exact-input `needs_check` rows that
are functionally proved are:

- `smoke_picorv32_insn_mul` (function proved by the exact `mul` package; the
  smoke row itself remains `needs_check`)
- `core_picorv32_insn_div`
- `core_picorv32_insn_mulh`
- `core_picorv32_insn_rem`
- `official/picorv32_insn_addi`
- `official/picorv32_insn_beq`
- `official/picorv32_insn_c_j`
- `official/picorv32_insn_jal`
- `official/picorv32_insn_mulh`

The remaining 12 open case rows are the 12 open functions listed above:
`21 - 9 = 12`. The `core_piccolo_lb` reject is one of them.

## Boundaries and non-claims

- Corrected DIV/REM packages do **not** prove the original contracts. They prove
  corrected contracts and are labelled accordingly.
- DIVU is proved on the original unsigned RTL, but the package target is
  PC/RD; the four official memory properties are not in the target and are not
  proved.
- Helper-model and corrected-contract rows that are not selected by the
  exact-input matrix do not upgrade it. The strict matrix stays 28/20/1.
  The NERV exact-extension packages are selected and are already counted in the
  28.
- The MULH full official surface is cill-only (31 obligations), not
  arithmetic-SMT. The strict helper MULH result is the 30-obligation PC/RD
  package.
- TCB-based flute/piccolo and SERV `reg` results are not counted as proved.
- The frozen `serv/pc_bwd` row is not upgraded by the corrected-checker
  diagnostic.

## Sources

- Functional table: `RESULTS_CURRENT.csv`, `RESULTS_CURRENT.md`.
- Exact-input matrix: `pcd/experiments/formal_reproof/results-20261106-clean-exact-all/results.json`
  (28 proved / 20 needs_check / 1 reject). The earlier
  `results-20261106-current/results.json` is the 24/24/1 snapshot and is kept
  as history.
- Helper ledger: `pcd/experiments/formal_reproof/results-20261106-helper-dev/results.json`.
- MULH package: `pcd/experiments/formal_reproof/results-20261106-helper-dev/mulh-smt-dev/`.
- NERV closure: `pcd/experiments/nerv_closure/` and
  `pcd/runs/smoke/smoke_nerv_reg/20261106T0940Z-nerv-exact-extension/`.
- SERV closure: `pcd/experiments/serv_closure/`.
- Corrected arithmetic: `div-signed-dev-20261106`, `divu-original-dev-20261106`,
  `rem-signed-dev-20261105`, `rem-original-20261105`,
  `remu-original-20261105`, `rem-qsum-dev-20261105` (the last remains
  `needs_check`).
