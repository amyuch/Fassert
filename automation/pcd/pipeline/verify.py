"""Offline kernel invocation for a run directory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kernel import kernel

from .core import PcdError, read_json, write_json


def run_check(run_dir: Path, case: dict[str, Any], *, allow_missing_artifacts: bool = False) -> dict[str, Any]:
    run_dir = Path(run_dir)
    proof_path = run_dir / "proof.json"
    if not proof_path.is_file():
        raise PcdError(f"missing proof package: {proof_path}")
    proof = read_json(proof_path)
    result = kernel.evaluate(case, proof, str(run_dir), allow_missing_artifacts=allow_missing_artifacts)
    payload = result.as_dict()
    payload["run_id"] = run_dir.name
    payload["case"] = case["case"]
    write_json(run_dir / "check.json", payload)
    write_json(run_dir / "composition.json", payload.get("composition", {}))
    return payload
