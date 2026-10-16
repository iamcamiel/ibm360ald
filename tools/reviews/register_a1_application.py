"""Register an independently published A1 table delta; never publish sources.

Preflight is the default.  --register updates only the current-field adapter
and mandatory A1 registry, preserving their exact predecessors.  This helper
does not import the historical adapter-building script or replay old releases.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

REGISTRY_SCHEMA = 'a1-table-current-application-registry-v1'
STAGE_SCHEMA = 'socket-table-literal-correction-private-stage-v1'
PUBLICATION_SCHEMA = 'socket-table-literal-correction-publication-v1'
ARTIFACT_SCHEMA = 'reviewed-existing-A1-table-and-auxiliary-data-v1'


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path.read_bytes())}
def file_bind(path): return {'file': str(Path(path).resolve()), 'sha256': sha(Path(path).read_bytes())}


def checked(link):
    path = Path(link.get('path', link.get('file', ''))).resolve()
    require(path.is_file() and sha(path.read_bytes()) == link.get('sha256'), 'Stale binding: ' + str(path))
    return path


def target_of(item):
    return str(Path(item.get('current_quartet', {}).get('txt', {}).get('path', '')).resolve())


def verify_chain(stage_path, publication_path, acceptance_path, *, live):
    stage_path, publication_path, acceptance_path = map(lambda p: Path(p).resolve(),
                                                       (stage_path, publication_path, acceptance_path))
    stage, pub, acceptance = map(read, (stage_path, publication_path, acceptance_path))
    require(stage.get('schema') == STAGE_SCHEMA and stage.get('artifact_schema') == ARTIFACT_SCHEMA, 'Unsupported A1 table stage')
    require(pub.get('schema') == PUBLICATION_SCHEMA and pub.get('passed') is True and not pub.get('failures'), 'Publication did not pass')
    require(checked(pub['manifest']) == stage_path, 'Publication binds another stage')
    require(checked(pub['independent_acceptance']) == acceptance_path, 'Publication binds another independent acceptance')
    require(acceptance.get('schema') == 'socket-table-literal-correction-independent-acceptance-v1'
            and acceptance.get('independent_review') is True
            and acceptance.get('passed') is True and not acceptance.get('failures'), 'Independent acceptance did not pass')
    require(acceptance.get('manifest_sha256') == sha(stage_path.read_bytes()), 'Independent acceptance binds another stage')
    require(pub.get('source') == stage.get('source'), 'Publication source differs')
    checked(stage['source'])
    for name in ['human_authority', 'source_crop', 'predecessor_acceptance', 'historical_repository_acceptance']:
        checked(stage[name])
    targets = {}
    for record in stage['files']:
        target = Path(record['target']).resolve()
        require(str(target) not in targets, 'Duplicate staged target')
        candidate = checked(record['candidate'])
        if record.get('before'): checked(record['before'])
        if live: require(target.is_file() and target.read_bytes() == candidate.read_bytes(), 'Publication target differs: ' + str(target))
        targets[str(target)] = record['candidate']['sha256']
    published = {}
    for link in pub['published_targets']:
        target = str(Path(link.get('path', link.get('target', ''))).resolve())
        require(target not in published, 'Duplicate published target')
        published[target] = link['sha256']
    require(published == targets, 'Publication target inventory differs from stage')
    # Independently retain exact text-cell authority, including line endings.
    working = [r for r in stage['files'] if r['role'] == 'working accepted TXT']
    require(len(working) == 1, 'Exactly one working TXT is required')
    record = working[0]
    old = checked(record['before']).read_bytes(); new = checked(record['candidate']).read_bytes()
    old_rows, new_rows = old.decode('utf-8-sig').splitlines(keepends=True), new.decode('utf-8-sig').splitlines(keepends=True)
    require(len(old_rows) == len(new_rows) and old.startswith(b'\xef\xbb\xbf') == new.startswith(b'\xef\xbb\xbf'), 'TXT format changed')
    actual = []
    for row, (a, b) in enumerate(zip(old_rows, new_rows)):
        require(len(a) == len(b) and a[len(a.rstrip('\r\n')):] == b[len(b.rstrip('\r\n')):], 'TXT row length or line ending changed')
        actual.extend({'row': row, 'column': col, 'before': x, 'after': y}
                      for col, (x, y) in enumerate(zip(a, b)) if x != y)
    require(actual == stage['exact_meaningful_cell_changes'], 'TXT delta differs from declared human correction')
    require(not stage.get('trailing_space_padding'), 'This registration supports no geometry padding')
    return stage, pub


def prepare(stage_path, publication_path, acceptance_path, adapter_path, registry_path,
            workspace, exports, source_root):
    workspace, exports, source_root = map(lambda p: Path(p).resolve(), (workspace, exports, source_root))
    adapter_path, registry_path = map(lambda p: Path(p).resolve(), (adapter_path, registry_path))
    for path in [stage_path, publication_path, acceptance_path, adapter_path, registry_path]:
        require(Path(path).resolve().is_relative_to(workspace), 'Proof or registry outside workspace')
    stage, _ = verify_chain(stage_path, publication_path, acceptance_path, live=True)
    require(checked(stage['source']).is_relative_to(source_root), 'Original source outside source root')
    working = next(r for r in stage['files'] if r['role'] == 'working accepted TXT')
    text = Path(working['target']).resolve()
    require(text.is_relative_to(exports) and text.parent.name == 'A1 Socket Listing', 'Not an A1 export TXT')
    require(text.name.split(' ', 1)[0] == stage['page'] and text.suffix == '.txt', 'Target/page mismatch')
    require(not text.with_suffix('.json').exists(), 'A1 no-page-JSON schema does not fit this target')
    required = {'txt': text, 'notes': text.with_name(text.stem + ' review notes.txt'),
                'preview': text.with_name(text.stem + ' preview.png')}
    by_target = {str(Path(r['target']).resolve()): r for r in stage['files']}
    require(all(str(path) in by_target for path in required.values()), 'Missing actual notes or preview companion')
    quartet = {kind: bind(path) for kind, path in required.items()}
    # Shared board/reference collections may acquire independently reviewed
    # successors for other pages. Their original mutations remain bound by the
    # immutable stage/publication, but are not this page's permanent live proof.
    columns = [r for r in stage['files'] if r['role'] == 'successor columns proof']
    require(len(columns) == 1, 'Exactly one page-specific successor columns proof is required')
    columns_path = Path(columns[0]['target']).resolve()
    predecessor_path = checked(stage['predecessor_acceptance'])
    require(all(path.is_relative_to(workspace/'tmp/ald-text/a1') for path in [columns_path, predecessor_path]),
            'Page-specific columns proofs must be inside the A1 review directory')
    auxiliary = [bind(columns_path), bind(predecessor_path)]
    item = {'page': stage['page'], 'eligible': True, 'artifact_schema': ARTIFACT_SCHEMA,
            'checks': dict(original_source_hash_current=True, independent_field_review_passed=True,
                           guarded_publication_passed=True, current_artifact_hashes_bound=True,
                           historical_full_source_acceptance_retained=True, uncertain_fields_not_applied=True),
            'source': stage['source'], 'current_quartet': quartet,
            'current_auxiliary_existing_data': auxiliary,
            'owner_receipt': file_bind(publication_path), 'independent_audit': file_bind(acceptance_path),
            'human_authority': file_bind(checked(stage['human_authority'])),
            'predecessor_acceptance': file_bind(checked(stage['predecessor_acceptance'])),
            'changed_cells': stage['exact_meaningful_cell_changes'],
            'historical_acceptance_note': 'Original columns-reviewed array and repository acceptance receipt remain unchanged historical evidence; successor columns are separate current proof.'}
    adapter = read(adapter_path)
    require(adapter.get('passed') is True and isinstance(adapter.get('pages'), list), 'Invalid existing current-field adapter')
    updated = deepcopy(adapter)
    matches = [i for i, existing in enumerate(updated['pages']) if target_of(existing) == str(text)]
    require(len(matches) <= 1, 'Duplicate adapter target')
    if matches: updated['pages'][matches[0]] = item
    else: updated['pages'].append(item)
    # Other records are copied without modification; no old receipt is replayed.
    require([x for x in adapter['pages'] if target_of(x) != str(text)] ==
            [x for x in updated['pages'] if target_of(x) != str(text)], 'Unrelated adapter items changed')
    registry = read(registry_path) if registry_path.exists() else {'schema': REGISTRY_SCHEMA, 'entries': []}
    require(registry.get('schema') == REGISTRY_SCHEMA and isinstance(registry.get('entries'), list), 'Invalid mandatory registry')
    entry = {'page': stage['page'], 'target': str(text), 'adapter_path': str(adapter_path),
             'application_item_sha256': sha(canonical(item)), 'stage': bind(stage_path),
             'publication': bind(publication_path), 'independent_acceptance': bind(acceptance_path)}
    registry = deepcopy(registry)
    matches = [i for i, old in enumerate(registry['entries']) if old.get('target') == str(text)]
    require(len(matches) <= 1, 'Duplicate registered target')
    if matches: registry['entries'][matches[0]] = entry
    else: registry['entries'].append(entry)
    return updated, registry, item


def validate_registered_applications(registry_path, adapter_path, workspace, exports, source_root, *, adapter=None, registry=None):
    """Mandatory exporter guard: missing/stale registry or proof raises.

    Call before scanning legacy proofs.  Every registered target must have its
    exact accepted adapter item and live TXT/notes/preview.  It cannot fall back
    to a historical columns file if any new proof is absent or changed.
    """
    registry_path, adapter_path = Path(registry_path).resolve(), Path(adapter_path).resolve()
    for path in [registry_path, adapter_path]:
        require(path.is_relative_to(Path(workspace).resolve()), 'Registry/adapter outside workspace')
    require(registry_path.is_file() or registry is not None, 'Mandatory A1 application registry is missing')
    registry = read(registry_path) if registry is None else registry
    adapter = read(adapter_path) if adapter is None else adapter
    require(registry.get('schema') == REGISTRY_SCHEMA and isinstance(registry.get('entries'), list), 'Invalid A1 registry')
    require(adapter.get('passed') is True, 'Current-field adapter did not pass')
    seen = set()
    for entry in registry['entries']:
        target = Path(entry['target']).resolve()
        require(str(target) not in seen and target.is_relative_to(Path(exports).resolve()), 'Duplicate/outside registered target')
        seen.add(str(target))
        require(Path(entry['adapter_path']).resolve() == adapter_path, 'Registry adapter path differs')
        matches = [item for item in adapter['pages'] if target_of(item) == str(target)]
        require(len(matches) == 1 and sha(canonical(matches[0])) == entry['application_item_sha256'], 'Registered adapter item missing or changed')
        stage_path, pub_path, peer_path = (checked(entry[key]) for key in ['stage', 'publication', 'independent_acceptance'])
        require(all(path.is_relative_to(Path(workspace).resolve()) for path in [stage_path, pub_path, peer_path]), 'Registered proof outside workspace')
        stage, _ = verify_chain(stage_path, pub_path, peer_path, live=False)
        require(stage['page'] == entry['page'] and checked(stage['source']).is_relative_to(Path(source_root).resolve()), 'Registered source identity differs')
        working = [r for r in stage['files'] if r['role'] == 'working accepted TXT']
        require(len(working) == 1 and Path(working[0]['target']).resolve() == target, 'Registered stage targets another TXT')
        item = matches[0]
        require(item.get('page') == stage['page'] and item.get('source') == stage['source'] and item.get('artifact_schema') == ARTIFACT_SCHEMA,
                'Registered adapter source/schema differs from stage')
        expected = {'txt': target, 'notes': target.with_name(target.stem+' review notes.txt'),
                    'preview': target.with_name(target.stem+' preview.png')}
        require(set(item['current_quartet']) == set(expected), 'Registered artifact inventory differs')
        staged = {str(Path(r['target']).resolve()): r['candidate']['sha256'] for r in stage['files']}
        for kind, link in item['current_quartet'].items():
            require(checked(link) == expected[kind] and link['sha256'] == staged.get(str(expected[kind])), 'Registered artifact differs from accepted stage')
    return {'passed': True, 'registered_targets': sorted(seen)}


def atomic(path, raw):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            name = stream.name; stream.write(raw)
        os.replace(name, path); name = None
    finally:
        if name is not None: Path(name).unlink(missing_ok=True)


def register(stage, publication, acceptance, adapter, registry, workspace, exports, source_root, *, apply=False):
    updated, registered, item = prepare(stage, publication, acceptance, adapter, registry, workspace, exports, source_root)
    validate_registered_applications(registry, adapter, workspace, exports, source_root, adapter=updated, registry=registered)
    paths = [Path(adapter).resolve(), Path(registry).resolve()]
    old = {p: p.read_bytes() if p.exists() else None for p in paths}
    result = {'passed': True, 'registered': False, 'page': item['page'], 'target': target_of(item),
              'adapter_candidate_sha256': sha(encode(updated)), 'registry_candidate_sha256': sha(encode(registered)),
              'source_files_written': 0, 'other_adapter_items_unchanged': True}
    if not apply: return result
    for path, raw in old.items():
        if raw is None: continue
        saved = path.parent/(path.name+'.history')/(sha(raw)+'.json')
        if saved.exists(): require(saved.read_bytes() == raw, 'Adapter/registry history changed')
        else: atomic(saved, raw)
    try:
        for path in paths:
            require((path.read_bytes() if path.exists() else None) == old[path], 'Concurrent adapter/registry change')
        atomic(paths[0], encode(updated)); atomic(paths[1], encode(registered))
        validate_registered_applications(registry, adapter, workspace, exports, source_root)
    except BaseException:
        for path, raw in old.items():
            if raw is None: path.unlink(missing_ok=True)
            else: atomic(path, raw)
        raise
    return {**result, 'registered': True, 'adapter': bind(adapter), 'registry': bind(registry)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['stage','publication','acceptance','adapter','registry','workspace','exports','source-root']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--register', action='store_true')
    args = parser.parse_args()
    print(json.dumps(register(args.stage,args.publication,args.acceptance,args.adapter,args.registry,
                             args.workspace,args.exports,args.source_root,apply=args.register),ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
