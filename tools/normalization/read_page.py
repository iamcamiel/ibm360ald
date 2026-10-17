"""Read current ALD models through one detached compatibility view.

Canonical page JSON uses v2. Legacy models remain supported for external
review stages and focused tests; no legacy copy is written to the repository.
"""
from copy import deepcopy
import json
from pathlib import Path

SCHEMA = "ibm360-ald-page-v2"
RUNTIME_FILES = ("read_page.py", "pages.py", "identity.py", "terminals.py")

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
    return isinstance(document, dict) and document.get("schema") == SCHEMA

def view(document):
    """Return a detached legacy consumer view; never mutate its input."""
    if not isinstance(document, dict):
        raise ValueError("Page model must be a JSON object")
    schema = document.get("schema")
    if schema == SCHEMA:
        from pages import restore_page
        result = restore_page(document)
        if not isinstance(result, dict):
            raise ValueError("Restored page model must be an object")
        return deepcopy(result)
    if isinstance(schema, str) and schema.startswith("ibm360-ald-page-"):
        raise ValueError("Unsupported ALD page schema: " + schema)
    return deepcopy(document)

source_view = view

def loads(raw):
    """Decode UTF-8 JSON with duplicate/type guards and dispatch its schema."""
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8-sig")
    if not isinstance(raw, str):
        raise TypeError("Expected JSON bytes or text")
    return view(json.loads(raw.lstrip("\ufeff"), object_pairs_hook=_pairs,
                           parse_constant=_constant))

def read(path):
    return loads(Path(path).read_bytes())

def runtime_paths(root):
    return [Path(root) / "tools/normalization" / name for name in RUNTIME_FILES]
