#!/usr/bin/env python3
"""Minimal proof-graph kernel (T2/T3).

Validates a proof-carrying decomposition (PCD) DAG:

  K1 well-formedness
  K2 local soundness for supported backends (independent poly certificate;
     trusted engines recorded with evidence; no over-claim)
  K3 dependency closure (no BMC_CLEAN/UNKNOWN/COUNTEREXAMPLE as premises)
  K4 abstraction gate (over-approximation certificate) when S4 is used
  K5 coverage (guard partitions / required premises marked checked)
  K6 root composition (target follows from discharged nodes at the target scope)
  K7 status/provenance (statuses valid, reuse assumption-match recorded,
     model ids consistent)
  K8 composition binding (a compose target must bind the artifact of the
     composition run that closes it, by sha256)
  K9 helper hygiene (committed helper sources must not contain tautological
     assertions: a neutered helper may not be recorded as a proved lemma)

Only the kernel closes the root. It does NOT independently validate arbitrary
engines; recorded engine results are `PROVED_TRUSTED`.

Usage:
  python3 kernel.py cases/mul/proof_graph.json
  python3 kernel.py --selftest
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict

STATUSES = {"PROVED_CHECKED", "PROVED_TRUSTED", "BMC_CLEAN", "UNKNOWN",
            "COUNTEREXAMPLE", "TCB_ASSUMPTION"}
PREMISE_OK = {"PROVED_CHECKED", "PROVED_TRUSTED", "TCB_ASSUMPTION"}
ROLES = {"invariant", "update", "algebra", "terminal", "temporal", "select",
         "operand", "observe", "rtl_link", "abstraction_gate", "coverage",
         "compose", "tcb", "interface"}
KINDS = {"inductive", "poly", "linear", "guarded", "ordering", "macro_step",
         "over_approx", "tcb"}
REUSE_FIELDS = {"model", "width", "guards", "phase", "transition"}

# K9: assertion shapes that are trivially true.  A helper that has been
# weakened to one of these proves nothing and must not back a `PROVED_TRUSTED`
# node.
TAUTOLOGY_PATTERNS = (
    (re.compile(r"\|\|\s*1'b1"), "tautology: '|| 1\\'b1'"),
    (re.compile(r"\|\|\s*1\s*\)"), "tautology: '|| 1)'"),
    (re.compile(r"assert\s*\(\s*1'b1\s*\)"), "tautology: assert(1'b1)"),
    (re.compile(r"assert\s*\(\s*true\s*\)"), "tautology: assert(true)"),
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- K2: independent polynomial certificate ----------
def _mono(*atoms):
    return tuple(sorted(atoms))


def _poly_mul(p, q, W):
    d = defaultdict(int)
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            d[tuple(sorted(m1 + m2))] += c1 * c2
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def _poly_add(p, q, W):
    d = defaultdict(int)
    for m, c in p.items():
        d[m] += c
    for m, c in q.items():
        d[m] += c
    mod = 1 << W
    return {k: v % mod for k, v in d.items() if v % mod}


def check_poly(payload):
    """payload: {W, terms:[[coeff,[atom,...]],...], subst:{atom:[[coeff,[atom..]],...]}}."""
    W = int(payload.get("W", 32))
    subst = payload.get("subst", {})

    def atom_poly(a):
        if a in subst:
            out = {}
            for c, atoms in subst[a]:
                if isinstance(atoms, str):
                    atoms = [atoms]
                term = {(): c % (1 << W)}
                for x in atoms:
                    term = _poly_mul(term, {_mono(x): 1}, W)
                out = _poly_add(out, term, W)
            return out
        return {_mono(a): 1}

    total = {}
    for coeff, atoms in payload.get("terms", []):
        term = {(): int(coeff) % (1 << W)}
        for a in atoms:
            term = _poly_mul(term, atom_poly(a), W)
        total = _poly_add(total, term, W)
    return not total


# ---------- graph checks ----------
def err(errs, msg):
    errs.append(msg)


def check_graph(g):
    errs = []
    nodes = {n.get("id"): n for n in g.get("nodes", [])}
    targets = g.get("targets", [])
    model = g.get("model")

    # K1 well-formedness + K7 status validity
    for nid, n in nodes.items():
        if not nid:
            err(errs, "K1 node without id")
            continue
        for f in ("role", "kind", "lemma", "assumes", "status"):
            if f not in n:
                err(errs, f"K1 {nid}: missing {f}")
        if n.get("role") not in ROLES:
            err(errs, f"K1 {nid}: bad role {n.get('role')}")
        if n.get("kind") not in KINDS:
            err(errs, f"K1 {nid}: bad kind {n.get('kind')}")
        if n.get("status") not in STATUSES:
            err(errs, f"K7 {nid}: bad status {n.get('status')}")
        if n.get("status") != "TCB_ASSUMPTION":
            for f in ("engine", "evidence", "model"):
                if not n.get(f):
                    err(errs, f"K1 {nid}: missing {f}")
        # K2 local soundness
        st = n.get("status")
        if st == "PROVED_CHECKED":
            cert = n.get("certificate") or {}
            if cert.get("checker") == "poly":
                if not check_poly(cert.get("payload", {})):
                    err(errs, f"K2 {nid}: poly certificate does not normalize to 0")
            else:
                err(errs, f"K2 {nid}: PROVED_CHECKED without a supported checker")
        elif st == "PROVED_TRUSTED":
            if not (n.get("engine") and n.get("evidence")):
                err(errs, f"K2 {nid}: PROVED_TRUSTED needs engine+evidence")
        elif st == "TCB_ASSUMPTION":
            if not n.get("tcb"):
                err(errs, f"K2 {nid}: TCB node needs a reason")
        # K4 abstraction gate
        if n.get("role") == "abstraction_gate" or n.get("kind") == "over_approx":
            gate = (n.get("certificate") or {}).get("gate") or {}
            if (n.get("certificate") or {}).get("format") != "over_approx" or \
               gate.get("status") not in PREMISE_OK:
                err(errs, f"K4 {nid}: abstraction gate missing/invalid")
        # K5 coverage
        if n.get("role") == "coverage" and not n.get("coverage_checked"):
            err(errs, f"K5 {nid}: coverage not checked")
        if n.get("guard_classes") and not n.get("coverage_checked"):
            err(errs, f"K5 {nid}: guard classes without coverage_checked")
        # K7 reuse assumption matching
        if n.get("reuse"):
            am = set(n["reuse"].get("assumption_match", []))
            missing = REUSE_FIELDS - am
            if missing:
                err(errs, f"K7 {nid}: reuse missing checks {sorted(missing)}")
            if n["reuse"].get("source_model") != n.get("model"):
                err(errs, f"K7 {nid}: reuse source_model != the node's model id")
    # K7 model consistency: a node's model id must be a model of this case.  A
    #    lemma proved on a model other than the primary one (e.g. on an isolated
    #    module) must carry a reuse block: the transfer to the case's model is
    #    a proof obligation, not a wording.
    models = dict(g.get("models") or {})
    primary = g.get("model")
    if primary:
        models.setdefault("primary", primary)
    for nid, n in nodes.items():
        if n.get("status") == "TCB_ASSUMPTION":
            continue
        nm = n.get("model")
        if not nm:
            err(errs, f"K7 {nid}: no model id")
            continue
        if nm not in models.values():
            err(errs, f"K7 {nid}: model {nm[:14]}... is not a model of this case")
            continue
        if primary and nm != primary and not n.get("reuse"):
            err(errs, f"K7 {nid}: proved on a non-primary model without a "
                      f"reuse (transfer) block")

    # K3 dependency existence + premise status
    for nid, n in nodes.items():
        for a in n.get("assumes", []):
            if a not in nodes:
                err(errs, f"K3 {nid}: assumption {a} does not exist")
            elif nodes[a].get("status") not in PREMISE_OK:
                err(errs, f"K3 {nid}: premise {a} not discharged "
                          f"({nodes[a].get('status')})")

    # K3 cycles (allow same simultaneous_group)
    def cyc(nid, stack):
        n = nodes.get(nid, {})
        for a in n.get("assumes", []):
            if a in stack:
                grp = n.get("simultaneous_group")
                if not grp or any(nodes.get(x, {}).get("simultaneous_group") != grp
                                  for x in stack[stack.index(a):] + [nid]):
                    err(errs, f"K3 cycle through {a}")
                    return True
            elif cyc(a, stack + [nid]):
                return True
        return False
    for nid in nodes:
        if cyc(nid, []):
            break

    # K6 root composition
    if not targets:
        err(errs, "K6 no target")
    for t in targets:
        tid = t.get("id")
        if tid not in nodes:
            err(errs, f"K6 target {tid} missing")
            continue
        root = nodes[tid]
        if root.get("role") != "compose":
            err(errs, f"K6 target {tid} is not a compose node")
        req = list(t.get("requires", []))
        for r in req:
            if r not in root.get("assumes", []):
                err(errs, f"K6 {tid}: requires {r} not assumed by root")
            if r not in nodes:
                err(errs, f"K6 {tid}: required {r} missing")
            elif nodes[r].get("status") not in PREMISE_OK:
                err(errs, f"K6 {tid}: required {r} not discharged")
        for tb in t.get("tcb", []):
            if tb not in nodes or nodes[tb].get("status") != "TCB_ASSUMPTION":
                err(errs, f"K6 {tid}: TCB {tb} missing/not TCB")
        if t.get("model") and t["model"] != model:
            err(errs, f"K6 {tid}: target model mismatch")

    # K8 composition binding: the run that closes a compose target is bound to
    #    the artifact(s) it produced (by sha256), so "closed at the integration
    #    level" points at a checkable run rather than at prose.
    here = os.path.dirname(os.path.abspath(__file__))
    for t in targets:
        comp = t.get("composition") or {}
        arts = comp.get("artifacts")
        if arts is None:
            arts = [comp] if comp.get("artifact") else []
        for a in arts:
            art = a.get("artifact") or a.get("file")
            if not art:
                continue
            path = art if os.path.isabs(art) else os.path.join(here, art)
            if not os.path.exists(path):
                err(errs, f"K8 {t.get('id')}: composition artifact missing: {art}")
                continue
            want = a.get("sha256")
            if want:
                got = sha256_file(path)
                if got != want:
                    err(errs, f"K8 {t.get('id')}: composition artifact sha256 "
                              f"mismatch ({art}: got {got[:12]}..., recorded "
                              f"{want[:12]}...)")

    # K9 helper hygiene: a committed helper source must not contain a
    #    tautological assertion; such a helper proves nothing and may not back
    #    a `PROVED_TRUSTED` node.
    for rel in g.get("helpers", []):
        path = rel if os.path.isabs(rel) else os.path.join(here, rel)
        if not os.path.exists(path):
            err(errs, f"K9 helper file missing: {rel}")
            continue
        for ln, line in enumerate(open(path, errors="replace"), 1):
            for pat, why in TAUTOLOGY_PATTERNS:
                if pat.search(line):
                    err(errs, f"K9 {rel}:{ln}: {why}")
    return (not errs), errs


def load(path):
    return json.load(open(path))


def show(path):
    g = load(path)
    ok, errs = check_graph(g)
    print(f"[{'ACCEPT' if ok else 'REJECT'}] {path}")
    for e in errs:
        print(f"    - {e}")
    return ok


def selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    cases = [os.path.join(here, "cases/mul/proof_graph.json"),
             os.path.join(here, "cases/div/proof_graph.json"),
             os.path.join(here, "cases/add/proof_graph.json"),
             os.path.join(here, "cases/sltu/proof_graph.json"),
             os.path.join(here, "cases/rem/proof_graph.json")]
    allok = True
    for c in cases:
        allok &= show(c)
        g = load(c)
        # negative controls
        mutations = {}
        # 1 missing assumption from root
        g1 = json.loads(json.dumps(g))
        root = next(n for n in g1["nodes"] if any(t["id"] == n["id"] for t in g1["targets"]))
        root["assumes"] = root["assumes"][1:]
        mutations["missing_assumption"] = g1
        # 2 uncovered guard
        g2 = json.loads(json.dumps(g))
        for n in g2["nodes"]:
            if n.get("guard_classes"):
                n["coverage_checked"] = False
                break
        else:
            g2["nodes"].append({"id": "cov_probe", "role": "coverage", "kind": "guarded",
                                "lemma": "probe", "assumes": [], "status": "PROVED_TRUSTED",
                                "engine": "x", "evidence": "x", "model": g2["model"],
                                "guard_classes": ["a", "b"], "coverage_checked": False})
        mutations["uncovered_guard"] = g2
        # 3 disconnected lemma (require a node not assumed)
        g3 = json.loads(json.dumps(g))
        g3["targets"][0]["requires"].append("orphan")
        g3["nodes"].append({"id": "orphan", "role": "invariant", "kind": "inductive",
                            "lemma": "orphan", "assumes": [], "status": "PROVED_TRUSTED",
                            "engine": "x", "evidence": "x", "model": g3["model"]})
        mutations["disconnected_lemma"] = g3
        # 4 status upgrade (a premise becomes UNKNOWN)
        g4 = json.loads(json.dumps(g))
        assumed = {a for n in g4["nodes"] for a in n.get("assumes", [])}
        victim = next(n for n in g4["nodes"] if n["id"] in assumed)
        victim["status"] = "UNKNOWN"
        mutations["status_upgrade"] = g4
        # 5 unsound abstraction
        g5 = json.loads(json.dumps(g))
        g5["nodes"].append({"id": "abs", "role": "abstraction_gate", "kind": "over_approx",
                            "lemma": "abs", "assumes": [], "status": "PROVED_TRUSTED",
                            "engine": "x", "evidence": "x", "model": g5["model"],
                            "certificate": {"format": "none"}})
        mutations["unsound_abstraction"] = g5
        # 6 reuse mismatch
        g6 = json.loads(json.dumps(g))
        victim = next(n for n in g6["nodes"] if n.get("status") != "TCB_ASSUMPTION")
        victim["reuse"] = {"from": "div", "assumption_match": ["model", "guards"]}
        mutations["reuse_mismatch"] = g6
        # 7 composition artifact not bound to the run that produced it
        g7 = json.loads(json.dumps(g))
        g7["targets"][0]["composition"] = {"artifact": "cases/rem/proof_graph.json",
                                           "sha256": "0" * 64}
        mutations["composition_unbound"] = g7
        # 8 neutered helper (tautological assertion) in a committed helper file
        g8 = json.loads(json.dumps(g))
        with tempfile.NamedTemporaryFile("w", suffix=".sv", delete=False) as fh:
            fh.write("module t; always @(posedge clk) "
                     "h_x: assert(a == b || 1'b1); endmodule\n")
            bad_helper = fh.name
        g8["helpers"] = [bad_helper]
        mutations["neutered_helper"] = g8
        for name, gm in mutations.items():
            ok2, errs2 = check_graph(gm)
            good = (not ok2)
            allok &= good
            print(f"[{'REJECT' if not ok2 else 'ACCEPT'}] negative:{name} "
                  f"({'expected' if good else 'MISSED'})")
            for e in errs2[:2]:
                print(f"    - {e}")
    print("\nSELFTEST:", "PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if show(sys.argv[1]) else 1)
