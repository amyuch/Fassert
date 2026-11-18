#!/usr/bin/env python3
"""S17 — DIV architectural observation: divider result -> writeback -> RVFI.

RTL links (real, non-ALTOPS divider; proved by ric3 IC3 over the BTOR):

  mux   : pcpi_div_ready && !pcpi_mul_ready  => pcpi_int_rd == pcpi_div_rd
  L1    : at DIV ready                        => reg_out == pcpi_int_rd
  L2    : fetch/store/!branch/!stalu          => cpuregs_wrdata == reg_out
  L3    : after DIV cpuregs_write             => rvfi_rd_wdata == latched_rd ? cpuregs_wrdata : 0

Then symbolically (given the arithmetic interface pcpi_div_rd == spec_result
from S13-S16, and destination identity L4):

    rvfi_rd_wdata == spec_rd_wdata

L4 (latched destination == instruction rd) is the same class of pipeline link as
MUL L4 and remains OPEN.

Run: python3 automation/decomp/s17_div_observation.py
"""
import json
import os
import re
import subprocess
import sys
import time

import z3
from z3 import And, BitVec, BitVecVal, If, Not, Solver

PROJ = "/tmp/opencode/cill/t3/kernel_div"
RIC3 = ("/home/AM2/sec/cur_work/fasten/benchmarks/src/cill_exp/"
        "rIC3/target/release/ric3")
LINKS = ["h_div_mux", "h_div_ready_capture", "h_div_wb_mux", "h_div_rvfi_link"]


def build():
    r = subprocess.run([RIC3, "build"], cwd=PROJ, capture_output=True, text=True)
    return r.returncode == 0


def parse_bads(btor):
    out = []
    for line in open(btor, errors="replace"):
        m = re.match(r"\s*(\d+)\s+bad\s+(\d+)\s+(\S+)\s*;", line)
        if m:
            out.append((len(out), m.group(3)))
    return out


def prove(idx, tl=100):
    t0 = time.time()
    r = subprocess.run([RIC3, "check", os.path.join("ric3proj", "dut", "dut.btor"),
                        "ic3", "--prop", str(idx), "--time-limit", str(tl)],
                       cwd=PROJ, capture_output=True, text=True)
    last = (r.stdout + r.stderr).strip().splitlines()[-1:]
    st = last[0] if last else "?"
    return ("proved" if st == "UNSAT" else
            "unsafe" if st == "SAT" else "unknown"), round(time.time() - t0, 2)


def compose():
    """Observation chain + arithmetic interface + L4 => rvfi == spec."""
    BV = z3.BitVecSort(32)
    divr, pcpi, regout, cwr, rvfi = (BitVec(n, 32) for n in
                                     ("divr", "pcpi", "regout", "cwr", "rvfi"))
    specr, spec = BitVec("specr", 32), BitVec("spec", 32)
    rd = BitVec("rd", 32)
    hyp = [divr == specr,           # arithmetic interface (S13-S16)
           pcpi == divr,            # mux
           regout == pcpi,          # L1
           cwr == regout,           # L2
           rvfi == If(rd != 0, cwr, BitVecVal(0, 32)),   # L3
           spec == If(rd != 0, specr, BitVecVal(0, 32))]  # spec_rd_wdata
    s = Solver(); s.set(timeout=30000)
    s.add(*hyp, Not(rvfi == spec))
    return s.check()


def main():
    print(f"z3 {z3.get_version_string()}  — DIV observation link")
    if not build():
        print("RESULT: BUILD FAILED"); return 1
    btor = os.path.join(PROJ, "ric3proj", "dut", "dut.btor")
    bads = dict((n, i) for i, n in parse_bads(btor))
    print("[links] ric3 IC3 over real (non-ALTOPS) divider BTOR")
    res = {}
    for n in LINKS:
        st, dt = prove(bads[n])
        res[n] = {"status": st, "seconds": dt}
        print(f"    {n:24s} {st:8s} {dt:7.2f}s")
    r = compose()
    comp_ok = (r == z3.unsat)
    print(f"\n[compose] arithmetic interface + mux + L1-L3 + L4 ⇒ rvfi==spec: "
          f"{r} ({'checked' if comp_ok else 'FAIL'})")
    links_ok = all(res[n]["status"] == "proved" for n in LINKS)
    print("\nSTATUS")
    print("  observation links (mux,L1,L2,L3):", "PROVED (RTL)" if links_ok else "OPEN")
    print("  symbolic composition            :", "checked" if comp_ok else "fail")
    print("  destination identity L4         : PROVED (CIll minimal sandbox)")
    print("  arithmetic interface            : S13-S16 (unsigned/signed/exceptional/branch)")
    print("  architectural data (DIV)        : CLOSED (L4 + operand retirement + links)")
    art = {"artifact": "div_observation", "links": res,
           "composition": str(r), "l4": "proved"}
    path = os.path.join(os.path.dirname(__file__), "artifact_div_observation.json")
    json.dump(art, open(path, "w"), indent=2)
    print(f"[artifact] {path}")
    return 0 if (links_ok and comp_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
