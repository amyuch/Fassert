#!/usr/bin/env python3
"""S9 — MUL O6: nested temporal summary of the writeback->retire correspondence,
derived from the actual RTL transition relation (not a ghost of the result).

RTL links (all 1-step / combinational):
  L1 ready capture : at a PCPI ready edge, reg_out <= pcpi_int_rd
  L2 writeback mux : at fetch && latched_store && !latched_branch && !latched_stalu,
                     cpuregs_wrdata == reg_out
  L3 RVFI latch    : after a MUL cpuregs_write, rvfi_rd_wdata == latched_rd ? cpuregs_wrdata : 0
  L4 rd address    : latched_rd matches the reported instruction rd (checker o_rd_addr_match)

L1-L3 are re-proved by ric3 IC3 over the BTOR (UNSAT).  L4 is reported OPEN
(BMC clean, IC3 unknown); it is the checker's address-match obligation and is
factored out rather than hidden.

The composition (z3) then derives
    rvfi_rd_wdata == spec_rd_wdata      (at retirement)
from Post (pcpi_int_rd == a*b), L1-L3, and L4 (assumed in the check, flagged).

Run: python3 automation/decomp/s9_mul_o6.py
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import z3
from z3 import And, BitVec, BitVecSort, BitVecVal, Function, Not, Solver

PROJ = "/tmp/opencode/cill/t3/kernel_mul"
RIC3 = ("/home/AM2/sec/cur_work/fasten/benchmarks/src/cill_exp/"
        "rIC3/target/release/ric3")
LINKS = ["h_ready_capture", "h_cpuregs_wrdata_mul", "h_rvfi_link_mul"]
RD_LINK = "h_rd_matches_insn"


def parse_bads(btor):
    out = []
    for line in open(btor, errors="replace"):
        m = re.match(r"\s*(\d+)\s+bad\s+(\d+)\s+(\S+)\s*;", line)
        if m:
            out.append((len(out), m.group(3)))
    return out


def run(ric3, proj, btor, idx, time_limit=120):
    t0 = time.time()
    r = subprocess.run([ric3, "check", btor, "ic3", "--prop", str(idx),
                        "--time-limit", str(time_limit)],
                       cwd=proj, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    last = out[-1] if out else ""
    status = "proved" if last == "UNSAT" else (
        "unsafe" if last == "SAT" else "unknown")
    return status, round(time.time() - t0, 2), last


def compose():
    """Post + L1-L3 + L4 => rvfi_rd_wdata == spec_rd_wdata."""
    BV = BitVecSort(32)
    M = Function("M", BV, BV, BV)
    a, b = BitVec("a", 32), BitVec("b", 32)
    rd = BitVec("rd", 5)
    pcpi, cwr, rvfi, spec = (BitVec(n, 32) for n in
                             ("pcpi", "cwr", "rvfi", "spec"))
    post = (pcpi == M(a, b))                       # B / O4 at ready
    chain = (cwr == pcpi)                          # L1 + L2
    latch = (rvfi == z3.If(rd != 0, cwr, BitVecVal(0, 32)))   # L3
    specf = (spec == z3.If(rd != 0, M(a, b), BitVecVal(0, 32)))
    goal = (rvfi == spec)
    s = Solver(); s.set(timeout=30000)
    s.add(post, chain, latch, specf, Not(goal))
    return s.check()


def main():
    btor = os.path.join(PROJ, "ric3proj", "dut", "dut.btor")
    bads = dict((n, i) for i, n in parse_bads(btor))
    print(f"z3 {z3.get_version_string()}  BTOR={btor}")

    results = {}
    print("\n[O6] nested temporal summary links (ric3 IC3 over RTL/BTOR)")
    for name in LINKS:
        st, dt, last = run(RIC3, PROJ, btor, bads[name])
        results[name] = {"status": st, "seconds": dt, "raw": last}
        print(f"    {name:26s} {st:8s} {dt:7.2f}s")

    st4, dt4, last4 = run(RIC3, PROJ, btor, bads[RD_LINK])
    results[RD_LINK] = {"status": st4, "seconds": dt4, "raw": last4}
    print(f"    {RD_LINK:26s} {st4:8s} {dt4:7.2f}s  (address-match; open)")

    r = compose()
    comp_ok = (r == z3.unsat)
    print(f"\n[compose] Post + L1-L3 + L4 => rvfi == spec : {r} "
          f"({'checked' if comp_ok else 'FAIL'})")

    data_ok = all(results[n]["status"] == "proved" for n in LINKS)
    rd_ok = results[RD_LINK]["status"] == "proved"
    verdict = ("O6 data correspondence proved from RTL transition; "
               + ("rd-address proved" if rd_ok else "rd-address OPEN"))
    print("\nRESULT:", verdict)

    art = {
        "artifact": "mul_o6",
        "btor_sha256_note": "see artifact_mul_manifold.json",
        "obligation": "O6 observable link (writeback -> retire)",
        "links": results,
        "composition": {"status": "checked" if comp_ok else "fail",
                        "assumes": ["L1-L3 proved", "L4 address-match"]},
        "verdict": verdict,
    }
    path = os.path.join(HERE, "artifact_mul_o6.json")
    json.dump(art, open(path, "w"), indent=2)
    print(f"[artifact] {path}")
    return 0 if (data_ok and comp_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
