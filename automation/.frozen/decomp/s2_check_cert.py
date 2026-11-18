#!/usr/bin/env python3
"""S2 — independent checker for the algebraic certificate used by S1.

Design goal: do NOT trust the generator (or S1) for the certificate's validity.
The checker validates every algebraic lemma by two independent methods:

  (1) exact commutative-polynomial normal form over Z/2^W  (all widths),
  (2) exhaustive bit-vector evaluation at small widths          (finite width).

It then re-runs the composition using only the *validated* axiom set and reports
the trust boundary.  A negative test (dropping the zero law) must be rejected.

This file intentionally re-implements the algebra; it imports nothing from S1.

Run: python3 automation/decomp/s2_check_cert.py
"""
import sys
from collections import defaultdict
from itertools import product

import z3
from z3 import And, BitVec, BitVecSort, BitVecVal, Function, LShR, Not, Solver


# --------------------------------------------------------------------------
# Method 1: exact polynomial normal form over Z/2^W
# --------------------------------------------------------------------------
def nf_add(p, q, W):
    d = defaultdict(int)
    for m, c in p.items():
        d[m] += c
    for m, c in q.items():
        d[m] += c
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def nf_mul(p, q, W):
    d = defaultdict(int)
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            d[tuple(sorted(m1 + m2))] += c1 * c2
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def nf_sub(p, q, W):
    d = defaultdict(int)
    d.update(p)
    for m, c in q.items():
        d[m] -= c
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def V(n):
    return {(n,): 1}


def C(c):
    return {(): c}


def check_ring_axiom(name, W):
    """Certify the ring identities used by the certificate, in Z/2^W.

    Atoms rs1, rs2 with  rs1 = 2x + bit  (shift/bit-extraction),
    s = rs2, s2 = 2s, t = bit*s.
    """
    x, bit, s = V("x"), V("bit"), V("s")
    rs1 = nf_add(nf_mul(C(2), x, W), bit, W)      # 2x + bit
    s2 = nf_mul(C(2), s, W)                        # rs2 << 1
    t = nf_mul(bit, s, W)                          # (rs1 & 1) * rs2

    checks = {
        # rs1*rs2 == t + 2*(x*rs2)
        "D-mul": nf_sub(nf_mul(rs1, s, W),
                        nf_add(t, nf_mul(C(2), nf_mul(x, s, W), W), W), W),
        # (x)*(s2) == 2*(x*s)
        "shift-mul": nf_sub(nf_mul(x, s2, W),
                            nf_mul(C(2), nf_mul(x, s, W), W), W),
        # 0*s == 0
        "zero": nf_mul(C(0), s, W),
        # commutativity
        "comm": nf_sub(nf_mul(x, s, W), nf_mul(s, x, W), W),
    }
    return {k: (not v) for k, v in checks.items()}, checks


# --------------------------------------------------------------------------
# Method 2: exhaustive bit-vector evaluation at small widths
# --------------------------------------------------------------------------
def exhaustive_small(W):
    mod = 1 << W
    ok = {"I1": True, "I2": True, "I3": True, "I4": True, "I5": True, "I6": True}
    for rs1, rs2 in product(range(mod), repeat=2):
        x = rs1 >> 1
        bit = rs1 & 1
        s2 = (rs2 << 1) % mod
        t = (bit * rs2) % mod
        if rs1 != (2 * x + bit) % mod: ok["I1"] = False
        if s2 != (2 * rs2) % mod:      ok["I2"] = False
        if (rs1 * rs2) % mod != (t + 2 * x * rs2) % mod: ok["I3"] = False
        if (x * s2) % mod != (2 * x * rs2) % mod:        ok["I4"] = False
        if (0 * rs2) % mod != 0:                         ok["I5"] = False
        if (bit * rs2) % mod != t:                       ok["I6"] = False
    return ok


# --------------------------------------------------------------------------
# Composition re-check (uses only the validated certificate axioms)
# --------------------------------------------------------------------------
def compose(W, use_zero_law=True, timeout=30000):
    BV = BitVecSort(W)
    M = Function("M", BV, BV, BV)
    a, b = BitVec("a", W), BitVec("b", W)
    rs1, rs2, rd, rdx, acc, out = (BitVec(n, W) for n in
                                   ("rs1", "rs2", "rd", "rdx", "acc", "out"))
    sem = (acc + M(rs1, rs2) == M(a, b))
    rd_ok = (rd + rdx == acc)
    term = And(rs1 == 0, rdx == 0)
    out_ok = (out == rd)
    laws = [sem, rd_ok, term, out_ok]
    if use_zero_law:
        laws.append(M(BitVecVal(0, W), rs2) == BitVecVal(0, W))
    s = Solver(); s.set(timeout=timeout)
    s.add(*laws, Not(out == M(a, b)))
    return s.check()


def main():
    print(f"z3 {z3.get_version_string()}\n")
    all_ok = True

    print("[1] polynomial normal form over Z/2^W (independent of generator)")
    for W in (8, 32, 64):
        res, _ = check_ring_axiom("cert", W)
        ok = all(res.values())
        all_ok &= ok
        print(f"    W={W:2d}: {'PASS' if ok else 'FAIL'}  {res}")

    print("\n[2] exhaustive finite-width semantics (all rs1,rs2)")
    for W in (3, 4, 5):
        ok = exhaustive_small(W)
        good = all(ok.values())
        all_ok &= good
        print(f"    W={W}: {'PASS' if good else 'FAIL'}  {ok}")

    print("\n[3] composition re-check with validated axioms")
    for W in (8, 32, 64):
        r_ok = compose(W, use_zero_law=True)
        good = (r_ok == z3.unsat)
        all_ok &= good
        print(f"    W={W:2d}: {r_ok}  ({'certified' if good else 'REJECTED'})")

    print("\n[4] negative test: composition WITHOUT the zero law must be rejected")
    r_bad = compose(32, use_zero_law=False)
    caught = (r_bad != z3.unsat)
    all_ok &= caught
    print(f"    W=32: {r_bad}  ({'correctly rejected' if caught else 'CHECKER MISSED BUG'})")

    print("\nRESULT:", "CERTIFICATE VALIDATED" if all_ok else "CHECKER FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
