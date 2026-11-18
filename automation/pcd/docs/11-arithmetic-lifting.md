# Arithmetic lifting

Arithmetic lifting is the pattern for proving an architectural arithmetic
result over an iterative or multi-stage datapath. It is guidance, not a new
acceptance rule: every edge still has to be checked by the kernel.

## 1. What is being lifted

A useful proof separates three statements:

1. **RTL operation.** The implementation performs the expected step relation:
   capture operands, iterate through the datapath, and expose a result.
2. **Arithmetic operator.** The mathematical relation between operands and
   result is correct. This is usually an induction over a quotient/remainder
   invariant or a bit-vector product lemma.
3. **Architectural observation.** The result and program counter visible to the
   RVFI checker match the architectural instruction semantics.

The proof is complete only when all three are connected on the target model.
A correct arithmetic lemma is not, by itself, evidence about the RTL.

## 2. Lift pattern

Use the same order for multiplication, division, remainder, and smaller
datapath proofs.

1. **Freeze the target contract.** Keep the original case inputs, target
   statements, and primary model identity. A helper model may be used to
   construct evidence, but it does not replace the target model.
2. **Name the operator surface.** Expose the operands, internal accumulator or
   partial-product state, control phase, and result bits. Do not hide a
   datapath fact inside an assumption.
3. **Prove the operator invariant.** Use `btor-smt` or `smt-induction` against
   the actual model expression, or a checked polynomial certificate. The
   invariant must mention the real state and transition, not a same-named
   specification.
4. **Discharge helper assumptions.** If a helper assertion is compiled into a
   model, its assumption must be discharged on the target cone. Compilation is
   not a proof of observational irrelevance.
5. **Transfer to the target model.** A fact on a helper model becomes usable
   only through a checked `btor-projection` or equivalent transfer. Same-width
   whole-atom maps are preferred; free states may use a checked bit map.
6. **Check the root.** The target root must be a checked composition of the
   required guarantees. A non-primary fact that is not on a target derivation
   path is not part of the proof; it may remain as a warning, but it cannot
   close the target.

## 3. Multiplication

A multiplier proof usually needs:

- an operand-capture lemma and a control-phase lemma;
- a partial-product or shift/add invariant over the iterated state;
- a relation between the final product register and the architectural result;
- an observation lemma for `rd` and any PC/retire metadata.

The current worked source is [`../cases/picorv32_mul`](../cases/picorv32_mul),
with a self-contained offline package at
[`../evidence/picorv32_mul`](../evidence/picorv32_mul). The small model-bound
example in [`../examples/solver_bridge_mul`](../examples/solver_bridge_mul)
shows the SMT/projection shape without the full core.

Wide products often need a portfolio or an explicit bit-level decomposition.
If Z3 times out, do not weaken the claim: add a checked lemma, a smaller
projection, or a validated backend. An `unknown` solver result is
`needs_check`, not `proved`.

## 4. Division and remainder

Unsigned division/remainder proofs are organized around the invariant

```
dividend = quotient * divisor + remainder
0 <= remainder < divisor
```

with the iteration showing how the pair `(quotient, remainder)` changes on each
step. Signed division adds sign handling and a final correction phase. The
common proof shape is:

- normalize operands and record the sign/zero special cases;
- prove the unsigned loop invariant;
- prove that the final correction produces the architectural result;
- prove the observation path exposes the corrected quotient/remainder.

Current worked sources are [`../cases/picorv32_div`](../cases/picorv32_div),
[`../cases/picorv32_remu`](../cases/picorv32_remu),
[`../cases/picorv32_rem`](../cases/picorv32_rem), and
[`../cases/picorv32_divu_official`](../cases/picorv32_divu_official). Offline
packages are under [`../evidence`](../evidence), and
[`../examples/remu_operator_bridge`](../examples/remu_operator_bridge) is the
compact operator-bridge example.

## 5. Helper models and observers

A helper model is a construction tool. It may add a monitor, a shadow register,
or a wrapper that makes an internal fact observable. The proof must then show
that the extension is observationally irrelevant to the target cone and that
every helper assumption is discharged.

Practical rules:

- keep helper source changes narrow and explicit;
- preserve the official spec, checker, and CPU sources byte-identically when
  the package is used for official provenance;
- record helper files and their hashes in the proof;
- bind every helper observation to a target guarantee;
- never treat a helper assertion as an axiom.

## 6. Failure modes

| symptom | usual cause | remedy |
|---|---|---|
| arithmetic lemma proved, target open | no checked transfer to the target model | add a projection/refinement edge |
| `unknown` on the operator query | wide product or missing invariant | split the lemma, add a portfolio, or use a validated backend |
| target root proved from a helper model | model identity was ignored | bind the target to the exact primary model |
| helper assumption remains open | helper compiled but not discharged | prove observational irrelevance or remove the helper |
| non-primary node warning | fact is outside every target derivation | connect it with a checked transfer or remove it |
| signed result differs only at the boundary | missing correction/sign case | add the explicit case split and coverage reply |

## 7. Recheck

Offline evidence is checked directly by the kernel:

```sh
./pcd check --case evidence/picorv32_mul/case.json \
            --proof evidence/picorv32_mul/proof.json
./pcd check --case evidence/picorv32_div/case.json \
            --proof evidence/picorv32_div/proof.json
```

The full offline set runs without an engine:

```sh
./pcd bench suites/offline.json
```

The selected source cases can be built and checked through the normal
`./pcd e2e <case>` flow. Current proved rows and bundled status are in
[`../RESULTS.md`](../RESULTS.md).

## 8. Limits

The kernel checks the certificates it is given. It does not invent an
arithmetic invariant, infer a missing transfer, or prove that a helper source
change is irrelevant. Those are proof obligations. A large arithmetic case that
does not yet have a checked invariant or transfer remains `needs_check`, even
if its local lemma is true.
