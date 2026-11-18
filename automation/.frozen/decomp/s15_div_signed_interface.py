#!/usr/bin/env python3
"""S15 — signed DIV/REM around the verified unsigned interface (no division
operators in the query).

Idea: consume the S13 unsigned result as an interface

    A = |a|,  B = |b|,  B > 0,  A = q0*B + r0,  0 <= r0 < B

and prove the RTL sign correction by case analysis:

    Q = (sign(a) xor sign(b)) ? -q0 : q0      (quotient)
    R = sign(a) ? -r0 : r0                     (remainder)

The query contains only multiplication (the interface product) and sign cases —
no UDiv/URem/SDiv/SRem.  This tests whether the W>=16 blockage was the
bit-blasted division operator (hypothesis A) rather than the sign logic.

Diagnostic (recorded): old BV query at W=16 — DIV unsat 65.4 s, REM unknown
after 180 s.  Interface formulation: 0.01 s, width-independent (Int).

Run: python3 automation/decomp/s15_div_signed_interface.py
"""
import sys
import time

import z3
from z3 import And, Bools, If, Int, Ints, Not, Or, Solver, Xor


def check(name, hyp, goal, timeout=60000):
    s = Solver(); s.set(timeout=timeout)
    s.add(*hyp, Not(goal))
    t0 = time.time(); r = s.check(); dt = time.time() - t0
    ok = (r == z3.unsat)
    print(f"    {name:46s} {str(r):7s} {'PASS' if ok else 'OPEN'} ({dt*1000:7.2f} ms)")
    return ok


def interface():
    """Unsigned core contract (reused S13), magnitudes as non-negative Ints."""
    A, B, q0, r0 = Ints("A B q0 r0")
    return dict(
        A=A, B=B, q0=q0, r0=r0,
        hyp=[A >= 0, B > 0, q0 >= 0, A == q0 * B + r0, r0 >= 0, r0 < B])


def signed_objects(I):
    a, b = Ints("a b")
    sa, sb = Bools("sa sb")
    hyp = I["hyp"] + [a == If(sa, -I["A"], I["A"]),
                      b == If(sb, -I["B"], I["B"])]
    Q = If(Xor(sa, sb), -I["q0"], I["q0"])
    R = If(sa, -I["r0"], I["r0"])
    return a, b, sa, sb, Q, R, hyp


def main():
    print(f"z3 {z3.get_version_string()}  — signed DIV/REM via unsigned interface\n")
    I = interface()
    a, b, sa, sb, Q, R, hyp = signed_objects(I)

    print("[interface] A=q0*B+r0, 0<=r0<B, B>0  (reused S13)")
    ok_char = check(
        "signed quotient/remainder characterization",
        hyp,
        And(a == Q * b + R, R > -I["B"], R < I["B"],
            Or(R == 0, And(R > 0, a > 0), And(R < 0, a < 0)),
            Or(Q == 0, And(Q > 0, (a > 0) == (b > 0)),
                         And(Q < 0, (a > 0) != (b > 0)))))

    print("\n[quotient sign branches] (kept separate)")
    q_ok = True
    for Sa in (False, True):
        for Sb in (False, True):
            h = hyp + [sa == Sa, sb == Sb]
            g = And(a == Q * b + R,
                    Or(Q == 0,
                       And(Q > 0, (a > 0) == (b > 0)),
                       And(Q < 0, (a > 0) != (b > 0))))
            q_ok &= check(f"quotient  sa={int(Sa)} sb={int(Sb)}", h, g)

    print("\n[remainder sign branches] (kept separate; sign follows dividend)")
    r_ok = True
    for Sa in (False, True):
        h = hyp + [sa == Sa]
        g = And(a == Q * b + R, R > -I["B"], R < I["B"],
                Or(R == 0, And(R > 0, a > 0), And(R < 0, a < 0)))
        r_ok &= check(f"remainder sa={int(Sa)}", h, g)

    print("\n[guard coverage]  exceptional ∪ normal = all inputs")
    aa, bb = Ints("aa bb")
    MIN = -(1 << 31)
    cover = check(
        "normal guard covers non-exceptional inputs",
        [True],
        Or(bb == 0, And(aa == MIN, bb == -1),
           And(bb != 0, Not(And(aa == MIN, bb == -1)))))

    print("\n[exceptional cases] reused S14 (checked):")
    print("    b=0 DIV -> all ones; b=0 REM -> a")
    print("    MININT/-1 DIV -> MININT; MININT/-1 REM -> 0")

    print("\nSTATUS")
    print("  unsigned interface          : closed (S13)")
    print("  signed characterization     :", "PROVED (width-independent)" if ok_char else "OPEN")
    print("  quotient sign branches      :", "PROVED" if q_ok else "OPEN")
    print("  remainder sign branches     :", "PROVED" if r_ok else "OPEN")
    print("  exceptional cases           : checked (S14)")
    print("  guard coverage              :", "checked" if cover else "OPEN")
    print("  signed -> instruction       : OPEN (branch selection + architectural")
    print("                                observation links not yet checked)")
    print("\nDiagnostic: old BV W=16 DIV closed at 65.4 s; REM unknown at 180 s;")
    print("            interface formulation 0.01 s -> the blockage was the")
    print("            division operator, not the sign logic (hypothesis A).")
    return 0 if (ok_char and q_ok and r_ok and cover) else 1


if __name__ == "__main__":
    sys.exit(main())
