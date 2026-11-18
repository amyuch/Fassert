#!/usr/bin/env python3
"""PCD kernel.

The kernel is the only component allowed to close a target. It never calls an
engine. It validates a proof package against the case and proof schemas, checks
each certificate/replay binding, dependency and guarantee closure, transfer and
coverage obligations, per-node artifact hashes, helper hygiene, and
proposal/verdict separation, then computes the claim level and final
disposition.

The supported certificate formats are deliberately small. Unsupported formats
are rejected rather than trusted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import jsonschema
import z3
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUTOMATION = os.path.dirname(ROOT)
for _path in (ROOT, AUTOMATION):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from checkers import induction as induction_checker  # noqa: E402
from checkers import poly as poly_checker  # noqa: E402
from checkers import smt as smt_checker  # noqa: E402
from checkers import composition as composition_checker  # noqa: E402
from checkers import expr as expr_checker  # noqa: E402
from checkers import model_smt as model_smt_checker  # noqa: E402
from common.pcd_util import load_json_or_yaml, read_text, resolve_path, sha256_file  # noqa: E402
from kernel import disposition  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "schema")
SCHEMA_IDS = {
    "case": "https://fassert.local/pcd/schema/case.schema.json",
    "obligation": "https://fassert.local/pcd/schema/obligation.schema.json",
    "proof": "https://fassert.local/pcd/schema/proof.schema.json",
}
EVIDENCE_RANK = {"TCB": 0, "REPLAY": 1, "CHECKED": 2}
ASSUMPTION_DIMENSIONS = {"model", "width", "guards", "phase", "transition"}
OFFICIAL_TCB_KINDS = {"frontend", "engine", "checker", "isa_model"}
TAUTOLOGY_PATTERNS = [
    r"\|\|\s*1\s*'\s*[bBdD]\s*1\b",
    r"\|\|\s*1\s*\)",
    r"\bassert\s*\(\s*1\s*'\s*[bBdD]\s*1\s*\)",
    r"\bassert\s*\(\s*1\s*\)",
    r"\bassert\s*\(\s*true\s*\)",
    r"\bassert\s*\(\s*([A-Za-z_][\w.]*)\s*(==|<=|>=)\s*\1\s*\)",
]


@dataclass
class Issue:
    rule: str
    message: str
    severity: str = "error"
    node: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rule": self.rule, "message": self.message}
        if self.node is not None:
            out["node"] = self.node
        return out


@dataclass
class CheckResult:
    accepted: bool = False
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    node_evidence: dict[str, str] = field(default_factory=dict)
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    composition: dict[str, Any] = field(default_factory=dict)
    status: str = "reject"
    obligations: list[dict[str, Any]] = field(default_factory=list)
    residual: list[dict[str, Any]] = field(default_factory=list)
    fatal_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def proved(self) -> bool:
        return self.status == "proved"

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "proved": self.proved,
            "errors": [i.as_dict() for i in self.errors],
            "warnings": [i.as_dict() for i in self.warnings],
            "node_evidence": self.node_evidence,
            "targets": self.targets,
            "composition": self.composition,
            "obligations": self.obligations,
            "residual": self.residual,
            "fatal_errors": self.fatal_errors,
        }


_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def _schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_CACHE:
        path = os.path.join(SCHEMA_DIR, f"{name}.schema.json")
        with open(path, "r", encoding="utf-8") as fh:
            _SCHEMA_CACHE[name] = json.load(fh)
    return _SCHEMA_CACHE[name]


def _registry() -> Registry:
    resources = []
    for name in SCHEMA_IDS:
        schema = _schema(name)
        resources.append(
            (
                SCHEMA_IDS[name],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


def _validate(doc: dict[str, Any], name: str, registry: Registry) -> list[Any]:
    validator = jsonschema.Draft202012Validator(_schema(name), registry=registry)
    return sorted(
        validator.iter_errors(doc),
        key=lambda e: (tuple(str(p) for p in e.absolute_path), e.message),
    )


def _err_path(error: Any) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/".join(parts) if parts else "<root>"


def _add(
    res: CheckResult,
    rule: str,
    message: str,
    *,
    severity: str = "error",
    node: str | None = None,
) -> None:
    issue = Issue(rule, message, severity=severity, node=node)
    if severity == "error":
        res.errors.append(issue)
    else:
        res.warnings.append(issue)


def _strip_comments(text: str) -> str:
    """Remove comments so helper scans do not mistake prose for evidence."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _helper_events(text: str, keyword: str) -> tuple[set[str], int]:
    """Return named ``keyword`` events and the number of unnamed events."""
    named: set[str] = set()
    unnamed = 0
    pattern = re.compile(
        rf"(?m)(?:([A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?\b{keyword}\b"
        rf"\s*(?:property\s*)?(?:#\s*[^;]*?)?\("
    )
    for match in pattern.finditer(text):
        if match.group(1):
            named.add(match.group(1))
        else:
            unnamed += 1
    return named, unnamed


def _complete_mode(case: dict[str, Any], proof: dict[str, Any]) -> bool:
    """Complete acceptance is the default; legacy must be opted into twice."""
    case_policy = case.get("acceptance", "complete")
    proof_policy = proof.get("acceptance", "complete")
    metadata_policy = proof.get("metadata", {}).get("completeness", "complete")
    return not (case_policy == proof_policy == metadata_policy == "legacy")


def _check_artifact(
    res: CheckResult,
    artifact: dict[str, Any],
    base: str,
    owner: str,
    allow_missing_artifacts: bool,
    rule: str = "K8",
) -> None:
    path = resolve_path(base, artifact["path"])
    if not os.path.exists(path):
        if allow_missing_artifacts:
            _add(res, rule, f"{owner}: artifact missing (dev override): {artifact['path']}", severity="warning", node=owner)
        else:
            _add(res, rule, f"{owner}: artifact missing: {artifact['path']}", node=owner)
        return
    actual = sha256_file(path)
    if actual != artifact["sha256"]:
        _add(
            res,
            rule,
            f"{owner}: artifact hash mismatch for {artifact['path']}: expected {artifact['sha256']}, got {actual}",
            node=owner,
        )


def _check_run_log(
    res: CheckResult,
    run: dict[str, Any],
    base: str,
    owner: str,
    allow_missing_artifacts: bool,
) -> None:
    log = run.get("log")
    if not log:
        return
    path = resolve_path(base, log)
    if not os.path.exists(path):
        if allow_missing_artifacts:
            _add(res, "K2", f"{owner}: replay log missing (dev override): {log}", severity="warning", node=owner)
        else:
            _add(res, "K2", f"{owner}: replay log missing: {log}", node=owner)
        return
    actual = sha256_file(path)
    if actual != run["log_sha256"]:
        _add(
            res,
            "K2",
            f"{owner}: replay log hash mismatch for {log}: expected {run['log_sha256']}, got {actual}",
            node=owner,
        )


def _check_assertion_file(
    res: CheckResult,
    assertion: dict[str, Any],
    base: str,
    owner: str,
    scanned: set[str],
) -> None:
    path = resolve_path(base, assertion["file"])
    if not os.path.exists(path):
        _add(res, "K9", f"{owner}: assertion file missing: {assertion['file']}", node=owner)
        return
    text = read_text(path)
    scanned.add(path)
    if not re.search(rf"\b{re.escape(assertion['name'])}\b", text):
        _add(
            res,
            "K9",
            f"{owner}: assertion {assertion['name']!r} not found in {assertion['file']}",
            node=owner,
        )
    if "line" in assertion:
        lines = text.splitlines()
        line_no = assertion["line"]
        if 1 <= line_no <= len(lines) and assertion["name"] not in lines[line_no - 1]:
            _add(
                res,
                "K9",
                f"{owner}: assertion {assertion['name']!r} is not on line {line_no} of {assertion['file']}",
                node=owner,
            )


def _check_certificate(
    res: CheckResult,
    node: dict[str, Any],
    model_ids: set[str],
    base: str,
    allow_missing_artifacts: bool,
    scanned: set[str],
    guarantees: dict[tuple[str, str], dict[str, Any]],
) -> None:
    nid = node["id"]
    cert = node["certificate"]
    evidence = cert["evidence"]
    provided = {g["name"] for g in node["provides"]}

    if evidence in {"CHECKED", "REPLAY"}:
        if cert.get("goal") not in provided:
            _add(
                res,
                "K2",
                f"{nid}: certificate goal {cert.get('goal')!r} is not one of this node's guarantees",
                node=nid,
            )

    if evidence == "CHECKED":
        fmt = cert["format"]
        payload = cert.get("payload", {})
        goal_guarantee = guarantees.get((nid, cert.get("goal")))
        if goal_guarantee is None:
            _add(
                res,
                "K2",
                f"{nid}: certificate goal {cert.get('goal')!r} has no formula in this node",
                node=nid,
            )
        if fmt == "poly":
            if not cert["checker"].startswith("pcd-poly"):
                _add(res, "K2", f"{nid}: poly certificate must name the pcd-poly checker", node=nid)
            if goal_guarantee is not None:
                ok, detail = poly_checker.check_expr(goal_guarantee["expr"], payload)
                if not ok:
                    _add(res, "K2", f"{nid}: poly certificate rejected: {detail}", node=nid)
        elif fmt == "smt-implication":
            if "z3" not in cert["checker"].lower():
                _add(res, "K2", f"{nid}: smt-implication certificate must name the z3 checker", node=nid)
            if goal_guarantee is not None:
                if goal_guarantee.get("sort") != "Bool":
                    _add(
                        res,
                        "K2",
                        f"{nid}: SMT goal has sort {goal_guarantee.get('sort')!r}; expected Bool",
                        node=nid,
                    )
                else:
                    premises, premises_ok = _premise_expressions(res, nid, node, guarantees)
                    if premises_ok:
                        ok, detail = smt_checker.check_implication(
                            premises,
                            goal_guarantee["expr"],
                            payload.get("smt2"),
                            payload.get("timeout_ms"),
                        )
                        if not ok:
                            _add(
                                res,
                                "K2",
                                f"{nid}: smt-implication certificate rejected: {detail}",
                                node=nid,
                            )
        elif fmt == "smt-induction":
            if "z3" not in cert["checker"].lower():
                _add(res, "K2", f"{nid}: smt-induction certificate must name the z3 checker", node=nid)
            if goal_guarantee is not None:
                if goal_guarantee.get("sort") != "Bool":
                    _add(
                        res,
                        "K2",
                        f"{nid}: induction goal has sort {goal_guarantee.get('sort')!r}; expected Bool",
                        node=nid,
                    )
                else:
                    premises, premises_ok = _premise_expressions(res, nid, node, guarantees)
                    if premises_ok:
                        ok, detail = induction_checker.check(
                            premises,
                            goal_guarantee["expr"],
                            payload,
                            payload.get("timeout_ms"),
                        )
                        if not ok:
                            _add(
                                res,
                                "K2",
                                f"{nid}: smt-induction certificate rejected: {detail}",
                                node=nid,
                            )
        elif fmt == composition_checker.FORMAT:
            # Model semantics and endpoint binding are checked together in K13.
            if cert["checker"] != composition_checker.CHECKER:
                _add(res, "K2", f"{nid}: projection must name {composition_checker.CHECKER}", node=nid)
        elif fmt == model_smt_checker.FORMAT:
            if cert["checker"] != model_smt_checker.CHECKER:
                _add(res, "K2", f"{nid}: model-bound SMT must name {model_smt_checker.CHECKER}", node=nid)
        else:
            _add(
                res,
                "K2",
                f"{nid}: no v0 checker for certificate format {fmt!r}; refusing to trust it",
                node=nid,
            )
        if "artifact" in cert:
            _check_artifact(res, cert["artifact"], base, nid, allow_missing_artifacts)

    elif evidence == "REPLAY":
        run = cert["run"]
        if run["model_sha256"] != node["model"]:
            _add(
                res,
                "K2",
                f"{nid}: replay model hash {run['model_sha256']} does not match node model {node['model']}",
                node=nid,
            )
        if run["model_sha256"] not in model_ids:
            _add(res, "K7", f"{nid}: replay model is not in the proof model registry", node=nid)
        _check_run_log(res, run, base, nid, allow_missing_artifacts)
        if "assertion" in cert:
            _check_assertion_file(res, cert["assertion"], base, nid, scanned)
        if "artifact" in cert:
            _check_artifact(res, cert["artifact"], base, nid, allow_missing_artifacts)

    elif evidence == "TCB":
        if not cert.get("tcb"):
            _add(res, "K2", f"{nid}: TCB certificate has no trust reason", node=nid)


def _check_cycles(res: CheckResult, nodes: dict[str, dict[str, Any]], *, complete: bool = False) -> None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def dfs(nid: str) -> None:
        state[nid] = 1
        stack.append(nid)
        for req in nodes[nid].get("requires", []):
            dep = req["node"]
            if dep not in nodes:
                continue
            s = state.get(dep, 0)
            if s == 1:
                idx = stack.index(dep)
                cycle = stack[idx:]
                groups = {nodes[x].get("simultaneous_group") for x in cycle}
                phases = {nodes[x]["phase"] for x in cycle}
                if complete or len(groups) != 1 or None in groups or len(phases) != 1:
                    _add(
                        res,
                        "K3",
                        "dependency cycle requires a checked joint-induction certificate: "
                        + " -> ".join(cycle + [dep]),
                    )
            elif s == 0:
                dfs(dep)
        stack.pop()
        state[nid] = 2

    for nid in nodes:
        if state.get(nid, 0) == 0:
            dfs(nid)


def _premise(req: dict[str, Any]) -> tuple[str, str]:
    return (req["node"], req["guarantee"])


def _support_cone(root: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
    """Every node that transitive premises of ``root`` depend on.

    This is the in-model derivation support of a guarantee.  A transfer's
    guarantee is established on the destination model from its source and any
    constraint-discharge witnesses; all of their same-model support nodes are
    part of the checked edge, not independent obligations.
    """
    seen: set[str] = set()
    pending = [root]
    while pending:
        nid = pending.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = nodes.get(nid)
        if node is None:
            continue
        for req in node.get("requires", []):
            dep = str(req["node"])
            if dep in nodes and dep not in seen:
                pending.append(dep)
    return seen


def _transfer_support(
    transfer: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> set[str]:
    """Support cone of every premise of a checked transfer edge."""
    support: set[str] = set()
    for req in transfer.get("requires", []):
        dep = str(req["node"])
        if dep in nodes:
            support |= _support_cone(dep, nodes)
    return support


def _checked_transfer_node(node: dict[str, Any]) -> bool:
    cert = node.get("certificate") or {}
    return (
        node.get("role") == "transfer"
        and cert.get("evidence") == "CHECKED"
        and cert.get("verdict") == "proved"
    )


def _guarantee_index(nodes: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (nid, guarantee["name"]): guarantee
        for nid, node in nodes.items()
        for guarantee in node["provides"]
    }


def _premise_expressions(
    res: CheckResult,
    nid: str,
    node: dict[str, Any],
    guarantees: dict[tuple[str, str], dict[str, Any]],
    rule: str = "K2",
) -> tuple[list[str], bool]:
    """Return the formulas of a node's premises, requiring Boolean premises."""
    exprs: list[str] = []
    ok = True
    for req in node.get("requires", []):
        guarantee = guarantees.get(_premise(req))
        if guarantee is None:
            _add(
                res,
                rule,
                f"{nid}: cannot bind premise {req['node']}.{req['guarantee']} to a formula",
                node=nid,
            )
            ok = False
            continue
        if guarantee.get("sort") != "Bool":
            _add(
                res,
                rule,
                f"{nid}: SMT premise {req['node']}.{req['guarantee']} has sort "
                f"{guarantee.get('sort')!r}; composition/SMT premises must be Bool",
                node=nid,
            )
            ok = False
            continue
        exprs.append(guarantee["expr"])
    return exprs, ok


def _semantic_checks(
    case: dict[str, Any],
    proof: dict[str, Any],
    base: str,
    allow_missing_artifacts: bool,
) -> CheckResult:
    res = CheckResult()
    policies = [case.get("acceptance", "complete"), proof.get("acceptance", "complete"),
                proof.get("metadata", {}).get("completeness", "complete")]
    if any(policy != policies[0] for policy in policies) or policies[0] not in {"complete", "legacy"}:
        _add(res, "K12", "case, proof and metadata acceptance policies disagree")

    # K1: identity, references, duplicates, model registry.
    if proof["case"] != case["case"]:
        _add(res, "K1", f"proof case {proof['case']!r} does not match case {case['case']!r}")

    models = proof["models"]
    primary = proof["primary_model"]
    model_ids = set(models.values())
    if primary not in model_ids:
        _add(res, "K1", f"primary_model {primary} is not present in models")
    if models.get("primary") != primary:
        _add(res, "K7", "models['primary'] must name primary_model")

    nodes: dict[str, dict[str, Any]] = {}
    for node in proof["nodes"]:
        nid = node["id"]
        if nid in nodes:
            _add(res, "K1", f"duplicate obligation id: {nid}", node=nid)
        else:
            nodes[nid] = node
        if node["model"] not in model_ids:
            _add(res, "K1", f"{nid}: model {node['model']} is not in the proof model registry", node=nid)
        res.node_evidence[nid] = node["certificate"]["evidence"]

    target_ids: set[str] = set()
    case_targets = {t["id"]: t for t in case["targets"]}
    for target in proof["targets"]:
        tid = target["id"]
        if tid in target_ids:
            _add(res, "K1", f"duplicate target id: {tid}", node=tid)
        target_ids.add(tid)
        root = nodes.get(tid)
        if root is None:
            _add(res, "K1", f"target {tid} has no root obligation", node=tid)
        elif root["role"] != "compose":
            _add(res, "K1", f"target {tid} root obligation must have role 'compose'", node=tid)
        if target["model"] not in model_ids:
            _add(res, "K1", f"target {tid} model {target['model']} is not registered", node=tid)
        case_target = case_targets.get(tid)
        if case_target is None:
            _add(res, "K1", f"proof target {tid} is not declared in the case", node=tid)
        else:
            case_model = case_target.get("model")
            if case_model is not None and case_model != target["model"]:
                _add(
                    res,
                    "K1",
                    f"proof target {tid} model {target['model']} does not match the case target model "
                    f"{case_model}",
                    node=tid,
                )
            if case_target.get("model_ref") == "primary" and target["model"] != primary:
                _add(
                    res,
                    "K1",
                    f"proof target {tid} model {target['model']} is not the case primary model {primary}",
                    node=tid,
                )
            if case_model is None and case_target.get("model_ref") != "primary":
                _add(res, "K1", f"case target {tid} has neither a model nor model_ref", node=tid)
            if case_target["statement"] != target["statement"]:
                _add(res, "K1", f"proof target {tid} statement does not match the frozen case target", node=tid)
            if case_target.get("claim_level") != "root":
                _add(res, "K1", f"case target {tid} is not a root target", node=tid)
    if target_ids != set(case_targets):
        _add(res, "K1", "proof does not cover exactly the declared case targets")

    # K2 / K8: local certificates, replay bindings, artifacts.
    guarantees = _guarantee_index(nodes)
    scanned: set[str] = set()
    for node in proof["nodes"]:
        _check_certificate(res, node, model_ids, base, allow_missing_artifacts, scanned, guarantees)

    # Dependency closure of each target, used to decide whether a TCB premise is
    # declared by a target that actually consumes it.
    def _deps(root_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [root_id]
        while stack:
            cur = stack.pop()
            for req in nodes[cur].get("requires", []):
                dep = req["node"]
                if dep in nodes and dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
        return seen

    tcb_allowed: dict[str, set[str]] = {}
    target_closures: dict[str, set[str]] = {}
    for target in proof["targets"]:
        if target["id"] not in nodes:
            continue
        closure = {target["id"]} | _deps(target["id"])
        target_closures[target["id"]] = closure
        for nid in closure:
            tcb_allowed.setdefault(nid, set()).update(target["tcb"])

    # Discharge-DAG support.  A node on a non-primary model is used soundly if
    # it supports a checked transfer edge that lies on the derivation of a
    # target.  The support is transitive through same-model premises, so an
    # internal fact used by an intermediate root is anchored by the transfer
    # that carries that root, not only by a transfer that names the fact
    # directly.  Cycles are rejected independently by K3.
    anchored: dict[str, str] = {}
    for closure in target_closures.values():
        for nid in closure:
            transfer = nodes.get(nid)
            if transfer is None or not _checked_transfer_node(transfer):
                continue
            for support_id in _transfer_support(transfer, nodes):
                anchored.setdefault(support_id, nid)
    all_closures: set[str] = set()
    for closure in target_closures.values():
        all_closures |= closure

    # K3: dependency closure, guarantee matching, diagnostic-premise rejection.
    for node in proof["nodes"]:
        nid = node["id"]
        for req in node.get("requires", []):
            dep = nodes.get(req["node"])
            if dep is None:
                _add(res, "K3", f"{nid}: missing premise node {req['node']}", node=nid)
                continue
            names = {g["name"] for g in dep["provides"]}
            if req["guarantee"] not in names:
                _add(
                    res,
                    "K3",
                    f"{nid}: premise {req['node']}.{req['guarantee']} is not provided by that node",
                    node=nid,
                )
                continue
            ev = dep["certificate"]["evidence"]
            if ev == "TCB":
                official = (
                    _complete_mode(case, proof)
                    and dep["certificate"].get("kind") in OFFICIAL_TCB_KINDS
                )
                if not official and req["node"] not in tcb_allowed.get(nid, set()):
                    _add(
                        res,
                        "K3",
                        f"{nid}: TCB premise {req['node']} is not declared in the tcb list of a target "
                        "that depends on this node",
                        node=nid,
                    )
            elif ev == "REPLAY" and dep["certificate"].get("verdict") != "proved":
                _add(
                    res,
                    "K3",
                    f"{nid}: premise {req['node']} has non-proof verdict "
                    f"{dep['certificate'].get('verdict')!r}",
                    node=nid,
                )
    _check_cycles(res, nodes, complete=_complete_mode(case, proof))

    # K4: transfer/abstraction gates and reuse.
    for node in proof["nodes"]:
        nid = node["id"]
        if node["role"] in {"transfer", "abstraction_gate"}:
            if node["certificate"]["evidence"] != "CHECKED":
                _add(res, "K4", f"{nid}: transfer/abstraction gate must be CHECKED", node=nid)
        reuse = node.get("reuse")
        if reuse is None:
            continue
        if reuse["source_model"] != node["model"]:
            _add(
                res,
                "K4",
                f"{nid}: reuse.source_model {reuse['source_model']} does not match node model {node['model']}",
                node=nid,
            )
        if set(reuse["assumption_match"]) != ASSUMPTION_DIMENSIONS:
            _add(res, "K4", f"{nid}: reuse does not match all five assumption dimensions", node=nid)
        transfer_id = reuse["transfer_node"]
        transfer = nodes.get(transfer_id)
        if transfer is None:
            _add(res, "K4", f"{nid}: reuse transfer node {transfer_id} does not exist", node=nid)
            continue
        if not _checked_transfer_node(transfer):
            _add(res, "K4", f"{nid}: reuse transfer node {transfer_id} is not a CHECKED transfer", node=nid)
        if transfer_id not in all_closures:
            _add(
                res,
                "K4",
                f"{nid}: reuse transfer node {transfer_id} is not on a target derivation path",
                node=nid,
            )
        if nid not in _transfer_support(transfer, nodes):
            _add(
                res,
                "K4",
                f"{nid}: reuse transfer node {transfer_id} does not depend on the reused node",
                node=nid,
            )

    # K5: coverage is a certificate.
    for node in proof["nodes"]:
        if node["role"] != "coverage":
            continue
        nid = node["id"]
        cov = node.get("coverage")
        if cov is None:
            _add(res, "K5", f"{nid}: coverage obligation has no coverage record", node=nid)
            continue
        if not cov.get("exhaustive"):
            _add(res, "K5", f"{nid}: guard partition is not marked exhaustive", node=nid)
        checked_by = cov.get("checked_by")
        if checked_by:
            checker_node = nodes.get(checked_by)
            if checker_node is not None and checker_node["certificate"]["evidence"] != "CHECKED":
                _add(
                    res,
                    "K5",
                    f"{nid}: coverage checker node {checked_by} is not CHECKED",
                    node=nid,
                )
        elif node["certificate"]["evidence"] != "CHECKED":
            _add(res, "K5", f"{nid}: coverage has neither a checked_by node nor a CHECKED certificate", node=nid)

    # K6: root composition and guarantee matching.
    for target in proof["targets"]:
        tid = target["id"]
        root = nodes.get(tid)
        if root is None:
            continue
        target_reqs = sorted(_premise(r) for r in target["requires"])
        root_reqs = sorted(_premise(r) for r in root.get("requires", []))
        if target_reqs != root_reqs:
            _add(
                res,
                "K6",
                f"{tid}: target requires do not match the root obligation requires",
                node=tid,
            )
        if len(target_reqs) != len(set(target_reqs)):
            _add(res, "K6", f"{tid}: duplicate target premise", node=tid)
        if target["model"] != root["model"]:
            _add(res, "K6", f"{tid}: target model does not match root model", node=tid)
        if target["model"] != primary:
            _add(res, "K6", f"{tid}: root target must be on the primary model", node=tid)

        provided = {g["name"] for g in root["provides"]}
        if target["goal"] not in provided:
            _add(res, "K6", f"{tid}: root does not provide goal {target['goal']}", node=tid)

        for req in target["requires"]:
            dep = nodes.get(req["node"])
            if dep is None:
                _add(res, "K6", f"{tid}: target premise node {req['node']} does not exist", node=tid)
                continue
            if req["guarantee"] not in {g["name"] for g in dep["provides"]}:
                _add(
                    res,
                    "K6",
                    f"{tid}: target premise {req['node']}.{req['guarantee']} is not provided",
                    node=tid,
                )
            ev = dep["certificate"]["evidence"]
            if ev == "TCB":
                if req["node"] not in target["tcb"]:
                    _add(
                        res,
                        "K6",
                        f"{tid}: TCB premise {req['node']} is not declared in target.tcb",
                        node=tid,
                    )
            elif ev == "REPLAY" and dep["certificate"].get("verdict") != "proved":
                _add(
                    res,
                    "K6",
                    f"{tid}: target premise {req['node']} has non-proof verdict "
                    f"{dep['certificate'].get('verdict')!r}",
                    node=tid,
                )

        for tcb_id in target["tcb"]:
            tcb_node = nodes.get(tcb_id)
            if tcb_node is None:
                _add(res, "K6", f"{tid}: declared TCB node {tcb_id} does not exist", node=tid)
            elif tcb_node["certificate"]["evidence"] != "TCB":
                _add(res, "K6", f"{tid}: declared TCB node {tcb_id} is not a TCB leaf", node=tid)

        comp = target["composition"]
        if comp["mode"] == "STRUCTURAL":
            _add(
                res,
                "K6",
                f"{tid}: STRUCTURAL composition accepted, but the claim is capped (not a proof)",
                severity="warning",
                node=tid,
            )
        else:
            payload = comp["payload"]
            payload_reqs = sorted(_premise(r) for r in payload["premises"])
            if payload_reqs != target_reqs:
                _add(
                    res,
                    "K6",
                    f"{tid}: composition payload premises do not match target requires",
                    node=tid,
                )
            if payload["goal"] != target["goal"]:
                _add(
                    res,
                    "K6",
                    f"{tid}: composition payload goal {payload['goal']!r} does not match target goal {target['goal']!r}",
                    node=tid,
                )
            premise_exprs, premises_ok = _premise_expressions(res, tid, root, guarantees, rule="K6")
            goal_guarantee = guarantees.get((tid, target["goal"]))
            if goal_guarantee is None:
                _add(
                    res,
                    "K6",
                    f"{tid}: composition goal {target['goal']!r} has no formula on the root node",
                    node=tid,
                )
            elif goal_guarantee.get("sort") != "Bool":
                _add(
                    res,
                    "K6",
                    f"{tid}: composition goal has sort {goal_guarantee.get('sort')!r}; expected Bool",
                    node=tid,
                )
            elif premises_ok:
                ok, detail = smt_checker.check_implication(
                    premise_exprs,
                    goal_guarantee["expr"],
                    payload.get("smt2"),
                    payload.get("timeout_ms"),
                )
                if not ok:
                    _add(res, "K6", f"{tid}: composition implication rejected: {detail}", node=tid)
            if "artifact" in comp:
                _check_artifact(res, comp["artifact"], base, tid, allow_missing_artifacts)

    # K7: non-primary model nodes must be discharged by a checked derivation.
    # A node on an intermediate model is anchored when it supports, transitively
    # through same-model premises, a checked transfer on a target derivation
    # path.  This permits a separated proof (engine/SMT facts, a checked root,
    # then one transfer) without weakening the transfer edge itself.
    for node in proof["nodes"]:
        nid = node["id"]
        if node["certificate"]["evidence"] == "TCB":
            continue
        if node["model"] == primary:
            if "reuse" in node:
                _add(res, "K7", f"{nid}: primary-model node carries a reuse block", severity="warning", node=nid)
            continue
        if "reuse" in node:
            continue
        if nid in anchored:
            continue
        if nid not in all_closures:
            # Unused nodes are harmless but cannot claim a proof role.
            _add(
                res,
                "K7",
                f"{nid}: non-primary model node is outside every target derivation",
                severity="warning",
                node=nid,
            )
            continue
        _add(res, "K7", f"{nid}: non-primary model node has no checked transfer discharge", node=nid)

    # K9: helper hygiene. Scan declared helpers and assertion files.
    for helper in proof.get("helpers", []):
        path = resolve_path(base, helper["path"])
        if not os.path.exists(path):
            _add(res, "K9", f"helper file missing: {helper['path']}")
            continue
        text = read_text(path)
        scanned.add(path)
        for pat in TAUTOLOGY_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE):
                _add(res, "K9", f"helper {helper['path']} contains a tautological assertion")
                break
        for assertion in helper.get("asserts", []):
            if assertion["node"] not in nodes:
                _add(res, "K9", f"helper {helper['path']} cites unknown node {assertion['node']}")
            if not re.search(rf"\b{re.escape(assertion['name'])}\b", text):
                _add(
                    res,
                    "K9",
                    f"helper {helper['path']} does not contain assertion {assertion['name']!r}",
                )

    # Also scan any assertion file referenced by a certificate but not declared
    # as a helper, so an unlisted vacuous file cannot hide.
    for node in proof["nodes"]:
        assertion = node["certificate"].get("assertion") if isinstance(node["certificate"], dict) else None
        if not assertion:
            continue
        path = resolve_path(base, assertion["file"])
        if path in scanned or not os.path.exists(path):
            continue
        text = read_text(path)
        scanned.add(path)
        for pat in TAUTOLOGY_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE):
                _add(res, "K9", f"assertion file {assertion['file']} contains a tautological assertion", node=node["id"])
                break

    # K10: proposals are not verdicts.
    metadata = proof.get("metadata", {})
    planner = metadata.get("planner")
    if isinstance(planner, dict):
        for key in ("status", "verdict", "claim", "level"):
            if key in planner:
                _add(res, "K10", f"planner metadata contains forbidden verdict field {key!r}")
    for key in ("status", "verdict", "claim_level", "level"):
        if key in metadata:
            _add(res, "K10", f"proof metadata contains forbidden verdict field {key!r}")
    for node in proof["nodes"]:
        for key in ("status", "planner_status", "planner_claim"):
            if key in node:
                _add(res, "K10", f"{node['id']}: obligation carries planner/status field {key!r}", node=node["id"])
    if case["run_policy"]["mode"] == "blind" and metadata.get("run_mode") != "blind":
        _add(
            res,
            "K10",
            "case run_policy is blind but proof metadata does not record run_mode='blind'",
            severity="warning",
        )

    # K11: cut contracts and helper discipline.  A cut is a pattern over the
    # obligation graph, not a new assumption: its entry/step/exit/link facts are
    # premises, its guard partition must be a checked coverage node, and any
    # assumption cut must name declared TCB helpers.  A helper is an obligation
    # with a role, never a free premise.
    consumers: dict[str, list[str]] = {}
    for node in proof["nodes"]:
        for req in node.get("requires", []):
            consumers.setdefault(req["node"], []).append(node["id"])
    for target in proof["targets"]:
        for req in target["requires"]:
            consumers.setdefault(req["node"], []).append(target["id"])

    cut_roles = {"interface", "observe", "invariant", "transfer", "abstraction_gate"}
    for node in proof["nodes"]:
        nid = node["id"]
        cut = node.get("cut")
        helper = node.get("helper")
        if cut is None and helper is None:
            continue
        if not any(other != nid for other in consumers.get(nid, [])):
            _add(res, "K11", f"{nid}: cut/helper is not consumed by any obligation or target", node=nid)

        if cut is not None:
            if node["role"] not in cut_roles:
                _add(
                    res,
                    "K11",
                    f"{nid}: role {node['role']!r} cannot carry a cut contract",
                    node=nid,
                )
            reqs = {_premise(req) for req in node.get("requires", [])}
            refs: list[tuple[str, str]] = []
            for part in ("entry", "step", "exit", "link"):
                for ref in cut.get(part, []):
                    refs.append(_premise(ref))
                    if _premise(ref) not in reqs:
                        _add(
                            res,
                            "K11",
                            f"{nid}: cut.{part} references {ref['node']}.{ref['guarantee']} "
                            "but the node does not require it",
                            node=nid,
                        )
            if not refs:
                _add(res, "K11", f"{nid}: cut contract has no entry/step/exit/link facts", node=nid)

            if cut.get("guards"):
                coverage_ref = cut.get("coverage")
                if not coverage_ref:
                    _add(
                        res,
                        "K11",
                        f"{nid}: guarded cut has no coverage premise",
                        node=nid,
                    )
                else:
                    cov_node = nodes.get(coverage_ref["node"])
                    if cov_node is None or cov_node["role"] != "coverage":
                        _add(
                            res,
                            "K11",
                            f"{nid}: cut coverage {coverage_ref['node']} is not a coverage node",
                            node=nid,
                        )
                    else:
                        provided = {g["name"] for g in cov_node["provides"]}
                        if coverage_ref["guarantee"] not in provided:
                            _add(
                                res,
                                "K11",
                                f"{nid}: cut coverage guarantee "
                                f"{coverage_ref['node']}.{coverage_ref['guarantee']} is not provided",
                                node=nid,
                            )
                        cut_guards = {g["name"] for g in cut["guards"]}
                        cov_guards = {
                            g["name"] for g in (cov_node.get("coverage") or {}).get("guards", [])
                        }
                        if cut_guards != cov_guards:
                            _add(
                                res,
                                "K11",
                                f"{nid}: cut guard names do not match coverage node {coverage_ref['node']}",
                                node=nid,
                            )

            assumptions = set(cut.get("assumptions", []))
            if cut.get("assumption_cut"):
                if not assumptions:
                    _add(
                        res,
                        "K11",
                        f"{nid}: assumption cut names no assumption helper",
                        node=nid,
                    )
                deps = _deps(nid)
                for aid in sorted(assumptions):
                    assumption = nodes.get(aid)
                    if assumption is None:
                        _add(res, "K11", f"{nid}: assumption helper {aid} does not exist", node=nid)
                    elif assumption["certificate"]["evidence"] != "TCB":
                        _add(
                            res,
                            "K11",
                            f"{nid}: assumption helper {aid} is not a TCB leaf",
                            node=nid,
                        )
                    elif (assumption.get("helper") or {}).get("kind") != "assumption":
                        _add(
                            res,
                            "K11",
                            f"{nid}: assumption helper {aid} is not declared with helper.kind=assumption",
                            node=nid,
                        )
                    elif aid not in deps:
                        _add(
                            res,
                            "K11",
                            f"{nid}: assumption helper {aid} is not a dependency of the cut",
                            node=nid,
                        )
                    elif aid not in tcb_allowed.get(nid, set()):
                        _add(
                            res,
                            "K11",
                            f"{nid}: assumption helper {aid} is not declared by a depending target",
                            node=nid,
                        )
            elif assumptions:
                _add(
                    res,
                    "K11",
                    f"{nid}: cut names assumptions without assumption_cut=true",
                    node=nid,
                )
            tcb_deps = {
                dep for dep in _deps(nid)
                if dep in nodes and nodes[dep]["certificate"]["evidence"] == "TCB"
            }
            unlabelled = tcb_deps - assumptions
            if unlabelled:
                _add(
                    res,
                    "K11",
                    f"{nid}: cut depends on TCB not named in cut.assumptions: "
                    + ", ".join(sorted(unlabelled)),
                    severity="warning",
                    node=nid,
                )

        if helper is not None:
            if node["role"] == "compose":
                _add(res, "K11", f"{nid}: a compose root cannot be a helper", node=nid)
            kind = helper.get("kind")
            evidence = node["certificate"]["evidence"]
            if kind == "monitor":
                if node["model"] != primary:
                    _add(res, "K11", f"{nid}: monitor helper must use the primary model", node=nid)
                if evidence not in {"REPLAY", "CHECKED"}:
                    _add(
                        res,
                        "K11",
                        f"{nid}: monitor helper must be REPLAY or CHECKED, not {evidence}",
                        node=nid,
                    )
                elif evidence == "REPLAY" and node["certificate"].get("verdict") != "proved":
                    _add(
                        res,
                        "K11",
                        f"{nid}: monitor helper has non-proof verdict "
                        f"{node['certificate'].get('verdict')!r}",
                        node=nid,
                    )
                if cut is not None and cut.get("assumption_cut"):
                    _add(
                        res,
                        "K11",
                        f"{nid}: monitor helper cannot be an assumption cut",
                        node=nid,
                    )
            elif kind == "assumption":
                if evidence != "TCB":
                    _add(
                        res,
                        "K11",
                        f"{nid}: assumption helper must be an explicit TCB leaf",
                        node=nid,
                    )
                if cut is not None and not cut.get("assumption_cut"):
                    _add(
                        res,
                        "K11",
                        f"{nid}: assumption helper is on a cut that is not marked assumption_cut",
                        node=nid,
                    )
                if nid not in tcb_allowed.get(nid, set()):
                    _add(
                        res,
                        "K11",
                        f"{nid}: assumption helper is not declared by a depending target",
                        node=nid,
                    )
            elif kind == "submodel":
                if node["model"] == primary:
                    _add(res, "K11", f"{nid}: submodel helper is on the primary model", node=nid)
                if "reuse" not in node:
                    _add(
                        res,
                        "K11",
                        f"{nid}: submodel helper has no reuse/transfer obligation",
                        node=nid,
                    )

    # K12: complete acceptance.  This is deliberately stricter than the
    # legacy rules above: the default is that every design fact in the target
    # closure is a checked/replayed proof, every helper assertion and
    # assumption is declared and bound to a proof, and the target composition
    # is a checked implication.  TCBs are limited to the official front-end,
    # engines/checkers, and the official ISA model; they may support a lemma
    # but may not be a direct target premise.
    if _complete_mode(case, proof):
        if allow_missing_artifacts:
            _add(
                res,
                "K12",
                "complete acceptance does not permit missing-artifact overrides",
            )

        closure_all: set[str] = set()
        for target in proof["targets"]:
            tid = target["id"]
            closure_all.add(tid)
            closure_all.update(_deps(tid))
            if target["tcb"]:
                _add(
                    res,
                    "K12",
                    f"{tid}: complete acceptance forbids direct TCBs in target.tcb",
                    node=tid,
                )
            if target["composition"]["mode"] != "CHECKED":
                _add(
                    res,
                    "K12",
                    f"{tid}: complete acceptance requires a CHECKED target composition",
                    node=tid,
                )
            root = nodes.get(tid)
            if root is not None:
                if root["certificate"]["evidence"] != "CHECKED":
                    _add(
                        res,
                        "K12",
                        f"{tid}: complete target root must be a CHECKED composition",
                        node=tid,
                    )
                if root["certificate"].get("verdict") != "proved":
                    _add(
                        res,
                        "K12",
                        f"{tid}: complete target root has non-proof verdict "
                        f"{root['certificate'].get('verdict')!r}",
                        node=tid,
                    )
            for req in target["requires"]:
                dep = nodes.get(req["node"])
                if dep is not None and dep["certificate"]["evidence"] == "TCB":
                    _add(
                        res,
                        "K12",
                        f"{tid}: complete acceptance forbids a direct TCB target premise {req['node']}",
                        node=tid,
                    )

        for nid in sorted(closure_all):
            node = nodes.get(nid)
            if node is None:
                continue
            cert = node["certificate"]
            evidence = cert["evidence"]
            helper = node.get("helper") or {}
            cut = node.get("cut") or {}
            if evidence == "TCB":
                kind = cert.get("kind")
                if kind not in OFFICIAL_TCB_KINDS:
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance only permits official TCB kinds "
                        f"{sorted(OFFICIAL_TCB_KINDS)}, not {kind!r}",
                        node=nid,
                    )
                if helper.get("kind") == "assumption":
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance forbids assumption-helper TCBs",
                        node=nid,
                    )
            else:
                if evidence not in {"CHECKED", "REPLAY"}:
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance requires CHECKED or REPLAY evidence, "
                        f"not {evidence!r}",
                        node=nid,
                    )
                if cert.get("verdict") != "proved":
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance requires verdict 'proved', "
                        f"not {cert.get('verdict')!r}",
                        node=nid,
                    )
                if len(node.get("provides", [])) != 1:
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance requires exactly one guarantee per proof node",
                        node=nid,
                    )
                elif cert.get("goal") != node["provides"][0]["name"]:
                    _add(
                        res,
                        "K12",
                        f"{nid}: certificate goal {cert.get('goal')!r} must be the node's "
                        f"single guarantee {node['provides'][0]['name']!r}",
                        node=nid,
                    )
                if helper.get("kind") == "assumption":
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance forbids design assumption helpers",
                        node=nid,
                    )
                if cut.get("assumption_cut"):
                    _add(
                        res,
                        "K12",
                        f"{nid}: complete acceptance forbids assumption cuts",
                        node=nid,
                    )
            if node.get("role") == "compose" and evidence != "CHECKED":
                _add(
                    res,
                    "K12",
                    f"{nid}: compose nodes must be CHECKED in complete mode",
                    node=nid,
                )

        # Design TCBs are forbidden even when they are not reachable from the
        # accepted target.  This keeps a package from hiding a design trust
        # boundary in an unused branch.
        for node in proof["nodes"]:
            cert = node["certificate"]
            helper = node.get("helper") or {}
            cut = node.get("cut") or {}
            if helper.get("kind") == "assumption":
                _add(
                    res,
                    "K12",
                    f"{node['id']}: complete acceptance forbids assumption-helper nodes",
                    node=node["id"],
                )
            if cut.get("assumption_cut"):
                _add(
                    res,
                    "K12",
                    f"{node['id']}: complete acceptance forbids assumption cuts",
                    node=node["id"],
                )
            if cert["evidence"] != "TCB":
                continue
            if cert.get("kind") not in OFFICIAL_TCB_KINDS:
                _add(
                    res,
                    "K12",
                    f"{node['id']}: complete acceptance forbids TCB kind {cert.get('kind')!r}",
                    node=node["id"],
                )

        # Every assertion/assumption in a declared helper must be named and
        # bound to a proved node.  This prevents an unlisted helper assertion
        # from becoming an unproved premise.
        for helper in proof.get("helpers", []):
            path = resolve_path(base, helper["path"])
            if not os.path.exists(path):
                continue  # K9 already reports the missing file
            raw = read_text(path)
            if helper.get("sha256"):
                actual = sha256_file(path)
                if actual != helper["sha256"]:
                    _add(
                        res,
                        "K12",
                        f"helper {helper['path']} hash mismatch: expected "
                        f"{helper['sha256']}, got {actual}",
                    )
            text = _strip_comments(raw)
            declared_asserts = {a["name"]: a for a in helper.get("asserts", [])}
            declared_assumes = {a["name"]: a for a in helper.get("assumes", [])}
            file_asserts, unnamed_asserts = _helper_events(text, "assert")
            file_assumes, unnamed_assumes = _helper_events(text, "assume")
            if unnamed_asserts:
                _add(
                    res,
                    "K12",
                    f"helper {helper['path']} has {unnamed_asserts} unnamed assertion(s); "
                    "complete mode requires every assertion to be labelled",
                )
            if unnamed_assumes:
                _add(
                    res,
                    "K12",
                    f"helper {helper['path']} has {unnamed_assumes} unnamed assumption(s); "
                    "complete mode requires every assumption to be labelled and proved",
                )
            for name in sorted(file_asserts - set(declared_asserts)):
                _add(
                    res,
                    "K12",
                    f"helper {helper['path']} assertion {name!r} is not declared in helper.asserts",
                )
            for name in sorted(file_assumes - set(declared_assumes)):
                _add(
                    res,
                    "K12",
                    f"helper {helper['path']} assumption {name!r} is not declared in helper.assumes",
                )
            for kind, declared, file_names in (
                ("assert", declared_asserts, file_asserts),
                ("assume", declared_assumes, file_assumes),
            ):
                for name, entry in sorted(declared.items()):
                    if name not in file_names:
                        _add(
                            res,
                            "K12",
                            f"helper {helper['path']} does not contain {kind} {name!r}",
                        )
                    dep = nodes.get(entry["node"])
                    if dep is None:
                        _add(
                            res,
                            "K12",
                            f"helper {helper['path']} cites unknown node {entry['node']}",
                        )
                        continue
                    dep_cert = dep["certificate"]
                    dep_evidence = dep_cert["evidence"]
                    if kind == "assume" and entry["node"] not in closure_all:
                        _add(
                            res,
                            "K12",
                            f"helper {helper['path']} assumption {name!r} is bound to "
                            f"non-target node {entry['node']}",
                        )
                    if kind == "assert":
                        if dep_evidence == "TCB":
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assertion {name!r} is bound to a TCB",
                            )
                        elif dep_evidence not in {"CHECKED", "REPLAY"}:
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assertion {name!r} is bound to "
                                f"unsupported evidence {dep_evidence!r}",
                            )
                        elif dep_cert.get("verdict") != "proved":
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assertion {name!r} is bound to "
                                f"non-proved node {entry['node']}",
                            )
                        assertion = dep_cert.get("assertion") or {}
                        if assertion.get("name") != name:
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assertion {name!r} is bound to "
                                f"node {entry['node']} whose certificate assertion is "
                                f"{assertion.get('name')!r}",
                            )
                        if assertion.get("file") != helper["path"]:
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assertion {name!r} is bound to "
                                f"node {entry['node']} whose certificate assertion file is "
                                f"{assertion.get('file')!r}",
                            )
                    else:
                        if dep_evidence == "TCB":
                            if dep_cert.get("kind") not in OFFICIAL_TCB_KINDS:
                                _add(
                                    res,
                                    "K12",
                                    f"helper {helper['path']} assumption {name!r} is bound to "
                                    f"a non-official TCB",
                                )
                        elif dep_cert.get("verdict") != "proved":
                            _add(
                                res,
                                "K12",
                                f"helper {helper['path']} assumption {name!r} is bound to "
                                f"non-proved node {entry['node']}",
                            )

    # K13: model/representation boundaries are obligations, not Boolean aliases.
    complete = _complete_mode(case, proof)
    guard = {"status": "not_required", "checked_edges": {}, "unresolved": []}
    store = composition_checker.ModelStore(proof, base)
    has_projections = False
    for nid, node in nodes.items():
        cert = node["certificate"]
        fmt = cert.get("format")
        message = None
        if fmt == composition_checker.FORMAT:
            has_projections = True
            try:
                guard["checked_edges"][nid] = composition_checker.check_projection(node, nodes, store)
            except (composition_checker.CompositionError, ValueError, KeyError, OSError, TypeError) as exc:
                message = f"{nid}: projection rejected: {exc}"
        elif fmt == model_smt_checker.FORMAT:
            has_projections = True
            try:
                guard["checked_edges"][nid] = model_smt_checker.check(node, nodes, store)
            except (ValueError, KeyError, OSError, TypeError, RecursionError, z3.Z3Exception) as exc:
                message = f"{nid}: model-bound SMT rejected: {exc}"
        else:
            crosses = any(
                r["node"] in nodes
                and nodes[r["node"]]["model"] != node["model"]
                and nodes[r["node"]]["certificate"]["evidence"] != "TCB"
                for r in node.get("requires", [])
            )
            if crosses:
                message = f"{nid}: cross-model premise requires a checked btor-projection; Boolean implication is insufficient"
        if message:
            guard["unresolved"].append({"node": nid, "reason": message})
            _add(res, "K13", message, node=nid, severity="error" if complete or fmt in {composition_checker.FORMAT, model_smt_checker.FORMAT} else "warning")
        if complete and fmt == "smt-induction":
            message = f"{nid}: RTL-to-arithmetic lifting is unsupported; an induction over a supplied recurrence is not a model binding"
            guard["unresolved"].append({"node": nid, "reason": message})
            _add(res, "K13", message, node=nid)
        if complete and fmt == "poly":
            # Guarantees currently carry Int arithmetic. A modular polynomial
            # identity cannot be consumed as an integer equality without a lift.
            for guarantee in node["provides"]:
                try:
                    script = expr_checker.canonical_script([], guarantee["expr"])
                    ok, detail = smt_checker.check_implication([], guarantee["expr"], script)
                except (ValueError, TypeError) as exc:
                    ok, detail = False, str(exc)
                if not ok:
                    _add(res, "K13", f"{nid}: modular polynomial has no valid Int interpretation: {detail}", node=nid)
    if complete:
        for helper in proof.get("helpers", []):
            for assumption in helper.get("assumes", []):
                matched = False
                for edge_id, record in guard["checked_edges"].items():
                    if record.get("kind") != composition_checker.FORMAT or record.get("source_model") != helper.get("model"):
                        continue
                    ref = assumption.get("constraint")
                    witness = nodes[edge_id]["certificate"]["payload"].get("discharge", {}).get(ref, {})
                    if ref in record.get("discharged_constraints", {}) and witness.get("node") == assumption["node"]:
                        matched = True
                        break
                if not matched:
                    nid = assumption["node"]
                    message = f"{nid}: helper assumption needs a model/constraint binding to a checked discharge edge"
                    guard["unresolved"].append({"node": nid, "reason": message})
                    _add(res, "K13", message, node=nid)
    # The case, not the proposed certificate format, selects formal target
    # binding. Dropping all guarded nodes must not bypass required_properties.
    if has_projections or any(t.get("required_properties") for t in case["targets"]):
        try:
            composition_checker.check_targets(case, proof, nodes, store)
        except (composition_checker.CompositionError, ValueError, KeyError, OSError, TypeError) as exc:
            message = f"guarded target binding rejected: {exc}"
            guard["unresolved"].append({"node": "targets", "reason": message})
            _add(res, "K13", message)
    if guard["unresolved"]:
        guard["status"] = "incomplete" if complete else "legacy_unchecked"
    elif guard["checked_edges"]:
        guard["status"] = "checked"
    res.composition = guard

    # Computed levels. Include transitive dependencies so a CHECKED transfer
    # never upgrades the assurance of the engine evidence it consumes.
    for target in proof["targets"]:
        root = nodes.get(target["id"])
        if root is None:
            continue
        req_nodes = [nodes[nid] for nid in _deps(target["id"]) if nid in nodes]
        tcb = set(target["tcb"])
        non_tcb = [n for n in req_nodes if n["certificate"]["evidence"] != "TCB"]
        if non_tcb:
            evidence = min(
                (n["certificate"]["evidence"] for n in non_tcb),
                key=lambda e: EVIDENCE_RANK[e],
            )
        else:
            evidence = "TCB"
        tcb_deps = {
            dep for dep in _deps(target["id"]) | {target["id"]}
            if dep in nodes and nodes[dep]["certificate"]["evidence"] == "TCB"
        }
        res.targets[target["id"]] = {
            "evidence": evidence,
            "composition": target["composition"]["mode"],
            "tcb": sorted(tcb),
            "tcb_deps": sorted(tcb_deps),
            "premises": sorted(f"{p[0]}.{p[1]}" for p in (_premise(r) for r in target["requires"])),
        }

    # Final acceptance is computed, never stored in the proof package.  The
    # complete policy requires a fully discharged obligation ledger; legacy
    # packages remain readable for development but are not complete proofs.
    disposition_result = disposition.classify(case, proof, res.errors)
    res.status = disposition_result.status
    res.obligations = [o.as_dict() for o in disposition_result.obligations]
    res.residual = [o.as_dict() for o in disposition_result.residual]
    res.fatal_errors = disposition_result.fatal_errors
    if _complete_mode(case, proof):
        res.accepted = res.status == "proved"
    else:
        res.accepted = not res.errors
    return res


def evaluate(
    case: dict[str, Any],
    proof: dict[str, Any],
    base: str,
    allow_missing_artifacts: bool = False,
) -> CheckResult:
    """Validate and check already-loaded documents."""
    res = CheckResult()
    registry = _registry()
    for name, doc in (("case", case), ("proof", proof)):
        schema_errors = _validate(doc, name, registry)
        if schema_errors:
            for error in schema_errors:
                _add(res, "K1", f"schema {name}: {_err_path(error)}: {error.message}")
            return res
    return _semantic_checks(case, proof, base, allow_missing_artifacts)


def check_paths(
    case_path: str,
    proof_path: str,
    allow_missing_artifacts: bool = False,
) -> CheckResult:
    case = load_json_or_yaml(case_path)
    proof = load_json_or_yaml(proof_path)
    base = os.path.dirname(os.path.abspath(proof_path))
    return evaluate(case, proof, base, allow_missing_artifacts)


def _print_human(result: CheckResult) -> None:
    if result.status == "proved":
        print("ACCEPT (PROVED)")
    elif result.status == "needs_check":
        print("NEEDS_CHECK")
    else:
        print("REJECT")
    print(f"status: {result.status}")
    if result.composition:
        print(f"composition guard: {result.composition['status']}")
    if result.node_evidence:
        print("node evidence:")
        for nid in sorted(result.node_evidence):
            print(f"  {nid}: {result.node_evidence[nid]}")
    if result.targets:
        print("targets:")
        for tid in sorted(result.targets):
            t = result.targets[tid]
            tcb = ",".join(t["tcb"]) if t["tcb"] else "-"
            tcb_deps = ",".join(t.get("tcb_deps", [])) if t.get("tcb_deps") else "-"
            print(
                f"  {tid}: leaf={t['evidence']} composition={t['composition']} "
                f"tcb={tcb} tcb_deps={tcb_deps}"
            )
    if result.residual:
        print("residual:")
        for ob in result.residual:
            print(f"  {ob['id']}: {ob.get('reason') or ob.get('direction')}")
    if result.errors:
        print("errors:")
        for issue in result.errors:
            print(f"  [{issue.rule}] {issue.message}")
    if result.warnings:
        print("warnings:")
        for issue in result.warnings:
            print(f"  [{issue.rule}] {issue.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pcd-kernel", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="offline schema + kernel check")
    p_check.add_argument("--case", required=True)
    p_check.add_argument("--proof", required=True)
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument(
        "--allow-missing-artifacts",
        action="store_true",
        help="dev only: downgrade missing artifact/log errors to warnings",
    )
    sub.add_parser("selftest", help="run the kernel unit tests")
    args = parser.parse_args(argv)

    if args.command == "selftest":
        import subprocess

        cmd = [sys.executable, "-m", "unittest", "discover", "-s", os.path.join(ROOT, "tests"), "-v"]
        return subprocess.call(cmd, cwd=ROOT)

    try:
        result = check_paths(args.case, args.proof, args.allow_missing_artifacts)
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed with a reason
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result.status == "proved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
