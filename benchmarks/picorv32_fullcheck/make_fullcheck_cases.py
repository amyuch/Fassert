#!/usr/bin/env python3
"""Materialize the full-property picorv32 benchmark family.

``picorv32_fullcheck/`` mirrors every case listed in
``../picorv32/manifest.csv`` (the 43 active cases and the 30 preserved cases).
Each case keeps the original RTL, harness, instruction spec, defines,
``ric3.toml`` and ``run.sh``; the only difference is that
``rvfi_insn_check.sv`` is replaced by the full RVFI checker
``../riscv-formal/rvfi_insn_check_origin.sv``.  The original family uses a
2-assert checker for instruction cases and a 1-assert memory-only checker for
load/store cases.

Usage:
    python3 make_fullcheck_cases.py [--check]

``--check`` only reports the files that would be written.
"""

import argparse
import csv
import re
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent
MANIFEST = BENCH / "picorv32" / "manifest.csv"
CHECKER = BENCH / "riscv-formal" / "rvfi_insn_check_origin.sv"


def parse_list(text, key):
    m = re.search(r"^%s\s*=\s*\[(.*?)\]" % key, text, re.S | re.M)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def build_file_list(src):
    toml = (src / "ric3.toml").read_text()
    files = parse_list(toml, "files") + parse_list(toml, "include_files")
    # The build recipe and per-case metadata are not listed in ric3.toml.
    files += ["ric3.toml", "run.sh", ".gitignore"]
    # Keep a case description if the source family ever adds one.
    files += ["description.txt"]
    return list(dict.fromkeys(files))


def materialize(case, src, check):
    dst = HERE / case
    files = build_file_list(src)
    for rel in files:
        s = src / rel
        if not s.exists():
            continue
        d = dst / rel
        if check:
            print("WOULD  %-24s %s" % (case, rel))
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    if check:
        print("WOULD  %-24s rvfi_insn_check.sv <- %s" % (case, CHECKER.name))
        return
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKER, dst / "rvfi_insn_check.sv")
    (dst / "run.sh").chmod(0o755)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would be written, do not modify the tree")
    args = ap.parse_args()

    if not CHECKER.exists():
        raise SystemExit("missing full checker: %s" % CHECKER)

    rows = list(csv.DictReader(open(MANIFEST)))
    for row in rows:
        case = row["case"]
        src = REPO / row["location"]
        if not (src / "ric3.toml").exists():
            raise SystemExit("missing source case: %s" % src)
        materialize(case, src, args.check)

    if args.check:
        print("checked: %d cases" % len(rows))
    else:
        print("wrote %d cases to %s" % (len(rows), HERE))


if __name__ == "__main__":
    main()
