"""Build-time catalogue projection of the installed PHP source contract.

No source data is read and no installed renderer is imported at module import.
All authoritative reads belong to the caller's publication snapshot.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import sys

from .publication import no_symlinks


V4_SCHEMA = 'https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json'
QUALIFIED_RENDERER_SHA256 = '265369551ac722e5199053318ef780d26c7c998dab9d99c764c70c34039f9bc6'
QUALIFIED_ADAPTER_SHA256 = '908e8c2487e1c971080cf1c5deeec68fecde7dd9ad2db6779e4b23a529524ea3'
CARD_FILE = re.compile(r'([0-9]{4})(?:-([0-9]+))?\.txt\Z')


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def strict_json(payload):
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON object key: ' + key)
            value[key] = item
        return value

    def constant(token):
        raise ValueError('Non-finite JSON number: ' + token)

    def number(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError('Non-finite JSON number: ' + token)
        return value

    def integer(token):
        value = int(token)
        return value if -(2 ** 63) <= value < 2 ** 63 else number(token)

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant,
                      parse_float=number, parse_int=integer)


def approved_content(document):
    """PHP's typed content digest, preserving empty objects versus arrays."""
    review = document.get('review')
    if not (document.get('schema') == 'ibm360-ald-page-v3'
            and isinstance(review, dict) and review.get('user_approved') is True
            and review.get('status') == 'approved'
            and isinstance(review.get('approval_statement'), str)
            and review['approval_statement'].strip(' \t\n\r\x00\x0b')
            and isinstance(review.get('approved_at'), str)):
        return False
    context = hashlib.sha256()

    def walk(value):
        if value is None:
            context.update(b'N')
        elif type(value) is bool:
            context.update(b'B1' if value else b'B0')
        elif type(value) is int:
            text = str(value).encode('ascii')
            context.update(b'I' + str(len(text)).encode() + b':' + text)
        elif type(value) is float:
            context.update(b'F' + struct.pack('>d', value))
        elif isinstance(value, str):
            text = value.encode('utf-8')
            context.update(b'S' + str(len(text)).encode() + b':' + text)
        elif isinstance(value, list):
            context.update(b'A' + str(len(value)).encode() + b':')
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            context.update(b'O' + str(len(value)).encode() + b':')
            for key in sorted(value):
                walk(key)
                walk(value[key])
        else:
            raise ValueError('Invalid JSON content value')

    walk({key: value for key, value in document.items() if key != 'review'})
    return review.get('content_sha256') == context.hexdigest()


def source_path(root, relative, prefix=None, suffix=None):
    if not isinstance(relative, str):
        raise ValueError('Invalid source identity')
    relative = relative.replace('\\', '/')
    parts = relative.split('/')
    if (parts[0] not in ('ALD', 'json', 'Card-ALD', 'notes')
            or any(part in ('', '.', '..') for part in parts)
            or ':' in relative or '\x00' in relative
            or (prefix is not None and parts[0] != prefix)
            or (suffix is not None and not relative.endswith(suffix))):
        raise ValueError('Invalid source identity: ' + relative)
    path = no_symlinks(root / relative)
    path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Source file is unavailable: ' + relative)
    return path, relative


def dimensions(text):
    value = text.removeprefix('\ufeff')
    if not value:
        return 0, 0
    rows = re.split(r'\r\n|\r|\n', value)
    if value.endswith(('\r', '\n')):
        rows.pop()
    return len(rows), max(map(len, rows), default=0)


def metadata(model):
    if not isinstance(model, dict):
        raise ValueError('Expected source model object')
    schema = model.get('$schema')
    if '$schema' in model and schema != V4_SCHEMA:
        raise ValueError('Unsupported functional page schema')
    for field in ('page', 'current_extensions', 'review'):
        if model.get(field) is not None and not isinstance(model[field], dict):
            raise ValueError('Invalid source model header')
    page = model.get('page') or {}
    extensions = model.get('current_extensions') or {}
    review = model.get('review') or {}
    title = page.get('title')
    if title is None:
        title = extensions.get('title')
    if isinstance(title, list):
        if any(not isinstance(part, str) for part in title):
            raise ValueError('Invalid source model title')
        title = ' '.join(title)
    functional = schema == V4_SCHEMA
    result = dict(functional=functional, page=page.get('page'), title=title,
                  type=extensions.get('page_type'),
                  reviewRef=review.get('details') if functional else None,
                  reviewStatus=(review.get('status') if review.get('status') is not None else 'unreviewed') if functional else 'unreviewed')
    for field in ('page', 'title', 'type', 'reviewRef'):
        if result[field] is not None and not isinstance(result[field], str):
            raise ValueError('Invalid source model metadata')
    if not isinstance(result['reviewStatus'], str):
        raise ValueError('Invalid review status')
    return result


def bind_review(snapshot, path, ref):
    if ref is None:
        return None
    if (not isinstance(ref, str) or not ref or '\\' in ref or ':' in ref
            or '\x00' in ref or any(part in ('', '.', '..') for part in ref.split('/'))):
        raise ValueError('Unsafe review details reference')
    target = no_symlinks(path.parent / ref)
    target.resolve(strict=True)
    if not target.is_relative_to(path.parent) or not target.is_file():
        raise ValueError('Review details escape page directory')
    return digest(snapshot.read(target))


def collect(root, snapshot, put_asset):
    """Return catalogue, compact legacy models, effective texts, native views.

    ``snapshot.read(Path)`` returns bound original bytes; ``track_directory``
    binds matching membership. The caller must verify the snapshot immediately
    before publishing the final catalogue and derive its generation afterward.
    """
    from .interactions import extract_legacy

    root = no_symlinks(root).resolve(strict=True)
    status_path, _ = source_path(root, 'notes/Source status.json')
    status_bytes = snapshot.read(status_path)
    status = strict_json(status_bytes)
    if not isinstance(status, dict) or not isinstance(status.get('records'), list) or not status['records']:
        raise ValueError('Source status must contain published records')
    specs = []
    identities = set()
    model_files = set()
    text_files = set()
    for record in status['records']:
        jp = record['repository']['json']['path']
        tp = record['repository']['txt']['path']
        model_path, jp = source_path(root, jp, 'json', '.json')
        text_path, tp = source_path(root, tp, 'ALD', '.txt')
        identity = digest(jp.encode())
        if (identity in identities or model_path in model_files or text_path in text_files
                or not isinstance(record.get('page'), str) or not record['page']):
            raise ValueError('Invalid or repeated published page identity')
        identities.add(identity)
        model_files.add(model_path)
        text_files.add(text_path)
        specs.append(dict(id=identity, model=jp, text=tp, model_path=model_path,
                          text_path=text_path, record=record))
    snapshot.track_directory(root / 'Card-ALD', '*.txt')
    for directory in (root / 'json/Card-ALD', root / 'json/Card-ALD/definitions'):
        snapshot.track_directory(directory, '*.json')
    for text_path in sorted((root / 'Card-ALD').glob('*.txt'), key=lambda path: path.name):
        match = CARD_FILE.fullmatch(text_path.name)
        if match is None:
            continue
        card, variant = match.groups()
        tp = 'Card-ALD/' + text_path.name
        text_path, _ = source_path(root, tp)
        jp = None
        model_path = None
        for candidate in ('json/Card-ALD/definitions/' + card + '.json', 'json/Card-ALD/' + card + '.json'):
            if (root / candidate).is_file():
                model_path, jp = source_path(root, candidate)
                break
        identity = digest(tp.encode())
        if identity in identities:
            raise ValueError('Repeated card identity')
        identities.add(identity)
        specs.append(dict(id=identity, model=jp, text=tp, model_path=model_path,
                          text_path=text_path, card=card, variant=variant))

    entries, legacy, texts, native, native_outputs = [], {}, {}, {}, {}
    adapter = None
    renderer_path = root / 'tools/ald_render.py'
    for completed, spec in enumerate(specs, 1):
        identity = spec['id']
        published = snapshot.read(spec['text_path'])
        published_sha = digest(published)
        text = published.decode('utf-8')
        model = None
        model_sha = None
        meta = None
        if spec['model_path'] is not None:
            model_bytes = snapshot.read(spec['model_path'])
            model_sha = digest(model_bytes)
            model = strict_json(model_bytes)
            meta = metadata(model)
        card = spec.get('card')
        functional = bool(meta and meta['functional'])
        stem = Path(spec['text']).stem
        file_code, _, filename_title = stem.partition(' ')
        page = stem if card is not None else spec['record']['page']
        if functional and meta['page'] != page:
            raise ValueError('Functional page identity does not match the catalogue')
        title = ('Symbol variant ' + spec['variant'] if spec['variant'] is not None else 'Canonical pinout') if card is not None else (meta['title'] if meta and meta['title'] is not None else (filename_title or stem))
        subpage_match = re.fullmatch(re.escape(page) + r'-([0-9]+)', file_code) if card is None else None
        subpage = subpage_match[1] if subpage_match else None
        display_title = title
        if subpage is not None and not re.search(r'\bpage\s*0*' + str(int(subpage)) + r'\b', title, re.I):
            display_title += ' page ' + subpage
        rows, columns = dimensions(text)
        entry = dict(id=identity, page=page, title=title,
                     section='Card ALD' if card is not None else '/'.join(spec['text'].split('/')[1:-1]),
                     type='card-ald' if card is not None else ('ald' if functional else (meta['type'] if meta and meta['type'] is not None else 'ald')),
                     rows=rows, columns=columns, textSha256=published_sha,
                     modelSha256=None if card is not None else model_sha,
                     grid=dict(columnPitch=20, rowPitch=30), originalScan=None,
                     txtDownloadName=Path(spec['text']).name,
                     _text=spec['text'], _model=spec['model'],
                     _publishedTextSha256=published_sha)
        if card is not None:
            entry.update(cardType=card, variant=spec['variant'])
        else:
            entry.update(displayPage=file_code if subpage is not None else page,
                         displayTitle=display_title, subpage=subpage)
        pair_current = card is not None or (spec['record']['repository']['json']['sha256'] == model_sha and spec['record']['repository']['txt']['sha256'] == published_sha)
        if not pair_current:
            raise ValueError('Published JSON/TXT does not match Source status SHA256')
        if model is not None:
            entry.update(jsonURL=put_asset(model_bytes, '.json'), jsonSha256=model_sha,
                         jsonDownloadName=card + '.json' if card is not None else Path(spec['model']).name)
        entry['_sourcePairCurrent'] = pair_current
        entry['userApproved'] = bool(not functional and card is None and pair_current and model is not None and approved_content(model))
        if functional:
            review_sha = bind_review(snapshot, spec['model_path'], meta['reviewRef'])
            if adapter is None:
                adapter_path = root / 'web/php/v4_view.py'
                if digest(snapshot.read(adapter_path)) != QUALIFIED_ADAPTER_SHA256:
                    raise ValueError('Native adapter differs from qualified installed source')
                if digest(snapshot.read(renderer_path)) != QUALIFIED_RENDERER_SHA256:
                    raise ValueError('Standalone renderer differs from qualified geometry adapter')
                module_spec = importlib.util.spec_from_file_location('aldbrowser_static_native_view', adapter_path)
                adapter = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(adapter)
            view = adapter.view(spec['model_path'], renderer_path)
            if (view['modelSha256'] != model_sha or view['page'] != page
                    or digest(view['text'].encode('utf-8')) != view['textSha256']):
                raise ValueError('Native view does not match bound source')
            text = view['text']
            rows, columns = dimensions(text)
            entry.update(format='v4', rows=rows, columns=columns,
                         textSha256=view['textSha256'], reviewStatus=view['reviewStatus'],
                         reviewBound=view['reviewBound'], unresolvedCount=view['unresolvedCount'],
                         publicationIssues=view.get('publicationIssues'),
                         renderVerified=True, nativeViewPending=False, userApproved=False,
                         _reviewSignature=[model_sha, review_sha])
            native[identity] = view
            native_outputs[identity] = [output['net number'] for output in model['outputs']]
        elif model is not None and card is None:
            legacy[identity] = extract_legacy(model)
        texts[identity] = text
        entry['url'] = put_asset(text.encode('utf-8') if functional else published, '.txt')
        entries.append(entry)
        if completed % 100 == 0 or completed == len(specs):
            print(f'Building browser cache: {completed}/{len(specs)} pages', file=sys.stderr, flush=True)

    def order(entry):
        card = entry['type'] == 'card-ald'
        page = entry.get('displayPage', entry['page'])
        if card and entry['variant'] is not None:
            page = entry['cardType'] + '-' + format(int(entry['variant']) + 1, '09d')
        return (int(card), entry['section'].lower(), page, entry['title'], entry['id'])

    entries.sort(key=order)
    default = next((entry for entry in entries if entry['page'] == 'AP154' and entry['type'] == 'ald'), entries[0])
    catalogue = dict(schema='aldbrowser-catalogue-v1', sourceStatusSha256=digest(status_bytes),
                     pageCount=len(entries), aldPageCount=sum('card' not in spec for spec in specs),
                     cardPageCount=sum('card' in spec for spec in specs), defaultPage=default['page'],
                     defaultPageId=default['id'], pages=entries, delivery='static-cache-v1',
                     _nativeOutputsById=native_outputs)
    return catalogue, legacy, texts, native
