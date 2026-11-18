import re
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from common.util import run_cmd

def get_design_data(design_file, top_module, regen_design_hier):
    design_json_path = Path(__file__).parents[0] / "generated" / "tmp" / (top_module + ".json")
    if not design_json_path.exists() or regen_design_hier:
        print("Re-generating design hierarchy for " + top_module)
        gen_design_hierarchy(design_file, top_module, design_json_path)
    design_data = load_design(design_json_path)
    return design_data

def gen_design_hierarchy(design_file, top, json_filename):
    gen_path = Path(__file__).parents[0] / "generated"
    tmp_path = Path(gen_path / "tmp")
    Path(tmp_path).mkdir(parents=True, exist_ok=True)

    ys_script = tmp_path / "tmp_get_design_hier.ys"
    with open(ys_script, "w") as f:
        f.write(f"read_verilog -sv {design_file}\n")
        f.write(f"hierarchy -top {top}\n")
        f.write("proc\n")
        f.write(f"write_json {json_filename}\n")

    run_cmd(f"yosys -q {ys_script}", print_stderr=True)

def load_design(json_filepath):
    with open(json_filepath, "r") as f:
        design = json.load(f)
    return design

def escaped_verilog_hierarchy_path_split(signal_path):
    ret = []
    part = ""
    last_c = ""
    in_escaped_name = False
    for c in signal_path:
        if not in_escaped_name and c == ".":
            if part != "":
                ret.append(part)
            part = ""
        elif c == "\\":
            if not in_escaped_name and last_c not in ("", "."):
                raise Exception(f"ERROR: found a \\ character in the middle of a path name: {signal_path}")
            in_escaped_name = True
            part += c
        elif c == " ":
            if in_escaped_name:
                in_escaped_name = False
                part += c
                if part.strip() != "":
                    ret.append(part)
                part = ""
            else:
                raise Exception(f"ERROR: Found an unexpected space in the signal path: {signal_path}")
        else:
            part += c
        last_c = c
    if part.strip(" ") != "":
        ret.append(part)
    return ret

def trim_size_marker(signame):
    if signame[-1] == "]":
        marker_start = signame.rfind("[")
        signame = signame[0:marker_start]
    return signame

def jasper_tcl_sig_list_split(signal_path):
    ret = []
    part = ""
    last_c = ""
    ignore_spaces = False
    for c in signal_path:
        if not ignore_spaces and c == " ":
            ret.append(part)
            part = ""
        elif c == "{":
            if last_c not in ("", " "):
                print(f"ERROR: found a {{ character in the middle of a signal name: {signal_path}\n")
            ignore_spaces = True
            part += c
        elif c == "}":
            if ignore_spaces:
                ignore_spaces = False
                part += c
            else:
                print(f"ERROR: Found an unexpected }} in the signal path: {signal_path}")
        else:
            part += c
        last_c = c
    ret.append(part.rstrip("\n"))
    return ret

def jasper_tcl_get_split_path_of_instance(tcl_sig_path):
    path = tcl_sig_path.lstrip("{")
    path = path.rstrip("}")
    split_inst_path = escaped_verilog_hierarchy_path_split(path)
    return split_inst_path[0:-1]

def jasper_tcl_sig_extract_sig_name(tcl_sig_path):
    path = tcl_sig_path.lstrip("{")
    path = path.rstrip("}")
    split_inst_path = escaped_verilog_hierarchy_path_split(path)
    return split_inst_path[-1]

def jasper_tcl_sig_add_top_module(top_module, tcl_sig_path, connector="."):
    if tcl_sig_path.startswith("{"):
        return f"{tcl_sig_path[0]}{top_module}{connector}{tcl_sig_path[1:]}"
    else:
        return f"{top_module}{connector}{tcl_sig_path}"

def remove_curley_brackets(sig):
    if len(sig) < 1:
        return sig
    new_sig = sig
    if sig[0] == "{":
        new_sig = sig[1:]
    if sig[-1] == "}":
        new_sig = new_sig[:-1]
    return new_sig

def flatten_signal_path(sig_path, connector="__"):
    flattened_path = remove_curley_brackets(sig_path)
    parts = escaped_verilog_hierarchy_path_split(flattened_path)
    unescaped_parts = []
    for part in parts:
        p_unesc = flatten_name(part)
        p_unesc = p_unesc.replace(".", connector)
        unescaped_parts.append(p_unesc)
    return connector.join(unescaped_parts)

def get_expanded_path(p, connector="__"):
    parts = escaped_verilog_hierarchy_path_split(p)
    return connector.join(parts)

def get_hierarchical_path(p, connector_expanded="__", connector_hier="."):
    parts = p.split(connector_expanded)
    return connector_hier.join(parts)

def escape_name(signame):
    special_chars = ["[", "]", "."]
    if any(sc in signame for sc in special_chars):
        return "\\" + signame + " "
    else:
        return signame

def flatten_name(signame, flattener="_"):
    special_chars1 = ["[", "]", "$", ":", "/"]
    special_chars2 = ["."]
    signame = unescape_name(signame)
    for sc in special_chars1:
        signame = signame.replace(sc, flattener)
    for sc in special_chars2:
        signame = signame.replace(sc, flattener * 2)
    return signame

def unescape_name(signame):
    if not (signame[0] == "\\" and signame[-1] == " "):
        return signame
    return signame[1:-1]

def connect_hier_paths(part1, part2, connector="."):
    if part1 == "":
        return part2
    else:
        return part1 + connector + part2

def get_module_type(design_data, split_inst_path):
    mod_type = split_inst_path[0]
    i = 1
    while i < len(split_inst_path):
        mod_type = design_data["modules"][mod_type]["cells"][unescape_name(split_inst_path[i])]["type"]
        i += 1
    return mod_type
