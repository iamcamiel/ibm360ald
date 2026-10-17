"""Independent BA-index source batch review. Only a private receipt is written."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import json,hashlib,copy
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
FOLDER=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1231-A1232-BA-portion-corrections'
MP=FOLDER/'Batch manifest.json';EXPECTED='ea64931427925bc5f3bf5a3fb0d97f371f45e83dc3fabe45a77296a45d1a7978'
checks=0;epochs={};missing=set()
def need(ok,why):
    global checks
    checks+=1
    if not ok:raise AssertionError(why)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(link,base=None):
    p=Path(link['path']);p=p if p.is_absolute() else (base or ROOT)/p;p=p.resolve()
    need(p.is_file() and sha(p)==link['sha256'],'Current exact binding '+str(p));epochs[p]=link['sha256'];return p
def ptr(doc,p):
    if not p:return doc
    for key in p.strip('/').split('/'):
        key=key.replace('~1','/').replace('~0','~');doc=doc[int(key)] if isinstance(doc,list) else doc[key]
    return doc
def apply(doc,patch):
    path=patch.get('path',patch.get('pointer'));parent,key=path.rsplit('/',1);item=ptr(doc,parent)
    if patch.get('op','replace')=='add':item.insert(int(key),copy.deepcopy(patch['after']))
    else:item[int(key) if isinstance(item,list) else key]=copy.deepcopy(patch['after'])
need(sha(MP)==EXPECTED,'Frozen exact BA batch');epochs[MP.resolve()]=EXPECTED;b=read(MP)
need(b['schema']=='socket-reference-batch-application-stage-v1' and b['source_changes_applied'] is False,'Private unapplied batch')
need(b['counts']=={'source_pages':2,'source_tokens':3,'source_cells':3,'candidate_files':17},'Exact scoped batch inventory')
need(b['tool_candidates']==[] and b['uniform_preimages']==[] and b['uniform_rebuild_deferred'] is True,'No tool or uniform-data mutation in batch')
for key in ['preparation_script','publication_script','authority','registration_helper','font','predecessor_adapter','registry_predecessor']:checked(b[key])
for link in b['metadata_preimages']+b['preserved_column_proofs']:checked(link)
for link in b['source_bindings']:checked(link,REPO)
for value in b['absent_legacy_paths_no_initialization_proposed']:
    p=Path(value);need(not p.exists(),'Absent legacy model remains absent');missing.add(p)
stage_list=read(FOLDER/'Prepared page stages.json');checked(stage_list['batch_manifest'])
need(stage_list['published'] is False and len(stage_list['page_stages'])==2,'Both unpublished page stages')
stage_shas={'A1231-01':'893b5cbb96f00538ba008c0cc4d98b3a2f377abc4716fd607c31edc68871fec3','A1232-01':'0752a476be24dfd88842103feeb88806806cbd65d74c3b826c8135cf5ff78510'}
stages={};nativeproofs=[]
for link in stage_list['page_stages']:
    stagepath=checked(link);s=read(stagepath);page=s['page'];stages[page]=s
    need(link['sha256']==stage_shas[page] and s['artifact_schema']=='reviewed-existing-A1-table-and-auxiliary-data-v1' and s['model_schema']=='socket-table-columns-v1','Honest columns schema and exact stage')
    checked(s['batch_manifest'])
    for key in ['source','human_authority','predecessor_acceptance','predecessor_application_snapshot','historical_repository_acceptance','historical_repository_original']:checked(s[key])
    need(Path(s['historical_repository_original']['path']).read_bytes()==Path(s['historical_repository_acceptance']['path']).read_bytes(),'Original repository review remains byte-identical')
    for crop in s['source_crops']:
        checked(crop);need(crop['source']==s['source'] and crop['bounds']==crop['box'],'Exact native source identity/coordinates')
        with Image.open(s['source']['path']) as src,Image.open(crop['path']) as tile:
            im=src.crop(crop['box']).convert('RGB');need(im.size==tile.size and im.tobytes()==tile.convert('RGB').tobytes(),'Native BA crop reproduced')
        nativeproofs.append(crop)
    need(len(s['files'])==5 and {f['role'] for f in s['files']}=={'working accepted TXT','repository accepted TXT','successor columns proof','source review notes','source preview'},'No invented current page model')
    for parent in [ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:
        absent=parent/(page+' SOCKET LISTING.json');need(not absent.exists(),'Existing absent page model not initialized');missing.add(absent)
allowed={('02B-C1',('G6','G7'),'RA301'),('02B-C1',('J6','J7'),'RB561'),('02B-C2',('D6','D7'),'RK301')}
counts=Counter();targets=set();filebytarget={};newcolumns={};texts={};candidate_bindings=[]
for f in b['files']:
    target=Path(f['target']).resolve();need(target not in targets,'Unique batch target');targets.add(target);filebytarget[str(target)]=f
    need(target.is_relative_to(ROOT) and target.suffix.lower() not in {'.tif','.tiff'},'No original source target')
    after=checked(f['candidate']);candidate_bindings.append(f['candidate'])
    before=checked(f['before']) if f['before'] else None
    if before is None:need(not target.exists(),'Exact absent new companion/proof guard');missing.add(target)
    else:need(target.is_file() and sha(target)==f['before']['sha256'],'Current target preimage');epochs[target]=f['before']['sha256']
    role=f['role']
    if role=='current auxiliary reference mirror':
        need(before is not None,'Auxiliary model must already exist');old=read(before);new=read(after);replay=copy.deepcopy(old)
        for change in f['changes']:
            p=change['path'];need(change['op'] in {'replace','add'},'Explicit reference operation')
            if change['op']=='replace':
                need(change['before']=='BB' and change['after']=='BA','Only misread first BB becomes BA')
                parent,index=p.rsplit('/',1);siblings=ptr(old,parent);new_siblings=ptr(new,parent);index=int(index)
                need(siblings==change['ordered_siblings_before'] and siblings[index:index+2]==['BB','BB'] and new_siblings[index:index+2]==['BA','BB'],'Following genuine BB retained with original order and multiplicity')
                owner_path=p.split('/references/')[0];owner=ptr(new,owner_path)
                refindex=int(p.split('/references/')[1].split('/')[0]);ref=owner['references'][refindex]
                need((owner['board'],tuple(owner['sockets']),ref['ALD_page']) in allowed and owner['card_type']=='4198' and owner['part_number']=='5804198','Exact physical module and source page')
                need(ptr(replay,p)=='BB','Original printed token current')
            else:
                need(p.startswith('/ALD_pages/'),'Only derived page index insertion permitted')
                parent,index=p.rsplit('/',1);array=ptr(replay,parent);index=int(index);olditem=array[index]
                need(olditem==change['insert_before_preimage'] and olditem['portion']=='BB','Retain existing deduplicated BB index item')
                newitem=change['after'];need(newitem==dict(olditem,portion='BA'),'New BA index is exact same module/source identity')
                need((newitem['board'],tuple(newitem['sockets']),parent.split('/')[-1]) in allowed,'Source-bound derived BA insertion')
            apply(replay,change);counts['active_legacy_JSON_operations']+=1
        need(replay==new,'No undeclared auxiliary/historical/model mutation')
    elif role in {'working accepted TXT','repository accepted TXT'}:
        need(before is not None,'Existing accepted source text required');old=before.read_bytes();new=after.read_bytes();ar=old.decode('utf-8-sig').splitlines();br=new.decode('utf-8-sig').splitlines()
        need(len(ar)==len(br) and list(map(len,ar))==list(map(len,br)),'Source character grid retained')
        actual=[dict(row=y,column=x,before=u,after=v) for y,(r,s) in enumerate(zip(ar,br)) for x,(u,v) in enumerate(zip(r,s)) if u!=v]
        page=target.name.split(' ')[0];expected=next(p['exact_meaningful_cell_changes'] for p in b['pages'] if p['page']==page)
        need(actual==f['changes']==expected,'Only3 independently read source cells in each mirror')
        rows=old.decode('utf-8').splitlines(keepends=True)
        for edit in actual:
            y,x=edit['row'],edit['column'];need(rows[y][x]=='B','Exact source cell before');rows[y]=rows[y][:x]+'A'+rows[y][x+1:]
            need('BA BB' in br[y],'Source next BB preserved')
        need(''.join(rows).encode('utf-8')==new,'Source TXT exact byte replay')
        texts[(page,role)]=new;counts['TXT_mirror_cells']+=len(actual)
    elif role=='successor columns proof':
        need(before is None,'Columns successor is new and never overwrites original proof')
        page=target.name.split(' ')[0];original=next(p['historical_columns'] for p in b['pages'] if p['page']==page)
        old=read(checked(original));new=read(after);replay=copy.deepcopy(old)
        need(isinstance(old,list) and isinstance(new,list) and len(old)==len(new)==7,'Actual7-column proof arrays')
        for change in f['changes']:
            need(ptr(replay,change['pointer'])==change['before'] and 'BB BB' in change['before'] and 'BA BB' in change['after'],'Precise raw column first duplicate correction')
            need(change['after']==change['before'].replace('BB BB','BA BB',1),'Only one source-column letter changes')
            apply(replay,change);counts['successor_column_token_changes']+=1
        need(replay==new,'Original source-column arrays preserved except exact successor3 tokens');newcolumns[page]=new
    elif role=='source review notes':
        need(before is None or after.read_bytes().startswith(before.read_bytes().rstrip(b'\r\n')),'Prior notes preserved')
        note=after.read_text(encoding='utf-8-sig');need('BA' in note and 'BB' in note,'Review note describes actual BA/BB distinction')
    elif role=='source preview':pass  # Pixel-check against accepted candidate text below.
    else:raise AssertionError('Unrequested batch role '+role)
for page,stage in stages.items():
    need(texts[(page,'working accepted TXT')]==texts[(page,'repository accepted TXT')],'Working/repository text mirror equality')
    for f in stage['files']:
        need(str(Path(f['target']).resolve()) in filebytarget and f==filebytarget[str(Path(f['target']).resolve())],'Exact page-stage target bound to approved batch')
    rows=texts[(page,'working accepted TXT')].decode('utf-8-sig').splitlines();font=ImageFont.truetype(b['font']['path'],18);cw=round(font.getlength('M'))
    im=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(im)
    for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
    preview=next(f for f in stage['files'] if f['role']=='source preview')
    with Image.open(preview['candidate']['path']) as tile:need(im.size==tile.size and im.tobytes()==tile.convert('RGB').tobytes(),'Corrected source preview independently reproduced')
    # Every new raw-column line must also occur in the corrected accepted TXT.
    proof=next(f for f in stage['files'] if f['role']=='successor columns proof')
    for change in proof['changes']:need(any(change['after'].strip() in row for row in rows),'Column successor token agrees with corrected accepted TXT')
need(len(targets)==17 and counts['active_legacy_JSON_operations']==23 and counts['TXT_mirror_cells']==6 and counts['successor_column_token_changes']==3,'Exact source/auxiliary/columns aggregate scope')
for path,digest in epochs.items():need(sha(path)==digest,'Final bound source/proof/preimage/candidate epoch '+str(path))
for path in missing:need(not path.exists(),'All absent original models/new targets remain uncreated before publication')
need(sha(MP)==EXPECTED,'Frozen batch unchanged at end')
receipt={'schema':'socket-reference-batch-independent-acceptance-v1','independent_review':True,'passed':True,'failures':[],
         'created_utc':datetime.now(timezone.utc).isoformat(),'check_count':checks,'batch_manifest':bind(MP),'accepted_page_stages':stage_list['page_stages'],
         'reviewer_program':bind(__file__),'candidate_bindings':candidate_bindings,'counts':dict(counts),'native_source_crops':nativeproofs,
         'native_readings_independently_viewed':3,'source_or_canonical_writes':False,
         'scope':'Only source BA/BB portions at02B-C1 G6/G7 RA301,02B-C1 J6/J7 RB561,02B-C2 D6/D7 RK301. Full ordered duplicate BB preservation, existing auxiliary models and new successor column proofs verified; absent page/legacy models and all original proof arrays unchanged. No publication performed.'}
dest=FOLDER/'Independent acceptance.json';need(not dest.exists(),'Never overwrite independent review history')
dest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'checks':checks,'receipt':bind(dest),'counts':dict(counts)},indent=2))
