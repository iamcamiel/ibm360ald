"""Fail closed before legacy writers touch a held typed publication index.

This is a rejection guard, not an adapter or a new publisher. Pure functions do
not call it. No lock, directory, chmod, inventory or source mutation occurs here.
"""
from pathlib import Path
import json,sys,os
INDEX='notes/Card-ALD/Universal card diagrams publication.json'
HELD_SCHEMA='held-derived-card-index-v1'
LEGACY_SCHEMAS=frozenset(('shared-card-renderer-publication-v1','universal-card-diagrams-publication-v1'))
GUARD_VERSION='legacy-held-index-mutation-guard-v1'

def repository_root(module_file):
    combined=[arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--root=')]
    if combined:
        if len(combined)!=1 or not combined[0] or '--root' in sys.argv:raise ValueError('One explicit --root repository path required')
        return Path(combined[0]).resolve()
    if '--root' in sys.argv:
        i=sys.argv.index('--root')
        if i+1>=len(sys.argv):raise ValueError('--root needs an explicit repository path')
        if sys.argv.count('--root')!=1:raise ValueError('One explicit --root repository path required')
        return Path(sys.argv[i+1]).resolve()
    return Path(module_file).resolve().parents[2]

def dependency_paths(root,module_file):
    """Current private/installed tree first; candidate siblings remain first."""
    root=Path(root).resolve();base=root/'tools/card_ald'
    if not (base/'card_source.py').is_file():
        base=next((p/'ibm360ald/tools/card_ald' for p in Path(module_file).resolve().parents if (p/'ibm360ald/tools/card_ald/card_source.py').is_file()),None)
    if base is None:raise ValueError('Complete current card runtime unavailable')
    if str(base) not in sys.path:sys.path.append(str(base))

def reject_held_index(root,operation):
    root=Path(root).resolve();path=root/INDEX
    if not path.exists():return None
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate publication index key')
            result[key]=value
        return result
    data=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=unique)
    if not isinstance(data,dict):raise ValueError('Publication index must be an object')
    schema=data.get('schema')
    if schema==HELD_SCHEMA:
        raise ValueError(f'{operation}: legacy mutation refuses held-derived-card-index-v1 before any canonical write; a separately reviewed atomic typed-index publication adapter is required')
    if schema not in LEGACY_SCHEMAS:
        raise ValueError(f'{operation}: unsupported publication index schema; no legacy mutation permitted')
    return schema

def guard_target(root,target,operation):
    lexical_root=Path(os.path.abspath(root));lexical_target=Path(os.path.abspath(target))
    # A canonical lexical path remains a canonical mutation when a symlink or
    # junction resolves it outside. Never discard ownership before the guard.
    if lexical_target.is_relative_to(lexical_root):
        rel=lexical_target.relative_to(lexical_root)
        if rel.parts and (rel.parts[0] in ('Card-ALD','json','csv','notes','tools') or rel.name=='.card-publication.lock'):
            reject_held_index(lexical_root,operation)
    root=lexical_root.resolve();target=lexical_target.resolve()
    if target.is_relative_to(root):
        rel=target.relative_to(root)
        if rel.parts and (rel.parts[0] in ('Card-ALD','json','csv','notes','tools') or rel.name=='.card-publication.lock'):reject_held_index(root,operation)

def require_guarded_renderer(renderer):
    if getattr(renderer,'LEGACY_INDEX_GUARD_VERSION',None)!=GUARD_VERSION:
        raise ValueError('Guarded publisher requires the coordinated guarded renderer; copy all registered candidates into one private/installed tool tree')

def guard_existing_ancestor_index(target,operation):
    lexical=Path(os.path.abspath(target))
    for root in lexical.parents:
        if (root/INDEX).is_file():
            guard_target(root,lexical,operation)
    target=lexical.resolve()
    for root in target.parents:
        if (root/INDEX).is_file():
            guard_target(root,target,operation)
