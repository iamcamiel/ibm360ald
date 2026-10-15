"""Make a tiny v3 manifest; keep every v2 bound artifact until explicit cleanup."""
from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json
ROOT=Path('D:/Github/IBM360');HERE=Path(__file__).resolve().parent
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
BIND=lambda p:{'path':str(Path(p).resolve()),'sha256':SHA(p)}
def save(p,data):
    assert not p.exists(),str(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    before=HERE/'application-unified64-v2/Private unified H rule application manifest.json';assert SHA(before)=='367885e060bfcdb5c2fd9d51e311a8ae1ca5be9a266c331b4a671fc7e9f5df55';old=READ(before);new=copy.deepcopy(old)
    ep=ROOT/'ibm360ald/notes/Reviewed export provenance.json';export=READ(ep);entries={str(e['source_scan_id']):e for e in export['exported']};mapping=[]
    for page in new['pages']:
        scan=str(page['source_scan_id']);entry=entries[scan];copied=Path(page['prior_review_record']['path']).resolve();retained=(ROOT/entry['review_record']).resolve();digest=page['prior_review_record']['sha256']
        assert copied.is_relative_to((HERE/'application-unified64-v2').resolve())and 'Immutable predecessor'in copied.parts
        assert copied.is_file()and retained.is_file()and SHA(copied)==SHA(retained)==digest
        assert retained.is_relative_to(ROOT.resolve())and not retained.is_relative_to((HERE/'application-unified64-v2').resolve())
        mapping.append({'page':page['page'],'source_scan_id':scan,'removed_private_binding':{'historical_path':str(copied),'sha256':digest,'bytes':copied.stat().st_size},'retained_existing_binding':BIND(retained),'accepted_export_review_record':entry['review_record']})
        page['prior_review_record']=BIND(retained)
    assert len(mapping)==33
    for oldpage,newpage in zip(old['pages'],new['pages']):
        restored=copy.deepcopy(newpage);restored['prior_review_record']=oldpage['prior_review_record'];assert restored==oldpage
    assert all(new[k]==old[k]for k in old if k!='pages')
    out=HERE/'application-unified64-v3/Private unified H rule application manifest.json';save(out,new)
    mapfile=HERE/'Compact v3 predecessor binding map.json';save(mapfile,{'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'before_manifest':BIND(before),'compact_manifest':BIND(out),'accepted_export_manifest':BIND(ep),'only_changes':'The33 prior_review_record path bindings now refer to existing byte-identical accepted originals. All64 fields, before/candidate quartet bytes, metadata/history, contact sheets and other manifest fields are unchanged.','mapping':mapping,'redundant_private_predecessor_bytes':sum(m['removed_private_binding']['bytes']for m in mapping),'source_writes':0,'repository_writes':0,'deletions_performed':0,'helper':BIND(Path(__file__))})
    partial=(HERE/'application-unified64').resolve();partialfiles=[p for p in partial.rglob('*')if p.is_file()];needles=[str(partial)+'\\',str(partial).replace('\\','/')+'/'];references=[]
    for p in [before,out,HERE/'Author unified64 private QA.json']+list((HERE/'independent-inventory/unified64-review').glob('*.json')):
        text=p.read_text(encoding='utf-8-sig')
        if any(needle in text or needle.replace('\\','\\\\')in text for needle in needles):references.append(str(p))
    assert not references,references
    cleanup=[]
    for m in mapping:cleanup.append({'kind':'redundant_private_predecessor','path':m['removed_private_binding']['historical_path'],'sha256':m['removed_private_binding']['sha256'],'bytes':m['removed_private_binding']['bytes'],'must_retain_existing':m['retained_existing_binding']})
    for p in partialfiles:
        assert p.resolve().is_relative_to(partial);cleanup.append({'kind':'incomplete_first_stage_file','path':str(p.resolve()),'sha256':SHA(p),'bytes':p.stat().st_size})
    diagnostic=HERE/'Incomplete unified64 stage diagnostic.json';assert diagnostic.is_file()
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'PRIVATE plan only; remove nothing until independent compact-v3 acceptance and explicit root cleanup release','compact_manifest':BIND(out),'binding_map':BIND(mapfile),'v2_manifest_preserved':BIND(before),'author_QA_preserved':BIND(HERE/'Author unified64 private QA.json'),'failure_diagnostic_preserved':BIND(diagnostic),'allowed_roots':[str((HERE/'application-unified64-v2').resolve()),str(partial)],'exact_cleanup_targets':cleanup,'counts':{'redundant_predecessor_files':33,'incomplete_first_stage_files':len(partialfiles),'files':len(cleanup),'anticipated_recovered_bytes':sum(x['bytes']for x in cleanup)},'before_candidate_quartets_contact_sheets_unchanged_and_preserved':True,'incomplete_stage_is_unreferenced_by_v2_v3_and_current_audits':True,'deletions_performed':0,'no_original_TIFFs_or_accepted_112_case_provenance_or_repository_files':True}
    planfile=HERE/'Compact v3 exact cleanup proposal.json';save(planfile,plan);print(json.dumps({'compact_manifest':BIND(out),'binding_map':BIND(mapfile),'cleanup_plan':BIND(planfile),'counts':plan['counts'],'deletions_performed':0}))
if __name__=='__main__':main()
