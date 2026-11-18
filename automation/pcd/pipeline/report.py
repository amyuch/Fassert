"""Render the run matrix from kernel results and recorded engine calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import PcdError, read_json, write_json, write_text


def _load_optional(path: Path) -> dict[str, Any] | None:
    return read_json(path) if path.is_file() else None


def run_report(run_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir)
    check_path = run_dir / "check.json"
    if not check_path.is_file():
        raise PcdError(f"missing kernel check: {check_path}")
    check = read_json(check_path)
    proof = _load_optional(run_dir / "proof.json") or {}
    discharge = _load_optional(run_dir / "discharge.json") or {}
    audit = _load_optional(run_dir / "audit.json")
    diagnostics = _load_optional(run_dir / "diagnostics.json")
    build = _load_optional(run_dir / "build.json") or {}
    run_record = _load_optional(run_dir / "run.json") or {}
    context = _load_optional(run_dir / "context.json") or {}

    nodes = {n["id"]: n for n in proof.get("nodes", [])}
    official_tcb_kinds = {"frontend", "engine", "checker", "isa_model"}
    open_items: list[dict[str, Any]] = []
    for node in nodes.values():
        cert = node.get("certificate", {})
        verdict = cert.get("verdict")
        if cert.get("evidence") == "REPLAY" and verdict != "proved":
            open_items.append({"node": node["id"], "reason": f"replay verdict: {verdict}"})
        if cert.get("evidence") == "TCB" and cert.get("kind") not in official_tcb_kinds:
            open_items.append({"node": node["id"], "reason": "declared design TCB"})

    cuts = [
        {"node": n["id"], "boundary": n["cut"].get("boundary")}
        for n in nodes.values()
        if n.get("cut")
    ]
    helpers = [
        {"node": n["id"], "kind": n["helper"].get("kind")}
        for n in nodes.values()
        if n.get("helper")
    ]
    sets = proof.get("metadata", {}).get("sets", [])
    if not isinstance(sets, list):
        sets = []

    targets = check.get("targets", {})
    rows = []
    for tid in sorted(targets):
        t = targets[tid]
        rows.append(
            {
                "target": tid,
                "leaf_evidence": t.get("evidence"),
                "composition": t.get("composition"),
                "tcb": t.get("tcb", []),
                "open": [o["node"] for o in open_items],
            }
        )

    engine_calls = discharge.get("engine_calls", [])
    unique_calls: dict[str, dict[str, Any]] = {}
    for call in engine_calls:
        key = str(call.get("log") or call.get("id"))
        previous = unique_calls.get(key)
        if previous is None or float(call.get("seconds", 0)) >= float(previous.get("seconds", 0)):
            unique_calls[key] = call
    engine_runs = list(unique_calls.values())
    bridge_solver_seconds = sum(
        float(query.get("seconds", 0))
        for edge in check.get("composition", {}).get("checked_edges", {}).values()
        for group in ("checks", "discharged_constraints")
        for query in edge.get(group, {}).values()
    )
    engine_wall_seconds = round(
        sum(float(c.get("engine_wall_seconds", c.get("seconds", 0))) for c in engine_runs), 6
    )
    engine_seconds = round(
        sum(float(c.get("engine_seconds", c.get("seconds", 0))) for c in engine_runs), 6
    )
    bmc_values = [c.get("bmc_seconds") for c in engine_runs]
    ind_values = [c.get("ind_seconds") for c in engine_runs]
    bmc_seconds = (
        round(sum(float(v) for v in bmc_values), 6)
        if bmc_values and all(v is not None for v in bmc_values)
        else None
    )
    ind_seconds = (
        round(sum(float(v) for v in ind_values), 6)
        if ind_values and all(v is not None for v in ind_values)
        else None
    )
    wall_seconds = run_record.get("wall_seconds")
    if wall_seconds is None:
        try:
            from datetime import datetime

            started = datetime.fromisoformat(str(run_record["started_utc"]))
            finished = datetime.fromisoformat(str(run_record["finished_utc"]))
            wall_seconds = round((finished - started).total_seconds(), 3)
        except Exception:  # noqa: BLE001 - old runs may not have both stamps
            wall_seconds = engine_wall_seconds
    wall_seconds = float(wall_seconds)
    engine_over_total = round(engine_seconds / wall_seconds, 4) if wall_seconds > 0 else None

    tcb_nodes = sorted(
        {
            str(node)
            for target in targets.values()
            for key in ("tcb", "tcb_deps")
            for node in target.get(key, [])
        }
    )
    properties = (context.get("model") or {}).get("properties", [])
    helper_properties = [
        p
        for p in properties
        if str(p.get("name", "")).startswith(("h_", "p_"))
        or "helper" in Path(str(p.get("assertion_file") or "")).name.lower()
    ]
    timed_out = any(bool(c.get("timed_out")) for c in engine_calls)
    if check.get("accepted"):
        verdict = "ACCEPT"
    elif timed_out:
        verdict = "TIMEOUT"
    elif run_record.get("result") == "error":
        verdict = "ERROR"
    else:
        verdict = "REJECT"

    report = {
        "schema_version": "pcd-report/0.1",
        "case": case["case"],
        "run_id": run_dir.name,
        "mode": case["run_policy"]["mode"],
        "planner": proof.get("metadata", {}).get("planner", {}),
        "model": build.get("model"),
        "accepted": check.get("accepted", False),
        "composition_guard": check.get("composition", {}),
        "verdict": verdict,
        "errors": check.get("errors", []),
        "warnings": check.get("warnings", []),
        "targets": rows,
        "open_items": open_items,
        "cuts": cuts,
        "helpers": helpers,
        "sets": sets,
        "inv": len(helper_properties),
        "tcb_nodes": tcb_nodes,
        "tcb_count": len(tcb_nodes),
        "engine_calls": engine_calls,
        "engine_included": bool(run_record.get("engine_included", bool(engine_runs))),
        "timing": {
            "bridge_solver_seconds": round(bridge_solver_seconds, 6),
            "wall_seconds": round(wall_seconds, 3),
            "engine_wall_seconds": engine_wall_seconds,
            "engine_seconds": engine_seconds,
            "bmc_seconds": bmc_seconds,
            "ind_seconds": ind_seconds,
            "engine_over_total": engine_over_total,
            "engine_runs": len(engine_runs),
            "engine_obligations": len(engine_calls),
            "sources": sorted({str(c.get("timing_source")) for c in engine_runs}),
        },
        "diagnostics": diagnostics,
        "diagnostics_context": run_record.get("diagnostics_context"),
        "audit": audit,
        "counts_as_planner_result": bool(audit and audit.get("counts_as_planner_result")),
    }
    write_json(run_dir / "report.json", report)

    lines: list[str] = []
    lines.append(f"# PCD run `{run_dir.name}`")
    lines.append("")
    lines.append(f"- case: `{case['case']}`")
    lines.append(f"- mode: `{case['run_policy']['mode']}`")
    planner = report.get("planner") or {}
    if not isinstance(planner, dict):
        planner = {"name": str(planner), "version": "?"}
    lines.append(f"- planner: `{planner.get('name', '?')}` ({planner.get('version', '?')})")
    model = report.get("model") or {}
    lines.append(f"- model: `{model.get('id', '?')}`")
    lines.append(f"- kernel: **{'ACCEPT' if report['accepted'] else 'REJECT'}**")
    lines.append(f"- composition guard: `{report['composition_guard'].get('status', 'not_recorded')}`")
    lines.append(f"- verdict: **{report['verdict']}**")
    timing = report["timing"]
    lines.append(
        f"- wall: `{timing['wall_seconds']} s`  engine: `{timing['engine_seconds']} s`  "
        f"engine/total: `{timing['engine_over_total']}`"
    )
    lines.append(
        f"- helper assertions: `{report['inv']}`  TCB nodes: `{report['tcb_count']}`  "
        f"engine included: `{report['engine_included']}`"
    )
    lines.append(f"- counts as planner result: `{report['counts_as_planner_result']}`")
    if report.get("diagnostics_context"):
        dc = report["diagnostics_context"]
        lines.append(
            f"- diagnostic context: `{dc.get('status')}` from "
            f"`{dc.get('source_run')}` (sha `{dc.get('sha256', '?')[:12]}...`)"
        )
    lines.append("")
    lines.append("| target | leaf evidence | composition | TCB | open |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        tcb = ", ".join(row["tcb"]) if row["tcb"] else "-"
        opened = ", ".join(row["open"]) if row["open"] else "-"
        lines.append(
            f"| `{row['target']}` | `{row['leaf_evidence']}` | `{row['composition']}` | {tcb} | {opened} |"
        )
    lines.append("")
    lines.append("## Timing")
    lines.append("")
    lines.append("| wall (s) | engine wall (s) | engine (s) | BMC (s) | induction (s) | engine runs | engine obligations | source |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---|")
    lines.append(
        f"| {timing['wall_seconds']} | {timing['engine_wall_seconds']} | "
        f"{timing['engine_seconds']} | {timing['bmc_seconds']} | {timing['ind_seconds']} | "
        f"{timing['engine_runs']} | {timing['engine_obligations']} | "
        f"{', '.join(timing['sources']) or '-'} |"
    )
    lines.append("")
    if cuts or helpers:
        lines.append("## Cuts and helpers")
        lines.append("")
        for cut in cuts:
            lines.append(f"- cut `{cut['node']}`: `{cut['boundary']}`")
        for helper in helpers:
            lines.append(f"- helper `{helper['node']}`: `{helper['kind']}`")
        lines.append("")
    if sets:
        lines.append("## Proof sets")
        lines.append("")
        lines.append("| set | method | nodes | assumes |")
        lines.append("|---|---|---|---|")
        for item in sets:
            if not isinstance(item, dict):
                continue
            members = item.get("nodes") or [
                *(item.get("lemmas") or []),
                *(item.get("targets") or []),
            ]
            nodes_text = ", ".join(f"`{n}`" for n in members) or "-"
            assumes_text = ", ".join(f"`{n}`" for n in item.get("assumes", [])) or "-"
            lines.append(
                f"| `{item.get('id', '?')}` | `{item.get('method', '?')}` | "
                f"{nodes_text} | {assumes_text} |"
            )
        lines.append("")
    if report["errors"]:
        lines.append("## Kernel errors")
        lines.append("")
        for err in report["errors"]:
            node = f" ({err.get('node')})" if err.get("node") else ""
            lines.append(f"- **{err.get('rule')}**{node}: {err.get('message')}")
        lines.append("")
    if report["warnings"]:
        lines.append("## Kernel warnings")
        lines.append("")
        for warn in report["warnings"]:
            node = f" ({warn.get('node')})" if warn.get("node") else ""
            lines.append(f"- **{warn.get('rule')}**{node}: {warn.get('message')}")
        lines.append("")
    if audit is not None:
        lines.append("## Audit")
        lines.append("")
        lines.append(f"- blind/policy audit: **{audit.get('result')}**")
        lines.append(f"- leak-free: `{audit.get('leak_free')}`")
        lines.append(f"- context bound: `{audit.get('context_bound')}`")
        lines.append(f"- diagnostics context bound: `{audit.get('diagnostics_context_ok')}`")
        lines.append(f"- proof bound: `{audit.get('proof_bound')}`")
        lines.append(f"- counts as planner result: `{audit.get('counts_as_planner_result')}`")
        if audit.get("marker_hits"):
            lines.append(f"- marker hits: `{audit['marker_hits']}`")
        lines.append("")
    if report.get("diagnostics_context") and report["diagnostics_context"].get("ctis"):
        dc = report["diagnostics_context"]
        lines.append("## Bound diagnostic context")
        lines.append("")
        lines.append(
            f"- source run: `{dc.get('source_run')}`  status: `{dc.get('status')}`  "
            f"sha256: `{dc.get('sha256')}`"
        )
        lines.append("")
        lines.append("| property | index | CTI status | frames | state signals |")
        lines.append("|---|---|---|---|---|")
        for item in dc.get("ctis", []):
            lines.append(
                f"| `{item.get('property_name', '?')}` | {item.get('property_index')} | "
                f"`{item.get('status')}` | {item.get('state_frames')} | "
                f"{len(item.get('final', {}))} |"
            )
        lines.append("")
    if diagnostics is not None:
        lines.append("## CTI diagnostics")
        lines.append("")
        lines.append(f"- status: `{diagnostics.get('status')}`")
        lines.append("- diagnostic-only: `True` (CTIs are not proof premises)")
        if diagnostics.get("ctis"):
            lines.append("")
            lines.append("| property | index | CTI status | frames | state signals |")
            lines.append("|---|---|---|---|---|")
            for item in diagnostics.get("ctis", []):
                cti = item.get("cti") or {}
                vcd = item.get("vcd") or {}
                frames = len(cti.get("state_frames", []))
                signals = len(vcd.get("final", {}))
                lines.append(
                    f"| `{item.get('property_name', '?')}` | {item.get('property_index')} | "
                    f"`{item.get('status')}` | {frames} | {signals} |"
                )
        lines.append("")
    if report["engine_calls"]:
        lines.append("## Engine calls")
        lines.append("")
        lines.append("| node | backend | verdict | wall (s) | engine (s) | source | log |")
        lines.append("|---|---|---|---:|---:|---|---|")
        for call in report["engine_calls"]:
            backend = call.get("backend", "?")
            lines.append(
                f"| `{call.get('node')}` | `{backend}` | `{call.get('verdict')}` | "
                f"{call.get('seconds')} | {call.get('engine_seconds')} | "
                f"`{call.get('timing_source')}` | `{call.get('log')}` |"
            )
        lines.append("")
    write_text(run_dir / "report.md", "\n".join(lines) + "\n")
    return report
