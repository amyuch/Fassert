#!/usr/bin/env python3
"""Generate the curated benchmark test lists.

The active corpus has 104 CIll cases, but the three picorv32 ``_altops``
variants are abstracted add/sub and are excluded.  The reduced test list
therefore has 101 cases:

    picorv32  40
    serv       4
    nerv      25
    flute     17
    piccolo   15

``testlist.csv`` contains those 101 cases with a cumulative ``tier`` column:

* ``smoke``    - 10 cases;
* ``core``     - 30 additional cases; the core run is 40;
* ``extended`` - 61 additional cases; extended is all 101.

The 40-case core suite is 23 picorv32, 4 serv, 3 nerv, 5 flute, and 5 piccolo.

``testlist_full.csv`` is a separate 5-case full-property suite using the
official riscv-formal imports under ``automation/pcd``:
``insn_addi``, ``insn_beq``, ``insn_c_j``, ``insn_jal``, and ``insn_mulh``.
All five also appear in the 23-case picorv32 core.  ``benchmarks/picorv32_full``
is the preserved *reduced* corpus and is not this full-property list.

``test4neuroabs`` is deliberately excluded.

Usage:
    python3 make_testlist.py [--check]
"""

import csv
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "picorv32" / "manifest.csv"

SMOKE = {
    # picorv32: add/addi, mul, branch, compressed jump, and shift.
    "picorv32/insn_add",
    "picorv32/insn_addi",
    "picorv32/insn_mul",
    "picorv32/insn_beq",
    "picorv32/insn_c_j",
    "picorv32/insn_sra",
    "serv/reg",
    "nerv/reg",
    "flute/ADD",
    "piccolo/ADD",
}

CORE = {
    # picorv32: logic is represented by xor, arithmetic by div/rem, and the
    # remaining branch/jump/memory/compressed/upper cases add diversity.
    "picorv32/insn_mulh",
    "picorv32/insn_div",
    "picorv32/insn_rem",
    "picorv32/insn_remu",
    "picorv32/insn_bge",
    "picorv32/insn_jal",
    "picorv32/insn_bne",
    "picorv32/insn_bgeu",
    "picorv32/insn_blt",
    "picorv32/insn_jalr",
    "picorv32/insn_lw",
    "picorv32/insn_sw",
    "picorv32/insn_sltu",
    "picorv32/insn_lui",
    "picorv32/insn_auipc",
    "picorv32/insn_c_add",
    "picorv32/insn_xor",
    # serv: all four properties; reg is in smoke.
    "serv/causal",
    "serv/pc_bwd",
    "serv/pc_fwd",
    # nerv: CSR and bus, in addition to the register smoke case.
    "nerv/csrw_mstatus",
    "nerv/bus_dmem",
    # flute: ADD is smoke; add immediate, branch, jump, store.
    "flute/ADDI",
    "flute/BNE",
    "flute/JAL",
    "flute/SB",
    # piccolo: ADD is smoke; add immediate, logic, branch, jump, load.
    "piccolo/ANDI",
    "piccolo/BEQ",
    "piccolo/JAL",
    "piccolo/LB",
}

FULL = [
    ("picorv32_insn_addi", "alu"),
    ("picorv32_insn_beq", "branch"),
    ("picorv32_insn_c_j", "compressed"),
    ("picorv32_insn_jal", "jump"),
    ("picorv32_insn_mulh", "mul"),
]

FIELDS = ["tier", "family", "case", "category", "semantics", "checker", "path", "note"]

CSrc = {
    "causal": ("causal", "rvfi_causal_check"),
    "pc_bwd": ("pc", "rvfi_pc_bwd_check"),
    "pc_fwd": ("pc", "rvfi_pc_fwd_check"),
    "reg": ("register", "rvfi_reg_check"),
}

NERV = {
    "causal": ("causal", "rvfi_causal_check"),
    "ill": ("illegal", "rvfi_ill_check"),
    "pc_bwd": ("pc", "rvfi_pc_bwd_check"),
    "pc_fwd": ("pc", "rvfi_pc_fwd_check"),
    "reg": ("register", "rvfi_reg_check"),
    "unique": ("unique", "rvfi_unique_check"),
    "csrc_const_custom_ro": ("csr-read", "rvfi_csrc_const_check"),
    "csrc_inc_mhpmcounter5": ("csr-read", "rvfi_csrc_inc_check"),
    "csrc_upcnt_mcycle": ("csr-read", "rvfi_csrc_upcnt_check"),
    "csrc_upcnt_minstret": ("csr-read", "rvfi_csrc_upcnt_check"),
}


def picorv32_rows():
    rows = []
    for r in csv.DictReader(open(MANIFEST)):
        if r["active"] != "yes" or r["semantics"] == "altops":
            continue
        mem = r["group"] in ("load", "store")
        rows.append({
            "family": "picorv32",
            "case": r["case"],
            "category": r["group"],
            "semantics": r["semantics"],
            "checker": "rvfi_insn_check_mem" if mem else "rvfi_insn_check",
            "note": r["note"],
        })
    return rows


def serv_nerv_rows(family):
    rows = []
    for d in sorted((HERE / family).iterdir()):
        if not (d.is_dir() and (d / "ric3.toml").exists()):
            continue
        case = d.name
        if family == "nerv":
            if case.startswith("bus_"):
                cat, checker = "bus", "rvfi_%s_check" % case
            elif case.startswith("csr_ill_"):
                cat, checker = "csr-ill", "rvfi_csr_ill_check"
            elif case.startswith("csrw_"):
                cat, checker = "csr-write", "rvfi_csrw_check"
            else:
                cat, checker = NERV[case]
        else:
            cat, checker = CSrc[case]
        rows.append({
            "family": family,
            "case": case,
            "category": cat,
            "semantics": "normal",
            "checker": checker,
            "note": "property-specific",
        })
    return rows


def ila_rows(family):
    rows = []
    for d in sorted((HERE / family).iterdir()):
        if not (d.is_dir() and (d / "ric3.toml").exists()):
            continue
        case = d.name
        if case.startswith("B"):
            cat = "branch"
        elif case == "JAL":
            cat = "jump"
        elif case in ("LB",):
            cat = "load"
        elif case in ("SB", "SH"):
            cat = "store"
        elif case in ("AUIPC", "LUI"):
            cat = "upper"
        elif case in ("ANDI", "OR", "OR_new", "XOR", "XORI", "XOR_new", "SLTI"):
            cat = "logic"
        elif case in ("SRA",):
            cat = "shift"
        else:
            cat = "alu"
        rows.append({
            "family": family,
            "case": case,
            "category": cat,
            "semantics": "normal",
            "checker": "ila_normalassert",
            "note": "immediate ILA assertion",
        })
    return rows


def active_rows():
    rows = picorv32_rows()
    rows += serv_nerv_rows("serv")
    rows += serv_nerv_rows("nerv")
    rows += ila_rows("flute")
    rows += ila_rows("piccolo")
    return rows


def full_rows():
    rows = []
    for case, category in FULL:
        rows.append({
            "family": "official",
            "case": case,
            "category": category,
            "semantics": "full",
            "checker": "rvfi_insn_check",
            "path": "automation/pcd/cases/official/%s" % case,
            "note": "official PCD/riscv-formal fullcheck import",
        })
    return rows


def assign_tiers(rows):
    for row in rows:
        key = "%s/%s" % (row["family"], row["case"])
        row["tier"] = "smoke" if key in SMOKE else "core" if key in CORE else "extended"
        row["path"] = "benchmarks/%s/%s" % (row["family"], row["case"])
    return rows


def validate(rows, fullrows):
    keys = {"%s/%s" % (r["family"], r["case"]) for r in rows}
    fullkeys = {"%s/%s" % (r["family"], r["case"]) for r in fullrows}
    for name, group in (("smoke", SMOKE), ("core", CORE)):
        missing = group - keys
        if missing:
            raise SystemExit("%s entries missing from active cases: %s" % (name, sorted(missing)))
    if SMOKE & CORE:
        raise SystemExit("smoke/core overlap: %s" % sorted(SMOKE & CORE))
    if len(rows) != 101:
        raise SystemExit("expected 101 non-ALT OPS active cases, got %d" % len(rows))
    expected_full = {"official/%s" % c for c, _ in FULL}
    if fullkeys != expected_full:
        raise SystemExit("full list mismatch")
    for r in rows:
        p = HERE.parent / r["path"]
        if not (p / "run.sh").exists():
            raise SystemExit("missing run.sh: %s" % p)
    for r in fullrows:
        p = HERE.parent / r["path"]
        if not (p / "build" / "build.sh").exists():
            raise SystemExit("missing build/build.sh: %s" % p)


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    check = "--check" in sys.argv
    rows = assign_tiers(active_rows())
    family_order = {f: i for i, f in enumerate(("picorv32", "serv", "nerv", "flute", "piccolo"))}
    tier_order = {"smoke": 0, "core": 1, "extended": 2}
    rows.sort(key=lambda r: (tier_order[r["tier"]], family_order[r["family"]], r["case"]))
    fullrows = full_rows()
    for row in fullrows:
        row["tier"] = "full"
    validate(rows, fullrows)

    counts = {t: sum(1 for r in rows if r["tier"] == t) for t in ("smoke", "core", "extended")}
    print("active: %d  smoke=%d core=+%d (total %d) extended=+%d (total %d)" % (
        len(rows), counts["smoke"], counts["core"], counts["smoke"] + counts["core"],
        counts["extended"], len(rows)))
    print("full: %d" % len(fullrows))
    for family in ("picorv32", "serv", "nerv", "flute", "piccolo"):
        print("  %-10s %d" % (family, sum(1 for r in rows if r["family"] == family)))

    if check:
        return
    write_csv(HERE / "testlist.csv", rows)
    write_csv(HERE / "testlist_full.csv", fullrows)
    print("wrote testlist.csv and testlist_full.csv")


if __name__ == "__main__":
    main()
