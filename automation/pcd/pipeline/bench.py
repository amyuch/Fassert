"""Generic suite runner.

A suite is data: a JSON file (or a comma-separated case list) naming cases and
run options. The runner has no case-specific branches; it calls the same
`run_e2e` path for every case and records the results together.
"""
from __future__ import annotations

import datetime as _dt
import secrets
from pathlib import Path
from typing import Any

from .core import PcdError, DEFAULT_RUNS_DIR, load_case, read_json, write_json
from .e2e import run_e2e
from kernel import kernel


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _parse_suite(suite: str) -> dict[str, Any]:
    p = Path(suite).expanduser()
    if p.is_file():
        doc = read_json(p)
        if "cases" not in doc or not isinstance(doc["cases"], list) or not doc["cases"]:
            raise PcdError(f"{p}: suite must contain a non-empty 'cases' list")
        return doc
    if p.is_dir():
        candidate = p / "suite.json"
        if candidate.is_file():
            return _parse_suite(str(candidate))
        raise PcdError(f"{p}: suite directory has no suite.json")
    if "," in suite:
        return {"cases": [x.strip() for x in suite.split(",") if x.strip()]}
    # A single case name is a valid one-case suite.
    return {"cases": [suite]}


def _suite_base(suite: str) -> Path:
    p = Path(suite).expanduser()
    if p.is_file():
        return p.resolve().parent
    if p.is_dir():
        return p.resolve()
    return Path.cwd().resolve()


def _resolve_package(ref: str, base: Path) -> Path:
    """Resolve a package path relative to the suite, the PCD root, or cwd."""
    p = Path(ref).expanduser()
    if p.is_absolute():
        return p.resolve()
    roots = [base, Path(__file__).resolve().parents[1], Path.cwd().resolve()]
    for root in roots:
        candidate = (root / p).resolve()
        if candidate.is_dir():
            return candidate
    return (base / p).resolve()


def _package_provenance(official: dict[str, Any], package: dict[str, Any]) -> list[str]:
    """Check that the package keeps the official spec, checker, and CPU sources.

    Harness and define files are intentionally extensible: helper assertions
    live there.  The instruction model, RVFI checker, and picorv32 core must be
    byte-identical to the imported official case.
    """
    problems: list[str] = []
    if package.get("acceptance") != "complete":
        problems.append(f"package acceptance is {package.get('acceptance')!r}, expected 'complete'")
    available: dict[str, set[str]] = {}
    for item in (package.get("inputs") or {}).get("files", []):
        available.setdefault(Path(item["path"]).name, set()).add(item["sha256"])
    for item in (official.get("inputs") or {}).get("files", []):
        if item.get("role") not in {"spec", "checker", "rtl"}:
            continue
        name = Path(item["path"]).name
        if item["sha256"] not in available.get(name, set()):
            problems.append(
                f"official {item.get('role')} source {name} ({item['sha256'][:12]}) "
                "is not present byte-identically in the package"
            )
    return problems


def run_bench(
    suite: str,
    *,
    planner: str | None = None,
    engine_seconds: int | None = None,
    runs_dir: str | None = None,
    manual_path: str | None = None,
    llm_command: str | None = None,
    decomposition_path: str | None = None,
) -> tuple[dict[str, Any], Path]:
    spec = _parse_suite(suite)
    planner_name = planner or spec.get("planner") or "template"
    proof_packages = spec.get("proof_packages") or {}
    if not isinstance(proof_packages, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in proof_packages.items()
    ):
        raise PcdError("suite 'proof_packages' must be an object mapping case names to package paths")
    provenance_policy = spec.get("provenance", "official")
    if provenance_policy not in {"official", "none"}:
        raise PcdError("suite 'provenance' must be 'official' or 'none'")
    suite_base = _suite_base(suite)
    seconds = engine_seconds if engine_seconds is not None else spec.get("engine_seconds")
    if seconds is not None:
        try:
            seconds = int(seconds)
        except (TypeError, ValueError) as exc:
            raise PcdError(f"engine_seconds must be an integer, got {seconds!r}") from exc
        if seconds < 1:
            raise PcdError("engine_seconds must be positive")
    base = Path(runs_dir).expanduser().resolve() if runs_dir else DEFAULT_RUNS_DIR
    bench_dir = base / "_bench"
    bench_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bench_id = f"{stamp}-{secrets.token_hex(3)}"
    result_path = bench_dir / f"{bench_id}.json"
    started = _utc()
    rows: list[dict[str, Any]] = []
    for case_ref in spec["cases"]:
        try:
            _, case = load_case(case_ref)
        except Exception as exc:  # noqa: BLE001
            rows.append({"case": str(case_ref), "result": "error", "error": f"{exc.__class__.__name__}: {exc}"})
            continue
        package_ref = proof_packages.get(case_ref)
        if package_ref:
            try:
                package_dir = _resolve_package(package_ref, suite_base)
                _, package_case = load_case(package_dir)
                problems = _package_provenance(case, package_case) if provenance_policy == "official" else []
                if problems:
                    rows.append(
                        {
                            "case": case["case"],
                            "suite_case": case_ref,
                            "package": str(package_dir),
                            "package_case": package_case.get("case"),
                            "result": "REJECT",
                            "accepted": False,
                            "model": None,
                            "audit": None,
                            "counts_as_planner_result": False,
                            "error": "; ".join(problems),
                        }
                    )
                    continue
                # Keep historical package checks immutable. Current validation
                # belongs to this benchmark invocation, beside its result.
                checked = kernel.check_paths(str(package_dir / "case.json"), str(package_dir / "proof.json"))
                check = checked.as_dict()
                check_path = bench_dir / f"{bench_id}-{len(rows)}.check.json"
                write_json(check_path, check)
                proof = read_json(package_dir / "proof.json")
                rows.append(
                    {
                        "case": case["case"],
                        "suite_case": case_ref,
                        "package": str(package_dir),
                        "package_case": package_case.get("case"),
                        "check": str(check_path),
                        "result": "ACCEPT" if check.get("accepted") else "REJECT",
                        "accepted": bool(check.get("accepted")),
                        "status": check.get("status"),
                        "residual": check.get("residual", []),
                        "model": proof.get("primary_model"),
                        "audit": None,
                        "counts_as_planner_result": False,
                        "error": None,
                        "errors": check.get("errors", []),
                        "warnings": check.get("warnings", []),
                        "targets": check.get("targets", {}),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "case": case.get("case", str(case_ref)),
                        "suite_case": case_ref,
                        "package": str(package_ref),
                        "result": "error",
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
            continue
        run, run_dir = run_e2e(
            case_ref,
            planner=planner_name,
            manual_path=manual_path,
            llm_command=llm_command,
            decomposition_path=decomposition_path,
            runs_dir=str(base),
            engine_seconds=int(seconds) if seconds is not None else None,
        )
        rows.append(
            {
                "case": case["case"],
                "run_dir": str(run_dir),
                "result": run.get("result"),
                "accepted": bool((run.get("check") or {}).get("accepted")),
                "status": (run.get("check") or {}).get("status"),
                "residual": (run.get("check") or {}).get("residual", []),
                "model": ((run.get("build") or {}).get("model") or {}).get("id"),
                "audit": (run.get("audit") or {}).get("result"),
                "counts_as_planner_result": run.get("counts_as_planner_result", False),
                "error": run.get("error"),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.get("result", "unknown")] = counts.get(row.get("result", "unknown"), 0) + 1
    bench = {
        "schema_version": "pcd-bench/0.1",
        "bench_id": bench_id,
        "suite": suite,
        "planner": planner_name,
        "engine_seconds": int(seconds) if seconds is not None else None,
        "started_utc": started,
        "finished_utc": _utc(),
        "cases": rows,
        "counts": counts,
        "all_accepted": all(row.get("accepted") for row in rows) if rows else False,
    }
    write_json(result_path, bench)
    return bench, result_path
