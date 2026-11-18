"""Stage a case and build its model, recording identity and provenance."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from .core import (
    PcdError,
    as_command,
    canonical_hash,
    hash_stage,
    read_json,
    run_command,
    sha256_file,
    stage_case,
    tool_versions,
    write_json,
)


def run_build(run_dir: Path, case_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir)
    staged = run_dir / "case"
    if not staged.exists():
        stage_case(case_dir, staged)

    stage_hashes = hash_stage(staged)
    case_file = next((staged / n for n in ("case.json", "case.yaml", "case.yml") if (staged / n).is_file()), None)
    recipe = case["build"]["recipe"]
    cwd = staged / recipe.get("cwd", ".")
    timeout_s = int(recipe.get("timeout_s") or case["budgets"]["total_seconds"])
    command = as_command(recipe["command"])
    log_path = run_dir / "logs" / "build.log"

    record: dict[str, Any] = {
        "schema_version": "pcd-build/0.1",
        "case": case["case"],
        "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "staged_case": "case",
        "case_file_sha256": sha256_file(str(case_file)) if case_file else None,
        "stage_sha256": {
            "input": canonical_hash(stage_hashes["input"]),
            "build": canonical_hash(stage_hashes["build"]),
        },
        "recipe": {
            "command": command,
            "cwd": recipe.get("cwd", "."),
            "timeout_s": timeout_s,
            "env": recipe.get("env", {}),
        },
        "tool_versions": {},
        "outputs": [],
        "ok": False,
    }

    result = run_command(
        command,
        cwd=cwd,
        log_path=log_path,
        timeout_s=timeout_s,
        env=recipe.get("env"),
        sandbox=case["run_policy"]["mode"] == "blind",
        sandbox_root=run_dir,
    )
    record["tool_versions"] = tool_versions()
    record["command"] = result
    record["seconds"] = result["seconds"]
    record["timed_out"] = result["timed_out"]

    expected = case["build"].get("expected_model")
    staged_root = staged.resolve()
    for spec in case["build"]["outputs"]:
        path = (staged / spec["path"]).resolve()
        if not path.is_relative_to(staged_root):
            record["outputs"].append(
                {
                    "path": spec["path"],
                    "kind": spec["kind"],
                    "exists": False,
                    "error": "build output escapes the staged case",
                }
            )
            continue
        item: dict[str, Any] = {
            "path": spec["path"],
            "kind": spec["kind"],
            "exists": path.is_file(),
        }
        if path.is_file():
            digest = sha256_file(str(path))
            item["sha256"] = digest
            item["model_id"] = f"{spec['kind']}:{digest}"
            if spec.get("sha256") and spec["sha256"] != digest:
                item["error"] = f"declared output hash {spec['sha256']} != actual {digest}"
        else:
            item["error"] = "missing build output"
        record["outputs"].append(item)

    primary = next((o for o in record["outputs"] if o.get("exists")), None)
    if primary is not None:
        record["model"] = {
            "id": primary["model_id"],
            "kind": primary["kind"],
            "sha256": primary["sha256"],
            "path": primary["path"],
        }

    errors: list[str] = []
    if result["returncode"] != 0:
        errors.append(f"build command exited {result['returncode']}")
    if result["timed_out"]:
        errors.append(f"build exceeded {timeout_s}s")
    for output in record["outputs"]:
        if output.get("error"):
            errors.append(output["error"])
    if primary is None:
        errors.append("no build output was produced")
    if expected is not None and primary is not None:
        if expected["kind"] != primary["kind"] or expected["sha256"] != primary["sha256"]:
            errors.append(
                "expected_model mismatch: "
                f"expected {expected['kind']}:{expected['sha256']}, got {primary['model_id']}"
            )
    record["errors"] = errors
    record["ok"] = not errors
    record["finished_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    write_json(run_dir / "build.json", record)
    if errors:
        raise PcdError("build failed: " + "; ".join(errors) + f" (see {run_dir / 'build.json'})")
    return record


def load_build(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / "build.json"
    if not path.is_file():
        raise PcdError(f"missing build record: {path}")
    record = read_json(path)
    if not record.get("ok") or "model" not in record:
        raise PcdError(f"build is not successful: {path}")
    staged = (Path(run_dir) / "case").resolve()
    model = record["model"]
    model_path = (staged / model["path"]).resolve()
    if not model_path.is_relative_to(staged) or not model_path.is_file():
        raise PcdError(f"build model path is missing or escapes the staged case: {model['path']}")
    if sha256_file(str(model_path)) != model["sha256"]:
        raise PcdError(f"build model hash does not match build.json: {model['path']}")
    return record
