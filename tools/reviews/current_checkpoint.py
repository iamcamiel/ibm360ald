"""Validate only current source status and bytes, without historical replay."""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

SCHEMA = 'ald-current-source-checkpoint-v1'
DEFAULT_PATH = 'notes/Source status.json'
SHA = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok: raise ValueError(message)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def relative(value):
    require(isinstance(value,str) and value and '\\' not in value and ':' not in value and '\x00' not in value,
            'Current source path must be portable and relative')
    p=PurePosixPath(value)
    require(bool(p.parts) and not p.is_absolute() and '..' not in p.parts and '.' not in p.parts and p.as_posix()==value,
            'Unsafe current source path: '+value)
    return value


def inside(root, value):
    value=relative(value);path=(root/value).resolve()
    require(path.is_relative_to(root),'Current source path escapes root: '+value)
    return path


def read_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate current checkpoint JSON key: '+key);result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite current checkpoint JSON number: '+value)
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)


class CurrentCheckpoint:
    def __init__(self,repo,path,raw,document,guards):
        self.repo,self.path=repo,path
        self.document=deepcopy(document)
        self.records=self.document['records']
        self.binding={'path':path.relative_to(repo).as_posix(),'sha256':digest(raw)}
        self._guards=tuple((relative,sha,path) for relative,(sha,path) in sorted(guards.items()))

    def recheck(self):
        for rel,expected,original_path in self._guards:
            path=inside(self.repo,rel)
            require(path==original_path and path.is_file(),'Current source path changed or missing: '+rel)
            require(digest(path.read_bytes())==expected,'Current source bytes changed: '+rel)
        return self.report()

    def report(self):
        counts={kind:sum(kind in record['repository'] for record in self.records)for kind in ('txt','json','notes')}
        return {'schema':SCHEMA,'passed':True,'checkpoint':deepcopy(self.binding),'records':len(self.records),
                'reviewed_records':sum(r['status']=='reviewed' for r in self.records),
                'current_files':counts,'checked_files':len(self._guards),'history_replayed':False,'scan_bytes_read':False}


def load_checkpoint(repo, path=None, *, inventory=None):
    """Load a current repository checkpoint and verify every declared artifact.

    inventory may be the current Repository records manifest for ownership
    checks. The checkpoint never binds that manifest, avoiding a hash cycle.
    Optional working_quartet declarations are descriptive; external owner files
    are neither opened nor modified by current repository verification.
    """
    repo=Path(repo).resolve()
    path=inside(repo,DEFAULT_PATH) if path is None else Path(path).resolve()
    require(path.is_relative_to(repo),'Checkpoint is outside repository')
    raw=path.read_bytes();doc=read_json(raw)
    require(isinstance(doc,dict) and doc.get('schema')==SCHEMA,'Unsupported current source checkpoint')
    require(set(doc)<={'schema','records','created_utc','updated_utc','scope','counts','policy'},'Unsupported or historical checkpoint fields')
    records=doc.get('records');require(isinstance(records,list),'Missing current source records')
    guards={path.relative_to(repo).as_posix():(digest(raw),path)}
    owned=None
    if inventory is not None:
        require(isinstance(inventory,dict) and isinstance(inventory.get('files'),list),'Invalid current inventory')
        owned={};owned_folded=set()
        for entry in inventory['files']:
            require(isinstance(entry,dict),'Invalid current inventory entry')
            rel=relative(entry.get('path'));require(rel.casefold() not in owned_folded,'Duplicate current inventory path')
            owned_folded.add(rel.casefold())
            owned[rel]=entry.get('sha256')
        require(owned.get(path.relative_to(repo).as_posix())==digest(raw),'Checkpoint inventory hash differs')
    paths=set();scans=set();allowed={'page','scan_reference','status','repository','working_quartet','significant_corrections','unresolved'}
    for record in records:
        require(isinstance(record,dict) and set(record)<=allowed,'Invalid or historical current source record fields')
        require(isinstance(record.get('page'),str) and bool(record['page'].strip()),'Missing current page identity')
        require(record.get('status') in ('reviewed','unreviewed'),'Invalid explicit current review status')
        scan=record.get('scan_reference');require(isinstance(scan,dict) and set(scan)<={'id','relative_path','sha256'},'Invalid scan reference')
        sid=scan.get('id');require(type(sid) in (str,int) and str(sid).strip()!='','Missing source scan identity')
        require(str(sid) not in scans,'Duplicate current scan identity');scans.add(str(sid))
        relative(scan.get('relative_path'))
        if 'sha256'in scan:require(isinstance(scan['sha256'],str) and SHA.fullmatch(scan['sha256']),'Invalid scan reference hash')
        artifacts=record.get('repository')
        require(isinstance(artifacts,dict) and 'txt'in artifacts and set(artifacts)<={'txt','json','notes'},'Current TXT required; only TXT/JSON/notes bindings allowed')
        for kind,link in artifacts.items():
            require(isinstance(link,dict) and set(link)=={'path','sha256'},'Invalid current artifact binding')
            rel=relative(link.get('path'));expected=link.get('sha256')
            require(isinstance(expected,str) and SHA.fullmatch(expected),'Invalid current artifact hash')
            require(rel.casefold() not in paths and rel.casefold()!=path.relative_to(repo).as_posix().casefold(),'Duplicate artifact or self-bound checkpoint');paths.add(rel.casefold())
            prefix={'txt':'ALD/','json':'json/','notes':'notes/'}[kind]
            require(rel.startswith(prefix),'Current artifact in wrong namespace')
            if kind in ('txt','json'):require(rel.endswith('.'+kind),'Wrong current artifact extension')
            target=inside(repo,rel);require(target.is_file(),'Missing current source artifact: '+rel)
            artifact_raw=target.read_bytes()
            require(digest(artifact_raw)==expected,'Current source hash differs: '+rel)
            artifact_raw.decode('utf-8-sig')
            if kind=='json':
                model=read_json(artifact_raw)
                require(isinstance(model,dict),'Current model must be a JSON object')
                import sys
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'normalization'))
                from pages import SCHEMA as PAGE_SCHEMA, validate_notation, _restore_page
                from review import validate as validate_review
                require(model.get('schema')==PAGE_SCHEMA,'Current canonical page format required: '+rel)
                validate_notation(_restore_page(model));validate_review(model)
                canonical=(json.dumps(model,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf8')
                require(canonical==artifact_raw,'Canonical page serialization required: '+rel)
            if owned is not None:require(owned.get(rel)==expected,'Current source inventory differs: '+rel)
            guards[rel]=(expected,target)
        if 'json'in artifacts:
            require(artifacts['json']['path']=='json/'+artifacts['txt']['path'][4:-4]+'.json','Current model/TXT identity differs')
        for key in ('significant_corrections','unresolved'):
            if key in record:require(isinstance(record[key],list) and all(isinstance(x,str) for x in record[key]),'Current notes must be short text arrays')
        if 'working_quartet'in record:
            working=record['working_quartet'];require(isinstance(working,dict) and set(working)=={'txt','json','notes','preview'},'Invalid optional working quartet')
            for link in working.values():
                require(isinstance(link,dict) and set(link)=={'path','sha256'},'Invalid optional working binding')
                relative(link['path']);require(isinstance(link['sha256'],str) and SHA.fullmatch(link['sha256']),'Invalid optional working hash')
    if owned is not None:
        declared_txt={r['repository']['txt']['path']for r in records}
        expected_txt={rel for rel in owned if rel.startswith('ALD/') and rel.endswith('.txt')}
        require(declared_txt==expected_txt,'Checkpoint/current inventory TXT membership differs')
        expected_models={'json/'+rel[4:-4]+'.json'for rel in declared_txt if 'json/'+rel[4:-4]+'.json'in owned}
        declared_models={r['repository']['json']['path']for r in records if'json'in r['repository']}
        require(declared_models==expected_models,'Checkpoint/current inventory model membership differs')
    result=CurrentCheckpoint(repo,path,raw,doc,guards)
    result.recheck()
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args()
    print(json.dumps(load_checkpoint(args.repo).report(),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
