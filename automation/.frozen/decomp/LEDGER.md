# Frozen ledger — MUL / DIV evidence (authoritative status)

This ledger resolves earlier open statuses against later closed results. Where
an artifact JSON predates a later closure, this ledger is authoritative and the
artifact is marked "historical".

## Toolchain

| tool | version |
|---|---|
| z3 / z3py | 5.1.0 |
| Yosys | 0.60+70 (git 8101c87fa) |
| Slang plugin | `yosys -m slang` |
| rIC3 | 1.5.2, **local build** with `read_slang ... --allow-genblk-reference` |

The local rIC3 patch is required to reference `genblk1.pcpi_mul` /
`genblk1.pcpi_div` internals. The installed `~/.cargo/bin/ric3` is unmodified.

## Artifacts and hashes

| artifact | sha256 | note |
|---|---|---|
| `artifact_mul_manifold.json` | `88dc016c…` | BTOR `e0693b18d2fa90315717676f5a9acaed716d57c876d15345bfc30fc36438cfbc` |
| `artifact_mul_spc.json` | `3cd2f94b…` | historical (before L4/M2 closure) |
| `artifact_mul_o6.json` | `07a15a8e…` | **historical**: L4 shown "unknown"; see S24 |
| `artifact_mul_rvfi.json` | `f31a1f64…` | **historical**: M2/PC "bmc-clean-unproved"; see S24/S25 |
| `artifact_div_observation.json` | `fdf726aa…` | DIV observation links; L4 proved |
| `artifact_div_rem_bridge.json` | `1e74774a…` | **new**: S19 step bridge + writeback-value checks (DIV/REM) |
| `artifact_rem_compose.json` | `3ec16da5…` | S18 observation chain + corners |

Scripts: `s1`–`s17` in this directory; `README.md`, `reproduce.sh`.

## MUL obligations

| obligation | engine | runtime | status |
|---|---|---|---|
| O0 rtl_link | frontend TCB | — | TCB |
| O1/O2 manifold (4 facts) | ric3 IC3 | 1.0–93.3 s | proved |
| B ring identity | poly Z/2^W | 0.04 ms | proved |
| B purified consecution | linear/EUF | 1.35 ms | proved (assumes manifold) |
| O5 endpoint | symbolic unroll | 64 ms (W=32) | proved |
| O4 finalization | linear | 0.57 ms | proved |
| O6 L1–L3 (ready/writeback/RVFI) | ric3 IC3 | 0.6–0.8 s | proved |
| L4 destination identity | CIll IC3 | 27 s | **proved** (S24) |
| M2 operand latch/start/retirement | CIll IC3 | 20/59 s | **proved** (S24) |
| PC boundary+stability | CIll/ric3 | — | **proved** (S25) |
| RTL↔recurrence accumulator | CIll IC3 | 16 s | **proved** (S27) |

**Closure claim (MUL):** `o_rd_wdata_match` and `o_pc_wdata_match` closed at the
integration level, under O0 frontend trust and solver trust. The arithmetic/M2
interfaces are matched at the operation boundary.

## DIV obligations

| obligation | engine | runtime | status |
|---|---|---|---|
| Δ1 manifold `N·msk==divisor` | S4/z3 | 0.76 ms | proved |
| Δ2 invariant + terminal step | z3 | 1.2/1.6 ms | proved |
| Δ3 terminal alignment | z3 | 1.2 ms | proved |
| unsigned quotient theorem | z3 | 25.6 ms | proved |
| signed sign-adjust | S15 (interface) | ~12 ms | proved (width-independent) |
| exceptional `b=0`, `MININT/-1` | S14 | <0.1 s | checked (distinct) |
| branch selection | S16 | 0.6–1.7 ms | checked |
| observation mux/L1/L2/L3 | ric3 IC3 | 1.4–2.2 s | proved (S17) |
| L4 destination identity | CIll IC3 | 31 s | **proved** (S24) |
| M2 operand retirement | CIll IC3 | 64 s | **proved** (S24) |
| PC boundary+stability | CIll IC3 | 27 s | **proved** (S26) |
| RTL loop state/update/invariant/terminal | CIll IC3 | 140 s | **proved** (S30) |

**Closure claim (DIV):** architectural data and `o_pc_wdata_match` closed at the
integration level, under O0 frontend trust and solver trust. Signed DIV at W≥16
is solver-limited; S15 is the width-independent result.

## Reconciliation (historical → final)

| earlier | final | resolution |
|---|---|---|
| `artifact_mul_o6.json`: `h_rd_matches_insn` = unknown, verdict "rd-address OPEN" | L4 **proved** | S24 (minimal sandbox, CIll): the full-BTOR Unknown was a bloated-model/solver artifact |
| `artifact_mul_rvfi.json`: M2/`h_pc_corr` "bmc-clean-unproved" | M2/PC **proved** | S24/S25: RTL operand latch + retirement correspondence, PC boundary+stability |
| S11 L4 "open" (entry relation false) | **closed** | wrong boundary; S24 used the retirement target/minimal sandbox |
| S28 DIV loop invariant "open" | **closed** | S30 shift-index manifold + phase/start/b=0 guards + terminal split |
| S13 abstract Δ / quotient | now instantiated on RTL | S30 RTL loop-state correspondence connects them |

## Exact trust boundary (for the closure claims)

- **O0:** Yosys/Slang→BTOR faithfully represents source RTL. The BTOR sha256 ties
  artifacts to an input; it is identity, **not** semantic equivalence.
- **Solver trust:** ric3/z3 soundness; results are not proof-log checked (L2).
- **Methodology:** focused checks over minimal sandboxes; not one unified
  full-checker run.
- **Model/interface matching:** arithmetic/M2 interfaces are tied at the
  operation boundary; the frontend remains the bridge to source RTL.

## Reproduction

See `README.md` §5 and `reproduce.sh`. Portable z3 suite runs without sandboxes;
the focused RTL/BTOR checks require the `/tmp/opencode/cill/t3/*` sandboxes
(provisioned as documented) and the local patched rIC3.

## Assurance-level mapping (final)

| evidence | level |
|---|---|
| S2 independent polynomial certificate | `PROVED_CHECKED` |
| ric3 IC3 / CIll IC3 / z3 checks | `PROVED_TRUSTED` |
| O0 front-end (Yosys/Slang→BTOR) | `TCB_ASSUMPTION` |
| signed DIV W≥16 (division bit-blast frontier) | `UNKNOWN` (solver-limited) |
| BMC/k-induction "no CEX within bound" | `BMC_CLEAN` (diagnostic) |
| historical artifact JSONs (`artifact_mul_o6`, `artifact_mul_rvfi`) | status per `LEDGER.md`, not per artifact |

The ledger's "proved" entries above are `PROVED_TRUSTED` unless they are the
independent S2 certificate (`PROVED_CHECKED`) or the front end
(`TCB_ASSUMPTION`). "Closed at integration level" means the composition is
accepted under those levels, not that every premise is `PROVED_CHECKED`.

## T-E2E status (reference/regression)

- `kernel.py` + `cases/mul/proof_graph.json` + `cases/div/proof_graph.json`.
- `python3 kernel.py --selftest` → **PASS**: both graphs accepted; negative
  controls rejected (missing assumption, uncovered guard, disconnected lemma,
  status upgrade, unsound abstraction, reuse mismatch).
- Evidence levels in the graphs: `PROVED_TRUSTED` (recorded ric3/CIll/z3),
  `PROVED_CHECKED` (MUL ring poly certificate), `TCB_ASSUMPTION` (O0).
- This is not a new proof and not a transfer result; it reconciles the ledger
  and exercises the composition checker on known-good/bad graphs.

## ADD transfer case (beyond MUL/DIV/REM)

- Baseline (empty helpers): `o_rd_wdata_match` and `o_pc_wdata_match` Not
  Inductive (BMC-clean); CTI = writeback/RVFI linkage.
- Proposed helpers (control/trap facts, `op_data`, writeback shadow,
  `wb_consistent`, `operand_id`, `dest_id`, `retire_align`, `pc_link`).
- CIll: **all properties inductive, proof succeeded (154 s)**; model
  `btor:a4dfde202ade2ee0d9a9d2c7ec29a28359998bbc92e6c4bf0b8c3b6391169597`.
- Proof graph `cases/add/proof_graph.json`: **ACCEPT** (kernel selftest).
- Status: `PROVED_TRUSTED`, O0 TCB. First transfer beyond the PCPI arithmetic
  family; difficulty = observation/control, not algebra.

## SLTU transfer case (CTI-derived, not copied)

- Baseline: `o_pc_wdata_match` Inductive; `o_rd_wdata_match` Not Inductive.
- CTI showed `instr_sltu=0` under a SLTU opcode and a non-0/1 `alu_out_q`.
- Derived facts: decode consistency, exec-operand match, 1-bit result,
  `op_data` (`wrdata == (rs1<rs2?1:0)`), writeback shadow + `wb_consistent`,
  operand/dest identity, retire alignment, `dbg_next` tracking.
- CIll: **all 10 properties inductive, proof succeeded (152 s)**; model
  `btor:c5afb5d1d46f17668d3913952264d69178e4a646c10ddf9b70f33a935949b0ae`.
- Proof graph `cases/sltu/proof_graph.json`: **ACCEPT** (kernel selftest).
- Status: `PROVED_TRUSTED`, O0 TCB. Same structure as ADD; operation-specific
  support facts were derived from the CTI.

## REM transfer case (held-out, real non-ALTOPS divider) — REVISED 2026-10-22

Audit outcome (the earlier entry above is superseded):

- The earlier REM closure was **not** proof-trusted: the recorded `updates` lemma
  was `h_dividend_update: assert(dividend == $past(dividend) || 1'b1)` — a
  tautology, hence semantically inert. The loop/step facts were therefore never
  proved. The graph also had no `role:"interface"` node, so `rem_arith` assumed
  only `terminal` and the arithmetic was never joined to the RTL.
- Repair: the real step lemma was re-derived and proved; the graph now carries
  an explicit interface node whose premise set contains the RTL-side facts.

### New evidence (the bridge)

| obligation | engine | venue | status |
|---|---|---|---|
| divider entry values (dividend/quotient/msk/divisor/outsign) | CIll (18/18 inductive, 189 s) | isolated divider model `btor:98dfa44b…` (REM), `btor:d3d475a4…` (DIV) | proved |
| per-step correspondence (divisor>>1, msk>>1, dividend-=divisor, quotient\|=msk) | CIll | same | proved |
| loop manifold `divisor==N<<k`, `msk==1<<k`; invariant; last premise; terminal | CIll | same | proved |
| finish-edge stability (no dividend update at the finish) | CIll | same | proved |
| finish mux (quotient vs dividend path, selected by the decode) | CIll | same | proved |
| step bridge: aligned trial `D==N*msk` ⇒ `d+N*q==M` preserved | z3 (S19 B0-1, + a **sat** mis-scaled control) | abstract | proved |
| entry/terminal instantiation ⇒ `d==M%N`, `q==M/N` | z3 (S19 B0-2/3/4) | abstract | proved |
| writeback value == architectural remainder/quotient (signed/unsigned, `rs2==0`, `MININT/-1`) | z3 (S19 B1-*) | abstract | proved |
| observation chain + corners | z3 (S18 [C]/[D]) | abstract | proved |

### Transfer argument (why the isolated model suffices)

The isolated divider model contains the *identical* `picorv32.sv` divider text
(sha256-identical to the benchmark copy) and lets `pcpi_rs1/rs2/insn/valid` be
free — i.e. it over-approximates the core's environment. Every fact proved
inductively there therefore also holds in the full core. The one extra
permission (a divider *restart*, which the core never issues) is excluded by
the `!$past(h_start)` guards on the finish-edge lemmas. The transfer is
recorded in each node's `reuse` block (kernel K7).

### Revised trust statement

| claim | level | why |
|---|---|---|
| divider-internal facts (entry, step, manifold, invariant, terminal, finish mux) | `PROVED_TRUSTED` | CIll, inductive, 18/18, isolated model + documented transfer |
| observation/PC facts (mux, ready capture, wb mux, RVFI link, dest, operands, PC) | `PROVED_TRUSTED` | CIll/ric3 on the full core |
| `o_rd_wdata_match` (REM/DIV) | **L2 — closed by checked composition** | S18+S19 artifacts, sha256-bound to the graph (kernel K8); *not* CIll-inductive, and **not** claimed to be |
| `o_pc_wdata_match` | `PROVED_TRUSTED` (L1) | directly inductive |

Assurance vocabulary used above: **L1** = the engine returned UNSAT/inductive
for that exact query; **L2** = a machine-checked composition of L1 leaves under
a recorded assumption-match; **L3** = kernel structural checks only (DAG
closure, provenance, artifact binding) — an L3 acceptance is *not* a proof.

### Model ids of record

| model | id | role |
|---|---|---|
| full core, repaired helpers | `btor:395e28fdd2bcd78297be7ea9bc0e3545e1a8d04d634752d8d4374d2a5327d63a` | REM primary |
| full core, pre-repair helpers | `btor:a4a932b28eb81a6f1789ff1f6592d40995242ec082648fc36c8b3bf131da0c6c` | venue of the observation/PC verdicts (identical state space; the removed assertion was a tautology) |
| isolated divider, REM | `btor:98dfa44ba1cd91347f5cc165d4a6c430073215c28a5988f80853743a32402247` | divider facts |
| isolated divider, DIV | `btor:d3d475a4f4522aba1d225e5e27701d7eb8828eca99686c616f989d3db63d236b` | divider facts |
| full core, DIV | `btor:90040e379a309171d1566b434e3330830269dc8ab0691a7887d3b6da8ff484e1` | DIV primary |

Reproduction: `sh cases/rem/min/repro.sh <dir>` and
`sh cases/div/min/repro.sh <dir>` rebuild the isolated models from the
committed contracts and print the model id; `python3 kernel.py
cases/rem/proof_graph.json` re-checks the graph (K8 verifies the artifact
sha256s).
