#!/usr/bin/env python3
"""Generate a CEGAR-compatible Yosys script for a generated corpus case.

The corpus ``gen_btor.ys`` reads the behavioural RTL (``nerv.sv``, ``serv``
rtl sources, ``picorv32.sv``, ...) and flattens ``testbench``.  CEGAR instead
substitutes its refined ``wrapper_abstract_llm_new.v`` for the DUT, so the
model has to be rebuilt from the checker and testbench plus the case's flat
``wrapper.v``.  This script derives that Yosys script from ``gen_btor.ys``:

* every ``read_verilog`` line for a ``*_check.sv``, ``insn_*.v`` or ``tb.sv``
  file is kept;
* the behavioural DUT reads are replaced by ``read_verilog -sv wrapper.v``;
* the post-read pipeline (``prep`` ... ``write_btor``) is copied verbatim.

With ``--dut`` the script instead keeps the behavioural harness
``wrapper.sv`` and emits a ``read_verilog -sv wrapper.v`` placeholder for the
abstracted unflattened core.  ``src/cegar.py`` substitutes the refined core
for that placeholder on every iteration; the extra abstraction ports are left
unconnected by the harness and become free inputs via ``setundef -anyseq``.

Usage:
    python3 src/make_cegar_script.py <case_dir> [-o out.ys] \
        [--clock clock --reset reset]

Without ``-o`` the script is written to stdout.  The generated script writes
``<case>/wrapper_abstract_llm_new.btor2``; ``src/cegar.py`` rewrites that path
for every refinement iteration.

The generated nerv/serv/picorv32 ``gen_btor.ys`` files include the same
one-cycle reset writeback that the original rIC3 build performs.  This tool
copies that ``sim -clock ... -reset ... -w ...`` line when it is present, so
the refined model starts from the same post-reset state as the corpus
baseline.  For an older script without the writeback, passing
``--clock clock --reset reset`` inserts it explicitly.

The legacy ``piccolo``/``flute`` cases already ship a ``gen_btor.ys`` that
reads ``wrapper.v`` directly (including their ``sim`` reset initialisation).
For those use the shipped script, prefixed with ``async2sync`` before ``sim``
on Yosys >= 0.60; this tool refuses to regenerate them.
"""

import argparse
import os
import re
import sys


def collect_reads(lines, case):
    """Return the checker / instruction-model / testbench read lines."""
    reads = []
    for line in lines:
        match = re.match(r"\s*read_verilog\s+(?:-sv\s+)?(?:-I\S*\s+)*(\S+)", line)
        if not match:
            continue
        name = os.path.basename(match.group(1))
        if name.endswith("_check.sv") or name == "tb.sv" or re.match(r"insn_.*\.v$", name):
            reads.append(name)
    return reads


def build_script(case, clock=None, reset=None, top="testbench", dut=False):
    source = os.path.join(case, "gen_btor.ys")
    if not os.path.exists(source):
        raise SystemExit("missing {}".format(source))

    with open(source) as handle:
        lines = handle.read().splitlines()

    if any("wrapper.v" in line and "read_verilog" in line for line in lines):
        raise SystemExit(
            "{} already reads wrapper.v; use that script directly "
            "(add `async2sync` before `sim` on Yosys >= 0.60)".format(source)
        )

    names = collect_reads(lines, case)
    if "tb.sv" not in names:
        raise SystemExit("{} does not read tb.sv".format(source))

    if bool(clock) != bool(reset):
        raise SystemExit("--clock and --reset must be given together")

    checker = [name for name in names if name != "tb.sv"]
    script = [
        "read_verilog -sv -I{0} {1}".format(case, os.path.join(case, name))
        for name in checker
    ]
    if dut:
        # Unflattened flow (picorv32): keep the behavioural harness
        # (``wrapper.sv`` instantiates ``picorv32``) and substitute a
        # placeholder for the *abstracted* core.  ``src/cegar.py`` replaces
        # the ``wrapper.v`` basename with the refined DUT on every iteration.
        # Ports added by NeuroAbs are left unconnected by the harness, so
        # Yosys reports them undriven and ``setundef -anyseq`` turns them into
        # free inputs.
        script.append("read_verilog -sv -I{0} {1}".format(
            case, os.path.join(case, "wrapper.sv")))
        script.append("read_verilog -sv wrapper.v")
    else:
        script.append("read_verilog -sv {0}".format(os.path.join(case, "wrapper.v")))
    script.append("read_verilog -sv -I{0} {1}".format(case, os.path.join(case, "tb.sv")))
    script += [
        "prep -flatten -nordff -top {0}".format(top),
        "chformal -early",
        "memory",
        "async2sync",
        "chformal -assume -early",
        "chformal -live -fair -cover -remove",
        "opt_clean",
        "setundef -anyseq",
        "opt -keepdc -fast",
        "check",
        "hierarchy -simcheck",
        "dffunmap",
    ]
    if clock and reset:
        # Explicit override for an older gen_btor.ys that predates the
        # reset-initialising sim step.
        script += [
            "async2sync",
            "sim -clock {0} -reset {1} -rstlen 1 -n 1 -w {2}".format(clock, reset, top),
        ]
    else:
        # Reuse the corpus writeback so the refined model starts from the same
        # post-reset state as problem.btor2.
        sim = next((line.strip() for line in lines
                    if re.match(r"\s*sim\s", line) and "-w" in line), None)
        if sim:
            script += ["async2sync", sim]
    output_dir = os.path.join(case, "dut") if dut else case
    script.append("write_btor {0}".format(os.path.join(output_dir, "wrapper_abstract_llm_new.btor2")))
    return "\n".join(script) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("case", help="case directory (contains gen_btor.ys and wrapper.v)")
    parser.add_argument("-o", "--output", help="output .ys file (default: stdout)")
    parser.add_argument("--clock", help="top-level clock port (with --reset)")
    parser.add_argument("--reset", help="top-level active-high reset port (with --clock)")
    parser.add_argument("--top", default="testbench", help="top module (default: testbench)")
    parser.add_argument(
        "--dut",
        action="store_true",
        help="unflattened DUT flow: read wrapper.sv + an abstracted core "
             "placeholder (wrapper.v) instead of the flat wrapper.v",
    )
    args = parser.parse_args(argv)

    case = os.path.abspath(args.case)
    script = build_script(case, args.clock, args.reset, args.top, dut=args.dut)
    if args.output:
        with open(args.output, "w") as handle:
            handle.write(script)
        print(args.output)
    else:
        sys.stdout.write(script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
