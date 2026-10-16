"""Mirror only the accepted A1 correction's notes and hash/provenance records."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import sys

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr
import register_a1_application as registration

def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(doc):return (json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def read(path):return json.loads(path.read_text('utf-8-sig'))
def bind(path):return {'path':str(path),'sha256':sha(path.read_bytes())}

def main():
    adapter=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
    registry=ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json'
    registration.validate_registered_applications(registry,adapter,ROOT,ROOT/'ALD_Visual_Transcriptions',Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))
    plan=read(ROOT/'tmp/ald-text/ald/repository-export/export plan.json')
    selected=[x for x in plan['exported'] if str(x['source_scan_id'])=='119'];assert len(selected)==1
    item=selected[0]
    native=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1232-01 SOCKET LISTING.txt'
    target=REPO/'ALD/A1 Socket Listing/A1232-01 SOCKET LISTING.txt'
    assert item['text_sha256']==sha(native.read_bytes())==sha(target.read_bytes())
    assert item['review_record']==str(adapter.relative_to(ROOT)), 'New exact acceptance was not selected'
    spec=importlib.util.spec_from_file_location('a1_note_export',ROOT/'tmp/ald-text/ald/repository-export/export_reviewed.py')
    exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    import csv,io
    rows=list(csv.DictReader(io.StringIO((exporter.SOURCE/'ALD Scan Order.csv').read_text('utf-8-sig'))))
    at=next(i for i,r in enumerate(rows) if str(r['id'])=='119');row=rows[at]
    _,meta=exporter.companion_metadata(native)
    note=exporter.note_content(Path(row['newpath']),native,meta,row,rows[at-1]['newname'],rows[at+1]['newname'],item['review_record'])
    assert sha(note)==item['notes_sha256']
    updates={REPO/'notes/A1 Socket Listing/A1232-01 SOCKET LISTING review notes.txt':note}
    record_path=REPO/'notes/A1 Socket Listing/A1232-01 SOCKET LISTING review record.json'
    record=read(record_path);record['text_sha256']=item['text_sha256'];record['acceptance_record']=item['review_record']
    record['confirmed_reference_correction']={'from':'REC41AY4','to':'RE041AY4','row':8,'column':24,
        'raw_answer':'Yes, certainly RE041AY4',
        'independent_proof':'notes/Reference data/Uniform socket listings/Confirmed reference correction/Private stage/Independent acceptance.json'}
    updates[record_path]=enc(record)
    provenance_path=REPO/'notes/Reviewed export provenance.json'
    content_path=REPO/'notes/Content data manifest.json';content=read(content_path)
    changed=[]
    for entry in content['files']:
        if entry['path'] in ['json/A1 Socket Listing/Socket reference.json','json/A1 Socket Listing/ALD references.json']:
            current=REPO/entry['path'];entry['sha256']=sha(current.read_bytes());changed.append(entry['path'])
            content['managed_files'][entry['path']]=entry['sha256']
    assert len(changed)==2
    content['updated_utc']=datetime.now(timezone.utc).isoformat();updates[content_path]=enc(content)
    # Keep the prior full-export baseline aligned only for this accepted page.
    last_path=ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json';last=read(last_path)
    assert provenance_path.read_bytes()==last_path.read_bytes(), 'Prior export/provenance baselines differ'
    matches=[i for i,x in enumerate(last['exported']) if str(x['source_scan_id'])=='119'];assert len(matches)==1
    last['exported'][matches[0]]=item
    last.setdefault('managed_files',{})[item['destination']]=item['text_sha256']
    last['managed_files'][item['notes_destination']]=item['notes_sha256']
    if 'reviewed_plan_sha256' in last:
        last['reviewed_plan_sha256']=sha((ROOT/'tmp/ald-text/ald/repository-export/export plan.json').read_bytes())
    last['updated_utc']=datetime.now(timezone.utc).isoformat()
    updates[last_path]=enc(last);updates[provenance_path]=enc(last)
    saved=[]
    for path,raw in updates.items():
        before=path.read_bytes();backup=HERE/'Metadata predecessors'/sha(before)/path.name
        if backup.exists():assert backup.read_bytes()==before
        else:sr.atomic_write(backup,before)
        saved.append((path,before,raw,backup))
    written=[]
    try:
        for path,before,raw,_ in saved:
            assert path.read_bytes()==before
            sr.atomic_write(path,raw);written.append((path,before))
        for path,_,raw,_ in saved:assert path.read_bytes()==raw
    except BaseException:
        for path,before in reversed(written):sr.atomic_write(path,before)
        raise
    receipt={'schema':'a1-confirmed-reference-metadata-publication-v1','passed':True,
        'source_publication':bind(HERE/'Publication receipt.json'),'registered_proof':bind(registry),
        'changed_metadata':[{'target':bind(p),'before':bind(b)} for p,_,_,b in saved],
        'historical_acceptance_arrays_modified':False,'other_pages_updated':0}
    sr.atomic_write(HERE/'Metadata publication receipt.json',enc(receipt))
    print(json.dumps({'passed':True,'metadata_files_updated':len(saved),'active_reference_models_updated':changed}))

if __name__=='__main__':main()
