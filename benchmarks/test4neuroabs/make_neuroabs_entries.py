#!/usr/bin/env python3
"""Generate the NeuroAbs entry points for the test4neuroabs corpus.

``baselines/neuroabs/src/main.py`` wants a single self-contained Verilog file
with a matching ``*_constant.v`` file next to it.  The corpus stores the DUT as
a small ``wrapper.sv`` that instantiates the CPU and leaves the environment
(instruction/data bus, interrupts, ...) as free ``rvformal_rand_reg`` signals.
This script turns that into:

  wrapper.v           flattened ``rvfi_wrapper``, free environment signals
                      exposed as top-level inputs (renamed to ``i_<name>``).
  wrapper_constant.v  the same netlist with the scenario environment tied to
                      constants, so the core runs a fixed instruction stream.

The constant variant is produced in one of two ways:

* picorv32: the free memory bus is *not* tied.  Instead the three signals that
  carry the decoded instruction inside the core are replaced at the source
  level (this mirrors the legacy ``picorv32_input_constant.v``).  The
  instruction word is built from the case's ``spec_valid`` guard: fields the
  guard constrains are concrete, register/immediate fields stay ``x``.
* serv / nerv: the free environment inputs are tied in the flattened netlist.
  The scenario instruction is placed on the instruction bus.

Usage:
    ./make_neuroabs_entries.py                # all cases, all families
    ./make_neuroabs_entries.py nerv serv      # selected families
    ./make_neuroabs_entries.py picorv32/insn_add nerv/bus_dmem
    ./make_neuroabs_entries.py --list

The generated files are large; regenerate them rather than editing by hand.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

FAMILIES = ("picorv32", "nerv", "serv")

# Free environment inputs tied by the constant variant for nerv.  ``imem_data``
# is replaced per case by the scenario instruction.
NERV_BASE_TIES = {
    "stall": "1'b0",
    "dmem_rdata": "32'b0",
    "irq": "32'b0",
    "imem_fault": "1'b0",
    "dmem_fault": "1'b0",
}

# RISC-V instruction helpers -------------------------------------------------
ADD = 0x00000033          # add x0, x0, x0
LW_X1_0_X0 = 0x00002083   # lw x1, 0(x0)

CSR_FUNCT3 = {"csrrw": 1, "csrrs": 2, "csrrc": 3,
              "csrrwi": 5, "csrrsi": 6, "csrrci": 7}


def csr_insn(csr, op="csrrw", rd=0, rs1=0):
    """Encode a Zicsr instruction (RV32)."""
    return ((csr & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | \
           (CSR_FUNCT3[op] << 12) | ((rd & 0x1F) << 7) | 0x73


# nerv CSR addresses (see nerv.sv)
NERV_CSRS = {
    "csrw_mstatus": 0x300,
    "csrw_mcycle": 0xB00,
    "csrw_minstret": 0xB02,
    "csrw_mhpmcounter5": 0xB05,
    "csrw_mhpmevent3": 0x323,
    "csrw_mhpmevent5": 0x325,
    "csrw_mhpmevent9": 0x329,
    "csrw_custom": 0xBC0,
    "csrw_custom_ro": 0xFC0,
    "csrc_const_custom_ro": 0xFC0,
    "csrc_inc_mhpmcounter5": 0xB05,
    "csrc_upcnt_mcycle": 0xB00,
    "csrc_upcnt_minstret": 0xB02,
}

NERV_ILL_CSRS = {
    "csr_ill_f11": 0xF11,
    "csr_ill_fff": 0xFFF,
}


def nerv_scenario_insn(case):
    """Instruction placed on nerv's instruction bus for a case."""
    if case in NERV_ILL_CSRS:
        return csr_insn(NERV_ILL_CSRS[case], "csrrw")
    if case in NERV_CSRS:
        addr = NERV_CSRS[case]
        if case.startswith("csrw_"):
            return csr_insn(addr, "csrrw")
        return csr_insn(addr, "csrrs", rd=1)
    if case.startswith("bus_dmem"):
        return LW_X1_0_X0
    if case == "ill":
        return 0
    # reg, causal, unique, pc_bwd, pc_fwd, bus_imem, bus_imem_fault
    return ADD


def nerv_ties(case, semantic_names):
    """Constant-variant ties for one nerv case."""
    ties = dict(NERV_BASE_TIES)
    ties["imem_data"] = "32'h%08x" % nerv_scenario_insn(case)
    # The bus cases expose the deliberately unconstrained next-access data.
    if case.startswith("bus_"):
        ties["next_dmem_rdata"] = "32'b0"
        ties["next_dmem_fault"] = "1'b0"
    # Fault cases must actually take the fault path.
    if case.endswith("_fault"):
        if "imem" in case:
            ties["imem_fault"] = "1'b1"
        if "dmem" in case:
            ties["dmem_fault"] = "1'b1"
            if "next_dmem_fault" in ties:
                ties["next_dmem_fault"] = "1'b1"
    # Only tie inputs that really exist in this case.
    return {k: v for k, v in ties.items() if k in semantic_names}


# picorv32 masked instruction literal ---------------------------------------
def picorv32_word(case_dir, case):
    """Return a 32-bit Verilog literal for the case's target instruction.

    The ``insn_<case>.v`` checker derives ``spec_valid`` from the instruction
    fields.  We mirror that guard: constrained fields get concrete values, all
    other bits stay ``x`` so the scenario does not over-constrain registers or
    immediates.  Compressed instructions are duplicated into both 16-bit
    halves, keeping the core executing the target.
    """
    src = open(os.path.join(case_dir, case + ".v")).read()
    ranges = {}
    for m in re.finditer(
            r"wire\s*\[[^\]]*\]\s*insn_(\w+)\s*=\s*rvfi_insn\[\s*(\d+)\s*:\s*(\d+)\s*\];",
            src):
        ranges[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    guard = re.search(r"assign spec_valid = ([^;]+);", src).group(1)

    bits = [None] * 32

    def set_field(name, value):
        if name not in ranges:
            return False
        hi, lo = ranges[name]
        for i in range(lo, hi + 1):
            bits[i] = (value >> (i - lo)) & 1
        return True

    # Equality constraints: funct7/funct6/funct4/funct3/funct2/opcode, and
    # compressed rs1/rd checks (== 5'd 2).
    for m in re.finditer(r"insn_(\w+)\s*(==|!=)\s*(\d+)'([bdh])\s*([0-9a-fA-Fx]+)",
                         guard):
        name, op, _width, base, value = m.groups()
        if op == "!=":
            # Any value other than the excluded one; 1 is never excluded here.
            set_field(name, 1)
        else:
            set_field(name, int(value.replace("x", "0"),
                                {"b": 2, "d": 10, "h": 16}[base]))

    # Shift amount high bit (slli/srli/srai).
    for m in re.finditer(r"insn_(\w+)\[(\d+)\]", guard):
        name, idx = m.group(1), int(m.group(2))
        if name in ranges:
            hi, lo = ranges[name]
            if lo <= idx <= hi:
                bits[idx] = 0

    # Bare fields are nonzero requirements.
    for name in ("imm", "rd", "rs2", "rs1_rd"):
        if re.search(r"(?<![!\w])insn_%s(?![\[\w]|\s*(?:==|!=))" % name, guard):
            if not set_field(name, 1):
                # Immediate is a concatenation; bit 12 exists in all three
                # compressed immediate formats that use this check.
                bits[12] = 1

    # !insn_rs2 is a zero requirement.
    if re.search(r"!\s*insn_rs2(?![\[\w])", guard):
        set_field("rs2", 0)

    compressed = bool(re.search(r"insn_opcode\s*==\s*2'", guard))
    if compressed:
        for i in range(16, 32):
            bits[i] = 0

    low = "".join("x" if bits[i] is None else str(bits[i])
                  for i in range(15, -1, -1))
    if compressed:
        return low + low
    return "".join("x" if bits[i] is None else str(bits[i])
                   for i in range(31, -1, -1))


# Yosys helpers --------------------------------------------------------------
def run_yosys(case_dir, sources, top, out, quiet=True):
    fd, script = tempfile.mkstemp(suffix=".ys", prefix=".entry.", dir=case_dir)
    try:
        with os.fdopen(fd, "w") as f:
            for source in sources:
                f.write("read_verilog -sv -I. %s\n" % source)
            f.write("hierarchy -check -top %s\n" % top)
            f.write("proc\nflatten\ndelete t:$anyseq\n")
            f.write("setundef -undriven -expose\n")
            f.write("write_verilog -noattr %s\n" % out)
        cmd = ["yosys"] + (["-q"] if quiet else []) + ["-s", script]
        r = subprocess.run(cmd, cwd=case_dir, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        if r.returncode:
            sys.stderr.write(r.stdout[-4000:])
            raise RuntimeError("yosys failed in %s" % case_dir)
    finally:
        os.unlink(script)


def split_ports(text, top):
    m = re.search(r"^module\s+%s\s*\((.*?)\);" % re.escape(top), text,
                  re.M | re.S)
    if not m:
        raise RuntimeError("no module header for %s" % top)
    return [p.strip() for p in m.group(1).replace("\n", " ").split(",")
            if p.strip()]


def input_decls(text):
    return {m.group(2): (m.group(1) or "").strip()
            for m in re.finditer(
                r"^\s*input\s+(\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z0-9_$]*)\s*;",
                text, re.M)}


def free_inputs(text, top):
    ports = split_ports(text, top)
    decls = input_decls(text)
    return [p for p in ports if p in decls and p not in ("clock", "reset")]


def semantic_names(text, free):
    """Map free port -> semantic wire name via ``assign <sem> = <port>;``."""
    out = {}
    for port in free:
        m = re.search(
            r"^\s*assign\s+([A-Za-z][A-Za-z0-9_$]*)\s*=\s*%s\s*;\s*$"
            % re.escape(port), text, re.M)
        out[port] = m.group(1) if m else port
    return out


def prepare_normal(case_dir, sources, top="rvfi_wrapper", out_name="wrapper.v"):
    """Flatten, expose free inputs, rename them and write ``out_name``."""
    raw = ".entry.raw.v"
    run_yosys(case_dir, sources, top, raw)
    text = open(os.path.join(case_dir, raw)).read()
    os.unlink(os.path.join(case_dir, raw))

    free = free_inputs(text, top)
    sem = semantic_names(text, free)

    # Rename only the free ports, so internal ``_NNNN_`` names stay intact.
    for port in free:
        if sem[port] != port:
            text = re.sub(
                r"(?<![A-Za-z0-9_$])%s(?![A-Za-z0-9_$])" % re.escape(port),
                "i_" + sem[port], text)

    open(os.path.join(case_dir, out_name), "w").write(text)
    return text, sem


def tie_constant(case_dir, text, sem, ties, top="rvfi_wrapper"):
    """Write ``wrapper_constant.v`` by tying selected free inputs."""
    port_of = {s: p for p, s in sem.items()}
    out = text
    for name, value in ties.items():
        if name not in port_of:
            raise RuntimeError("%s: no free input %r (have %s)"
                               % (case_dir, name, sorted(port_of)))
        orig = port_of[name]
        port = orig if orig == name else "i_" + name

        # Drop the port from the module header.
        out, n = re.subn(r",\s*%s(?=\s*[,\)])" % re.escape(port), "",
                         out, count=1)
        if n == 0:
            out, n = re.subn(r"(?<=[(,\s])%s\s*," % re.escape(port), "",
                             out, count=1)
        if n != 1:
            raise RuntimeError("%s: could not remove port %s" % (case_dir, port))

        # Drop its input declaration.
        out = re.sub(r"^\s*input\s+(\[[^\]]*\]\s*)?%s\s*;\s*$" % re.escape(port),
                     "", out, flags=re.M)

        # Drive the semantic wire.
        if orig != name:
            out, n = re.subn(
                r"^\s*assign\s+%s\s*=\s*%s\s*;\s*$"
                % (re.escape(name), re.escape(port)),
                "  assign %s = %s;" % (name, value), out, flags=re.M)
            if n != 1:
                raise RuntimeError("%s: no alias assign for %s" % (case_dir, name))
        else:
            out = out.replace("\nendmodule",
                              "\n  assign %s = %s;\nendmodule" % (name, value),
                              1)

        if port in split_ports(out, top):
            raise RuntimeError("%s: port %s still present" % (case_dir, port))

    open(os.path.join(case_dir, "wrapper_constant.v"), "w").write(out)


# picorv32 constant: patch the instruction-carrying signals in the core ------
PATCHED_SOURCE = ".picorv32_constant.sv"


def prepare_picorv32_constant(case_dir, word):
    """Build wrapper_constant.v from a source-level patched picorv32.sv."""
    src = open(os.path.join(case_dir, "picorv32.sv")).read()
    literal = "32'b" + word
    patterns = [
        (r"^(\s*)assign mem_rdata_latched_noshuffle = .*?;\s*$",
         r"\1assign mem_rdata_latched_noshuffle = %s;" % literal),
        (r"^(\s*)mem_rdata_q <= .*?;\s*$",
         r"\1mem_rdata_q <= %s;" % literal),
        (r"^(\s*)next_insn_opcode <= .*?;\s*$",
         r"\1next_insn_opcode <= %s;" % literal),
    ]
    for pattern, repl in patterns:
        src, n = re.subn(pattern, repl, src, count=1, flags=re.M)
        if n != 1:
            raise RuntimeError("%s: could not patch %r" % (case_dir, pattern))

    patched = os.path.join(case_dir, PATCHED_SOURCE)
    open(patched, "w").write(src)
    try:
        prepare_normal(case_dir, [PATCHED_SOURCE, "wrapper.sv"],
                       out_name="wrapper_constant.v")
    finally:
        os.unlink(patched)


# Per-family drivers ---------------------------------------------------------
def cases_for(family):
    root = os.path.join(HERE, family)
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d))
                  and os.path.exists(os.path.join(root, d, "wrapper.sv")))


def serv_sources(case_dir):
    rtl = os.path.join(case_dir, "rtl")
    return ["rtl/" + f for f in sorted(os.listdir(rtl))
            if f.endswith((".v", ".sv"))] + ["wrapper.sv"]


def build_picorv32(case_dir, case):
    prepare_normal(case_dir, ["picorv32.sv", "wrapper.sv"])
    prepare_picorv32_constant(case_dir, picorv32_word(case_dir, case))


def build_serv(case_dir, case):
    _, sem = prepare_normal(case_dir, serv_sources(case_dir))
    ties = {
        "ibus_rdt": "32'h%08x" % ADD,
        "ibus_ack": "1'b1",
        "dbus_ack": "1'b1",
        "dbus_rdt": "32'b0",
    }
    tie_constant(case_dir, open(os.path.join(case_dir, "wrapper.v")).read(),
                 sem, ties)


def build_nerv(case_dir, case):
    text, sem = prepare_normal(case_dir, ["nerv.sv", "wrapper.sv"])
    tie_constant(case_dir, text, sem, nerv_ties(case, set(sem.values())))


BUILDERS = {
    "picorv32": build_picorv32,
    "serv": build_serv,
    "nerv": build_nerv,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*",
                    help="family or family/case (default: all)")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    args = ap.parse_args(argv)

    selected = []
    if not args.targets:
        selected = [(f, c) for f in FAMILIES for c in cases_for(f)]
    else:
        for target in args.targets:
            if "/" in target:
                family, case = target.split("/", 1)
                selected.append((family, case))
            elif target in BUILDERS:
                selected.extend((target, c) for c in cases_for(target))
            else:
                ap.error("unknown target %r" % target)

    if args.list:
        for family, case in selected:
            print("%s/%s" % (family, case))
        return 0

    for family, case in selected:
        if family not in BUILDERS:
            ap.error("unknown family %r" % family)
        case_dir = os.path.join(HERE, family, case)
        if not os.path.isdir(case_dir):
            ap.error("no such case: %s/%s" % (family, case))
        print("%s/%s" % (family, case))
        BUILDERS[family](case_dir, case)
    return 0


if __name__ == "__main__":
    sys.exit(main())
