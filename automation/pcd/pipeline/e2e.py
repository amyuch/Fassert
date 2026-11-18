"""End-to-end orchestration: build -> sketch -> plan -> discharge -> check -> report."""
from __future__ import annotations

import datetime as _dt
import shutil
import time
from pathlib import Path
from typing import Any

from .audit import run_audit
from .backends import normalize_engines
from .build import run_build
from .core import (
    PcdError,
    canonical_hash,
    load_case,
    new_run_dir,
    read_json,
    sha256_file,
    write_json,
    write_text,
)
from .cti import run_cti_diagnosis
from .discharge import run_discharge
from .plan import run_plan
from .report import run_report
from .sketch import run_sketch
from .verify import run_check


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def run_e2e(
    case_ref: str,
    *,
    planner: str,
    manual_path: str | None = None,
    llm_command: str | None = None,
    decomposition_path: str | None = None,
    runs_dir: str | None = None,
    allow_missing_artifacts: bool = False,
    engine_seconds: int | None = None,
    engines: dict[str, Any] | None = None,
    cti: bool = False,
    cti_property: int | None = None,
    cti_timeout_s: int | None = None,
    diagnostics_context: str | None = None,
) -> tuple[dict[str, Any], Path]:
    case_dir, case = load_case(case_ref)
    declared_planner = case.get("run_policy", {}).get("planner")
    if declared_planner and planner != declared_planner:
        raise PcdError(
            f"planner {planner!r} does not match the case's declared planner "
            f"{declared_planner!r}; update run_policy.planner for this attempt"
        )
    engine_catalog = normalize_engines(engines)
    if engine_seconds is not None:
        if engine_seconds < 1:
            raise PcdError("--engine-seconds must be positive")
        case["budgets"].setdefault("engine_seconds", {})["ric3"] = int(engine_seconds)
    run_dir = new_run_dir(case["case"], runs_dir)
    started_monotonic = time.monotonic()
    run: dict[str, Any] = {
        "schema_version": "pcd-run/0.1",
        "run_id": run_dir.name,
        "case": case["case"],
        "mode": case["run_policy"]["mode"],
        "planner_requested": planner,
        "started_utc": _utc(),
        "artifacts": {},
        "stage": {"case": "case"},
    }
    if cti:
        run["cti_requested"] = {
            "property_index": cti_property,
            "timeout_s": cti_timeout_s,
        }
    if diagnostics_context is not None:
        run["diagnostics_context_requested"] = str(diagnostics_context)
    if decomposition_path is not None:
        decomposition_source = Path(decomposition_path)
        if not decomposition_source.is_file():
            raise PcdError(f"decomposition manifest not found: {decomposition_path}")
        decomposition_dest = run_dir / "decomposition.json"
        shutil.copy2(decomposition_source, decomposition_dest)
        run["decomposition"] = {
            "path": "decomposition.json",
            "sha256": sha256_file(str(decomposition_dest)),
        }
        run.setdefault("artifacts", {})["decomposition"] = "decomposition.json"
    if engine_seconds is not None:
        run["budget_override"] = {"engine_seconds.ric3": int(engine_seconds)}
    write_json(run_dir / "run.json", run)
    try:
        build = run_build(run_dir, case_dir, case)
        run["build"] = {"path": "build.json", "model": build.get("model"), "ok": True}
        run["artifacts"]["build"] = "build.json"

        context = run_sketch(
            run_dir,
            case,
            build,
            engines=engine_catalog,
            diagnostics_path=diagnostics_context,
        )
        context_sha = canonical_hash(context)
        run["context"] = {"path": "context.json", "sha256": context_sha}
        run["artifacts"]["context"] = "context.json"
        if context.get("diagnostics"):
            run["diagnostics_context"] = context["diagnostics"]
            run["artifacts"]["diagnostics_context"] = "diagnostics-context.json"
        write_json(run_dir / "run.json", run)

        proposals = run_plan(
            run_dir,
            case,
            planner=planner,
            manual_path=manual_path,
            llm_command=llm_command,
            decomposition_path=decomposition_path,
        )
        proposal_sha = canonical_hash(proposals)
        run["proposals"] = {"path": "proposals.json", "sha256": proposal_sha}
        run["artifacts"]["proposals"] = "proposals.json"
        write_json(run_dir / "run.json", run)

        run_discharge(run_dir, case, build=build, proposals=proposals, engines=engine_catalog)
        run["artifacts"]["proof"] = "proof.json"
        run["artifacts"]["discharge"] = "discharge.json"
        run["engine_included"] = bool(read_json(run_dir / "discharge.json").get("engine_calls"))

        check = run_check(run_dir, case, allow_missing_artifacts=allow_missing_artifacts)
        run["check"] = {
            "path": "check.json",
            "accepted": check["accepted"],
            "targets": check.get("targets", {}),
            "errors": len(check.get("errors", [])),
            "warnings": len(check.get("warnings", [])),
        }
        run["artifacts"]["check"] = "check.json"

        if cti:
            diagnostics = run_cti_diagnosis(
                run_dir,
                case,
                build=build,
                context=context,
                property_index=cti_property,
                timeout_s=cti_timeout_s,
            )
            run["diagnostics"] = {
                "path": "diagnostics.json",
                "sha256": canonical_hash(diagnostics),
                "status": diagnostics.get("status"),
                "ctis": len(diagnostics.get("ctis", [])),
            }
            run["artifacts"]["diagnostics"] = "diagnostics.json"
            write_json(run_dir / "run.json", run)

        audit = run_audit(run_dir, case)
        run["audit"] = {
            "path": "audit.json",
            "result": audit.get("result"),
            "blind_ok": audit.get("blind_ok"),
            "counts_as_planner_result": audit.get("counts_as_planner_result"),
        }
        run["artifacts"]["audit"] = "audit.json"

        # Reports need the checker-only work too; an engine-free proof must
        # neither claim a hardware-engine call nor report zero pipeline time.
        run["wall_seconds"] = round(time.monotonic() - started_monotonic, 3)
        write_json(run_dir / "run.json", run)
        report = run_report(run_dir, case)
        run["artifacts"]["report"] = "report.md"
        if case["run_policy"]["mode"] == "blind" and not audit.get("blind_ok"):
            result = "invalid"
        elif check["accepted"]:
            result = "accepted"
        else:
            result = "rejected"
        run["result"] = result
        run["counts_as_planner_result"] = bool(audit.get("counts_as_planner_result"))
        run["wall_seconds"] = round(time.monotonic() - started_monotonic, 3)
        run["finished_utc"] = _utc()
        write_json(run_dir / "run.json", run)
        return run, run_dir
    except Exception as exc:  # noqa: BLE001 - record, then fail closed at the CLI
        run["result"] = "error"
        run["error"] = f"{exc.__class__.__name__}: {exc}"
        run.setdefault("engine_included", False)
        run["wall_seconds"] = round(time.monotonic() - started_monotonic, 3)
        run["finished_utc"] = _utc()
        write_json(run_dir / "run.json", run)
        write_text(
            run_dir / "report.md",
            f"# PCD run `{run_dir.name}`\n\n"
            f"- case: `{case['case']}`\n"
            f"- mode: `{case['run_policy']['mode']}`\n"
            f"- result: **error**\n"
            f"- error: `{run['error']}`\n",
        )
        return run, run_dir
