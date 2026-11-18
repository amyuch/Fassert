#!/usr/bin/env python3
"""sketch_extract.py -- lift a Yosys RTLIL netlist into a microarchitectural sketch.

Standalone and stdlib-only.  Input is a Yosys ``write_rtlil`` netlist, ideally
after ``proc`` (and, for hierarchical designs, ``flatten``).  Output:

  * ``<base>.sketch.json`` -- machine-readable sketch
  * ``<base>.sketch.dot``  -- Graphviz view for human inspection

The sketch is split into two trust tiers on purpose:

  * ``sorts``/``stages`` -- *structural*, mechanically derived from the netlist
    (a trusted vocabulary of registers, roles and cut points).
  * ``contracts``        -- *conjectured* relations (candidate helper
    assertions) that must still pass the soundness+vacuity gate before they may
    be promoted to assumptions.

This tool only reads the netlist; it never changes the proof.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# RTLIL tokenizer / parser
# ---------------------------------------------------------------------------

RE_MODULE = re.compile(r"^module\s+(\S+)")
RE_WIRE = re.compile(r"^\s*wire\b")
RE_WIDTH = re.compile(r"\bwidth\s+(\d+)")
RE_CELL = re.compile(r"^\s*cell\s+(\S+)\s+(\S+)\s*$")
RE_PARAM = re.compile(r"^\s*parameter\s+\\(\S+)\s+(.*?)\s*$")
RE_CONN = re.compile(r"^\s*connect\s+\\(\S+)\s+(.*?)\s*$")
RE_END = re.compile(r"^\s*end\s*$")
RE_MEMORY = re.compile(r"^\s*memory\b")
RE_ATTR_TOP = re.compile(r"^\s*attribute\s+\\top\s+1\b")

# State-holding cell types.  `$anyinit` is a formal-flow register with an
# unconstrained initial value; `$ff` is the clock-abstracted flop; both carry
# Q/D exactly like `$dff`.
REG_TYPES = {
    "$dff", "$dffe", "$adff", "$adffe", "$sdff", "$sdffe", "$dffsr",
    "$dffsre", "$aldff", "$aldffe", "$ff", "$ffe", "$anyinit",
    "$dlatch", "$adlatch", "$sdlatch",
}
# Data ports that are outputs of a cell (never traversed as inputs).
OUT_PORTS = {"Y", "Q", "DATA", "RD_DATA"}
# Non-data ports we never treat as cone inputs.
SKIP_PORTS = {"CLK", "C", "TRG", "ARGS"}
ARITH_TYPES = {"$add", "$sub", "$mul", "$div", "$mod", "$shl", "$shr",
               "$sshl", "$sshr", "$neg", "$pos", "$pow"}
CMP_TYPES = {"$eq", "$ne", "$lt", "$le", "$gt", "$ge", "$eqx", "$nex"}
CONST_RE = re.compile(r"^(?:\d+)?'[01xzXZ]+$")


class Sig:
    __slots__ = ("name", "msb", "lsb", "kind")

    def __init__(self, name=None, msb=None, lsb=None, kind="other"):
        self.name = name
        self.msb = msb
        self.lsb = lsb
        self.kind = kind

    def __repr__(self):
        return f"Sig({self.name!r},{self.msb},{self.lsb},{self.kind!r})"


def parse_sig(text):
    s = text.strip()
    if not s:
        return Sig(None, None, None, "empty")
    if s[0] in "{(":
        return Sig(None, None, None, "concat")
    if s.startswith("\\"):
        parts = s.split(None, 1)
        name = parts[0][1:]
        msb = lsb = None
        if len(parts) > 1:
            m = re.match(r"^\[(\d+)(?::(\d+))?\]$", parts[1].strip())
            if m:
                msb = int(m.group(1))
                lsb = int(m.group(2)) if m.group(2) is not None else msb
        return Sig(name, msb, lsb, "wire")
    if CONST_RE.match(s) or s in ("0", "1") or re.match(r"^\d+$", s):
        return Sig(None, None, None, "const")
    # Internal (auto-generated) wires are written without a leading backslash
    # (`$24y`, `$procmux$17_Y`, ...); they are still real signal names.
    if re.match(r"^[$A-Za-z_]", s):
        parts = s.split(None, 1)
        name = parts[0]
        msb = lsb = None
        if len(parts) > 1:
            m = re.match(r"^\[(\d+)(?::(\d+))?\]$", parts[1].strip())
            if m:
                msb = int(m.group(1))
                lsb = int(m.group(2)) if m.group(2) is not None else msb
        return Sig(name, msb, lsb, "wire")
    return Sig(None, None, None, "other")


def const_value(text):
    s = text.strip()
    m = re.match(r"^(?:(\d+))?'([01xzXZ]+)$", s)
    if m:
        bits = m.group(2)
        if any(b in "xzXZ" for b in bits):
            return None
        try:
            return int(bits, 2)
        except ValueError:
            return None
    if re.match(r"^\d+$", s):
        return int(s)
    return None


class Cell:
    __slots__ = ("type", "name", "params", "conns", "attrs", "line")

    def __init__(self, ctype, name, line):
        self.type = ctype
        self.name = name
        self.params = {}
        self.conns = {}
        self.attrs = {}
        self.line = line

    def out_wire(self):
        for p in ("Y", "Q", "DATA", "RD_DATA"):
            if p in self.conns:
                return parse_sig(self.conns[p]).name
        return None

    def in_wires(self):
        out = []
        for port, raw in self.conns.items():
            if port in OUT_PORTS or port in SKIP_PORTS:
                continue
            sg = parse_sig(raw)
            if sg.kind == "wire" and sg.name:
                out.append(sg.name)
        return out


class Module:
    def __init__(self, name):
        self.name = name
        self.wires = {}
        self.inputs = {}
        self.outputs = {}
        self.cells = []
        self.cell_by_name = {}
        self.is_top = False


def parse_rtlil(text):
    modules = []
    cur = None
    pending_top = False
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if RE_ATTR_TOP.match(line):
            pending_top = True
            i += 1
            continue
        m = RE_MODULE.match(line)
        if m:
            cur = Module(m.group(1).lstrip("\\"))
            cur.is_top = pending_top
            pending_top = False
            modules.append(cur)
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        c = RE_CELL.match(line)
        if c:
            cell = Cell(c.group(1), c.group(2), i + 1)
            i += 1
            while i < n and not RE_END.match(lines[i]):
                pm = RE_PARAM.match(lines[i])
                if pm:
                    cell.params[pm.group(1)] = pm.group(2)
                else:
                    cm = RE_CONN.match(lines[i])
                    if cm:
                        cell.conns[cm.group(1)] = cm.group(2)
                i += 1
            i += 1
            cur.cells.append(cell)
            cur.cell_by_name[cell.name] = cell
            continue
        if RE_WIRE.match(line):
            wm = RE_WIDTH.search(line)
            width = int(wm.group(1)) if wm else 1
            names = re.findall(r"\\([^\s\\]+(?:\s*\[\d+:\d+\])?)", line)
            for raw in names:
                raw = raw.strip()
                if not raw:
                    continue
                base = raw.split()[0]
                cur.wires[base] = width
                if " input " in line:
                    cur.inputs[base] = width
                if " output " in line:
                    cur.outputs[base] = width
            i += 1
            continue
        if RE_MEMORY.match(line):
            i += 1
            while i < n and not RE_END.match(lines[i]):
                i += 1
            i += 1
            continue
        if RE_END.match(line):
            cur = None
            i += 1
            continue
        i += 1
    return modules


# ---------------------------------------------------------------------------
# Sketch analysis
# ---------------------------------------------------------------------------

ROLE_RULES = [
    ("control", re.compile(r"(csr|mcycle|minstret|mhpm|counter|status|mode|"
                           r"privilege|state|fsm|phase|decoder|decode|trigger|"
                           r"irq|waitirq|pseudo_trigger)")),
    ("pipeline", re.compile(r"(valid|ready|stall|req|ack|fire|accept|enable|"
                            r"_en$|handshake|latched|prefetched|cached|insn_|"
                            r"opcode|is_|q_insn|alu_out|reg_op|reg_sh|"
                            r"reg_out)")),
    ("datapath", re.compile(r"(^|_)(add|sub|mul|div|alu|shift|shamt)(_|$)")),
    ("interface", re.compile(r"(rvfi|mem_|instr|pc_|pc$|imem|dmem|addr|"
                             r"wdata|rdata|wstrb|rmask|wmask|dbg|trap|"
                             r"pcpi|fwd|bypass)")),
    ("arch_state", re.compile(r"(regfile|regs\[|gpr|rs1|rs2|\brd\b|xreg|"
                              r"register)")),
]


def infer_role(name, kind):
    n = name.lower()
    if kind == "aux":
        return "aux"
    if kind == "counter":
        return "control"
    for role, rx in ROLE_RULES:
        if rx.search(n):
            return role
    if kind == "fsm":
        return "control"
    return "unknown"


def parse_const_param(raw):
    v = const_value(raw)
    if v is not None:
        return v
    try:
        return int(raw, 0)
    except (ValueError, TypeError):
        return None


def build_sketch(module):
    wires = module.wires
    driver = {}
    for cell in module.cells:
        w = cell.out_wire()
        if w:
            driver[w] = cell
    input_wires = set(module.inputs.keys())

    regs = {}
    for cell in module.cells:
        if cell.type not in REG_TYPES:
            continue
        q = parse_sig(cell.conns.get("Q", "")).name
        if not q:
            continue
        width = cell.params.get("WIDTH")
        width = int(width) if width and width.isdigit() else wires.get(q, 1)
        d = parse_sig(cell.conns.get("D", ""))
        regs[q] = {
            "name": q,
            "cell": cell.name,
            "cell_type": cell.type,
            "width": width,
            "d": d.name,
            "d_kind": d.kind,
            "enable": parse_sig(cell.conns.get("EN", "")).name if "EN" in cell.conns else None,
            "arst": parse_sig(cell.conns.get("ARST", "")).name if "ARST" in cell.conns else None,
            "srst": parse_sig(cell.conns.get("SRST", "")).name if "SRST" in cell.conns else None,
            "init": parse_const_param(cell.params.get("INIT", "")) if "INIT" in cell.params else None,
        }

    def cone(start_wires):
        stack = list(start_wires)
        seen = set()
        cells = set()
        src_regs = set()
        while stack:
            w = stack.pop()
            if not w or w in seen:
                continue
            seen.add(w)
            drv = driver.get(w)
            if drv is None:
                continue
            if drv.type in REG_TYPES:
                src_regs.add(w)
                continue
            cells.add(drv.name)
            for iw in drv.in_wires():
                stack.append(iw)
        return cells, src_regs

    # Formal-flow artifacts: `$past` history witnesses and fminit flops are not
    # design state -- tag them so they do not pollute contracts/clusters.
    reg_kind = {}
    for q in regs:
        if q.startswith("_witness_") or "$auto$fminit" in q:
            reg_kind[q] = "aux"

    # --- recurrences / counters -------------------------------------------
    recurrences = []
    for q, R in regs.items():
        if q in reg_kind or not R["d"]:
            continue
        cells, src = cone([R["d"]])
        inc = None
        enable = R["enable"]
        bounds = []
        for cn in cells:
            c = module.cell_by_name.get(cn)
            if c is None:
                continue
            if c.type in ("$add", "$sub"):
                ports = {p: parse_sig(c.conns[p]) for p in ("A", "B") if p in c.conns}
                if any(s.name == q for s in ports.values()):
                    other = [s for s in ports.values() if s.name != q]
                    if other and other[0].kind == "const":
                        v = const_value(c.conns["A"] if ports.get("B") and ports["B"].name == q else c.conns["B"])
                        if v == 1:
                            inc = 1 if c.type == "$add" else -1
            if c.type in CMP_TYPES:
                ops = {p: parse_sig(c.conns[p]) for p in ("A", "B") if p in c.conns}
                if any(s.name == q for s in ops.values()):
                    for p, s in ops.items():
                        if s.kind == "const":
                            v = const_value(c.conns[p])
                            if v is not None:
                                bounds.append(v)
            if c.type in ("$mux", "$pmux") and enable is None:
                s = parse_sig(c.conns.get("S", ""))
                if s.kind == "wire" and s.name:
                    ins = [parse_sig(c.conns[p]) for p in c.conns if p in ("A", "B")]
                    if any(x.name == q for x in ins):
                        enable = s.name
        if inc is not None:
            reg_kind[q] = "counter"
            recurrences.append({
                "reg": q,
                "width": R["width"],
                "increment": inc,
                "enable": enable,
                "bound_candidates": sorted(set(bounds)),
                "evidence": "structural",
            })

    # --- FSMs --------------------------------------------------------------
    fsms = []
    for q, R in regs.items():
        if q in reg_kind:
            continue
        if R["width"] > 8 or not R["d"]:
            continue
        name_hit = re.search(r"(state|fsm|phase)", q, re.I) is not None
        cells, _ = cone([R["d"]])
        muxes = sum(1 for cn in cells if module.cell_by_name.get(cn) and
                    module.cell_by_name[cn].type in ("$mux", "$pmux"))
        arith = sum(1 for cn in cells if module.cell_by_name.get(cn) and
                    module.cell_by_name[cn].type in ARITH_TYPES)
        # A next-state function decodes the register against its own value.
        self_eq = 0
        for cn in cells:
            c = module.cell_by_name.get(cn)
            if c is None or c.type not in CMP_TYPES:
                continue
            for p in ("A", "B"):
                if p in c.conns and parse_sig(c.conns[p]).name == q:
                    self_eq += 1
        if name_hit or (R["width"] >= 2 and arith == 0 and self_eq >= 1 and muxes >= 1):
            reg_kind[q] = "fsm"
            fsms.append({
                "reg": q,
                "width": R["width"],
                "encoding": "binary",
                "name_hint": name_hit,
                "evidence": "structural",
            })

    # --- handshakes --------------------------------------------------------
    HANDSHAKE_ROLE = [
        ("valid", re.compile(r"(^|[._])valid($|[._\d])|(^|[._])vld($|[._\d])", re.I)),
        ("ready", re.compile(r"(^|[._])ready($|[._\d])|(^|[._])rdy($|[._\d])", re.I)),
        ("req", re.compile(r"(^|[._])req($|[._\d])|(^|[._])request($|[._\d])", re.I)),
        ("ack", re.compile(r"(^|[._])ack($|[._\d])|(^|[._])acknowledge($|[._\d])", re.I)),
        ("stall", re.compile(r"(^|[._])stall($|[._\d])", re.I)),
    ]
    valid_like, ready_like, other_like = [], [], []
    for q, R in regs.items():
        if R["width"] != 1:
            continue
        for role, rx in HANDSHAKE_ROLE:
            if rx.search(q):
                if role == "valid":
                    valid_like.append(q)
                elif role == "ready":
                    ready_like.append(q)
                else:
                    other_like.append((role, q))
                break
    handshakes = []
    used_ready = set()
    for v in valid_like:
        best, best_len = None, 0
        vp = v.rsplit(".", 1)
        for r in ready_like:
            if r in used_ready:
                continue
            rp = r.rsplit(".", 1)
            pre = os.path.commonprefix([vp[0], rp[0]])
            if len(pre) > best_len:
                best, best_len = r, len(pre)
        if best is not None and best_len >= max(len(vp[0]), 1) - 4:
            used_ready.add(best)
            handshakes.append({"valid": v, "ready": best, "evidence": "structural"})
    for role, q in other_like:
        handshakes.append({role: q, "evidence": "structural"})

    # --- datapath (weak) ---------------------------------------------------
    datapath = []
    for cell in module.cells:
        if cell.type in ARITH_TYPES:
            out = cell.out_wire()
            owner = None
            for q, R in regs.items():
                if R["d"] == out:
                    owner = q
                    break
            datapath.append({
                "op": cell.type,
                "out": out,
                "owner_reg": owner,
                "evidence": "structural",
            })

    # --- register dependency graph ----------------------------------------
    dep = {}
    for q, R in regs.items():
        if not R["d"]:
            dep[q] = []
            continue
        _, src = cone([R["d"]])
        dep[q] = sorted(src)

    # --- clusters ("stages") ----------------------------------------------
    names = list(regs.keys())

    def dominant_prefix(names):
        cnt = defaultdict(int)
        for n in names:
            parts = n.split(".")
            for k in range(1, len(parts)):
                cnt[".".join(parts[:k])] += 1
        best, thresh = "", max(2, len(names) // 2)
        for pref, c in cnt.items():
            if c >= thresh and len(pref) > len(best):
                best = pref
        return best

    common_prefix = dominant_prefix(names)

    def cluster_of(name):
        if common_prefix and name.startswith(common_prefix + "."):
            rel = name[len(common_prefix) + 1:]
        else:
            rel = name
        comp = rel.split(".")[0].split("[")[0]
        if "_" in comp:
            head = comp.split("_")[0]
            if len(head) >= 2:
                comp = head
        return comp or "(top)"

    clusters = defaultdict(list)
    for q in names:
        clusters[cluster_of(q)].append(q)

    # --- property cone / cut set ------------------------------------------
    assert_cells = []
    for cell in module.cells:
        if cell.type == "$assert":
            assert_cells.append(cell)
        elif cell.type == "$check" and cell.params.get("FLAVOR", "").strip('"') == "assert":
            assert_cells.append(cell)
    frontier = set()
    next_level = set()
    endpoints = []
    for a in assert_cells:
        starts = []
        for p in ("A", "EN"):
            if p in a.conns:
                sg = parse_sig(a.conns[p])
                if sg.kind == "wire" and sg.name:
                    starts.append(sg.name)
        _, fregs = cone(starts)
        frontier |= fregs
        endpoints.append({
            "name": a.name.lstrip("\\"),
            "flavor": "assert",
            "frontier": sorted(fregs),
        })
    for q in list(frontier):
        next_level |= set(dep.get(q, []))
    next_level -= frontier

    cut_groups = defaultdict(list)
    for q in frontier:
        cut_groups[cluster_of(q)].append(q)

    # --- assemble sorts ----------------------------------------------------
    reg_cluster = {q: cluster_of(q) for q in regs}
    sorts = []
    for q, R in regs.items():
        kind = reg_kind.get(q, "plain")
        sorts.append({
            "name": q,
            "cell_type": R["cell_type"],
            "width": R["width"],
            "role": infer_role(q, kind),
            "kind": kind,
            "enable": R["enable"],
            "reset": R["arst"] or R["srst"],
            "init": R["init"],
            "cluster": reg_cluster[q],
            "in_property_frontier": q in frontier,
        })

    sketch = {
        "design": {
            "module": module.name,
            "n_registers": len(regs),
            "n_cells": len(module.cells),
            "n_properties": len(assert_cells),
            "common_prefix": common_prefix,
        },
        "sorts": {
            "registers": sorted(sorts, key=lambda d: d["name"]),
            "inputs": sorted(module.inputs.keys()),
        },
        "stages": {
            "clusters": {k: sorted(v) for k, v in sorted(clusters.items())},
            "edges": {k: v for k, v in sorted(dep.items())},
        },
        "contracts": {
            "recurrences": recurrences,
            "handshakes": handshakes,
            "fsms": fsms,
            "datapath": datapath,
        },
        "cutset": {
            "frontier": sorted(frontier),
            "next": sorted(next_level),
            "groups": {k: sorted(v) for k, v in sorted(cut_groups.items())},
        },
        "property": {"endpoints": endpoints},
        "_meta": {
            "tool": "sketch_extract.py",
            "reg_types": sorted(REG_TYPES),
            "evidence_tiers": {
                "structural": "machine-derived; trusted vocabulary",
                "contracts": "conjectured; must pass soundness+vacuity gate",
            },
        },
    }
    return sketch


# ---------------------------------------------------------------------------
# Graphviz
# ---------------------------------------------------------------------------

ROLE_COLOR = {
    "control": "#f7b6d2",
    "pipeline": "#aec7e8",
    "interface": "#c5b0d5",
    "arch_state": "#c7e9c0",
    "unknown": "#dddddd",
}


def write_dot(sketch, path, max_nodes=300):
    regs = {r["name"]: r for r in sketch["sorts"]["registers"]}
    frontier = set(sketch["cutset"]["frontier"])
    kinds = {}
    for c in sketch["contracts"]["recurrences"]:
        kinds[c["reg"]] = "counter"
    for c in sketch["contracts"]["fsms"]:
        kinds[c["reg"]] = "fsm"

    keep = set(frontier)
    if len(regs) <= max_nodes:
        keep |= set(regs.keys())
    else:
        for n, r in regs.items():
            if n in kinds:
                keep.add(n)
            if r["role"] != "unknown":
                keep.add(n)
    keep |= {c["reg"] for c in sketch["contracts"]["recurrences"]}
    keep |= {c["reg"] for c in sketch["contracts"]["fsms"]}
    for h in sketch["contracts"]["handshakes"]:
        for v in h.values():
            if isinstance(v, str):
                keep.add(v)
    keep &= set(regs.keys())

    lines = ["digraph sketch {", '  rankdir=LR;',
             '  node [shape=box, style="rounded,filled", fontname="monospace", fontsize=9];']
    by_cluster = defaultdict(list)
    for n in keep:
        by_cluster[regs[n]["cluster"]].append(n)
    for cluster, members in sorted(by_cluster.items()):
        lines.append(f'  subgraph "cluster_{cluster}" {{')
        lines.append(f'    label="{cluster}"; style=dashed; color=gray;')
        for n in sorted(members):
            r = regs[n]
            color = "#ffbbbb" if n in frontier else ROLE_COLOR.get(r["role"], "#dddddd")
            kind = kinds.get(n, "")
            label = f"{n}\\n({r['width']}b, {r['role']})"
            shape = "box"
            if kind == "fsm":
                shape = "component"
            elif kind == "counter":
                shape = "cylinder"
            lines.append(f'    "{n}" [label="{label}", fillcolor="{color}", shape={shape}];')
        lines.append("  }")
    for q, preds in sketch["stages"]["edges"].items():
        if q not in keep:
            continue
        for p in preds:
            if p in keep:
                lines.append(f'  "{p}" -> "{q}";')
    lines.append("}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Human summary
# ---------------------------------------------------------------------------

def print_summary(sketch):
    d = sketch["design"]
    print(f"== sketch: module {d['module']} ==")
    print(f"registers={d['n_registers']} cells={d['n_cells']} properties={d['n_properties']}")
    print(f"common prefix: {d['common_prefix']!r}")
    print("\n-- clusters (stage proxy) --")
    for c, members in sketch["stages"]["clusters"].items():
        print(f"  {c:24} {len(members):3} regs")
    print("\n-- contracts --")
    for c in sketch["contracts"]["recurrences"]:
        print(f"  counter : {c['reg']}  width={c['width']} inc={c['increment']} "
              f"en={c['enable']} bounds={c['bound_candidates']}")
    for c in sketch["contracts"]["fsms"]:
        print(f"  fsm     : {c['reg']}  width={c['width']} enc={c['encoding']}")
    for c in sketch["contracts"]["handshakes"]:
        print(f"  handshake: {c}")
    print(f"  datapath ops: {len(sketch['contracts']['datapath'])}")
    print("\n-- property cut set (frontier) --")
    for g, members in sketch["cutset"]["groups"].items():
        print(f"  {g:24} {len(members):3}: {', '.join(members[:8])}"
              + (" ..." if len(members) > 8 else ""))
    print(f"  frontier total={len(sketch['cutset']['frontier'])} "
          f"next-level={len(sketch['cutset']['next'])}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rtlil", help="design.il (Yosys write_rtlil output)")
    ap.add_argument("-o", "--out", help="sketch JSON path (default <base>.sketch.json)")
    ap.add_argument("--dot", help="Graphviz path (default <base>.sketch.dot)")
    ap.add_argument("--module", help="module to sketch (default: top / largest)")
    ap.add_argument("--max-dot-regs", type=int, default=300)
    ap.add_argument("--no-dot", action="store_true")
    args = ap.parse_args(argv)

    with open(args.rtlil) as f:
        text = f.read()
    modules = parse_rtlil(text)
    if not modules:
        sys.exit(f"no modules found in {args.rtlil}")
    if args.module:
        module = next((m for m in modules if m.name == args.module), None)
        if module is None:
            sys.exit(f"module {args.module!r} not found")
    else:
        top = [m for m in modules if m.is_top]
        module = top[0] if top else max(modules, key=lambda m: len(m.cells))

    sketch = build_sketch(module)
    base = os.path.splitext(args.rtlil)[0]
    out = args.out or base + ".sketch.json"
    with open(out, "w") as f:
        json.dump(sketch, f, indent=2)
    print(f"wrote {out}")
    if not args.no_dot:
        dot = args.dot or base + ".sketch.dot"
        write_dot(sketch, dot, max_nodes=args.max_dot_regs)
        print(f"wrote {dot}")
    print()
    print_summary(sketch)


if __name__ == "__main__":
    main()
