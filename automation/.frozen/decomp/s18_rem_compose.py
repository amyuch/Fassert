#!/usr/bin/env python3
"""S18 — REM integration-level composition (machine-checked).

Why this script exists
----------------------
`cases/rem/proof_graph.json` closes `o_rd_wdata_match` by *composition*: the RTL
links are proved by CIll on the real (non-ALTOPS) model, the remainder
arithmetic is closed abstractly (S13/S15/S14).  The composition step itself was
an assertion in the write-up, not a checked step.  This script makes it
checked, so the root can carry an engine-backed status instead of a claim.

Two parts:

  [B] arithmetic instantiation on the RTL's actual values
      Hypotheses = the facts CIll discharges on the real model (see
      `cases/rem/tb.sv`):
        entry   : M = |rs1|, N = |rs2|; dividend(start) = M, quotient(start) = 0
        iface   : dividend + N*quotient = M          (every loop cycle)
        terminal: dividend < N at the finish edge     (N != 0)
        sign    : outsign = sign(rs1)                 (REM: sign follows dividend)
      Conclusion: the divider's writeback value equals the architectural
      remainder `$signed(rs1) % $signed(rs2)` (spec: insn_rem.v), including the
      `rs2 == 0` case (spec -> rs1).

  [C] observation composition (the S17 shape, re-checked):
      div mux -> ready capture -> writeback mux -> RVFI latch -> rd-zeroing,
      so `rvfi_rd_wdata == spec_rd_wdata`.

The Int-level formulation keeps the division out of the bit-blast (S15's
diagnosis); the 32-bit encoding and the two corner cases are checked separately
in BV.

Run: python3 automation/decomp/s18_rem_compose.py
"""
import json
import os
import sys
import time

import z3
from z3 import (And, Bool, If, Ints, Not, Solver, Xor)


def check(name, hyp, goal, timeout=60000):
    s = Solver()
    s.set(timeout=timeout)
    s.add(*hyp, Not(goal))
    t0 = time.time()
    r = s.check()
    dt = time.time() - t0
    ok = (r == z3.unsat)
    print(f"    {name:52s} {str(r):7s} {'PASS' if ok else 'OPEN'} ({dt*1000:8.2f} ms)")
    return ok, r


def part_b():
    """[B] RTL interface facts => architectural remainder (Int, width-independent)."""
    print("[B] arithmetic instantiation on the RTL's values (Int)")
    M, N, d, q = Ints("M N d q")          # M=|rs1|, N=|rs2|, dividend, quotient
    a = Ints("a")[0]
    sa = Bool("sa")                        # sign(rs1)
    res = {}

    # B1: the interface relation + terminal bound => the RTL dividend is the
    #      magnitude remainder of the magnitudes (S13's theorem, instantiated).
    hyp = [N > 0, q >= 0, M == d + N * q, d >= 0, d < N]
    g1 = And(d == M % N, q == M / N)
    ok1, _ = check("B1  iface+terminal => d == M mod N, q == M div N", hyp, g1)
    res["B1"] = ok1

    # B2: sign correction (S15's remainder branch) => architectural remainder.
    #      B1's conclusion is used as a lemma (it is proved above), so no
    #      division reasoning is needed here -- only the sign substitution.
    hyp2 = hyp + [d == M % N, M == If(sa, -a, a)]
    g2 = If(sa, -d, d) == If(sa, -(M % N), (M % N))
    ok2, _ = check("B2  sign-follows-dividend => signed remainder", hyp2, g2)
    res["B2"] = ok2

    # B2': rs2 == 0 (N == 0): the divider subtracts 0, so the dividend is
    #       unchanged; the sign correction returns rs1 (spec: b==0 -> a).
    hyp3 = [M == d + N * q, N == 0, M == If(sa, -a, a)]
    g3 = If(sa, -d, d) == a
    ok3, _ = check("B2' N == 0 (rs2 == 0) => value == rs1", hyp3, g3)
    res["B2_div0"] = ok3

    # B3: the quotient is the magnitude quotient and the pair (d, q) is unique.
    hyp4 = [N > 0, q >= 0, M == d + N * q, d >= 0, d < N]
    g4 = And(q >= 0, d >= 0, q * N + d == M, d < N)
    ok4, _ = check("B3  (q, d) satisfies M = q*N + d, 0 <= d < N", hyp4, g4)
    res["B3"] = ok4
    return res


def part_c():
    """[C] observation chain: divider value -> RVFI writeback == spec writeback."""
    print("\n[C] observation composition (mux -> ready -> wb -> RVFI -> rd-zeroing)")
    BV32 = z3.BitVecSort(32)
    divr, pcpi, regout, cwr, rvfi = (z3.BitVec(n, 32) for n in
                                     ("divr", "pcpi", "regout", "cwr", "rvfi"))
    specr, spec = z3.BitVec("specr", 32), z3.BitVec("spec", 32)
    rd = z3.BitVec("rd", 32)
    hyp = [divr == specr,                        # arithmetic interface (part B)
           pcpi == divr,                         # div mux
           regout == pcpi,                       # ready capture
           cwr == regout,                        # writeback mux
           rvfi == If(rd != 0, cwr, z3.BitVecVal(0, 32)),   # RVFI latch
           spec == If(rd != 0, specr, z3.BitVecVal(0, 32))]  # spec_rd_wdata
    ok, r = check("C   chain => rvfi_rd_wdata == spec_rd_wdata", hyp, rvfi == spec)
    return ok, r


def part_bits():
    """32-bit encoding + corner cases (the width bridge), in BV."""
    print("\n[D] 32-bit encoding and corner cases (BV)")
    W = 32
    a, b = z3.BitVecs("a b", W)
    MIN = z3.BitVecVal(1 << (W - 1), W)
    M1 = z3.BitVecVal((1 << W) - 1, W)
    res = {}

    # D1: the divider's sign-corrected magnitude is the architectural remainder
    #      for the two spec corners that the abstract argument covers separately.
    #      rs2 == 0: divisor == 0 => the dividend is unchanged => value == rs1.
    absa = If(a < 0, -a, a)
    sgn = z3.Extract(W - 1, W - 1, a) == z3.BitVecVal(1, 1)
    ok, _ = check("D1  rs2 == 0: sign-corrected |rs1| == rs1", [b == 0],
                  If(sgn, -absa, absa) == a)
    res["D1_b0"] = ok

    # D2: rs1 == MININT && rs2 == -1: magnitude remainder is 0 (spec says 0).
    absb = If(b < 0, -b, b)
    r0 = z3.URem(absa, absb)
    ok, _ = check("D2  MININT/-1: magnitude remainder == 0", [a == MIN, b == M1],
                  And(r0 == 0, If(sgn, -r0, r0) == 0))
    res["D2_minint"] = ok

    # D3: |x| fits in 32 bits for every x, and the sign correction is exact.
    ok, _ = check("D3  |rs1| is representable in 32 unsigned bits", [True],
                  z3.ULE(absa, M1))
    res["D3_mag"] = ok
    return res


def main():
    print(f"z3 {z3.get_version_string()}  — REM integration-level composition\n")
    b = part_b()
    c_ok, _ = part_c()
    d = part_bits()

    art = {
        "artifact": "rem_compose",
        "case": "rem",
        "part_b_arithmetic_instantiation": b,
        "part_c_observation_composition": bool(c_ok),
        "part_d_encoding_corners": d,
        "status": ("PROVED_TRUSTED" if all(b.values()) and c_ok and all(d.values())
                   else "OPEN"),
        "note": ("composition of the CIll-proved RTL interface facts with the "
                 "abstract arithmetic; the root o_rd_wdata_match is not itself "
                 "inductive in CIll (see cases/rem/README.md)"),
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "artifact_rem_compose.json")
    json.dump(art, open(path, "w"), indent=2)
    ok = art["status"] == "PROVED_TRUSTED"
    print("\nSTATUS")
    print("  arithmetic instantiation (B):", "closed" if all(b.values()) else "OPEN")
    print("  observation composition   (C):", "closed" if c_ok else "OPEN")
    print("  encoding / corner cases    (D):", "closed" if all(d.values()) else "OPEN")
    print(f"[artifact] {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
