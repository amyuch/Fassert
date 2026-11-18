#!/usr/bin/env python3
"""Computed proof disposition: proved, needs_check, or reject.

The proof package never stores a status tag.  The kernel derives the status from
the case contract and the attempted derivation:

* ``reject`` means the package contains invalid or refuted evidence (or the case
  is malformed).  It is not a claim that the design is false.
* ``needs_check`` means the derivation is well formed but at least one required
  obligation has no valid witness.  The open obligations are the residual.
* ``proved`` means every required obligation in the target closure is
  discharged under the explicit TCB.

This module deliberately does not import the kernel.  It consumes plain case,
proof, and issue records so the status can be audited independently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

PROVED = "proved"
NEEDS_CHECK = "needs_check"
REJECT = "reject"

OFFICIAL_TCB_KINDS = {"frontend", "engine", "checker", "isa_model"}

# Rules whose failures mean the supplied evidence itself is invalid, not merely
# that a required obligation is still open.
_FATAL_RULES = {"K1", "K2", "K8", "K9", "K10"}


@dataclass
class Obligation:
    """One required subgoal of the target claim."""

    id: str
    kind: str
    origin: str
    required: bool = True
    discharged: bool = False
    model: str | None = None
    formula: str | None = None
    direction: str | None = None
    reason: str | None = None
    evidence: str | None = None
    fatal: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "origin": self.origin,
            "required": self.required,
            "discharged": self.discharged,
            "model": self.model,
            "formula": self.formula,
            "direction": self.direction,
            "reason": self.reason,
            "evidence": self.evidence,
            "fatal": self.fatal,
        }


@dataclass
class Disposition:
    status: str
    obligations: list[Obligation] = field(default_factory=list)
    residual: list[Obligation] = field(default_factory=list)
    fatal_errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "obligations": [o.as_dict() for o in self.obligations],
            "residual": [o.as_dict() for o in self.residual],
            "fatal_errors": list(self.fatal_errors),
        }


def _issue_fields(issue: Any) -> tuple[str, str, str | None]:
    if isinstance(issue, dict):
        return (
            str(issue.get("rule", "?")),
            str(issue.get("message", "")),
            issue.get("node"),
        )
    return (
        str(getattr(issue, "rule", "?")),
        str(getattr(issue, "message", "")),
        getattr(issue, "node", None),
    )


def _is_fatal(issue: Any) -> bool:
    rule, message, _ = _issue_fields(issue)
    if rule in _FATAL_RULES:
        return True
    if rule == "K3" and "cycle" in message:
        return True
    if "counterexample" in message.lower() or "'cex'" in message.lower():
        return True
    # A rejected composition implication or a malformed bound payload is an
    # invalid witness.  A missing premise or an unproved target is open.
    if rule == "K6" and (
        "composition implication rejected" in message
        or "payload premise" in message
        or "payload goal" in message
        or "composition payload" in message
    ):
        return True
    if rule == "K11":
        # A malformed helper/cut package is not a conditional proof.
        return True
    if rule == "K12":
        open_markers = (
            "requires a CHECKED target composition",
            "complete target root must be a CHECKED composition",
            "complete target root has non-proof verdict",
            "complete acceptance requires CHECKED or REPLAY evidence",
            "complete acceptance requires verdict 'proved'",
            "compose nodes must be CHECKED in complete mode",
        )
        if any(marker in message for marker in open_markers):
            return False
        return True
    if rule == "K13" and (
        "hash mismatch" in message
        or "missing or changed model" in message
        or "forged" in message
        or "counterexample" in message
    ):
        return True
    return False


def _add(
    obligations: dict[str, Obligation],
    ob: Obligation,
) -> None:
    previous = obligations.get(ob.id)
    if previous is None:
        obligations[ob.id] = ob
        return
    # Keep a fatal/refuted record stronger than a merely open one.
    if ob.fatal and not previous.fatal:
        obligations[ob.id] = ob
    elif ob.discharged and not previous.discharged:
        obligations[ob.id] = ob


def _premise_key(req: dict[str, Any]) -> tuple[str, str]:
    return (str(req.get("node")), str(req.get("guarantee")))


def _closure(root: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
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
            dep = str(req.get("node"))
            if dep in nodes and dep not in seen:
                pending.append(dep)
    return seen


def _support_cone(root: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
    """Transitive same-model premise support of a node."""
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
            dep = str(req.get("node"))
            if dep in nodes and dep not in seen:
                pending.append(dep)
    return seen


def _checked_transfer_node(node: dict[str, Any]) -> bool:
    cert = node.get("certificate") or {}
    return (
        node.get("role") == "transfer"
        and cert.get("evidence") == "CHECKED"
        and cert.get("verdict") == "proved"
    )


def _anchored(
    nid: str,
    closure: set[str],
    nodes: dict[str, dict[str, Any]],
) -> bool:
    """A non-primary node is discharged if a checked transfer on this target
    derivation depends on it through same-model premises.

    This generalises the old direct ``reuse.transfer_node`` edge: an internal
    fact may support an intermediate root, and the transfer may carry that root
    rather than naming the fact directly.
    """
    for tid in closure:
        transfer = nodes.get(tid)
        if transfer is None or not _checked_transfer_node(transfer):
            continue
        for req in transfer.get("requires", []):
            dep = str(req.get("node"))
            if dep in nodes and nid in _support_cone(dep, nodes):
                return True
    return False


def _required_properties(
    case: dict[str, Any],
    proof: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    target: dict[str, Any],
) -> list[str]:
    case_targets = {str(t.get("id")): t for t in case.get("targets", [])}
    case_target = case_targets.get(str(target.get("id"))) or {}
    required = list(case_target.get("required_properties") or [])
    if not required:
        return []
    primary = str(proof.get("primary_model"))
    closure = _closure(str(target.get("id")), nodes)
    bound: set[str] = set()
    for nid in closure:
        node = nodes.get(nid) or {}
        if str(node.get("model")) != primary:
            continue
        for guarantee in node.get("provides", []):
            binding = guarantee.get("binding") or {}
            if binding.get("kind") == "btor-bad" and binding.get("property"):
                bound.add(str(binding["property"]))
    return [name for name in required if name not in bound]


def _complete_mode(case: dict[str, Any], proof: dict[str, Any]) -> bool:
    case_policy = case.get("acceptance", "complete")
    proof_policy = proof.get("acceptance", "complete")
    metadata_policy = (proof.get("metadata") or {}).get("completeness", "complete")
    return not (case_policy == proof_policy == metadata_policy == "legacy")


def elaborate(
    case: dict[str, Any],
    proof: dict[str, Any],
    errors: Iterable[Any],
) -> tuple[dict[str, Obligation], list[dict[str, Any]]]:
    """Elaborate the target obligations and fold in local checker failures."""
    nodes: dict[str, dict[str, Any]] = {}
    for node in proof.get("nodes", []):
        nid = str(node.get("id"))
        nodes[nid] = node

    by_node: dict[str, list[Any]] = {}
    fatal_errors: list[dict[str, Any]] = []
    for issue in errors:
        rule, message, node = _issue_fields(issue)
        if node:
            by_node.setdefault(str(node), []).append(issue)
        if _is_fatal(issue):
            fatal_errors.append({"rule": rule, "message": message, "node": node})

    obligations: dict[str, Obligation] = {}
    complete = _complete_mode(case, proof)

    if not complete:
        _add(
            obligations,
            Obligation(
                id="mode.complete",
                kind="mode",
                origin="case acceptance policy",
                model=str(proof.get("primary_model")),
                formula="complete acceptance",
                direction="legacy mode is not a complete proof",
                reason="proof is declared legacy; the theorem requires complete acceptance",
                evidence="legacy",
            ),
        )

    proof_targets = {str(t.get("id")): t for t in proof.get("targets", [])}
    case_targets = {str(t.get("id")): t for t in case.get("targets", [])}
    if set(proof_targets) != set(case_targets):
        _add(
            obligations,
            Obligation(
                id="targets.coverage",
                kind="coverage",
                origin="case targets",
                formula="proof targets = case targets",
                reason="the proof does not cover exactly the declared case targets",
            ),
        )

    for tid, target in proof_targets.items():
        root = nodes.get(tid)
        if root is None:
            _add(
                obligations,
                Obligation(
                    id=f"target.{tid}.root",
                    kind="target",
                    origin="target root",
                    model=str(target.get("model")),
                    formula=str(target.get("goal")),
                    direction="root must be proved on the target model",
                    reason="target has no root obligation",
                ),
            )
            continue

        root_cert = root.get("certificate") or {}
        root_ok = (
            root_cert.get("evidence") in {"CHECKED", "REPLAY"}
            and root_cert.get("verdict") == "proved"
        )
        composition = target.get("composition") or {}
        comp_ok = composition.get("mode") == "CHECKED"
        model_ok = str(root.get("model")) == str(target.get("model"))
        _add(
            obligations,
            Obligation(
                id=f"target.{tid}.root",
                kind="target",
                origin="target root",
                model=str(target.get("model")),
                formula=str(target.get("goal")),
                direction="root must be a CHECKED composition on the target model",
                reason=(
                    None if root_ok and comp_ok and model_ok
                    else "root evidence or target composition is not a complete proof"
                ),
                evidence=str(root_cert.get("evidence")),
                discharged=bool(root_ok and comp_ok and model_ok),
            ),
        )

        for name in _required_properties(case, proof, nodes, target):
            _add(
                obligations,
                Obligation(
                    id=f"target.{tid}.property.{name}",
                    kind="target-property",
                    origin="case required_properties",
                    model=str(target.get("model")),
                    formula=name,
                    direction="required property must be bound in the target closure",
                    reason="required case property has no proved destination binding",
                ),
            )

        for nid in sorted(_closure(tid, nodes)):
            node = nodes.get(nid)
            if node is None:
                _add(
                    obligations,
                    Obligation(
                        id=f"premise.{nid}",
                        kind="premise",
                        origin=f"target {tid}",
                        formula=nid,
                        direction="missing premise is an open subgoal",
                        reason="dependency is referenced but not present in the proof",
                    ),
                )
                continue

            cert = node.get("certificate") or {}
            evidence = str(cert.get("evidence"))
            verdict = cert.get("verdict")
            node_issues = by_node.get(nid, [])
            fatal_here = [i for i in node_issues if _is_fatal(i)]
            open_here = [i for i in node_issues if not _is_fatal(i)]

            if fatal_here:
                rule, message, _ = _issue_fields(fatal_here[0])
                _add(
                    obligations,
                    Obligation(
                        id=f"node.{nid}",
                        kind="evidence",
                        origin=f"target {tid}",
                        model=str(node.get("model")),
                        formula=str(cert.get("goal") or nid),
                        direction="local evidence must be valid",
                        reason=f"{rule}: {message}",
                        evidence=evidence,
                        fatal=True,
                    ),
                )
                continue

            if evidence == "TCB":
                official = cert.get("kind") in OFFICIAL_TCB_KINDS
                _add(
                    obligations,
                    Obligation(
                        id=f"tcb.{nid}",
                        kind="tcb",
                        origin=f"target {tid}",
                        model=str(node.get("model")),
                        formula=str(cert.get("tcb") or nid),
                        direction="explicit trust boundary",
                        reason=None if official else "TCB is not an official front-end/engine/checker/ISA boundary",
                        evidence=evidence,
                        discharged=bool(official),
                    ),
                )
                continue

            proved = evidence in {"CHECKED", "REPLAY"} and verdict == "proved"
            reason = None
            if not proved:
                reason = f"node evidence is not a proved certificate (evidence={evidence!r}, verdict={verdict!r})"
            elif open_here:
                rule, message, _ = _issue_fields(open_here[0])
                reason = f"{rule}: {message}"
            _add(
                obligations,
                Obligation(
                    id=f"node.{nid}",
                    kind="evidence",
                    origin=f"target {tid}",
                    model=str(node.get("model")),
                    formula=str(cert.get("goal") or nid),
                    direction="engine/checker witness for this obligation",
                    reason=reason,
                    evidence=evidence,
                    discharged=bool(proved and not open_here),
                ),
            )

            if (
                str(node.get("model")) != str(target.get("model"))
                and evidence != "TCB"
                and not _anchored(nid, _closure(tid, nodes), nodes)
            ):
                _add(
                    obligations,
                    Obligation(
                        id=f"cross-model.{nid}",
                        kind="simulation",
                        origin=f"target {tid}",
                        model=str(node.get("model")),
                        formula=f"{node.get('model')} -> {target.get('model')}",
                        direction="destination executions must be represented in the source model",
                        reason="cross-model premise has no checked refinement/transfer edge",
                        evidence=evidence,
                    ),
                )

    for helper in proof.get("helpers", []):
        for assumption in helper.get("assumes", []):
            hnode = str(assumption.get("node"))
            target = nodes.get(hnode)
            cert = (target or {}).get("certificate") or {}
            ok = cert.get("evidence") in {"CHECKED", "REPLAY"} and cert.get("verdict") == "proved"
            _add(
                obligations,
                Obligation(
                    id=f"helper.assume.{hnode}",
                    kind="helper-assumption",
                    origin=str(helper.get("path") or "helper"),
                    model=str((target or {}).get("model") or helper.get("model")),
                    formula=str(assumption.get("name") or hnode),
                    direction="helper assumption must be discharged on the original model",
                    reason=None if ok else "helper assumption has no proved discharge",
                    evidence=str(cert.get("evidence")) if target else None,
                    discharged=bool(ok),
                ),
            )

    return obligations, fatal_errors


def classify(
    case: dict[str, Any],
    proof: dict[str, Any],
    errors: Iterable[Any],
) -> Disposition:
    """Compute the disposition.  This function never trusts a stored tag."""
    obligations_map, fatal_errors = elaborate(case, proof, errors)
    obligations = list(obligations_map.values())
    residual = [o for o in obligations if o.required and not o.discharged]

    # Every checker error must be accounted for by an obligation.  An error
    # that is not attached to a target-closure obligation is a package-level
    # defect (malformed policy, unused TCB, undeclared helper, ...), not a mere
    # open side condition.  Failing closed here is what keeps a stray error
    # from being hidden by an otherwise complete-looking closure.
    covered_nodes = set()
    for ob in obligations:
        for prefix in ("node.", "premise.", "tcb.", "cross-model.", "helper.assume."):
            if ob.id.startswith(prefix):
                covered_nodes.add(ob.id[len(prefix):])
    for issue in errors:
        if _is_fatal(issue):
            continue
        rule, message, node = _issue_fields(issue)
        if node is None or str(node) not in covered_nodes:
            fatal_errors.append({"rule": rule, "message": message, "node": node})

    if fatal_errors or any(o.fatal for o in obligations):
        return Disposition(REJECT, obligations, residual, fatal_errors)
    if residual:
        return Disposition(NEEDS_CHECK, obligations, residual, [])
    return Disposition(PROVED, obligations, [], [])
