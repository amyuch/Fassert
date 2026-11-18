# Checked Z3-to-rIC3 import on a MUL pipeline

This example contains an actual 32-bit RTL multiplier pipeline, its original
BTOR model, a constrained rIC3 model, and a complete checked composition.

Z3 proves two inductive facts on the original model: captured product arithmetic
and the retirement data relationship. The restricted model imports their typed
BV predicates. rIC3 proves `o_result` on that model. The projection guard closes
both assumptions and transfers the result to the original model/property.

From the PCD root, offline:

```sh
./pcd compose --case examples/solver_bridge_mul/case.json \
  --proof examples/solver_bridge_mul/proof.json
```

Rebuild and execute a fresh bounded-budget hardware check:

```sh
python3 examples/solver_bridge_mul/reproduce.py --rebuild --run-engine
```

`evidence/execution.json` records the actual rIC3 invocation and model identity;
`engine.log` contains UNSAT. Z3 queries are regenerated from the original BTOR.
All local proof and constraint-discharge results are recomputed by `pcd check`.
No assumption is proved under itself, and final leaf assurance remains REPLAY.

This is a solver-composition example, not a performance or agent-discovery
claim. Mode is development. Frontend, Z3 and rIC3 correctness remain trusted.
See [the solver bridge rules](../../docs/10-solver-bridge.md).
