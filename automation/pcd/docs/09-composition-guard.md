# Semantic composition guard (K13)

K13 checks synchronous bit-vector structural projections between model hashes.
A checked Boolean identity alone does not transfer a fact. Model-bound SMT
reasoning, explicit BV/Int bindings, and checked source-constraint discharge are
specified in [`10-solver-bridge.md`](10-solver-bridge.md).

## Run it

From the PCD root:

```sh
./pcd selftest
python3 examples/composition_add/prepare.py
./pcd compose --case examples/composition_add/case.json \
  --proof examples/composition_add/proof.json
./pcd check --case examples/composition_add/case.json \
  --proof examples/composition_add/proof.json --json
```

`compose` runs the offline kernel and prints its composition record and errors.
It never calls a hardware engine or changes the package. `check` also enforces
K13, so using a different CLI command cannot bypass the guard.

The ADD example uses a recorded successful real picorv32 run and an observer
extension of that model. All 25 property transfers are checked. The observer
has its own toggling state but cannot affect the original DUT or properties.
This is frozen-evidence validation, not a new engine run, a speedup measurement,
or a blind planner experiment. The source evidence is bundled in the example.

## Certificate records

The proof's `model_artifacts` maps model IDs to file paths and SHA256 hashes.
The hash must agree with both the file contents and the registered `btor:` ID.
Each transferred Boolean guarantee has:

```json
"binding": {"kind": "btor-bad", "property": "o_pc_wdata_match"}
```

It means that the named BTOR bad property is false on every allowed execution.
The model is the obligation's `model`; bindings never infer meaning from a
variable's spelling. Different model properties use distinct Boolean atoms.

A transfer certificate uses `format: "btor-projection"`,
`checker: "pcd-compose/0.1"`, and this payload:

```json
{
  "source": {"node": "source.pc", "guarantee": "PC"},
  "state_map": {"123": "456"},
  "input_map": {"2": "2", "4": "4"},
  "free_map": {"789": ["456:0", "456:1"]}
}
```

Node IDs in maps are local BTOR IDs, encoded as decimal strings. The transfer
must require exactly the source guarantee. The kernel checks its evidence,
model artifacts, endpoint properties, maps, initialization, transitions, and
constraints. It does not trust a planner-supplied SMT script for this edge.

`free_map` is optional and applies only to source states with no initializer and
no next-state equation. It gives one destination free-state bit for every source
free-state bit. A destination bit may be shared, but one source bit may not be
forced to two independent destination bits. The map is a proposal: the checker
recomputes `Model.bits` with per-bit atom labels and verifies the property,
initialization, transitions, and constraints. For `concat(a, b)`, `b` is the low
half and `a` is the high half, matching `Model.bits`.

Generate an untrusted mapping suggestion with:

```sh
./pcd compose --proof examples/composition_add/proof.json \
  --propose transfer.o_pc_wdata_match
```

A proposed map is not proof. The verifier ignores signal names and independently
checks the mapped expressions. Failed mapping heuristics can reject a valid
relationship; they cannot certify an invalid one.

## Checked direction

Let S be the source model where a lemma is proved and D the destination where
it is consumed. The map projects D state/input values into S values. The guard
establishes that D executions are represented in S, so a safety property
proved in S is usable in D. Full equivalence is unnecessary.

1. Source/destination atom kinds and bit widths must match.
2. The source property and every source constraint determine a state/input
   cone, closed through state initializers and next-state expressions. Every
   atom in that cone must be mapped; free states may use a checked bit map.
3. Mapped initialized source states must have identical destination initial
   values. Initializers in S must be constant expressions, including forgotten
   source states; this prevents an inconsistent forgotten initializer from
   making the source proof vacuous.
4. Every mapped state update must match structurally after normalization.
   Presence of a next-state equation must also match. Free states have neither,
   and their property/constraint bits must match under the bit map.
5. Every source constraint must occur in D after mapping. S may have fewer
   constraints, giving an over-approximation. Added source assumptions cannot
   silently make a lemma applicable to D.
6. The mapped source bad expression must equal the actual destination bad
   expression. Identical property names with different bodies are insufficient.

Normalization flattens wiring operations: concatenation, slicing, zero/sign
extension and constants. Other bit-vector operators preserve their widths,
operator and operand order. There is no hidden arithmetic rewrite.

The case must freeze `build.expected_model` and declare each guarded target's
`required_properties`. The primary artifact must match that expected model.
The checked root must establish the declared properties through proved,
model-bound facts in its dependency closure. A root proving `true` cannot
substitute for a required hardware property.

The relation is relative to the selected case/model contract. Deciding whether
an environment or repaired checker matches the intended benchmark remains a
separate contract-review task; a projection does not approve a new scope.

## Assurance and reporting

Structural projection checks have CHECKED evidence. A source engine proof
remains REPLAY evidence: transitive assurance is computed without upgrading it
through a checked transfer. Engine/front-end correctness is still trusted.
The checker binds known rIC3 commands and frozen logs to named properties; it
does not independently certify IC3 proofs or authenticate prior execution.

Kernel JSON includes `composition.status`, `checked_edges`, and `unresolved`.
`run_check` writes `composition.json`; run reports include `composition_guard`.
Frozen suite packages are read-only: current checks are written alongside the
new benchmark result, preserving their existing `check.json` and manifests.

## Discharge DAG and multi-hop composition

A proof is a directed acyclic graph over model-bound obligations.  The target
root is on the primary model.  Walking its `requires` backwards, the only
cross-model edges are checked projection transfers.  A node on a non-primary
model is **anchored** when it supports, transitively through same-model
premises, a checked transfer on the target derivation path. This is the rule needed for
separated proofs:

```
engine facts on source model
  -> same-model SMT/compose root
  -> checked projection to an intermediate model
  -> checked projection to the primary model
  -> checked target composition
```

The semantic argument is local at every edge.  A same-model SMT/compose node is
proved from its premises; a projection is proved by `check_projection`; a
target composition is proved by the canonical SMT implication.  Because the
graph is acyclic and every cross-model edge is a checked projection, the target
root holds on the primary model.  Facts do **not** each need their own transfer:
if a checked intermediate root is transferred, its same-model support cone is
part of that checked edge.

The kernel enforces this by:

- rejecting a cycle (K3);
- requiring every cross-model premise to be a checked projection (K13);
- accepting a non-primary node only when it is anchored in a target derivation
  (K7), rather than requiring a direct `reuse.transfer_node` edge;
- keeping every projection edge strict: source and destination property, maps,
  initialization, transitions, constraints, and discharge witnesses are still
  re-checked.

`reuse` remains an optional descriptive record.  If present, K4 checks that its
transfer is a CHECKED transfer on a target derivation and that the reused node
lies in that transfer's transitive premise support.  The record cannot make an
edge true; only `check_projection` can.

### Manifest driver

`pcd crossmodel --manifest FILE` assembles this shape from a declarative
manifest:

- frozen models, by local path (the driver computes the `btor:<sha256>` ids and
  copies the artifacts);
- `replay` nodes backed by frozen engine logs;
- `smt` nodes checked by `pcd-btor-smt/0.1` against the actual model;
- `transfer` nodes whose maps are proposed by the structural mapper and
  immediately re-checked by `check_projection`;
- a target composition.

The driver never assigns a status.  It writes `proof.json`, `case.json`, and
`crossmodel.json`, then calls the kernel.  A missing or failed edge is
`needs_check` or `reject` according to the computed disposition.  A manifest
cannot supply a trusted map or a status tag.

## Fail-closed boundaries and migration

Complete mode rejects:

- cross-model premises supported only by an SMT identity or unbound prose;
- destination helper assumptions without a supported semantic binding;
- supplied `smt-induction` recurrences without an RTL-to-arithmetic bridge;
- cyclic dependencies, including cycles labelled as simultaneous groups;
- inconsistent case/proof/metadata acceptance policies or omitted case targets.

Polynomial guarantees currently have integer semantics in composition. A
modular identity therefore needs an additional valid integer interpretation;
the kernel checks it rather than consuming a modular equality as an Int fact.

Arrays, relational/nonconstant source initialization, asynchronous or stuttering
refinement, arbitrary functional maps, and arithmetic lifting are not
implemented. Constraint discharge is implemented as a checked projection edge
(`payload.discharge` with a witness proved on the destination model), and
multi-model orchestration is implemented by the discharge DAG and the
`pcd crossmodel` driver. Unsupported relationships remain incomplete rather
than being accepted by a tag. The mathematical induction checker remains
available for explicit development use; a complete claim still needs the
corresponding model-bound edge.

The generic e2e builder creates one primary model. Cross-model packages are
assembled by `pcd crossmodel`; the builder is not silently rewritten. The
arithmetic lift patterns are in
[`11-arithmetic-lifting.md`](11-arithmetic-lifting.md). The discharge DAG accepts
such a lift only through a model-bound SMT check or a checked projection, never
through a `py:` algebra TCB.
