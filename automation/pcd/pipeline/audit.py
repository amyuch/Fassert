"""Blind-run and proposal-integrity audit.

The audit is deliberately filesystem-local to the staged run. It never walks a
prior-proof tree; it checks that no oracle path was staged, that the frozen
artifacts still hash to what the planner saw, and that blind
build/planner/engine commands actually went through the bwrap execution path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from common.pcd_util import sha256_file

from .core import (
    find_forbidden_status,
    iter_strings,
    load_frozen_json,
    read_json,
    write_json,
)

ORACLE_MARKERS = ("oracle/", "/oracle/")


def _scan_markers(obj: Any) -> list[str]:
    found: list[str] = []
    for text in iter_strings(obj):
        for marker in ORACLE_MARKERS:
            if marker in text:
                found.append(text[:240])
                break
    return sorted(set(found))


def _staged_oracle_paths(run_dir: Path) -> list[str]:
    root = run_dir / "case"
    found: list[str] = []
    if not root.is_dir():
        return found
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(run_dir).as_posix()
        parts = set(rel.split("/"))
        if "oracle" in parts:
            found.append(rel)
    return found


def _sandbox_ok(run_dir: Path, run_record: dict[str, Any], mode: str) -> bool:
    """Blind runs must have actually used the bwrap execution path."""
    if mode != "blind":
        return True
    build_path = run_dir / "build.json"
    if not build_path.is_file():
        return False
    build = read_json(build_path)
    command = build.get("command") or {}
    if not command.get("sandboxed"):
        return False
    discharge_path = run_dir / "discharge.json"
    if discharge_path.is_file():
        discharge = read_json(discharge_path)
        for call in discharge.get("engine_calls", []):
            if not call.get("sandboxed"):
                return False
    if run_record.get("planner_requested") == "llm":
        plan_log = run_dir / "logs" / "plan.log"
        if not plan_log.is_file() or "# sandbox: bwrap" not in plan_log.read_text(
            encoding="utf-8", errors="replace"
        ):
            return False
    return True


def _artifact_ok(run_dir: Path, artifact: Any) -> bool:
    if not isinstance(artifact, dict) or not artifact.get("exists", True):
        return True
    path = artifact.get("path")
    digest = artifact.get("sha256")
    if not path or not digest:
        return False
    target = run_dir / str(path)
    return target.is_file() and sha256_file(str(target)) == digest


def _diagnostics_context_ok(run_dir: Path, context: dict[str, Any], mode: str) -> bool:
    """A feedback iteration may consume diagnostics, but only as diagnostics."""
    entry = context.get("diagnostics")
    path = run_dir / "diagnostics-context.json"
    if entry is None:
        return not path.exists()
    if not isinstance(entry, dict):
        return False
    if entry.get("path") != "diagnostics-context.json" or not path.is_file():
        return False
    if sha256_file(str(path)) != entry.get("sha256"):
        return False
    try:
        doc = read_json(path)
    except Exception:  # noqa: BLE001
        return False
    if doc.get("evidence") != "DIAGNOSTIC" or doc.get("proof") is not False:
        return False
    if doc.get("status") not in {"cti", "no_cti", "cex", "unknown", "error"}:
        return False
    if mode == "blind":
        calls = doc.get("calls")
        if not isinstance(calls, list) or not calls:
            return False
        if any(not isinstance(call, dict) or not call.get("sandboxed") for call in calls):
            return False
    return True


def _diagnostics_ok(run_dir: Path, mode: str) -> bool:
    """Verify CTI diagnostics are diagnostic-only and, in blind mode, sandboxed."""
    path = run_dir / "diagnostics.json"
    if not path.is_file():
        return True
    try:
        diag, _ = load_frozen_json(path)
    except Exception:  # noqa: BLE001 - a changed diagnostic fails the audit
        return False
    if diag.get("evidence") != "DIAGNOSTIC" or diag.get("proof") is not False:
        return False
    if diag.get("status") not in {"cti", "no_cti", "cex", "unknown", "error"}:
        return False
    if mode == "blind":
        calls = diag.get("calls")
        if not isinstance(calls, list) or not calls:
            return False
        if any(not isinstance(call, dict) or not call.get("sandboxed") for call in calls):
            return False
    if not _artifact_ok(run_dir, diag.get("artifacts", {}).get("check_log")):
        return False
    for cti in diag.get("ctis", []):
        if not isinstance(cti, dict):
            return False
        for artifact in (cti.get("artifacts") or {}).values():
            if not _artifact_ok(run_dir, artifact):
                return False
        if cti.get("status") == "cti":
            if not isinstance(cti.get("cti"), dict) or not isinstance(cti.get("vcd"), dict):
                return False
            if not (cti.get("cti") or {}).get("state_frames"):
                return False
    return True


def run_audit(run_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir)
    context, context_sha = load_frozen_json(run_dir / "context.json")
    proposals, proposal_sha = load_frozen_json(run_dir / "proposals.json")
    proof_path = run_dir / "proof.json"
    proof = read_json(proof_path) if proof_path.is_file() else None

    marker_hits = _scan_markers(context) + _scan_markers(proposals)
    staged_oracles = _staged_oracle_paths(run_dir)
    forbidden = find_forbidden_status(proposals)

    run_path = run_dir / "run.json"
    run_record = read_json(run_path) if run_path.is_file() else {}
    recorded_context = (run_record.get("context") or {}).get("sha256")
    recorded_proposals = (run_record.get("proposals") or {}).get("sha256")
    proposal_context = proposals.get("planner", {}).get("context_sha256")
    context_bound = proposal_context == context_sha
    if recorded_context is not None:
        context_bound = context_bound and recorded_context == context_sha
    proof_bound = True
    planner_bound = True
    if proof is not None:
        metadata = proof.get("metadata", {})
        proof_bound = metadata.get("proposal_sha256") == proposal_sha
        if recorded_proposals is not None:
            proof_bound = proof_bound and recorded_proposals == proposal_sha
        mode_ok = metadata.get("run_mode") == case["run_policy"]["mode"]
        expected_planner = case["run_policy"].get("planner")
        actual_planner = (metadata.get("planner") or {}).get("name")
        if expected_planner:
            planner_bound = actual_planner == expected_planner
    else:
        mode_ok = False

    leak_free = not marker_hits and not staged_oracles
    mode = case["run_policy"]["mode"]
    diagnostics_context_ok = _diagnostics_context_ok(run_dir, context, mode)
    frozen_ok = context_bound and proof_bound and diagnostics_context_ok
    completed = proof is not None and (run_dir / "check.json").is_file()
    sandbox_ok = _sandbox_ok(run_dir, run_record, mode)
    diagnostics_ok = _diagnostics_ok(run_dir, mode)
    blind_ok = (
        leak_free
        and frozen_ok
        and planner_bound
        and sandbox_ok
        and diagnostics_ok
        and not forbidden
        and (proof is None or mode_ok)
    )
    counts_as_result = bool(mode == "blind" and blind_ok and completed)
    audit = {
        "schema_version": "pcd-audit/0.1",
        "case": case["case"],
        "run_id": run_dir.name,
        "mode": mode,
        "context_sha256": context_sha,
        "proposal_sha256": proposal_sha,
        "context_bound": context_bound,
        "proof_bound": proof_bound,
        "planner_bound": planner_bound,
        "mode_recorded": mode_ok,
        "marker_hits": marker_hits,
        "staged_oracle_paths": staged_oracles,
        "forbidden_proposal_fields": forbidden,
        "leak_free": leak_free,
        "frozen_ok": frozen_ok,
        "diagnostics_context_ok": diagnostics_context_ok,
        "sandbox_ok": sandbox_ok,
        "diagnostics_ok": diagnostics_ok,
        "completed": completed,
        "blind_ok": blind_ok,
        "counts_as_planner_result": counts_as_result,
        "result": "pass" if blind_ok and completed else ("incomplete" if blind_ok else "fail"),
    }
    write_json(run_dir / "audit.json", audit)
    return audit
