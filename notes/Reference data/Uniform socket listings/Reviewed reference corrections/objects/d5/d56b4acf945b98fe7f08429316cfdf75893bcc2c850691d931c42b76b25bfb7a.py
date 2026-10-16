"""Independent private-stage checks; no production preparation code imported."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,re,sys
from PIL import Image

base=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent.parent;repo=Path('D:/Github/IBM360/ibm360ald')
manifest=base/'Stage manifest.json';checks=[];failures=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def need(ok,description):
    checks.append({'passed':bool(ok),'check':description})
    if not ok:failures.append(description)
def binding(b):
    need(Path(b['path']).is_file() and sha(b['path'])==b['sha256'],'Hash '+b['path'])
def pointer(doc,p):
    for key in (p[1:].split('/') if p else []):
        key=key.replace('~1','/').replace('~0','~');doc=doc[int(key)] if isinstance(doc,list) else doc[key]
    return doc
def context(doc,p):
    found={};cur=doc
    for key in [None]+(p[1:].split('/') if p else []):
        if key is not None:
            key=key.replace('~1','/').replace('~0','~');cur=cur[int(key)] if isinstance(cur,list) else cur[key]
        if not isinstance(cur,dict):continue
        for field in ['board','card_type','pin','portion','printed_portions','portions','ALD_reference']:
            if field in cur:found[field]=cur[field]
        if isinstance(cur.get('socket'),str):found['sockets']=[cur['socket']]
        if isinstance(cur.get('sockets'),list) and all(isinstance(x,str) for x in cur['sockets']):found['sockets']=cur['sockets']
    return found
def sockets(values):return {re.sub(r'(?<=\d)[BT]$','',s) for s in values}

try:
    m=read(manifest);original_manifest_sha=sha(manifest)
    binding(m['reviewed_findings']);binding(m['preparation_script']);binding(m['font'])
    for link in m['source_bindings']:binding({'path':str(repo/link['path']),'sha256':link['sha256']})
    truth=deepcopy(read(repo/'json/Socket listings uniform/Socket listings.json')['records'])
    edits={};expected_cells={};reviewed_tokens=0
    for p in m['pages']:
        binding(p['working_txt']);binding(p['repository_txt'])
        raw=Path(p['repository_txt']['path']).read_bytes();lines=raw.decode('utf-8-sig').splitlines(keepends=True)
        after=list(lines);cells=[]
        for e in p['reviewed_tokens']:
            s=e['span'];key=(str(s['scan_id']),s['row'],s['token_column']);need(key not in edits,'Unique reviewed token '+str(key));edits[key]=e
            need(s['page']==p['page'] and str(s['scan_id'])==str(p['scan_id']),'Source token belongs to same scan')
            need(lines[s['row']][s['column']:s['column']+len(s['literal'])]==s['literal'],'Bound source span literal')
            need(lines[s['row']][s['token_column']:s['token_column']+5]==e['old'],'Exact old token at bound source cells')
            need(m['reference_aliases'][e['old']]==e['new'] and len(e['old'])==len(e['new'])==5,'Reviewed alias exact fixed-width change')
            y,x=s['row'],s['token_column'];after[y]=after[y][:x]+e['new']+after[y][x+5:]
            cells.extend({'row':y,'column':x+i,'before':a,'after':b} for i,(a,b) in enumerate(zip(e['old'],e['new'])) if a!=b);reviewed_tokens+=1
        ordered=lambda values:sorted(values,key=lambda cell:(cell['row'],cell['column']))
        need(ordered(cells)==ordered(p['exact_meaningful_cell_changes']),'Declared page cells exactly token-derived '+p['page'])
        expected_cells[p['page']]=cells
        new=(b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+''.join(after).encode('utf-8')
        for f in m['files']:
            if f['target'] in [p['working_txt']['path'],p['repository_txt']['path']]:
                need(Path(f['candidate']['path']).read_bytes()==new,'Candidate TXT exactly reviewed cell edits '+p['page'])
                need([len(x) for x in new.decode('utf-8-sig').splitlines()]==[len(x) for x in raw.decode('utf-8-sig').splitlines()],'Grid geometry unchanged '+p['page'])
        if p['historical_columns']:binding(p['historical_columns'])
    # Build source truth from existing uniform exact-cell evidence; do not re-run parser.
    changed_ref_rows=0
    for r in truth:
        for ref in r['references']:
            match=[]
            for span in ref['source_spans']:
                for (scan,y,x),e in edits.items():
                    if scan==str(span.get('scan_id')) and y==span['row'] and span['column']<=x< span['column']+len(span['literal']) and ref['page']==e['old']:
                        match.append(e['new'])
            if match:
                need(len(set(match))==1,'Corrected source reference has unique successor')
                ref['page']=match[0];changed_ref_rows+=1
    by_site=defaultdict(list)
    for r in truth:
        for s in sockets(r['sockets']):by_site[(r['board'],s)].append(r)
    def witnesses(c):
        if not c.get('board') or not c.get('sockets'):return []
        out={r['id']:r for s in sockets(c['sockets']) for r in by_site.get((c['board'],s),[]) if not c.get('card_type') or r['card_type']==c['card_type']}
        return list(out.values())
    def page_witness(page,c):
        portions=c.get('printed_portions',c.get('portions',[]))
        if isinstance(c.get('portion'),str):portions=[c['portion']]
        return any(ref['page']==page and (not portions or set(portions)<=set(ref['portions'])) for r in witnesses(c) for ref in r['references'])
    def pin_witness(value,c):
        return any(p['ALD_reference']==value and (not c.get('pin') or p['pin']==c['pin']) for r in witnesses(c) for p in r['pin_references'])
    operations=0;moved=0
    for f in m['files']:
        binding(f['candidate'])
        if f['before']:
            binding(f['before']);need(Path(f['target']).is_file() and sha(f['target'])==f['before']['sha256'],'Live target unchanged '+f['target'])
        else:need(not Path(f['target']).exists(),'New proof target does not overwrite live file')
        if f['role']!='current active JSON mirror candidate':continue
        before=read(f['before']['path']);candidate=read(f['candidate']['path']);rebuilt=deepcopy(before)
        for op in f['changes']:
            operations+=1
            if op.get('operation')=='move_bucket_entries':
                buckets=pointer(rebuilt,op['bucket_path']);need(len(op['moved_entries'])==op['count'],'Bucket movement count')
                for entry in op['moved_entries']:
                    c=context(rebuilt,op['bucket_path']);c.update(context(entry,''))
                    good=page_witness(op['after_key'],c) if entry.get('kind')=='card portion' else pin_witness(entry.get('ALD_reference',''),c)
                    need(good,'Moved bucket entry has exact current-source physical witness')
                    need(entry in buckets[op['before_key']],'Moved bucket entry exists after declared leaf edits')
                    buckets[op['before_key']].remove(entry);buckets.setdefault(op['after_key'],[]).append(entry);moved+=1
                if not buckets[op['before_key']]:del buckets[op['before_key']]
            else:
                path=op['pointer'];need(pointer(rebuilt,path)==op['before'],'JSON leaf before value exact '+path)
                c=context(candidate,path.rsplit('/',1)[0]);field=path.rsplit('/',1)[1]
                need(field in ['ALD_page','ald_page','page','ALD_reference','text'],'Only active reference fields or positioned source text changed')
                if field=='text':
                    annotation=pointer(before,path.rsplit('/',1)[0]);page=Path(f['target']).stem.split()[0]
                    related=next(p for p in m['pages'] if p['page']==page);source_rows=Path(related['repository_txt']['path']).read_text(encoding='utf-8-sig').splitlines()
                    edges=[i for i,ch in enumerate(source_rows[annotation['row']]) if ch=='│'];lefts=[0]+[i+1 for i in edges];rights=edges+[len(source_rows[annotation['row']])]
                    slot=annotation['column']-1;left,right=lefts[slot],rights[slot]
                    matches=[e for e in related['reviewed_tokens'] if e['span']['row']==annotation['row'] and left<=e['span']['token_column']<right and e['span']['literal'].split()==op['before'].split()]
                    good=len(matches)==1 and op['after']==op['before'].replace(matches[0]['old'],matches[0]['new'],1)
                else:good=pin_witness(op['after'],c) if field=='ALD_reference' else page_witness(op['after'],c)
                need(good,'JSON leaf has exact current-source physical witness '+path)
                parent=pointer(rebuilt,path.rsplit('/',1)[0]);key=path.rsplit('/',1)[1].replace('~1','/').replace('~0','~');parent[int(key) if isinstance(parent,list) else key]=op['after']
        need(rebuilt==candidate,'JSON candidate equals declared active reference operations only '+f['target'])
    native=[];native_seen=set()
    for a in m['authority_records']:
        finding=a['finding']
        if finding.get('human_correction_binding'):binding(finding['human_correction_binding'])
        for c in finding.get('native_crops',[])+finding.get('crops',[]):
            crop=c.get('crop',c);source=c.get('source',crop.get('source'));rect=c.get('native_rect',c.get('rectangle',c.get('bounds',crop.get('bounds'))))
            if not source or not rect:continue
            key=(source['path'],crop['path'])
            if key in native_seen:continue
            native_seen.add(key);binding(source);binding(crop)
            with Image.open(source['path']) as original,Image.open(crop['path']) as image:
                pixelmatch=original.convert('RGB').crop(rect).tobytes()==image.convert('RGB').tobytes() and tuple(image.size)==(rect[2]-rect[0],rect[3]-rect[1])
                need(pixelmatch,'Native crop exact source pixels '+crop['path'])
            native.append({'source':source,'crop':crop,'rectangle':rect})
    need(reviewed_tokens==m['counts']['reviewed_tokens'] and operations==m['counts']['json_field_changes'],'Declared stage totals independently reproduced')
    need(sha(manifest)==original_manifest_sha,'Manifest epoch unchanged during independent review')
    holds=[{'old':'RF091','proposed':'RF081','reason':'Independent native crop inspection reads RF091 C1. Exact physical counterpart RF081 does not establish a transcription error; withhold pending human/source clarification.'}] if 'RF091' in m['reference_aliases'] else []
    report={'schema':'socket-reference-private-stage-independent-review-v1','created_utc':datetime.now(timezone.utc).isoformat(),'mechanical_checks_passed':not failures,'accepted_for_publication':False,'failures':failures,'visual_holds':holds,'checks':len(checks),'stage':{'path':str(manifest),'sha256':original_manifest_sha},'counts':{'reviewed_tokens':reviewed_tokens,'text_cells':sum(map(len,expected_cells.values())),'corrected_source_reference_rows':changed_ref_rows,'JSON_operations':operations,'bucket_entries_moved':moved,'native_crops_pixel_verified':len(native)},'historical_acceptance_changes':False,'canonical_changes_applied':False,'limits':['Initial source/data stage only; schema-aware acceptance/adapter publication metadata still require a separate frozen-stage review.','One native reading is held; other22 aliases mechanically eligible subject to final schema-aware source acceptance.'],'reviewer':{'path':str(Path(__file__)),'sha256':sha(__file__)}}
except Exception as exc:
    report={'mechanical_checks_passed':False,'accepted_for_publication':False,'exception':str(exc),'failures':failures,'checks':len(checks),'canonical_changes_applied':False}
(base/'Independent stage review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
