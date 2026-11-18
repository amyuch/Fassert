#!/usr/bin/env python3
"""Add a disconnected observer to the frozen ADD model (no engine execution)."""
from pathlib import Path


def observer_extension(text: str) -> str:
    tokens = [line.split(";", 1)[0].split() for line in text.splitlines()]
    ids = [int(t[0]) for t in tokens if t]
    bit = next(int(t[0]) for t in tokens if len(t) == 4 and t[1:] == ["sort", "bitvec", "1"])
    n = max(ids) + 1
    return text.rstrip() + "\n" + (
        f"{n} zero {bit}\n"
        f"{n + 1} state {bit} composition_demo_observer\n"
        f"{n + 2} init {bit} {n + 1} {n}\n"
        f"{n + 3} not {bit} {n + 1}\n"
        f"{n + 4} next {bit} {n + 1} {n + 3}\n"
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / "models" / "observed.btor"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(observer_extension((root / "input/models/source.btor").read_text()))
