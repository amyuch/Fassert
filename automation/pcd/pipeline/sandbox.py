"""Filesystem isolation for blind planner/build/engine processes.

A blind run is not blind merely because the oracle was not copied.  The external
process can still read the host filesystem.  This module wraps commands in
bubblewrap, hiding the workspace (which contains the frozen oracle, source cases,
and prior runs) and the system temporary directory.  The current run directory is
rebound read-write so logs and build outputs work.

The wrapper fails closed when bwrap is unavailable.  It is only used for
``run_policy.mode == "blind"``; dev runs keep the ordinary subprocess path.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .core import PcdError

# sandbox.py -> pipeline -> pcd -> automation -> workspace
WORKSPACE = Path(__file__).resolve().parents[3]


def available() -> bool:
    return shutil.which("bwrap") is not None


def _add_parent_dirs(args: list[str], root: Path, target: Path) -> None:
    try:
        rel = target.relative_to(root)
    except ValueError:
        return
    current = root
    for part in rel.parts:
        current = current / part
        args.extend(["--dir", str(current)])


def wrap_command(
    command: list[str],
    *,
    cwd: Path,
    run_dir: Path,
    allow_network: bool = False,
) -> list[str]:
    """Return a bwrap invocation that isolates ``command`` to ``run_dir``."""
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise PcdError(
            "blind run requires bwrap for filesystem isolation, but bwrap is not installed"
        )
    if not command:
        raise PcdError("empty command cannot be sandboxed")

    run_dir = Path(run_dir).resolve()
    cwd = Path(cwd).resolve()
    if not cwd.is_relative_to(run_dir):
        raise PcdError(f"sandbox cwd {cwd} is outside the run directory {run_dir}")
    if not run_dir.is_dir():
        raise PcdError(f"sandbox run directory does not exist: {run_dir}")

    # Keep the system/toolchain visible read-only, but replace the workspace and
    # the system temp dir with empty tmpfs mounts.  The current run is then
    # selectively rebound.  This hides cases/, prior runs, and any source-case
    # oracle material that happens to live under either hidden root.
    args: list[str] = [
        bwrap,
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--ro-bind",
        "/proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        str(WORKSPACE),
    ]
    hidden_roots = [Path("/tmp"), WORKSPACE]
    for root in hidden_roots:
        _add_parent_dirs(args, root, run_dir)
    args.extend(["--bind", str(run_dir), str(run_dir)])
    args.extend(["--chdir", str(cwd), "--unshare-all"])
    if allow_network:
        args.append("--share-net")
    args.extend(["--die-with-parent", "--", *command])
    return args
