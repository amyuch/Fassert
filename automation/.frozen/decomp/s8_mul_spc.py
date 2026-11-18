#!/usr/bin/env python3
"""S8 — assemble the MUL SPC proof package from checked obligations.

Statuses are reported per obligation; nothing is upgraded beyond what was
actually checked.

  O0  rtl_link        : front-end TCB (BTOR hash)
  O1/O2 manifold      : S7 artifact (ric3 IC3, RTL/BTOR)          -> proved
  B   ring/consecution: S1/S2 algebraic certificate               -> proved
  O5  Delta (endpoint): S1 symbolic unroll of the carry-save loop  -> proved (op-local)
  O4  finalization    : S1 compose                                -> proved
  O6  observable link : retire/writeback chain                    -> OPEN (deep)

The O6 gap is localized: as a global BTOR safety property it is deep
(BMC > 28 cycles / IC3 unknown), so it must be checked as an operation-local
temporal summary (nested SPC), not a monolithic CPU property.

Run: python3 automation/decomp/s8_mul_spc.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import z3
import s1_compose as S1

MANIFOLD_ART = os.path.join(HERE, "artifact_mul_manifold.json")


def main():
    art = json.load(open(MANIFOLD_ART))
    manifold_ok = (art.get("verdict", "").startswith("MANIFOLD CERTIFIED"))
    props = {p["name"]: p for p in art["properties"]}

    # algebraic / endpoint / composition obligations (S1)
    ring_ok, ms_ring = S1.discharge_B_ring(32)
    r_sem, ms_sem = S1.discharge_A_sem_step(32)
    sem_ok = (r_sem == z3.unsat)
    r_end, _terms, ms_end = S1.discharge_C_endpoint(32)
    end_ok = (r_end == z3.unsat)
    r_comp, ms_comp = S1.compose(32)
    comp_ok = (r_comp == z3.unsat)

    print(f"z3 {z3.get_version_string()}")
    print(f"[O0] front-end TCB; BTOR sha256 = {art['btor_sha256'][:16]}…")
    print("[O1/O2] manifold (ric3 IC3, RTL/BTOR):")
    for n in ("h_carrysave", "h_counter", "h_shift_rs1", "h_shift_rs2"):
        p = props.get(n)
        st = p["status"] if p else "missing"
        print(f"    {n:20s} {st:8s} {p['seconds'] if p else '-':>8} s")
    print(f"[B] ring identity      : {'proved' if ring_ok else 'FAIL'} "
          f"({ms_ring*1000:.2f} ms)")
    print(f"[B] purified consecution: {'proved' if sem_ok else 'FAIL'} "
          f"({ms_sem*1000:.2f} ms)")
    print(f"[O5] endpoint (op-local): {'proved' if end_ok else 'FAIL'} "
          f"({ms_end*1000:.2f} ms)")
    print(f"[O4] finalization      : {'proved' if comp_ok else 'FAIL'} "
          f"({ms_comp*1000:.2f} ms)")
    print("[O6] observable link   : OPEN (deep: BMC >28 cycles, IC3 unknown)")

    op_core_ok = manifold_ok and ring_ok and sem_ok and end_ok and comp_ok
    full_ok = op_core_ok  # O6 still open

    pkg = {
        "artifact": "mul_spc_package",
        "btor_sha256": art["btor_sha256"],
        "front_end_tcb": art["front_end"],
        "obligations": {
            "O0_rtl_link": {"status": "tcb",
                            "note": "Yosys/Slang front-end; hash-tied"},
            "O1O2_manifold": {"status": "proved" if manifold_ok else "open",
                              "engine": "ric3-ic3", "source": "S7"},
            "B_ring": {"status": "proved" if ring_ok else "open",
                       "engine": "poly Z/2^W", "seconds": round(ms_ring, 4)},
            "B_consecution": {"status": "proved" if sem_ok else "open",
                               "engine": "purified-linear",
                               "assumes": ["O1O2_manifold"],
                               "seconds": round(ms_sem, 4)},
            "O5_endpoint": {"status": "proved" if end_ok else "open",
                            "engine": "symbolic-unroll (op-local)",
                            "seconds": round(ms_end, 4)},
            "O4_finalization": {"status": "proved" if comp_ok else "open",
                                 "engine": "linear",
                                 "assumes": ["B_consecution", "O5_endpoint"],
                                 "seconds": round(ms_comp, 4)},
            "O6_observable": {"status": "open",
                              "note": "deep; needs op-local temporal summary"},
        },
        "edges": [
            ["O1O2_manifold", "B_consecution"],
            ["B_ring", "B_consecution"],
            ["B_consecution", "O4_finalization"],
            ["O5_endpoint", "O4_finalization"],
            ["O4_finalization", "O6_observable"],
        ],
        "verdict": ("MUL SPC composition checked (op-model) — O6 open"
                    if full_ok else "MUL SPC composition OPEN"),
    }
    path = os.path.join(HERE, "artifact_mul_spc.json")
    json.dump(pkg, open(path, "w"), indent=2)
    print(f"\nRESULT: {pkg['verdict']}")
    print(f"[artifact] {path}")
    return 0 if full_ok else 1


if __name__ == "__main__":
    sys.exit(main())
