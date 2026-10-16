"""Publish only the independently reviewed, explicit eleven-file A1 correction."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys

WORKSPACE=Path('D:/Github/IBM360').resolve()
sys.path.insert(0,str(WORKSPACE/'ibm360ald/tools/reviews'))
import source_review as sr

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def binding(path):return {'path':str(path),'sha256':sha(path.read_bytes())}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parent
    path=root/'Stage manifest.json';raw=path.read_bytes();doc=read(path)
    assert sha(raw)=='4b49f7f81faf5ad37778857794ef466eda6ff291f0fc75a58cf3894f62d0494e'
    acceptance=args.acceptance.resolve();approval=read(acceptance)
    assert approval.get('passed') is True and approval.get('failures')==[]
    assert approval.get('independent_review') is True and approval['manifest_sha256']==sha(raw)
    def checked(link):
        p=Path(link['path']);b=p.read_bytes();assert sha(b)==link['sha256'],p;return b
    def evidence(value):
        if isinstance(value,dict):
            if {'path','sha256'}<=set(value):checked(value)
            else:
                for child in value.values():evidence(child)
        elif isinstance(value,list):
            for child in value:evidence(child)
    for key in ['source','human_authority','source_crop','predecessor_acceptance',
                'historical_repository_acceptance','corroboration','render_font']:
        evidence(doc[key])
    prepared=[]
    for item in doc['files']:
        target=Path(item['target']).resolve()
        assert target.is_relative_to(WORKSPACE) and target.suffix.lower() not in {'.tif','.tiff'}
        before=checked(item['before']) if item['before'] else None
        current=target.read_bytes() if target.exists() else None
        assert current==before, 'Stale target: '+str(target)
        candidate=checked(item['candidate'])
        prepared.append((target,before,candidate))
    assert len(prepared)==11 and len({p for p,_,_ in prepared})==11
    written=[]
    try:
        for target,before,candidate in prepared:
            assert (target.read_bytes() if target.exists() else None)==before
            sr.atomic_write(target,candidate);written.append((target,before))
        for target,_,candidate in prepared:assert target.read_bytes()==candidate
        checked(doc['source']);checked(doc['predecessor_acceptance']);checked(doc['historical_repository_acceptance'])
    except BaseException:
        for target,before in reversed(written):
            if before is None:target.unlink()
            else:sr.atomic_write(target,before)
        raise
    receipt={'schema':'socket-table-literal-correction-publication-v1','passed':True,
        'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':binding(path),
        'independent_acceptance':binding(acceptance),'source':doc['source'],
        'publisher':binding(Path(__file__).resolve()),
        'published_targets':[binding(p) for p,_,_ in prepared],
        'historical_acceptances_unchanged':True,'original_TIFF_unchanged':True}
    output=root/'Publication receipt.json';assert not output.exists()
    sr.atomic_write(output,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'passed':True,'published_files':len(prepared),'receipt':str(output)}))

if __name__=='__main__':main()
