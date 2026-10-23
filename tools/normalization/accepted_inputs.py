"""Read current accepted source facts; no historical receipts or scan I/O.

The compact source checkpoint and published inventory jointly bind each input.
Page-level or node-level false/null review literals are retained verbatim;
checkpoint acceptance is not a new visual review of individual fields.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

STATUS = 'notes/Source status.json'
CONTENT = 'notes/Content data manifest.json'
INVENTORY = 'notes/Repository records manifest.json'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class AcceptedInputError(ValueError):
    """An input is unsafe, unowned, inconsistent, incomplete or changed."""


def _need(ok, message):
    if not ok:
        raise AcceptedInputError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw, label):
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, 'Duplicate JSON property in ' + label + ': ' + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise AcceptedInputError('Nonfinite JSON number in ' + label + ': ' + value)
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptedInputError('Invalid UTF-8 JSON in ' + label) from exc


def _relative(relative):
    _need(isinstance(relative, str) and bool(relative), 'Missing repository-relative path')
    p = PurePosixPath(relative)
    _need('\\' not in relative and ':' not in relative and '\x00' not in relative
          and not p.is_absolute() and not PureWindowsPath(relative).is_absolute()
          and '..' not in p.parts and '.' not in p.parts and p.as_posix() == relative,
          'Unsafe repository path: ' + relative)
    return relative


def _inside(repo, relative):
    path = (repo / _relative(relative)).resolve()
    _need(path.is_relative_to(repo), 'Repository path escapes root: ' + relative)
    return path


def _records(items, label):
    _need(isinstance(items, list), label + ' is not a file list')
    result = {}; folded = set()
    for item in items:
        _need(isinstance(item, dict), label + ' entry is not an object')
        relative = _relative(item.get('path'))
        _need(relative.casefold() not in folded, 'Duplicate/case-aliased path in ' + label + ': ' + relative)
        _need(isinstance(item.get('sha256'), str) and SHA256.fullmatch(item['sha256']), 'Invalid file hash in ' + label + ': ' + relative)
        folded.add(relative.casefold()); result[relative] = item
    return result


class AcceptedInputs:
    def __init__(self, repo, bindings, documents, pages, unmodeled, guards):
        self.repo = repo
        self.globals_bindings = deepcopy(bindings)
        self.global_documents = documents
        self.pages = pages
        self.unmodeled_exports = unmodeled
        self._guards = tuple((relative, expected, resolved) for relative, (expected, resolved) in sorted(guards.items()))

    def recheck(self):
        for relative, expected, resolved in self._guards:
            path = _inside(self.repo, relative)
            _need(path == resolved, 'Input path resolution changed: ' + relative)
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise AcceptedInputError('Input missing/unreadable: ' + relative) from exc
            _need(_sha(raw) == expected, 'Input changed: ' + relative)
        return {'passed': True, 'files_checked': len(self._guards), 'models': len(self.pages)}


def load_accepted_inputs(repo, expected_count=None):
    """Load the checkpoint's exact published-model membership and rehash it."""
    _need(expected_count is None or (type(expected_count) is int and expected_count >= 0), 'Invalid expected page count')
    repo = Path(repo).resolve()
    _need(repo.is_dir(), 'Repository root is missing')
    guards = {}; globals_ = {}; documents = {}

    def checked(relative, expected=None):
        path = _inside(repo, relative)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AcceptedInputError('Input missing/unreadable: ' + relative) from exc
        actual = _sha(raw)
        if expected is not None:
            _need(actual == expected, 'Changed input: ' + relative)
        if relative in guards:
            _need(guards[relative] == (actual, path), 'Repeated input binding disagrees: ' + relative)
        guards[relative] = (actual, path)
        return raw, path, actual

    for relative in (INVENTORY, STATUS, CONTENT):
        raw, path, digest = checked(relative)
        doc = _json(raw, relative)
        _need(isinstance(doc, dict), 'Global manifest is not an object: ' + relative)
        documents[relative] = doc
        globals_[relative] = {'path': relative, 'sha256': digest}
    inventory = _records(documents[INVENTORY].get('files'), 'Repository records manifest')
    _need(documents[INVENTORY].get('schema') == 'ald-current-repository-inventory-v1', 'Unsupported repository inventory schema')

    def owned(relative, digest):
        _need(relative in inventory, 'Input not owned by repository inventory: ' + relative)
        _need(inventory[relative]['sha256'] == digest, 'Repository inventory hash disagrees: ' + relative)

    for relative in (STATUS, CONTENT):
        owned(relative, globals_[relative]['sha256'])
    status = documents[STATUS]
    _need(status.get('schema') == 'ald-current-source-checkpoint-v1', 'Unsupported source checkpoint schema')
    _need(isinstance(status.get('records'), list), 'Missing current source records')
    content = _records(documents[CONTENT].get('files'), 'Content data manifest')
    declared_models = {p: r['sha256'] for p, r in content.items() if r.get('role') == 'Published page content model'}
    selected = {}; pages = []; unmodeled = []; scan_ids = set(); all_paths = set()
    for record in status['records']:
        _need(isinstance(record, dict) and record.get('status') == 'reviewed', 'Source checkpoint record is not reviewed')
        scan = record.get('scan_reference')
        _need(isinstance(scan, dict) and type(scan.get('id')) in (str, int) and str(scan['id']) != '', 'Missing source scan ID')
        scan_id = str(scan['id'])
        _need(scan_id not in scan_ids, 'Duplicate source scan ID')
        scan_ids.add(scan_id)
        _relative(scan.get('relative_path'))
        _need(scan['relative_path'].lower().endswith(('.tif', '.tiff')), 'Source scan reference is not TIFF')
        refs = record.get('repository')
        _need(isinstance(refs, dict) and set(refs) <= {'txt', 'json', 'notes'} and {'txt', 'notes'} <= set(refs), 'Unsupported checkpoint repository bindings')
        loaded = {}
        for kind, ref in refs.items():
            item = _records([ref], 'Source checkpoint ' + kind)
            relative, binding = next(iter(item.items()))
            namespace, suffix = {'txt': ('ALD/', '.txt'), 'json': ('json/', '.json'), 'notes': ('notes/', '.txt')}[kind]
            _need(relative.startswith(namespace) and relative.endswith(suffix), 'Wrong checkpoint namespace: ' + relative)
            _need(relative.casefold() not in all_paths, 'Duplicate checkpoint file membership: ' + relative)
            all_paths.add(relative.casefold())
            owned(relative, binding['sha256'])
            raw, path, digest = checked(relative, binding['sha256'])
            loaded[kind] = (raw, path, digest)
        if 'json' not in refs:
            unmodeled.append(deepcopy(record)); continue
        model_rel = refs['json']['path']; text_rel = refs['txt']['path']
        _need(text_rel == 'ALD/' + model_rel[5:-5] + '.txt', 'Model/TXT paths do not correspond')
        _need(declared_models.get(model_rel) == refs['json']['sha256'], 'Published-model membership/hash differs: ' + model_rel)
        canonical_model = _json(loaded['json'][0], model_rel)
        _need(isinstance(canonical_model, dict), 'Published page model is not an object')
        from read_page import source_view
        model = source_view(canonical_model)
        selected[model_rel] = refs['json']['sha256']
        page_review = {'model_sha256': refs['json']['sha256'], 'text_sha256': refs['txt']['sha256'],
                       'exact_current_accepted': True, 'source_reviewed_present': 'source_reviewed' in model,
                       'provenance_binding': deepcopy(globals_[STATUS])}
        if 'source_reviewed' in model:
            page_review['source_reviewed'] = deepcopy(model['source_reviewed'])
        context = {'source_model': deepcopy(refs['json']), 'text': deepcopy(refs['txt']), 'accepted_page': page_review,
                   'page_id': deepcopy(record.get('page')), 'model_relative': model_rel, 'source_scan_id': scan_id}
        pages.append({'page_id': deepcopy(record.get('page')), 'model_relative': model_rel, 'text_relative': text_rel,
                      'model_path': loaded['json'][1], 'text_path': loaded['txt'][1],
                      'model_sha256': refs['json']['sha256'], 'text_sha256': refs['txt']['sha256'], 'model': model,
                      'current_document': canonical_model if canonical_model.get('schema')=='ibm360-ald-page-v3' else None,
                      'source_scan_id': scan_id, 'source_relative': scan['relative_path'],
                      'scan_reference': deepcopy(scan), 'context': context})
    _need(selected == declared_models, 'Exact current published-model membership differs')
    if expected_count is not None:
        _need(len(pages) == expected_count, 'Accepted source page count differs from required scope')
    pages.sort(key=lambda p: p['model_relative'])
    accepted = AcceptedInputs(repo, globals_, documents, pages, unmodeled, guards)
    accepted.recheck()
    return accepted
