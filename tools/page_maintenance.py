"""Recoverable updates to current diagram models and derived text."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from browser_cache.catalogue import strict_json, V4_SCHEMA
from browser_cache.publication import no_symlinks


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(document, previous=b''):
    text = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if b'\r\n' in previous:
        text = text.replace('\n', '\r\n')
    return text.encode('utf-8')


def content_digest(document):
    return sha(json.dumps({k: v for k, v in document.items() if k != 'review'},
                          ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('utf-8'))


def safe(root, path):
    root = Path(root).resolve(strict=True)
    path = no_symlinks(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path escapes source tree: ' + str(path))
    return path


def models(root):
    """Visit current JSON only, excluding archived inputs and review sidecars."""
    folder = Path(root) / 'json'
    for path in sorted(folder.rglob('*.json')):
        relative = path.relative_to(folder)
        if any(part.lower() in ('review', 'reviews') for part in relative.parts[:-1]):
            continue
        path = safe(root, path)
        raw = path.read_bytes()
        document = strict_json(raw)
        if not isinstance(document, dict):
            continue
        if document.get('$schema') == V4_SCHEMA:
            yield path, raw, document, 'v4'
        elif document.get('schema') in ('ibm360-ald-page-v2', 'ibm360-ald-page-v3') or 'text_layout' in document:
            yield path, raw, document, 'layout'


def review(root, path, document):
    reference = document.get('review', {}).get('details')
    if not reference:
        return None, None, None
    if not isinstance(reference, str) or '\\' in reference or any(p in ('', '.', '..') for p in reference.split('/')):
        raise ValueError('Unsafe review reference: ' + str(reference))
    target = safe(root, path.parent / reference)
    if not target.is_relative_to(path.parent):
        raise ValueError('Review reference escapes page directory')
    raw = target.read_bytes()
    details = strict_json(raw)
    if details.get('content sha256') != content_digest(document):
        raise ValueError('Review content digest mismatch: ' + str(path))
    return target, raw, details


@contextmanager
def writer_lock(root):
    path = Path(root) / 'notes/.page-maintenance.lock'
    token = (str(os.getpid()) + ':' + uuid.uuid4().hex).encode()
    with path.open('xb') as stream:
        stream.write(token)
    try:
        yield
    finally:
        if path.read_bytes() == token:
            path.unlink()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.page-maintenance-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_changes(root, changes, kind, report, backup_root=None):
    """Preflight the whole plan, back up exact bytes, then replace and rollback on error.

    Each change is (path, expected_before_bytes, new_bytes). Only the published
    model/TXT hashes in Source status are refreshed; other status fields survive.
    Caller holds writer_lock from reading the inputs until this returns.
    """
    root = Path(root).resolve(strict=True)
    changes = [(safe(root, p), before, after) for p, before, after in changes if before != after]
    if not changes:
        return {**report, 'filesChanged': 0, 'receipt': None}
    if len({p for p, _, _ in changes}) != len(changes):
        raise ValueError('Conflicting updates to one file')
    status_path = root / 'notes/Source status.json'
    status_before = status_path.read_bytes()
    status = strict_json(status_before)
    records = {entry['path']: entry for record in status['records']
               for key, entry in record['repository'].items() if key in ('json', 'txt')}
    for path, before, after in changes:
        if path.read_bytes() != before:
            raise ValueError('Source changed before write: ' + str(path))
        record = records.get(path.relative_to(root).as_posix())
        if record is not None:
            if record['sha256'] != sha(before):
                raise ValueError('Source status mismatch: ' + str(path))
            record['sha256'] = sha(after)
    status_after = encode(status, status_before)
    if status_after != status_before:
        changes.append((status_path, status_before, status_after))
    base = Path(backup_root) if backup_root else root / 'review/maintenance'
    folder = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + kind)
    folder.mkdir(parents=True, exist_ok=False)
    entries = []
    for path, before, after in changes:
        saved = folder / 'before' / path.relative_to(root)
        saved.parent.mkdir(parents=True, exist_ok=True)
        with saved.open('xb') as stream:
            stream.write(before); stream.flush(); os.fsync(stream.fileno())
        entries.append({'path': str(path), 'before_sha256': sha(before), 'after_sha256': sha(after),
                        'before_bytes': len(before), 'after_bytes': len(after), 'preimage': str(saved)})
    payload = {**report, 'schema': 'ald-page-maintenance-v1', 'kind': kind, 'completed': False,
               'files': entries, 'status': {'path': str(status_path), 'before': sha(status_before),
               'after': sha(status_after), 'preimage': str(folder / 'before/notes/Source status.json')}}
    atomic(folder / 'plan.json', encode(payload))
    written = []
    try:
        for path, before, after in changes:
            if path.read_bytes() != before:
                raise ValueError('Source changed during batch: ' + str(path))
            atomic(path, after)
            written.append((path, before))
    except BaseException:
        for path, before in reversed(written):
            atomic(path, before)
        raise
    payload['completed'] = True
    payload['filesChanged'] = len(changes)
    atomic(folder / 'receipt.json', encode(payload))
    return {**report, 'filesChanged': len(changes), 'receipt': str(folder / 'receipt.json')}
