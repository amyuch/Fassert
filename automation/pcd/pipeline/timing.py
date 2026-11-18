"""Parse engine timing records without trusting wall-clock guesses.

The CIll backend writes ``ric3proj/cill/statistic.ron`` in the staged build
tree.  Its shape is deliberately small::

    (start:"...",bmc_time:(secs,nanos),ind_time:(secs,nanos))

The seconds are split into whole seconds and nanoseconds.  A missing file is
normal for a timeout or a launch failure; callers then fall back to wall time.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from common.pcd_util import sha256_file

_START = re.compile(r'start\s*:\s*"([^"]*)"')


def _phase_seconds(text: str, name: str) -> float | None:
    match = re.search(rf"{name}\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", text)
    if match is None:
        return None
    return int(match.group(1)) + int(match.group(2)) / 1_000_000_000


def parse_statistic_ron(path: Path) -> dict[str, Any] | None:
    """Return exact CIll phase timings, or ``None`` if no usable record exists."""
    path = Path(path)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    bmc = _phase_seconds(text, "bmc_time")
    ind = _phase_seconds(text, "ind_time")
    if bmc is None and ind is None:
        return None
    bmc = bmc or 0.0
    ind = ind or 0.0
    start = _START.search(text)
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(str(path)),
        "start": start.group(1) if start else None,
        "bmc_seconds": round(bmc, 6),
        "ind_seconds": round(ind, 6),
        "engine_seconds": round(bmc + ind, 6),
    }


def cill_statistic_path(project_root: Path) -> Path:
    """Locate the CIll statistic file under a staged ``.pcd-build`` root."""
    return Path(project_root) / "ric3proj" / "cill" / "statistic.ron"
