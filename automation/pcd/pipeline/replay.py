"""Clean re-build and replay of a frozen run.

Replay never re-plans. It stages the same legitimate inputs, rebuilds the model,
checks that the model/context identities are unchanged, re-runs the frozen
proposals, and compares the kernel result with the original run.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from .audit import run_audit
from .build import load_build, run_build
from .core import PcdError, canonical_hash, freeze_json, load_case, new_run_dir, read_json, write_json
from .discharge import run_discharge
from .plan import load_proposals
from .report import run_report
from .sketch import load_context, run_sketch
from .verify import run_check


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def run_replay(
    case_ref: str,
    old_run: str | Path,
    *,
    runs_dir: str | None = None,
) -> tuple[dict[str, Any], Path]:
    old_dir = Path(old_run).expanduser().resolve()
    if not (old_dir / "context.json").is_file() or not (old_dir / "proposals.json").is_file():
        raise PcdError(f"{old_dir}: not a completed run with context and proposals")
    old_context, old_context_sha = load_context(old_dir)
    old_proposals, proposal_sha = load_proposals(old_dir)
    old_build = read_json(old_dir / "build.json")
    old_check = read_json(old_dir / "check.json") if (old_dir / "check.json").is_file() else None
    if not old_check:
        raise PcdError(f"{old_dir}: no kernel check to replay")
    old_model = (old_build.get("model") or {}).get("id")
    if not old_model:
        raise PcdError(f"{old_dir}: original run has no model identity")

    case_dir, case = load_case(case_ref)
    # A run-local budget override is part of the context that the planner saw.
    if old_context["case"].get("budgets"):
        case["budgets"] = old_context["case"]["budgets"]
    run_dir = new_run_dir(case["case"], runs_dir)
    run: dict[str, Any] = {
        "schema_version": "pcd-run/0.1",
        "run_id": run_dir.name,
        "case": case["case"],
        "mode": case["run_policy"]["mode"],
        "planner_requested": "replay",
        "replay_of": old_dir.as_posix(),
        "started_utc": _utc(),
        "artifacts": {},
        "stage": {"case": "case"},
    }
    write_json(run_dir / "run.json", run)
    try:
        build = run_build(run_dir, case_dir, case)
        run["build"] = {"path": "build.json", "model": build.get("model"), "ok": True}
        run["artifacts"]["build"] = "build.json"
        new_model = (build.get("model") or {}).get("id")
        if new_model != old_model:
            raise PcdError(f"replay model changed: expected {old_model}, got {new_model}")
        if build.get("stage_sha256") != old_build.get("stage_sha256"):
            raise PcdError("replay stage changed: input/build hashes differ from the original run")
        if build.get("case_file_sha256") != old_build.get("case_file_sha256"):
            raise PcdError("replay case file changed since the original run")
        diagnostic_source = old_dir / "diagnostics-context.json"
        context = run_sketch(
            run_dir,
            case,
            build,
            diagnostics_path=diagnostic_source if diagnostic_source.is_file() else None,
        )
        context_sha = canonical_hash(context)
        if context.get("diagnostics"):
            run["diagnostics_context"] = context["diagnostics"]
            run["artifacts"]["diagnostics_context"] = "diagnostics-context.json"
        if context_sha != old_context_sha:
            raise PcdError(
                f"replay context changed: expected {old_context_sha}, got {context_sha}; "
                "the staged inputs or tool versions are not identical"
            )
        run["context"] = {"path": "context.json", "sha256": context_sha}
        run["artifacts"]["context"] = "context.json"
        write_json(run_dir / "run.json", run)
        # Re-freeze the exact proposal object in the new run.
        freeze_json(run_dir / "proposals.json", old_proposals)
        run["proposals"] = {"path": "proposals.json", "sha256": proposal_sha}
        run["artifacts"]["proposals"] = "proposals.json"
        write_json(run_dir / "run.json", run)
        run_discharge(run_dir, case, build=build, proposals=old_proposals)
        check = run_check(run_dir, case)
        audit = run_audit(run_dir, case)
        report = run_report(run_dir, case)
        replay_ok = bool(
            check.get("accepted") == old_check.get("accepted")
            and check.get("targets", {}) == old_check.get("targets", {})
            and audit.get("blind_ok")
        )
        replay = {
            "schema_version": "pcd-replay/0.1",
            "case": case["case"],
            "old_run": old_dir.as_posix(),
            "new_run": run_dir.as_posix(),
            "model": new_model,
            "context_sha256": context_sha,
            "proposal_sha256": proposal_sha,
            "old_accepted": old_check.get("accepted"),
            "new_accepted": check.get("accepted"),
            "old_targets": old_check.get("targets", {}),
            "new_targets": check.get("targets", {}),
            "audit": audit.get("result"),
            "replay_ok": replay_ok,
        }
        write_json(run_dir / "replay.json", replay)
        run["artifacts"] = {
            "build": "build.json",
            "context": "context.json",
            "proposals": "proposals.json",
            "proof": "proof.json",
            "check": "check.json",
            "audit": "audit.json",
            "report": "report.md",
            "replay": "replay.json",
        }
        if run.get("diagnostics_context"):
            run["artifacts"]["diagnostics_context"] = "diagnostics-context.json"
        run["check"] = {"accepted": check.get("accepted"), "targets": check.get("targets", {})}
        run["audit"] = {"result": audit.get("result"), "blind_ok": audit.get("blind_ok")}
        run["replay_ok"] = replay_ok
        run["result"] = "replay_ok" if replay_ok else "replay_mismatch"
        run["finished_utc"] = _utc()
        write_json(run_dir / "run.json", run)
        return run, run_dir
    except Exception as exc:  # noqa: BLE001
        run["result"] = "error"
        run["error"] = f"{exc.__class__.__name__}: {exc}"
        run["finished_utc"] = _utc()
        write_json(run_dir / "run.json", run)
        return run, run_dir
