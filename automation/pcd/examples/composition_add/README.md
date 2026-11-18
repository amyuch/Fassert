# Checked ADD observer projection

This self-contained offline example transfers the 25 properties of an existing
successful picorv32 ADD model to a model with an extra disconnected observer.
The target remains the original PC and destination-register data properties.

From the PCD root:

```sh
python3 examples/composition_add/prepare.py
./pcd compose --case examples/composition_add/case.json \
  --proof examples/composition_add/proof.json
```

Expected: `accepted: true`, `composition.status: checked`, 25 checked edges.
Leaf assurance remains REPLAY. `prepare.py` regenerates the observer model,
case, explicit projection maps and proof from bundled evidence; it runs no engine.

The source BTOR, checker/RTL and CIll log were copied from
`smoke_picorv32_insn_add/20261101T041641Z-smoke_picorv32_insn_add-58830d`.
The original run's case/proof records are under `evidence/source/`. They are
provenance, not instructions. No original runs directory is needed to reproduce
this example. This reuses frozen engine evidence and is a development checking
demonstration, not a fresh or blind planner result or an acceleration measurement.

The verifier checks actual property expressions, state updates, initialization,
and source constraints under each mapping. The extra observer must not affect
those cones. Changing an original transition or adding an unmatched source
assumption prevents acceptance, even if property names remain unchanged.

See [the guard specification](../../docs/09-composition-guard.md) for the soundness
direction, limitations, and migration policy.
