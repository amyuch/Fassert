"""Independent polynomial normal-form checker.

This is the v0 generic checker for `format: "poly"`. It does not trust the
producer: it normalises the supplied polynomials over Z/2^W and accepts only if
`lhs - rhs` is zero and the identity is not structurally trivial.

Payload (preferred):

    {
      "W": 32,
      "lhs": [[1, ["y"]], [-1, ["x"]], [-1, []]],
      "rhs": []
    }

A term is [coefficient, [atom, ...]]. An atom is a variable name (string) or a
key in `subst`, whose value is a list of terms. The empty monomial is ().

The legacy-compatible `"terms"` form is still accepted, but an empty or
structurally trivial payload is rejected: a certificate that proves `0 = 0` (or
`x = x`) proves nothing about the obligation.

This checker establishes the polynomial identity only. The link from that
identity to the obligation's guarantee is part of the certificate provenance and
is deliberately not a free-text status.
"""
from __future__ import annotations

from collections import defaultdict

from . import expr

MAX_TERMS = 10_000
MAX_ATOMS = 64


def _add(p, q, W):
    d = defaultdict(int)
    for m, c in p.items():
        d[m] += c
    for m, c in q.items():
        d[m] += c
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def _sub(p, q, W):
    return _add(p, {m: -c for m, c in q.items()}, W)


def _mul(p, q, W):
    d = defaultdict(int)
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            d[tuple(sorted(m1 + m2))] += c1 * c2
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def _term(coeff, atoms, W, subst, stack=()):
    out = {(): int(coeff) % (1 << W)}
    for atom in atoms:
        if isinstance(atom, str) and atom in subst:
            if atom in stack:
                raise ValueError(f"cyclic substitution: {' -> '.join(stack + (atom,))}")
            out = _mul(out, _subst_poly(atom, W, subst, stack + (atom,)), W)
        else:
            out = _mul(out, {(atom,): 1}, W)
    return out


def _subst_poly(atom, W, subst, stack):
    out = {}
    for item in subst.get(atom, []):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"bad substitution for {atom!r}: {item!r}")
        coeff, atoms = item
        if isinstance(atoms, str):
            atoms = [atoms]
        if not isinstance(atoms, (list, tuple)):
            raise ValueError(f"bad atoms in substitution for {atom!r}: {item!r}")
        if len(atoms) > MAX_ATOMS:
            raise ValueError(f"too many atoms in substitution for {atom!r}")
        out = _add(out, _term(coeff, atoms, W, subst, stack), W)
    return out


def _sum_terms(items, W, subst):
    if not isinstance(items, (list, tuple)):
        raise ValueError("term list must be an array")
    if len(items) > MAX_TERMS:
        raise ValueError(f"too many terms ({len(items)} > {MAX_TERMS})")
    total = {}
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"bad term {item!r}")
        coeff, atoms = item
        if isinstance(atoms, str):
            atoms = [atoms]
        if not isinstance(atoms, (list, tuple)):
            raise ValueError(f"bad atoms in term {item!r}")
        if len(atoms) > MAX_ATOMS:
            raise ValueError(f"too many atoms in term {item!r}")
        total = _add(total, _term(coeff, atoms, W, subst), W)
    return total


def check(payload: dict) -> tuple[bool, str]:
    """Return (ok, detail)."""
    try:
        W = int(payload.get("W", 32))
        if W < 1 or W > 4096:
            return False, f"unsupported width {W}"
        subst = payload.get("subst", {}) or {}
        if not isinstance(subst, dict):
            return False, "subst must be an object"
        if len(subst) > MAX_TERMS:
            return False, "too many substitutions"

        if "lhs" in payload or "rhs" in payload:
            lhs_raw = payload.get("lhs", []) or []
            rhs_raw = payload.get("rhs", []) or []
            if not lhs_raw and not rhs_raw:
                return False, "empty identity (vacuous)"
            if lhs_raw == rhs_raw:
                return False, "lhs and rhs are syntactically identical (vacuous)"
            lhs = _sum_terms(lhs_raw, W, subst)
            rhs = _sum_terms(rhs_raw, W, subst)
            diff = _sub(lhs, rhs, W)
            return (not diff), ("zero" if not diff else f"non-zero: {dict(diff)}")

        terms = payload.get("terms")
        if not terms:
            return False, "no terms (vacuous)"
        total = _sum_terms(terms, W, subst)
        return (not total), ("zero" if not total else f"non-zero: {dict(total)}")
    except Exception as exc:  # noqa: BLE001 - checker must not crash on bad input
        return False, f"checker error: {exc}"


def check_expr(expr_text: str, payload: dict | None = None) -> tuple[bool, str]:
    """Check the polynomial equality that is the obligation itself.

    The old payload-only `check` proves an identity in isolation.  That is not
    enough for a CHECKED obligation: the identity must be the guarantee's
    formula.  This entry point parses that formula with the restricted
    expression language and checks its normal form over Z/2^W.  If a payload is
    supplied, its width is used and any legacy term payload is checked as an
    additional independent witness.
    """
    payload = payload or {}
    if not isinstance(payload, dict):
        return False, "payload must be an object"
    try:
        W = int(payload.get("W", 32))
    except Exception:  # noqa: BLE001
        return False, "W must be an integer"
    ok, detail = expr.poly_identity(expr_text, W)
    if not ok:
        return False, detail
    if "lhs" in payload or "rhs" in payload or "terms" in payload:
        legacy_ok, legacy_detail = check(payload)
        if not legacy_ok:
            return False, f"payload witness rejected: {legacy_detail}"
    return True, detail
