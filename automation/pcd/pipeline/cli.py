#!/usr/bin/env python3
"""One-click CLI for the PCD workbench."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUTOMATION = ROOT.parent
for _p in (ROOT, AUTOMATION):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from kernel import kernel  # noqa: E402

from .audit import run_audit  # noqa: E402
from .build import load_build, run_build  # noqa: E402
from .core import (  # noqa: E402
    DEFAULT_RUNS_DIR,
    PcdError,
    canonical_hash,
    load_case,
    new_run_dir,
    read_json,
    write_json,
)
from .cti import run_cti_diagnosis  # noqa: E402
from .discharge import run_discharge  # noqa: E402
from .e2e import run_e2e  # noqa: E402
from .import_case import import_benchmark  # noqa: E402
from .plan import load_proposals, run_plan  # noqa: E402
from .report import run_report  # noqa: E402
from .sketch import run_sketch  # noqa: E402
from .verify import run_check  # noqa: E402


def _latest_run(case_name: str) -> Path:
    base = DEFAULT_RUNS_DIR / case_name
    if not base.is_dir():
        raise PcdError(f"no runs for case {case_name!r}; run `pcd build {case_name}` or `pcd e2e {case_name}`")
    runs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    if not runs:
        raise PcdError(f"no runs for case {case_name!r}")
    return runs[-1]


def _run_for(case_name: str, run_dir: str | None) -> Path:
    path = Path(run_dir).expanduser().resolve() if run_dir else _latest_run(case_name)
    if not (path / "run.json").is_file():
        raise PcdError(f"{path}: not a PCD run directory")
    record = read_json(path / "run.json")
    if record.get("case") != case_name:
        raise PcdError(f"{path}: run case {record.get('case')!r} does not match {case_name!r}")
    return path


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_build(args: argparse.Namespace) -> int:
    case_dir, case = load_case(args.case)
    run_dir = new_run_dir(case["case"], args.runs_dir)
    record = {
        "schema_version": "pcd-run/0.1",
        "run_id": run_dir.name,
        "case": case["case"],
        "mode": case["run_policy"]["mode"],
        "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "stage": {"case": "case"},
        "artifacts": {},
    }
    write_json(run_dir / "run.json", record)
    try:
        build = run_build(run_dir, case_dir, case)
    except Exception as exc:  # noqa: BLE001 - record the failed run, then fail closed
        record["result"] = "error"
        record["error"] = f"{exc.__class__.__name__}: {exc}"
        write_json(run_dir / "run.json", record)
        raise
    record["build"] = {"path": "build.json", "model": build.get("model"), "ok": True}
    record["artifacts"]["build"] = "build.json"
    record["result"] = "built"
    write_json(run_dir / "run.json", record)
    print(f"run: {run_dir}")
    print(f"model: {build['model']['id']}")
    return 0


def cmd_sketch(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    build = load_build(run_dir)
    context = run_sketch(run_dir, case, build, diagnostics_path=args.diagnostics_context)
    record = read_json(run_dir / "run.json")
    record["context"] = {"path": "context.json", "sha256": canonical_hash(context)}
    record.setdefault("artifacts", {})["context"] = "context.json"
    if context.get("diagnostics"):
        record["diagnostics_context"] = context["diagnostics"]
        record["artifacts"]["diagnostics_context"] = "diagnostics-context.json"
    write_json(run_dir / "run.json", record)
    print(f"run: {run_dir}")
    print(f"context: {run_dir / 'context.json'}")
    print(f"context-sha256: {canonical_hash(context)}")
    print(f"properties: {len(context['model'].get('properties', []))}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    proposals = run_plan(
        run_dir,
        case,
        planner=args.planner,
        manual_path=args.proposals,
        llm_command=args.llm_command,
        decomposition_path=args.decomposition,
    )
    record = read_json(run_dir / "run.json")
    record["proposals"] = {"path": "proposals.json", "sha256": canonical_hash(proposals)}
    record.setdefault("artifacts", {})["proposals"] = "proposals.json"
    write_json(run_dir / "run.json", record)
    print(f"run: {run_dir}")
    print(f"proposals: {run_dir / 'proposals.json'}")
    print(f"proposal-sha256: {canonical_hash(proposals)}")
    print(f"nodes: {len(proposals['nodes'])}")
    return 0


def cmd_discharge(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    build = load_build(run_dir)
    proposals, _ = load_proposals(run_dir)
    proof = run_discharge(run_dir, case, build=build, proposals=proposals)
    record = read_json(run_dir / "run.json")
    record["proof"] = {"path": "proof.json"}
    record["discharge"] = {"path": "discharge.json"}
    record.setdefault("artifacts", {})["proof"] = "proof.json"
    record["artifacts"]["discharge"] = "discharge.json"
    write_json(run_dir / "run.json", record)
    print(f"run: {run_dir}")
    print(f"proof: {run_dir / 'proof.json'}")
    print(f"nodes: {len(proof['nodes'])}")
    return 0


def cmd_cti(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    diagnostics = run_cti_diagnosis(
        run_dir,
        case,
        property_index=args.property,
        timeout_s=args.timeout_seconds,
    )
    record = read_json(run_dir / "run.json")
    record["diagnostics"] = {
        "path": "diagnostics.json",
        "sha256": canonical_hash(diagnostics),
        "status": diagnostics.get("status"),
        "ctis": len(diagnostics.get("ctis", [])),
    }
    record.setdefault("artifacts", {})["diagnostics"] = "diagnostics.json"
    write_json(run_dir / "run.json", record)
    print(f"run: {run_dir}")
    print(f"diagnostics: {run_dir / 'diagnostics.json'}")
    print(f"status: {diagnostics.get('status')}")
    print(f"ctis: {len(diagnostics.get('ctis', []))}")
    if args.json:
        _print_json(diagnostics)
    return 0 if diagnostics.get("status") in {"cti", "no_cti", "cex"} else 1


def cmd_check(args: argparse.Namespace) -> int:
    return kernel.main(
        [
            "check",
            "--case",
            args.case,
            "--proof",
            args.proof,
            *(["--json"] if args.json else []),
        ]
    )


def cmd_compose(args: argparse.Namespace) -> int:
    from .compose import inspect, propose

    if args.propose:
        _print_json(propose(args.proof, args.propose))
        return 0
    if not args.case:
        raise PcdError("compose requires --case unless --propose is used")
    result = inspect(args.case, args.proof)
    _print_json(result)
    return 0 if result.get("status") == "proved" else 1


def cmd_crossmodel(args: argparse.Namespace) -> int:
    from .crossmodel import build_and_attach

    report = build_and_attach(args.manifest, clean=not args.keep)
    print(f"out: {report['out']}")
    print(f"status: {report['status']}")
    if report.get("residual"):
        print(f"residual: {len(report['residual'])} open obligation(s)")
    if report.get("fatal_errors"):
        print(f"fatal: {len(report['fatal_errors'])} error(s)")
    if args.json:
        _print_json(report)
    return 0 if report["status"] == "proved" else 1


def cmd_e2e(args: argparse.Namespace) -> int:
    run, run_dir = run_e2e(
        args.case,
        planner=args.planner,
        manual_path=args.proposals,
        llm_command=args.llm_command,
        decomposition_path=args.decomposition,
        runs_dir=args.runs_dir,
        engine_seconds=args.engine_seconds,
        cti=args.cti,
        cti_property=args.cti_property,
        cti_timeout_s=args.cti_timeout_seconds,
        diagnostics_context=args.diagnostics_context,
    )
    print(f"run: {run_dir}")
    print(f"result: {run.get('result')}")
    if run.get("build", {}).get("model"):
        print(f"model: {run['build']['model']['id']}")
    if run.get("check"):
        print(f"kernel-accepted: {run['check']['accepted']}")
        print(f"status: {run['check'].get('status', 'unknown')}")
        if run['check'].get('residual'):
            print(f"residual: {len(run['check']['residual'])} open obligation(s)")
    if run.get("audit"):
        print(f"audit: {run['audit'].get('result')}")
    if run.get("error"):
        print(f"error: {run['error']}", file=sys.stderr)
    if args.json:
        _print_json(run)
    return 0 if run.get("result") == "accepted" else 1


def cmd_report(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    report = run_report(run_dir, case)
    print(f"run: {run_dir}")
    print(f"report: {run_dir / 'report.md'}")
    print(f"accepted: {report['accepted']}")
    return 0 if report["accepted"] else 1


def cmd_audit(args: argparse.Namespace) -> int:
    _, case = load_case(args.case)
    run_dir = _run_for(case["case"], args.run_dir)
    audit = run_audit(run_dir, case)
    print(f"run: {run_dir}")
    print(f"audit: {audit['result']}")
    print(f"blind-ok: {audit['blind_ok']}")
    print(f"completed: {audit.get('completed')}")
    print(f"counts-as-result: {audit['counts_as_planner_result']}")
    return 0 if audit["result"] == "pass" else 1


def cmd_bench(args: argparse.Namespace) -> int:
    from .bench import run_bench

    bench, path = run_bench(
        args.suite,
        planner=args.planner,
        engine_seconds=args.engine_seconds,
        runs_dir=args.runs_dir,
        manual_path=args.proposals,
        llm_command=args.llm_command,
        decomposition_path=args.decomposition,
    )
    print(f"bench: {path}")
    print(f"all-accepted: {bench['all_accepted']}")
    for row in bench["cases"]:
        print(
            f"- {row.get('case')}: {row.get('result')}"
            f" (accepted={row.get('accepted')}, status={row.get('status', 'unknown')}, "
            f"audit={row.get('audit')})"
        )
    if args.json:
        _print_json(bench)
    return 0 if bench["all_accepted"] else 1


def cmd_summary(args: argparse.Namespace) -> int:
    from .summary import write_summary

    conclusion = None
    if args.conclusion:
        conclusion_path = Path(args.conclusion).expanduser()
        conclusion = conclusion_path.read_text(encoding="utf-8")
    result = write_summary(
        runs_dir=args.runs_dir,
        output_csv=args.output,
        output_md=args.markdown,
        suite=args.suite,
        baseline=args.baseline,
        conclusion=conclusion,
    )
    print(f"csv: {result['csv']}")
    print(f"markdown: {result['markdown']}")
    return 0


def cmd_import_benchmark(args: argparse.Namespace) -> int:
    result = import_benchmark(
        args.benchmark,
        args.destination,
        case_name=args.case_name,
        family=args.family,
        mode=args.mode,
        force=args.force,
    )
    print(f"case: {result['case']}")
    print(f"destination: {result['destination']}")
    print(f"model-output: {result['model_output']}")
    print(f"sources: {', '.join(result['sources'])}")
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    return subprocess.call(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
        cwd=str(ROOT),
    )


def cmd_replay(args: argparse.Namespace) -> int:
    from .replay import run_replay

    _, case = load_case(args.case)
    old_run = _run_for(case["case"], args.run_dir)
    run, run_dir = run_replay(args.case, old_run, runs_dir=args.runs_dir)
    print(f"run: {run_dir}")
    print(f"replay-of: {old_run}")
    print(f"result: {run.get('result')}")
    if run.get("replay_ok") is not None:
        print(f"replay-ok: {run['replay_ok']}")
    if run.get("error"):
        print(f"error: {run['error']}", file=sys.stderr)
    return 0 if run.get("result") == "replay_ok" else 1


def cmd_fail_closed(name: str):
    def _inner(_args: argparse.Namespace) -> int:
        raise PcdError(f"{name} is not implemented in this baseline")

    return _inner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pcd", description="proof-carrying decomposition workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="offline schema + kernel check")
    p.add_argument("--case", required=True)
    p.add_argument("--proof", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("compose", help="offline semantic composition guard or mapping proposal")
    p.add_argument("--case")
    p.add_argument("--proof", required=True)
    p.add_argument("--propose", metavar="TRANSFER_NODE", help="emit an untrusted mapping proposal; does not accept a proof")
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser(
        "crossmodel",
        help="assemble a manifest-driven cross-model discharge DAG and check it",
    )
    p.add_argument("--manifest", required=True, help="pcd-crossmodel manifest JSON")
    p.add_argument("--keep", action="store_true", help="do not clear the output directory")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_crossmodel)

    p = sub.add_parser("selftest", help="run the unit/negative-control suite")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser(
        "import-benchmark",
        help="import an official riscv-formal benchmark as a clean case package",
    )
    p.add_argument("benchmark", help="benchmark directory containing ric3.toml and its sources")
    p.add_argument("destination", help="new case-package directory")
    p.add_argument("--case-name", help="override the generated case id")
    p.add_argument(
        "--family",
        help="prefix for the generated case id, e.g. picorv32, serv, nerv, flute, piccolo",
    )
    p.add_argument("--mode", choices=["blind", "dev"], default="blind")
    p.add_argument("--force", action="store_true", help="replace an existing destination")
    p.set_defaults(func=cmd_import_benchmark)

    p = sub.add_parser("build", help="stage a case and build its model")
    p.add_argument("case")
    p.add_argument("--runs-dir")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("sketch", help="create the frozen planner context")
    p.add_argument("case")
    p.add_argument("--run-dir")
    p.add_argument(
        "--diagnostics-context",
        help="path to a prior diagnostic.json to bind into this frozen planner context",
    )
    p.set_defaults(func=cmd_sketch)

    p = sub.add_parser("plan", help="freeze planner proposals")
    p.add_argument("case")
    p.add_argument("--planner", choices=["manual", "template", "decompose", "llm"], required=True)
    p.add_argument("--proposals")
    p.add_argument("--llm-command")
    p.add_argument("--decomposition")
    p.add_argument("--run-dir")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("discharge", help="run the frozen proposals and build proof.json")
    p.add_argument("case")
    p.add_argument("--run-dir")
    p.set_defaults(func=cmd_discharge)

    p = sub.add_parser("e2e", help="build -> sketch -> plan -> discharge -> check -> report")
    p.add_argument("case")
    p.add_argument("--planner", choices=["manual", "template", "decompose", "llm"], required=True)
    p.add_argument("--proposals")
    p.add_argument("--llm-command")
    p.add_argument("--decomposition")
    p.add_argument("--runs-dir")
    p.add_argument("--engine-seconds", type=int, help="run-local override for engine budgets")
    p.add_argument("--cti", action="store_true", help="capture ric3 cill CTIs after the engine phase")
    p.add_argument("--cti-property", type=int, help="select one property index for CTI generation")
    p.add_argument("--cti-timeout-seconds", type=int, help="run-local cill timeout")
    p.add_argument(
        "--diagnostics-context",
        help="path to a prior diagnostic.json to bind into this frozen planner context",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_e2e)

    p = sub.add_parser("cti", help="capture ric3 cill CTI diagnostics for a built run")
    p.add_argument("case")
    p.add_argument("--run-dir")
    p.add_argument("--property", type=int, help="select one property index")
    p.add_argument("--timeout-seconds", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cti)

    p = sub.add_parser("bench", help="run a suite of cases through e2e")
    p.add_argument("suite", help="suite.json, a suite directory, a comma list, or one case")
    p.add_argument("--planner", choices=["manual", "template", "decompose", "llm"])
    p.add_argument("--proposals")
    p.add_argument("--llm-command")
    p.add_argument("--decomposition")
    p.add_argument("--runs-dir")
    p.add_argument("--engine-seconds", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("summary", help="build a cross-case CSV/Markdown summary from runs")
    p.add_argument("--runs-dir", required=True)
    p.add_argument("--output", required=True, help="output CSV path")
    p.add_argument("--markdown", help="output Markdown path (default: CSV path with .md)")
    p.add_argument("--suite", help="suite.json defining case order and labels")
    p.add_argument("--baseline", help="optional CIll SUMMARY.tsv for comparison")
    p.add_argument("--conclusion", help="optional Markdown file appended to the report")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("report", help="render report.md from a run")
    p.add_argument("case")
    p.add_argument("--run-dir")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("audit", help="audit a run for blindness and frozen artifacts")
    p.add_argument("case")
    p.add_argument("--run-dir")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("replay", help="clean rebuild and replay a frozen run")
    p.add_argument("case")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--runs-dir")
    p.set_defaults(func=cmd_replay)

    for name in ("init",):
        p = sub.add_parser(name, help=f"{name} (not implemented)")
        p.set_defaults(func=cmd_fail_closed(name))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PcdError as exc:
        print(f"pcd: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("pcd: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
