# PCD documentation map

The documents are ordered from the proof model to the operational flow. Rules
that affect acceptance are normative; the hard-case playbook and arithmetic
guidance are discovery guidance only.

| document | role | normative? |
|---|---|---|
| `00-theorem.md` | relative soundness, computed disposition, and residual completeness | yes |
| `01-principles.md` | why the framework is shaped this way | yes |
| `02-method.md` | target, cut, obligation, and hand-off method | yes |
| `03-rules.md` | soundness and acceptance rules `R1–R24` | yes |
| `04-workflow.md` | build/plan/discharge/check/report workflow | yes |
| `05-ir.md` | obligation, guarantee, and certificate IR | yes |
| `06-decomposition.md` | lemma-chain planner and checked cuts | yes |
| `07-hard-case-playbook.md` | discovery heuristics for difficult cases | advisory only |
| `08-official-flow.md` | importing and validating official riscv-formal cases | yes |
| `09-composition-guard.md` | semantic projection checks and unsupported boundaries | yes |
| `10-solver-bridge.md` | model-bound Z3 proofs and constraint discharge | yes |
| `11-arithmetic-lifting.md` | general arithmetic-lifting patterns | advisory only |

The kernel is the final authority for acceptance. The playbook and arithmetic
guidance cannot weaken a target, turn an assumption into a lemma, or make a
design TCB acceptable.

Current results and the bundled-case view are in [`../RESULTS.md`](../RESULTS.md).
The offline replay path is documented in [`../README.md`](../README.md) and
[`08-official-flow.md`](08-official-flow.md).
