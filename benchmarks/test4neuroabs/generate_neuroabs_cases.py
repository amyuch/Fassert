#!/usr/bin/env python3
"""Materialize the active rvfi cases (nerv / serv / picorv32) in NeuroAbs layout.

For every case in ../<family>/<case>/ that has a ric3.toml this script creates
test4neuroabs/<family>/<case>/ containing:

  * the exact case sources referenced by ric3.toml (files + include_files,
    relative paths preserved),
  * description.txt  -- benchmark / property description,
  * gen_btor.ys     -- Yosys -> problem.btor2  (reset-initialised; bad + constraint preserved),
  * gen_aiger.ys    -- Yosys -> problem.aig    (bad + constraint preserved),
  * run.sh          -- runs both generators,
  * .gitignore      -- generated artifacts.

The legacy prototypes (which hard-coded insn_add_ch0.sv / iter/ paths) live in
test4neuroabs/_legacy/ and are not touched.

Usage:  python3 generate_neuroabs_cases.py [--check]
        --check  only report what would be written
"""

import os
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)

FAMILIES = ("nerv", "serv", "picorv32")

NERV_DESC = {
    "bus_dmem": "data-memory bus handshake / protocol",
    "bus_dmem_fault": "data-memory bus fault reporting",
    "bus_imem": "instruction-memory bus handshake / protocol",
    "bus_imem_fault": "instruction-memory bus fault reporting",
    "causal": "causality of register reads",
    "csr_ill_f11": "illegal access to CSR 0xf11",
    "csr_ill_fff": "illegal access to CSR 0xfff",
    "csrc_const_custom_ro": "read of the read-only custom CSR is constant",
    "csrc_inc_mhpmcounter5": "mhpmcounter5 increments on commit",
    "csrc_upcnt_mcycle": "mcycle counts up",
    "csrc_upcnt_minstret": "minstret counts up",
    "csrw_custom": "write to the custom CSR",
    "csrw_custom_ro": "write to the read-only custom CSR is ignored",
    "csrw_mcycle": "write to mcycle",
    "csrw_mhpmcounter5": "write to mhpmcounter5",
    "csrw_mhpmevent3": "write to mhpmevent3",
    "csrw_mhpmevent5": "write to mhpmevent5",
    "csrw_mhpmevent9": "write to mhpmevent9",
    "csrw_minstret": "write to minstret",
    "csrw_mstatus": "write to mstatus",
    "ill": "illegal-instruction trap",
    "pc_bwd": "backward program-counter behavior",
    "pc_fwd": "forward program-counter behavior",
    "reg": "register-file write / commit behavior",
    "unique": "unique instruction order",
}

SERV_DESC = {
    "causal": "causality of register reads",
    "pc_bwd": "backward program-counter behavior",
    "pc_fwd": "forward program-counter behavior",
    "reg": "register-file write / commit behavior",
}


def parse_toml(path):
    txt = open(path).read()

    def arr(key):
        m = re.search(r"^%s\s*=\s*\[(.*?)\]" % key, txt, re.S | re.M)
        return re.findall(r'"([^"]+)"', m.group(1)) if m else []

    def scalar(key):
        m = re.search(r'^%s\s*=\s*"([^"]+)"' % key, txt, re.M)
        return m.group(1) if m else None

    return {
        "files": arr("files"),
        "include_files": arr("include_files"),
        "top": scalar("top"),
        "reset": scalar("reset"),
        # rIC3's ric3.toml only names the reset; the clock is conventionally
        # `clock` in every generated testbench port list.
        "clock": scalar("clock") or "clock",
    }


def read_verilog_lines(files):
    return "\n".join("read_verilog -sv -I. %s" % f for f in files)


BTOR_TAIL = """\
prep -flatten -nordff -top {top}
chformal -early
memory
async2sync
chformal -assume -early
chformal -live -fair -cover -remove
opt_clean
setundef -anyseq
opt -keepdc -fast
check
hierarchy -simcheck
dffunmap
# Start from the post-reset state.  ric3.toml declares `reset`; without this
# writeback the model starts from an arbitrary, unreachable state.
async2sync
sim -clock {clock} -reset {reset} -rstlen 1 -n 1 -w {top}
write_btor problem.btor2
"""

AIGER_TAIL = """\
prep -flatten -nordff -top {top}
chformal -early
memory
async2sync
chformal -lower
chformal -assume -early
chformal -live -fair -cover -remove
opt_clean
setundef -anyseq
opt -keepdc -fast
check
hierarchy -simcheck
techmap
dffunmap
opt_clean
setundef -undriven -expose
abc -fast -g AND
write_aiger -zinit -vmap map.txt problem.aig
"""

RUN_SH = """\
#!/bin/sh
# NeuroAbs-format artifact generation (Yosys -> BTOR2 + AIGER).
set -eu
cd "$(dirname "$0")"
YOSYS="${YOSYS:-yosys}"
"$YOSYS" -q -s gen_btor.ys
"$YOSYS" -q -s gen_aiger.ys
awk '/^[0-9]+ bad /{b++} /^[0-9]+ constraint /{c++} END{printf "problem.btor2: %d bad(s), %d constraint(s)\\n", b, c}' problem.btor2
echo "problem.aig:   $(head -1 problem.aig)"
"""

RUN_SH_PP = """\
#!/bin/sh
# NeuroAbs-format artifact generation (preprocess -> Yosys -> BTOR2 + AIGER).
set -eu
cd "$(dirname "$0")"
./preprocess.sh
YOSYS="${YOSYS:-yosys}"
"$YOSYS" -q -s gen_btor.ys
"$YOSYS" -q -s gen_aiger.ys
awk '/^[0-9]+ bad /{b++} /^[0-9]+ constraint /{c++} END{printf "problem.btor2: %d bad(s), %d constraint(s)\\n", b, c}' problem.btor2
echo "problem.aig:   $(head -1 problem.aig)"
"""

PREPROCESS_SH = """\
#!/bin/sh
# The yosys built-in Verilog frontend cannot preprocess the `quoted`-style
# macro nesting used by this checker, so preprocess with Verilator first.
# (The rIC3 build covers the same case with its yosys-slang frontend.)
set -eu
cd "$(dirname "$0")"
VERILATOR="${{VERILATOR:-verilator}}"
"$VERILATOR" -E -DYOSYS -I. {files} > design_pp.v
"""

GITIGNORE = "problem.btor2\nproblem.aig\nmap.txt\n"
GITIGNORE_PP = "problem.btor2\nproblem.aig\nmap.txt\ndesign_pp.v\n"


def picorv32_description(case, files):
    """Derive the instruction name / decode guard from the riscv-formal spec."""
    insn = case[len("insn_"):].upper()
    spec = os.path.join(BENCH, "picorv32", case, case + ".v")
    guard = ""
    if os.path.exists(spec):
        for line in open(spec):
            if "assign spec_valid" in line:
                guard = line.split("=", 1)[1].strip().rstrip(";").strip()
                break
    lines = [
        "Benchmark: picorv32 / %s." % case,
        "Property focus: riscv-formal rvfi_insn_check for the %s instruction." % insn,
        "Instruction source: the RVFI instruction word (rvfi_insn; in the "
        "picorv32 wrapper this comes from mem_rdata).",
    ]
    if guard:
        lines.append("Decode guard: %s" % guard)
    lines.append(
        "Harness: wrapper.sv + tb.sv (top = testbench), single RVFI channel, "
        "unbounded check."
    )
    return "\n".join(lines) + "\n"


def checker_name(case_dir):
    d = os.path.join(case_dir, "defines.sv")
    if not os.path.exists(d):
        return "rvfi_insn_check"
    m = re.search(r"`define\s+RISCV_FORMAL_CHECKER\s+(\S+)", open(d).read())
    return m.group(1) if m else "rvfi_insn_check"


def description(family, case, case_dir):
    if family == "picorv32":
        return picorv32_description(case, None)
    table = NERV_DESC if family == "nerv" else SERV_DESC
    focus = table.get(case, case.replace("_", " "))
    checker = checker_name(case_dir)
    return (
        "Benchmark: %s / %s.\n"
        "Property focus: %s.\n"
        "Checker: riscv-formal %s.\n"
        "Harness: wrapper.sv + tb.sv (top = testbench), single RVFI channel, "
        "unbounded check.\n" % (family, case, focus, checker)
    )


def materialize(family, case, check_only):
    src = os.path.join(BENCH, family, case)
    dst = os.path.join(HERE, family, case)
    cfg = parse_toml(os.path.join(src, "ric3.toml"))
    if not cfg["files"] or not cfg["top"] or not cfg["reset"]:
        print("SKIP %s/%s: ric3.toml has no files/top/reset" % (family, case))
        return False

    if check_only:
        print("WOULD  %s/%s  files=%d include=%d top=%s"
              % (family, case, len(cfg["files"]), len(cfg["include_files"]), cfg["top"]))
        return True

    os.makedirs(dst, exist_ok=True)

    # sources
    for rel in cfg["files"] + cfg["include_files"]:
        s = os.path.join(src, rel)
        if not os.path.exists(s):
            print("MISSING %s/%s: %s" % (family, case, rel))
            return False
        d = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d) or dst, exist_ok=True)
        shutil.copy2(s, d)

    preprocess = needs_preprocess(cfg["files"], src)

    header = (
        "# Generated by generate_neuroabs_cases.py from "
        "../../%s/%s/ric3.toml.\n"
        "# Self-contained: no iter/ or insn_*_ch0.sv dependency.\n"
        % (family, case)
    )
    if preprocess:
        header += (
            "# This case is preprocessed by preprocess.sh (verilator -E) because\n"
            "# the yosys built-in frontend cannot expand its `quoted` macros.\n"
        )
        read = "read_verilog -sv design_pp.v"
    else:
        read = read_verilog_lines(cfg["files"])

    with open(os.path.join(dst, "gen_btor.ys"), "w") as f:
        f.write(header + read + "\n" + BTOR_TAIL.format(**cfg))
    with open(os.path.join(dst, "gen_aiger.ys"), "w") as f:
        f.write(header + read + "\n" + AIGER_TAIL.format(**cfg))
    with open(os.path.join(dst, "description.txt"), "w") as f:
        f.write(description(family, case, src))
    with open(os.path.join(dst, "run.sh"), "w") as f:
        f.write(RUN_SH_PP if preprocess else RUN_SH)
    os.chmod(os.path.join(dst, "run.sh"), 0o755)
    with open(os.path.join(dst, ".gitignore"), "w") as f:
        f.write(GITIGNORE_PP if preprocess else GITIGNORE)
    if preprocess:
        files = " ".join(shlex.quote(f) for f in cfg["files"])
        with open(os.path.join(dst, "preprocess.sh"), "w") as f:
            f.write(PREPROCESS_SH.format(files=files))
        os.chmod(os.path.join(dst, "preprocess.sh"), 0o755)
    return True


def needs_preprocess(files, srcdir):
    """True when the yosys built-in frontend cannot parse the sources."""
    reads = "; ".join("read_verilog -sv -I. %s" % shlex.quote(f) for f in files)
    p = subprocess.run(["yosys", "-q", "-p", reads], cwd=srcdir,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p.returncode != 0


def main():
    check_only = "--check" in sys.argv
    total = ok = 0
    for family in FAMILIES:
        root = os.path.join(BENCH, family)
        if not os.path.isdir(root):
            continue
        for case in sorted(os.listdir(root)):
            p = os.path.join(root, case)
            if not os.path.isdir(p) or not os.path.exists(os.path.join(p, "ric3.toml")):
                continue
            total += 1
            ok += bool(materialize(family, case, check_only))
    print("%s: %d/%d cases" % ("checked" if check_only else "materialized", ok, total))


if __name__ == "__main__":
    main()
