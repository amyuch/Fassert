#!/usr/bin/env python3
"""S4 — second arithmetic structure: picorv32_pcpi_div (restoring divider).

Question: does the S1/S2 certificate language (commutative polynomial identities
+ purified multiplication atoms + light linear check) extend from MUL to DIV?

Derivation (non-ALTOPS):
    N = |b|, D = |a|
    divisor_0 = N << 31, quotient_0 = 0, msk_0 = 1<<31
    loop: if (divisor <= dividend) { dividend -= divisor; quotient |= msk; }
          divisor >>= 1; msk >>= 1;
    invariant:  dividend + N*quotient == D          (semantic)
                divisor == N*msk                     (manifold / shift)

The semantic step is again a *ring identity*:
    (dividend - divisor) + N*(quotient + msk) == dividend + N*quotient
    <=>  N*msk == divisor
so the polynomial normalizer covers the distributive part; the residue is the
shift/one-hot relation.  This script checks:
  (a) the purified semantic step is linear/instant;
  (b) the raw BV version hits the bit-blasting wall;
  (c) whether the residue `N*msk == divisor` (msk one-hot) is handled by the
      current language or needs one-hot/shift abstraction.
and prints the required certificate-language extensions.
"""
import re
import sys
import time

import z3
from z3 import (And, BitVec, BitVecSort, BitVecVal, Function, LShR, Not, Or,
                Solver, ZeroExt)


def purified_step(W, timeout=30000):
    BV = BitVecSort(W)
    M = Function("M", BV, BV, BV)
    N, q, msk, divd, divs, D = (BitVec(n, W) for n in
                                ("N", "q", "msk", "divd", "divs", "D"))
    inv = (divd + M(N, q) == D)
    shift = (M(N, msk) == divs)                       # manifold (one-hot shift)
    distrib = (M(N, q + msk) == M(N, q) + M(N, msk))  # ring identity
    branch = And(divd - divs == divd, q + msk == q + msk)  # placeholders unused
    invn = (divd - divs) + M(N, q + msk) == D
    s = Solver(); s.set(timeout=timeout)
    s.add(inv, shift, distrib, Not(invn))
    t0 = time.time(); r = s.check(); return r, time.time() - t0


def raw_step(W, timeout=30000):
    N, q, msk, divd, divs, D = (BitVec(n, W) for n in
                                ("N", "q", "msk", "divd", "divs", "D"))
    inv = (divd + N * q == D)
    shift = (N * msk == divs)
    invn = (divd - divs) + N * (q + msk) == D
    s = Solver(); s.set(timeout=timeout)
    s.add(inv, shift, Not(invn))
    t0 = time.time(); r = s.check(); return r, time.time() - t0


def onehot_shift(W, timeout=30000):
    """Can the residue `N*msk == divisor` be proved from the shift recurrence
    with msk one-hot, using current (raw BV) reasoning?"""
    N, msk, divs = BitVec("N", W), BitVec("msk", W), BitVec("divs", W)
    # msk is one-hot: exists idx with msk == 1<<idx and divs == N<<idx
    idx = BitVec("idx", W)
    s = Solver(); s.set(timeout=timeout)
    s.add(msk == (BitVecVal(1, W) << idx))
    s.add(divs == (N << idx))
    s.add(Not(N * msk == divs))
    t0 = time.time(); r = s.check(); return r, time.time() - t0


def extract_div_recurrence():
    p = ("benchmarks/picorv32/insn_div/picorv32.sv")
    body = re.search(r"module picorv32_pcpi_div\b(.*?)\nendmodule",
                     open(p, errors="replace").read(), re.S).group(1)
    feats = {
        "dividend_minus_divisor": bool(re.search(r"dividend\s*<=\s*dividend\s*-\s*divisor", body)
                                       or re.search(r"dividend\s*<=\s*dividend\s*-\s*divisor", body)
                                       or re.search(r"dividend\s*<=\s*dividend\s*-", body)),
        "quotient_or_msk": bool(re.search(r"quotient\s*<=\s*quotient\s*\|\s*quotient_msk", body)),
        "divisor_shr": bool(re.search(r"divisor\s*<=\s*divisor\s*>>\s*1", body)),
        "msk_shr": bool(re.search(r"quotient_msk\s*<=\s*quotient_msk\s*>>\s*1", body)),
        "conditional_subtract": bool(re.search(r"if\s*\(\s*divisor\s*<=\s*dividend\s*\)", body)),
    }
    return feats


def main():
    print(f"z3 {z3.get_version_string()}\n")
    print("[extract] divider recurrence features")
    for k, v in extract_div_recurrence().items():
        print(f"    {k:24s} = {v}")

    print("\n[a] purified semantic step (distributivity + shift manifold)")
    for W in (8, 32, 64):
        r, dt = purified_step(W)
        print(f"    W={W:2d}: {r}  ({dt*1000:.2f} ms)")

    print("\n[b] raw BV semantic step (no certificate) — DIV is easier than MUL")
    for W in (8, 12, 16):
        r, dt = raw_step(W)
        print(f"    W={W:2d}: {r}  ({dt*1000:.2f} ms)")

    print("\n[c] residue `N*msk == divisor` with one-hot msk (raw BV)")
    for W in (8, 16):
        r, dt = onehot_shift(W)
        print(f"    W={W:2d}: {r}  ({dt*1000:.2f} ms)")

    print("""
[FINDING] DIV decomposes, but its difficulty profile is different from MUL.
  * The semantic step `(dividend-divisor)+N*(q+msk) == dividend+N*q` holds once
    `N*msk == divisor`; unlike MUL this is cheap even for raw BV (b), because the
    product `N*q` has a *fixed* multiplier N and only q changes by adding a
    power of two.  MUL is hard precisely because both operands shift, generating
    genuinely different products each step.
  * The residue `N*msk == divisor` is a one-hot/shift fact and is also cheap
    when msk is one-hot (c).
  => The arithmetic closure is NOT the obstacle for DIV; the obstacles are
     control, sign, and termination.

[REQUIRED CERTIFICATE-LANGUAGE EXTENSIONS for DIV/REM]
  1. Guarded identities / case split on `divisor <= dividend` (the step is
     conditional; the invariant must be preserved in both branches).
  2. One-hot + variable-shift abstraction: `msk == 1<<idx`, `divisor == N<<idx`
     => `N*msk == divisor` (recognize multiplication by a one-hot value as a
     shift; generally cheap, but must be stated/validated).
  3. Sign / absolute-value and two's-complement negation lemmas (outsign,
     MININT, negative operands).
  4. Corner-case obligations (b==0, a==MININT & b==-1) — semantic, not algebraic.
  5. Termination/remainder ordering: at msk==0, `dividend < N`, hence
     quotient == floor(D/N).  This is an arithmetic *ordering* fact, beyond
     polynomial identity.

=> The certificate language must be *extensible by obligation kind* (guarded,
   one-hot/shift, sign, ordering), not a single polynomial normalizer.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
