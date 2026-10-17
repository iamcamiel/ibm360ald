"""Refresh only explicitly hash-authorized repository inventory changes.

Dry run by default. The allowlist binds the predecessor manifest and every
permitted before/after file hash. Unexplained recorded-file changes fail closed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reviews'))
import source_review as sr
import current_checkpoint

ROOT=Path(__file__).resolve().parents[2]


def digest(raw):return sha256(raw).hexdigest()
def encode(doc):return (json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def require(ok,text):
    if not ok:raise ValueError(text)


def target(repo,relative):
    require(isinstance(relative,str) and relative and not Path(relative).is_absolute(),'Inventory path must be relative')
    path=(repo/relative).resolve();require(path.is_relative_to(repo),'Inventory target escapes repository')
    return path


def prepare(repo,allowlist_path,*,preserve_history=None):
    repo=Path(repo).resolve();allowlist_path=Path(allowlist_path).resolve()
    original_allowlist=allowlist_path.read_bytes();allowlist=json.loads(original_allowlist.decode('utf-8-sig'))
    require(allowlist.get('schema')=='repository-inventory-allowlist-v1','Unsupported inventory allowlist')
    manifest=repo/'notes/Repository records manifest.json';original=manifest.read_bytes()
    compact=(repo/current_checkpoint.DEFAULT_PATH).is_file() and preserve_history is not True
    if preserve_history is False:require(compact,'Compact inventory mode requires current Source status')
    checkpoint=current_checkpoint.load_checkpoint(repo) if compact else None
    require(allowlist['baseline_manifest']['sha256']==digest(original),'Stale inventory predecessor')
    require(Path(allowlist['baseline_manifest']['path']).resolve()==manifest,'Allowlist names another inventory')
    doc=json.loads(original.decode('utf-8-sig'));updated=deepcopy(doc)
    inventory={entry['path']:entry for entry in updated['files']}
    require(len(inventory)==len(updated['files']),'Duplicate prior inventory paths')
    authorized={entry['path']:entry for entry in allowlist['entries']}
    require(len(authorized)==len(allowlist['entries']),'Duplicate allowlist paths')
    guards={manifest:digest(original),allowlist_path:digest(original_allowlist)};changes=[]
    removed=set()
    for relative,item in authorized.items():
        require(item.get('action','update') in ('update','remove'),'Unknown inventory action: '+relative)
        if item.get('action')!='remove':continue
        require(isinstance(item.get('authority'),str) and item['authority'].strip(),'Explicit removal authority required: '+relative)
        require(relative in inventory and item.get('before_sha256')==inventory[relative]['sha256'],'Incorrect retirement predecessor: '+relative)
        require(item.get('after_sha256') is None,'Inventory retirement must have null after hash: '+relative)
        path=target(repo,relative);require(path!=manifest and not path.exists(),'Retirement requires an already absent file: '+relative)
        removed.add(relative);guards[path]=None
        changes.append({'path':relative,'action':'remove','before_sha256':inventory[relative]['sha256'],'after_sha256':None})
    if removed:updated['files']=[entry for entry in updated['files'] if entry['path'] not in removed]
    for relative,entry in inventory.items():
        if relative in removed:continue
        path=target(repo,relative);require(path.is_file(),'Missing recorded inventory file: '+relative)
        raw=path.read_bytes();actual=digest(raw);guards[path]=actual
        if actual!=entry['sha256']:
            item=authorized.get(relative)
            require(item is not None,'Unexplained inventory change: '+relative)
            require(item.get('before_sha256')==entry['sha256'] and item.get('after_sha256')==actual,'Allowlist before/after mismatch: '+relative)
            changes.append({'path':relative,'before_sha256':entry['sha256'],'after_sha256':actual})
    for relative,item in authorized.items():
        if relative in removed:continue
        require(isinstance(item.get('authority'),str) and item['authority'].strip(),'Explicit change authority required: '+relative)
        path=target(repo,relative);require(path!=manifest,'Inventory must not inventory itself')
        require(path.is_file(),'Allowed file missing: '+relative)
        raw=path.read_bytes();actual=digest(raw);require(actual==item['after_sha256'],'Allowed current hash differs: '+relative)
        guards[path]=actual
        if path.suffix.lower() in {'.txt','.json','.csv','.py'}:raw.decode('utf-8-sig')
        if relative in inventory:
            require(item.get('before_sha256')==inventory[relative]['sha256'],'Incorrect authorized predecessor: '+relative)
            entry=inventory[relative]
        else:
            require(item.get('before_sha256') is None,'New file claims an inventory predecessor: '+relative)
            entry={'path':relative};updated['files'].append(entry);inventory[relative]=entry
            changes.append({'path':relative,'before_sha256':None,'after_sha256':actual})
        entry['sha256']=actual
        if item.get('role'):entry['role']=item['role']
    preserved=None
    if not compact:
        preserved=repo/'notes/Source reviews/Inventory predecessors'/digest(original)/manifest.name
        prior=preserved.read_bytes() if preserved.is_file() else None
        require(prior in (None,original),'Predecessor inventory preservation changed')
        guards[preserved]=None if prior is None else digest(prior)
        relative=preserved.relative_to(repo).as_posix()
        if relative not in inventory:
            updated['files'].append({'path':relative,'sha256':digest(original),'role':'Immutable predecessor repository integrity inventory'})
        else:require(inventory[relative]['sha256']==digest(original),'Predecessor inventory recorded hash differs')
    updated['updated_utc']=allowlist.get('created_utc',sr.now())
    if compact:
        updated.pop('scoped_inventory_reviews',None)
        updated.pop('historical_shared_tools',None)
        updated['scope']='Current published data, concise notes and reusable tools; Git holds version history.'
        updated['reviewed_texts']=sum(record['status']=='reviewed' for record in checkpoint.records)
        updated['shared_tools']=sum(entry['path'].startswith('tools/') for entry in updated['files'])
        updated['current_inventory_review']={'allowlist_sha256':digest(original_allowlist),'authorized_files':len(authorized)}
        checkpoint=current_checkpoint.load_checkpoint(repo,inventory=updated)
    else:
        updated.setdefault('scoped_inventory_reviews',[]).append({'allowlist_sha256':digest(original_allowlist),'predecessor_sha256':digest(original),'authorized_files':len(authorized)})
    new=encode(updated)
    report={'schema':'repository-inventory-refresh-plan-v1','passed':True,'baseline_manifest':sr.binding(manifest),
            'allowlist':sr.binding(allowlist_path),'checked_existing_files':len(doc['files']),
            'authorized_changes':changes,'preserved_predecessor':None if compact else {'path':str(preserved),'sha256':digest(original)},
            'retention':'compact-current' if compact else 'legacy-history',
            'current_source_status':deepcopy(checkpoint.binding) if compact else None,
            'new_inventory_sha256':digest(new),'new_inventory_files':len(updated['files']),
            'content_file_changes':0,'write':False}
    return report,manifest,original,new,preserved,guards


def apply(prepared):
    report,manifest,original,new,preserved,guards=prepared
    if report.get('retention')=='compact-current':
        checkpoint=current_checkpoint.load_checkpoint(manifest.parents[1],inventory=json.loads(new.decode('utf-8-sig')))
        require(checkpoint.binding==report['current_source_status'],'Current checkpoint changed after preparation')
    for path,expected in guards.items():
        actual=digest(path.read_bytes()) if path.is_file() else None
        require(actual==expected,'Input changed before inventory refresh: '+str(path))
    if preserved is not None and not preserved.exists():sr.atomic_write(preserved,original)
    try:
        sr.atomic_write(manifest,new)
        require(manifest.read_bytes()==new and (preserved is None or preserved.read_bytes()==original),'Inventory write verification failed')
    except BaseException:
        if manifest.read_bytes()!=original:sr.atomic_write(manifest,original)
        raise
    return {**report,'schema':'repository-inventory-refresh-receipt-v1','write':True,'passed':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('allowlist',type=Path)
    parser.add_argument('--repo',type=Path,default=ROOT);parser.add_argument('--write',action='store_true')
    parser.add_argument('--retain-inventory-history',action='store_true',help='Explicitly retain legacy predecessor snapshots instead of compact current retention')
    parser.add_argument('--report',type=Path);args=parser.parse_args()
    prepared=prepare(args.repo,args.allowlist,preserve_history=True if args.retain_inventory_history else None);report=apply(prepared) if args.write else prepared[0]
    if args.report:
        output=args.report.resolve();require(not output.is_relative_to(args.repo.resolve()),'Report must be outside repository')
        sr.atomic_write(output,encode(report))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
