# Diagnosis case results (feasibility)

Pre-registered cases and reproduced failures. This is a **retrospective
feasibility study** from our own MUL/DIV history, not a blind or general test.
The freeze snapshot is in `freeze.md`.

## Outcome table

| case | pre-registered failure type | observed failure | strategy | repair | observed outcome |
|---|---|---|---|---|---|
| **D1** | unreachable CTI | bad finish-only accumulator: BMC-clean, **Not Inductive**; CTI uses arbitrary carry-save state | S1 | assert on active cycles (`!mul_waiting`) | **good inductive** (16 s) |
| **D2** | representation | raw BV: W=8 0.10 s, W=10 4.58 s, W=12/16 **unknown** (30 s) | S3 | purified ring identity | **ring PASS 0.14 ms @W=64** (`PROVED_CHECKED`) |
| **D3** | uncovered branch | bad mux without priority guard: BMC-clean, **Not Inductive** | S2 | add `!pcpi_mul_ready` | **good inductive** (30 s) |
| **D6** | sampling / false premise | bad finish mux at `pcpi_ready`: **CEX h_branch_r** | A0 | sample at the finish edge via `$past` | **h_branch_q/r inductive**; `h_inv`/`h_term` are separate (S30) |
| D6b | false algebraic premise | missing zero law | checker | reject | independent checker **correctly rejects** (S2 negative) |
| **D4a** | temporal (terminal) | global `dividend<N`: **CEX** | S5/terminal | invariant + last premise; assert at finish | **10 props inductive** (140 s) |
| **D4b** | temporal (macro-step) | one-step `partial==a+b`: **SAT** | S5 | macro-step `Inv(k)` + completion at done | **base/step/exit UNSAT** (0.01–0.5 ms) |

Artifacts per case: `bad.log`, `good.log`, and `cti.vcd`/`cex.vcd` where a
counterexample/CTI was produced. `D2/log.txt` records the raw-BV timings and the
purified result.

## What this supports

- In all four cases the observed failure matched the pre-registered category,
  and the selected strategy addressed the diagnosed cause:
  - **unreachable CTI** → active-cycle invariant (D1),
  - **representation mismatch** → purification (D2),
  - **uncovered branch/priority** → explicit guard (D3),
  - **sampling error** → `$past` finish-edge values (D6).
- The failure taxonomy was *operational*: each case had a distinguishing test
  (BMC-clean+Not-Inductive vs CEX; raw-frontier vs purified; guard coverage;
  sampling edge), not just a narrative label.

## What this does not establish

- It is **retrospective**: the cases were chosen from proofs we had already
  fixed. This calibrates the taxonomy and the evidence requirements; it does not
  show the workflow discovers fixes on unseen failures. That requires held-out
  cases (REM/SERV).
- Small n (4 + 1 sub-case); no statistical claim.
- The "good" results are `PROVED_TRUSTED` CIll runs except D2's ring
  (`PROVED_CHECKED`, kernel polynomial check). The kernel was not re-run on a
  repair graph for these local contracts (`kernel_outcome` = not applicable).
- D6's repair closes the **mux obligation**; the DIV loop invariant/terminal are
  separate obligations (S30) and were deliberately not conflated.

## Deferred

- **D4** (temporal): DIV terminal sampling (S30) and SERV macro-step (S5), next.
- **D5** (abstraction refinement): no reproducible in-project example; do not
  include until we run one (or borrow NeuroAbs explicitly as external).

## Reproduce

```sh
cd automation/decomp/cases/diagnosis
python3 D2/repro.py                    # D2 (self-contained)
# D1/D3/D6: rebuild the bad/good sandboxes from the recorded configs and run
#   $RIC3 cill check        (bad: Not Inductive/CEX; good: inductive)
#   $RIC3 cill select 0     (bad CTI)
# see each record.json for the exact bad/good edits.
```
