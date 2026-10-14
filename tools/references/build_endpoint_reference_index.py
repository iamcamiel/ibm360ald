"""Build a literal current ALD endpoint index and exact A1 reference matcher.

Only accepted export TXT and manifest-bound current repository models are read.
No source, canonical, workbook, old manifest, or repository writes are made.
Socket trailing T/B aliases affect only the socket field; full units and pins
remain exact. Bare unit expansions require the explicit human receipt rules.
"""
import argparse,csv,hashlib,json,re,shutil
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ENDPOINT=re.compile(r'(?<![A-Z0-9�])(?P<prefix>(?:[0-9A-Z�]{2})?[A-Z�])-(?P<gate>[A-Z�][0-9�])(?P<socket>[A-Z�][0-9�]{1,2}(?:[TB�])?)(?P<pin>[A-Z�][A-Z0-9�]{2})(?![A-Z0-9�])')
CODE=re.compile(r'(?<![A-Z0-9�])(?:[A-Z�]{2}[0-9�]{3}(?:-[0-9�]{2})?)?[A-Z�]{1,3}[0-9�]{1,2}(?![A-Z0-9�])')
FULL_REF=re.compile(r'^[A-Z]{2}[0-9]{3}(?:-[0-9]{2})?[A-Z]{1,3}[0-9]{1,2}$')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
_hash_cache={}
def digest(p):
    p=Path(p);s=p.stat();key=(str(p),s.st_size,s.st_mtime_ns)
    if key not in _hash_cache:_hash_cache[key]=hashlib.sha256(p.read_bytes()).hexdigest()
    return _hash_cache[key]
def binding(p):return {'path':str(p),'sha256':digest(p)}
def repo_binding(p,repo):return {'path':Path(p).relative_to(repo).as_posix(),'sha256':digest(p)}
def normalize_socket(socket):return re.sub(r'(?<=[0-9])[TB]$','',socket)
def mask_compatible(fragment,value):return len(fragment)==len(value)and all(a=='�'or a==b for a,b in zip(fragment,value))
def masks_overlap(a,b):return len(a)==len(b)and all(x==y or x=='�'or y=='�'for x,y in zip(a,b))
def socket_masks_overlap(a,b):
    # A damaged terminal socket suffix can represent the authorized T/B alias.
    # It remains unreadable, so this only adds ambiguity and never a High mate.
    return masks_overlap(a,b)or(a.endswith('�')and masks_overlap(a[:-1],b))or(b.endswith('�')and masks_overlap(a,b[:-1]))
def parse_endpoint(token,human_units):
    mt=ENDPOINT.fullmatch(token)
    if not mt:return None
    d=mt.groupdict();prefix=d['prefix'];d.update(raw_endpoint=token,raw_board=prefix+'-'+d['gate'],socket_normalized=normalize_socket(d['socket']),socket_alias_removed=d['socket']!=normalize_socket(d['socket']))
    if len(prefix)==3 and prefix[:2].isdigit()and'�'not in prefix:
        d.update(unit=prefix[:2],board=prefix+'-'+d['gate'],unit_resolution='literal_full_unit',unit_rule_receipt=None)
    elif len(prefix)==1 and prefix in human_units:
        d.update(unit='02',board='02'+prefix+'-'+d['gate'],unit_resolution='direct_human_abbreviation',unit_rule_receipt=human_units[prefix])
    else:d.update(unit=None,board=None,unit_resolution='unresolved_unlisted_or_damaged_prefix',unit_rule_receipt=None)
    d['fully_readable']=d['board']is not None and'�'not in d['board']+d['socket']+d['pin']and bool(re.fullmatch(r'[A-Z][0-9]{2}',d['pin']))
    return d
def page_identity(page,lines):
    found=[]
    for r,l in enumerate(lines):
        if(page in l)and(r<3 or r>=len(lines)-10):found.append({'row':r,'column':l.index(page),'excerpt':page,'kind':'literal_horizontal_page_identifier'})
    if not found:
        for c in [1,2,max(map(len,lines))-2,max(map(len,lines))-3]:
            chars=''.join(l[c]if c<len(l)else' 'for l in lines[-10:]).replace(' ','')
            if page in chars:found.append({'rows':[len(lines)-10,len(lines)-1],'column':c,'excerpt':chars,'kind':'literal_vertical_page_identifier'})
    return found
def heading_support(code,model,lines,start):
    if FULL_REF.fullmatch(code or''):return {'supported':True,'kind':'literal_full_ALD_reference'}
    if not code or'�'in code:return {'supported':False,'kind':'unreadable_heading'}
    variants={code,re.sub(r'[0-9]{1,2}$','',code),code[:-1]}
    proof=[]
    for v in variants:
        if not v:continue
        pattern=re.compile(r'\b[0-9]+[A-Z][─-]{1,}'+re.escape(v)+r'(?![A-Z0-9])')
        for r,line in enumerate(lines[:start]):
            for mt in pattern.finditer(line):proof.append({'row':r,'column':mt.start(),'excerpt':mt.group()})
    nodes=(model or{}).get('nodes',[]);nodes=nodes.values()if isinstance(nodes,dict)else nodes
    ids={str(n.get('printed_id',n.get('id','')))for n in nodes if isinstance(n,dict)}
    known=sorted(variants&ids)
    return {'supported':bool(proof or known),'kind':'printed_body_node_or_reference_context'if proof or known else'unsupported_nearby_token','literal_body_proof':proof,'accepted_model_node_ids':known}
def footer_headers(lines,start,model=None):
    headers=[]
    for r in range(start,len(lines)):
        previous_end=0
        for end in ENDPOINT.finditer(lines[r]):
            left=lines[r][previous_end:end.start()];matches=list(CODE.finditer(left))
            if matches:
                code=matches[-1];after=left[code.end():]
                if not after.strip():headers.append({'row':r,'column':previous_end+code.start(),'raw_code':code.group(),'endpoint_column':end.start(),'excerpt':lines[r],'support':heading_support(code.group(),model,lines,start)})
            previous_end=end.end()
        # A separate heading row is a boundary even without its first endpoint.
        stripped=lines[r].strip()
        if CODE.fullmatch(stripped):
            headers.append({'row':r,'column':lines[r].index(stripped),'raw_code':stripped,'endpoint_column':None,'excerpt':lines[r],'support':heading_support(stripped,model,lines,start)})
    for x in(model or{}).get('printed_labels',[]):
        if isinstance(x,dict)and x.get('row',-1)>=start and CODE.fullmatch(x.get('text','').strip()):
            r=x['row'];original_column=x.get('column');label=x['text']
            if not isinstance(original_column,int)or r>=len(lines)or lines[r][original_column:original_column+len(label)]!=label:continue
            code=label.strip();c=original_column+len(label)-len(label.lstrip())
            if not any(h['row']==r and h['column']==c for h in headers):headers.append({'row':r,'column':c,'raw_code':code,'endpoint_column':None,'excerpt':lines[r],'support':heading_support(code,model,lines,start)})
    anchors=[]
    modelcolumns=set()
    for x in(model or{}).get('printed_labels',[]):
        if isinstance(x,dict)and isinstance(x.get('row'),int)and x['row']>=start and ENDPOINT.search(x.get('text','')):
            r=x['row'];c=x.get('column');s=x['text']
            if isinstance(c,int)and lines[r][c:c+len(s)]==s:modelcolumns.add(c)
    for c in sorted({x['column']for x in headers}|modelcolumns):
        if not anchors or c-anchors[-1][-1]>4:anchors.append([c])
        else:anchors[-1].append(c)
    for h in headers:h['table_column']=next(min(a)for a in anchors if h['column']in a)
    return headers,[min(a)for a in anchors]
def extract_entries(page,sid,lines,models,human_units,bound):
    start=max(0,len(lines)-13);headers,anchors=footer_headers(lines,start,models);carry={};entries=[];idproof=page_identity(page,lines)
    frame=[{'row':r,'column':mt.start(1),'literal':mt.group(1),'excerpt':lines[r]}for r in range(start,len(lines))for mt in re.finditer(r'\bFRAME\s*([0-9�]{2})(?![0-9])',lines[r])]
    for r,line in enumerate(lines):
        hs=[h for h in headers if h['row']==r]
        for h in hs:carry[h['table_column']]=h
        for mt in ENDPOINT.finditer(line):
            d=parse_endpoint(mt.group(),human_units);govern=None;method=None;column=None
            if r>=start:
                viable=[a for a in anchors if a<=mt.start()+3]
                if viable:
                    column=max(viable);govern=carry.get(column);method='literal_same_line_header'if govern and govern['row']==r else'printed_footer_column_continuation'if govern else'unresolved_footer_column_without_prior_header'
                    # Column positions alone do not establish reading order.
                    # Retain a possible wrap as an explicitly ineligible inference.
                    if not govern and models and anchors.index(column)>0:
                        priorcols=anchors[:anchors.index(column)]
                        previous=[h for h in headers if h['table_column']in priorcols]
                        if previous:
                            prior=max(previous,key=lambda h:(h['table_column'],h['row']));govern=prior;method='inferred_footer_column_wrap'
                else:method='unresolved_footer_endpoint_without_header_column'
            else:
                left=line[:mt.start()];codes=list(CODE.finditer(left));g=codes[-1]if codes else None
                if g and not left[g.end():].strip()and FULL_REF.fullmatch(g.group()):govern={'row':r,'column':g.start(),'raw_code':g.group(),'excerpt':line,'support':{'supported':True,'kind':'literal_full_ALD_reference'}};method='literal_inline_full_reference'
                else:method='unresolved_inline_endpoint_without_full_reference'
            rawcode=govern['raw_code']if govern else None;fullref=(rawcode if FULL_REF.fullmatch(rawcode or'')else page+rawcode if rawcode and re.fullmatch(r'[A-Z]{1,3}[0-9]{1,2}',rawcode)and idproof else None)
            pointer=[]
            for key in ['printed_labels','connector_table','footer']:
                obj=(models or{}).get(key,[])
                if isinstance(obj,list):
                    for i,x in enumerate(obj):
                        if isinstance(x,dict)and x.get('row')==r and mt.group()in json.dumps(x,ensure_ascii=False):pointer.append('/'+key+'/'+str(i))
            rawparts=d.copy();d.update(id=sid+':'+str(r)+':'+str(mt.start()),page=page,source_scan_id=sid,row=r,column=mt.start(),raw_token=mt.group(),full_row=line,region='footer_table'if r>=start else'inline_or_body',table_column=column,governing_raw_code=rawcode,governing_full_reference=fullref,governance_method=method,governing_header=govern,printed_page_identity=idproof,printed_frame_evidence=frame,model_pointers=pointer,binding=bound)
            d['governing_source_support']=bool(govern and govern.get('support',{}).get('supported'))
            d['governing_reference_pattern']=rawcode if FULL_REF.fullmatch(rawcode or'')else page+rawcode if rawcode and idproof else None
            d['eligible_exact_match']=bool(d['fully_readable']and fullref and govern and d['governing_source_support']and'�'not in rawcode and(method in ['literal_same_line_header','printed_footer_column_continuation','literal_inline_full_reference']))
            entries.append(d)
    return entries
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path);parser.add_argument('--repo','--repository-root',dest='repo',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--export-manifest',type=Path);parser.add_argument('--issued-manifest',type=Path);parser.add_argument('--pending-overlay',type=Path);parser.add_argument('--authority-dir',type=Path);args=parser.parse_args()
    script=Path(__file__).resolve();private=script.parent.name=='endpoint-reference-index-v1';defaultrepo=script.parents[5]/'ibm360ald'if private else script.parents[2];repo=(args.repo or defaultrepo).resolve();root=(args.workspace or repo.parent).resolve();out=(args.output or(script.parent if private else Path.cwd()/'endpoint-reference-index-v1')).resolve();out.mkdir(parents=True,exist_ok=True)
    def current_input(explicit,portable,workspace):return explicit or(portable if portable.is_file()else workspace)
    export=current_input(args.export_manifest,repo/'notes/Reviewed export provenance.json',root/'tmp/ald-text/ald/repository-export/last export manifest.json');records=repo/'notes/Repository records manifest.json';content=repo/'notes/Content data manifest.json';issued=current_input(args.issued_manifest,repo/'notes/Manual verification/Workbook binding manifest v4.json',root/'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v4.json');overlay=current_input(args.pending_overlay,repo/'notes/Manual verification/Pending inventory after V4.json',root/'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/Pending inventory after V4.json');catalogue=repo/'notes/ALD Scan Order.csv'
    authorities=args.authority_dir or(out if(out/'Direct human bare A endpoint instruction.json').is_file()else repo/'notes/A1 Socket Listing/Endpoint reference index')
    authorityfiles=[authorities/'Direct human socket matching instruction.json',authorities/'Direct human bare A endpoint instruction.json',authorities/'Direct human abbreviated endpoint units instruction.json'];assert all(p.is_file()for p in authorityfiles),'Direct human abbreviation receipts are required'
    units={x:'direct_human_bare_A_to_02A'if x=='A'else'direct_human_bare_B_C_E_K_L_to_02_units'for x in ['A','B','C','E','K','L']};ex=read(export);assert not ex.get('export_in_progress')and ex['bytewise_copy_verified']and len(ex['exported'])==2307
    rm=read(records);owned={p['path'].replace('\\','/'):p['sha256']for p in rm['files']};cm=read(content);modelindex={p['path'].replace('\\','/'):p for p in cm['files']};inputs=[binding(p)for p in [export,records,content,issued,overlay,catalogue,*authorityfiles]]
    all_entries=[];pages=[];page_by_scan={};models_by_scan={};lines_by_scan={}
    for e in ex['exported']:
        basename=e['destination'].replace('\\','/').rsplit('/',1)[-1];folder=e['source_relative'].replace('\\','/').rsplit('/',1)[0];rel='ALD/'+folder+'/'+basename;tp=repo/rel;assert digest(tp)==e['text_sha256']==owned[rel],rel
        modelrel='json/'+str(Path(rel).relative_to('ALD').with_suffix('.json')).replace('\\','/');mp=repo/modelrel;model=None;mb=None
        if mp.is_file():
            assert modelrel in modelindex and digest(mp)==modelindex[modelrel]['sha256']==owned[modelrel],modelrel;model=read(mp);mb=repo_binding(mp,repo)
        sid=str(e['source_scan_id']);lines=tp.read_text(encoding='utf-8').splitlines();bound={'text':repo_binding(tp,repo),'model':mb,'source_relative':e['source_relative'],'original_scan_name':e.get('original_scan_name'),'accepted_export_record':e['review_record']}
        entries=extract_entries(e['page'],sid,lines,model,units,bound);all_entries.extend(entries);pages.append({'page':e['page'],'source_scan_id':sid,'binding':bound,'endpoint_count':len(entries),'model_status':'Current separately published model'if mb else'No separately published page model; literal accepted TXT is authority'});page_by_scan[sid]=e;models_by_scan[sid]=model;lines_by_scan[sid]=lines
    # Prefer independently literal full-unit proof when the same governed endpoint
    # exists in both full and abbreviated form; never merge different unit values.
    by_physical=defaultdict(list)
    for d in all_entries:
        if d['board']:by_physical[(d['board'],d['socket_normalized'],d['pin'])].append(d)
    v4=read(issued);ov=read(overlay);closed={q['id']for q in ov['source_derived_resolutions']};issued_ids={q['id']for q in v4['questions']};assert closed<=issued_ids,'Overlay contains IDs absent from the issued manifest'
    issued_a1=[q for q in v4['questions']if q['group']=='A1'];a1=[q for q in issued_a1 if q['id']not in closed];matches=[]
    for q in a1:
        sid=str(q['source_scan_id']);lines=lines_by_scan[sid];row=q['row'];col=q['column'];assert lines[row][col:col+len(q['current_reading'])]==q['current_reading'];ref=q['current_reading'];pc=q.get('physical_context',{});board=pc.get('board');socket=pc.get('socket');pin=pc.get('pin');connector=pc.get('connector');targetline=lines[row];left=targetline[:col];segment=left.split('│')[-1]
        # Verify the target physical key using literal current A1 body/footer.
        boardproof=[{'row':r,'column':m.start(1),'excerpt':lines[r],'literal':m.group(1)}for r,l in enumerate(lines)for m in re.finditer(r'\bBOARD\s*([0-9]{2}[A-Z]-[A-Z][0-9])',l)]
        if not board:
            vals={x['literal']for x in boardproof};board=next(iter(vals))if len(vals)==1 else None
        pairs=list(re.finditer(r'\b([A-Z][0-9]{1,2}[TB]?)\s+([A-Z][0-9]{2})\s*$',segment))
        literalpair=pairs[-1]if pairs else None
        if literalpair:
            printed_connector,printed_pin=literalpair.groups()
            if not pin:pin=printed_pin
            if not socket:socket=printed_connector
            connector=printed_connector
        chosen=connector or socket;target_key_clear=bool(board and chosen and pin and'�'not in board+chosen+pin and any(x['literal']==board for x in boardproof)and literalpair and printed_pin==pin and normalize_socket(printed_connector)==normalize_socket(chosen))
        field_supported=bool(re.match(r'^[A-Z�]{2}[0-9�]{3}(?:-[0-9�]{2})?[A-Z�]{1,3}[0-9�]{1,2}$',ref))
        candidates=by_physical.get((board,normalize_socket(chosen or''),pin),[])[:]if target_key_clear and field_supported else[]
        # Wildcard-damaged endpoint components remain plausible competitors.
        # Fully explicit different units/boards/pins are never collapsed.
        if target_key_clear and field_supported:
            target_prefix,target_gate=board.split('-')
            for d in all_entries:
                if d in candidates or d['fully_readable']:continue
                pref=d['board'].split('-')[0]if d['board']else d['prefix'];pref_target=target_prefix if len(pref)==3 else target_prefix[-1]
                if masks_overlap(pref,pref_target)and masks_overlap(d['gate'],target_gate)and socket_masks_overlap(d['socket_normalized'],normalize_socket(chosen))and masks_overlap(d['pin'],pin):candidates.append(d)
        # Keep all alias fan-out before applying the damaged reference mask.
        compatible=[d for d in candidates if d['governing_full_reference']and mask_compatible(ref,d['governing_full_reference'])]
        competing=[]
        for d in candidates:
            if d['eligible_exact_match']:continue
            pattern=d.get('governing_reference_pattern')
            if pattern and masks_overlap(pattern,ref):competing.append(d)
            elif not pattern and mask_compatible(ref[:len(d['page'])],d['page']):competing.append(d)
            elif d['governing_full_reference']and mask_compatible(ref,d['governing_full_reference']):competing.append(d)
        eligible_values=sorted({d['governing_full_reference']for d in compatible if d['eligible_exact_match']});values=sorted({d['governing_full_reference']for d in compatible});status='High'if len(eligible_values)==1 and not competing else'Tentative'if compatible or competing else'Unresolved'
        if not field_supported:status='Outside endpoint matcher scope'
        r={'id':q['id'],'page':q['page'],'source_scan_id':sid,'current_reading':ref,'covered_cells':q['covered_cells'],'original_issued_question':q,'target':{'board':board,'socket_raw':socket,'connector_raw':connector,'physical_socket_used':chosen,'socket_normalized':normalize_socket(chosen or''),'pin':pin,'literal_row':row,'literal_column':col,'literal_body_row':targetline,'board_proof':boardproof,'exact_physical_key_verified':target_key_clear,'current_text_binding':pages[[p['source_scan_id']for p in pages].index(sid)]['binding']['text']},'all_physical_alias_endpoint_ids':[d['id']for d in candidates],'compatible_endpoint_ids':[d['id']for d in compatible],'candidate_values':values,'candidate':values[0]if len(values)==1 else'','confidence':status,'basis':'Unique independently readable governing reference and exact board/socket/pin; only authorized bare-unit/socket-suffix normalization applied.'if status=='High'else'Multiple compatible references remain; no alias is suppressed.'if status=='Tentative'else'Portion/card/function fields are not endpoint-reference questions.'if not field_supported else'No independently readable compatible complete physical mate currently indexed.','evidence':compatible,'Answer':'','issued_V4_changed':False,'known_human_answers_preserved':True}
        r['competing_unresolved_observation_ids']=[d['id']for d in competing]
        r['eligible_candidate_values']=eligible_values
        if competing:r['basis']='Plausible same-physical-key observations have unresolved, damaged or unsupported governing headings; preserve all observation IDs and alternatives before claiming uniqueness.'
        matches.append(r)
    example=next((q for q in matches if q['id']=='A1154-01-9d72e8e1d9'),None)
    if example:assert example['confidence']=='High'and example['candidate']=='LS051AC4',example['target']
    counts={'accepted_scans':len(pages),'literal_endpoints':len(all_entries),'pages_with_endpoints':sum(bool(p['endpoint_count'])for p in pages),'eligible_exact_reference_endpoints':sum(d['eligible_exact_match']for d in all_entries),'unresolved_governing_reference':sum(d['governing_full_reference']is None for d in all_entries),'unit_resolution':dict(Counter(d['unit_resolution']for d in all_entries)),'A1_issued_questions':len(issued_a1),'already_closed_ids_excluded':sum(q['id']in closed for q in issued_a1),'remaining_A1_questions_examined':len(matches),'match_confidence':dict(Counter(q['confidence']for q in matches))}
    common={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'Private current repository inventory and candidate matches; not canonical/source/workbook publication','counts':counts,'inputs':inputs,'normalization_policy':{'bare_units':{u:'02'+u for u in units},'bare_unit_authority':authorityfiles,'socket_terminal_suffixes_ignored':['T','B'],'socket_suffix_rule':'Remove only a final T/B immediately after the socket digits. Do not touch pin B05 or board/unit spelling.','distinct_full_units_preserved':True,'unlisted_or_damaged_unit_prefixes_unresolved':True,'all_alias_candidates_retained_before_reference_mask':True}}
    common['normalization_policy']['bare_unit_authority']=[str(p)for p in authorityfiles]
    ip=out/'Endpoint inventory.json';mp=out/'A1 endpoint matching results.json';meta=out/'Endpoint tool metadata.json'
    # Page bindings, repeated grid rows and header proof are stored exactly once.
    # Endpoint IDs and scan IDs connect compact records to their literal evidence.
    compact_pages={p['source_scan_id']:dict(p)for p in pages};compact_entries=[]
    for d in all_entries:
        p=compact_pages[d['source_scan_id']];p.setdefault('literal_rows',{})[str(d['row'])]=d['full_row'];p['printed_page_identity']=d['printed_page_identity'];p['printed_frame_evidence']=d['printed_frame_evidence']
        h=d['governing_header'];hid=None
        if h:
            hid=str(h['row'])+':'+str(h['column'])
            p.setdefault('governing_headers',{})[hid]=h
            p['literal_rows'][str(h['row'])]=h['excerpt']
        cd={k:v for k,v in d.items()if k not in ['binding','full_row','printed_page_identity','printed_frame_evidence','governing_header']}
        cd['literal_row_evidence']=str(d['row']);cd['governing_header_id']=hid;compact_entries.append(cd)
    compact_by_id={d['id']:d for d in compact_entries}
    for m in matches:m['evidence']=[compact_by_id[d['id']]for d in m['evidence']]
    common['normalization_policy']['rule_receipts']={'direct_human_bare_A_to_02A':binding(authorityfiles[1]),'direct_human_bare_B_C_E_K_L_to_02_units':binding(authorityfiles[2]),'direct_human_socket_terminal_T_B_alias':binding(authorityfiles[0])}
    ip.write_text(json.dumps({**common,'schema_version':2,'pages':compact_pages,'endpoints':compact_entries},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');mp.write_text(json.dumps({**common,'schema_version':2,'endpoint_inventory':{'path':ip.name,'sha256':digest(ip)},'excluded_already_resolved_ids':sorted(closed),'results':matches},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cp=out/'Endpoint inventory.csv';fields=['id','page','source_scan_id','region','row','column','raw_endpoint','raw_board','board','unit_resolution','socket','socket_normalized','pin','governing_raw_code','governing_full_reference','governance_method','eligible_exact_match','text_path','text_sha256','model_path','model_sha256','full_row']
    with cp.open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in all_entries:
            x={k:d.get(k)for k in fields};x.update(text_path=d['binding']['text']['path'],text_sha256=d['binding']['text']['sha256'],model_path=d['binding']['model']['path']if d['binding']['model']else'',model_sha256=d['binding']['model']['sha256']if d['binding']['model']else'');w.writerow(x)
    for p in inputs:assert digest(p['path'])==p['sha256'],f'Input changed during inventory: {p["path"]}'
    frozen=out/'Initial input snapshots';frozen.mkdir(exist_ok=True);snapshots=[]
    for name,original in [('Pending inventory before endpoint index.json',overlay),('Reviewed export provenance.json',export),('Repository records manifest.json',records),('Content data manifest.json',content),('Workbook binding manifest v4.json',issued)]:
        dest=frozen/name
        if not dest.exists():shutil.copyfile(original,dest)
        snapshots.append({'original':binding(original),'frozen':binding(dest)})
    metadata={**common,'builder':binding(Path(__file__)),'outputs':[binding(ip),binding(cp),binding(mp)],'initial_input_snapshots':snapshots,'schema_version':2,'coordinates':'zero-based current TXT character grid','scope':'All literal complete physical endpoint tokens from verified current repository TXT; safe governing footer headers/column continuations and explicit full inline references. No node-port ordinal inference or stale accepted-reference index.','compact_provenance':'pages is keyed by source_scan_id; each endpoint links to literal_rows by literal_row_evidence and governing_headers by governing_header_id. Original accepted export/scan provenance remains once per page. Human receipts are once per rule.','portable_cli':'python build_endpoint_reference_index.py --repository-root PATH --export-manifest PATH/notes/Reviewed export provenance.json --issued-manifest PATH/notes/Manual verification/Workbook binding manifest v4.json --pending-overlay PATH/notes/Manual verification/Pending inventory after V4.json --authority-dir PATH/notes/A1 Socket Listing/Endpoint reference index --output OUTPUT','no_publication':True};meta.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':counts,'outputs':[binding(ip),binding(cp),binding(mp),binding(meta)],'matches':[{k:q[k]for k in ['id','current_reading','candidate','confidence']}for q in matches]},indent=2))
if __name__=='__main__':main()
