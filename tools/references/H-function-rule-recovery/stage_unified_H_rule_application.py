"""Stage a private, source-specific H/unknown-function application and contact sheets.

No canonical/repository writes or publisher are implemented. A separately frozen
unified inventory and independent review must precede any publication.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import argparse,copy,hashlib,importlib.util,json,sys
from PIL import Image,ImageChops,ImageDraw,ImageFont
sys.dont_write_bytecode=True
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=ROOT/'tmp/ald-text/ald/card-type-database';HERE=Path(__file__).resolve().parent
DB=BASE/'build-accepted-v11-derived112';AUTHORITY=HERE/'Direct human H function and port-count rules.json'
UNREADABLE=HERE/'Independent unreadable H exclusion review.json'
EXCEPTIONS=HERE/'Direct human three A exception confirmation.json'
HISTORY='source_derived_H_rule_function_recovery_v1'
SHARED=BASE/'prepare_non_ap_OR_corrections.py';spec=importlib.util.spec_from_file_location('shared_staging',SHARED);u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
def require(ok,message):
    if not ok:raise ValueError(message)
def checked(b):
    p=Path(b.get('path',b.get('file',''))).resolve();require(p.is_file()and u.sha(p)==b['sha256'],'Changed/missing input: '+str(p));return p
def port_reading(inputs,outputs):
    if inputs==1 and outputs==0:return 'R'
    if isinstance(inputs,int)and inputs>=2 and outputs==1:return 'A'
    return None
def replace_aliases(before,lines,fields):
    model=copy.deepcopy(before);changes={}
    def assign(pointer,old,new):
        pieces=pointer.strip('/').split('/');value=model
        for token in pieces[:-1]:value=value[int(token)]if isinstance(value,list)else value[token]
        last=int(pieces[-1])if isinstance(value,list)else pieces[-1];require(value[last]==old,'Alias changed while staging')
        if pointer in changes:
            require(changes[pointer]['after']==old,'Nonsequential alias');changes[pointer]['after']=new
        else:changes[pointer]={'json_pointer':pointer,'before':old,'after':new}
        value[last]=new
    for f in fields:
        ni=int(f['node_pointer'].split('/')[-1]);node=model['nodes'][ni];old=f['function_before'];new=f['function_after'];r,c=f['row'],f['column']
        require(old in {'H','�'}and new in {'A','R'}and before['nodes'][ni]['function']==old,'Unsupported exact function change')
        require(node['row']<r<node['row']+3 and node['column']<c<node['column']+node.get('width',8)-1,'Function is outside exact block header')
        require(lines[r][c]==old,'Exact printed function cell missing')
        for key in ('function','printed_function','function_text'):
            value=node.get(key)
            if isinstance(value,str)and value.strip(' ')==old:assign(f['node_pointer']+'/'+key,value,value.replace(old,new))
        layout=node.get('function_layout')
        if isinstance(layout,dict)and isinstance(layout.get('printed_function_literal'),str)and layout['printed_function_literal'].strip(' ')==old:
            value=layout['printed_function_literal'];assign(f['node_pointer']+'/function_layout/printed_function_literal',value,value.replace(old,new))
        for collection in ('printed_labels','labels'):
            for i,label in enumerate(model.get(collection,[])):
                if not isinstance(label,dict)or not isinstance(label.get('text'),str)or label.get('row')!=r or not isinstance(label.get('column'),int):continue
                lc=label['column'];text=label['text']
                if not lc<=c<lc+len(text):continue
                source_label=before[collection][i]['text'];require(lines[r][lc:lc+len(source_label)]==source_label and text[c-lc]==old,'Display alias not exact source/coordinate')
                chars=list(text);chars[c-lc]=new;assign('/'+collection+'/'+str(i)+'/text',text,''.join(chars))
    return model,list(changes.values())
def preview(lines,text):
    options=[text.with_name(text.stem+' preview.png'),text.with_suffix('.png'),text.with_name(text.stem+' JuliaMono preview.png'),text.with_name(text.stem+' JuliaMono.png')];matches=[]
    for path in options:
        if not path.exists():continue
        with Image.open(path)as image:
            config={'size':list(image.size),'font_size':20,'row_height':18,'x':(image.width-2940)//2,'y':(image.height-1854)//2}
            if list(image.size)==[2956,1870]:config['anchor']='lt'
            if ImageChops.difference(image.convert('RGB'),u.render(lines,config)).getbbox()is None:matches.append((path,config))
    require(len(matches)==1,'Exactly one accepted preview must reproduce current TXT: '+str(text));return matches[0]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--expected-inventory-sha256',required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    require(u.sha(AUTHORITY)=='32b2e29139fbf497a84fe7bbfb9367134400f313020a2d52b81db7c674cc0469','Wrong direct human rules')
    require(u.sha(UNREADABLE)=='6106b1a933eb9b8432f1329a97933dc4d4159eb9b34a97af3dd17009ce8a2449','Changed twelve-case approval')
    require(u.sha(args.inventory)==args.expected_inventory_sha256,'Wrong unified approval inventory');inventory=u.load(args.inventory)
    require(inventory['passed']is True and not inventory.get('failures'),'Unified inventory not accepted');require(checked(inventory['authority'])==AUTHORITY.resolve(),'Wrong authority')
    require(u.sha(EXCEPTIONS)=='e5898ee7c105d5f9c6fa5ace92f16bf349fbbc0aaf9754f2d7e3f6400d6cdd36','Wrong direct three-A exceptions');exception_answers=u.load(EXCEPTIONS)['answers']
    cases=inventory['cases'];require(len(cases)==64 and len({c['candidate_id']for c in cases})==64,'Only exact64-field scope allowed')
    require(sum(c['case_class']=='previously_ambiguous_unreadable_function'for c in cases)==12 and sum(c['case_class']=='standalone_H_function'for c in cases)==52,'Wrong class scope')
    proofs=[checked(b)for b in inventory['proof_inputs']];require(UNREADABLE.resolve()in proofs,'Missing frozen masked-function evidence')
    output=args.output.resolve();require(output.is_relative_to(HERE.resolve())and not output.exists(),'Choose new private output under H review folder')
    mp=DB/'notes/Card types/Build manifest.json';require(u.sha(mp)=='9adb260eebad41271a90cdbe41c5ea54f432fbf3d9aeb7be0ab36e7d63e6167a','Wrong V11 database')
    ixp=DB/'json/Card types/Card type index.json';index=u.load(ixp);build=u.load(mp);hashes={x['path']:x['sha256']for x in build['outputs']};require(u.sha(ixp)==hashes['json/Card types/Card type index.json'],'Stale V11 index')
    ep=REPO/'notes/Reviewed export provenance.json';cp=REPO/'notes/Content data manifest.json';entries={str(e['source_scan_id']):e for e in u.load(ep)['exported']};content={f['path'].replace('\\','/'):f for f in u.load(cp)['files']};cards={};groups=defaultdict(list)
    unreadable={c['candidate_id']:c for c in u.load(UNREADABLE)['cases']}
    for case in cases:
        t=case['target'];code=t['card_type'];rec=next(r for r in index['card_types']if r['card_type']==code)
        if code not in cards:require(u.sha(DB/rec['file'])==hashes[rec['file']],'Changed V11 observations');cards[code]=u.load(DB/rec['file'])['diagram_observations']
        obs=next(o for o in cards[code]if o['observation_id']==t['observation_id']);require(obs['function_literal']==case['function_before']and obs['JSON_pointer']==t['node_pointer']and str(obs['scan_id'])==str(t['scan_id']),'Wrong observation/node/source')
        require((obs['node_identifier'],obs['station'],obs['printed_card_portion_literal'],obs['unit_code_literal'],obs['location_literal'])==(t['node_identifier'],t['station'],t['printed_card_portion'],t['unit'],t['location']),'Wrong exact node/card/unit/socket identity')
        require(obs['literal_text_bindings']['function']==t['function_literal_bindings'],'Wrong V11 function coordinates')
        for key,sid in [('model_binding',obs['source_id']),('text_binding',obs['text_source_id'])]:require(checked(t[key])==(REPO/index['sources'][sid]['path']).resolve() and t[key]['sha256']==index['sources'][sid]['sha256'],'Wrong current accepted registry binding')
        entry=entries[str(t['scan_id'])];require(checked(t['canonical_text_binding'])==Path(entry['transcription_source']).resolve(),'Wrong canonical text path')
        model_record=content[index['sources'][obs['source_id']]['path']];require(checked(t['canonical_model_binding'])==Path(model_record['source']).resolve(),'Wrong canonical model path')
        native=index['sources'][index['pages'][str(t['scan_id'])]['original_source_id']];require(checked(t['original_source_binding'])==(Path('D:/Reference Materials/IBM 360/IBM_360_ALD')/native['path']).resolve() and t['original_source_binding']['sha256']==native['sha256'],'Wrong exact original scan')
        combo=obs['function_combination']['value'];inputs=combo['input']['exact_connected_count'];outputs=combo['output']['exact_connected_count']
        if case.get('direct_A_exception'):
            require(case['candidate_id']in {'H-n6e1a3a5416ca5674','H-n885c3b22f635a94d','H-nd6314e953086d382'}and inputs==outputs==1 and case['function_after']=='A','Unapproved exception/no invented second input')
            matches=[a for a in exception_answers if a['page']==t['page']and a['block']in {t['block'],t['node_identifier']}and a['card_portion']==t['printed_card_portion']and a['function']=='A'];require(len(matches)==1,'Exception not explicitly human confirmed');checked(case['direct_exception_authority'])
        else:require(port_reading(inputs,outputs)==case['function_after'],'Human port rule does not determine this reading')
        require(not combo['input']['connection_unknown_count']and not combo['output']['connection_unknown_count']and not obs['source_review_pending'],'Unknown connection/source finding')
        if case['case_class']=='previously_ambiguous_unreadable_function':require(case==unreadable[case['candidate_id']],'Masked case differs from exact frozen proof')
        else:require(case['function_before']=='H'and t['function_literal']=='H','Standalone H scope changed')
        require(t['function_literal']==case['function_before']and len(t['function_literal_bindings'])==1,'Ambiguous function span')
        b=t['function_literal_bindings'][0];require((case['row'],case['column'],case['function_before'])==(b['row'],b['column'],b['literal']),'Wrong source field coordinates')
        for key in ('model_binding','text_binding','canonical_model_binding','canonical_text_binding','original_source_binding'):checked(t[key])
        groups[str(t['scan_id'])].append(case)
    output.mkdir(parents=True);inputs=[AUTHORITY,EXCEPTIONS,UNREADABLE,args.inventory,mp,ixp,ep,cp,SHARED,u.FONT]+proofs
    protected={str(p.resolve()):u.binding(p)for p in inputs};app={'schema':'private-unified-H-rule-function-application-v1','created_utc':datetime.now(timezone.utc).isoformat(),'status':'PRIVATE; independent application review and explicit root release required before any canonical publication','authority':u.binding(AUTHORITY),'raw_authority_records':[u.binding(EXCEPTIONS)],'approved_inventory':u.binding(args.inventory),'protected_inputs':list(protected.values()),'snapshot_inputs':[u.freeze(p,output/'Immutable input receipts')for p in inputs if p.suffix=='.json'],'history_key':HISTORY,'pages':[],'held_cases':inventory.get('held_cases',[]),'contact_sheets':[],'preparation_helper':u.binding(Path(__file__))};panels=[]
    for scan,fields in groups.items():
        entry=entries[scan];t=fields[0]['target'];tp=checked(t['canonical_text_binding']);model_path=checked(t['canonical_model_binding']);require(u.sha(tp)==entry['text_sha256']==t['text_binding']['sha256'],'Accepted TXT epoch mismatch');require(u.sha(model_path)==t['model_binding']['sha256'],'Accepted JSON epoch mismatch')
        notes=tp.with_name(tp.stem+' review notes.txt');beforebytes=tp.read_bytes();raw=beforebytes.decode('utf-8');lines=raw.splitlines();rows=raw.splitlines(keepends=True);require(len(lines)==103 and all(len(s)<=245 for s in lines),'Unexpected page geometry');newlines=list(lines);pp,config=preview(lines,tp)
        source=checked(t['original_source_binding']);canonical={'txt':tp,'json':model_path,'notes':notes,'preview':pp};folder=output/(entry['page']+'-'+scan);before={k:u.freeze(p,folder/'before')for k,p in canonical.items()};source_guard=folder/'before/Original source hash guard.json';u.save(source_guard,{'source':u.binding(source),'storage':'Existing archive original is SHA-256-bound and rechecked; no TIFF duplicate was created','original_unchanged':True});model=u.load(model_path);changes=[];normalized=[]
        for case in fields:
            t=case['target'];r,c=case['row'],case['column'];old,new=case['function_before'],case['function_after'];require(newlines[r][c]==old,'Overlapping/stale exact function cell');newlines[r]=newlines[r][:c]+new+newlines[r][c+1:];change={'row':r,'column':c,'before':old,'after':new};changes.append(change)
            normalized.append({'candidate_id':case['candidate_id'],'case_class':case['case_class'],'node_pointer':t['node_pointer'],'node':t['node_identifier'],'printed_node_identifier':t['block'],'function_before':old,'function_after':new,'row':r,'column':c,'connected_inputs':case['connected_inputs'],'connected_outputs':case['connected_outputs'],'exact_meaningful_cell_changes':[change],'source_evidence':case})
        require(len({(c['row'],c['column'])for c in changes})==len(changes),'Overlapping target cells');updated,allowed=replace_aliases(model,lines,normalized);require(HISTORY not in model,'Same H-rule history already present')
        updated[HISTORY]={'authority':u.binding(AUTHORITY),'raw_authority_records':[u.binding(EXCEPTIONS)],'approved_inventory':u.binding(args.inventory),'source_sha256':u.sha(source),'fields':normalized,'scope':'Exact human H/port rules and three direct A exceptions applied only to independently approved H or unreadable function cells. All results remain marked as reconstructed and cannot become independent native witnesses.'}
        deltas=u.diff(model,updated);require(sorted([d for d in deltas if not d['json_pointer'].startswith('/'+HISTORY)],key=lambda x:x['json_pointer'])==sorted(allowed,key=lambda x:x['json_pointer']),'Extra model change')
        require(all(len(a)==len(z)for a,z in zip(lines,newlines)),'Line lengths changed');newraw=''.join(z+row[len(a):]for a,z,row in zip(lines,newlines,rows));restored=list(newraw.splitlines(keepends=True))
        for change in changes:r,c=change['row'],change['column'];restored[r]=restored[r][:c]+change['before']+restored[r][c+1:]
        require(''.join(restored).encode('utf-8')==beforebytes,'Unrelated bytes/endings changed')
        candidates={k:folder/'candidate'/path.name for k,path in canonical.items()};candidates['txt'].parent.mkdir(parents=True);candidates['txt'].write_bytes(newraw.encode('utf-8'));u.save(candidates['json'],updated)
        note=notes.read_bytes().decode('utf-8');nl='\r\n'if'\r\n'in note else'\n';candidates['notes'].write_bytes((note+nl+'Human H/function port-count rule recoveries: '+', '.join(f['candidate_id']for f in normalized)+'. Exact source/cell and independent evidence retained in the private application receipt.'+nl).encode('utf-8'));afterimage=u.render(newlines,config);afterimage.save(candidates['preview'])
        prior=ROOT/entry['review_record'];require(prior.is_file(),'Current accepted predecessor must be an immutable file for this scope');priorbinding=u.freeze(prior,folder/'before/Immutable predecessor')
        app['pages'].append({'page':entry['page'],'source_scan_id':scan,'source':u.binding(source),'immutable_original_source_guard':u.binding(source_guard),'canonical_quartet':{k:u.binding(p)for k,p in canonical.items()},'before_quartet':before,'candidate_quartet':{k:u.binding(p)for k,p in candidates.items()},'prior_review_record':priorbinding,'function_fields':normalized,'exact_meaningful_cell_changes':changes,'allowed_active_semantic_changes':allowed,'metadata_changes':[d for d in deltas if d['json_pointer'].startswith('/'+HISTORY)],'render_config':config,'line_lengths_before':[len(s)for s in lines],'line_endings_preserved':True,'trailing_space_padding':0})
        beforeimage=u.render(lines,config)
        for f in normalized:
            node=model['nodes'][int(f['node_pointer'].split('/')[-1])];x=config['x']+node['column']*12;y=config['y']+node['row']*18;box=(max(0,x-60),max(0,y-25),min(afterimage.width,x+170),min(afterimage.height,y+155));panels.append((f,beforeimage.crop(box),afterimage.crop(box)))
    font=ImageFont.truetype(str(u.FONT),15)
    for start in range(0,len(panels),8):
        selected=panels[start:start+8];sheet=Image.new('RGB',(700,len(selected)*225),'white');draw=ImageDraw.Draw(sheet)
        for i,(f,b,a)in enumerate(selected):
            y=i*225;draw.text((8,y+2),f["source_evidence"]["target"]["page"]+' '+f['printed_node_identifier']+' '+f['function_before']+' -> '+f['function_after']+' '+f['candidate_id'],font=font,fill='black');sheet.paste(b,(8,y+32));sheet.paste(a,(350,y+32))
        path=output/'Contact sheets'/('Before after '+str(start//8+1)+'.png');path.parent.mkdir(exist_ok=True);sheet.save(path);app['contact_sheets'].append({'image':u.binding(path),'candidate_ids':[f['candidate_id']for f,_,_ in selected]})
    for b in protected.values():checked(b)
    for page in app['pages']:
        checked(page['source'])
        for b in page['canonical_quartet'].values():checked(b)
    app['counts']={'pages':len(groups),'functions':len(cases),'standalone_H':52,'unreadable':12,'direct_A_exceptions':3,'changed_cells':sum(len(p['exact_meaningful_cell_changes'])for p in app['pages'])};dest=output/'Private unified H rule application manifest.json';u.save(dest,app);print(json.dumps({'manifest':u.binding(dest),'counts':app['counts'],'canonical_writes':0,'repository_writes':0}))
if __name__=='__main__':main()
