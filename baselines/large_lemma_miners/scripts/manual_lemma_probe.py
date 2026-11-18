#!/usr/bin/env python3
"""Manual lemma probe for the adapted fassert picorv32 case.

This is a thin wrapper around the same EBMC invocation the large-lemma-miners
baseline uses (src/evaluation.py): k-induction bound 1 with the formal top and
reset, and optionally a bounded BMC run.  It exists only so that the assistant
can act as the lemma generator without calling any external LLM.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("/tmp/llm_6h/cases/insn_add.sv")
OUT = Path("/tmp/llm_probe")


def insert_lemma(text: str, name: str, body: str, with_prop: bool) -> str:
    marker = "endproperty\n"
    idx = text.rfind(marker)
    if idx < 0:
        raise SystemExit("no endproperty found")
    idx += len(marker)
    lemma = (
        f"\n\tproperty {name};\n"
        f"\t\t@(posedge clock) disable iff (reset)\n"
        f"\t\t\t({body});\n"
        f"\tendproperty\n"
    )
    assertion = f"\tassert property ({name}{' and prop' if with_prop else ''});\n"
    return text[:idx] + lemma + assertion + text[idx:]


def run(cmd: list[str], timeout: float):
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        dt = time.perf_counter() - t0
        return p.returncode, p.stdout, p.stderr, dt
    except subprocess.TimeoutExpired as e:
        dt = time.perf_counter() - t0
        return 124, e.stdout or "", (e.stderr or "") + "\nTIMEOUT", dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="lem")
    ap.add_argument("--body", default=None)
    ap.add_argument("--body-file", default=None)
    ap.add_argument("--with-prop", action="store_true")
    ap.add_argument("--bmc", type=int, default=0, help="also run BMC to this bound")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    text = Path(args.base).read_text()
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text().strip()
    if body is None:
        ap.error("--body or --body-file is required")
    text = insert_lemma(text, args.name, body, args.with_prop)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"probe_{os.getpid()}_{args.name}.sv"
    f.write_text(text)

    common = ["ebmc", str(f), "--top", "testbench", "--reset", "testbench.reset"]
    if args.trace:
        common.append("--trace")

    kat = common + ["--k-induction", "--bound", "1"]
    rc, out, err, dt = run(kat, args.timeout)
    print(f"=== k-induction bound 1 ({'lemma and prop' if args.with_prop else 'lemma alone'}) {dt:.2f}s rc={rc}")
    print(out[-4000:])
    if err.strip():
        print("STDERR:", err[-2000:])

    if args.bmc:
        bmc = common + ["--bound", str(args.bmc)]
        rc2, out2, err2, dt2 = run(bmc, args.timeout)
        print(f"=== BMC bound {args.bmc} {dt2:.2f}s rc={rc2}")
        print(out2[-4000:])
        if err2.strip():
            print("STDERR:", err2[-2000:])

    if not args.keep:
        f.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
