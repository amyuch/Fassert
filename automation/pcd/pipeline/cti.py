"""CTI diagnostics from ``ric3 cill``.

A CTI (counterexample to induction) is a *diagnostic*, not a proof and not a
premise.  This module only records what the engine emitted: normalized
inductiveness results, the raw CTI/state artifacts, hashes, and a bounded
human-readable summary of the VCD trace.  Unknown results and timeouts are
represented as ``unknown`` and never promoted to a CTI.

The commands themselves come from a trusted diagnostic catalog.  A planner
cannot provide a command here, just as it cannot for discharge engines.
"""
from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path
from typing import Any

import jsonschema

from common.pcd_util import read_text, sha256_file

from .backends import normalize_diagnostics, resolve_diagnostic_command
from .build import load_build
from .core import (
    PcdError,
    freeze_json,
    read_json,
    relative_to,
    run_command,
    write_json,
)
from .sketch import load_context

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "diagnostic.schema.json"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
MAX_FRAMES = 64
MAX_ASSIGNMENTS = 20000
MAX_VCD_SIGNALS = 512
MAX_VALUE_CHARS = 512

# Signals worth surfacing to a planner.  This is deliberately generic: RTL
# observation names, operation-interface names, and control/phase names.
INTERESTING_PREFIXES = (
    "rvfi_",
    "spec_",
    "pcpi_",
    "mem_",
    "dbg_",
    "cpuregs_",
    "latched_",
    "decoder_",
    "next_pc",
    "reg_",
    "cpu_state",
    "insn_",
    "trap",
    "irq",
    "reset",
    "clock",
    "check",
)


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _tail(text: str, lines: int = 20) -> list[str]:
    return [line for line in text.strip().splitlines()[-lines:] if line.strip()]


def parse_cill_check_log(text: str) -> dict[str, Any]:
    """Parse the table printed by ``ric3 cill check`` conservatively."""
    bmc = "unknown"
    properties: dict[int, dict[str, Any]] = {}
    for raw in text.splitlines():
        line = _strip_ansi(raw).strip()
        if not line:
            continue
        if "BMC found no CEX" in line:
            bmc = "clean"
            continue
        if re.search(r"BMC found (?:a )?CEX|counter-?example found|A CEX violating .+ was found",
                     line, flags=re.IGNORECASE):
            bmc = "cex"
            continue
        m = re.match(r"^(\d+)\s+(\S+)\s+(.+?)\s*$", line)
        if not m:
            continue
        index = int(m.group(1))
        name = m.group(2)
        result_text = m.group(3).lower()
        if "not inductive" in result_text:
            result = "not_inductive"
        elif "inductive" in result_text:
            result = "inductive"
        elif "unknown" in result_text or "timeout" in result_text:
            result = "unknown"
        elif "error" in result_text:
            result = "error"
        else:
            continue
        properties[index] = {"index": index, "name": name, "result": result}
    return {
        "bmc": bmc,
        "properties": [properties[i] for i in sorted(properties)],
        "tail": _tail(text),
    }


def parse_select_log(text: str) -> dict[str, Any]:
    clean = _strip_ansi(text)
    if "CTI VCD generated" in clean:
        return {"ok": True, "reason": "cti_vcd_generated", "tail": _tail(clean)}
    if "Unable to select" in clean:
        return {"ok": False, "reason": "unable_to_select", "tail": _tail(clean)}
    if "No CTI exists" in clean:
        return {"ok": False, "reason": "no_cti_exists", "tail": _tail(clean)}
    if "has not been run" in clean:
        return {"ok": False, "reason": "cill_check_not_run", "tail": _tail(clean)}
    return {"ok": False, "reason": "no_cti_marker", "tail": _tail(clean)}


def parse_cti_file(text: str) -> dict[str, Any]:
    """Parse the small RON-ish CTI format emitted by ric3 cill.

    The numeric identifiers are engine-internal node ids.  We preserve them
    verbatim rather than guessing a mapping to BTOR/VCD names; the VCD summary
    supplies the named signal view.
    """
    status = "unknown"
    bad: str | None = None
    state_frames: list[dict[str, Any]] = []
    input_frames: list[dict[str, Any]] = []
    current_state: dict[str, Any] | None = None
    current_input: dict[str, Any] | None = None
    sink = "state"
    assignments = 0
    truncated = False

    def _frame(index: int) -> dict[str, Any]:
        return {"index": index, "assignments": {}}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"sat", "unsat", "unknown"}:
            status = line
            continue
        m_bad = re.match(r"^b(\d+)$", line)
        if m_bad:
            bad = m_bad.group(1)
            continue
        m_state = re.match(r"^#(\d+)$", line)
        if m_state:
            if len(state_frames) >= MAX_FRAMES:
                truncated = True
                break
            current_state = _frame(int(m_state.group(1)))
            state_frames.append(current_state)
            sink = "state"
            continue
        m_input = re.match(r"^@(\d+)$", line)
        if m_input:
            if len(input_frames) >= MAX_FRAMES:
                truncated = True
                break
            current_input = _frame(int(m_input.group(1)))
            input_frames.append(current_input)
            sink = "input"
            continue
        if line == ".":
            break
        m_assign = re.match(r"^(\d+)\s+([01xXzZ]+)$", line)
        if not m_assign:
            continue
        if assignments >= MAX_ASSIGNMENTS:
            truncated = True
            break
        assignments += 1
        target = current_state if sink == "state" else current_input
        if target is None:
            continue
        value = m_assign.group(2).lower()
        if len(value) > MAX_VALUE_CHARS:
            value = value[:MAX_VALUE_CHARS]
            truncated = True
        target["assignments"][m_assign.group(1)] = value

    return {
        "status": status,
        "bad": bad,
        "state_frames": state_frames,
        "input_frames": input_frames,
        "assignments": assignments,
        "truncated": truncated,
    }


def _scope_name(parts: list[str]) -> str:
    return ".".join(part for part in parts if part)


def parse_vcd(text: str) -> dict[str, Any]:
    """Parse a VCD into a bounded named-signal view.

    The full VCD remains an artifact.  This view keeps the named values at the
    final frame plus per-frame changes so a planner can inspect the CTI without
    ingesting a multi-megabyte trace.
    """
    variables: dict[str, dict[str, Any]] = {}
    scopes: list[str] = []
    current: dict[str, str] = {}
    snapshots: list[tuple[int, dict[str, str]]] = []
    frame: int | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("$scope"):
            body = line[:-4].strip() if line.endswith("$end") else line
            parts = body.split()
            if len(parts) >= 3:
                scopes.append(parts[2])
            continue
        if line.startswith("$upscope"):
            if scopes:
                scopes.pop()
            continue
        if line.startswith("$var"):
            body = line[:-4].strip() if line.endswith("$end") else line
            parts = body.split()
            if len(parts) >= 5:
                try:
                    width = int(parts[2])
                except ValueError:
                    continue
                ident = parts[3]
                name = parts[4]
                variables[ident] = {
                    "name": _scope_name(scopes + [name]),
                    "width": width,
                }
            continue
        if line.startswith("$"):
            continue
        if line.startswith("#"):
            if frame is not None and len(snapshots) < MAX_FRAMES:
                snapshots.append((frame, dict(current)))
            try:
                frame = int(line[1:])
            except ValueError:
                continue
            continue
        if line[0] in "01xXzZ":
            value = line[0].lower()
            ident = line[1:].strip()
        elif line[0] in "bB":
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            value = parts[0][1:].lower()
            ident = parts[1].strip()
        else:
            # real/string value changes are not needed for this summary
            continue
        if ident in variables:
            current[ident] = value

    if frame is not None and len(snapshots) < MAX_FRAMES:
        snapshots.append((frame, dict(current)))

    # Build a stable name -> (width, id) view.
    by_name: dict[str, dict[str, Any]] = {}
    for ident, meta in variables.items():
        name = meta["name"]
        if not name or meta["width"] > 256:
            continue
        by_name[name] = {"id": ident, "width": meta["width"]}

    def _interesting(name: str) -> bool:
        short = name.rsplit(".", 1)[-1]
        return any(
            name == prefix
            or name.startswith(prefix)
            or short == prefix
            or short.startswith(prefix)
            for prefix in INTERESTING_PREFIXES
        )

    selected_names = sorted(
        name for name in by_name if _interesting(name)
    )
    if len(selected_names) > MAX_VCD_SIGNALS:
        selected_names = selected_names[:MAX_VCD_SIGNALS]

    frames: list[int] = []
    final: dict[str, dict[str, Any]] = {}
    changes: list[dict[str, Any]] = []
    previous: dict[str, str] = {}
    for index, (number, values) in enumerate(snapshots):
        frames.append(number)
        frame_values: dict[str, str] = {}
        for name in selected_names:
            value = values.get(by_name[name]["id"])
            if value is None:
                continue
            if not any(bit in value for bit in "01"):
                continue
            frame_values[name] = value
        if index == len(snapshots) - 1:
            final = {
                name: {"value": value, "width": by_name[name]["width"]}
                for name, value in sorted(frame_values.items())
            }
        delta = {
            name: {"value": value, "width": by_name[name]["width"]}
            for name, value in sorted(frame_values.items())
            if previous.get(name) != value
        }
        if delta:
            changes.append({"frame": number, "values": delta})
        previous = frame_values

    return {
        "frames": frames,
        "signal_count": len(variables),
        "selected_signal_count": len(selected_names),
        "final": final,
        "changes": changes,
        "truncated": len(snapshots) >= MAX_FRAMES or len(selected_names) >= MAX_VCD_SIGNALS,
    }


def _project_and_cill(model_path: Path) -> tuple[Path, Path]:
    resolved = model_path.resolve()
    for parent in resolved.parents:
        if (parent / "ric3proj").is_dir():
            return parent, parent / "ric3proj" / "cill"
    # A caller/test may use a non-ric3 layout.  Keep the location explicit but
    # local to the staged build instead of guessing outside the run.
    return resolved.parent, resolved.parent / "cill"


def _artifact(run_dir: Path, path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": relative_to(path, run_dir),
        "exists": path.is_file(),
    }
    if path.is_file():
        record["sha256"] = sha256_file(str(path))
        record["bytes"] = path.stat().st_size
    return record


def _copy_artifacts(run_dir: Path, cill_dir: Path, dest: Path) -> dict[str, Any]:
    dest.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {}
    for name in ("cti", "cti.vcd", "state.ron", "select.ron", "statistic.ron", "inv.ron"):
        src = cill_dir / name
        if not src.is_file():
            artifacts[name] = {"path": relative_to(dest / name, run_dir), "exists": False}
            continue
        out = dest / name
        shutil.copy2(src, out)
        artifacts[name] = _artifact(run_dir, out)
    return artifacts


def _call_record(phase: str, result: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    return {
        "phase": phase,
        "command": result["command"],
        "cwd": result.get("cwd"),
        "returncode": result["returncode"],
        "timed_out": result["timed_out"],
        "seconds": result["seconds"],
        "sandboxed": bool(result.get("sandboxed")),
        "log": relative_to(Path(result["log"]), run_dir),
        "log_sha256": result["log_sha256"],
    }


def _read_optional(path: Path) -> str:
    return read_text(str(path)) if path.is_file() else ""


def run_cti_diagnosis(
    run_dir: Path,
    case: dict[str, Any],
    *,
    build: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    property_index: int | None = None,
    timeout_s: int | None = None,
    diagnostics: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """Run ``ric3 cill`` and write a diagnostic record.

    The returned object is also frozen to ``diagnostics.json`` with a sibling
    sha256 file.  It is deliberately not a proof artifact.
    """
    run_dir = Path(run_dir)
    if build is None:
        build = load_build(run_dir)
    if context is None:
        context, _ = load_context(run_dir)
    model = build.get("model")
    if not model:
        raise PcdError("build record has no model")
    model_path = (run_dir / "case" / model["path"]).resolve()
    if not model_path.is_file():
        raise PcdError(f"built model is missing: {model_path}")
    if sha256_file(str(model_path)) != model["sha256"]:
        raise PcdError(f"built model changed: {model['path']}")
    if case["run_policy"]["mode"] == "blind" and property_index is not None:
        if property_index < 0:
            raise PcdError("--property must be non-negative")

    if project_dir is not None:
        project_root = Path(project_dir).resolve()
        cill_dir = project_root / "ric3proj" / "cill"
    else:
        project_root, cill_dir = _project_and_cill(model_path)
    if not project_root.is_dir():
        raise PcdError(f"cill project directory does not exist: {project_root}")

    catalog = normalize_diagnostics(diagnostics)
    budget = int(
        timeout_s
        or case["budgets"].get("engine_seconds", {}).get("ric3")
        or case["budgets"]["total_seconds"]
    )
    if budget < 1:
        raise PcdError("CTI timeout must be positive")
    mode = case["run_policy"]["mode"]
    sandbox = mode == "blind"

    calls: list[dict[str, Any]] = []
    # A stale cill directory would let a timeout look like a fresh CTI.
    if cill_dir.exists():
        shutil.rmtree(cill_dir)

    check_command = resolve_diagnostic_command(catalog, "ric3-cill", "check", {})
    check_log = run_dir / "logs" / "cti-check.log"
    check_result = run_command(
        check_command,
        cwd=project_root,
        log_path=check_log,
        timeout_s=budget,
        sandbox=sandbox,
        sandbox_root=run_dir,
    )
    calls.append(_call_record("check", check_result, run_dir))
    check_text = _read_optional(check_log)
    parsed_check = parse_cill_check_log(check_text)
    bmc = parsed_check["bmc"]
    parsed_props = {p["index"]: p for p in parsed_check["properties"]}

    context_props = {
        int(p["index"]): {"index": int(p["index"]), "name": str(p.get("name", ""))}
        for p in context.get("model", {}).get("properties", [])
    }
    properties: list[dict[str, Any]] = []
    for index in sorted(set(context_props) | set(parsed_props)):
        info = dict(context_props.get(index, {"index": index, "name": ""}))
        if index in parsed_props:
            info["result"] = parsed_props[index]["result"]
            if parsed_props[index].get("name"):
                info["name"] = parsed_props[index]["name"]
        else:
            info["result"] = "unknown"
        info["selected"] = False
        properties.append(info)

    def _base(status: str, note: str | None = None) -> dict[str, Any]:
        diag: dict[str, Any] = {
            "schema_version": "pcd-diagnostic/0.1",
            "case": case["case"],
            "run_id": run_dir.name,
            "model_sha256": model["id"],
            "source": {
                "tool": "ric3-cill",
                "catalog": copy.deepcopy(catalog),
                "mode": mode,
            },
            "evidence": "DIAGNOSTIC",
            "proof": False,
            "status": status,
            "bmc": bmc,
            "properties": properties,
            "ctis": [],
            "calls": calls,
            "artifacts": {
                "check_log": _artifact(run_dir, check_log),
            },
            "notes": [
                "CTIs are diagnostics, not proof evidence.",
                "A timeout, UNKNOWN, or missing artifact is never promoted to a CTI.",
            ],
        }
        if note:
            diag["notes"].append(note)
        return diag

    if check_result["timed_out"]:
        diag = _base("unknown", f"cill check timed out after {budget}s")
        freeze_json(run_dir / "diagnostics.json", diag)
        return diag
    if check_result["returncode"] != 0:
        diag = _base("unknown", f"cill check exited {check_result['returncode']}")
        freeze_json(run_dir / "diagnostics.json", diag)
        return diag
    if bmc == "cex":
        diag = _base("cex", "BMC reported a counterexample; no CTI was generated")
        freeze_json(run_dir / "diagnostics.json", diag)
        return diag

    candidates = [
        p for p in properties if p.get("result") == "not_inductive"
    ]
    if property_index is not None:
        match = next((p for p in properties if p["index"] == property_index), None)
        if match is None:
            diag = _base("unknown", f"property index {property_index} is not in the model")
            freeze_json(run_dir / "diagnostics.json", diag)
            return diag
        candidates = [match]

    if not candidates:
        if bmc == "clean":
            diag = _base("no_cti", "cill found no non-inductive property to select")
        else:
            diag = _base("unknown", "cill produced no usable inductiveness table")
        freeze_json(run_dir / "diagnostics.json", diag)
        return diag

    ctis: list[dict[str, Any]] = []
    for prop in candidates:
        index = int(prop["index"])
        name = str(prop.get("name", ""))
        prop["selected"] = True
        select_command = resolve_diagnostic_command(
            catalog, "ric3-cill", "select", {"property": str(index)}
        )
        select_log = run_dir / "logs" / f"cti-select-{index:03d}.log"
        select_result = run_command(
            select_command,
            cwd=project_root,
            log_path=select_log,
            timeout_s=budget,
            sandbox=sandbox,
            sandbox_root=run_dir,
        )
        calls.append(_call_record(f"select:{index}", select_result, run_dir))
        select_text = _read_optional(select_log)
        select_status = parse_select_log(select_text)
        entry: dict[str, Any] = {
            "property_index": index,
            "property_name": name,
            "status": "unknown",
            "select": select_status,
            "artifacts": {},
            "cti": None,
            "vcd": None,
        }
        if select_result["timed_out"]:
            entry["reason"] = f"select timed out after {budget}s; not a CTI"
            ctis.append(entry)
            continue
        if select_result["returncode"] != 0 or not select_status["ok"]:
            entry["reason"] = f"select did not produce a CTI ({select_status['reason']}); not a CTI"
            ctis.append(entry)
            continue

        dest = run_dir / "diagnostics" / f"cti-{index:03d}"
        entry["artifacts"] = _copy_artifacts(run_dir, cill_dir, dest)
        state_text = _read_optional(cill_dir / "state.ron").strip()
        entry["state"] = state_text
        if name and state_text and f'"{name}"' not in state_text:
            entry["reason"] = "cill state does not name the selected property; not a CTI"
            ctis.append(entry)
            continue
        cti_path = dest / "cti"
        vcd_path = dest / "cti.vcd"
        if not cti_path.is_file() or not vcd_path.is_file():
            entry["reason"] = "select succeeded but cti/cti.vcd is missing; not a CTI"
            ctis.append(entry)
            continue
        parsed_cti = parse_cti_file(_read_optional(cti_path))
        parsed_vcd = parse_vcd(_read_optional(vcd_path))
        entry["cti"] = parsed_cti
        entry["vcd"] = parsed_vcd
        if parsed_cti["status"] == "sat" and parsed_cti["state_frames"]:
            entry["status"] = "cti"
            entry["reason"] = "cill emitted a satisfiable CTI state sequence"
        else:
            entry["status"] = "unknown"
            entry["reason"] = f"CTI artifact status is {parsed_cti['status']!r}; not a usable CTI"
        ctis.append(entry)

    if any(entry["status"] == "cti" for entry in ctis):
        status = "cti"
    elif bmc == "clean" and all(p.get("result") == "inductive" for p in properties):
        status = "no_cti"
    else:
        status = "unknown"
    diag = _base(status)
    diag["ctis"] = ctis
    diag["selected_property_index"] = property_index
    diag["timeout_s"] = budget
    if SCHEMA_PATH.is_file():
        jsonschema.Draft202012Validator(read_json(SCHEMA_PATH)).validate(diag)
    freeze_json(run_dir / "diagnostics.json", diag)
    return diag
