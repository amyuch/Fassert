# Real REMU quotient operator/step bridge

This self-contained package proves a local arithmetic bridge on the real
`remu_complete` BTOR design using its existing 18-property CIll evidence.
It does **not** prove or upgrade the architectural RD target.

From the PCD root:

```sh
python3 examples/remu_operator_bridge/prepare.py
./pcd compose --case examples/remu_operator_bridge/case.json \
  --proof examples/remu_operator_bridge/proof.json
```

The original helper predicates are imported with checked model projections,
preserving their actual guards and registered sampling. Z3 then checks:

- the lower quotient bits are clear through the active mask;
- quotient/mask disjointness;
- equality of unsigned OR and integer addition under the real loop guard;
- the correctly sampled integer quotient update on a non-restarting,
  non-resetting loop transition.

The target `o_remu_or_add` is an observation-only addition to the original
model, and its meaning is bound in the case. The source model, RTL/helper
files, proof provenance and engine log are bundled. `prepare.py` invokes no
hardware engine; the new semantic queries are rechecked by the kernel.

This closes the quotient-operator bridge, not the remaining operand/phase and
architectural writeback correspondence needed for a complete REMU instruction
proof. It is a local checking example, not a new acceleration measurement.
See [the shared semantics and solver bridge](../../docs/10-solver-bridge.md).
