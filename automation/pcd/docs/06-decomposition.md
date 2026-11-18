# Decomposition planner (`--planner decompose`)

The template planner is deliberately simple: one replay node per bad property,
composed by conjunction. It is sound, but it hides the structure of a proof. The
decomposition planner exposes the lemma chain and the checked hand-offs. See
[`09-composition-guard.md`](09-composition-guard.md) for the cross-model rules
and [`11-arithmetic-lifting.md`](11-arithmetic-lifting.md) for arithmetic proof
shapes.

The template planner is deliberately simple: one replay node per bad
property, composed by conjunction. It is sound, but it hides the structure of
a proof. In particular it cannot say that one helper is the read-data link,
another is the shadow link, and the target is the transitivity of the two.

`pcd e2e --planner decompose --decomposition FILE` reads a small manifest and
emits a graph with:

- one replay node per helper lemma, marked `helper.kind = monitor`;
- one replay node per target property;
- one CHECKED `interface` node per cut, whose premises are the cut members and
  whose goal is their conjunction;
- a CHECKED root whose premises are the targets plus the cut interfaces (and
  any helper not consumed by a cut).

The engine evidence is unchanged: every replay node still points at the same
primary model and the same `cill check` run. The improvement is in the
obligation graph and in the checked hand-offs between the lemma chain and the
target.

## Manifest

```json
{
  "schema_version": "pcd-decomposition/0.1",
  "id": "name",
  "case": "case_id",
  "lemmas": [
    {
      "id": "reset",
      "property": "h_reset",
      "role": "invariant",
      "kind": "inductive",
      "phase": "entry",
      "statement": "reset establishes the tracker"
    },
    {
      "id": "read_link",
      "property": "h_read_link",
      "role": "operand",
      "kind": "inductive",
      "phase": "loop",
      "statement": "read data equals the architectural value",
      "requires": ["reset"]
    }
  ],
  "targets": [
    {
      "id": "target",
      "property": "o_target",
      "statement": "target property",
      "requires": ["read_link"]
    }
  ],
  "cuts": [
    {
      "id": "chain",
      "boundary": "checker shadow and RF",
      "members": ["reset", "read_link", "target"],
      "entry": ["reset"],
      "step": ["read_link"],
      "exit": ["read_link"],
      "link": ["target"]
    }
  ]
}
```

The manifest must bind every property in the frozen model sketch exactly once.
The planner rejects unknown ids, duplicate bindings, a cut fact that is not a
member, and a cut without a link. The target list in the case must have one
root; the planner uses that root id.

## Sets, methods, and checked blackboxes

A manifest may also partition the lemmas and targets into named `sets`.  Each
set selects a trusted engine backend and may consume lemmas that an earlier set
already proved:

```json
"sets": [
  {"id": "monitor", "method": "cill",
   "lemmas": ["reset", "read_link"]},
  {"id": "result", "method": "ic3", "assumes": ["read_link"],
   "targets": ["rd"]}
]
```

`method` is one of the backends in the trusted engine catalog (`cill`,
`portfolio`, `ic3`, `kind`, `bmc`).  The planner copies it into each node's
`certificate_hint.backend`; it never supplies a command.  A lemma or target may
override the set method with its own `backend` field.

`assumes` is the proof-carrying blackbox seam.  It may name only a lemma from an
*earlier* set, and the planner adds that lemma's guarantee as an ordinary
`requires` edge on every node in the consuming set.  The assumed fact is a
proved node, not a TCB and not an assumption helper.  A forward or same-set
assumption is rejected, so the dependency graph is acyclic by construction.

All nodes still live on the primary model in the current implementation.  The
difference is that a non-`cill` node gets its own engine invocation with its own
`--prop` index, while `cill` nodes share the model's all-properties run.  This
is enough to prove one set with IC3 while another set uses cill, provided the
cill run is itself fully inductive.  Per-set *models* (separate BTOR
projections and cross-model transfers) remain the next step; the proof schema
and kernel already accept them, but `e2e` still builds one primary model.

The case's `run_policy.planner` must also name `decompose`. `pcd e2e` fails
before building when `--planner` and the declared policy disagree, so a
successful engine run cannot end up with an audit that is bound to a different
planner.

## Multi-model proof

The proof schema and kernel accept multiple models. `pcd crossmodel --manifest`
assembles a package from per-model checks: separate BTOR projections per lemma,
checked transfer nodes between projections, and same-model SMT nodes for
arithmetic facts. A non-primary node is accepted when it supports a checked
transfer on the target derivation path.

Current worked sources are [`../examples/solver_bridge_mul`](../examples/solver_bridge_mul)
and [`../evidence/picorv32_mul`](../evidence/picorv32_mul). The `e2e` builder
still uses one primary build recipe per case; multi-model packages are
assembled by their construction script and then checked offline. Extending the
case-level build list is an implementation gap, not a schema limitation.

## What the checked nodes mean

The cut interface node is not an assumption. It is a `CHECKED` implication:

```
(entry and step and exit and link facts) => conjunction of the members
```

The SMT script is the canonical script generated from the member guarantee
expressions; a planner cannot supply an arbitrary script. The kernel checks
the SMT script, the cut facts against the node's `requires`, and the helper
role discipline.

The root is also a canonical conjunction. It requires the target replay nodes
directly, so the target property is still a premise, not a derived fact. The
cut is an additional checked premise that records the decomposition.

An **unguarded** cut has `entry/step/exit/link` facts as its premises and a
checked conjunction as its goal. It is a checked hand-off, not a state-partition
cut with a coverage proof. A guarded cut (with `cut.guards` and a `coverage`
node) is the form to use when the decomposition needs to partition states rather
than just name a lemma chain.

## What this does *not* change

The engine still proves all properties in one `cill check` run and its local
induction may assume the other properties. The graph records and checks the
decomposition, but it does not give the engine a different induction problem.
That is why the planner accepts a helper chain that is *inductive as a whole*;
a logically redundant lemma can still change the engine's clause set.

Multi-model discharge is implemented as an acyclic discharge DAG: separate
BTOR projections per lemma, transfer nodes between projections, and same-model
SMT nodes for arithmetic facts.  A non-primary node is accepted when it supports
a checked transfer on the target derivation path, so an intermediate root may
carry its own fact cone through one checked hop.  `pcd crossmodel --manifest`
assembles such packages; §7 of `09-composition-guard.md` is the contract.  The
remaining missing piece for arithmetic cases is the typed RTL-to-arithmetic
lift, not the transfer graph.
