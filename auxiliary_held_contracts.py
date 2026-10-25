"""Closed auxiliary held-card contracts. No ALD source/checkpoint extensions."""
import json
import re
from pathlib import Path


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def array(item, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum}


TEXT = {"type": "string", "minLength": 1}
CARD = {"type": "string", "pattern": r"^[0-9]{4}$"}
FALSE = {"const": False}
DEFS = {}
RELATIVE = {"type": "string", "pattern": r"^(?![/.])(?!.*(?:^|/)\.\.?(?:/|$))(?!.*//)[^\\:]+(?<!/)$"}
DEFS["binding"] = obj({"path": RELATIVE, "sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"}})
DEFS["historical_file"] = obj({"published_path": RELATIVE, "artifact": ref("binding")})
HISTORICAL = {"generation": ref("binding"), "drawing": ref("binding"),
                           "audit": ref("binding"), "accepted_review": ref("binding"),
                           "files": array(ref("historical_file"), 1), "current_seal": FALSE}
DEFS["historical_not_recorded"] = obj({**HISTORICAL, "physical_review": {"const": None},
    "physical_review_status": {"const": "not-recorded"}})
DEFS["historical_recorded"] = obj({**HISTORICAL, "physical_review": ref("binding"),
    "physical_review_status": {"const": "recorded-historical-evidence"}})
DEFS["historical"] = {"oneOf": [ref("historical_not_recorded"), ref("historical_recorded")]}
DEFS["finding"] = obj({"kind": {"enum": ["builder_uncertainty", "builder_failure", "source_audit"]}, "detail": TEXT})
DEFS["audit"] = obj({"schema": {"const": "held-derived-card-audit-findings-v1"}, "card_type": CARD,
                     "builder_evidence": ref("binding"), "source_audit": ref("binding"),
                     "findings": array(ref("finding"), 1)})
DEFS["event"] = obj({"schema": {"const": "held-derived-card-source-event-v1"}, "event_id": TEXT,
                     "card_type": CARD, "source_bindings": array(ref("binding"), 1),
                     "evidence_bindings": array(ref("binding"), 1),
                     "source_publication_receipt": ref("binding"), "current_checkpoint": ref("binding"),
                     "audit_findings": ref("binding")})
DEFS["proposal"] = obj({"schema": {"const": "held-derived-card-source-proposal-v1"}, "proposal_id": TEXT,
                        "card_type": CARD, "proposed": {"const": True}, "published": FALSE, "approval": FALSE,
                        "source_plan": ref("binding"), "proposed_checkpoint": ref("binding"),
                        "source_bindings": array(ref("binding"), 1), "evidence_bindings": array(ref("binding"), 1),
                        "audit_findings": ref("binding")})
DEFS["generation"] = obj({"schema": {"const": "held-derived-card-generation-v2"}, "card_type": CARD,
                          "status": {"const": "held"}, "current": FALSE, "usable_as_current": FALSE,
                          "approval": FALSE, "visible_reason": TEXT, "source_event": ref("binding"),
                          "audit_findings": ref("binding"), "historical_accepted": ref("historical"),
                          "sequence": {"type": "integer", "minimum": 1},
                          "predecessor_held": {"oneOf": [ref("binding"), {"const": None}]}})
DEFS["current_entry"] = obj({"card_type": CARD, "status": {"const": "current"}, "generation": ref("binding")})
DEFS["held_entry"] = obj({"card_type": CARD, "status": {"const": "held"}, "generation": ref("binding")})
DEFS["legacy_definition"] = {"oneOf": [
    obj({"declared_binding": ref("binding"), "artifact": ref("binding"), "status": {"const": "recorded-historical-evidence"}}),
    obj({"declared_binding": ref("binding"), "artifact": {"const": None}, "status": {"const": "recorded-binding-artifact-unavailable"}})]}
LEGACY = {"generation": ref("binding"), "canonical": ref("binding"),
          "files": array(ref("historical_file"), 1), "definition_provenance": ref("legacy_definition"),
          "audit": {"const": None}, "audit_status": {"const": "not-recorded"},
          "accepted_review": {"const": None}, "accepted_review_status": {"const": "not-recorded"},
          "current_seal": FALSE}
legacy_branches = []
for evidence in (False, True):
    for physical in (False, True):
        name = "legacy_history_" + str(int(evidence)) + str(int(physical))
        DEFS[name] = obj({**LEGACY, "source_evidence": ref("binding") if evidence else {"const": None},
            "source_evidence_status": {"const": "embedded-generation-value" if evidence else "not-recorded"},
            "physical_review": ref("binding") if physical else {"const": None},
            "physical_review_status": {"const": "recorded-historical-evidence" if physical else "not-recorded"}})
        legacy_branches.append(ref(name))
DEFS["legacy_historical"] = {"oneOf": legacy_branches}
DEFS["legacy_entry"] = obj({"card_type": CARD, "status": {"const": "legacy-proof-only"},
                            "visible_reason": TEXT, "historical_legacy": ref("legacy_historical")})
DEFS["counts"] = obj({k: {"type": "integer", "minimum": 0}
                       for k in ["families", "current", "held", "legacy_proof_only"]})
DEFS["index"] = obj({"schema": {"const": "held-derived-card-index-v3"}, "authoritative": {"const": True},
                     "base_inventory": ref("binding"), "current_checkpoint": ref("binding"),
                     "predecessor_index": {"oneOf": [ref("binding"), {"const": None}]},
                     "entries": array({"oneOf": [ref("current_entry"), ref("held_entry"), ref("legacy_entry")]}),
                     "counts": ref("counts")})
DEFS["capture"] = obj({"schema": {"const": "held-derived-card-capture-v1"}, "index": ref("binding"),
                       "current_checkpoint": ref("binding"), "counts": ref("counts"),
                       "current_passed": array(CARD), "held_validated": array(CARD),
                       "legacy_proof_only_validated": array(CARD), "all_families_current": {"type": "boolean"}})
DEFS["namespace_record"] = obj({"card_type": CARD, "status": {"enum": ["current", "held", "legacy-proof-only"]},
                                "artifact": ref("binding")})
DEFS["capture"]["properties"].update({"usable_current_metadata": array(ref("binding")),
    "namespace_inventory": array(ref("namespace_record")),
    "usable_current_metadata_records": {"type": "integer", "minimum": 0}})
DEFS["capture"]["required"] = list(DEFS["capture"]["properties"])
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:ibm360:auxiliary:held-derived-card:v3",
          "title": "Closed auxiliary card contracts v3 with separate legacy proof history", "$defs": DEFS,
          "oneOf": [ref(x) for x in ["generation", "event", "proposal", "audit", "index", "capture"]]}


def _validate(value, rule, location):
    if "$ref" in rule:
        return _validate(value, DEFS[rule["$ref"].split("/")[-1]], location)
    if "oneOf" in rule:
        matches = 0
        for option in rule["oneOf"]:
            try:
                _validate(value, option, location)
                matches += 1
            except ValueError:
                pass
        if matches != 1:
            raise ValueError(location + ": must match exactly one closed versioned contract")
        return
    if "const" in rule and (type(value) is not type(rule["const"]) or value != rule["const"]):
        raise ValueError(location + ": invalid constant")
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError(location + ": unsupported value")
    kind = rule.get("type")
    if kind == "object":
        if not isinstance(value, dict) or set(value) - set(rule["properties"]) or set(rule["required"]) - set(value):
            raise ValueError(location + ": missing or unknown fields")
        for key, item in value.items():
            _validate(item, rule["properties"][key], location + "/" + key)
    elif kind == "array":
        if not isinstance(value, list) or len(value) < rule["minItems"]:
            raise ValueError(location + ": invalid array")
        for i, item in enumerate(value):
            _validate(item, rule["items"], location + "/" + str(i))
    elif kind == "string":
        if not isinstance(value, str) or not value.strip() or ("pattern" in rule and not re.fullmatch(rule["pattern"], value)):
            raise ValueError(location + ": invalid string")
    elif kind == "integer":
        if type(value) is not int or value < rule["minimum"]:
            raise ValueError(location + ": invalid integer")
    elif kind == "boolean" and type(value) is not bool:
        raise ValueError(location + ": invalid boolean")


def validate(value, contract=None):
    _validate(value, ref(contract) if contract else SCHEMA, "$")
    return value


def write_schema(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(SCHEMA, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    write_schema(Path(__file__).parent / "Contracts/held_derived_card.schema.json")
