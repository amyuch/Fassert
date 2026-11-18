# Hard-case playbook (advisory)

Status: **advisory discovery heuristics**. This document is not a soundness
rulebook. `01-principles.md`, `02-method.md`, `03-rules.md`, and the kernel are
authoritative. Nothing here may weaken a target, turn an assumption into a
lemma, or make a design TCB acceptable.

Use this when a case is too large, too slow, not inductive, or its local facts
do not compose cleanly. The goal is to choose a proof shape before spending the
engine budget.

For arithmetic and iterative datapath cases, the reusable lift pattern is in
[`11-arithmetic-lifting.md`](11-arithmetic-lifting.md). It is guidance for the
proof shape, not an acceptance rule.

---

## 0. First freeze the theorem and trust boundary

Before trying a new tactic:

1. State the target exactly: guards, reset, observation point, and whether the
   claim is a leaf or a full-core/root claim.
2. Record the model identity and build recipe.
3. Name every environment assumption and classify it as an official TCB or a
   lemma obligation.
4. Decide what would count as a *new* proof versus a reproducibility run.

If the target or the trust boundary is still moving, do not decompose yet.

---

## 1. Classify the case before choosing a proof shape

| case shape | typical obligation | first proof shape |
|---|---|---|
| local instruction/leaf | one architectural fact for one instruction | instruction template + local RTL lemma |
| component | RF, ALU, CSR, memory interface | real-model cut + local contract |
| operation family | add/shift/branch/load-store family | per-family lemma + checked dispatch/coverage |
| protocol | serialized RF, bus handshake, multi-cycle memory | phase model + snapshot/timing lemma |
| full core | arbitrary instruction stream, traps, hazards | global invariant + retire/commit link + family lemmas |
| reuse/replay | same model, new evidence run | rebuild model, rerun engine, no staged logs |

The same tactic that closes a leaf can be actively misleading for a full core.
A local lemma is not a substitute for a global invariant.

---

## 2. Diagnose the failure mode before retrying

| symptom | likely cause | next move |
|---|---|---|
| not inductive | invariant too weak, or state is not constrained | strengthen the invariant; add a reachable-state/manifold fact |
| counterexample | wrong observation point, stale monitor, old/new edge mix | inspect the CTI; move the snapshot or split by phase |
| timeout on a small model | wrong backend/logic | route to a different engine; shrink the cut |
| timeout on the full model | monolithic query | decompose before increasing the budget |
| checked lemma does not help | lemma is not the fact the target needs | restate the contract at the target's boundary |
| transfer/reuse fails | model, guards, phase, or transition differ | re-instantiate; do not copy the old proof |
| helper assumption feels circular | target relation is being assumed | replace it with a proved local lemma plus an explicit transfer |

A timeout is not evidence. An `UNKNOWN` is not a proof. A CTI is diagnostic
only.

---

## 3. Cut-selection heuristics

Prefer cuts that have a real semantic boundary and a small, stable contract:

- architectural RF read/write and commit;
- ALU operation result and operand capture;
- memory request/response and acknowledgement;
- CSR read/write and trap side effects;
- pipeline entry/exit, flush, and retire;
- phase boundaries of a serialized protocol.

Good cut properties:

- the cut model can reuse real RTL modules, or has a small explicit
  refinement to them;
- the interface is stated in terms of model signals, not guessed ghost state;
- the observation point is explicit: which edge, old or new value, which
  phase;
- the target-side consumer of the lemma is obvious.

Avoid cuts that hide control flow, trap handling, or an entire instruction
stream. Those are usually invitations to a design TCB in disguise.

---

## 4. Lemma-design checklist

For each local lemma, write down:

1. **Model:** exact source set and model hash.
2. **Contract:** the formula being proved, including guards and sampling edge.
3. **Interface:** the signals shared with the parent model and their timing.
4. **Environment:** reset, free inputs, memory consistency, and TCB kind.
5. **Observation:** transaction start, completion, retire, or another named
   point.
6. **Consumer:** the target assumption or parent obligation that will use it.
7. **Transfer:** how the lemma's formula becomes a fact about the parent model.

Useful recurring shapes:

- read-after-write / read-at-transaction-start;
- write-data and write-address commit;
- shadow/checker update relative to retire;
- x0 or other fixed architectural constants;
- operand/destination identity at the observation point;
- branch-target and PC-update correspondence;
- request/acknowledge handshakes;
- trap suppression and valid requirements.

Do not use a debug or diagnostic signal as a general architectural reference
unless the protocol proves that it is stable outside traps and exceptions.

---

## 5. Composition and transfer

The black-box seam is only sound if the consumer receives the same fact that
the producer proved.

- A helper assertion must be bound to a proved node whose certificate names
  that exact assertion.
- A helper assumption must be bound to a proved lemma or an official TCB in the
  target closure.
- A submodel lemma must have an explicit `reuse`/`transfer` obligation.
- Reuse requires matching model, width, guards, phase, and transition. Similar
  RTL is a reason to try, not evidence.
- Do not replace a transfer with a name-only binding or an identity implication
  that assumes the shared semantics.

If the target assumption and the submodel lemma are stated in different
vocabularies, record the missing refinement as work. Do not silently treat
name similarity as a proof.

---

## 6. Engine-routing heuristics

- Run the smallest model that contains the actual boundary and its timing.
- Use targeted IC3/cill on local lemmas; use the full model for glue and the
  final replay, not for every fact.
- Do not rerun the same query with a larger timeout unless the obligation's
  form has changed.
- Keep each engine invocation attributable to one certificate and one model
  hash.
- If the full model is too large, ask which fact is missing, not which timeout
  is longer.
- Prefer a fresh, reproducible engine run over a copied log unless the run is
  explicitly a replay of the same frozen evidence.

The 3-hour limit is a cutoff, not a proof strategy.

---

## 7. What transfers between cases

There are three different kinds of reuse:

1. **Same case, fresh run.** Rebuild the model and rerun. This checks
   reproducibility and the environment; it proves nothing new.
2. **Same family, different core.** Reuse the *shape* (read-after-write,
   operand identity, branch target, x0, handshake), then re-instantiate the
   actual RTL timing, environment, and transfer.
3. **Full-core reuse.** Reuse the proof architecture and lemma library, not the
   local package. Full-core claims still need a global invariant, coverage of
   instruction families, and a retire/commit refinement.

Do not transfer:
- model hashes;
- engine logs;
- a local lemma whose guards or phase do not match;
- an environment TCB whose contract belongs to another harness;
- a smoke package relabeled as a core/full proof.

---

## 8. Full-core escalation

A full-core case usually needs all of the following:

- a global reachable-state invariant over control and architectural state;
- a retire/commit link from internal state to the RVFI observation;
- coverage over instruction classes and their interactions;
- trap, exception, and CSR side-effect reasoning;
- memory ordering and consistency;
- instruction-family lemmas composed under the global invariant.

Smoke-style local lemmas can be **inputs** to this proof. They are not the
proof. If the target is full-core, expect to spend the decomposition budget on
control invariants and coverage, not only on the datapath.

---

## 9. If you are stuck

Try these in order:

1. Re-read the CTI and move the observation point.
2. Split the property by phase or by instruction family.
3. Strengthen the local contract with an explicit timing/guard fact.
4. Shrink the cut until the model is small enough to diagnose.
5. Find the missing reachable-state invariant.
6. Replace a guessed ghost relation with a model-side contract.
7. Re-route the obligation to a different backend.
8. Only then increase the budget or try a larger monolithic query.

If a proof only closes after adding an assumption that directly restates the
target, stop: that is a circularity signal, not progress.

---

## 10. Review checklist for a hard package

- Is the target unchanged from the frozen case?
- Is every environment assumption an official TCB or a proved lemma?
- Does every helper assumption have a proved consumer and an explicit transfer?
- Is every lemma's observation point stated with old/new timing?
- Does every local model use real RTL where it claims a design link?
- Is every engine run fresh and bound to the model hash?
- Is the root a checked implication from independent target facts?
- Is any local lemma being asked to carry a full-core claim?
- Would a fresh run reproduce the package from the recorded inputs?
- Is there a documented path from the smoke/local result to the core/full
  result, or is that still open?

---

## 11. Experience record template

When a hard case is solved, record the reusable part in a short note:

```text
case shape:
target boundary:
trust boundary / TCB:
cut points:
lemma contracts:
observation/timing points:
transfer obligations:
engine routing:
failure modes seen:
what should transfer:
what must be re-instantiated:
```

Keep the record abstract enough to apply to a new model. The concrete model
hash, logs, and case name belong to the package, not to the reusable experience.
