"""Create a hashed, oracle-free planner context from the staged case/model."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import jsonschema

from common.pcd_util import read_text, sha256_file

from .backends import normalize_engines
from .build import load_build
from .core import (
    PcdError,
    freeze_json,
    iter_strings,
    load_frozen_json,
    read_json,
    relative_to,
)

TEXT_SUFFIXES = {".v", ".sv", ".vh", ".svh", ".sva", ".json", ".yaml", ".yml", ".txt"}
DIAGNOSTIC_SCHEMA = Path(__file__).resolve().parents[1] / "schema" / "diagnostic.schema.json"


def _diagnostic_context(source: str | Path, run_dir: Path) -> dict[str, Any]:
    """Copy a validated CTI diagnostic into the run and make a bounded view.

    This is the feedback seam: a new frozen iteration may include diagnostics
    from an earlier run, but never a proof, contract, or decomposition.  The
    diagnostic file is hashed into the context and the audit checks that it is
    still the same diagnostic-only record.
    """
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise PcdError(f"diagnostics context does not exist: {source}")
    markers = ("oracle/", "/oracle/")
    if any(marker in str(source) for marker in markers):
        raise PcdError(f"diagnostics context is oracle-tainted: {source}")
    doc = read_json(source)
    if any(marker in text for text in iter_strings(doc) for marker in markers):
        raise PcdError("diagnostics context contains an oracle marker")
    schema = read_json(DIAGNOSTIC_SCHEMA)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(doc),
        key=lambda e: (tuple(str(p) for p in e.absolute_path), e.message),
    )
    if errors:
        where = "/".join(str(p) for p in errors[0].absolute_path) or "<root>"
        raise PcdError(f"diagnostics context is invalid at {where}: {errors[0].message}")
    if doc.get("evidence") != "DIAGNOSTIC" or doc.get("proof") is not False:
        raise PcdError("diagnostics context is not diagnostic-only")
    dest = run_dir / "diagnostics-context.json"
    shutil.copy2(source, dest)
    ctis = []
    for item in doc.get("ctis", []):
        cti = item.get("cti") or {}
        vcd = item.get("vcd") or {}
        ctis.append(
            {
                "property_index": item.get("property_index"),
                "property_name": item.get("property_name"),
                "status": item.get("status"),
                "reason": item.get("reason"),
                "state_frames": len(cti.get("state_frames", [])),
                "vcd_frames": vcd.get("frames", []),
                "final": vcd.get("final", {}),
                "changes": vcd.get("changes", []),
            }
        )
    return {
        "path": "diagnostics-context.json",
        "sha256": sha256_file(str(dest)),
        "source_run": doc.get("run_id"),
        "status": doc.get("status"),
        "bmc": doc.get("bmc"),
        "properties": doc.get("properties", []),
        "ctis": ctis,
        "notes": doc.get("notes", []),
    }


def _parse_btor(path: Path) -> dict[str, Any]:
    text = read_text(str(path))
    counts = {"inputs": 0, "states": 0, "bad": 0, "constraints": 0, "justice": 0}
    inputs: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    properties: list[dict[str, Any]] = []
    for line in text.splitlines():
        m_bad = re.match(r"^\s*\d+\s+bad\s+\d+\s+([^\s;]+)(?:\s*;\s*(.*))?$", line)
        if m_bad:
            properties.append(
                {
                    "index": len(properties),
                    "name": m_bad.group(1),
                    "source": (m_bad.group(2) or "").strip() or None,
                }
            )
            continue
        m_input = re.match(r"^\s*\d+\s+input\s+\d+(?:\s+([^\s;]+))?", line)
        if m_input:
            counts["inputs"] += 1
            inputs.append({"name": m_input.group(1)})
            continue
        m_state = re.match(r"^\s*\d+\s+state\s+\d+(?:\s+([^\s;]+))?", line)
        if m_state:
            counts["states"] += 1
            states.append({"name": m_state.group(1)})
            continue
        if re.match(r"^\s*\d+\s+constraint\b", line):
            counts["constraints"] += 1
        elif re.match(r"^\s*\d+\s+justice\b", line):
            counts["justice"] += 1
    counts["bad"] = len(properties)
    return {
        "counts": counts,
        "properties": properties,
        "inputs": [x for x in inputs if x.get("name")],
        "states": [x for x in states if x.get("name")],
    }


def _parse_info(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    info: dict[str, Any] = {"name": None, "posedges": []}
    for line in read_text(str(path)).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "name":
            info["name"] = parts[1]
        elif len(parts) >= 2 and parts[0] == "posedge":
            try:
                info["posedges"].append(int(parts[1]))
            except ValueError:
                pass
    return info


def _parse_source(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"modules": [], "assertions": []}
    if path.suffix not in TEXT_SUFFIXES or path.stat().st_size > 4 * 1024 * 1024:
        return out
    try:
        text = read_text(str(path))
    except OSError:
        return out
    out["modules"] = sorted(set(re.findall(r"(?m)^\s*module\s+([A-Za-z_]\w*)", text)))
    seen: set[str] = set()
    for m in re.finditer(r"(?m)^\s*([A-Za-z_]\w*)\s*:\s*assert\b", text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out["assertions"].append(name)
    for m in re.finditer(r"(?m)^\s*assert\s*(?:property)?\s*\(\s*([^)\n]+)", text):
        expr = " ".join(m.group(1).split())
        if expr and expr not in seen:
            seen.add(expr)
            out["assertions"].append(expr[:240])
    return out


def _input_sketch(staged: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in case["inputs"]["files"]:
        p = staged / spec["path"]
        item: dict[str, Any] = {
            "path": spec["path"],
            "role": spec["role"],
            "exists": p.is_file(),
        }
        if p.is_file():
            item["sha256"] = sha256_file(str(p))
            if p.suffix in TEXT_SUFFIXES:
                item.update(_parse_source(p))
        items.append(item)
    return items


def run_sketch(
    run_dir: Path,
    case: dict[str, Any],
    build: dict[str, Any] | None = None,
    *,
    engines: dict[str, Any] | None = None,
    diagnostics_path: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    engine_catalog = normalize_engines(engines)
    staged = run_dir / "case"
    if build is None:
        build = load_build(run_dir)
    model = build.get("model")
    if not model:
        raise PcdError("build record has no model")
    model_path = (staged / model["path"]).resolve()
    if not model_path.is_file():
        raise PcdError(f"built model is missing: {model_path}")
    parsed = _parse_btor(model_path)
    info = _parse_info(model_path.parent / "dut.info")
    for spec in case["inputs"]["files"]:
        declared = spec.get("sha256")
        if not declared:
            continue
        p = staged / spec["path"]
        if p.is_symlink() or not p.is_file():
            raise PcdError(f"staged input is missing or a symlink: {spec['path']}")
        actual = sha256_file(str(p))
        if actual != declared:
            raise PcdError(f"staged input changed before sketching: {spec['path']}")
    inputs = _input_sketch(staged, case)

    # Bind bad properties to assertion declarations where the source makes the
    # name visible. This is provenance, not proof.
    for prop in parsed["properties"]:
        prop["assertion_file"] = None
        for item in inputs:
            if prop["name"] in item.get("assertions", []):
                prop["assertion_file"] = item["path"]
                break

    policy = case["run_policy"]
    context: dict[str, Any] = {
        "schema_version": "pcd-context/0.1",
        "case": {
            "id": case["case"],
            "description": case.get("description", ""),
            "claim_scope": case["claim_scope"],
            "targets": [
                {
                    "id": t["id"],
                    "statement": t["statement"],
                    "guard": t.get("guard"),
                    "observation": t.get("observation"),
                    "claim_level": t["claim_level"],
                    **({"required_properties": t["required_properties"]} if "required_properties" in t else {}),
                }
                for t in case["targets"]
            ],
            "budgets": case["budgets"],
            "run_policy": {
                "mode": policy["mode"],
                "planner": policy.get("planner"),
                "pre_registered": policy.get("pre_registered", False),
                "template_backend": policy.get("template_backend", "portfolio"),
            },
        },
        "build": {
            "model": {
                "id": model["id"],
                "kind": model["kind"],
                "sha256": model["sha256"],
                "path": relative_to(model_path, staged),
            },
            "tool_versions": build.get("tool_versions", {}),
            "recipe": build.get("recipe", {}),
        },
        "model": {
            **parsed,
            "info": info,
            "path": relative_to(model_path, run_dir),
        },
        "inputs": inputs,
        "allowed": {
            "evidence": ["REPLAY", "CHECKED", "TCB"],
            "certificate_formats": ["replay", "poly", "smt-implication", "smt-induction", "btor-smt", "tcb"],
            "engines": engine_catalog,
        },
    }
    if diagnostics_path is not None:
        context["diagnostics"] = _diagnostic_context(diagnostics_path, run_dir)
    freeze_json(run_dir / "context.json", context)
    return context


def load_context(run_dir: Path) -> tuple[dict[str, Any], str]:
    return load_frozen_json(Path(run_dir) / "context.json")
