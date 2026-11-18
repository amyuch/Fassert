"""Offline composition inspection and untrusted projection-map proposals."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from checkers import composition
from kernel import kernel
from .core import PcdError, read_json


def inspect(case_path: str, proof_path: str) -> dict[str, Any]:
    result = kernel.check_paths(case_path, proof_path)
    return {
        "accepted": result.accepted,
        "status": result.status,
        "proved": result.proved,
        "composition": result.composition,
        "residual": result.residual,
        "fatal_errors": result.fatal_errors,
        "errors": [issue.as_dict() for issue in result.errors],
    }


def propose(proof_path: str, node_id: str) -> dict[str, Any]:
    proof = read_json(proof_path)
    nodes = {n["id"]: n for n in proof["nodes"]}
    node = nodes.get(node_id)
    if node is None or node.get("role") != "transfer" or len(node.get("requires", [])) != 1:
        raise PcdError("mapping proposals require one transfer node with exactly one source")
    source = node["requires"][0]
    if source["node"] not in nodes:
        raise PcdError("transfer source node is missing")
    store = composition.ModelStore(proof, str(Path(proof_path).resolve().parent))
    try:
        return composition.proposal(nodes[source["node"]]["model"], node["model"],
                                    source["node"], source["guarantee"], store)
    except (ValueError, OSError, KeyError) as exc:
        raise PcdError(str(exc)) from exc
