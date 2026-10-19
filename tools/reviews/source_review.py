"""Durable answers and declarative, independently accepted source corrections.

No OCR, inference, acceptance generation, repository export or scan writes.
Only explicit same-width text edits and JSON pointer patches are supported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

from source_review_guards import validate_pin_edits

sys.dont_write_bytecode = True
KINDS = {'txt', 'json', 'notes', 'preview'}
INTENT = 'source-review-intent-v1'
STAGE = 'source-review-stage-v1'
LEGACY = 'native-card-review-private-stage-v1'
LEDGER = 'source-review-answer-ledger-v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def resolve(path, base):
    path = Path(path)
    require(path.is_absolute() or not path.drive, 'Drive-relative paths are unsupported')
    return (path if path.is_absolute() else Path(base) / path).resolve()


def checked(link, base):
    require(isinstance(link, dict) and isinstance(link.get('sha256'), str), 'Missing file binding')
    path = resolve(link.get('path', link.get('file', '')), base)
    raw = path.read_bytes()
    require(digest(raw) == link['sha256'], 'Stale file binding: ' + str(path))
    return path, raw


def atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    require(path.read_bytes() == raw, 'Atomic write verification failed: ' + str(path))


@contextmanager
def locked(path):
    """OS locks are released on process exit/reboot; no stale sentinel lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        deadline = time.monotonic() + 10
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ValueError('Another process is updating this review; retry without discarding your response') from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def event_hash(event):
    body = {k: v for k, v in event.items() if k != 'sha256'}
    return digest(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def json_equal(first, second):
    return json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(',', ':')) == json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def json_delta_paths(first, second, pointer=''):
    if json_equal(first, second):
        return []
    if isinstance(first, dict) and isinstance(second, dict):
        result = []
        for key in sorted(set(first) | set(second)):
            child = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
            result.extend(json_delta_paths(first[key], second[key], child) if key in first and key in second else [child])
        return result
    if isinstance(first, list) and isinstance(second, list) and len(first) == len(second):
        return [path for index, (a, b) in enumerate(zip(first, second)) for path in json_delta_paths(a, b, pointer + '/' + str(index))]
    return [pointer]


def verify_ledger(document):
    require(document.get('schema') == LEDGER, 'Unsupported answer ledger schema')
    questions, responses = {}, {}
    previous = '0' * 64
    for revision, event in enumerate(document.get('events', []), 1):
        require(event.get('revision') == revision and event.get('previous_sha256') == previous,
                'Broken answer ledger revision/hash chain')
        require(event.get('sha256') == event_hash(event), 'Changed answer ledger event')
        if event.get('kind') == 'question':
            question = event['question']
            key = question['question_id']
            require(key not in questions and isinstance(question.get('text'), str) and 'latest_response_id' not in question, 'Duplicate/invalid question')
            questions[key] = deepcopy(question)
        elif event.get('kind') == 'answer':
            key = event['question_id']
            require(key in questions and isinstance(event.get('raw'), str) and isinstance(event.get('normalized'), str),
                    'Answer has no question or lost literal text')
            require(event['response_id'] not in responses, 'Duplicate response ID')
            responses[event['response_id']] = event
            questions[key]['latest_response_id'] = event['response_id']
        else:
            raise ValueError('Unsupported ledger event')
        previous = event['sha256']
    require(document.get('revision') == len(document.get('events', [])), 'Wrong ledger revision')
    require(document.get('head_sha256') == previous and document.get('questions') == questions,
            'Ledger current view differs from its immutable events')
    return {'passed': True, 'revision': document['revision'], 'questions': len(questions),
            'answered': sum('latest_response_id' in q for q in questions.values()), 'responses': len(responses)}


def ledger_init(path, review_id):
    path = Path(path).resolve()
    with locked(path.with_name(path.name + '.lock')):
        require(not path.exists(), 'Ledger already exists; refusing replacement')
        document = {'schema': LEDGER, 'review_id': review_id, 'created_utc': now(),
                    'revision': 0, 'head_sha256': '0' * 64, 'questions': {}, 'events': []}
        atomic_write(path, encode(document))
    return verify_ledger(document)


def ledger_record(path, question=None, question_id=None, raw=None, normalized=None,
                  response_id=None, normalization_note='', expected_revision=None):
    path = Path(path).resolve()
    with locked(path.with_name(path.name + '.lock')):
        original = path.read_bytes()
        document = json.loads(original.decode('utf-8-sig'))
        verify_ledger(document)
        if question is not None:
            require(isinstance(question.get('question_id'), str) and question['question_id'], 'Missing question ID')
            require(isinstance(question.get('text'), str) and question['text'], 'Missing question text')
            require('latest_response_id' not in question, 'Question cannot inject an answer pointer')
            for link in question.get('evidence', []):
                checked(link, path.parent)
            key = question['question_id']
            if key in document['questions']:
                old = {k: v for k, v in document['questions'][key].items() if k != 'latest_response_id'}
                require(json_equal(old, question), 'Question ID already has different text/context')
                return verify_ledger(document)
            event = {'kind': 'question', 'question': deepcopy(question)}
        else:
            require(question_id in document['questions'], 'Question must be recorded before its answer')
            require(isinstance(raw, str), 'Raw response must be literal text')
            normalized = raw if normalized is None else normalized
            require(isinstance(normalized, str), 'Normalized response must be text')
            response_id = response_id or str(uuid.uuid4())
            event = {'kind': 'answer', 'question_id': question_id, 'raw': raw, 'normalized': normalized,
                     'response_id': response_id, 'normalization_note': normalization_note}
            previous = next((x for x in document['events'] if x.get('response_id') == response_id), None)
            if previous is not None:
                require(all(previous.get(k) == v for k, v in event.items()), 'Retry ID already records a different response')
                return verify_ledger(document)
        if expected_revision is not None:
            require(document['revision'] == expected_revision, 'Ledger changed; retry against the current revision')
        history = path.parent / (path.name + '.history') / f"{document['revision']:06d}-{digest(original)}.json"
        if history.exists():
            require(history.read_bytes() == original, 'Prior ledger history was changed')
        else:
            atomic_write(history, original)
        event.update(revision=document['revision'] + 1, created_utc=now(), previous_sha256=document['head_sha256'])
        event['sha256'] = event_hash(event)
        document['events'].append(event)
        document.update(revision=event['revision'], head_sha256=event['sha256'])
        if event['kind'] == 'question':
            document['questions'][question['question_id']] = deepcopy(question)
        else:
            document['questions'][question_id]['latest_response_id'] = response_id
        verify_ledger(document)
        atomic_write(path, encode(document))
        return verify_ledger(document)


def text_rows(raw, grid):
    text = raw.decode('utf-8-sig')
    rows = text.splitlines(keepends=True)
    require(isinstance(grid, dict) and isinstance(grid.get('width'), int) and isinstance(grid.get('height'), int),
            'Explicit integer text grid required')
    require(grid['width'] > 0 and grid['height'] > 0 and len(rows) == grid['height'], 'Text grid height differs')
    plain = [x.rstrip('\r\n') for x in rows]
    require(all(len(x) <= grid['width'] and '\r' not in x and '\n' not in x for x in plain), 'Text grid width differs')
    require(all(row[len(body):] in {'', '\n', '\r\n'} for row, body in zip(rows, plain)), 'Unsupported line ending')
    return rows, plain


def patch_text(raw, edits, grid):
    rows, plain = text_rows(raw, grid)
    touched = {}
    for edit in edits:
        row, col = edit['row'], edit['column']
        before, after = edit['before'], edit['after']
        require(isinstance(row, int) and isinstance(col, int) and 0 <= row < len(rows), 'Invalid text edit coordinate')
        require(isinstance(before, str) and isinstance(after, str) and len(before) == len(after) > 0,
                'Only explicit nonempty same-width text replacements are supported')
        require('\n' not in after and '\r' not in after and 0 <= col and col + len(before) <= len(plain[row]),
                'Text edit leaves the existing row or changes line endings')
        require(plain[row][col:col + len(before)] == before, 'Text preimage differs')
        for offset, char in enumerate(after):
            point = (row, col + offset)
            require(point not in touched or touched[point] == char, 'Conflicting overlapping text edits')
            touched[point] = char
    for (row, col), char in touched.items():
        rows[row] = rows[row][:col] + char + rows[row][col + 1:]
    output = ''.join(rows).encode('utf-8')
    if raw.startswith(b'\xef\xbb\xbf'):
        output = b'\xef\xbb\xbf' + output
    require([len(x) for x in text_rows(output, grid)[1]] == [len(x) for x in plain], 'Text row lengths changed')
    return output


def pointer_parts(pointer):
    require(isinstance(pointer, str) and pointer.startswith('/') and pointer != '/', 'Non-root JSON pointer required')
    require(not re.search(r'~(?![01])', pointer), 'Invalid JSON pointer escape')
    return [x.replace('~1', '/').replace('~0', '~') for x in pointer[1:].split('/')]


def declared_model(model, schema):
    require(isinstance(model,dict), 'Unsupported JSON model: object required')
    if schema=='ald-page-nodes-v1':
        require(isinstance(model.get('nodes'),list), 'Declared ALD model requires nodes list')
    elif schema=='ald-socket-listing-table-v1':
        require('nodes' not in model and isinstance(model.get('records'),list)
                and all(isinstance(row,dict)for row in model['records']),
                'Declared socket table requires records list and no synthetic nodes')
    elif schema=='ald-socket-collection-page-v1':
        require(_socket_collection(model),
                'Declared socket collection requires sockets list of objects and no nodes/records')
    else:raise ValueError('Unsupported declared page model schema')
    return schema


def _socket_collection(model):
    return (isinstance(model,dict) and 'nodes' not in model and 'records' not in model
            and isinstance(model.get('sockets'),list)
            and all(isinstance(row,dict)for row in model['sockets']))


def patch_model(model, patches):
    require(isinstance(model, dict) and (isinstance(model.get('nodes'), list) or
            'nodes' not in model and isinstance(model.get('records'),list) and
            all(isinstance(row,dict)for row in model['records']) or _socket_collection(model)),
            'Unsupported JSON model: nodes-list ALD, records-list socket table or declared sockets collection required')
    output = deepcopy(model)
    seen = []
    for patch in patches:
        parts = pointer_parts(patch['pointer'])
        require(not any(parts[:len(old)] == old or old[:len(parts)] == parts for old in seen), 'Overlapping JSON patch scopes')
        seen.append(parts)
        parent = output
        for part in parts[:-1]:
            if isinstance(parent, list):
                require(part.isdigit() and str(int(part)) == part and int(part) < len(parent), 'Invalid array pointer')
                parent = parent[int(part)]
            else:
                require(isinstance(parent, dict) and part in parent, 'Missing JSON pointer parent')
                parent = parent[part]
        last = parts[-1]
        if isinstance(parent, list):
            require(last.isdigit() and str(int(last)) == last and int(last) < len(parent), 'Invalid JSON array index')
            last = int(last)
        require(isinstance(parent, (dict, list)), 'JSON pointer parent is scalar')
        operation = patch.get('op', 'replace')
        if operation == 'replace':
            require(last in parent if isinstance(parent, dict) else 0 <= last < len(parent), 'Missing replace target')
            require('before' in patch and json_equal(parent[last], patch['before']), 'JSON preimage differs: ' + patch['pointer'])
            parent[last] = deepcopy(patch['after'])
        elif operation == 'add':
            require(isinstance(parent, dict) and last not in parent, 'Only addition of a new object member is supported')
            parent[last] = deepcopy(patch['after'])
        elif operation == 'remove':
            require(isinstance(parent, dict) and last in parent and json_equal(parent[last], patch['before']), 'Object removal preimage differs')
            del parent[last]
        else:
            raise ValueError('Unsupported JSON patch operation')
    return output


def model_bytes(model, original):
    newline = '\r\n' if b'\r\n' in original else '\n'
    raw = json.dumps(model, ensure_ascii=False, indent=2).replace('\n', newline)
    if original.endswith(b'\n'):
        raw += newline
    return (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'') + raw.encode('utf-8')


def append_note(raw, paragraph):
    if not paragraph:
        return raw
    require(isinstance(paragraph, str), 'Notes append must be explicit text')
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    return raw.rstrip(b'\r\n') + newline * 2 + paragraph.encode('utf-8').replace(b'\r\n', b'\n').replace(b'\n', newline) + newline


def render_preview(raw, config, base):
    from PIL import Image, ImageDraw, ImageFont
    allowed = {'font', 'width', 'height', 'font_size', 'cell_width', 'row_height', 'origin', 'anchor'}
    require(set(config) <= allowed and allowed - {'anchor'} <= set(config), 'Unsupported/incomplete preview configuration')
    font_path, _ = checked(config['font'], base)
    for key in ['width', 'height', 'font_size', 'cell_width', 'row_height']:
        require(isinstance(config[key], int) and config[key] > 0, 'Invalid preview dimension')
    origin = config['origin']
    require(isinstance(origin, list) and len(origin) == 2 and all(isinstance(x, int) and x >= 0 for x in origin), 'Invalid preview origin')
    require(config.get('anchor') in {None, 'lt'}, 'Unsupported text anchor')
    font = ImageFont.truetype(str(font_path), config['font_size'])
    image = Image.new('RGB', (config['width'], config['height']), 'white')
    draw = ImageDraw.Draw(image)
    rows = raw.decode('utf-8-sig').splitlines()
    require(origin[1] + len(rows) * config['row_height'] <= config['height'], 'Preview clips text rows')
    require(all(origin[0] + len(row) * config['cell_width'] <= config['width'] for row in rows), 'Preview clips text columns')
    for row_index, row in enumerate(rows):
        for col, char in enumerate(row):
            if char != ' ':
                draw.text((origin[0] + col * config['cell_width'], origin[1] + row_index * config['row_height']),
                          char, font=font, fill='black', anchor=config.get('anchor'))
    stream = BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def same_pixels(first, second):
    from PIL import Image, ImageChops
    with Image.open(BytesIO(first)) as a, Image.open(BytesIO(second)) as b:
        return a.size == b.size and ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is None


def quartet_paths(quartet, base, target_root=None):
    require(set(quartet) == KINDS, 'Exact txt/json/notes/preview quartet required')
    result = {}
    for kind, link in quartet.items():
        path, raw = checked(link, base)
        require(path.suffix.lower() == {'txt': '.txt', 'json': '.json', 'notes': '.txt', 'preview': '.png'}[kind],
                'Wrong quartet file type')
        if target_root is not None:
            require(path.is_relative_to(target_root), 'Target outside declared target root')
        result[kind] = (path, raw)
    require(len({x[0] for x in result.values()}) == 4, 'Quartet paths alias each other')
    return result


def create_stage(intent_path, stage_path):
    intent_path = Path(intent_path).resolve()
    intent_raw = intent_path.read_bytes()
    intent = json.loads(intent_raw.decode('utf-8-sig'))
    require(intent.get('schema') == INTENT, 'Unsupported intent schema')
    require(intent.get('unresolved_questions') == [], 'Resolve and record uncertainties before staging corrections')
    require(isinstance(intent.get('review_id'), str) and intent['review_id'], 'Review ID required')
    root = resolve(intent['target_root'], intent_path.parent)
    stage_path = Path(stage_path).resolve()
    require(not stage_path.exists() and not stage_path.is_relative_to(root), 'Stage must be new and outside the target tree')
    pages = intent.get('pages', [])
    require(pages and len({x['page'] for x in pages}) == len(pages), 'Nonempty unique page inventory required')
    prepared, protected, inputs = [], set(), {}
    for link in intent.get('evidence', []):
        path, raw = checked(link, intent_path.parent)
        protected.add(path)
        inputs[path] = raw
    for page in pages:
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}', page['page']), 'Unsafe page key')
        require(page.get('model_schema') in {'ald-page-nodes-v1','ald-socket-listing-table-v1','ald-socket-collection-page-v1'}, 'Unsupported declared page model schema')
        source, _ = checked(page['source'], intent_path.parent)
        require(source.suffix.lower() in {'.tif', '.tiff'}, 'Original TIFF binding required')
        protected.add(source)
        prior = quartet_paths(page['prior_quartet'], intent_path.parent, root)
        require(not ({x[0] for x in prior.values()} & protected), 'A target aliases protected evidence/source')
        for link in page.get('evidence', []):
            path, raw = checked(link, intent_path.parent)
            protected.add(path)
            inputs[path] = raw
        grid = page['grid']
        after = dict((kind, raw) for kind, (path, raw) in prior.items())
        after['txt'] = patch_text(after['txt'], page.get('cell_edits', []), grid)
        model = json.loads(after['json'].decode('utf-8-sig'))
        declared_model(model,page['model_schema'])
        updated = patch_model(model, page.get('json_patches', []))
        require(not validate_pin_edits(model, updated, page), 'Pin annotation/contact mirror guard rejected the declared changes: ' + json.dumps(validate_pin_edits(model, updated, page), ensure_ascii=False))
        if not json_equal(updated, model):
            after['json'] = model_bytes(updated, after['json'])
        after['notes'] = append_note(after['notes'], page.get('notes_append'))
        preview = deepcopy(page.get('preview_config'))
        if after['txt'] != prior['txt'][1]:
            require(isinstance(preview, dict), 'Changed TXT requires explicit preview configuration')
            font, raw = checked(preview['font'], intent_path.parent)
            inputs[font] = raw
            protected.add(font)
            preview['font'] = binding(font)
            require(same_pixels(render_preview(prior['txt'][1], preview, intent_path.parent), prior['preview'][1]),
                    'Preview configuration does not reproduce the accepted preimage')
            after['preview'] = render_preview(after['txt'], preview, intent_path.parent)
        prepared.append((page, source, prior, after, preview))
    targets = [path for page, source, prior, after, preview in prepared for path, raw in prior.values()]
    require(len(set(targets)) == len(targets) and not (set(targets) & protected), 'Targets overlap each other or protected source/evidence')
    for page, source, prior, after, preview in prepared:
        checked(page['source'], intent_path.parent)
        for kind, (target, raw) in prior.items():
            require(target.read_bytes() == raw, 'Preimage changed during staging')
    # No candidate files are created until every declaration/preimage validates.
    stage_path.mkdir(parents=True)
    input_dir = stage_path / 'inputs'
    atomic_write(input_dir / 'intent.json', intent_raw)
    input_records = [{'original_path': str(intent_path), **binding(input_dir / 'intent.json')}]
    snapshots = {}
    for index, (path, raw) in enumerate(sorted(inputs.items(), key=lambda x: str(x[0]))):
        snapshot = input_dir / f'{index:04d}-{digest(raw)[:16]}-{path.name}'
        atomic_write(snapshot, raw)
        input_records.append({'original_path': str(path), **binding(snapshot)})
        snapshots[path] = binding(snapshot)
    tool_snapshot = input_dir / 'source_review.py'
    atomic_write(tool_snapshot, Path(__file__).read_bytes())
    input_records.append({'original_path': str(Path(__file__).resolve()), **binding(tool_snapshot)})
    guard_source = Path(__file__).with_name('source_review_guards.py')
    guard_snapshot = input_dir / guard_source.name
    atomic_write(guard_snapshot, guard_source.read_bytes())
    input_records.append({'original_path': str(guard_source.resolve()), **binding(guard_snapshot)})
    manifest = {'schema': STAGE, 'created_utc': now(), 'review_id': intent['review_id'],
                'card_type': intent.get('card_type'), 'target_root': str(root), 'tool': binding(tool_snapshot),
                'inputs': input_records, 'intent_snapshot': binding(input_dir / 'intent.json'),
                'guard_tool': binding(guard_snapshot), 'records': []}
    for page, source, prior, after, preview in prepared:
        if preview is not None and resolve(preview['font']['path'], intent_path.parent) in snapshots:
            preview['font'] = snapshots[resolve(preview['font']['path'], intent_path.parent)]
        folder = stage_path / page['page']
        before_saved, candidate, prior_bindings = {}, {}, {}
        for kind, (target, raw) in prior.items():
            before_path = folder / ('before-' + target.name)
            candidate_path = folder / target.name
            atomic_write(before_path, raw)
            atomic_write(candidate_path, after[kind])
            before_saved[kind], candidate[kind], prior_bindings[kind] = binding(before_path), binding(candidate_path), binding(target)
        manifest['records'].append({'page': page['page'], 'source': {'path': str(source), 'sha256': page['source']['sha256']}, 'prior_quartet': prior_bindings,
                                    'before_saved': before_saved, 'staged_quartet': candidate, 'grid': page['grid'],
                                    'model_schema': page['model_schema'],
                                    'cell_edits': page.get('cell_edits', []), 'json_patches': page.get('json_patches', []),
                                    'notes_append': page.get('notes_append'), 'preview_config': preview,
                                    'evidence': page.get('evidence', [])})
    atomic_write(stage_path / 'manifest.json', encode(manifest))
    return verify_stage(stage_path / 'manifest.json', phase='staged')


def acceptance_document(path, manifest_path, pages):
    document = read_json(path)
    require(document.get('passed') is True and not document.get('failures'), 'Independent acceptance did not pass')
    require(document.get('manifest_sha256') == digest(Path(manifest_path).read_bytes()), 'Acceptance binds a different stage')
    if document.get('schema') == 'source-review-independent-acceptance-v1':
        require(document.get('independent_review') is True and document.get('unresolved_questions') == [], 'Incomplete independent acceptance')
        require(isinstance(document.get('reviewer'), str) and document['reviewer'], 'Independent reviewer identity required')
        require(set(document.get('accepted_pages', [])) == set(pages) and len(document['accepted_pages']) == len(pages), 'Accepted page inventory differs')
    return document


def verify_stage(manifest_path, phase='either', acceptance=None):
    """Read-only exact artifact/delta check; no correction is reapplied."""
    manifest_path = Path(manifest_path).resolve()
    manifest = read_json(manifest_path)
    schema = manifest.get('schema')
    require(schema in {STAGE, LEGACY}, 'Unsupported stage schema; no inference attempted')
    require(phase in {'staged', 'published', 'either', 'snapshots'}, 'Unsupported verification phase')
    records = manifest.get('records', [])
    pages = [r['page'] for r in records]
    require(records and len(set(pages)) == len(pages), 'Invalid stage page inventory')
    for link in manifest.get('inputs', []):
        checked(link, manifest_path.parent)
    if schema == STAGE:
        require(not manifest_path.parent.is_relative_to(Path(manifest['target_root']).resolve()), 'Stage overlaps the target tree')
        checked(manifest['tool'], manifest_path.parent)
        checked(manifest['guard_tool'], manifest_path.parent)
        checked(manifest['intent_snapshot'], manifest_path.parent)
    if acceptance is not None:
        acceptance_document(acceptance, manifest_path, pages)
    require(schema != LEGACY or acceptance is not None,
            'Legacy manifests omit declarative JSON patches; provide their exact independent acceptance')
    before_epoch, after_epoch, summaries = True, True, []
    target_paths = set()
    for record in records:
        source, _ = checked(record['source'], manifest_path.parent)
        require(source.suffix.lower() in {'.tif', '.tiff'}, 'Bound original is not a TIFF')
        before = quartet_paths(record['before_saved'], manifest_path.parent)
        candidate = quartet_paths(record['staged_quartet'], manifest_path.parent)
        require(all(path.is_relative_to(manifest_path.parent) for path, raw in [*before.values(), *candidate.values()]),
                'Stage snapshots must be inside the manifest directory')
        require(set(record['prior_quartet']) == KINDS, 'Incomplete target quartet')
        for kind, (path, raw) in before.items():
            require(digest(raw) == record['prior_quartet'][kind]['sha256'], 'Predecessor snapshot binding differs')
            target = resolve(record['prior_quartet'][kind]['path'], manifest_path.parent)
            require(target not in target_paths, 'Repeated target path')
            target_paths.add(target)
            require(target != source and target.suffix.lower() != '.tif' and target.suffix.lower() != '.tiff', 'Target aliases original scan')
            if schema == STAGE:
                require(target.is_relative_to(Path(manifest['target_root']).resolve()), 'Target outside declared root')
            if phase != 'snapshots':
                value = digest(target.read_bytes())
                before_epoch &= value == digest(raw)
                after_epoch &= value == digest(candidate[kind][1])
        grid = record.get('grid')
        if grid is None:
            # The native manifest schema defines the standard source-sheet grid.
            grid = {'width': 245, 'height': 103}
        expected = patch_text(before['txt'][1], record.get('cell_edits', []), grid)
        require(expected == candidate['txt'][1], 'Undeclared TXT cells or line endings changed: ' + record['page'])
        before_model = json.loads(before['json'][1].decode('utf-8-sig'))
        after_model = json.loads(candidate['json'][1].decode('utf-8-sig'))
        require(isinstance(before_model, dict) and isinstance(after_model, dict), 'Unsupported model snapshots')
        if schema == STAGE:
            declared_model(before_model,record.get('model_schema','ald-page-nodes-v1'))
            declared_model(after_model,record.get('model_schema','ald-page-nodes-v1'))
            require(json_equal(patch_model(before_model, record.get('json_patches', [])), after_model), 'Undeclared JSON change')
            require(not validate_pin_edits(before_model, after_model, record), 'Pin annotation/contact mirror guard rejected the staged model')
            require(append_note(before['notes'][1], record.get('notes_append')) == candidate['notes'][1], 'Undeclared notes change')
            if expected != before['txt'][1]:
                config = record['preview_config']
                require(same_pixels(render_preview(before['txt'][1], config, manifest_path.parent), before['preview'][1]), 'Preview baseline differs')
                require(render_preview(expected, config, manifest_path.parent) == candidate['preview'][1], 'Candidate preview differs from TXT')
            else:
                require(before['preview'][1] == candidate['preview'][1], 'Unchanged TXT has a changed preview')
        summaries.append({'page': record['page'], 'text_changed': before['txt'][1] != candidate['txt'][1],
                          'model_changed': not json_equal(before_model, after_model),
                          'before_model': record['before_saved']['json'], 'after_model': record['staged_quartet']['json'],
                          'json_delta_paths': json_delta_paths(before_model, after_model),
                          'json_patch_scope': 'exact_declarative_replay' if schema == STAGE else 'bound_independent_acceptance; legacy_has_no_declarative_patch_list'})
    actual_phase = 'snapshots_only' if phase == 'snapshots' else 'unchanged' if before_epoch and after_epoch else 'staged' if before_epoch else 'published' if after_epoch else 'mixed_or_unrecognized'
    require(actual_phase != 'mixed_or_unrecognized', 'Live quartet epoch is mixed or has unrelated changes')
    require(phase in {'either', 'snapshots'} or actual_phase in {phase, 'unchanged'}, 'Live files do not match requested phase')
    return {'passed': True, 'manifest': binding(manifest_path), 'schema': schema, 'pages': len(records),
            'phase': actual_phase, 'original_scan_writes': 0, 'checks': summaries,
            'scope': 'Hash/source/grid/text delta/current epoch; exact JSON/notes/preview replay for generic schema; legacy scope uses bound independent acceptance'}


def publish(manifest_path, acceptance_path):
    manifest_path, acceptance_path = Path(manifest_path).resolve(), Path(acceptance_path).resolve()
    manifest = read_json(manifest_path)
    require(manifest.get('schema') == STAGE, 'Publishing legacy stages is unsupported; verification only')
    publication_path = manifest_path.parent / 'publication.json'
    journal_path = manifest_path.parent / 'publication-in-progress.json'
    with locked(manifest_path.parent / '.publication.lock'):
        if publication_path.exists():
            receipt = read_json(publication_path)
            require(receipt['manifest']['sha256'] == digest(manifest_path.read_bytes()), 'Different stage already published')
            require(receipt['independent_acceptance']['sha256'] == digest(acceptance_path.read_bytes()), 'Different acceptance already published')
            verify_stage(manifest_path, 'published', acceptance_path)
            return {**receipt, 'idempotent_retry': True}
        require(not journal_path.exists(), 'Incomplete publication journal exists; preserve backups and reconcile explicitly')
        acceptance = acceptance_document(acceptance_path, manifest_path, [r['page'] for r in manifest['records']])
        require(acceptance.get('schema') == 'source-review-independent-acceptance-v1', 'Generic independent acceptance schema required for publication')
        verify_stage(manifest_path, 'staged', acceptance_path)
        frozen_acceptance = manifest_path.parent / 'independent-acceptance.snapshot.json'
        atomic_write(frozen_acceptance, acceptance_path.read_bytes())
        transaction = {'schema': 'source-review-publication-journal-v1', 'manifest': binding(manifest_path),
                       'acceptance': binding(frozen_acceptance), 'created_utc': now(), 'records': manifest['records']}
        atomic_write(journal_path, encode(transaction))
        for record in manifest['records']:
            for kind, prior in record['prior_quartet'].items():
                target = Path(prior['path']).resolve()
                require(digest(target.read_bytes()) == prior['sha256'], 'Preimage changed during publication')
                _, candidate = checked(record['staged_quartet'][kind], manifest_path.parent)
                if target.read_bytes() != candidate:
                    atomic_write(target, candidate)
        verify_stage(manifest_path, 'published', frozen_acceptance)
        receipt = {'schema': 'source-review-publication-v1', 'created_utc': now(), 'passed': True,
                   'review_id': manifest['review_id'], 'card_type': manifest.get('card_type'),
                   'manifest': binding(manifest_path), 'independent_acceptance': binding(frozen_acceptance),
                   'published_pages': [r['page'] for r in manifest['records']], 'original_scan_writes': 0}
        receipt['pages'] = [{
            'page': record['page'], 'eligible': True,
            'artifact_schema': 'reviewed-current-quartet-v1',
            'source': deepcopy(record['source']),
            'current_quartet': {kind: {
                'path': str(resolve(record['prior_quartet'][kind]['path'], manifest_path.parent)),
                'sha256': record['staged_quartet'][kind]['sha256']
            } for kind in sorted(KINDS)},
            'checks': {'source_binding': True, 'exact_declarative_replay': True,
                       'independent_acceptance': True, 'current_quartet': True}
        } for record in manifest['records']]
        atomic_write(publication_path, encode(receipt))
        journal_path.unlink()
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    bind = commands.add_parser('bind');bind.add_argument('file', type=Path)
    init = commands.add_parser('ledger-init');init.add_argument('ledger', type=Path);init.add_argument('--review-id', required=True)
    question = commands.add_parser('add-question');question.add_argument('ledger', type=Path);question.add_argument('--question-json', type=Path, required=True);question.add_argument('--expected-revision', type=int)
    answer = commands.add_parser('record-answer');answer.add_argument('ledger', type=Path);answer.add_argument('--question-id', required=True)
    raw = answer.add_mutually_exclusive_group(required=True);raw.add_argument('--raw');raw.add_argument('--raw-file', type=Path)
    answer.add_argument('--normalized');answer.add_argument('--response-id');answer.add_argument('--normalization-note', default='');answer.add_argument('--expected-revision', type=int)
    check = commands.add_parser('verify-ledger');check.add_argument('ledger', type=Path)
    stage = commands.add_parser('stage');stage.add_argument('--intent', type=Path, required=True);stage.add_argument('--stage', type=Path, required=True)
    verify = commands.add_parser('verify-stage');verify.add_argument('manifest', type=Path);verify.add_argument('--phase', choices=['staged', 'published', 'either', 'snapshots'], default='either');verify.add_argument('--acceptance', type=Path);verify.add_argument('--report', type=Path)
    release = commands.add_parser('publish');release.add_argument('manifest', type=Path);release.add_argument('--acceptance', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'bind':result = binding(args.file)
    elif args.command == 'ledger-init':result = ledger_init(args.ledger, args.review_id)
    elif args.command == 'add-question':result = ledger_record(args.ledger, question=read_json(args.question_json), expected_revision=args.expected_revision)
    elif args.command == 'record-answer':result = ledger_record(args.ledger, question_id=args.question_id,
        raw=args.raw_file.read_text(encoding='utf-8-sig') if args.raw_file else args.raw, normalized=args.normalized,
        response_id=args.response_id, normalization_note=args.normalization_note, expected_revision=args.expected_revision)
    elif args.command == 'verify-ledger':result = verify_ledger(read_json(args.ledger))
    elif args.command == 'stage':result = create_stage(args.intent, args.stage)
    elif args.command == 'verify-stage':
        if args.report is not None:
            require(args.report.suffix.lower() == '.json' and not args.report.exists(), 'Report must be a new JSON file; existing records are never replaced')
        result = verify_stage(args.manifest, args.phase, args.acceptance)
        if args.report is not None:
            atomic_write(args.report, encode(result))
    else:result = publish(args.manifest, args.acceptance)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
