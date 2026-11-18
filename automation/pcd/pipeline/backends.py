"""Trusted engine catalog.

Planner proposals choose an engine and backend name.  They never execute a
command directly: the runner resolves the command from this catalog and rejects
a proposal whose optional command does not exactly match the trusted template.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .core import PcdError


DEFAULT_ENGINES: dict[str, Any] = {
    "ric3": {
        "backends": {
            "portfolio": [
                "ric3",
                "check",
                "{model}",
                "portfolio",
                "--prop",
                "{prop}",
                "--time-limit",
                "{time_limit}",
            ],
            "ic3": [
                "ric3",
                "check",
                "{model}",
                "ic3",
                "--prop",
                "{prop}",
                "--time-limit",
                "{time_limit}",
            ],
            "kind": [
                "ric3",
                "check",
                "{model}",
                "kind",
                "--prop",
                "{prop}",
                "--time-limit",
                "{time_limit}",
            ],
            "bmc": [
                "ric3",
                "check",
                "{model}",
                "bmc",
                "--prop",
                "{prop}",
                "--time-limit",
                "{time_limit}",
            ],
            "cill": [
                "ric3",
                "cill",
                "check",
            ],
        },
        "notes": "portfolio is the timeout-safe baseline; bmc is diagnostic only; cill checks named helper assertions",
    }
}


DEFAULT_DIAGNOSTICS: dict[str, Any] = {
    "ric3-cill": {
        "commands": {
            "check": ["ric3", "cill", "check"],
            "select": ["ric3", "cill", "select", "{property}"],
        },
        "notes": "ric3 cill produces CTI diagnostics only; an UNKNOWN/timeout is never a CTI",
    }
}


def default_engines() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_ENGINES)


def default_diagnostics() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_DIAGNOSTICS)


def normalize_engines(engines: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and copy an engine catalog (case/context/test supplied)."""
    if engines is None:
        return default_engines()
    if not isinstance(engines, dict) or not engines:
        raise PcdError("engine catalog must be a non-empty object")
    out: dict[str, Any] = {}
    for engine, spec in engines.items():
        if not isinstance(engine, str) or not engine:
            raise PcdError("engine name must be a non-empty string")
        if not isinstance(spec, dict):
            raise PcdError(f"engine {engine!r} must be an object")
        backends = spec.get("backends")
        if not isinstance(backends, dict) or not backends:
            raise PcdError(f"engine {engine!r} has no backends")
        clean: dict[str, Any] = {"backends": {}}
        for name, template in backends.items():
            if not isinstance(name, str) or not name:
                raise PcdError(f"engine {engine!r}: backend name must be a non-empty string")
            if not isinstance(template, list) or not template or not all(
                isinstance(x, str) and x for x in template
            ):
                raise PcdError(f"engine {engine!r}/{name!r}: command template must be a non-empty string array")
            clean["backends"][name] = list(template)
        if isinstance(spec.get("notes"), str):
            clean["notes"] = spec["notes"]
        out[engine] = clean
    return out


def resolve_engine_command(
    engines: dict[str, Any],
    hint: dict[str, Any],
    mapping: dict[str, str],
) -> tuple[str, str, list[str]]:
    """Resolve a proposal's engine/backend to the trusted command template."""
    engine = str(hint.get("engine") or "ric3")
    backend = str(hint.get("backend") or "portfolio")
    spec = engines.get(engine)
    if spec is None:
        raise PcdError(f"engine {engine!r} is not in the trusted catalog")
    template = spec["backends"].get(backend)
    if template is None:
        raise PcdError(f"engine {engine!r} has no trusted backend {backend!r}")
    resolved = [token for token in _subst(template, mapping)]
    if any(re.search(r"\{[A-Za-z0-9_.-]+\}", token) for token in resolved):
        raise PcdError(f"engine {engine!r}/{backend!r}: unresolved command placeholder")
    provided = hint.get("command")
    if provided is not None:
        try:
            provided_list = [str(x) for x in provided]
        except TypeError as exc:
            raise PcdError("proposal command must be a string array") from exc
        if provided_list != resolved:
            raise PcdError(
                f"proposal command does not match trusted backend {engine}/{backend}"
            )
    return engine, backend, resolved


def normalize_diagnostics(catalog: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and copy a trusted diagnostic-command catalog."""
    if catalog is None:
        return default_diagnostics()
    if not isinstance(catalog, dict) or not catalog:
        raise PcdError("diagnostic catalog must be a non-empty object")
    out: dict[str, Any] = {}
    for name, spec in catalog.items():
        if not isinstance(name, str) or not name:
            raise PcdError("diagnostic name must be a non-empty string")
        if not isinstance(spec, dict):
            raise PcdError(f"diagnostic {name!r} must be an object")
        commands = spec.get("commands")
        if not isinstance(commands, dict) or not commands:
            raise PcdError(f"diagnostic {name!r} has no commands")
        clean: dict[str, Any] = {"commands": {}}
        for phase, template in commands.items():
            if not isinstance(phase, str) or not phase:
                raise PcdError(f"diagnostic {name!r}: command name must be a non-empty string")
            if not isinstance(template, list) or not template or not all(
                isinstance(x, str) and x for x in template
            ):
                raise PcdError(f"diagnostic {name!r}/{phase!r}: command template must be a non-empty string array")
            clean["commands"][phase] = list(template)
        if isinstance(spec.get("notes"), str):
            clean["notes"] = spec["notes"]
        out[name] = clean
    return out


def resolve_diagnostic_command(
    catalog: dict[str, Any],
    name: str,
    phase: str,
    mapping: dict[str, str],
) -> list[str]:
    """Resolve a diagnostic phase from the trusted catalog, never from a proposal."""
    spec = catalog.get(name)
    if spec is None:
        raise PcdError(f"diagnostic {name!r} is not in the trusted catalog")
    template = spec["commands"].get(phase)
    if template is None:
        raise PcdError(f"diagnostic {name!r} has no trusted command {phase!r}")
    resolved = [token for token in _subst(template, mapping)]
    if any(re.search(r"\{[A-Za-z0-9_.-]+\}", token) for token in resolved):
        raise PcdError(f"diagnostic {name!r}/{phase!r}: unresolved command placeholder")
    return resolved


def _subst(tokens: list[str], mapping: dict[str, str]) -> list[str]:
    out = []
    for token in tokens:
        for key, value in mapping.items():
            token = token.replace("{" + key + "}", value)
        out.append(token)
    return out
