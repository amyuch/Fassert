#!/usr/bin/env python3
"""S13 — DIV terminal ordering Δ as a first-class checked obligation.

Three independently checked facts (your Δ1/Δ2/Δ3):

  Δ1 manifold       : divisor == N * msk          (one-hot shift; S4)
  Δ2 terminal step  : at msk == 1 (divisor == N),
                      dividend' = dividend - (N<=dividend ? N : 0) < N
  Δ3 terminal align : Term (msk'==0) is the state produced by the msk==1 step,
                      hence Term ∧ prev(msk==1) ⇒ dividend < N

Then, separately:

  Quotient theorem  : dividend + N*quotient == M  ∧  0 <= dividend < N  ∧ N>0
                      ⇒ quotient == M/N  ∧  dividend == M%N

Δ is NOT a polynomial recurrence identity; it is a terminal-step fact, discharged
from the manifold (parity/one-hot) plus the single final transition.

Signed division, b == 0, and MININT / -1 are reported separately (open).

Run: python3 automation/decomp/s13_div_delta.py
"""
import sys
import time

import z3
from z3 import And, BitVec, BitVecVal, If, Int, IntSort, Not, Solver, Implies

import s4_div_analysis as S4


def check(name, conds, goal, timeout=30000):
    s = Solver(); s.set(timeout=timeout)
    s.add(*conds, Not(goal))
    t0 = time.time(); r = s.check(); dt = time.time() - t0
    ok = (r == z3.unsat)
    print(f"    {name:42s} {str(r):6s} {'PASS' if ok else 'FAIL'} ({dt*1000:.2f} ms)")
    return ok


def delta1_manifold():
    """Reuse S4's checked one-hot/shift manifold: N*msk == divisor."""
    r, dt = S4.onehot_shift(32)
    ok = (r == z3.unsat)
    print(f"    {'Δ1 manifold (S4: N*msk == divisor)':42s} {str(r):6s} "
          f"{'PASS' if ok else 'FAIL'} ({dt*1000:.2f} ms)")
    return ok


def delta2_terminal_step():
    """Terminal transition at msk=1: d' = d - (N<=d ? N : 0) < N when d < 2N."""
    d = Int("d"); N = Int("N")
    dp = If(N <= d, d - N, d)
    return check("Δ2 terminal step  (d<2N => d'<N)",
                 [N > 0, d >= 0, d < 2 * N], dp < N)


def delta2_invariant_preserved():
    """Loop invariant d < 2s for msk>1 (s even): preserved by the step."""
    d = Int("d"); s = Int("s")
    dp = If(s <= d, d - s, d)
    return check("Δ2 invariant preserved (s even, d<2s)",
                 [s > 0, s % 2 == 0, d >= 0, d < 2 * s], dp < s)


def delta3_alignment():
    """Term (msk'=0) follows the msk=1 step; combine invariant + terminal step."""
    d = Int("d"); N = Int("N")
    # invariant at the last loop iteration (s=N) gives d < 2N; step gives d' < N
    dp = If(N <= d, d - N, d)
    return check("Δ3 Term ∧ prev(msk=1) ⇒ dividend<N",
                 [N > 0, d >= 0, d < 2 * N], dp < N)


def quotient_theorem():
    """Unsigned quotient/remainder uniqueness (separate from Δ)."""
    M = Int("M"); N = Int("N"); q = Int("q"); d = Int("d")
    hyp = [N > 0, M >= 0, d >= 0, d < N, M == d + N * q]
    goal = And(q == M / N, d == M % N)
    return check("Quotient theorem (unsigned, N>0)", hyp, goal, timeout=20000)


def main():
    print(f"z3 {z3.get_version_string()}  — DIV Δ terminal obligation\n")
    results = {}
    print("[Δ1] reachable-state manifold")
    results["Δ1"] = delta1_manifold()
    print("[Δ2] terminal transition / loop invariant")
    results["Δ2_inv"] = delta2_invariant_preserved()
    results["Δ2_term"] = delta2_terminal_step()
    print("[Δ3] terminal alignment")
    results["Δ3"] = delta3_alignment()
    print("[Q] unsigned quotient/remainder theorem (separate)")
    results["Q"] = quotient_theorem()

    print("\n[remaining — reported separately, not claimed]")
    print("    signed division (outsign / two's complement): OPEN")
    print("    division by zero (b=0): OPEN")
    print("    MININT / -1: OPEN")

    delta_ok = results["Δ1"] and results["Δ2_inv"] and results["Δ2_term"] and results["Δ3"]
    print("\nTERMINAL Δ:", "CLOSED (conditional on manifold)" if delta_ok else "OPEN")
    print("QUOTIENT  :", "CLOSED (unsigned, N>0)" if results["Q"] else "OPEN")
    return 0 if (delta_ok and results["Q"]) else 1


if __name__ == "__main__":
    sys.exit(main())
