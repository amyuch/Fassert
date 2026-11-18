# Freeze snapshot (T-E2E regression)

Date: 2026-10-21T09:16:14Z

## Versions
- z3: 5.1.0
- yosys: Yosys 0.60+70 (git sha1 8101c87fa, g++ 12.3.0 -fPIC -O3)
- ric3: rIC3 1.5.2

## Artifact hashes
fdf726aa30de9d2d82f0d95d42f68ff6967f1ae51363325a5eba79d744490ae4  artifact_div_observation.json
88dc016c7f402d3268ea32156eae791263d4a4a23858bff25128fc189d145cf6  artifact_mul_manifold.json
07a15a8e7ab02145437d48eed47b4ba1a8346dfaa0e74953faebd43c73c35d89  artifact_mul_o6.json
f31a1f64284fd0183a241fa81692a5318a223918d02c0e788acdc8539afe7273  artifact_mul_rvfi.json
3cd2f94b456deb97e3487220a3bb295946ed2164b33693b05323f9471d9cebee  artifact_mul_spc.json
83aef725e1a3dd55f449dd6662be1e199397cbc628e1da6e07db6ebaefcb65ce  cases/div/proof_graph.json
a96cc6a7ac87b74b88bd085b6c39163e112ee9ca1f599fdc6e373e36a65431a6  cases/mul/proof_graph.json

## Kernel selftest
    - K7 loop_state: reuse missing checks ['phase', 'transition', 'width']

SELFTEST: PASS

## Portable suite (subset)
--- s1_compose ---

RESULT: ALL OBLIGATIONS DISCHARGED — end-to-end proof certified
--- s2_check_cert ---

RESULT: CERTIFICATE VALIDATED
--- s13_div_delta ---
TERMINAL Δ: CLOSED (conditional on manifold)
QUOTIENT  : CLOSED (unsigned, N>0)
--- s15_div_signed_interface ---
            interface formulation 0.01 s -> the blockage was the
            division operator, not the sign logic (hypothesis A).
--- s16_div_branch_selection ---
BRANCH SELECTION: CHECKED
NEXT: architectural observation is closed in S17/S24 (see LEDGER.md).
