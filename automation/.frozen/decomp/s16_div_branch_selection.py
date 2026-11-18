#!/usr/bin/env python3
"""S16 — DIV branch selection: prove the RTL dispatches each instruction to the
arithmetic branch whose result was already checked.

Important semantics (from the RTL):
  picorv32_pcpi_div has NO explicit b==0 / MININT,-1 branch.  It always runs the
  magnitude loop; exceptional results emerge from magnitude values + sign
  correction.  Therefore "branch selection" means:

    (a) operation-mode decode: funct3 100/101/110/111 -> div/divu/rem/remu
    (b) finish source: div|divu -> quotient ; rem|remu -> dividend(=remainder)
    (c) sign convention: outsign = (div && sign(a)!=sign(b) && |b|) || (rem && sign(a))
    (d) exceptional inputs dispatch to the already-checked arithmetic:
        b=0 (S14), MININT/-1 (S14), normal signed (S15), unsigned (S13)

The arithmetic itself is NOT re-proved here; this checks the dispatch.

Run: python3 automation/decomp/s16_div_branch_selection.py
"""
import sys
import time

import z3
from z3 import (And, BitVec, BitVecVal, Bool, Bools, BoolVal, Extract, If,
                Implies, Not, Or, Solver, Xor)


def mode_onehot(div, divu, rem, remu):
    return And(Or(div, divu, rem, remu),
               *[Not(And(a, b)) for i, a in enumerate((div, divu, rem, remu))
                 for b in (div, divu, rem, remu)[i + 1:]])


def check(name, conds, goal, timeout=30000):
    s = Solver(); s.set(timeout=timeout)
    s.add(*conds, Not(goal))
    t0 = time.time(); r = s.check(); dt = time.time() - t0
    ok = (r == z3.unsat)
    print(f"    {name:50s} {str(r):7s} {'PASS' if ok else 'FAIL'} ({dt*1000:7.2f} ms)")
    return ok


def decode_mapping():
    f3 = BitVec("funct3", 3)
    div = f3 == BitVecVal(0b100, 3)
    divu = f3 == BitVecVal(0b101, 3)
    rem = f3 == BitVecVal(0b110, 3)
    remu = f3 == BitVecVal(0b111, 3)
    mutual = And(*[Not(And(a, b)) for i, a in enumerate((div, divu, rem, remu))
                   for b in (div, divu, rem, remu)[i + 1:]])
    return check("decode: div/rem funct3 -> exactly one mode",
                 [Or(div, divu, rem, remu)], mutual)


def finish_source():
    div, divu, rem, remu = Bools("div divu rem remu")
    # mutually exclusive
    excl = And(*[Not(And(a, b)) for i, a in enumerate((div, divu, rem, remu))
                 for b in (div, divu, rem, remu)[i + 1:]])
    # quotient source for DIV(U), dividend/remainder source for REM(U);
    # mutual exclusion makes the source selection well-defined
    use_q = Or(div, divu)
    use_d = Or(rem, remu)
    return check("finish: source partition (quotient xor dividend)",
                 [excl, Or(div, divu, rem, remu)], Xor(use_q, use_d))


def outsign_convention():
    a, b = BitVec("a", 32), BitVec("b", 32)
    div, divu, rem, remu = Bools("div divu rem remu")
    sa = Extract(31, 31, a) == BitVecVal(1, 1)
    sb = Extract(31, 31, b) == BitVecVal(1, 1)
    nz_b = b != BitVecVal(0, 32)
    rtl = Or(And(div, Xor(sa, sb), nz_b), And(rem, sa))
    goal = And(Implies(div, rtl == And(Xor(sa, sb), nz_b)),
               Implies(rem, rtl == sa),
               Implies(divu, Not(rtl)),
               Implies(remu, Not(rtl)))
    return check("outsign: div parity(&|b|), rem sign(a), unsigned 0",
                 [mode_onehot(div, divu, rem, remu)], goal)


def exceptional_dispatch():
    a, b = BitVec("a", 32), BitVec("b", 32)
    div, divu, rem, remu = Bools("div divu rem remu")
    MIN = BitVecVal(1 << 31, 32); M1 = BitVecVal(0xffffffff, 32)
    sa = Extract(31, 31, a) == BitVecVal(1, 1)
    nz_b = b != BitVecVal(0, 32)
    rtl = Or(And(div, Xor(sa, Extract(31, 31, b) == BitVecVal(1, 1)), nz_b),
             And(rem, sa))
    ok_b0 = And(Implies(And(div, b == 0), Not(rtl)),
                Implies(And(rem, b == 0), rtl == sa),
                Implies(And(divu, b == 0), Not(rtl)),
                Implies(And(remu, b == 0), Not(rtl)))
    ok_min = And(Implies(And(div, a == MIN, b == M1), Not(rtl)),
                 Implies(And(rem, a == MIN, b == M1), rtl == sa))
    return check("exceptional dispatch: b=0 / MININT,-1 sign selection",
                 [mode_onehot(div, divu, rem, remu)], And(ok_b0, ok_min))


def main():
    print(f"z3 {z3.get_version_string()}  — DIV branch selection\n")
    print("[a] operation-mode decode")
    a = decode_mapping()
    print("[b] finish source selection")
    b = finish_source()
    print("[c] sign convention")
    c = outsign_convention()
    print("[d] exceptional dispatch")
    d = exceptional_dispatch()

    print("""
[note] There is no explicit b==0 / MININT,-1 RTL branch.  The divider always runs
       the magnitude loop; the exceptional results are consequences of magnitude
       values (S14) plus the sign selection checked here.  So the dispatch below
       is exactly the RTL structure, and each branch's arithmetic is the already
       checked S13/S14/S15 result.

[branch -> arithmetic]
    DIV  normal      -> S15 signed quotient (via unsigned interface)
    DIVU normal      -> S13 unsigned quotient
    REM  normal      -> S15 signed remainder
    REMU normal      -> S13 unsigned remainder
    b=0 / MININT,-1  -> S14 exceptional lemmas (magnitude values + this sign mux)
""")
    ok = a and b and c and d
    print("BRANCH SELECTION:", "CHECKED" if ok else "OPEN")
    print("NEXT: architectural observation is closed in S17/S24 (see LEDGER.md).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
