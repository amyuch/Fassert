# SLTU — CTI-derived transfer case (not copied from res/)

PicoRV32 `insn_sltu` (base ALU). Target: `o_rd_wdata_match`, `o_pc_wdata_match`.

## Baseline (empty helpers)

`o_pc_wdata_match` **Inductive**; `o_rd_wdata_match` Not Inductive (BMC-clean).
The CTI is the writeback/RVFI linkage.

## CTI-derived decomposition (not copied)

The CTI showed `dbg_insn_opcode=SLTU` with `instr_sltu=0`, and later
`alu_out_q`/`rvfi_rd_wdata` with bit1 set (not a 0/1 result). The proposed
helpers were motivated by those observations:

- decode consistency: `cpuregs_write && dbg_is_sltu ⇒ instr_sltu`;
- `exec_operands`: at exec with `instr_sltu`, `reg_op1/op2 == dbg_rs1val/rs2val`;
- `op_data`: on an SLTU writeback `cpuregs_wrdata == (dbg_rs1val < dbg_rs2val ? 1 : 0)`;
- `result_1bit`: `spec_valid && !trap ⇒ rvfi_rd_wdata[31:1]==0`;
- writeback shadow + `wb_consistent`: `wb_wdata == (wb_rs1 < wb_rs2 ? 1 : 0)`;
- operand identity, destination identity, retire alignment;
- `dbg_next` tracks `launch_next_insn`.

(The official `res/` SLTU solution was inspected only as a reference for the
*kind* of missing fact; the helper block here was derived from the CTI/RTL.)

## Outcome

- CIll: BMC clean, **all 10 properties inductive, proof succeeded (152 s)**;
  model `btor:c5afb5d1d46f17668d3913952264d69178e4a646c10ddf9b70f33a935949b0ae`.
- Proof graph `cases/sltu/proof_graph.json`: **ACCEPT** (kernel selftest).

## Lesson

The same observation/control pattern as ADD transferred, but the *support
facts* differed (1-bit result, exec-operand match, decode consistency). This is
the intended behavior: reuse the structure, derive the operation-specific facts.
