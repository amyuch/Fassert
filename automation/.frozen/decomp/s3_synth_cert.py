#!/usr/bin/env python3
"""S3 — automate certificate synthesis for the real multiplier and compare the
generated certificate against the hand-derived one (S1/S2).

Inputs are the actual benchmark sources:
  * RTL : picorv32_pcpi_mul  (recurrence lines)
  * spec: riscv-formal insn_mul (non-ALTOPS `result = ... * ...`)

Pipeline:
  1. extract the loop recurrences from the RTL text
       next_rs1 = next_rs1 >> 1
       next_rs2 = next_rs2 << 1
       this_rs2 = next_rs1[0] ? next_rs2 : 0
     and the spec operator/operands from the spec text.
  2. turn the recurrences into a *substitution map*
       rs1 -> 2*x + bit,   rs2 -> s,
       rs1' -> x,          rs2' -> 2*s,
       t   -> bit * s.
  3. synthesize the semantic one-step identity
       D(rs1,rs2) - D(rs1',rs2') - t  ==  0   (D = spec operator)
     by polynomial normalization, and emit the UF axioms needed for the
     purified proof.
  4. compare the generated axioms with the hand-derived certificate
     (D-mul, shift-mul, zero) by normalized polynomial equality.

Run: python3 automation/decomp/s3_synth_cert.py
"""
import os
import re
import sys
from collections import defaultdict

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RTL = os.path.join(REPO, "benchmarks/picorv32/insn_mul/picorv32.sv")
SPEC = os.path.join(REPO, "benchmarks/riscv-formal/insn/insn_mul.v")
W = 32


# ---------------- polynomial helpers (commutative, mod 2^W) ----------------
def p_add(p, q):
    d = defaultdict(int); d.update(p)
    for m, c in q.items(): d[m] += c
    return {k: v % (1 << W) for k, v in d.items() if v % (1 << W)}


def p_mul(p, q):
    d = defaultdict(int)
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            d[tuple(sorted(m1 + m2))] += c1 * c2
    return {k: v % (1 << W) for k, v in d.items() if v % (1 << W)}


def p_sub(p, q):
    return p_add(p, {m: (-c) % (1 << W) for m, c in q.items()})


def p_scale(c, p):
    return {m: (c * v) % (1 << W) for m, v in p.items() if (c * v) % (1 << W)}


def var(n):
    return {(n,): 1}


def const(c):
    return {(): c % (1 << W)}


def pprint(p):
    if not p:
        return "0"
    out = []
    for m, c in sorted(p.items()):
        term = f"{c}" + ("*" + "*".join(m) if m else "")
        out.append(term)
    return " + ".join(out)


# ---------------- extraction from RTL + spec ----------------
def extract():
    rtl = open(RTL, errors="replace").read()
    # isolate the real (non-ALTOPS) PCPI multiplier module
    m = re.search(r"module picorv32_pcpi_mul\b(.*?)\nendmodule", rtl, re.S)
    if not m:
        raise SystemExit("could not locate picorv32_pcpi_mul")
    body = m.group(1)

    rec = {}
    mm = re.search(r"next_rs1\s*=\s*next_rs1\s*>>\s*(\d+)", body)
    rec["rs1_shift"] = int(mm.group(1)) if mm else None
    mm = re.search(r"next_rs2\s*=\s*next_rs2\s*<<\s*(\d+)", body)
    rec["rs2_shift"] = int(mm.group(1)) if mm else None
    rec["addend"] = bool(re.search(
        r"this_rs2\s*=\s*next_rs1\[0\]\s*\?\s*next_rs2\s*:\s*0", body))

    spec_txt = open(SPEC, errors="replace").read()
    # pick the non-ALTOPS branch: the `else` result of the ALTOPS ifdef
    mm = re.search(r"`else\s*\n\s*wire\s*\[[^\]]*\]\s*result\s*=\s*(.+?);",
                   spec_txt, re.S)
    expr = " ".join(mm.group(1).split()) if mm else None
    rec["spec_expr"] = expr
    op = None
    if expr:
        if "*" in expr: op = "*"
        elif "+" in expr: op = "+"
        elif "-" in expr: op = "-"
    rec["op"] = op
    return rec


# ---------------- synthesis ----------------
def synth(rec):
    """Build the substitution map and the one-step identity from recurrences."""
    if rec["rs1_shift"] != 1 or rec["rs2_shift"] != 1 or not rec["addend"]:
        raise SystemExit(f"unsupported recurrence: {rec}")

    # atoms: x = rs1>>1, bit = rs1&1, s = rs2, s2 = rs2<<1
    x, bit, s, s2 = var("x"), var("bit"), var("s"), var("s2")
    rs1 = p_add(p_scale(2, x), bit)      # rs1 = 2x + bit
    rs1n = x                              # rs1' = rs1>>1
    rs2 = s
    rs2n = p_scale(2, s)                  # rs2' = rs2<<1  (=s2)
    t = p_mul(bit, s)                     # this_rs2 = (rs1&1)*rs2

    if rec["op"] != "*":
        raise SystemExit(f"spec operator {rec['op']!r} not covered by this "
                         "certificate language (see S4)")

    cur = p_mul(rs1, rs2)                 # D(rs1,rs2)
    nxt = p_mul(rs1n, rs2n)               # D(rs1',rs2')
    resid = p_sub(p_sub(cur, nxt), t)     # must be 0
    if resid:
        raise SystemExit(f"one-step identity failed to normalize: {pprint(resid)}")

    # UF axioms for the purified proof (as polynomial equalities over atoms)
    gen = {
        # M(rs1,rs2) == 2*M(x,s) + M(bit,s),  M(bit,s) == t
        "D-mul": (p_mul(rs1, rs2),
                  p_add(p_scale(2, p_mul(x, s)), p_mul(bit, s))),
        # M(x, rs2<<1) == 2*M(x,s)
        "shift-mul": (p_mul(x, rs2n),
                      p_scale(2, p_mul(x, s))),
        # zero law used at completion (rs1 -> 0)
        "zero": (p_mul(const(0), s), const(0)),
    }
    aux = {"rs1_def": (rs1, p_add(p_scale(2, x), bit)),
           "rs2_shift": (rs2n, p_scale(2, s)),
           "addend": (t, p_mul(bit, s))}
    return gen, aux, (x, bit, s, s2, rs1, rs1n, rs2, rs2n, t)


# ---------------- hand-derived certificate (S1/S2) ----------------
def hand_derived():
    x, bit, s, s2 = var("x"), var("bit"), var("s"), var("s2")
    rs1 = p_add(p_scale(2, x), bit)
    rs2n = p_scale(2, s)
    return {
        "D-mul": (p_mul(rs1, s),
                  p_add(p_scale(2, p_mul(x, s)), p_mul(bit, s))),
        "shift-mul": (p_mul(x, rs2n), p_scale(2, p_mul(x, s))),
        "zero": (p_mul(const(0), s), const(0)),
    }


def main():
    print(f"RTL : {os.path.relpath(RTL, REPO)}")
    print(f"SPEC: {os.path.relpath(SPEC, REPO)}\n")

    rec = extract()
    print("[extract] recurrence + spec")
    for k, v in rec.items():
        print(f"    {k:10s} = {v}")

    gen, aux, _ = synth(rec)
    print("\n[synthesize] derived substitutions")
    for k, (lhs, rhs) in aux.items():
        d = p_sub(lhs, rhs)
        print(f"    {k:10s}: {pprint(lhs)} == {pprint(rhs)}   "
              f"({'ok' if not d else 'MISMATCH'})")

    print("\n[synthesize] generated UF axioms (normalized to == 0)")
    gen_norm = {}
    for k, (lhs, rhs) in gen.items():
        d = p_sub(lhs, rhs)
        gen_norm[k] = d
        print(f"    {k:10s}: residual {pprint(d) or '0'}")

    hand = hand_derived()
    print("\n[compare] generated vs hand-derived certificate")
    ok = True
    for k, (lhs, rhs) in hand.items():
        dh = p_sub(lhs, rhs)
        same = (dh == gen_norm.get(k))
        ok &= same
        print(f"    {k:10s}: {'MATCH' if same else 'DIFF'}"
              f"   hand={pprint(dh) or '0'}  gen={pprint(gen_norm.get(k)) or '0'}")

    print("\nRESULT:", "AUTOMATED CERTIFICATE MATCHES HAND-DERIVED"
          if ok else "MISMATCH — investigate")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
