"""Independent native table-literal stage review; source files are read only.

Supply a frozen stage/hash and a separately reviewed native proposal set.
Only the new private acceptance receipt is written.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,hashlib
from PIL import Image,ImageDraw,ImageFont

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def pointer(doc,p):
    for key in p.strip('/').split('/'):
        key=key.replace('~1','/').replace('~0','~')
        doc=doc[int(key)] if isinstance(doc,list) else doc[key]
    return doc
def setpointer(doc,p,value):
    parent,key=p.rsplit('/',1);item=pointer(doc,parent)
    item[int(key) if isinstance(item,list) else key]=value
def physical(value):
    value=str(value)
    return value[:-1] if len(value)>1 and value[-1] in 'BT' and value[-2].isdigit() else value

def main():
    ap=argparse.ArgumentParser();ap.add_argument('manifest',type=Path);ap.add_argument('expected_sha256');ap.add_argument('native_proposals',type=Path);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    checks=0;epochs={}
    def need(ok,why):
        nonlocal checks
        checks+=1
        if not ok:raise AssertionError(why)
    def checked(link):
        p=Path(link['path']).resolve();need(p.is_file() and sha(p)==link['sha256'],'Exact binding '+str(p));epochs[p]=link['sha256'];return p
    def diff(a,b,p=''):
        if type(a)!=type(b):return [(p,a,b)]
        if isinstance(a,dict):
            need(a.keys()==b.keys(),'JSON key topology unchanged '+p)
            return [r for k in a for r in diff(a[k],b[k],p+'/'+k.replace('~','~0').replace('/','~1'))]
        if isinstance(a,list):
            need(len(a)==len(b),'JSON array topology unchanged '+p)
            return [r for i,(x,y) in enumerate(zip(a,b)) for r in diff(x,y,p+'/'+str(i))]
        return [] if a==b else [(p,a,b)]
    need(not args.output.exists(),'Do not overwrite prior review')
    need(sha(args.manifest)==args.expected_sha256,'Frozen exact stage')
    m=read(args.manifest);epochs[args.manifest.resolve()]=args.expected_sha256
    need(m['schema']=='socket-table-literal-correction-private-stage-v1' and m['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1','Honest table schema')
    need(m['published'] is False and m['independent_acceptance_required'] is True,'Private pending stage')
    proposal_binding=bind(args.native_proposals);epochs[args.native_proposals.resolve()]=proposal_binding['sha256']
    proposals=[p for p in read(args.native_proposals)['pages'] if Path(p['text_preimage']['path']).stem==Path(m['files'][0]['target']).stem]
    need(bool(proposals),'Separate reviewed native proposal set for exact page')
    for key in ['source','human_authority','predecessor_acceptance','historical_repository_acceptance','historical_repository_original','font','preparation_script','predecessor_adapter','registry_predecessor','registration_helper']:checked(m[key])
    for link in m['metadata_preimages']:checked(link)
    authority=read(m['human_authority']['path'])
    need(set(authority['selected_records'])=={p['record_id'] for p in proposals},'Exact reviewed physical records')
    for link in authority.values():
        if isinstance(link,dict) and 'path' in link and 'sha256' in link:checked(link)
    allowed_cells=[];sites={};part_rules={};model_changes=[];native_proofs=[]
    for p in proposals:
        need(p['source']==m['source'] and p['board']==m['board'],'Same native source and board')
        checked(p['source']);crop=checked(p['native_crop'])
        for link in p.get('evidence',[]):checked(link)
        with Image.open(p['source']['path']) as im,Image.open(crop) as tile:
            pixels=im.crop(p['native_crop']['box']).convert('RGB')
            need(pixels.size==tile.size and pixels.tobytes()==tile.convert('RGB').tobytes(),'Pixel-exact native occurrence '+p['record_id'])
        for edit in p['text_edits']:
            need(len(edit['before'])==len(edit['after']),'Equal-width proposal text')
            allowed_cells += [dict(row=edit['row'],column=edit['column']+i,before=a,after=b) for i,(a,b) in enumerate(zip(edit['before'],edit['after'])) if a!=b]
        changes={patch['pointer'].rsplit('/',1)[-1]:(patch['before'],patch['after']) for patch in p['json_patches']}
        need(set(changes)=={'part_number','card_type'},'Only reviewed card identity axes')
        sites[tuple(sorted(map(physical,p['sockets'])))]=changes
        part_rules.update({a:b for a,b in changes.values()});model_changes+=p['json_patches']
        native_proofs.append(dict(record_id=p['record_id'],source=p['source'],native_crop=p['native_crop'],literal_native_reading=p['literal_native_reading']))
    need(sorted(m['exact_meaningful_cell_changes'],key=lambda c:(c['row'],c['column']))==sorted(allowed_cells,key=lambda c:(c['row'],c['column'])) and not m['trailing_space_padding'],'All and only independently reviewed literal cells')
    need(Path(m['historical_repository_acceptance']['path']).read_bytes()==Path(m['historical_repository_original']['path']).read_bytes(),'Historical acceptance exact immutable copy')
    targets=set();jsonops=0;textbytes=[];models=[];companions=[]
    for f in m['files']:
        target=Path(f['target']).resolve();need(target not in targets,'Unique scoped target');targets.add(target)
        after=checked(f['candidate']);before=f['before']
        if before is None:
            need(not target.exists(),'New companion absent guard')
            need(f['role'] in {'source preview','source review notes'},'Only new quartet companion may be created')
            companions.append(f);continue
        oldpath=checked(before);need(target.is_file() and sha(target)==before['sha256'],'Current target exact preimage');epochs[target]=before['sha256']
        if f['role']=='source preview':
            continue  # Independently regenerated from the corrected grid below.
        if f['role']=='source review notes':
            need(after.read_bytes().startswith(oldpath.read_bytes().rstrip()),'Existing review notes preserved before appended current correction')
            continue
        if target.suffix=='.txt':
            a=oldpath.read_text(encoding='utf-8-sig').splitlines();b=after.read_text(encoding='utf-8-sig').splitlines()
            need(len(a)==len(b) and list(map(len,a))==list(map(len,b)),'Preserve TXT character grid')
            changes=[dict(row=y,column=x,before=c,after=d) for y,(r,s) in enumerate(zip(a,b)) for x,(c,d) in enumerate(zip(r,s)) if c!=d]
            if f['role'] in {'working accepted TXT','repository accepted TXT'}:
                need(changes==f['changes'] and sorted(changes,key=lambda c:(c['row'],c['column']))==sorted(allowed_cells,key=lambda c:(c['row'],c['column'])),'Exact source text grid changes')
                textbytes.append(after.read_bytes())
            else:raise AssertionError('Unexpected existing TXT target role '+f['role'])
        elif target.suffix=='.json':
            a,b=read(oldpath),read(after);changes=diff(a,b)
            need(sorted(changes,key=lambda c:c[0])==sorted([(p['pointer'],p['before'],p['after']) for p in f['changes']],key=lambda c:c[0]),'No hidden JSON changes')
            replay=copy.deepcopy(a)
            for patch in f['changes']:
                ptr=patch['pointer'];need(pointer(a,ptr)==patch['before'],'Exact JSON preimage')
                parent=ptr.rsplit('/',1)[0]
                if '/printed_lines/' in ptr:parent=parent.rsplit('/',1)[0]
                item=pointer(b,parent);sockets=item.get('sockets') or ([item['socket']] if item.get('socket') else [])
                site=tuple(sorted(map(physical,sockets)));need(site in sites,'Only reviewed physical site changed')
                board=item.get('board',b.get('board'));need(board==m['board'],'Exact board binding')
                local=sites[site];field=ptr.rsplit('/',1)[-1]
                if '/printed_lines/' in ptr:
                    expected=patch['before']
                    for old,new in sorted(part_rules.items(),key=lambda x:-len(x[0])):expected=expected.replace(old,new)
                    need(expected==patch['after'],'Printed identity mirror only')
                else:need(field in local and (patch['before'],patch['after'])==local[field],'Only reviewed identity field')
                need(item.get('part_number')==local['part_number'][1] and item.get('card_type')==local['card_type'][1],'Full same-site identity aftervalue')
                setpointer(replay,ptr,patch['after'])
            need(replay==b,'Complete independent active JSON replay');jsonops+=len(changes)
            if f['role']=='current accepted socket table model':
                models.append(b)
                for p in model_changes:need(pointer(a,p['pointer'])==p['before'] and pointer(b,p['pointer'])==p['after'],'Primary source model exact proposal axes')
        else:raise AssertionError('Unexpected existing target '+str(target))
    need(len(textbytes)==2 and textbytes[0]==textbytes[1],'Working and repository text identical')
    need(len(models)==2 and models[0]==models[1],'Working and repository models identical')
    visible=textbytes[0].decode('utf-8-sig').splitlines();font=ImageFont.truetype(m['font']['path'],18);cw=round(font.getlength('M'))
    preview=Image.new('RGB',(32+max(map(len,visible))*cw,32+len(visible)*25),'white');draw=ImageDraw.Draw(preview)
    for y,line in enumerate(visible):draw.text((16,16+y*25),line,font=font,fill='black')
    f=next(f for f in m['files'] if f['role']=='source preview')
    with Image.open(f['candidate']['path']) as tile:need(tile.size==preview.size and tile.convert('RGB').tobytes()==preview.tobytes(),'Exact independently regenerated corrected-grid preview')
    note=Path(next(f for f in m['files'] if f['role']=='source review notes')['candidate']['path']).read_text(encoding='utf-8-sig')
    need('Acceptance and publication are separate receipts.' in note,'Review note does not invent publication')
    for path,expected in epochs.items():need(sha(path)==expected,'Final source/candidate/preimage epoch '+str(path))
    for f in companions:need(not Path(f['target']).exists(),'Final absent companion guard')
    receipt={'schema':'socket-table-literal-correction-independent-acceptance-v1','independent_review':True,'passed':True,'failures':[],
             'manifest_sha256':args.expected_sha256,'stage_manifest':bind(args.manifest),'created_utc':datetime.now(timezone.utc).isoformat(),
             'check_count':checks,'reviewer':bind(__file__),'native_proposals':proposal_binding,'native_occurrences':native_proofs,
             'native_readings_independently_viewed':True,'target_count':len(m['files']),'meaningful_txt_cells':len(allowed_cells),'active_json_fields':jsonops,
             'candidate_bindings':[dict(target=f['target'],role=f['role'],before=f['before'],candidate=f['candidate']) for f in m['files']],
             'source_or_canonical_writes':False,'scope':'Exact frozen table stage only. Native evidence independently viewed and reproduced. Printed identity, same-site active mirrors and corrected preview verified. All historical ledgers preserved; no source publication performed.'}
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'check_count':checks,'receipt':bind(args.output)},indent=2))
if __name__=='__main__':main()
