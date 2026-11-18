"""Import an official riscv-formal benchmark directory as a PCD case package.

The importer is deliberately a *case builder*, not a proof builder.  It copies
only the RTL/spec/checker surface named by the benchmark's ``ric3.toml`` and
creates a deterministic rIC3 build recipe.  It never copies a prior
``ric3proj/``, run directory, proof, helper assertion, or oracle.
"""
from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

from .core import PcdError, sha256_file, write_json, write_text


def _role(name: str) -> str:
    if name.startswith("insn_"):
        return "spec"
    if name == "rvfi_insn_check.sv" or name.endswith("_check.sv"):
        return "checker"
    if name == "defines.sv":
        return "defines"
    if name.endswith((".vh", ".svh")):
        return "include"
    if name in {"tb.sv", "wrapper.sv"}:
        return "harness"
    if name.startswith("helpers_"):
        return "helper"
    if name.endswith((".v", ".sv")):
        return "rtl"
    return "other"


def _case_name(path: Path, family: str | None = None) -> str:
    # Keep the historical picorv32_ prefix when no family is supplied so
    # existing official imports keep their names.  Callers importing the
    # multi-family benchmark tree should pass family="picorv32", "serv", etc.
    name = f"{family or 'picorv32'}_" + path.name
    name = "".join(ch.lower() if ch.isalnum() or ch in "_-" else "_" for ch in name)
    if not name[0].isalpha():
        name = "case_" + name
    return name


def _load_sources(benchmark: Path) -> tuple[list[str], dict[str, Any]]:
    toml_path = benchmark / "ric3.toml"
    if not toml_path.is_file():
        raise PcdError(f"benchmark has no ric3.toml: {benchmark}")
    with toml_path.open("rb") as fh:
        try:
            config = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise PcdError(f"{toml_path}: invalid TOML: {exc}") from exc
    dut = config.get("dut")
    if not isinstance(dut, dict):
        raise PcdError(f"{toml_path}: missing [dut] table")
    names: list[str] = []
    for key in ("files", "include_files"):
        values = dut.get(key, [])
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise PcdError(f"{toml_path}: dut.{key} must be a string array")
        for value in values:
            rel = Path(value)
            if (
                value in {"", ".", ".."}
                or rel.is_absolute()
                or ".." in rel.parts
                or rel.as_posix() == "."
            ):
                raise PcdError(
                    f"{toml_path}: source path must be relative and stay inside "
                    f"the benchmark: {value!r}"
                )
            posix = rel.as_posix()
            if posix not in names:
                names.append(posix)
    if not names:
        raise PcdError(f"{toml_path}: no source files listed")
    missing = [name for name in names if not (benchmark / name).is_file()]
    if missing:
        raise PcdError(f"benchmark is missing source files: {', '.join(missing)}")
    return names, config


def _build_script() -> str:
    return """#!/bin/sh
# Imported official benchmark: stage exactly the case inputs, then build.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work="$root/.pcd-build"
rm -rf "$work"
mkdir -p "$work"
# Copy recursively so benchmarks whose ric3.toml names subdirectories
# (for example serv's rtl/serv_*.v) keep the same layout in the work tree.
cp -R "$root"/input/rtl/. "$work"/
cp "$root"/build/ric3.toml "$work"/
cd "$work"
"${RIC3:-ric3}" build
"""


def import_benchmark(
    benchmark: str | Path,
    destination: str | Path,
    *,
    case_name: str | None = None,
    family: str | None = None,
    mode: str = "blind",
    force: bool = False,
) -> dict[str, Any]:
    """Create a case package from one official benchmark directory.

    The generated case targets every checker property in the model.  Which
    properties are actually applicable is a property of the ILA/checker, not of
    this importer; the planner and kernel decide whether the resulting
    obligations are proved.
    """
    benchmark = Path(benchmark).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    if not benchmark.is_dir():
        raise PcdError(f"benchmark directory does not exist: {benchmark}")
    if mode not in {"blind", "dev"}:
        raise PcdError(f"mode must be 'blind' or 'dev', got {mode!r}")
    if destination == Path(destination.anchor):
        raise PcdError(f"refusing to import into the filesystem root: {destination}")
    if destination == benchmark or benchmark.is_relative_to(destination):
        raise PcdError(f"destination must not contain the benchmark directory: {destination}")
    if destination.exists():
        if not force:
            raise PcdError(f"destination already exists: {destination} (use --force to replace)")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    sources, config = _load_sources(benchmark)
    name = case_name or _case_name(benchmark, family)
    if not name or not name[0].isalpha() or any(not (c.isalnum() or c in "_-") for c in name):
        raise PcdError(f"invalid case name: {name!r}")

    input_dir = destination / "input" / "rtl"
    build_dir = destination / "build"
    input_dir.mkdir(parents=True)
    build_dir.mkdir(parents=True)

    files: list[dict[str, str]] = []
    for rel in sources:
        src = benchmark / rel
        if src.is_symlink():
            raise PcdError(f"benchmark source must not be a symlink: {rel}")
        dst = input_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files.append(
            {
                "path": dst.relative_to(destination).as_posix(),
                "role": _role(src.name),
                "sha256": sha256_file(str(dst)),
            }
        )

    # Keep the benchmark's own build configuration, but use a case-local,
    # disposable build directory through the recipe script.
    shutil.copy2(benchmark / "ric3.toml", build_dir / "ric3.toml")
    write_text(build_dir / "build.sh", _build_script())

    top = config.get("dut", {}).get("top", "testbench")
    reset = config.get("dut", {}).get("reset", "reset")
    case = {
        "schema_version": "pcd-case/0.1",
        "case": name,
        "acceptance": "complete",
        "description": f"official riscv-formal benchmark {benchmark.name}",
        "claim_scope": "safety",
        "inputs": {
            "files": files,
            "environment": {
                "top": top,
                "reset": reset,
                "clock": "clock",
                "frontend": "yosys-slang",
                "defines": ["RISCV_FORMAL"],
            },
        },
        "build": {
            "kind": "btor",
            "recipe": {
                "command": ["sh", "build/build.sh"],
                "cwd": ".",
                "timeout_s": 300,
            },
            "outputs": [
                {
                    "path": ".pcd-build/ric3proj/dut/dut.btor",
                    "kind": "btor",
                }
            ],
        },
        "targets": [
            {
                "id": "root",
                "statement": f"all official RVFI checks for {benchmark.name}",
                "guard": "!reset && check",
                "observation": "rvfi retire",
                "claim_level": "root",
                "model_ref": "primary",
            }
        ],
        "budgets": {
            "total_seconds": 1800,
            "max_iterations": 4,
            "engine_seconds": {"ric3": 1200},
        },
        "run_policy": {
            "mode": mode,
            "oracle_paths": [],
            "pre_registered": True,
            "planner": "template",
            "template_backend": "cill",
            "notes": "imported official benchmark; no prior proof, run, oracle, or ric3proj is staged",
        },
    }
    write_json(destination / "case.json", case)
    return {
        "case": name,
        "destination": str(destination),
        "sources": list(sources),
        "model_output": ".pcd-build/ric3proj/dut/dut.btor",
        "mode": mode,
    }
