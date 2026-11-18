"""Build the cross-case smoke/benchmark summary from PCD run records.

The CSV is intentionally small and stable.  The Markdown report keeps the
methodology, per-attempt detail, and an optional CIll comparison out of the
machine-readable table.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .core import PcdError, load_case, read_json

CSV_COLUMNS = [
    "case",
    "verdict",
    "time_s",
    "tried",
    "engine_s",
    "engine_over_total",
    "inv",
    "engine_included",
    "tcb",
]


def _display_case(case_id: str) -> str:
    name = case_id[len("smoke_") :] if case_id.startswith("smoke_") else case_id
    if "_" in name:
        family, rest = name.split("_", 1)
        return f"{family}/{rest}"
    return name


def _suite_cases(suite: str | None, base: Path) -> list[tuple[str, str]]:
    if suite:
        path = Path(suite).expanduser()
        doc = read_json(path)
        refs = doc.get("cases")
        if not isinstance(refs, list) or not refs:
            raise PcdError(f"{path}: suite has no non-empty 'cases' list")
        labels = doc.get("labels") if isinstance(doc.get("labels"), dict) else {}
        out: list[tuple[str, str]] = []
        for ref in refs:
            _, case = load_case(ref)
            case_id = case["case"]
            label = labels.get(ref) or labels.get(case_id) or _display_case(case_id)
            out.append((case_id, str(label)))
        return out
    if not base.is_dir():
        raise PcdError(f"runs directory does not exist: {base}")
    out = []
    for child in sorted(base.iterdir(), key=lambda p: p.name):
        if child.is_dir() and any(
            (p / "report.json").is_file() or (p / "run.json").is_file()
            for p in child.iterdir()
            if p.is_dir()
        ):
            out.append((child.name, _display_case(child.name)))
    return out


def _run_record(run_dir: Path) -> dict[str, Any]:
    report_path = run_dir / "report.json"
    run_path = run_dir / "run.json"
    if not report_path.is_file() and not run_path.is_file():
        raise PcdError(f"missing report.json and run.json: {run_dir}")
    report = read_json(report_path) if report_path.is_file() else {}
    run = read_json(run_path) if run_path.is_file() else {}
    timing = report.get("timing") or {}
    wall = timing.get("wall_seconds")
    if wall is None:
        wall = run.get("wall_seconds", 0.0)
    engine = timing.get("engine_seconds")
    if engine is None:
        engine = 0.0
    engine_runs = timing.get("engine_runs")
    if engine_runs is None:
        engine_runs = len({str(c.get("log")) for c in report.get("engine_calls", [])})
    verdict = report.get("verdict")
    if not verdict:
        if report.get("accepted"):
            verdict = "ACCEPT"
        elif run.get("result") == "error":
            verdict = "ERROR"
        elif not report:
            verdict = "NO_REPORT"
        else:
            verdict = "REJECT"
    return {
        "run_id": run_dir.name,
        "run_dir": run_dir,
        "verdict": verdict,
        "wall_s": float(wall or 0.0),
        "engine_s": float(engine or 0.0),
        "engine_runs": int(engine_runs or 0),
        "inv": int(report.get("inv") or 0),
        "tcb": int(report.get("tcb_count") or 0),
        "engine_included": bool(report.get("engine_included", run.get("engine_included", False))),
        "engine_source": ",".join((timing.get("sources") or [])),
        "accepted": bool(report.get("accepted")),
        "errors": report.get("errors") or [],
    }


def _baseline(path: str | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    p = Path(path).expanduser()
    if not p.is_file():
        raise PcdError(f"baseline summary does not exist: {p}")
    with p.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    return {row.get("case", ""): row for row in rows}


def write_summary(
    *,
    runs_dir: str,
    output_csv: str,
    output_md: str | None = None,
    suite: str | None = None,
    baseline: str | None = None,
    conclusion: str | None = None,
) -> dict[str, Any]:
    base = Path(runs_dir).expanduser().resolve()
    cases = _suite_cases(suite, base)
    baseline_rows = _baseline(baseline)
    rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for case_id, label in cases:
        case_runs_dir = base / case_id
        run_dirs = (
            sorted(
                (
                    p
                    for p in case_runs_dir.iterdir()
                    if p.is_dir()
                    and ((p / "report.json").is_file() or (p / "run.json").is_file())
                ),
                key=lambda p: p.name,
            )
            if case_runs_dir.is_dir()
            else []
        )
        attempts = [_run_record(p) for p in run_dirs]
        final = attempts[-1] if attempts else None
        time_s = sum(a["wall_s"] for a in attempts)
        engine_s = sum(a["engine_s"] for a in attempts)
        tried = sum(a["engine_runs"] for a in attempts)
        ratio = engine_s / time_s if time_s > 0 else 0.0
        rows.append(
            {
                "case": label,
                "verdict": final["verdict"] if final else "NO_RUN",
                "time_s": f"{time_s:.2f}",
                "tried": str(tried),
                "engine_s": f"{engine_s:.2f}",
                "engine_over_total": f"{ratio:.3f}",
                "inv": str(final["inv"] if final else 0),
                "engine_included": "yes" if final and final["engine_included"] else "no",
                "tcb": str(final["tcb"] if final else 0),
            }
        )
        details.append({"case": label, "case_id": case_id, "attempts": attempts})

    out = Path(output_csv).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    md_path = Path(output_md).expanduser() if output_md else out.with_suffix(".md")
    _write_markdown(md_path, rows, details, baseline_rows, conclusion)
    return {"csv": str(out), "markdown": str(md_path), "rows": rows}


def _write_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    details: list[dict[str, Any]],
    baseline: dict[str, dict[str, str]],
    conclusion: str | None = None,
) -> None:
    lines: list[str] = []
    lines.append("# PCD smoke summary")
    lines.append("")
    lines.append("Fresh PCD end-to-end runs. The engine is run again for every attempt; prior")
    lines.append("case logs are not staged. The MUL row is a multi-model package assembled")
    lines.append("from fresh submodel runs; the builder still emits one primary model. Helper")
    lines.append("assertions are case inputs and are counted across the proof's models/sets.")
    lines.append("")
    lines.append("## Definitions")
    lines.append("")
    lines.append("- `verdict`: final PCD result (`ACCEPT`, `REJECT`, `TIMEOUT`, `ERROR`).")
    lines.append("- `time_s`: sum of recorded wall time over all attempts, including build, sketch, plan, engine, kernel, and report.")
    lines.append("- `tried`: distinct engine invocations over all attempts. A multi-set proof counts each cill/z3/structural invocation.")
    lines.append("- `engine_s`: sum of `bmc_time + ind_time` from each `cill/statistic.ron`; wall time is used and labeled when a statistic is missing. Sets may run concurrently, so a multi-model row can have `engine_s > time_s`.")
    lines.append("- `engine_over_total`: `engine_s / time_s`; values above 1 indicate concurrent engine sets.")
    lines.append("- `inv`: helper assertions bound across the final proof's models/sets (`h_*`/`p_*` or helper source files).")
    lines.append("- `engine_included`: whether the row includes a fresh engine run (`yes`) or is package-only (`no`).")
    lines.append("- `tcb`: distinct TCB dependencies reachable from the final root. Official `isa_model`/tool TCBs count; complete acceptance forbids design TCBs.")
    lines.append("")
    lines.append("## Table")
    lines.append("")
    lines.append("| case | verdict | time_s | tried | engine_s | engine_over_total | inv | engine_included | tcb |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|---:|")
    for row in rows:
        lines.append(
            f"| `{row['case']}` | {row['verdict']} | {row['time_s']} | {row['tried']} | "
            f"{row['engine_s']} | {row['engine_over_total']} | {row['inv']} | "
            f"{row['engine_included']} | {row['tcb']} |"
        )
    lines.append("")
    if baseline:
        lines.append("## CIll baseline comparison")
        lines.append("")
        lines.append("Baseline values are the prior 5-hour CIll evaluation. A negative delta means PCD")
        lines.append("used less wall time; a positive delta means it used more.")
        lines.append("")
        lines.append("| case | CIll verdict | CIll time_s | PCD verdict | PCD time_s | delta_s |")
        lines.append("|---|---|---:|---|---:|---:|")
        for row in rows:
            old = baseline.get(row["case"])
            if not old:
                continue
            try:
                old_time = float(old.get("time_s", "0"))
                new_time = float(row["time_s"])
                delta = new_time - old_time
                delta_text = f"{delta:+.2f}"
            except ValueError:
                delta_text = "n/a"
            lines.append(
                f"| `{row['case']}` | {old.get('verdict', '?')} | {old.get('time_s', '?')} | "
                f"{row['verdict']} | {row['time_s']} | {delta_text} |"
            )
        lines.append("")
    lines.append("## Per-attempt detail")
    lines.append("")
    for item in details:
        lines.append(f"### `{item['case']}`")
        lines.append("")
        if not item["attempts"]:
            lines.append("- no runs found")
            lines.append("")
            continue
        lines.append("| run | verdict | wall_s | engine_s | engine_runs | inv | tcb | engine source |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        for attempt in item["attempts"]:
            lines.append(
                f"| `{attempt['run_id']}` | {attempt['verdict']} | {attempt['wall_s']:.2f} | "
                f"{attempt['engine_s']:.2f} | {attempt['engine_runs']} | {attempt['inv']} | "
                f"{attempt['tcb']} | `{attempt['engine_source'] or '-'}` |"
            )
        lines.append("")
    if conclusion and conclusion.strip():
        lines.append("")
        lines.append(conclusion.strip())
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
