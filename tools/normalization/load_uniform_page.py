"""Load current uniform data; never load historical sidecars or raw archives."""
import json
from pathlib import Path, PurePosixPath
from pages import SCHEMA, restore_page, validate_current_page

ENVELOPE={'schema','document_id','page','source_status_ref','objects','nets','junctions','source_containers','current_extensions','review'}


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate JSON key: '+key)
        result[key]=value
    return result


def _path(root,relative):
    if not isinstance(relative,str) or not relative or '\\' in relative or ':' in relative:raise ValueError('Expected a portable relative path')
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or p.as_posix()!=relative:raise ValueError('Unsafe relative path')
    root=Path(root).resolve(strict=True);path=root.joinpath(*p.parts).resolve(strict=True)
    if not path.is_relative_to(root):raise ValueError('Path escapes dataset root')
    return path


def validate_page(data):
    if not isinstance(data,dict) or data.get('schema')!=SCHEMA or set(data)!=ENVELOPE:raise ValueError('Unknown uniform page envelope')
    if not isinstance(data['document_id'],str) or not data['document_id']:raise ValueError('Missing document identity')
    if not isinstance(data['page'],dict) or not isinstance(data['page'].get('scan_id'),str) or not isinstance(data['page'].get('kind'),str):raise ValueError('Invalid page identity')
    ref=data['source_status_ref']
    if not isinstance(ref,dict) or set(ref)!={'path','scan_id'} or ref['path']!='notes/Source status.json' or ref['scan_id']!=data['page']['scan_id']:raise ValueError('Invalid current Source status reference')
    if not data['document_id'].startswith(data['page']['scan_id']+':'):raise ValueError('Document and scan identity disagree')
    for key in ('objects','nets','junctions'):
        if not isinstance(data[key],list):raise ValueError('Expected current occurrence array')
    if not isinstance(data['source_containers'],dict) or not isinstance(data['current_extensions'],dict):raise ValueError('Invalid current field collection')
    validate_current_page(data)
    return data


def load_page(root,relative):
    """Read common current facts. This does not grant fresh source acceptance."""
    data=json.loads(_path(root,relative).read_text(encoding='utf-8-sig'),object_pairs_hook=_pairs)
    return validate_page(data)


def load_legacy_view(root,relative):
    return restore_page(load_page(root,relative))
