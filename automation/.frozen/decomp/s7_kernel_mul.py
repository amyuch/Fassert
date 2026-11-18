#!/usr/bin/env python3
"""S7 — MUL kernel prototype: certify the reachable-manifold invariant (SPC O1/O2)
on the RTL/BTOR with ric3's SAT engines (not Yosys's inline SAT).

The artifact is a set of property checks:
  - the front-end (Yosys/Slang -> BTOR) is in the TCB;
  - for each manifold property, ric3 IC3 proves it as a safety property from
    reset, independently of the CIll helper-selection process;
  - the script records model hash, property names, engine, status, and time.

This is the L1 "certificate-carrying manifold": each O1/O2 fact is re-proved by
an independent SAT-based engine over the actual BTOR.

Run:
  python3 automation/decomp/s7_kernel_mul.py \
      --proj /tmp/opencode/cill/t3/kernel_mul \
      --ric3 /home/AM2/sec/cur_work/fasten/benchmarks/src/cill_exp/rIC3/target/release/ric3
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

MANIFOLD = ["h_carrysave", "h_counter", "h_shift_rs1", "h_shift_rs2"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(proj, ric3):
    r = subprocess.run([ric3, "build"], cwd=proj, capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def parse_bads(btor):
    """Return [(index, name)] in BTOR bad order (0-based index for --prop)."""
    bads = []
    for line in open(btor, errors="replace"):
        m = re.match(r"\s*(\d+)\s+bad\s+(\d+)\s+(\S+)\s*;", line)
        if m:
            bads.append((len(bads), m.group(3)))
    return bads


def prove(ric3, proj, btor, idx, name, time_limit):
    t0 = time.time()
    r = subprocess.run(
        [ric3, "check", btor, "ic3", "--prop", str(idx),
         "--time-limit", str(time_limit)],
        cwd=proj, capture_output=True, text=True)
    dt = time.time() - t0
    out = r.stdout + r.stderr
    proved = "IC3 proved the property" in out
    unsafe = ("unsafe" in out.lower()) and not proved
    return {
        "name": name, "index": idx, "engine": "ric3-ic3",
        "status": "proved" if proved else ("unsafe" if unsafe else "unknown"),
        "seconds": round(dt, 2), "returncode": r.returncode,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proj", default="/tmp/opencode/cill/t3/kernel_mul")
    ap.add_argument("--ric3",
                    default="/home/AM2/sec/cur_work/fasten/benchmarks/src/"
                            "cill_exp/rIC3/target/release/ric3")
    ap.add_argument("--time-limit", type=int, default=300)
    ap.add_argument("--rebuild", action="store_true", default=True)
    ap.add_argument("--no-rebuild", dest="rebuild", action="store_false")
    ap.add_argument("--artifact", default=None)
    args = ap.parse_args()

    proj = os.path.abspath(args.proj)
    print(f"[kernel] proj = {proj}")
    print(f"[kernel] ric3 = {args.ric3}")

    if args.rebuild:
        print("[kernel] O0: front-end rebuild (Yosys/Slang -> BTOR) [TCB]")
        ok, out = build(proj, args.ric3)
        if not ok:
            print(out[-2000:])
            print("RESULT: BUILD FAILED")
            return 1

    btor = os.path.join(proj, "ric3proj", "dut", "dut.btor")
    if not os.path.exists(btor):
        print("RESULT: no BTOR")
        return 1
    bhash = sha256(btor)
    bads = parse_bads(btor)
    print(f"[kernel] dut.btor sha256 = {bhash[:16]}…  properties = {len(bads)}")
    for i, n in bads:
        print(f"    bad[{i:2d}] = {n}")

    results = []
    print("\n[kernel] O1/O2: ric3 IC3 safety proof per manifold property")
    for idx, name in bads:
        if name not in MANIFOLD:
            continue
        res = prove(args.ric3, proj, btor, idx, name, args.time_limit)
        results.append(res)
        print(f"    {name:26s} idx={idx:2d}  {res['status']:8s} "
              f"{res['seconds']:7.2f}s")

    missing = set(MANIFOLD) - {r["name"] for r in results}
    proved = all(r["status"] == "proved" for r in results) and not missing
    verdict = "MANIFOLD CERTIFIED (ric3 IC3, RTL/BTOR)" if proved else "OPEN"

    print(f"\nTCB: Yosys/Slang front-end + ric3 IC3 (SAT). Provenance: BTOR hash.")
    print("RESULT:", verdict)

    art = {
        "artifact": "mul_manifold",
        "btor_sha256": bhash,
        "front_end": "yosys-slang (TCB)",
        "engine": "ric3-ic3 (SAT)",
        "properties": results,
        "missing": sorted(missing),
        "verdict": verdict,
    }
    path = args.artifact or os.path.join(os.path.dirname(__file__),
                                         "artifact_mul_manifold.json")
    with open(path, "w") as f:
        json.dump(art, f, indent=2)
    print(f"[artifact] {path}")
    return 0 if proved else 1


if __name__ == "__main__":
    sys.exit(main())
