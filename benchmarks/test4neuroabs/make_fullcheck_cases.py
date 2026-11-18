#!/usr/bin/env python3
"""Materialize the full-property variant of test4neuroabs.

The source tree uses the reduced CIll checkers.  This script copies each case
into ``fullcheck/<family>/<case>`` and swaps in the full-property checker where
one exists:

* ``picorv32/*``: ``rvfi_insn_check.sv`` ->
  ``benchmarks/riscv-formal/rvfi_insn_check_origin.sv`` (20 asserts instead of
  2, or 1 for the memory-only variant);
* ``nerv/reg`` and ``serv/reg``: ``rvfi_reg_check.sv`` -> the upstream
  ``rvfi_reg_check.sv`` (restores the ``assume`` and
  ``rvfi_order < insn_order`` behaviour);
* ``nerv/pc_bwd`` and ``serv/pc_bwd``: ``rvfi_pc_bwd_check.sv`` -> the upstream
  ``rvfi_pc_bwd_check.sv``.

All other checkers are copied unchanged.  The full checkers are prefixed with
``default_nettype none`` / ``include "defines.sv"`` so they work with the
materialized read order.

The script regenerates ``problem.btor2`` with the case's existing
``gen_btor.ys`` (which includes the reset-initialising ``sim`` writeback).  It
does not generate ``problem.aig`` by default; pass ``--aiger`` for that, or run
``./run.sh`` in a generated case.

Usage:
    python3 make_fullcheck_cases.py [--check] [--aiger] [--jobs N]
"""

import argparse
import concurrent.futures
import csv
import os
import re
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent
OUT = HERE / "fullcheck"
FULL_INSN = BENCH / "riscv-formal" / "rvfi_insn_check_origin.sv"
UPSTREAM_CHECKS = REPO / "baselines" / "cill" / "deps" / "riscv-formal" / "checks"
UP_REG = UPSTREAM_CHECKS / "rvfi_reg_check.sv"
UP_PC_BWD = UPSTREAM_CHECKS / "rvfi_pc_bwd_check.sv"

# Files that are part of a self-contained case.  Everything else in the source
# directory is a generated CEGAR/NeuroAbs artefact and is deliberately skipped.
EXPLICIT = {
    "defines.sv", "rvfi_macros.vh", "gen_btor.ys", "gen_aiger.ys",
    "run.sh", "description.txt", ".gitignore", "preprocess.sh",
    "design_pp.v", "wrapper.v", "wrapper_constant.v", "tb.sv", "wrapper.sv",
    "picorv32.sv", "nerv.sv",
}
BAD_FRAGMENTS = (
    "abstract", "noassert", "input", "problem", "cegar", "old",
)


def is_source_file(path):
    name = path.name
    if name in EXPLICIT:
        return True
    if name.startswith("."):
        return False
    if name.endswith((".sv", ".v", ".vh")):
        return not any(frag in name for frag in BAD_FRAGMENTS)
    return False


def checker_override(family, case):
    if family == "picorv32":
        return "rvfi_insn_check.sv", FULL_INSN, "full-insn"
    if case == "reg":
        return "rvfi_reg_check.sv", UP_REG, "full-reg"
    if case == "pc_bwd":
        return "rvfi_pc_bwd_check.sv", UP_PC_BWD, "full-pc_bwd"
    return None


def adapted_checker(path):
    text = path.read_text()
    if '`include "defines.sv"' not in text:
        text = '`default_nettype none\n`include "defines.sv"\n\n' + text
    return text


def copy_case(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        if path.is_dir():
            if path.name == "rtl":
                shutil.copytree(path, dst / "rtl", dirs_exist_ok=True)
            continue
        if is_source_file(path):
            shutil.copy2(path, dst / path.name)
    if (dst / "run.sh").exists():
        (dst / "run.sh").chmod(0o755)


def build_case(family, case, aiger):
    src = HERE / family / case
    dst = OUT / family / case
    copy_case(src, dst)

    override = checker_override(family, case)
    checker_label = "as-source"
    if override:
        filename, source, checker_label = override
        if not source.exists():
            raise SystemExit("missing checker: %s" % source)
        text = adapted_checker(source)
        (dst / filename).write_text(text)

    if (dst / "gen_btor.ys").exists() and "design_pp.v" in (dst / "gen_btor.ys").read_text():
        if not (dst / "design_pp.v").exists() and (dst / "preprocess.sh").exists():
            subprocess.run(["./preprocess.sh"], cwd=dst, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True)

    def run(script):
        proc = subprocess.run(
            ["yosys", "-q", "-s", script],
            cwd=dst, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.returncode != 0:
            tail = "\n".join(proc.stdout.splitlines()[-8:])
            raise RuntimeError("%s/%s: %s failed\n%s" % (family, case, script, tail))

    run("gen_btor.ys")
    if aiger:
        run("gen_aiger.ys")

    lines = (dst / "problem.btor2").read_text().splitlines()
    bad = sum(1 for l in lines if re.match(r"^\d+ bad ", l))
    constraint = sum(1 for l in lines if re.match(r"^\d+ constraint ", l))
    init = sum(1 for l in lines if re.match(r"^\d+ init ", l))
    return {
        "family": family,
        "case": case,
        "checker": checker_label,
        "bad": bad,
        "constraint": constraint,
        "init": init,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report the plan, do not write or build")
    ap.add_argument("--aiger", action="store_true",
                    help="also run gen_aiger.ys (legacy zero-init AIGER)")
    ap.add_argument("--jobs", type=int, default=8,
                    help="parallel Yosys jobs (default: 8)")
    args = ap.parse_args()

    tasks = []
    for family in ("nerv", "serv", "picorv32"):
        for src in sorted((HERE / family).iterdir()):
            if src.is_dir() and (src / "gen_btor.ys").exists():
                override = checker_override(family, src.name)
                tasks.append((family, src.name,
                              override[2] if override else "as-source"))

    if args.check:
        for family, case, checker in tasks:
            print("%-10s %-24s %s" % (family, case, checker))
        print("checked: %d cases" % len(tasks))
        return

    rows = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(build_case, family, case, args.aiger): (family, case)
            for family, case, _ in tasks
        }
        for fut in concurrent.futures.as_completed(futures):
            family, case = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:  # keep going; report at the end
                failures.append((family, case, str(exc)))
                print("FAIL %s/%s" % (family, case))
                continue
            rows.append(row)
            print("OK   %-10s %-24s %-12s bad=%-3d constraint=%-2d init=%d" % (
                row["family"], row["case"], row["checker"],
                row["bad"], row["constraint"], row["init"]))

    rows.sort(key=lambda r: (r["family"], r["case"]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "manifest.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "family", "case", "checker", "bad", "constraint", "init",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print("wrote %d cases to %s" % (len(rows), OUT))
    if failures:
        print("%d failures:" % len(failures))
        for family, case, msg in failures:
            print("  %s/%s: %s" % (family, case, msg.splitlines()[0]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
