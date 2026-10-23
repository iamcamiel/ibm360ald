"""Read current ALD models through one detached compatibility view.

Canonical page JSON uses v3. Legacy models remain supported for external
review stages and focused tests; no legacy copy is written to the repository.
"""
from copy import deepcopy
import json
from pathlib import Path

SCHEMA = "ibm360-ald-page-v3"
READ_SCHEMAS = (SCHEMA, "ibm360-ald-page-v2")
RUNTIME_FILES = ("read_page.py", "pages.py", "printed_literals.py", "identity.py", "terminals.py", "legacy_v2.py", "notation.py", "review.py", "check_format.py", "Canonical vocabulary.json", "ALD page schema.json", "Format release.json")

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result

def _constant(value):
    raise ValueError("Non-finite JSON constant: " + value)

def is_uniform(document):
    return isinstance(document, dict) and document.get("schema") in READ_SCHEMAS

def view(document):
    """Return a detached legacy consumer view; never mutate its input."""
    if not isinstance(document, dict):
        raise ValueError("Page model must be a JSON object")
    schema = document.get("schema")
    if schema in READ_SCHEMAS:
        from pages import restore_page
        result = restore_page(document)
        if not isinstance(result, dict):
            raise ValueError("Restored page model must be an object")
        return deepcopy(result)
    if isinstance(schema, str) and schema.startswith("ibm360-ald-page-"):
        raise ValueError("Unsupported ALD page schema: " + schema)
    return deepcopy(document)

source_view = view

def loads(raw, *, semantic=False):
    """Decode UTF-8 JSON with duplicate/type guards and dispatch its schema."""
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8-sig")
    if not isinstance(raw, str):
        raise TypeError("Expected JSON bytes or text")
    document = json.loads(raw.lstrip("\ufeff"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    return facts_view(document) if semantic else view(document)

def read(path, *, semantic=False):
    return loads(Path(path).read_bytes(), semantic=semantic)

def runtime_paths(root):
    return [Path(root) / "tools/normalization" / name for name in RUNTIME_FILES]


def facts_view(document):
    """Read canonical node facts without changing the lossless source view.

    Consumers of card facts must use the normalized semantic fields. The
    default view remains a literal reconstruction for source-review tools.
    """
    result = view(document)
    if not is_uniform(document):
        return result
    for obj in document['objects']:
        form = obj['source_form']
        if form['container'] != 'nodes' or form['value_type'] != 'object':
            continue
        node = result['nodes'][form['ordinal']]
        identity = obj['card_identity']
        if any(node.get(key) is True for key in ('symbol_only', 'annotation_only', 'annotation_block')):
            continue
        if identity['parse_status'] == 'conflict':
            raise ValueError('Conflicting normalized card identity')
        if identity['parse_status'] != 'resolved':
            continue
        if obj['circuit']['parse_status'] == 'conflict':
            raise ValueError('Conflicting normalized circuit identity')
        if identity['parse_status'] == 'resolved':
            node['card_type'] = identity['card_type']
            node['portion'] = identity['portion']
        for key, section, field in [('function', 'function', 'label'),
                                    ('unit', 'circuit', 'identifier'),
                                    ('location', 'site', 'label')]:
            if field in obj[section]:
                node[key] = deepcopy(obj[section][field])
        if obj['site'].get('grid_label') is not None:
            node['grid'] = deepcopy(obj['site']['grid_label'])
        if 'pins' not in node:
            pins = []
            for terminal in obj['terminals']:
                if terminal['occurrence_kind'] != 'primary':
                    continue
                pin = deepcopy(terminal['source_literals'])
                if not isinstance(pin, dict):
                    pin = {'pin': pin}
                pin.update(deepcopy(terminal.get('extensions', {})))
                pin.update(deepcopy(terminal['geometry']))
                side = terminal.get('side') or terminal.get('declared_container_role')
                if side is not None:
                    pin['side'] = side
                for decoration in terminal['border_decorations']:
                    if decoration.get('kind') == 'triangle':
                        pin['triangle'] = decoration.get('observed_value')
                pins.append(pin)
            node['pins'] = pins
    return result
