# ADD — first workflow transfer case beyond MUL/DIV/REM

PicoRV32 `insn_add` (base ALU, **non-PCPI**). Target: `o_rd_wdata_match`,
`o_pc_wdata_match`.

## Baseline (empty helpers, real RTL, CIll)

```
o_pc_wdata_match  Not Inductive
o_rd_wdata_match  Not Inductive
```

BMC found no CEX (bounded). The CTI (selected on `o_rd`) shows the retiring ADD
with the writeback/RVFI linkage unconstrained (and an abstract `cpu_state`),
i.e. the gap is **observation/control**, not arithmetic.

## Proposed decomposition (planner; derived from the CTI + RTL)

- control facts: trap/dbg clearing, no spec_valid during trap, no dbg_irq_call,
  no add+sub, dbg_add implies instr_add;
- `op_data`: on an ADD writeback `cpuregs_wrdata == dbg_rs1val + dbg_rs2val`;
- writeback shadow (`wb_valid/rd/rs1/rs2/wdata`) and `wb_consistent`:
  `wb_wdata == wb_rs1 + wb_rs2`;
- `operand_id`: spec `rvfi_rs1/rs2_rdata` equal the captured operands at retire;
- `dest_id`: `rvfi_rd_addr == rvfi_insn[11:7]`;
- `retire_align`: `spec_valid ⇒ wb_valid ∧ rvfi_rd_wdata == (wb_rd ? wb_wdata : 0)`;
- `pc_link`: for a retiring ADD `rvfi_pc_wdata == rvfi_pc_rdata + 4`.

This mirrors the MUL/DIV observation discipline (writeback shadow + operand
identity + destination identity) with a trivial arithmetic core.

## Outcome

- CIll (`ric3 cill check`) with the proposed helpers: BMC clean, **all properties
  inductive, proof succeeded (154 s)**; model
  `btor:a4dfde202ade2ee0d9a9d2c7ec29a28359998bbc92e6c4bf0b8c3b6391169597`.
- Proof graph `proof_graph.json` **ACCEPT** by `kernel.py` (included in
  `--selftest`).

## Why this matters

This is the first case beyond MUL/DIV/REM: the workflow transfers to a simpler,
non-PCPI ALU instruction where the difficulty is the architectural
observation/control linkage rather than a multi-cycle arithmetic closure.
It supports the failure-taxonomy hypothesis (here: composition/observation gap
→ contract/shadow, not algebra), within the same trust boundary
(`PROVED_TRUSTED` CIll, O0 TCB).
