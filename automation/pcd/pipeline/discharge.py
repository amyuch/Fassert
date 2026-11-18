"""Discharge frozen proposals with engines and assemble a proof package.

This is the only construction-side module that calls an engine. It does not
decide whether the target is closed; it records verdicts and hands the proof to
the kernel.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import z3
from checkers import model_smt

from common.pcd_util import read_text, sha256_file

from .backends import normalize_engines, resolve_engine_command
from .build import load_build
from .core import PcdError, parse_verdict, relative_to, run_command, write_json
from .cti import parse_cill_check_log
from .plan import load_proposals, validate_proposal
from .timing import cill_statistic_path, parse_statistic_ron


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "node"


def _tool_version(build: dict[str, Any], tool: str) -> str:
    versions = build.get("tool_versions", {})
    value = versions.get(tool)
    if value:
        return str(value)
    return "unknown"


def _z3_checker() -> str:
    return f"z3/{z3.get_version_string()}"


def _assertion_record(run_dir: Path, hint: dict[str, Any]) -> dict[str, Any] | None:
    name = hint.get("assertion_name")
    file_ref = hint.get("assertion_file")
    if not name or not file_ref:
        return None
    file_ref = str(file_ref)
    if file_ref.startswith("/") or ".." in Path(file_ref).parts:
        raise PcdError(f"assertion_file must be case-relative: {file_ref}")
    staged_file = run_dir / "case" / file_ref
    staged_root = (run_dir / "case").resolve()
    if staged_file.is_symlink() or not staged_file.is_file():
        raise PcdError(f"assertion file does not exist in staged case: {file_ref}")
    if not staged_file.resolve().is_relative_to(staged_root):
        raise PcdError(f"assertion file escapes the staged case: {file_ref}")
    return {"name": name, "file": f"case/{file_ref}"}


def _project_root(model_path: Path) -> Path:
    for parent in model_path.resolve().parents:
        if (parent / "ric3proj").is_dir():
            return parent
    raise PcdError(f"cill project directory not found above model {model_path}")


def _cill_verdict(parsed: dict[str, Any], hint: dict[str, Any]) -> str:
    if parsed.get("bmc") == "cex":
        return "cex"
    props = parsed.get("properties", [])
    name = hint.get("assertion_name")
    index = hint.get("property_index")
    match = None
    if name:
        match = next((p for p in props if p.get("name") == name), None)
    if match is None and index is not None:
        try:
            wanted = int(index)
        except (TypeError, ValueError):
            wanted = -1
        match = next((p for p in props if p.get("index") == wanted), None)
    if match is None:
        # When every property is inductive cill prints a summary instead of a
        # per-property table.  The summary is enough only when a name was
        # explicitly bound to the node.
        text = "\n".join(parsed.get("tail", []))
        if name and "All properties are inductive" in text:
            return "proved"
        return "unknown"
    result = match.get("result")
    if result == "inductive":
        return "proved"
    return "unknown"


def _replay_certificate(
    run_dir: Path,
    build: dict[str, Any],
    node: dict[str, Any],
    model_id: str,
    model_rel: str,
    index: int,
    engine_calls: list[dict[str, Any]],
    case: dict[str, Any],
    engines: dict[str, Any],
    cill_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hint = node["certificate_hint"]
    goal = hint["goal"]
    timeout_s = int(hint.get("timeout_s") or case["budgets"]["total_seconds"])
    mapping = {
        "model": model_rel,
        "backend": str(hint.get("backend") or "portfolio"),
        "prop": str(hint.get("property_index", "")),
        "time_limit": str(timeout_s),
        "timeout": str(timeout_s),
    }
    engine, backend, command = resolve_engine_command(engines, hint, mapping)
    safe = _safe(node["id"])
    staged = run_dir / "case"
    model_path = (staged / model_rel).resolve()
    timing: dict[str, Any] | None = None
    if backend == "cill":
        project = _project_root(model_path)
        cache_key = f"{project.resolve()}|{model_id}"
        cache = cill_cache if cill_cache is not None else {}
        cached = cache.get(cache_key)
        log_path = run_dir / "logs" / "engine-cill.log"
        if cached is None:
            result = run_command(
                command,
                cwd=project,
                log_path=log_path,
                timeout_s=timeout_s + 30,
                env=None,
                sandbox=case["run_policy"]["mode"] == "blind",
                sandbox_root=run_dir,
            )
            log_text = read_text(str(log_path))
            parsed = parse_cill_check_log(log_text)
            timing = parse_statistic_ron(cill_statistic_path(project))
            cached = {
                "result": result,
                "log_path": log_path,
                "parsed": parsed,
                "timing": timing,
            }
            cache[cache_key] = cached
        else:
            result = cached["result"]
            log_path = cached["log_path"]
            parsed = cached["parsed"]
            timing = cached.get("timing")
        verdict = _cill_verdict(parsed, hint)
    else:
        log_path = run_dir / "logs" / f"engine-{index:03d}-{safe}.log"
        result = run_command(
            command,
            cwd=staged,
            log_path=log_path,
            timeout_s=timeout_s + 30,
            env=None,
            sandbox=case["run_policy"]["mode"] == "blind",
            sandbox_root=run_dir,
        )
        log_text = read_text(str(log_path))
        verdict = parse_verdict(
            log_text,
            backend=backend,
            returncode=result["returncode"],
            timed_out=result["timed_out"],
        )
    cwd = _project_root(model_path) if backend == "cill" else staged
    engine_seconds = (
        float(timing["engine_seconds"]) if timing is not None else float(result["seconds"])
    )
    run_record = {
        "id": f"engine-{index:03d}-{safe}",
        "command": result["command"],
        "tool": engine,
        "version": _tool_version(build, engine),
        "model_sha256": model_id,
        "log": relative_to(log_path, run_dir),
        "log_sha256": result["log_sha256"],
        "cwd": relative_to(cwd, run_dir),
        "seconds": result["seconds"],
        "engine_wall_seconds": result["seconds"],
        "engine_seconds": round(engine_seconds, 6),
        "bmc_seconds": timing.get("bmc_seconds") if timing else None,
        "ind_seconds": timing.get("ind_seconds") if timing else None,
        "timing_source": "statistic.ron" if timing else "wall-fallback",
        "statistic": relative_to(Path(timing["path"]), run_dir) if timing else None,
        "statistic_sha256": timing.get("sha256") if timing else None,
    }
    cert: dict[str, Any] = {
        "evidence": "REPLAY",
        "format": "replay",
        "verdict": verdict,
        "goal": goal,
        "run": run_record,
    }
    assertion = _assertion_record(run_dir, hint)
    if assertion is not None:
        cert["assertion"] = assertion
    engine_calls.append(
        {
            "node": node["id"],
            "backend": backend,
            "command": result["command"],
            "cwd": relative_to(staged, run_dir),
            "returncode": result["returncode"],
            "timed_out": result["timed_out"],
            "seconds": result["seconds"],
            "engine_wall_seconds": result["seconds"],
            "engine_seconds": round(engine_seconds, 6),
            "bmc_seconds": timing.get("bmc_seconds") if timing else None,
            "ind_seconds": timing.get("ind_seconds") if timing else None,
            "timing_source": "statistic.ron" if timing else "wall-fallback",
            "statistic": relative_to(Path(timing["path"]), run_dir) if timing else None,
            "verdict": verdict,
            "log": relative_to(log_path, run_dir),
            "log_sha256": result["log_sha256"],
            "model_sha256": model_id,
            "sandboxed": result["sandboxed"],
        }
    )
    return cert


def _checked_certificate(node: dict[str, Any]) -> dict[str, Any]:
    hint = node["certificate_hint"]
    fmt = hint["format"]
    if fmt not in {"poly", "smt-implication", "smt-induction", model_smt.FORMAT}:
        raise PcdError(f"{node['id']}: no v0 checker for CHECKED format {fmt!r}")
    checker = hint.get("checker")
    if not checker:
        checker = model_smt.CHECKER if fmt == model_smt.FORMAT else "pcd-poly/0.1" if fmt == "poly" else _z3_checker()
    if fmt == model_smt.FORMAT and checker != model_smt.CHECKER:
        raise PcdError(f"{node['id']}: model-bound SMT must name {model_smt.CHECKER}")
    if fmt == "poly" and not checker.startswith("pcd-poly"):
        raise PcdError(f"{node['id']}: poly checker must be pcd-poly")
    if fmt in {"smt-implication", "smt-induction"} and "z3" not in checker.lower():
        raise PcdError(f"{node['id']}: {fmt} checker must name z3")
    if "payload" not in hint:
        raise PcdError(f"{node['id']}: CHECKED certificate hint has no payload")
    cert: dict[str, Any] = {
        "evidence": "CHECKED",
        "format": fmt,
        "checker": checker,
        "verdict": "proved",
        "goal": hint["goal"],
        "payload": hint["payload"],
    }
    if "artifact" in hint:
        cert["artifact"] = hint["artifact"]
    return cert


def _assemble_node(
    run_dir: Path,
    case: dict[str, Any],
    build: dict[str, Any],
    node: dict[str, Any],
    model_id: str,
    model_rel: str,
    index: int,
    engine_calls: list[dict[str, Any]],
    engines: dict[str, Any],
    cill_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hint = node["certificate_hint"]
    if hint["evidence"] == "REPLAY":
        cert = _replay_certificate(
            run_dir,
            build,
            node,
            model_id,
            model_rel,
            index,
            engine_calls,
            case,
            engines,
            cill_cache,
        )
    elif hint["evidence"] == "CHECKED":
        cert = _checked_certificate(node)
    elif hint["evidence"] == "TCB":
        cert = {
            "evidence": "TCB",
            "format": "tcb",
            "verdict": "assumed",
            "tcb": hint["tcb"],
        }
        if hint.get("kind"):
            cert["kind"] = hint["kind"]
    else:
        raise PcdError(f"{node['id']}: unsupported certificate evidence {hint['evidence']!r}")
    out = {
        "schema_version": "pcd-obligation/0.1",
        "id": node["id"],
        "role": node["role"],
        "kind": node["kind"],
        "phase": node["phase"],
        "model": model_id,
        "statement": node["statement"],
        "requires": node["requires"],
        "provides": node["provides"],
        "certificate": cert,
    }
    # A proposal may declare a cut contract or a helper role.  They are copied
    # as untrusted planner claims; the kernel validates them in K11.
    for key in ("cut", "helper"):
        if key in node:
            out[key] = node[key]
    return out


def run_discharge(
    run_dir: Path,
    case: dict[str, Any],
    *,
    build: dict[str, Any] | None = None,
    proposals: dict[str, Any] | None = None,
    engines: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if engines is None:
        # A standalone discharge/replay uses the catalog frozen into the
        # planner context.  The command is still not taken from the proposal.
        try:
            from .sketch import load_context

            context, _ = load_context(run_dir)
            catalog = context.get("allowed", {}).get("engines")
            engines = catalog if isinstance(catalog, dict) else None
        except Exception:  # noqa: BLE001 - no context means default catalog
            engines = None
    engines = normalize_engines(engines)
    if build is None:
        build = load_build(run_dir)
    if proposals is None:
        proposals, proposal_sha = load_proposals(run_dir)
    else:
        from .core import canonical_hash

        proposal_sha = canonical_hash(proposals)
    validate_proposal(proposals)
    if proposals["case"] != case["case"]:
        raise PcdError("proposal case does not match the case package")
    model = build.get("model")
    if not model:
        raise PcdError("build record has no model")
    model_path = run_dir / "case" / model["path"]
    if not model_path.is_file():
        raise PcdError(f"built model is missing: {model_path}")
    actual = sha256_file(str(model_path))
    if actual != model["sha256"]:
        raise PcdError(f"built model changed: expected {model['sha256']}, got {actual}")
    model_id = model["id"]
    model_rel = model["path"]

    engine_calls: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    tcb_nodes: set[str] = set()
    # A cill run checks every assertion in the built model.  Reuse one run for
    # all helper and target nodes that bind to the same model.
    cill_cache: dict[str, dict[str, Any]] = {}
    for i, node in enumerate(proposals["nodes"]):
        out = _assemble_node(
            run_dir, case, build, node, model_id, model_rel, i, engine_calls, engines, cill_cache
        )
        nodes.append(out)
        if out["certificate"]["evidence"] == "TCB":
            tcb_nodes.add(out["id"])

    node_by_id = {n["id"]: n for n in nodes}
    case_targets = {t["id"]: t for t in case["targets"]}
    proof_targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in proposals["targets"]:
        tid = t["id"]
        if tid in seen:
            raise PcdError(f"duplicate proposal target: {tid}")
        seen.add(tid)
        if tid not in case_targets:
            raise PcdError(f"proposal target {tid} is not in the case")
        if tid not in node_by_id:
            raise PcdError(f"proposal target {tid} has no root obligation")
        ct = case_targets[tid]
        comp = t["composition_hint"]
        if comp["mode"] == "CHECKED":
            if comp.get("checker") != "z3-implication":
                raise PcdError(f"{tid}: only z3-implication is a v0 CHECKED composition")
            if "payload" not in comp:
                raise PcdError(f"{tid}: CHECKED composition has no payload")
            composition = {
                "mode": "CHECKED",
                "checker": "z3-implication",
                "payload": comp["payload"],
            }
            if comp.get("notes"):
                composition["notes"] = comp["notes"]
        else:
            composition = {"mode": "STRUCTURAL"}
            if comp.get("notes"):
                composition["notes"] = comp["notes"]
        decl_tcb = list(t.get("tcb", []))
        for req in t["requires"]:
            if req["node"] in tcb_nodes and req["node"] not in decl_tcb:
                decl_tcb.append(req["node"])
        for nid in decl_tcb:
            if nid not in node_by_id:
                raise PcdError(f"{tid}: declared TCB node {nid} is not a proposal node")
            if nid not in tcb_nodes:
                raise PcdError(f"{tid}: declared TCB node {nid} is not a TCB certificate")
        proof_targets.append(
            {
                "id": tid,
                "statement": ct["statement"],
                "model": model_id,
                "goal": t["goal"],
                "requires": t["requires"],
                "tcb": decl_tcb,
                "composition": composition,
            }
        )
    missing = sorted(set(case_targets) - seen)
    if missing:
        raise PcdError("proposal does not cover case targets: " + ", ".join(missing))

    proof = {
        "schema_version": "pcd-proof/0.1",
        "case": case["case"],
        "acceptance": case.get("acceptance", "complete"),
        "models": {"primary": model_id},
        "primary_model": model_id,
        "model_artifacts": {model_id: {"path": f"case/{model_rel}", "sha256": model["sha256"]}},
        "nodes": nodes,
        "targets": proof_targets,
        "metadata": {
            "run_mode": case["run_policy"]["mode"],
            "run_id": run_dir.name,
            "planner": proposals["planner"],
            "proposal_sha256": proposal_sha,
            "completeness": case.get("acceptance", "complete"),
        },
    }
    write_json(run_dir / "proof.json", proof)
    discharge = {
        "schema_version": "pcd-discharge/0.1",
        "case": case["case"],
        "run_id": run_dir.name,
        "model": model,
        "engine_calls": engine_calls,
        "nodes": [
            {
                "id": n["id"],
                "evidence": n["certificate"]["evidence"],
                "verdict": n["certificate"].get("verdict"),
                "goal": n["certificate"].get("goal"),
            }
            for n in nodes
        ],
        "targets": [t["id"] for t in proof_targets],
    }
    write_json(run_dir / "discharge.json", discharge)
    return proof
