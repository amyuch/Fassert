#!/usr/bin/env python3
"""Adapt one fassert picorv32 RVFI case into a single-file large-lemma-miners input.

The large-lemma-miners baseline expects:
  * one SystemVerilog file,
  * a module named by ``top`` in ``ric3.toml``,
  * a distinguished ``property prop; ... endproperty`` at that top level,
  * an EBMC-parseable source (no function-like macros / multi-file includes).

This script:
  1. preprocesses the case with Icarus Verilog (``iverilog -E``),
  2. removes the RVFI checker's immediate asserts,
  3. adds ``property prop`` to the formal top, inlining the same guard and
     payload (with hierarchical references into the checker instance).

Only the reduced/full RVFI instruction checker shape is handled.  That is the
shape used by ``insn_add``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path


def read(path: Path) -> str:
    return path.read_text(errors="replace")


def find_module_span(text: str, module: str) -> tuple[int, int]:
    m = re.search(rf"\bmodule\s+{re.escape(module)}\b", text)
    if not m:
        raise ValueError(f"module {module!r} not found")
    end = text.find("endmodule", m.start())
    if end < 0:
        raise ValueError(f"endmodule for {module!r} not found")
    return m.start(), end


def collect_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """Return lines of a begin/end block starting at ``lines[start]``.

    ``lines[start]`` must contain ``begin``.  The returned block includes the
    opening line; the final ``end`` line is included as well.
    """
    depth = 0
    out = []
    for i in range(start, len(lines)):
        line = lines[i]
        out.append(line)
        # Good enough for the generated checker: no begin/end inside strings.
        depth += len(re.findall(r"\bbegin\b", line))
        depth -= len(re.findall(r"\bend\b", line))
        if i > start and depth <= 0:
            return out, i + 1
    raise ValueError("unterminated begin/end block")


def qualify(expr: str) -> str:
    """Prefix checker-local identifiers with the instance name."""
    return re.sub(
        r"\b(spec_\w+|mem_access_fault)\b", r"checker_inst.\1", expr
    )


def adapt(case_dir: Path, out_file: Path) -> None:
    cfg = tomllib.loads(read(case_dir / "ric3.toml"))
    dut = cfg["dut"]
    top = dut["top"]
    files = dut["files"]

    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_pre = out_file.with_suffix(".pre.sv")
    cmd = [
        "iverilog",
        "-E",
        "-g2012",
        "-I",
        str(case_dir),
        "-o",
        str(tmp_pre),
        *files,
    ]
    subprocess.run(cmd, cwd=case_dir, check=True)
    text = read(tmp_pre)
    tmp_pre.unlink()

    # The reduced RVFI instruction checker is selected by this macro.
    defines = read(case_dir / "defines.sv")
    m = re.search(r"`define\s+RISCV_FORMAL_CHECKER\s+(\w+)", defines)
    if not m:
        raise ValueError("RISCV_FORMAL_CHECKER macro not found")
    checker = m.group(1)

    c_start, c_end = find_module_span(text, checker)
    checker_text = text[c_start : c_end + len("endmodule")]

    # Locate the clocked block that contains the immediate asserts.
    c_lines = checker_text.splitlines(keepends=True)
    block_start = None
    for i, line in enumerate(c_lines):
        if "always" in line and "posedge clock" in line and "begin" in line:
            block_start = i
    if block_start is None:
        raise ValueError("clocked checker block not found")
    block, block_end = collect_block(c_lines, block_start)
    block_text = "".join(block)

    asserts = re.findall(r"assert\s*\((.*?)\)\s*;", block_text, re.S)
    if not asserts:
        raise ValueError("no immediate asserts found in checker")
    guards = re.findall(r"if\s*\((.*?)\)\s*begin", block_text, re.S)
    if not guards:
        raise ValueError("no guard conditions found in checker")

    guard = " && ".join(f"({g.strip()})" for g in guards)
    payload = " && ".join(f"({a.strip()})" for a in asserts)
    fail_expr = qualify(f"({guard}) && !({payload})")

    # Remove the assert block from the checker.
    c_lines[block_start:block_end] = [
        "\t// Immediate asserts replaced by the top-level property prop.\n"
    ]
    checker_text = "".join(c_lines)
    text = text[:c_start] + checker_text + text[c_end + len("endmodule") :]

    # Add the target property at the formal top.
    t_start, t_end = find_module_span(text, top)
    prop = (
        "\n\t// prop is violated when a valid ADD retires with a mismatched\n"
        "\t// rd_wdata or pc_wdata.  rvfi_valid is high for every retired\n"
        "\t// instruction, not only ADD.\n"
        "\t// The DUT pipeline state is under testbench.wrapper.uut.  EBMC's\n"
        "\t// k-induction does not support $past; use current-state invariants.\n"
        "\tproperty prop;\n"
        "\t\t@(posedge clock) disable iff (reset)\n"
        f"\t\t\t!({fail_expr});\n"
        "\tendproperty\n"
    )
    text = text[:t_end] + prop + text[t_end:]

    out_file.write_text(text)
    print(f"wrote {out_file} ({len(text)} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir", type=Path)
    ap.add_argument("out_file", type=Path)
    args = ap.parse_args()
    adapt(args.case_dir.resolve(), args.out_file.resolve())


if __name__ == "__main__":
    sys.exit(main())
