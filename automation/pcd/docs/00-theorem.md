# Relative-soundness theorem and computed disposition

This document defines the meaning of a final `proved` result. It does not add a
new trust assumption; it makes the trust boundary explicit and makes open side
conditions machine-readable. The operational rules are in
[`03-rules.md`](03-rules.md); arithmetic patterns are in
[`11-arithmetic-lifting.md`](11-arithmetic-lifting.md).

## 1. Judgments

A proof package is checked against an original case contract. The kernel emits
exactly one of three computed dispositions:

| status | meaning |
|---|---|
| `proved` | Every required obligation in every target closure is discharged under the TCB, and the target composition is checked. This is the only final accept. |
| `needs_check` | The package is well formed but at least one required obligation has no valid witness. The open obligations are the residual. This is not a success, not a partial accept, and not an assumption. |
| `reject` | The package contains invalid or refuted evidence, or the case/proof is malformed. `reject` is a statement about the package, not about the design. |

The status is computed by `kernel/disposition.py` from the case, the proof graph,
and the checker issues. It is never read from a stored tag. A proof that carries
a status field is rejected by the schema/kernel rules.

## 2. Claim

Let `C` be a case contract with target properties `P_1 ... P_n`, and let `Π` be
a proof package. The kernel's `proved` judgment means:

> For every target `i`, every execution of the target model that satisfies the
> case's environment contract satisfies `P_i`, relative to the trusted computing
> base described in §5.

The target model is the model bound in the case and proof. It is not replaced by
a helper model or a model with a different hash.

## 3. Obligations and directions

The ledger has one required obligation for each of the following:

1. **Target root.** The root obligation is a checked composition on the target
   model. Its goal is the target property, and its premises are exactly the
   target's required guarantees.
2. **Premises.** Every referenced premise exists and provides the guarantee it
   is required to provide.
3. **Local evidence.** Every non-TCB node consumed by the closure has a valid
   `CHECKED` or `REPLAY` witness with verdict `proved`.
4. **Model boundary.** A node on a different model is connected to the target by
   a checked refinement/transfer edge. A same-hash model needs no transfer; a
   different hash does.
5. **Helper assumptions.** A helper assumption is discharged on the original
   model. A helper assertion does not become an assumption merely because the
   helper is compiled into the model.
6. **Target properties.** Every property named by the case's
   `required_properties` is bound to a proved destination property.
7. **Coverage.** Guard partitions are exhaustive and their coverage certificate
   is checked.

Directions that are easy to get backwards:

- A source proof does **not** transfer to a destination model by name, colour,
  helper decomposition, or planner intent. The transfer obligation is
  `destination executions ⊆ source executions` along an explicit relation.
- A stronger environment is not an accept. It requires `E_use ⇒ E_case`.
- A stronger property is not an accept. It requires `P_proved ⇒ P_claim`.
- A helper may be a conservative extension of the design only if the extension
  is proved observationally irrelevant to the target cone. Compiling the helper
  into the model is not that proof.
- A missing obligation is `needs_check`, not a vacuous truth. A false witness is
  `reject`, not `needs_check`.

## 4. Residual completeness

For every non-discharged required obligation there is a residual entry with an
identifier and a reason. The residual is the machine-readable statement of what
is still missing. In particular:

- An error attached to a target-closure node becomes an open residual.
- An error not attached to any target-closure obligation is a package-level
  defect and makes the disposition `reject`; it cannot be hidden by a complete
  looking closure.

This is the no-implicit-acceptance property: there is no path from a missing
premise, an unproved transfer, a helper assumption, or a stored policy to
`accepted = true` in complete mode.

## 5. Trusted computing base

The theorem is relative to:

- The frontend translation from RTL to BTOR2 (Yosys and the project build).
- rIC3/BMC engine verdicts and their replay logs.
- Z3 and the canonical SMT/polynomial encodings.
- The model and certificate parsers, the expression semantics, the composition
  checker, and this disposition implementation.

Trust in these components is explicit. The kernel does not trust a planner, a
status field, a model name, a helper file, a stored acceptance tag, or an
engine's prose. A TCB node is accepted only for the official kinds
`frontend`, `engine`, `checker`, and `isa_model`, and a TCB may not be a direct
target premise in complete mode.

## 6. Limits

The composition checker implements a structural projection.  Non-free
state/input atoms use same-width whole-atom maps.  Free source states, which
have neither an initial value nor a next-state function, may use a checked
bit-level map (`free_map`).  The map is a proposal, never evidence: the checker
re-runs `Model.bits` with per-bit atom labels and verifies the property,
initial values, transitions, and source constraints under that map.  A source
free bit may share one destination free bit, but one source bit may not be
forced to two independent destination bits; the latter would constrain the
destination's freedom and is rejected.  The bit normalizer follows the
authoritative `Model.bits` concatenation convention: for `concat(a, b)`,
`b` is the low half and `a` is the high half.

The checker composes an acyclic discharge DAG. A same-model SMT/compose node is
a checked implication; a model hop is a checked projection; a non-primary fact
is accepted when it supports a checked transfer on the target derivation path,
even when the transfer carries an intermediate root rather than naming the fact
directly. This is sound because every edge is checked locally and the target
root is on the primary model. It does not add trust in `reuse` records,
planners, or stored status.

The checker still does not implement arbitrary relational refinement,
asynchronous stuttering, or arrays. When those are required, the honest result
is `needs_check` with a projection residual; it is not an accept. Closing those
residuals is future work, not a change to the theorem. Reusable arithmetic
patterns are described in [`11-arithmetic-lifting.md`](11-arithmetic-lifting.md).
