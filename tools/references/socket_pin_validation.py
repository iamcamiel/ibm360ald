"""Read-only physical-pin validation for accepted ALD node dictionaries.

``audit_node_pins(node, kinds, definition=None)`` returns one result per source
pin object.  It never edits the node.  ``kinds`` is a resolved SINGLE/DOUBLE
listing kind, or a card-type mapping; no card-number heuristic implies SLT.
Range checks, source-mirror agreement and reviewed-portion coverage are separate
checks in each result's ``issues``.  A readable contact is selected only when
all readable physical mirrors agree, including invalid-looking readings.
"""
from __future__ import annotations

from collections.abc import Mapping
import re


LITERAL_FIELDS = (
    "pin", "physical_pin", "physical_pin_candidate", "printed_pin",
    "printed_label", "printed_pin_label", "physical_pin_label", "terminal_pin",
    "printed_combined_label",
)
QUALIFIER_FIELDS = (
    "printed_numeric_suffix", "printed_control_prefix", "numeric_control_prefix",
    "printed_qualifier", "printed_prefix", "printed_suffix", "printed_annotation",
    "printed_control_suffix", "control_prefix", "control_suffix", "qualifier",
)
SUPPLY = {"D08": "GROUND", "D03": "+3V", "B06": "-3V", "B11": "+6V",
          "J08": "GROUND", "J03": "+3V", "G06": "-3V", "G11": "+6V"}
CONTACT = re.compile(r"(?P<prefix>[0-9LT ]*)(?P<letter>[A-Z])(?P<number>[0-9]{2})(?P<suffix>[LT✲* ]*)\Z")
CONTROL = re.compile(r"(?:[0-9]+|[LTEKX]|(?:IN|OUT|INPUT|OUTPUT)[0-9]*|UNLABELLED|UNLABELED)\Z")
UNKNOWN = re.compile(r"[�?]")
SEVERITY = {"info": 0, "review": 1, "error": 2}


def _kind(value):
    if isinstance(value, str):
        literal = value.upper().replace("_", " ").strip()
        if literal in ("SINGLE", "SINGLE CARD"):
            return "single"
        if literal in ("DOUBLE", "DOUBLE CARD"):
            return "double"
    if isinstance(value, (list, tuple, set, frozenset)):
        resolved = {_kind(item) for item in value}
        return next(iter(resolved)) if len(resolved) == 1 else None
    return None


def parse_pin_literal(value, pin=None):
    """Return contact/control/pinless/unreadable/other without losing literal.

    The letter and number are deliberately unrestricted during parsing, so a
    damaged U12 or D14 survives to the range checker.  A trailing numeric
    qualifier is stripped only with explicit source metadata (B122 -> B12).
    """
    if value is None or str(value).strip() == "":
        return {"kind": "pinless", "contact": None}
    text = str(value).strip().upper()
    if UNKNOWN.search(text):
        return {"kind": "unreadable", "contact": None}
    if CONTROL.fullmatch(text):
        return {"kind": "control", "contact": None}
    suffix = (pin or {}).get("printed_numeric_suffix")
    removed = None
    if suffix is not None and str(suffix).isdigit() and text.endswith(str(suffix)):
        candidate = text[:-len(str(suffix))]
        if CONTACT.fullmatch(candidate):
            text, removed = candidate, str(suffix)
    match = CONTACT.fullmatch(text)
    if not match:
        return {"kind": "other", "contact": None}
    return {"kind": "contact", "contact": match["letter"] + match["number"],
            "prefix": match["prefix"], "suffix": match["suffix"],
            "explicit_numeric_suffix": removed}


def _primary(node):
    words = str(node.get("function") or "").strip().lstrip("✲*").split()
    return words[0] if words else ""


def audit_node_pins(node, kinds, definition=None):
    """Validate source pins and optionally a reviewed common-card definition.

    ``severity`` is info/review/error.  Missing kind or definition means the
    relevant check was not performed; it never means a contact passed it.
    Omitted unused ports, pinless connections, supply ties and repeat contact
    stubs are legal.  Only literal facts are checked; no pin is guessed.
    """
    kind_value = kinds.get(str(node.get("card_type")), None) if isinstance(kinds, Mapping) else kinds
    kind = _kind(kind_value)
    definition_matches = not definition or str(definition.get("card_type")) == str(node.get("card_type"))
    boxes = {str(box.get("portion")): box for box in (definition or {}).get("boxes", [])}
    box = boxes.get(str(node.get("portion")))
    power = dict(SUPPLY) if kind else {}
    if kind == "single":
        power = {key: value for key, value in power.items() if key[0] in "BD"}
    if definition and definition_matches:
        power.update(definition.get("power_contacts", {}))
    prepared = []
    for index, pin in enumerate(node.get("pins", [])):
        if not isinstance(pin, Mapping):
            prepared.append((pin, {}, {}, set()))
            continue
        literals = {field: pin[field] for field in LITERAL_FIELDS if field in pin}
        readings = {field: parse_pin_literal(value, pin) for field, value in literals.items()}
        contacts = {item["contact"] for item in readings.values() if item["kind"] == "contact"}
        prepared.append((pin, literals, readings, contacts))
    observed = {(pin.get("side"), next(iter(contacts)))
                for pin, _, _, contacts in prepared if isinstance(pin, Mapping) and len(contacts) == 1}
    seen = set()
    results = []
    for index, (pin, literals, readings, contacts) in enumerate(prepared):
        issues = []
        def add(status, severity, message, **detail):
            issues.append(dict(status=status, severity=severity, message=message, **detail))
        if not isinstance(pin, Mapping):
            results.append(dict(pin_index=index, side=None, status="malformed_pin_object", severity="review",
                                literals={"value": pin}, physical_contact=None, expected=None,
                                issues=[dict(status="malformed_pin_object", severity="review")]))
            continue
        contact = next(iter(contacts)) if len(contacts) == 1 else None
        side = pin.get("side")
        result = dict(pin_index=index, side=side, status="valid", severity="info",
                      literals=literals, physical_contact=contact, expected=None,
                      card_kind=kind, normalized_readings=readings,
                      qualifiers={field: pin[field] for field in QUALIFIER_FIELDS if field in pin}, issues=issues)
        if not definition_matches:
            add("definition_card_mismatch", "review", "Supplied definition describes a different card type; no common-pin check performed.")
        if len(contacts) > 1:
            add("mirror_conflict", "review", "Readable physical/printed mirrors disagree; no contact selected.",
                contacts=sorted(contacts))
        if any(item["kind"] == "unreadable" for item in readings.values()):
            add("unreadable_pin", "review", "A source pin field contains unreadable characters.")
        # Descriptive printed_label/combined_label may hold prose, rather than a
        # terminal.  Strict pin fields retain malformed values as review items.
        malformed = [field for field, item in readings.items() if item["kind"] == "other"
                     and field not in ("printed_label", "printed_combined_label")]
        if malformed:
            add("malformed_pin", "review", "Pin field is neither a physical contact nor a supported control/alias.", fields=malformed)
        if contact:
            if kind is None:
                add("unknown_kind", "info", "Single/double SLT kind is unresolved; physical range was not checked.")
            else:
                letter, number = contact[0], int(contact[1:])
                if letter not in ("BD" if kind == "single" else "BDGJ"):
                    add("invalid_letter", "error", "Contact letter is outside the known SLT module's pin banks.",
                        expected="BD" if kind == "single" else "BDGJ")
                if not 2 <= number <= 13:
                    add("invalid_number", "error", "Contact number is outside 02 through 13.", expected="02..13")
            if contact in power:
                add("supply_contact", "info", "Supply contact is range-valid and separate from common signal-pin coverage.", voltage=power[contact])
                result["expected"] = {"voltage": power[contact]}
            elif definition and definition_matches:
                if box is None:
                    add("definition_portion_unknown", "review", "Portion is absent from the reviewed definition.")
                elif side not in ("input", "output"):
                    add("direction_unknown", "review", "Physical contact has no input/output role usable for common-pin matching.")
                else:
                    expected = {(p.get("side"), p.get("pin")) for p in box.get("ports", []) if p.get("pin")}
                    result["expected"] = sorted(f"{s}:{p}" for s, p in expected)
                    if (side, contact) in expected:
                        add("definition_match", "info", "Contact and side occur on this reviewed portion.")
                    else:
                        other = "input" if side == "output" else "output"
                        if _primary(node) == "AR" and (other, contact) in expected and (other, contact) in observed:
                            add("shared_contact_passthrough", "info", "AR repeats the same physical input/output contact; redundant stub is allowed.")
                        else:
                            add("definition_discrepancy", "review", "Contact or direction is absent from this reviewed portion.")
            elif kind:
                add("valid", "info", "Physical contact is in the known SLT pin range; no reviewed portion check supplied.")
            key = (side, contact, bool(pin.get("triangle")) or pin.get("border_marker") == "◺")
            if key in seen:
                add("repeated_same_contact", "info", "Repeated identical contact/polarity is one physical pin, not an extra input.")
            seen.add(key)
        elif not issues:
            if any(item["kind"] == "control" for item in readings.values()):
                add("control", "info", "Control/alias notation has no physical pin contact to range-check.")
            else:
                add("pinless", "info", "Unlabeled internal connection is allowed.")
        if issues:
            # Preserve the first issue at the highest severity; secondary
            # checks remain present even when a source mirror blocks matching.
            primary = max(issues, key=lambda issue: SEVERITY[issue["severity"]])
            result["status"], result["severity"] = primary["status"], primary["severity"]
        results.append(result)
    return results
