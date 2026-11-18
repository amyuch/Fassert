# Spec-Directed Proof Decomposition — reproduction notes

This directory contains the prototype method and the checking scripts described
in `PLAN.md`. It consolidates the selected proof obligations into one documented
flow. It does **not** claim a single unified full-checker run; the focused CIll
runs are focused checks, reported with their assumptions.

## See also

- `CONCLUSION.md` — what the evidence establishes (and does not).
- `PROOF_FLOW.md` — the stable method (Steps 0–5, schema, kernel rules, DAGs).
- `RULEBOOK.md` — R1–R11 + negative rules, tagged evidence vs hypothesis.
- `LEDGER.md` — frozen evidence, hashes, per-obligation statuses, reconciliation.

## 1. Method (SPC, brief)

Iterative RTL operations are proved by a **Stratified Progress Contract**:

```
contract C = (A, E, X, T_G, Φ=M∧C_rec∧Σ, ρ, Δ, Post, P)
O0 rtl_link; O1 entry; O2 preservation (guard-covered);
O3 progress; O4 finalization; O5 terminal facts; O6 observable link
```

Obligations are classified by *kind* (manifold / algebraic / guarded / terminal /
temporal) and discharged by the appropriate engine. The kernel checks the
composition; engines only supply certificates. See `PLAN.md` §12.

## 2. Toolchain / trusted computing base (TCB)

| tool | version | role |
|---|---|---|
| z3 | 5.1.0 (`z3py`) | SMT/algebra checks, linear composition |
| Yosys | 0.60+70 | front-end (RTL → BTOR/IL), `read_slang` plugin |
| Slang (`yosys -m slang`) | with Yosys | SystemVerilog elaboration |
| rIC3 (`ric3`) | 1.5.2 local build | IC3/kind/BMC + CIll (`cill check/select`) |

**Important:** the local `ric3` was built with a one-line change in
`src/cli/yosys.rs`:
`read_slang -Wnone -D FORMAL -D YOSYS_SLANG --allow-genblk-reference`.
Without it, references to `genblk1.pcpi_mul.*` (internal multiplier/divider
state) do not elaborate. The installed `~/.cargo/bin/ric3` is unmodified.

TCB (explicit for every architectural result):
- O0: the Yosys/Slang front-end faithfully represents the source RTL. The BTOR
  sha256 ties artifacts to a specific input; it is identity, **not** semantic
  equivalence.
- Solver soundness (z3/ric3) for L1 re-checks. Proof-log validation (L2) is not
  implemented.

## 3. Obligations and where they are checked

### 3.1 Portable z3 checks (no external RTL sandbox)

| script | checks | status |
|---|---|---|
| `s1_compose.py` | MUL ring identity, purified consecution, endpoint, compose (W=8/16/32/64) | proved |
| `s2_check_cert.py` | independent certificate checker + negative test | validated |
| `s3_synth_cert.py` | automated certificate synthesis vs hand-derived | match |
| `s4_div_analysis.py` | DIV arithmetic profile (fixed multiplier, one-hot) | analysis |
| `s5_temporal.py` | SERV bit-serial ADD macro-step summary | proved |
| `s6_proofgraph.py` | router + proof graph + generality table | MUL/SERV closed, DIV localized |
| `s13_div_delta.py` | DIV Δ1/Δ2/Δ3 + unsigned quotient theorem | Δ closed; quotient closed |
| `s14_div_signed.py` | DIV exceptional cases + signed sign-adjust (W=8/12) | exceptional checked; signed W≥16 solver-limited |
| `s15_div_signed_interface.py` | signed DIV via unsigned interface (no division operator) | proved (width-independent) |
| `s16_div_branch_selection.py` | DIV decode/finish/sign/exceptional dispatch | checked |
| `s18_rem_compose.py` | observation chain (mux → ready → writeback → RVFI → rd-zeroing) + 32-bit corners | proved |
| `s19_div_rem_bridge.py` | DIV/REM step bridge (aligned trial ⇒ `d+N*q==M`) + writeback-value checks | proved |

### 3.2 RTL/BTOR checks (CIll + minimal sandboxes)

Sandboxes live under `/tmp/opencode/cill/t3/` (provisioned as in §5). These are
focused checks over the **real** RTL.

| sandbox | property | engine | result |
|---|---|---|---|
| `kernel_l4` (MUL) | `rvfi_rd_addr == rvfi_insn[11:7]` at retire | CIll IC3 | proved (27 s) |
| `kernel_div_l4` | same (DIV) | CIll IC3 | proved (31 s) |
| `kernel_m2` (MUL) | operand latch + start correspondence + retirement correspondence | CIll IC3 | proved (20/59 s) |
| `kernel_div_m2` | operand retirement correspondence (DIV) | CIll IC3 | proved (64 s) |
| `kernel_mul` | manifold property package (4 facts) | ric3 IC3 | proved (1–93 s) |
| `kernel_div_pc` | DIV PC boundary + stability | CIll IC3 | proved (27 s) |
| `mul_contract` | carry-save accumulator == plain shift-add | CIll IC3 | proved (16 s) |
| `div_contract` | DIV finish mux + last update | CIll IC3 | proved |
| `insn_mul_real` | MUL data chain L1–L3 (ready/writeback/RVFI) | ric3 IC3 | proved |
| `kernel_div` | DIV observation links (mux/L1/L2/L3) | ric3 IC3 | proved |
| `cases/div/min` (committed) | divider entry/step/manifold/invariant/terminal/finish facts (18 props) | CIll IC3 | **proved, 18/18 inductive (192 s)**, model `btor:d3d475a4…` |
| `cases/rem/min` (committed) | same fact set for the remainder path (18 props) | CIll IC3 | **proved, 18/18 inductive (189 s)**, model `btor:98dfa44b…` |

Open / solver-limited (BMC-clean, **not** counterexampled):
- Signed DIV at W≥16: z3 bit-blasted division frontier; S15 is the
  width-independent interface result.
- (DIV RTL loop invariant/ordering is now closed in S30.)
- Signed DIV at W≥16: z3 bit-blasted division frontier; the interface proof
  (S15) is the width-independent result.

## 4. Status (keep distinctions)

| property | status |
|---|---|
| MUL operation arithmetic | closed (S1/S2) |
| MUL `o_rd_wdata_match` | **closed** (L1–L4 + operands + arithmetic), O0 TCB |
| MUL `o_pc_wdata_match` | **closed** (PC boundary+stability+latch), O0 TCB |
| MUL RTL↔recurrence (accumulator) | **closed** (contract) |
| DIV Δ terminal ordering | closed (abstract, S13) |
| DIV unsigned quotient | closed (S13) |
| DIV signed sign-adjust | closed (S15, interface) |
| DIV exceptional b=0 / MININT,-1 | checked (S14) |
| DIV branch selection | checked (S16) |
| DIV observation data chain | **proved (RTL, S17)** |
| DIV architectural data | **closed** (S13–S17 + L4 + operands), O0 TCB |
| DIV `o_pc_wdata_match` | **closed** (S26), O0 TCB |
| DIV RTL loop invariant/ordering | **closed (S30: shift-index manifold + invariant + terminal, inductive)** |
| REM divider facts (entry/step/manifold/invariant/terminal/finish) | **proved (CIll 18/18 inductive, isolated divider model; transfer recorded in the graph's `reuse` blocks)** |
| DIV/REM `o_rd_wdata_match` | **closed at L2 by a checked composition** (S18+S19; artifacts sha256-bound, kernel K8). CIll reports *Not Inductive* on the full core; that verdict is **not** overridden |
| DIV/REM `o_pc_wdata_match` | **proved (L1)** |

Terminology: "proved" = an engine returned UNSAT/inductive for the exact query.
"BMC-clean" = no counterexample up to the tested bound, **not** a proof.
"UNKNOWN"/timeout is not a counterexample.

Assurance levels used in this directory: **L1** = an engine verdict for the exact
query; **L2** = a machine-checked composition of L1 leaves under a recorded
assumption-match; **L3** = kernel structural checks only (DAG closure,
provenance, artifact binding) — an L3 acceptance is not a proof.

## 5. Reproduce

### 5.1 Portable z3 suite

```sh
cd automation/decomp
for s in s1_compose s2_check_cert s3_synth_cert s4_div_analysis \
         s5_temporal s6_proofgraph s13_div_delta s14_div_signed \
         s15_div_signed_interface s16_div_branch_selection \
         s18_rem_compose s19_div_rem_bridge; do
  python3 -u $s.py
done
```

### 5.1b Rebuild the isolated divider models (committed, no sandbox needed)

```sh
cd automation/decomp
sh cases/div/min/repro.sh /tmp/opencode/cill/t3/div_min_verify
sh cases/rem/min/repro.sh /tmp/opencode/cill/t3/rem_min_verify
```

Each script stages the benchmark's `picorv32.sv` + `rvfi_macros.vh`, the
committed contract, builds the BTOR, prints its sha256 (the model id) and runs
`ric3 cill check` — the expected outcome is `18/18 inductive` with the model id
`btor:d3d475a4…` (DIV) / `btor:98dfa44b…` (REM).

### 5.2 Provision the real-RTL sandboxes

From the repo root (paths assume `/tmp/opencode/cill/t3`):

```sh
# real (non-ALTOPS) MUL / DIV
for p in insn_mul insn_div; do
  cp -rL benchmarks/picorv32/$p /tmp/opencode/cill/t3/$p
  sed -i '/RISCV_FORMAL_ALTOPS/d' /tmp/opencode/cill/t3/$p/defines.sv
done
# MUL real config: wrapper.sv .ENABLE_FAST_MUL(0), .ENABLE_MUL(1)
# DIV real config: wrapper.sv keeps .ENABLE_DIV(1)
```

The minimal CIll sandboxes (`kernel_l4`, `kernel_m2`, `kernel_div_pc`, ...) are
created by copying the corresponding real project, removing the checker instance,
and injecting the focused helper block (`h_is_mul`/`h_is_div` + the property).
Each contains a `ric3.toml`; run:

```sh
# RIC3 = the local patched build (see TCB)
$RIC3 cill check
# if non-inductive:
$RIC3 cill select <ID>
```

BTOR-level checks (S7/S17) run `$RIC3 build` then `$RIC3 check <btor> ic3 --prop i`.

## 6. Caveats

- O0 front-end trust; BTOR hash is identity, not equivalence.
- The arithmetic/M2 interfaces are matched at the operation boundary (S1 model,
  S13 interface, contracts), not via one monolithic kernel-checked certificate.
- Focused CIll checks are not a single unified full-checker run.
- `PLAN.md` §12.14–12.19 records the exact history, including the CTI-guided
  corrections (shadow vs RTL latch; finish-only vs active-cycle invariant;
  `$past` sampling edges; 63-bit overflow).

## Minimal kernel (T2/T3) and T-E2E reference graphs

`kernel.py` validates a proof-carrying decomposition DAG (K1–K9). The reference
graphs are `cases/mul/proof_graph.json`, `cases/div/proof_graph.json`,
`cases/add/proof_graph.json`, `cases/sltu/proof_graph.json`, and
`cases/rem/proof_graph.json`.

```sh
python3 kernel.py cases/mul/proof_graph.json
python3 kernel.py cases/div/proof_graph.json
python3 kernel.py cases/rem/proof_graph.json
python3 kernel.py --selftest   # accepts the graphs, rejects 8 bad variants
```

Kernel rules added after the 2026-10-22 audit:

- **K7 (extended)** — a case may declare several `models`; a node proved on a
  non-primary model must carry a `reuse` block whose `source_model` is that
  model and whose `assumption_match` records the matched dimensions
  (`model/width/guards/phase/transition`).
- **K8** — a target closed by composition must bind the artifact of that
  composition run by sha256, so "closed" points at a checkable run.
- **K9** — committed helper sources must not contain tautological assertions
  (e.g. `|| 1'b1`): a neutered helper may not be recorded as a proved lemma.
  This rule exists because the REM `h_dividend_update` lemma had been proved
  vacuously and no structural check could see it.

Status meaning in the graphs: `PROVED_TRUSTED` nodes carry recorded engine
evidence (ric3/CIll/z3); `PROVED_CHECKED` nodes carry an independently checked
certificate (the MUL ring identity is validated by the kernel's polynomial
normal form); `TCB_ASSUMPTION` is the front-end. The kernel does not re-run the
trusted engines yet; that is a planned extension. Re-running would not upgrade
them beyond `PROVED_TRUSTED` unless a checked certificate exists.

T-E2E is a **reference/regression** test of the soundness layer, not a
transfer/generality result.
