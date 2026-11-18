"""Shared orchestration primitives: cases, staging, run dirs, and commands."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import jsonschema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUTOMATION = ROOT.parent
for _path in (ROOT, AUTOMATION):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common.pcd_util import canonical_json, sha256_file, sha256_json  # noqa: E402

SCHEMA_DIR = ROOT / "schema"
CASES_DIR = ROOT / "cases"
DEFAULT_RUNS_DIR = ROOT / "runs"


class PcdError(RuntimeError):
    """A fail-closed pipeline error with a short, actionable reason."""


def read_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise PcdError(f"{path}: top-level JSON value must be an object")
    return obj


def write_json(path: str | os.PathLike[str], obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, p)


def write_text(path: str | os.PathLike[str], text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(obj: Any) -> str:
    return sha256_json(obj)


def find_case(case: str | os.PathLike[str]) -> Path:
    """Find a case directory from a path, case name, or case file."""
    p = Path(case).expanduser()
    if p.is_file():
        return p.resolve().parent
    if p.is_dir():
        if _case_file(p) is not None:
            return p.resolve()
        # A directory named like a case but containing only input/build is not
        # a valid case package.
        raise PcdError(f"{p}: not a case package (missing case.json/case.yaml)")
    candidate = CASES_DIR / str(case)
    if candidate.is_dir() and _case_file(candidate) is not None:
        return candidate.resolve()
    raise PcdError(f"case not found: {case}")


def _case_file(case_dir: Path) -> Path | None:
    for name in ("case.json", "case.yaml", "case.yml"):
        p = case_dir / name
        if p.is_file():
            return p
    return None


def load_case_doc(case_dir: Path) -> dict[str, Any]:
    path = _case_file(case_dir)
    if path is None:
        raise PcdError(f"{case_dir}: missing case.json/case.yaml")
    if path.suffix in {".yaml", ".yml"}:
        from common.pcd_util import load_json_or_yaml

        return load_json_or_yaml(str(path))
    return read_json(path)


def _check_case_relative(path: str, where: str) -> None:
    p = Path(path)
    if p.is_absolute() or ".." in p.parts:
        raise PcdError(f"{where} must be a case-relative path with no '..': {path}")


def validate_case(doc: dict[str, Any]) -> None:
    schema_path = SCHEMA_DIR / "case.schema.json"
    schema = read_json(schema_path)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(doc),
        key=lambda e: (tuple(str(p) for p in e.absolute_path), e.message),
    )
    if errors:
        details = []
        for e in errors:
            where = "/".join(str(p) for p in e.absolute_path) or "<root>"
            details.append(f"{where}: {e.message}")
        raise PcdError("case schema validation failed: " + "; ".join(details))
    for i, item in enumerate(doc["inputs"]["files"]):
        _check_case_relative(item["path"], f"inputs.files[{i}].path")
    _check_case_relative(doc["build"]["recipe"].get("cwd", "."), "build.recipe.cwd")
    for i, item in enumerate(doc["build"]["outputs"]):
        _check_case_relative(item["path"], f"build.outputs[{i}].path")


def load_case(case: str | os.PathLike[str]) -> tuple[Path, dict[str, Any]]:
    case_dir = find_case(case)
    doc = load_case_doc(case_dir)
    validate_case(doc)
    for item in doc["inputs"]["files"]:
        declared = item.get("sha256")
        if not declared:
            continue
        path = case_dir / item["path"]
        if not path.is_file():
            raise PcdError(f"case input is missing: {item['path']}")
        if path.is_symlink():
            raise PcdError(f"case input must not be a symlink: {item['path']}")
        resolved = path.resolve()
        if not resolved.is_relative_to(case_dir.resolve()):
            raise PcdError(f"case input escapes the case directory: {item['path']}")
        actual = sha256_file(str(path))
        if actual != declared:
            raise PcdError(
                f"case input changed: {item['path']} expected {declared}, got {actual}"
            )
    return case_dir, doc


def new_run_dir(case_name: str, runs_dir: str | os.PathLike[str] | None = None) -> Path:
    base = Path(runs_dir).expanduser().resolve() if runs_dir else DEFAULT_RUNS_DIR
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(20):
        run_id = f"{stamp}-{case_name}-{secrets.token_hex(3)}"
        path = base / case_name / run_id
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return path
    raise PcdError("could not allocate a unique run directory")


def _ignore_generated(_dir: str, names: list[str]) -> list[str]:
    ignored = {"__pycache__", ".pytest_cache", ".mypy_cache"}
    return [n for n in names if n in ignored or n.endswith(".pyc")]


def stage_case(case_dir: Path, dest: Path) -> None:
    """Stage only the legitimate case surface: case file, input/, and build/.

    The oracle is never copied, even for dev runs. A development run that needs
    oracle regression data must consume it through a separate, explicitly
    marked scorer path.
    """
    if dest.exists():
        raise PcdError(f"staging destination already exists: {dest}")
    case_file = _case_file(case_dir)
    if case_file is None:
        raise PcdError(f"{case_dir}: missing case.json/case.yaml")
    if case_file.is_symlink():
        raise PcdError(f"case staging refuses symlink: {case_file.name}")
    dest.mkdir(parents=True)
    shutil.copy2(case_file, dest / case_file.name)
    for sub in ("input", "build"):
        src = case_dir / sub
        if src.is_dir():
            for p in src.rglob("*"):
                if p.is_symlink():
                    raise PcdError(f"case staging refuses symlink: {p.relative_to(case_dir)}")
            shutil.copytree(src, dest / sub, ignore=_ignore_generated)
    if not (dest / "input").is_dir():
        raise PcdError(f"{case_dir}: missing input/ directory")
    if not (dest / "build").is_dir():
        raise PcdError(f"{case_dir}: missing build/ directory")


def hash_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[p.relative_to(root).as_posix()] = sha256_file(str(p))
    return out


def hash_stage(staged_case: Path) -> dict[str, Any]:
    return {
        "input": hash_tree(staged_case / "input"),
        "build": hash_tree(staged_case / "build"),
    }


def as_command(command: str | list[str]) -> list[str]:
    if isinstance(command, str):
        return ["sh", "-c", command]
    if not command:
        raise PcdError("empty command")
    return [str(x) for x in command]


def _version_of(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            check=False,
        )
        text = (proc.stdout or "").strip().splitlines()
        return text[0] if text else f"exit {proc.returncode}"
    except Exception as exc:  # noqa: BLE001 - version probing is best effort
        return f"unavailable ({exc.__class__.__name__})"


def tool_versions() -> dict[str, str]:
    return {
        "ric3": _version_of(["ric3", "--version"]),
        "yosys": _version_of(["yosys", "-V"]),
        "python": sys.version.split()[0],
        "z3": _version_of(["z3", "--version"]),
    }


def run_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_s: int | None,
    env: dict[str, str] | None = None,
    sandbox: bool = False,
    sandbox_root: Path | None = None,
    sandbox_network: bool = False,
) -> dict[str, Any]:
    """Run a command, capturing a complete log and a structured record.

    Non-zero exits and timeouts are recorded rather than raised. The caller
    decides whether a failed command is a diagnostic or a hard pipeline error.

    ``sandbox`` wraps the process in bwrap with only ``sandbox_root`` visible
    read-write.  It is required for blind runs and fails closed if bwrap or the
    run directory is unavailable.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    exec_command = command
    if sandbox:
        if sandbox_root is None:
            raise PcdError("sandboxed command requires a run directory")
        from .sandbox import wrap_command

        exec_command = wrap_command(
            command,
            cwd=Path(cwd),
            run_dir=Path(sandbox_root),
            allow_network=sandbox_network,
        )
    started = time.monotonic()
    with open(log_path, "wb") as log:
        header = (
            "# command: " + " ".join(shlex.quote(x) for x in command) + "\n"
            "# cwd: " + str(cwd) + "\n"
            "# timeout_s: " + (str(timeout_s) if timeout_s is not None else "none") + "\n"
            + ("# sandbox: bwrap\n" if sandbox else "")
            + "# ---\n"
        )
        log.write(header.encode("utf-8"))
        log.flush()
        try:
            proc = subprocess.Popen(
                exec_command,
                cwd=str(cwd),
                env=merged_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            log.write(f"# launch error: {exc}\n".encode("utf-8"))
            seconds = time.monotonic() - started
            return {
                "command": command,
                "cwd": str(cwd),
                "returncode": 127,
                "timed_out": False,
                "seconds": round(seconds, 3),
                "log": str(log_path),
                "log_sha256": sha256_file(str(log_path)),
                "launch_error": str(exc),
                "sandboxed": bool(sandbox),
            }
        except Exception as exc:  # noqa: BLE001
            log.write(f"# launch error: {exc}\n".encode("utf-8"))
            seconds = time.monotonic() - started
            return {
                "command": command,
                "cwd": str(cwd),
                "returncode": 126,
                "timed_out": False,
                "seconds": round(seconds, 3),
                "log": str(log_path),
                "log_sha256": sha256_file(str(log_path)),
                "launch_error": str(exc),
                "sandboxed": bool(sandbox),
            }

        timed_out = False
        try:
            rc = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:  # noqa: BLE001 - fall back to the direct child
                proc.kill()
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                rc = -9
            log.write(f"\n# external timeout after {timeout_s}s\n".encode("utf-8"))
            log.flush()
        seconds = time.monotonic() - started
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": rc,
        "timed_out": timed_out,
        "seconds": round(seconds, 3),
        "log": str(log_path),
        "log_sha256": sha256_file(str(log_path)),
        "sandboxed": bool(sandbox),
    }


_RESULT_ALIASES = {
    "UNSAT": "proved",
    "unsat": "proved",
    "SAFE": "proved",
    "safe": "proved",
    "PROVED": "proved",
    "proved": "proved",
    "PROVEN": "proved",
    "SAT": "cex",
    "sat": "cex",
    "UNSAFE": "cex",
    "unsafe": "cex",
    "CEX": "cex",
    "cex": "cex",
    "UNKNOWN": "unknown",
    "unknown": "unknown",
    "TIMEOUT": "unknown",
    "timeout": "unknown",
}


def parse_verdict(log_text: str, *, backend: str = "portfolio", returncode: int = 0, timed_out: bool = False) -> str:
    """Map an engine log to the proof vocabulary, conservatively.

    Only an explicit proof result from a complete engine mode is `proved`.
    BMC UNSAT is `bmc_clean` (diagnostic), never a proof.
    """
    if timed_out:
        return "unknown"
    found: str | None = None
    for raw in reversed(log_text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        if "Terminated by timeout" in line:
            return "unknown"
        token = line.split()[-1] if line.split() else line
        for key in (line, token):
            if key in _RESULT_ALIASES:
                found = _RESULT_ALIASES[key]
                break
        if found is not None:
            break
    if found is None:
        if re.search(r"counter-?example(?: found)?", log_text, flags=re.IGNORECASE):
            return "cex"
        return "error" if returncode not in (0, None) else "unknown"
    if found == "proved" and backend in {"bmc", "wl-bmc"}:
        return "bmc_clean"
    return found


def verify_hash(path: Path, expected_path: Path) -> str:
    if not path.is_file():
        raise PcdError(f"missing file: {path}")
    actual = sha256_file(str(path))
    if expected_path.is_file():
        expected = expected_path.read_text(encoding="utf-8").strip().split()[0]
        if actual != expected:
            raise PcdError(f"hash mismatch for {path.name}: expected {expected}, got {actual}")
    return actual


def freeze_json(path: Path, obj: Any) -> str:
    write_json(path, obj)
    digest = canonical_hash(obj)
    write_text(path.with_suffix(path.suffix + ".sha256"), digest + "\n")
    return digest


def load_frozen_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise PcdError(f"missing frozen artifact: {path}")
    obj = read_json(path)
    digest = canonical_hash(obj)
    expected_path = path.with_suffix(path.suffix + ".sha256")
    if expected_path.is_file():
        expected = expected_path.read_text(encoding="utf-8").strip().split()[0]
        if digest != expected:
            raise PcdError(f"frozen file changed: {path} (expected {expected}, got {digest})")
    return obj, digest


def relative_to(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return str(path.resolve())


def iter_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_strings(v)


def find_forbidden_status(obj: Any, *, where: str = "") -> list[str]:
    """Find planner/verdict fields that must not appear in a proposal."""
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{where}.{k}" if where else str(k)
            if k in {"status", "verdict", "claim", "claim_level", "level", "planner_status", "planner_claim"}:
                bad.append(here)
            bad.extend(find_forbidden_status(v, where=here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(find_forbidden_status(v, where=f"{where}[{i}]"))
    return bad
