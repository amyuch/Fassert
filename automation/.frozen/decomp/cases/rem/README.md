# REM — held-out transfer (real non-ALTOPS divider)

PicoRV32 `insn_rem` (real `picorv32_pcpi_div`, funct3=110). Targets:
`o_rd_wdata_match`, `o_pc_wdata_match`.

## Baseline (empty helpers)

Both Not Inductive (BMC-clean). The o_rd CTI showed the writeback/RVFI linkage;
a later CTI showed `pcpi_mul_ready=1` on a REM instruction.

## Audit (2026-10-22) — the earlier closure was not proof-trusted

- The recorded step lemma was `h_dividend_update: assert(dividend ==
  $past(dividend) || 1'b1)` — a tautology, hence semantically inert: the
  dividend-update obligation had never been proved.
- The graph had **no** `role:"interface"` node, so `rem_arith` assumed only
  `terminal`; the abstract arithmetic was never joined to the RTL's states.
- Both defects are now repaired (real lemma re-proved; explicit interface node
  with the RTL-side facts among its premises) and the kernel gained rule K9
  (helper hygiene) plus rule K8 (composition-artifact binding).

## Divider facts (re-proved, 18/18 inductive)

On the **isolated divider model** (`cases/rem/min/contract.sv`, environment
over-approximated):

| fact | property |
|---|---|
| entry values | `h_rem_start_{dividend,quotient,msk,divisor,outsign}` |
| loop manifold | `h_msk_shift`, `h_div_shift` (`divisor==N<<k`, `msk==1<<k`) |
| step | `h_div_update`, `h_msk_update`, `h_k_update`, `h_dividend_update`, `h_quotient_update` |
| invariant / last premise / terminal | `h_inv`, `h_last_premise`, `h_term` |
| finish edge | `h_rem_finish_stable` (guarded by `!$past(h_start)`) |
| finish mux | `h_finish_value_div` / `h_finish_value_rem` (the mux follows the decode) |

Model id `btor:98dfa44ba1cd91347f5cc165d4a6c430073215c28a5988f80853743a32402247`
(189 s). Rebuild with `sh cases/rem/min/repro.sh <dir>`.

## Bridge (S19) and composition (S18)

- S19 B0: the aligned trial `D==N*msk` preserves `d+N*q==M` (the mis-scaled
  control is **sat**, so the check has teeth); entry + terminal give
  `d==M%N`, `q==M/N`; `rs2==0` accumulates to `0xffffffff`.
- S19 B1: the writeback value equals the architectural remainder for signed and
  unsigned REM, including `rs2==0` and `MININT/-1`.
- S18 [C]/[D]: the observation chain (`mux → ready capture → writeback → RVFI →
  rd-zeroing`) and the 32-bit encoding corners.
- Artifacts `artifact_div_rem_bridge.json`, `artifact_rem_compose.json` are
  sha256-bound to the graph targets (kernel K8).

## Transfer argument

The isolated model contains the identical `picorv32.sv` divider text
(sha256-identical to the benchmark copy) and lets `pcpi_rs1/rs2/insn/valid` be
free, i.e. it over-approximates the core's environment; every fact proved
inductively there also holds in the full core. The one extra permission (a
divider *restart*, which the core never issues) is excluded by the
`!$past(h_start)` guards. The transfer is recorded per node in `reuse` blocks
(kernel K7: `model/width/guards/phase/transition`).

## Outcome

| claim | level | evidence |
|---|---|---|
| divider facts above | `PROVED_TRUSTED` (L1) | CIll 18/18 inductive on the isolated model + documented transfer |
| observation/PC facts (mux, ready capture, wb mux, RVFI link, dest, operands, PC) | `PROVED_TRUSTED` (L1) | CIll on the full core |
| `o_pc_wdata_match` | `PROVED_TRUSTED` (L1) | directly inductive |
| `o_rd_wdata_match` | **L2 — closed by checked composition** | S18+S19; **not** CIll-inductive, and not claimed to be |

The kernel acceptance of `cases/rem/proof_graph.json` is an L3 check (structure,
provenance, artifact binding) — it is not a proof.

## Models of record

| model | id |
|---|---|
| full core, repaired helpers (primary) | `btor:395e28fdd2bcd78297be7ea9bc0e3545e1a8d04d634752d8d4374d2a5327d63a` |
| full core, pre-repair helpers | `btor:a4a932b28eb81a6f1789ff1f6592d40995242ec082648fc36c8b3bf131da0c6c` |
| isolated divider | `btor:98dfa44ba1cd91347f5cc165d4a6c430073215c28a5988f80853743a32402247` |

The two full-core models have the same transition system and initial states
(the removed assertion was a tautology, i.e. no constraint), so the verdicts on
the shared properties carry over; that is recorded in the `reuse` blocks.
