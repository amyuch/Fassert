"""Check synchronous BTOR property transfers against frozen model artifacts.

The implemented certificate is a structural projection, not arbitrary semantic
equivalence. Every source transition in the relevant cone is reproduced by the
destination under an explicit state/input mapping. All source constraints must
also be present after mapping. Unsupported bridges fail closed.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import shlex
import re
from typing import Any

from common.pcd_util import sha256_file
from . import btor, bitproj, expr, smt, model_smt, semantics


FORMAT = "btor-projection"
CHECKER = "pcd-compose/0.1"


class CompositionError(ValueError):
    pass


class ModelStore:
    def __init__(self, proof: dict[str, Any], base: str):
        self.proof = proof
        self.base = Path(base)
        self.cache: dict[str, btor.Model] = {}
        self.normalized: dict[tuple, dict[int, tuple[str, ...]]] = {}

    def get(self, model_id: str) -> btor.Model:
        if model_id in self.cache:
            return self.cache[model_id]
        if model_id not in self.proof["models"].values():
            raise CompositionError(f"unregistered model {model_id}")
        artifact = self.proof.get("model_artifacts", {}).get(model_id)
        if not isinstance(artifact, dict):
            raise CompositionError(f"missing frozen model artifact for {model_id}")
        if model_id != "btor:" + artifact.get("sha256", ""):
            raise CompositionError("model identity does not match its artifact hash")
        path = self.base / artifact["path"]
        if not path.is_file():
            raise CompositionError(f"missing or changed model artifact: {artifact['path']}")
        contents = path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != artifact["sha256"]:
            raise CompositionError(f"missing or changed model artifact: {artifact['path']}")
        model = btor.Model(path, text=contents.decode("utf-8"))
        self.cache[model_id] = model
        return model


def bound_property(node: dict, guarantee: dict, store: ModelStore) -> tuple[btor.Model, str]:
    binding = guarantee.get("binding") or {}
    if binding.get("kind") != "btor-bad":
        raise CompositionError(f"{node['id']}: guarantee needs an exact btor-bad binding")
    ast = expr.parse(guarantee["expr"])
    if ast[0] != "var" or guarantee["sort"] != "Bool":
        raise CompositionError("a bound property must be a Boolean atom, not an arbitrary formula")
    model = store.get(node["model"])
    name = binding.get("property")
    if name not in model.properties:
        raise CompositionError(f"property {name!r} is not in the bound model")
    cert = node["certificate"]
    if cert.get("goal") != guarantee.get("name"):
        raise CompositionError("property binding does not match the certificate's proved guarantee")
    if cert["evidence"] == "REPLAY":
        assertion = cert.get("assertion") or {}
        if assertion.get("name") != name:
            raise CompositionError("replay assertion does not match the model property binding")
        run = cert["run"]
        if run.get("model_sha256") != node["model"]:
            raise CompositionError("bound replay model identity disagrees with the obligation")
        log = run.get("log")
        if not log:
            raise CompositionError("a bound replay needs its frozen engine log")
        path = store.base / log
        if not path.is_file() or sha256_file(str(path)) != run.get("log_sha256"):
            raise CompositionError("bound replay log is missing or changed")
        command = run["command"]
        argv = shlex.split(command) if isinstance(command, str) else command
        text = re.sub(r"\x1b\[[0-9;]*m", "", path.read_text(encoding="utf-8"))
        if re.search(r"Not Inductive|Terminated by timeout|# external timeout|(?m:^rc=[1-9])", text):
            raise CompositionError("bound replay includes an incomplete or failed engine result")
        if len(argv) < 3 or Path(argv[0]).name != "ric3":
            raise CompositionError("bound property replay requires a registered ric3 invocation")
        if argv[1:3] == ["cill", "check"]:
            if len(argv) != 3:
                raise CompositionError("bound cill replay has unsupported command options")
            if "All properties are inductive" not in text or "BMC found no CEX" not in text:
                raise CompositionError("bound cill replay must prove the whole property group")
        elif argv[1] == "check" and len(argv) > 3 and argv[3] in {"ic3", "kind", "portfolio", "multi-prop"}:
            options = argv[4:]
            if len(options) % 2 or any(options[i] not in {"--prop", "--time-limit"}
                                      or not options[i + 1].isdecimal() for i in range(0, len(options), 2)):
                raise CompositionError("bound engine replay has unsupported command options")
            if not re.search(r"(?m)^\s*UNSAT\s*$", text):
                raise CompositionError("bound engine replay has no explicit proof result")
            if re.search(r"(?m)^\s*SAT\s*$", text):
                raise CompositionError("bound engine replay reports a counterexample result")
            if "--prop" in argv:
                if argv.count("--prop") != 1:
                    raise CompositionError("ambiguous engine property selection")
                index = argv.index("--prop")
                if index + 1 >= len(argv) or argv[index + 1] != str(list(model.properties).index(name)):
                    raise CompositionError("engine --prop does not select the bound model property")
            elif argv[3] == "multi-prop":
                # rIC3's multi-prop engine checks the whole selected property
                # group; a bare UNSAT is a proof of every property in the
                # model.  This is the same whole-group evidence cill provides,
                # but for an explicit BTOR model.
                pass
            elif len(model.properties) != 1:
                raise CompositionError("multi-property replay requires an explicit property selection")
        else:
            raise CompositionError("unsupported bound property engine invocation")
    elif cert.get("format") not in {FORMAT, model_smt.FORMAT}:
        raise CompositionError("a model property needs a bound engine proof or another checked projection")
    return model, name


def check_projection(node: dict, nodes: dict[str, dict], store: ModelStore) -> dict[str, Any]:
    """Verify a certificate; raise on every unproved relationship."""
    cert = node["certificate"]
    if node["role"] != "transfer" or cert.get("checker") != CHECKER:
        raise CompositionError("BTOR projections require role=transfer and the pcd-compose checker")
    payload = cert.get("payload", {})
    required_payload = {"source", "state_map", "input_map"}
    allowed_payload = required_payload | {"discharge", "free_map"}
    if (not isinstance(payload, dict) or not required_payload <= payload.keys()
            or set(payload) - allowed_payload):
        raise CompositionError(
            "projection payload requires source, state_map, input_map and optional discharge/free_map"
        )
    ref = payload["source"]
    if not isinstance(ref, dict) or set(ref) != {"node", "guarantee"}:
        raise CompositionError("invalid projection source reference")
    discharge = payload.get("discharge", {})
    if not isinstance(discharge, dict):
        raise CompositionError("constraint discharge must be an object")
    witnesses = []
    for key, witness in discharge.items():
        try:
            canonical = str(int(key)) == key
        except (TypeError, ValueError):
            canonical = False
        if not canonical or not isinstance(witness, dict) or set(witness) != {"node", "guarantee"}:
            raise CompositionError("invalid source-constraint discharge reference")
        if witness not in witnesses:
            witnesses.append(witness)
    if node.get("requires") != [ref, *witnesses] or ref["node"] == node["id"]:
        raise CompositionError("projection must require its distinct source guarantee and every discharge witness")
    source_node = nodes.get(ref["node"])
    if source_node is None:
        raise CompositionError("projection source node is missing")
    scert = source_node["certificate"]
    if scert.get("verdict") != "proved" or scert["evidence"] not in {"CHECKED", "REPLAY"}:
        raise CompositionError("projection source is not proved")
    source_guarantees = [g for g in source_node["provides"] if g["name"] == ref["guarantee"]]
    target_guarantees = [g for g in node["provides"] if g["name"] == cert.get("goal")]
    if len(source_guarantees) != 1 or len(target_guarantees) != 1:
        raise CompositionError("ambiguous projection endpoints")
    source, source_name = bound_property(source_node, source_guarantees[0], store)
    destination, destination_name = bound_property(node, target_guarantees[0], store)
    source_free = {
        ref for ref in source.states
        if source.initial.get(ref) is None and source.next.get(ref) is None
    }
    destination_free = {
        ref for ref in destination.states
        if destination.initial.get(ref) is None and destination.next.get(ref) is None
    }
    free_map_raw = payload.get("free_map", {})
    if not isinstance(free_map_raw, dict):
        raise CompositionError("free_map must be an object")
    free_map: dict[int, list[tuple[int, int]]] = {}
    for key, values in free_map_raw.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise CompositionError("free_map source endpoints must be canonical decimal node IDs")
        source_id = int(key)
        if source_id not in source.nodes:
            raise CompositionError("free_map references a missing source node")
        source_node_entry = source.nodes[source_id]
        if source_node_entry.op != "state" or source_id not in source_free:
            raise CompositionError("free_map keys must be free source states")
        if source_id in free_map:
            raise CompositionError("duplicate free_map source endpoint")
        if not isinstance(values, list) or len(values) != source_node_entry.width:
            raise CompositionError("free_map must provide exactly one destination bit per source bit")
        destination_bits: list[tuple[int, int]] = []
        for value in values:
            if not isinstance(value, str) or value.count(":") != 1:
                raise CompositionError("free_map entries must be 'node:bit' strings")
            raw_node, raw_bit = value.split(":")
            if (not raw_node.isdecimal() or not raw_bit.isdecimal()
                    or str(int(raw_node)) != raw_node or str(int(raw_bit)) != raw_bit):
                raise CompositionError("free_map entries must use canonical decimal node IDs and bit indices")
            destination_id, destination_bit = int(raw_node), int(raw_bit)
            if destination_id not in destination.nodes:
                raise CompositionError("free_map references a missing destination node")
            destination_node = destination.nodes[destination_id]
            if destination_node.op != "state" or destination_id not in destination_free:
                raise CompositionError("free_map destinations must be free destination states")
            if destination_bit >= destination_node.width:
                raise CompositionError("free_map destination bit is out of range")
            destination_bits.append((destination_id, destination_bit))
        free_map[source_id] = destination_bits
    # Forgotten source state must admit an extension of every mapped initial
    # state. Constant initializers ensure this without existential reasoning.
    # Otherwise an inconsistent, irrelevant source init could make L vacuous.
    for initial in source.initial.values():
        states_in_init, inputs_in_init = source.cone([initial])
        if states_in_init or inputs_in_init:
            raise CompositionError("relational source initialization is unsupported")
    mapping: dict[int, int] = {}
    for field, op in (("state_map", "state"), ("input_map", "input")):
        raw = payload[field]
        if not isinstance(raw, dict):
            raise CompositionError(f"{field} must be an object")
        for key, value in raw.items():
            if not isinstance(key, str) or not key.isdecimal() or not isinstance(value, str) or not value.isdecimal():
                raise CompositionError("mapping endpoints must be positive decimal node IDs")
            a, b = int(key), int(value)
            if a in mapping or str(a) != key or str(b) != value:
                raise CompositionError("duplicate or noncanonical mapping endpoint")
            if a not in source.nodes or b not in destination.nodes:
                raise CompositionError("mapping references a missing model node")
            sn, dn = source.nodes[a], destination.nodes[b]
            if sn.op != op or dn.op != op or sn.width != dn.width:
                raise CompositionError("mapping changes state/input kind or bit-vector width")
            mapping[a] = b
    if "free_map" in payload:
        overlap = set(free_map) & set(mapping)
        if overlap:
            raise CompositionError("a source free state cannot also have a whole-atom mapping")
        free_sources = set(mapping) & source_free
        if free_sources:
            raise CompositionError("free source states require bit-level free_map entries")
        if len(set(mapping.values())) != len(mapping):
            raise CompositionError("non-free source atoms must map one-to-one")
        occupied = set(mapping.values()) & destination_free
        if occupied:
            raise CompositionError("free destination states cannot also be whole-atom mapping targets")
    states, inputs = source.cone([source.properties[source_name], *source.constraints])
    if free_map:
        extra = set(free_map) - states
        if extra:
            raise CompositionError("free_map contains source free states outside the checked cone")
        missing = {
            atom for atom in (states | inputs)
            if atom not in mapping and atom not in free_map
        }
    else:
        missing = (states | inputs) - mapping.keys()
    if missing:
        raise CompositionError(f"mapping omits source cone atoms {sorted(missing)[:8]}")
    # The same source atom/bit must mean the same destination bit in initial,
    # transition, constraint and observation checks. Names play no role here.
    use_free_map = "free_map" in payload
    if use_free_map:
        def source_bit_atom(n: btor.Node, bit: int) -> str:
            if n.id in free_map:
                destination_id, destination_bit = free_map[n.id][bit]
                return f"destination:{destination_id}:{destination_bit}"
            if n.id not in mapping:
                return f"unmapped-source:{n.id}:{bit}"
            return f"destination:{mapping[n.id]}:{bit}"
        source_key = (
            source_node["model"],
            tuple(sorted(mapping.items())),
            tuple((ref, tuple(bits)) for ref, bits in sorted(free_map.items())),
            "bits",
        )
        destination_key = (node["model"], "identity-bits")
        if source_key not in store.normalized:
            store.normalized[source_key] = source.bits(bit_atom=source_bit_atom)
        if destination_key not in store.normalized:
            store.normalized[destination_key] = destination.bits(
                bit_atom=lambda n, bit: f"destination:{n.id}:{bit}"
            )
    else:
        def source_atom(n: btor.Node) -> str:
            if n.id not in mapping:
                return f"unmapped-source:{n.id}"
            return f"destination:{mapping[n.id]}"
        source_key = (source_node["model"], tuple(sorted(mapping.items())))
        destination_key = (node["model"], "identity")
        if source_key not in store.normalized:
            store.normalized[source_key] = source.bits(source_atom)
        if destination_key not in store.normalized:
            store.normalized[destination_key] = destination.bits(lambda n: f"destination:{n.id}")
    sbits, dbits = store.normalized[source_key], store.normalized[destination_key]
    for state in sorted(states):
        if state in source_free and state not in mapping:
            continue
        mapped = mapping.get(state)
        if mapped is None:
            raise CompositionError(f"source state {state} has no destination mapping")
        si, di = source.initial.get(state), destination.initial.get(mapped)
        if si is not None and (di is None or sbits[si] != dbits[di]):
            raise CompositionError(f"initial-state correspondence failed for state {state}")
        sn, dn = source.next.get(state), destination.next.get(mapped)
        # Be conservative about unspecified next-state semantics: presence
        # must match, rather than assuming the frontend's default convention.
        if (sn is None) != (dn is None) or sn is not None and sbits[sn] != dbits[dn]:
            raise CompositionError(f"transition correspondence failed for state {state}")
    constraints = {dbits[ref] for ref in destination.constraints}
    discharged = {}
    for ref in source.constraints:
        if sbits[ref] not in constraints or str(ref) in discharge:
            witness = discharge.get(str(ref))
            if witness is None:
                raise CompositionError("source proof has a constraint not established by the destination model")
            dep = nodes.get(witness["node"])
            if dep is None or dep["model"] != node["model"] or dep["id"] == node["id"]:
                raise CompositionError("a discharge witness must be proved on the original destination model")
            if dep["certificate"].get("payload", {}).get("method") == "step":
                raise CompositionError("a state constraint cannot be discharged by a transition-only theorem")
            matches = [g for g in dep["provides"] if g["name"] == witness["guarantee"]]
            if len(matches) != 1:
                raise CompositionError("ambiguous constraint discharge guarantee")
            try:
                fact = model_smt.binding_term(dep, matches[0], store)
                if 1 in fact.frames:
                    raise CompositionError("constraint discharge cannot assume future values")
                dctx = model_smt.context(store, node["model"])
                mapped = semantics.Context(source, source_node["model"],
                    atoms=lambda atom, frame: dctx.ref(mapping[atom.id], frame))
                discharged[str(ref)] = model_smt.prove([fact.value], mapped.ref(ref) == 1,
                                                     "constraint discharge", 5000)
            except (semantics.SemanticError, KeyError) as exc:
                raise CompositionError(str(exc)) from exc
    if set(discharge) != set(discharged):
        raise CompositionError("unused or non-source constraint discharge entries")
    if sbits[source.properties[source_name]] != dbits[destination.properties[destination_name]]:
        raise CompositionError("mapped source property does not match the destination property")
    return {
        "accepted": True,
        "kind": FORMAT,
        "source_model": source_node["model"],
        "destination_model": node["model"],
        "source_property": source_name,
        "destination_property": destination_name,
        "mapped_states": len(states),
        "mapped_inputs": len(inputs),
        "mapped_free_states": len(free_map),
        "mapped_free_bits": sum(len(bits) for bits in free_map.values()),
        "source_constraints": len(source.constraints),
        "discharged_constraints": discharged,
        "evidence": "CHECKED",
    }


def check_targets(case: dict, proof: dict, nodes: dict[str, dict], store: ModelStore) -> None:
    """Bind guarded roots to case-declared properties on the frozen primary model."""
    primary = proof["primary_model"]
    expected = case["build"].get("expected_model")
    if not expected or primary != f"{expected['kind']}:{expected['sha256']}":
        raise CompositionError("guarded composition requires the case's frozen expected_model")
    model = store.get(primary)
    meanings: dict[str, tuple[str, str]] = {}
    unbound: set[str] = set()
    for node in nodes.values():
        for guarantee in node["provides"]:
            if guarantee.get("binding"):
                binding = guarantee["binding"]
                if binding.get("kind") == "btor-expression":
                    model_smt.binding_term(node, guarantee, store)
                    name = "expression:" + btor.digest(binding["expression"])
                else:
                    _, name = bound_property(node, guarantee, store)
                atom = guarantee["expr"]
                meaning = (node["model"], name)
                if atom in meanings and meanings[atom] != meaning:
                    raise CompositionError("different model properties share an unqualified Boolean atom")
                meanings[atom] = meaning
            elif node["role"] != "compose":
                unbound.add(guarantee["expr"])
    if unbound & meanings.keys():
        raise CompositionError("an unbound guarantee aliases a model-bound property atom")
    case_targets = {target["id"]: target for target in case["targets"]}
    for target in proof["targets"]:
        required = case_targets[target["id"]].get("required_properties")
        if not required:
            raise CompositionError("guarded case targets must declare required_properties")
        if set(required) - model.properties.keys():
            raise CompositionError("a required case property is missing from the primary model")
        closure: set[str] = set()
        pending = [target["id"]]
        while pending:
            nid = pending.pop()
            if nid in closure:
                continue
            if nid not in nodes:
                raise CompositionError("missing node in target dependency closure")
            closure.add(nid)
            pending.extend(r["node"] for r in nodes[nid]["requires"])
        atoms: dict[str, str] = {}
        for nid in closure:
            node = nodes[nid]
            if node["model"] != primary:
                continue
            for guarantee in node["provides"]:
                binding = guarantee.get("binding") or {}
                if binding.get("kind") == "btor-bad":
                    atoms[binding["property"]] = guarantee["expr"]
        missing = set(required) - atoms.keys()
        if missing:
            raise CompositionError("required properties have no proved destination binding: " + ", ".join(sorted(missing)))
        root = nodes[target["id"]]
        guarantees = [g for g in root["provides"] if g["name"] == target["goal"]]
        if len(guarantees) != 1:
            raise CompositionError("ambiguous guarded root goal")
        goal = "(and " + " ".join(atoms[p] for p in required) + ")" if len(required) > 1 else atoms[required[0]]
        premise = guarantees[0]["expr"]
        script = expr.canonical_script([premise], goal)
        ok, detail = smt.check_implication([premise], goal, script)
        if not ok:
            raise CompositionError("root does not establish every required case property: " + detail)


def cone_mapping(source: btor.Model, destination: btor.Model, property_name: str) -> dict[int, int]:
    """Restrict a structural whole-atom proposal to the checked property cone.

    The proposal is still untrusted; ``check_projection`` recomputes the
    semantics.  Restricting the map keeps unrelated free states out of the
    transfer, which is required when the source and destination models carry
    different instrumentation.
    """
    if property_name not in source.properties:
        raise CompositionError(f"property {property_name!r} is not in the source model")
    source_free = {
        ref for ref in source.states
        if source.initial.get(ref) is None and source.next.get(ref) is None
    }
    states, inputs = source.cone([source.properties[property_name], *source.constraints])
    raw = btor.propose_mapping(source, destination)
    return {
        int(key): int(value)
        for key, value in raw.items()
        if int(key) in (states | inputs)
        and int(key) not in source_free
        and source.nodes[int(key)].op in {"state", "input"}
    }


def proposal(source_id: str, destination_id: str, source_node: str, guarantee: str,
             store: ModelStore) -> dict[str, Any]:
    """Build an untrusted mapping proposal; checking is a separate operation."""
    source, destination = store.get(source_id), store.get(destination_id)
    mapping = btor.propose_mapping(source, destination)
    return {
        "source": {"node": source_node, "guarantee": guarantee},
        "state_map": {k: v for k, v in mapping.items() if source.nodes[int(k)].op == "state"},
        "input_map": {k: v for k, v in mapping.items() if source.nodes[int(k)].op == "input"},
    }


def bit_proposal(source_node: dict, destination_node: dict, source_guarantee: dict,
                 destination_guarantee: dict, store: ModelStore,
                 mapping: dict[int, int] | None = None) -> dict[str, Any]:
    """Propose a bit-level projection payload.

    The result is untrusted until ``check_projection`` verifies it.  Free
    source atoms are removed from the whole-atom map and related bitwise to
    destination free states.  ``mapping`` may supply an already checked
    whole-atom mapping; otherwise the structural proposer is used.
    """
    source, source_name = bound_property(source_node, source_guarantee, store)
    destination, destination_name = bound_property(destination_node, destination_guarantee, store)
    source_property = source.properties[source_name]
    destination_property = destination.properties[destination_name]
    source_states, inputs = source.cone([source_property, *source.constraints])
    source_free = {
        ref for ref in source.states
        if source.initial.get(ref) is None and source.next.get(ref) is None
    }
    destination_free = {
        ref for ref in destination.states
        if destination.initial.get(ref) is None and destination.next.get(ref) is None
    }
    if mapping is None:
        raw = btor.propose_mapping(source, destination)
        mapping = {
            int(key): int(value)
            for key, value in raw.items()
            if source.nodes[int(key)].op in {"state", "input"} and int(key) not in source_free
        }
    else:
        mapping = {
            int(key): int(value)
            for key, value in mapping.items()
            if source.nodes[int(key)].op in {"state", "input"} and int(key) not in source_free
        }
    missing = (source_states | inputs) - set(mapping) - source_free
    if missing:
        raise CompositionError(f"bit proposal omits source atoms {sorted(missing)[:8]}")
    if len(set(mapping.values())) != len(mapping):
        raise CompositionError("bit proposal maps distinct source atoms to the same destination atom")
    occupied = set(mapping.values()) & destination_free
    if occupied:
        raise CompositionError("bit proposal maps a non-free source atom to a free destination state")
    free_map = bitproj.propose_free_map(
        source,
        destination,
        mapping,
        source_property=source_property,
        destination_property=destination_property,
        source_states=source_states,
    )
    return {
        "source": {
            "node": source_node["id"],
            "guarantee": source_guarantee["name"],
        },
        "state_map": {
            str(key): str(value)
            for key, value in mapping.items()
            if source.nodes[key].op == "state"
        },
        "input_map": {
            str(key): str(value)
            for key, value in mapping.items()
            if source.nodes[key].op == "input"
        },
        "free_map": {
            str(key): [f"{destination_id}:{bit}" for destination_id, bit in bits]
            for key, bits in sorted(free_map.items())
        },
    }
