#!/usr/bin/env python3
"""Manifest-driven cross-model proof assembly.

The manifest is declarative: it names frozen models, the engine/SMT facts that
live on each model, the checked projection edges between models, and the final
target.  This module builds a proof package and then lets the kernel compute the
status.  It never assigns ``proved`` itself.

The shape supported here is the discharge DAG:

    engine/SMT facts on a source model
        -> same-model SMT/compose derivation
        -> checked projection to an intermediate model
        -> ... (any acyclic number of hops)
        -> checked projection to the primary model
        -> checked target composition

Projection maps are *proposed* by the structural bit mapper and immediately
re-checked by :func:`checkers.composition.check_projection`.  A manifest cannot
supply a trusted map; it can only ask the checker to propose one.  Missing or
failed edges leave the package open (``needs_check``) or invalid (``reject``)
according to the kernel.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from checkers import composition, expr, model_smt
from kernel import kernel

from .core import PcdError, read_json, write_json

MANIFEST_VERSION = "pcd-crossmodel/0.1"

_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _atom(value: str) -> str:
    atom = _ID_RE.sub("_", value)
    if not atom or not re.match(r"[A-Za-z_]", atom[0]):
        atom = "A_" + atom
    return atom


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


class Manifest:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.base = self.path.parent
        self.doc = read_json(self.path)
        if self.doc.get("schema_version") != MANIFEST_VERSION:
            raise PcdError(f"{self.path}: expected schema_version {MANIFEST_VERSION!r}")
        self.out = Path(self.doc.get("out") or (self.base / "out")).expanduser()
        if not self.out.is_absolute():
            self.out = (self.base / self.out).resolve()
        self.case_path = self._resolve(self.doc["case"])
        self.case = read_json(self.case_path)
        self.models: dict[str, dict[str, Any]] = {}
        self.model_ids: dict[str, str] = {}
        for role, entry in self.doc.get("models", {}).items():
            path = self._resolve(entry["path"])
            if not path.is_file():
                raise PcdError(f"model {role!r} is missing: {path}")
            sha = _sha(path)
            model_id = "btor:" + sha
            self.models[role] = {"path": path, "sha256": sha, "id": model_id}
            self.model_ids[role] = model_id
        if not self.models:
            raise PcdError("manifest declares no models")
        self.primary_role = self.doc.get("primary")
        if self.primary_role not in self.models:
            raise PcdError("manifest primary must name a declared model role")
        expected = self.case.get("build", {}).get("expected_model")
        if expected and self.primary != f"{expected['kind']}:{expected['sha256']}":
            raise PcdError("manifest primary differs from the case's frozen expected_model")
        target_spec = self.doc.get("target", {})
        case_targets = {target["id"]: target for target in self.case.get("targets", [])}
        case_target = case_targets.get(target_spec.get("id", "root"), {})
        required = case_target.get("required_properties")
        if required and set(required) != set(target_spec.get("required_properties", [])):
            raise PcdError("manifest must preserve the case's frozen required_properties")

    def _resolve(self, value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else (self.base / p).resolve()

    @property
    def primary(self) -> str:
        return self.model_ids[self.primary_role]


def _copy(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return _sha(dst)


def _requires(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PcdError("requires must be a list")
    out = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"node", "guarantee"}:
            raise PcdError("each requires entry needs exactly node and guarantee")
        out.append({"node": str(item["node"]), "guarantee": str(item["guarantee"])})
    return out


def _goal_binding(goal: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    kind = goal.get("kind")
    if kind == "property":
        prop = goal.get("property")
        if not isinstance(prop, str) or not prop:
            raise PcdError("property goal needs a property name")
        return "", {"kind": "btor-bad", "property": prop}
    if kind == "expression":
        expression = goal.get("expression")
        if not isinstance(expression, dict):
            raise PcdError("expression goal needs a typed expression")
        return "", {"kind": "btor-expression", "expression": expression}
    raise PcdError("goal kind must be 'property' or 'expression'")


def _replay_node(
    manifest: Manifest,
    spec: dict[str, Any],
    model_role: str,
    copied_logs: dict[Path, str],
    copied_assertions: dict[Path, str],
) -> list[dict[str, Any]]:
    properties = spec.get("properties")
    if properties is None:
        properties = [spec["property"]]
    if not isinstance(properties, list) or not properties:
        raise PcdError(f"{spec.get('id')}: replay needs properties")
    log_src = manifest._resolve(spec["log"])
    if log_src not in copied_logs:
        copied_logs[log_src] = _rel(
            manifest.out / "logs" / f"{spec.get('id', 'replay')}-{log_src.name}",
            manifest.out,
        )
        _copy(log_src, manifest.out / copied_logs[log_src])
    log_rel = copied_logs[log_src]
    assertion_src = manifest._resolve(spec["assertion"])
    if assertion_src not in copied_assertions:
        copied_assertions[assertion_src] = _rel(
            manifest.out / "case" / assertion_src.name, manifest.out
        )
        _copy(assertion_src, manifest.out / copied_assertions[assertion_src])
    assertion_rel = copied_assertions[assertion_src]
    run = dict(spec.get("run") or {})
    command = run.get("command", ["ric3", "cill", "check"])
    run.update({
        "command": command,
        "tool": run.get("tool", "ric3-cill"),
        "version": run.get("version", "ric3"),
        "model_sha256": manifest.model_ids[model_role],
        "log": log_rel,
        "log_sha256": _sha(manifest.out / log_rel),
    })
    run.setdefault("id", f"run-{spec.get('id', 'replay')}")
    nodes = []
    for prop in properties:
        nid = str(spec.get("id") or prop)
        if len(properties) > 1:
            nid = f"{nid}.{_atom(prop)}"
        guarantee = str(spec.get("guarantee") or f"G_{_atom(nid)}")
        nodes.append({
            "schema_version": "pcd-obligation/0.1",
            "id": nid,
            "kind": "replay",
            "role": spec.get("role", "observe"),
            "phase": spec.get("phase", "any"),
            "model": manifest.model_ids[model_role],
            "statement": spec.get("statement") or f"{prop} proved on {model_role}",
            "requires": [],
            "provides": [{
                "name": guarantee,
                "expr": guarantee,
                "sort": "Bool",
                "binding": {"kind": "btor-bad", "property": prop},
            }],
            "certificate": {
                "evidence": "REPLAY",
                "format": "replay",
                "verdict": "proved",
                "goal": guarantee,
                "assertion": {"name": prop, "file": assertion_rel},
                "run": run,
            },
        })
    return nodes


def _smt_node(manifest: Manifest, spec: dict[str, Any], model_role: str) -> dict[str, Any]:
    nid = str(spec["id"])
    guarantee = str(spec.get("guarantee") or f"G_{_atom(nid)}")
    goal = spec.get("goal")
    if not isinstance(goal, dict):
        raise PcdError(f"{nid}: smt needs a goal")
    _, binding = _goal_binding(goal)
    method = spec.get("method", "induction")
    payload: dict[str, Any] = {"method": method}
    if "invariants" in spec:
        payload["invariants"] = spec["invariants"]
    if "timeout_ms" in spec:
        payload["timeout_ms"] = spec["timeout_ms"]
    return {
        "schema_version": "pcd-obligation/0.1",
        "id": nid,
        "kind": spec.get("node_kind", "inductive"),
        "role": spec.get("role", "invariant"),
        "phase": spec.get("phase", "any"),
        "model": manifest.model_ids[model_role],
        "statement": spec.get("statement") or f"{nid} proved on {model_role}",
        "requires": _requires(spec.get("requires")),
        "provides": [{"name": guarantee, "expr": guarantee, "sort": "Bool", "binding": binding}],
        "certificate": {
            "evidence": "CHECKED",
            "format": model_smt.FORMAT,
            "checker": model_smt.CHECKER,
            "verdict": "proved",
            "goal": guarantee,
            "payload": payload,
        },
    }


def _compose_node(manifest: Manifest, spec: dict[str, Any], model_role: str) -> dict[str, Any]:
    nid = str(spec["id"])
    guarantee = str(spec.get("guarantee") or f"G_{_atom(nid)}")
    goal_text = spec.get("goal_expr")
    if not isinstance(goal_text, str) or not goal_text.strip():
        raise PcdError(f"{nid}: compose needs goal_expr")
    requires = _requires(spec.get("requires"))
    premises = [str(spec["_premise_expr"][(r["node"], r["guarantee"])]) for r in requires]
    script = expr.canonical_script(premises, goal_text)
    return {
        "schema_version": "pcd-obligation/0.1",
        "id": nid,
        "kind": spec.get("node_kind", "linear"),
        "role": "compose",
        "phase": spec.get("phase", "any"),
        "model": manifest.model_ids[model_role],
        "statement": spec.get("statement") or f"{nid} composition",
        "requires": requires,
        "provides": [{"name": guarantee, "expr": goal_text, "sort": "Bool"}],
        "certificate": {
            "evidence": "CHECKED",
            "format": "smt-implication",
            "checker": "z3",
            "verdict": "proved",
            "goal": guarantee,
            "payload": {"smt2": script, "timeout_ms": spec.get("timeout_ms", 30_000)},
        },
    }


def build(manifest_path: str | Path, *, clean: bool = True) -> dict[str, Any]:
    """Build and check a cross-model package from a manifest.

    Returns the kernel result plus the output path.  The proof file is always
    written, even when the kernel rejects it, so the failure is auditable.
    """
    manifest = Manifest(manifest_path)
    out = manifest.out
    if clean and out.exists():
        shutil.rmtree(out)
    (out / "models").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "case").mkdir(parents=True, exist_ok=True)

    proof: dict[str, Any] = {
        "schema_version": "pcd-proof/0.1",
        "case": manifest.case["case"],
        "acceptance": "complete",
        "models": {"primary": manifest.primary},
        "primary_model": manifest.primary,
        "model_artifacts": {},
        "nodes": [],
        "targets": [],
        "metadata": {
            "completeness": "complete",
            "run_mode": manifest.doc.get("run_mode", "dev"),
            "development_mode": manifest.doc.get("run_mode", "dev"),
            "generator": "pipeline/crossmodel.py",
            "manifest": manifest.path.name,
            "manifest_sha256": _sha(manifest.path),
            "notes": "Manifest-driven discharge DAG; projection maps are proposed and independently checked.",
        },
    }
    for role, record in manifest.models.items():
        dst = out / "models" / f"{role}.btor"
        sha = _copy(record["path"], dst)
        model_id = "btor:" + sha
        manifest.model_ids[role] = model_id
        proof["models"][role] = model_id
        proof["model_artifacts"][model_id] = {"path": _rel(dst, out), "sha256": sha}
    proof["models"]["primary"] = manifest.primary
    proof["primary_model"] = manifest.primary

    copied_logs: dict[Path, str] = {}
    copied_assertions: dict[Path, str] = {}
    expr_index: dict[tuple[str, str], str] = {}
    node_specs: dict[str, dict[str, Any]] = {}

    for spec in manifest.doc.get("nodes", []):
        kind = spec.get("kind")
        if kind == "replay":
            role = spec.get("model")
            if role not in manifest.models:
                raise PcdError(f"replay node names unknown model role {role!r}")
            created = _replay_node(manifest, spec, role, copied_logs, copied_assertions)
            proof["nodes"].extend(created)
            for node in created:
                node_specs[node["id"]] = spec
                expr_index[(node["id"], node["provides"][0]["name"])] = node["provides"][0]["expr"]
            continue
        if kind == "smt":
            role = spec.get("model")
            if role not in manifest.models:
                raise PcdError(f"smt node names unknown model role {role!r}")
            node = _smt_node(manifest, spec, role)
        elif kind == "compose":
            role = spec.get("model")
            if role not in manifest.models:
                raise PcdError(f"compose node names unknown model role {role!r}")
            spec = dict(spec)
            spec["_premise_expr"] = expr_index
            node = _compose_node(manifest, spec, role)
        elif kind == "transfer":
            role = spec.get("model", manifest.primary_role)
            if role not in manifest.models:
                raise PcdError(f"transfer node names unknown model role {role!r}")
            node = _transfer_node(manifest, spec, role)
        else:
            raise PcdError(f"unsupported node kind {kind!r}")
        proof["nodes"].append(node)
        node_specs[node["id"]] = spec
        expr_index[(node["id"], node["provides"][0]["name"])] = node["provides"][0]["expr"]

    target_spec = manifest.doc.get("target")
    if not isinstance(target_spec, dict):
        raise PcdError("manifest needs a target")
    target_id = str(target_spec.get("id", "root"))
    guarantee = str(target_spec.get("guarantee", "GOAL"))
    goal_expr = target_spec.get("goal_expr")
    if not isinstance(goal_expr, str) or not goal_expr.strip():
        raise PcdError("target needs goal_expr")
    requires = _requires(target_spec.get("requires"))
    premises = [expr_index[(r["node"], r["guarantee"])] for r in requires]
    script = expr.canonical_script(premises, goal_expr)
    root = {
        "schema_version": "pcd-obligation/0.1",
        "id": target_id,
        "kind": "linear",
        "role": "compose",
        "phase": "any",
        "model": manifest.primary,
        "statement": required_statement(manifest, target_spec),
        "requires": requires,
        "provides": [{"name": guarantee, "expr": goal_expr, "sort": "Bool"}],
        "certificate": {
            "evidence": "CHECKED",
            "format": "smt-implication",
            "checker": "z3",
            "verdict": "proved",
            "goal": guarantee,
            "payload": {"smt2": script, "timeout_ms": target_spec.get("timeout_ms", 30_000)},
        },
    }
    proof["nodes"].append(root)
    proof["targets"] = [{
        "id": target_id,
        "statement": root["statement"],
        "model": manifest.primary,
        "goal": guarantee,
        "requires": requires,
        "tcb": list(target_spec.get("tcb", [])),
        "composition": {
            "mode": "CHECKED",
            "checker": "z3-implication",
            "payload": {
                "premises": requires,
                "goal": guarantee,
                "smt2": script,
                "timeout_ms": target_spec.get("timeout_ms", 30_000),
            },
        },
    }]

    case = dict(manifest.case)
    case["build"] = dict(case.get("build", {}))
    case["build"]["expected_model"] = {
        "kind": "btor", "sha256": manifest.models[manifest.primary_role]["sha256"]
    }
    case["targets"] = [dict(t) for t in case.get("targets", [])]
    if not case["targets"]:
        raise PcdError("case has no target")
    case["targets"][0]["required_properties"] = list(target_spec.get("required_properties", []))
    write_json(out / "case.json", case)
    write_json(out / "proof.json", proof)

    result = kernel.check_paths(str(out / "case.json"), str(out / "proof.json"))
    report = {
        "manifest": str(manifest.path),
        "out": str(out),
        "status": result.status,
        "proved": result.proved,
        "errors": [e.as_dict() for e in result.errors],
        "fatal_errors": result.fatal_errors,
        "residual": result.residual,
        "obligations": result.obligations,
        "composition": result.composition,
    }
    write_json(out / "crossmodel.json", report)
    return report


def required_statement(manifest: Manifest, target_spec: dict[str, Any]) -> str:
    statement = target_spec.get("statement")
    if isinstance(statement, str) and statement:
        return statement
    return str(manifest.case["targets"][0]["statement"])


def _transfer_node(manifest: Manifest, spec: dict[str, Any], role: str) -> dict[str, Any]:
    nid = str(spec["id"])
    source_ref = spec.get("source")
    if not isinstance(source_ref, dict):
        raise PcdError(f"{nid}: transfer needs source {{node, guarantee}}")
    source_ref = {"node": str(source_ref["node"]), "guarantee": str(source_ref["guarantee"])}
    dest_property = spec.get("dest_property")
    if not isinstance(dest_property, str) or not dest_property:
        raise PcdError(f"{nid}: transfer needs dest_property")
    dest_guarantee = str(spec.get("dest_guarantee") or f"D_{_atom(nid)}")
    node = {
        "schema_version": "pcd-obligation/0.1",
        "id": nid,
        "kind": "equivalence",
        "role": "transfer",
        "phase": "any",
        "model": manifest.model_ids[role],
        "statement": spec.get("statement") or f"checked projection to {role}",
        "requires": [source_ref],
        "provides": [{
            "name": dest_guarantee,
            "expr": dest_guarantee,
            "sort": "Bool",
            "binding": {"kind": "btor-bad", "property": dest_property},
        }],
        "certificate": {
            "evidence": "CHECKED",
            "format": composition.FORMAT,
            "checker": composition.CHECKER,
            "verdict": "proved",
            "goal": dest_guarantee,
            "payload": {},
        },
    }
    return node


def attach_projection_maps(proof: dict[str, Any], base: str | Path) -> list[dict[str, Any]]:
    """Propose and check every transfer in an assembled proof.

    The proposal is cone-restricted and then checked.  A failed projection is
    recorded, not hidden; the kernel will turn it into an error.
    """
    store = composition.ModelStore(proof, str(base))
    nodes = {node["id"]: node for node in proof["nodes"]}
    records = []
    for node in proof["nodes"]:
        if node.get("certificate", {}).get("format") != composition.FORMAT:
            continue
        source_ref = node["requires"][0]
        source_node = nodes[source_ref["node"]]
        source_guarantee = next(g for g in source_node["provides"] if g["name"] == source_ref["guarantee"])
        if (source_guarantee.get("binding") or {}).get("kind") != "btor-bad":
            raise PcdError(
                f"{node['id']}: a projection source must be a model property, not an expression lemma"
            )
        try:
            source_model = store.get(source_node["model"])
            destination_model = store.get(node["model"])
            mapping = composition.cone_mapping(
                source_model, destination_model, source_guarantee["binding"]["property"]
            )
            node["certificate"]["payload"] = composition.bit_proposal(
                source_node, node, source_guarantee, node["provides"][0], store, mapping=mapping
            )
            records.append(composition.check_projection(node, nodes, store))
        except (composition.CompositionError, ValueError, KeyError, OSError, TypeError) as exc:
            records.append({"accepted": False, "node": node["id"], "reason": str(exc)})
    return records


def build_and_attach(manifest_path: str | Path, *, clean: bool = True) -> dict[str, Any]:
    """Convenience wrapper: build the proof, attach maps, then re-check.

    The first build performs a kernel check with empty projection payloads, so
    the caller can inspect the structural result.  This wrapper attaches the
    proposed maps and runs the kernel again, which is the acceptance result.
    """
    manifest = Manifest(manifest_path)
    report = build(manifest_path, clean=clean)
    proof = read_json(manifest.out / "proof.json")
    attach_projection_maps(proof, manifest.out)
    write_json(manifest.out / "proof.json", proof)
    result = kernel.check_paths(str(manifest.out / "case.json"), str(manifest.out / "proof.json"))
    report = {
        "manifest": str(manifest.path),
        "out": str(manifest.out),
        "status": result.status,
        "proved": result.proved,
        "errors": [e.as_dict() for e in result.errors],
        "fatal_errors": result.fatal_errors,
        "residual": result.residual,
        "obligations": result.obligations,
        "composition": result.composition,
    }
    write_json(manifest.out / "crossmodel.json", report)
    return report
