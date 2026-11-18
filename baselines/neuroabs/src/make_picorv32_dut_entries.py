#!/usr/bin/env python3
"""Generate unflattened picorv32 DUT entry points for test4neuroabs.

The flattened ``wrapper.v`` entry points expose only a handful of the core's
internal signals (12 abstractable statements in ``insn_add``).  The official
riscv-formal flow instead abstracts the *unflattened* ``picorv32`` core and
keeps ``wrapper.sv`` / ``tb.sv`` / the instruction checker around it.  This
script generates that second entry point for every ``picorv32/<case>``:

  picorv32_input.v           Verilator-preprocessed core (``-E -I.``)
  picorv32_input_constant.v  the same core with the case's instruction word
                             written into the three instruction-carrying
                             signals (mirrors ``prepare_picorv32_constant``)
  dut/wrapper_abstract_llm_new.v
                             the core after NeuroAbs abstraction (shared;
                             the preprocessed core is identical for all cases)
  dut/statement.json         input -> original statement map
  dut/input_line.json        input -> line in the abstracted DUT
  dut_cegar.ys               CEGAR-ready Yosys script (``--dut`` mode)

The preprocessed core is byte-identical across picorv32 cases because only
``defines.sv``'s ``RISCV_FORMAL_INSN_MODEL`` macro changes; that macro is used
by the harness, not the core.  The shared abstraction can therefore be reused
for all cases, while each case still gets its own constant variant and its own
harness/checker selection.

Usage:
    python3 src/make_picorv32_dut_entries.py [--jobs 6] [--constant-only]
    python3 src/make_picorv32_dut_entries.py picorv32/insn_add
    python3 src/make_picorv32_dut_entries.py --reuse /path/to/abstracted-dut

``--constant-only`` (default) regenerates the entry points and runs
``main.py --constant-only`` to record the candidate count.  ``--abstract``
copies the shared abstraction and builds the final BTOR2 model.  ``--cegar``
additionally runs ``src/cegar.py`` on the selected cases.
"""

import argparse
import ast
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEUROABS_ROOT = os.path.dirname(HERE)
BENCH_ROOT = os.path.abspath(os.path.join(
    NEUROABS_ROOT, "..", "..", "benchmarks", "test4neuroabs"))
MAIN_PY = os.path.join(HERE, "main.py")
CEGAR_PY = os.path.join(HERE, "cegar.py")

sys.path.insert(0, HERE)
sys.path.insert(0, BENCH_ROOT)

from make_neuroabs_entries import picorv32_word  # noqa: E402
from make_cegar_script import build_script  # noqa: E402


# --------------------------------------------------------------------------
# Entry-point generation
# --------------------------------------------------------------------------
def normalize_source(src):
    """Make the Verilator output palatable to PyVerilog / the dataflow pass.

    * Verilator preserves the source spelling ``32'h 0000_0000``; PyVerilog's
      lexer wants the digits immediately after the base.
    * ``picorv32.sv`` uses parameter expressions in declarations; the dataflow
      width resolver only handles simple constants.  The default configuration
      gives the same values as the upstream ``picorv32.v`` that the official
      flow uses.
    """
    src = re.sub(r"(\d+'[bdhBDH])\s+(?=[0-9a-fA-FxXzZ_])", r"\1", src)
    replacements = [
        (r"localparam\s+integer\s+irq_timer\s*=\s*0;",
         "parameter irq_timer = 0;"),
        (r"localparam\s+integer\s+irq_ebreak\s*=\s*1;",
         "parameter irq_ebreak = 1;"),
        (r"localparam\s+integer\s+irq_buserror\s*=\s*2;",
         "parameter irq_buserror = 2;"),
        (r"localparam\s+integer\s+irqregs_offset\s*=\s*[^;]*;",
         "parameter irqregs_offset = 32;"),
        (r"localparam\s+integer\s+regfile_size\s*=\s*[^;]*;",
         "parameter regfile_size = 32;"),
        (r"localparam\s+integer\s+regindex_bits\s*=\s*[^;]*;",
         "parameter regindex_bits = 5;"),
    ]
    for pattern, repl in replacements:
        src, count = re.subn(pattern, repl, src, count=1)
        if count != 1:
            print("warning: normalization pattern did not match: %s" % pattern,
                  file=sys.stderr)
    return src


def preprocess_core(case_dir):
    """Run Verilator on one case's ``picorv32.sv`` preview."""
    proc = subprocess.run(
        ["verilator", "-E", "-I.", "picorv32.sv"],
        cwd=case_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    if proc.returncode:
        raise RuntimeError("verilator failed in %s:\n%s"
                           % (case_dir, proc.stderr[-4000:]))
    return normalize_source(proc.stdout)


def write_constant(case_dir, case, core_text):
    """Write ``picorv32_input_constant.v`` with the case's instruction word."""
    literal = "32'b" + picorv32_word(case_dir, case)
    patterns = [
        (r"^(\s*)assign mem_rdata_latched_noshuffle = .*?;\s*$",
         r"\1assign mem_rdata_latched_noshuffle = %s;" % literal),
        (r"^(\s*)mem_rdata_q <= .*?;\s*$",
         r"\1mem_rdata_q <= %s;" % literal),
        (r"^(\s*)next_insn_opcode <= .*?;\s*$",
         r"\1next_insn_opcode <= %s;" % literal),
    ]
    text = core_text
    for pattern, repl in patterns:
        text, count = re.subn(pattern, repl, text, count=1, flags=re.M)
        if count != 1:
            raise RuntimeError("%s: could not patch %r" % (case_dir, pattern))
    with open(os.path.join(case_dir, "picorv32_input_constant.v"), "w") as handle:
        handle.write(text)


def write_entry_points(case_dir, case, core_text, force):
    input_path = os.path.join(case_dir, "picorv32_input.v")
    if force or not os.path.exists(input_path):
        with open(input_path, "w") as handle:
            handle.write(core_text)
    write_constant(case_dir, case, core_text)


# --------------------------------------------------------------------------
# Candidate verification (main.py --constant-only)
# --------------------------------------------------------------------------
CLEAN_ARTIFACTS = (
    "normal.txt", "constant.txt", "extract.txt",
    "normal_extract.txt", "constant_extract.txt",
    "map.txt", "problem_0.v", "problem_1.v",
    ".llm4abs_constant_prop.ys",
    "picorv32_input.aag", "picorv32_input_constant.aag",
    "time_constant_prop.txt",
)


def parse_candidates(output):
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("[") and line.endswith("]") and "'" in line:
            try:
                value = ast.literal_eval(line)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, list):
                return value
    return None


def run_constant_only(case_dir, timeout=600):
    desc = os.path.join(case_dir, "description.txt")
    env = dict(os.environ)
    env.pop("API_KEY", None)
    env.pop("API_URL", None)
    cmd = [
        sys.executable, "-u", MAIN_PY,
        "--constant-only",
        "-t", "picorv32",
        "--constant-template", "picorv32",
        "-l",
        "-d", desc,
        "picorv32_input.v",
    ]
    started = time.time()
    proc = subprocess.run(cmd, cwd=case_dir, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True,
                          timeout=timeout, env=env)
    elapsed = time.time() - started
    candidates = parse_candidates(proc.stdout)
    for name in CLEAN_ARTIFACTS:
        path = os.path.join(case_dir, name)
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
    return {
        "returncode": proc.returncode,
        "seconds": round(elapsed, 2),
        "candidates": len(candidates) if candidates is not None else None,
        "output_tail": proc.stdout[-1200:],
    }


# --------------------------------------------------------------------------
# Shared abstraction + CEGAR model
# --------------------------------------------------------------------------
def copy_abstraction(case_dir, shared_dir):
    dut_dir = os.path.join(case_dir, "dut")
    os.makedirs(dut_dir, exist_ok=True)
    for name in ("wrapper_abstract_llm_new.v", "statement.json",
                 "input_line.json"):
        shutil.copy2(os.path.join(shared_dir, name),
                     os.path.join(dut_dir, name))
    return dut_dir


def write_cegar_script(case_dir):
    script = build_script(case_dir, dut=True)
    path = os.path.join(case_dir, "dut_cegar.ys")
    with open(path, "w") as handle:
        handle.write(script)
    return path


def build_model(case_dir, timeout=600):
    """Substitute the abstracted DUT for the placeholder and run Yosys."""
    script_path = os.path.join(case_dir, "dut_cegar.ys")
    with open(script_path) as handle:
        script = handle.read()
    dut_path = os.path.join(case_dir, "dut", "wrapper_abstract_llm_new.v")
    script = script.replace("read_verilog -sv wrapper.v",
                            "read_verilog -sv %s" % dut_path)
    dut_dir = os.path.join(case_dir, "dut")
    temp_path = os.path.join(dut_dir, ".dut_build.ys")
    with open(temp_path, "w") as handle:
        handle.write(script)
    env = dict(os.environ)
    env.setdefault("YOSYS_BIN", "yosys")
    started = time.time()
    try:
        proc = subprocess.run(
            [env["YOSYS_BIN"], "-q", "-s", temp_path],
            cwd=dut_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout, env=env)
        rc = proc.returncode
        tail = proc.stdout[-1200:]
    except subprocess.TimeoutExpired:
        rc = 124
        tail = "timeout after %ss" % timeout
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    return {
        "returncode": rc,
        "seconds": round(time.time() - started, 2),
        "btor2": os.path.exists(
            os.path.join(dut_dir, "wrapper_abstract_llm_new.btor2")),
        "output_tail": tail,
    }


def run_cegar(case_dir, timeout, pono_timeout=90):
    dut_dir = os.path.join(case_dir, "dut")
    env = dict(os.environ)
    env.setdefault("YOSYS_BIN", "yosys")
    cmd = [
        sys.executable, "-u", CEGAR_PY,
        "-f", "iter",
        "-y", os.path.join(case_dir, "dut_cegar.ys"),
        "--timeout", str(pono_timeout),
        os.path.join(dut_dir, "wrapper_abstract_llm_new.v"),
    ]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=dut_dir, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True,
                              timeout=timeout, env=env)
        rc = proc.returncode
        tail = proc.stdout[-2000:]
    except subprocess.TimeoutExpired:
        rc = 124
        tail = "timeout after %ss" % timeout
    return {
        "returncode": rc,
        "seconds": round(time.time() - started, 2),
        "output_tail": tail,
    }


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def case_list(targets):
    root = os.path.join(BENCH_ROOT, "picorv32")
    if not targets:
        return sorted(
            os.path.join(root, name) for name in os.listdir(root)
            if os.path.isdir(os.path.join(root, name))
            and os.path.exists(os.path.join(root, name, "picorv32.sv")))
    cases = []
    for target in targets:
        target = target.rstrip("/")
        if os.path.isdir(target):
            cases.append(os.path.abspath(target))
        elif "/" in target:
            cases.append(os.path.join(BENCH_ROOT, target))
        else:
            cases.append(os.path.join(root, target))
    return cases


def prepare_case(case_dir, core_text, shared_dir, force,
                 do_constant_only, do_abstract, do_build):
    case = os.path.basename(case_dir)
    result = {"case": case, "dir": case_dir}
    write_entry_points(case_dir, case, core_text, force)
    if do_abstract or do_build:
        copy_abstraction(case_dir, shared_dir)
        result["cegar_script"] = write_cegar_script(case_dir)
    if do_constant_only:
        result["constant_only"] = run_constant_only(case_dir)
    if do_build and shared_dir:
        result["build"] = build_model(case_dir)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*",
                        help="case directories or names (default: all)")
    parser.add_argument("--reuse",
                        default=os.path.join(HERE, "picorv32_dut_shared"),
                        help="directory with the shared abstracted DUT + maps "
                             "(default: src/picorv32_dut_shared)")
    parser.add_argument("--jobs", type=int, default=6,
                        help="parallel cases (default: 6)")
    parser.add_argument("--force", action="store_true",
                        help="rewrite picorv32_input.v even if it exists")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip main.py --constant-only")
    parser.add_argument("--abstract", action="store_true",
                        help="copy the shared abstraction and write dut_cegar.ys "
                             "(implied by --build/--cegar)")
    parser.add_argument("--build", action="store_true",
                        help="build the DUT BTOR2 model with Yosys")
    parser.add_argument("--cegar", action="store_true",
                        help="run src/cegar.py on the selected cases")
    parser.add_argument("--cegar-timeout", type=int, default=300,
                        help="wall-clock timeout per case (default: 300)")
    parser.add_argument("--pono-timeout", type=int, default=90,
                        help="timeout for each Pono query (default: 90)")
    parser.add_argument("--summary", default="/tmp/opencode/picorv32_dut_summary.json",
                        help="summary JSON path")
    args = parser.parse_args(argv)

    cases = case_list(args.targets)
    if not cases:
        parser.error("no picorv32 cases selected")
    if not os.path.isdir(args.reuse):
        parser.error("--reuse directory does not exist: %s" % args.reuse)
    shared = os.path.abspath(args.reuse)
    for name in ("wrapper_abstract_llm_new.v", "statement.json", "input_line.json"):
        if not os.path.exists(os.path.join(shared, name)):
            parser.error("missing %s in %s" % (name, shared))

    # All picorv32 cases share the same preprocessed core.
    core_text = preprocess_core(cases[0])
    core_md5 = __import__("hashlib").md5(core_text.encode()).hexdigest()
    print("preprocessed core: %d bytes, md5 %s" % (len(core_text), core_md5))

    do_constant_only = not args.no_verify
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(prepare_case, case_dir, core_text, shared,
                        args.force, do_constant_only,
                        args.abstract or args.build or args.cegar,
                        args.build): case_dir
            for case_dir in cases
        }
        for future in concurrent.futures.as_completed(futures):
            case_dir = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # keep going; record the failure
                result = {"case": os.path.basename(case_dir),
                          "dir": case_dir, "error": repr(exc)}
            results.append(result)
            status = "ok"
            if result.get("error"):
                status = "error: %s" % result["error"]
            else:
                co = result.get("constant_only") or {}
                build = result.get("build") or {}
                status = "cand=%s rc=%s" % (co.get("candidates"), co.get("returncode"))
                if build:
                    status += " build=%s" % build.get("returncode")
            print("%-22s %s" % (result["case"], status))

    results.sort(key=lambda item: item["case"])
    with open(args.summary, "w") as handle:
        json.dump(results, handle, indent=2)
    print("summary: %s" % args.summary)

    if args.cegar:
        for result in results:
            if result.get("error"):
                continue
            case_dir = result["dir"]
            print("cegar %s ..." % result["case"])
            result["cegar"] = run_cegar(case_dir, args.cegar_timeout,
                                        pono_timeout=args.pono_timeout)
            print("  rc=%s %.1fs" % (result["cegar"]["returncode"],
                                     result["cegar"]["seconds"]))
        with open(args.summary, "w") as handle:
            json.dump(results, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
