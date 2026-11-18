"""Small, dependency-light utilities shared by the PCD toolchain.

This module deliberately has no dependency on ``pcd`` or on the frozen
``decomp`` oracle. It only contains identity/IO helpers that are useful to the
kernel, future backends, and the blind-run harness.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Stable JSON encoding for hashing and run records."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def resolve_path(base: str, ref: str) -> str:
    """Resolve a manifest-relative path; absolute paths are kept as-is."""
    return ref if os.path.isabs(ref) else os.path.abspath(os.path.join(base, ref))


def load_json_or_yaml(path: str) -> dict[str, Any]:
    """Load a JSON document, or YAML when the suffix says so."""
    text = read_text(path)
    if path.endswith((".yaml", ".yml")):
        import yaml

        doc = yaml.safe_load(text)
    else:
        doc = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: top-level document must be an object")
    return doc
