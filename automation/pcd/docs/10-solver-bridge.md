# Model-bound Z3 proofs and checked rIC3 assumption import

This document extends K13 with typed predicates checked against actual BTOR
semantics and with explicit discharge of constraints in a restricted proof
model. It does not accept arbitrary supplied recurrences or SMT-LIB scripts as
RTL proofs.

## Reproduce the two examples

From the PCD root, offline with bundled models/logs:

```sh
./pcd compose --case examples/solver_bridge_mul/case.json \
  --proof examples/solver_bridge_mul/proof.json
./pcd compose --case examples/remu_operator_bridge/case.json \
  --proof examples/remu_operator_bridge/proof.json
./pcd selftest
```

To rebuild the multiplier from RTL and run a fresh rIC3 check:

```sh
python3 examples/solver_bridge_mul/reproduce.py --rebuild --run-engine
```

This uses the installed Yosys and rIC3 and an external engine timeout. Without
these flags, `reproduce.py` reconstructs the package from its bundled original
model and matching frozen execution record. Both paths recheck the Z3 bridge
and the final kernel result. This example demonstrates proof composition, not
a measured speedup or an agent-discovery experiment.

The REMU example uses the bundled real REMU model and its recorded successful
CIll log. New Z3 bridge checks are rerun. It proves the quotient operator/step
contract only; it does not claim the full architectural RD result. The example
package is read-only.

## Shared meaning, different solver inputs

The original model C is registered by its file hash. Z3 receives a regenerated
interpretation of C's actual initial states, next-state equations and constraints.
rIC3 can receive S, a copy of that model with imported constraints. A complete
result requires:

1. A checked theorem C satisfies L under the selected case environment.
2. A checked model map showing C's transitions are represented in S.
3. Every extra S constraint is implied by its bound theorem L on C.
4. The rIC3 result for S is bound to the actual required property on C.

The case's `required_properties` contract is enforced even when a proposal
drops every semantic certificate. Choosing a Boolean-only proof format
cannot bypass a formally bound case target.

Thus an assumption in S is never justified by proving it under that same
assumption in S. Its witness must live on the original destination model C.
Cycles in the proof graph remain forbidden.

## Typed expression bindings

A guarantee is a distinct Boolean theorem atom and carries either an existing
`btor-bad` property binding or a typed expression binding:

```json
{
  "name": "L",
  "expr": "capture_product_fact",
  "sort": "Bool",
  "binding": {
    "kind": "btor-expression",
    "expression": {
      "op": "eq",
      "args": [
        {"op": "uint", "args": [{"op": "ref", "id": 10}]},
        {"op": "int", "value": "0"}
      ]
    }
  }
}
```

Node IDs are local to the guarantee's frozen model. `ref` has an optional
`frame: 1` for next-state observations; absent/zero means current state.
There are no free planner variables. Sorts come from actual model nodes.

Supported expression forms include:

- `bool`, `int`, and explicitly sized `bv` constants;
- `truth` for a one-bit BV guard; `not`, `and`, `or`, `implies`, `eq`, `ite`;
- explicit BV arithmetic/bitwise/shift and signed/unsigned comparison operators;
- `extract` with `hi`/`lo`, `concat`, `zext`/`sext` with `amount`;
- `uint` and `sint` conversions and integer arithmetic/comparisons.

Integer and BV operations are distinct. A BV addition retains modular meaning;
its unsigned interpretation is not silently replaced by integer addition.
Constants, arities, widths, signedness, frames and unsupported syntax are checked.

Unsigned interpretation uses exact normalization rules: wiring extraction and
zero extension, conditional selection, modular add/subtract, and
`U(x|y) = U(x)+U(y)-U(x&y)`. The overlap term is retained. Disjointness and any
no-overflow conditions must be established separately. These rules are trusted
checker semantics, tested against exhaustive small-word boundary cases.

## The `btor-smt` certificate

Use `evidence: CHECKED`, `format: btor-smt`, `checker: pcd-btor-smt/0.1`:

```json
"payload": {"method": "induction", "timeout_ms": 5000}
```

The allowed methods are:

- `combinational`: actual current constraints and proved same-model state facts
  imply the bound predicate.
- `induction`: actual initialization implies the predicate and any optional
  strengthening invariants; actual transitions preserve their conjunction.
- `step`: actual transitions imply an explicitly current/next-state relation.

Only induction accepts `invariants`, a list of typed strengthening predicates.
All strengthening is checked in both base and step. Payload fields such as
`init`, `step`, `assumptions`, `vars`, or an SMT script are rejected.

Initial equations, transitions and per-frame constraints are regenerated from
the BTOR model. Deterministic next-state references may be replaced by their
actual next functions, an exact normalization. Unassigned next state remains
free, a conservative interpretation. The initial environment must also have a
demonstrated satisfying state. This does not establish property-trigger coverage.

Premises must be exact, proved bindings on the same model. A state fact can be
used at current/next reachable states. A transition theorem is used only in a
transition context: it cannot certify a state property, discharge a current
constraint, or be assumed by a current-state implication. Acyclic dependency
closure is enforced by the kernel.

The checker reruns Z3 and records query hashes, methods, results and solver
seconds. `unknown`, timeout, failed initialization or counterexample prevents
acceptance. A saved `accepted: true` record is never substituted for checking.

The SMT portfolio can first try multiplication congruence. It exactly rewrites
the low k bits of a wide product as a k-bit product of the low operand bits,
then replaces same-width multiplication with a shared arbitrary function.
This is a conservative over-approximation, useful for capture and pipeline
correspondence lemmas. Only UNSAT is accepted from that query; SAT/unknown
falls back to the actual arithmetic solvers. The original query hash and
the abstraction's query hash are both recorded.

## Constraint discharge

`btor-projection` retains its initialization, update, width and exact endpoint
checks. Its payload can additionally include:

```json
"discharge": {
  "66": {"node": "capture", "guarantee": "L"},
  "70": {"node": "retirement", "guarantee": "L"}
}
```

Keys are source constraint expression IDs, not line IDs. The projection's
`requires` lists its source theorem followed by every distinct witness.
Each witness must be a proved state fact on the original destination model.
Z3 verifies that this fact implies the actual mapped source constraint. Missing,
wrong-model, future-only, mismatched and unused witnesses are rejected.

`emit_btor.py` exports supported typed BV predicates as BTOR constraints. It is
a construction helper: the guard independently checks the resulting expression.
An emitter bug or manual edit cannot be accepted merely because the original
Z3 formula was proved. Integer formulas require an explicitly checked BV
representation; the emitter does not truncate or coerce them.

Declared helper assumptions additionally bind their compiled `helper.model`
and `assumes[].constraint` to an accepted discharge edge and its proved node.

## What the REMU bridge establishes

Under the real non-reset loop guard, the package proves:

1. The lower quotient bits through the current mask are clear (actual-model
   induction, using the recorded local helper properties).
2. `q & msk == 0` under that guard.
3. `U(q | msk) == U(q) + U(msk)` under that guard.
4. On the correctly sampled, non-restarting/non-resetting loop step,
   `U(q_next) == ite(U(D) <= U(d), U(q)+U(msk), U(q))`.

The original RTL uses OR; integer addition is justified by these proofs rather
than assigned to the helper's name. Current and previous helper observations
are interpreted through their actual registered BTOR state and updates.

The package's frozen target is the local `o_remu_or_add` observation, together
with the separately checked step theorem. Operand-to-RVFI links, the rest of the
arithmetic invariant, termination/phase coverage and final RD correspondence
still need an architectural proof. A raw `smt-induction` REMU/RD certificate is
insufficient and is not silently promoted.

## Trust and remaining limits

The checker/parser and normalization rules, Z3, the frontend, and the rIC3
execution/replay boundary remain trusted. This is not independent certification
of every SAT/SMT proof or authentication of prior execution.

The framework supports model-bound arithmetic reasoning and explicit assumption
discharge. It does not automatically discover sufficient invariants,
solve every nonlinear query, infer valid transaction alignments, support arrays
or asynchronous/stuttering refinement, or approve a changed benchmark contract.
Multi-model construction uses package scripts; the generic e2e path can
construct model-bound SMT obligations on its primary model. Arithmetic lift
patterns are in [`11-arithmetic-lifting.md`](11-arithmetic-lifting.md).
