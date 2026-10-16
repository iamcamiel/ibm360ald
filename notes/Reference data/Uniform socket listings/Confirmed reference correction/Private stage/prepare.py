"""Prepare the independently reviewable A1232 literal correction; no publication."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json
from PIL import Image, ImageDraw, ImageFont

R = Path('D:/Github/IBM360')
O = Path(__file__).resolve().parent
OLD, NEW = 'REC41AY4', 'RE041AY4'
def sha(b): return hashlib.sha256(b).hexdigest()
def bind(p): return {'path':str(p.resolve()),'sha256':sha(p.read_bytes())}
def encode(v): return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf8')
files=[]
def candidate(target,raw,role,changes):
    target=Path(target); exists=target.exists()
    before=target.read_bytes() if exists else None
    if exists:
        snap=O/'before'/sha(before)/target.name; snap.parent.mkdir(parents=True,exist_ok=True);snap.write_bytes(before)
    out=O/'candidate'/str(len(files)).zfill(2)/target.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
    files.append({'target':str(target.resolve()),'before':bind(snap) if exists else None,
                  'candidate':bind(out),'role':role,'changes':changes})
    return out

txt=R/'ALD_Visual_Transcriptions/A1 Socket Listing/A1232-01 SOCKET LISTING.txt'
raw=txt.read_bytes(); assert raw.count(OLD.encode())==1
new=raw.replace(OLD.encode(),NEW.encode());a=raw.decode('utf8').splitlines();b=new.decode('utf8').splitlines()
delta=[dict(row=y,column=x,before=c,after=d) for y,(aa,bb) in enumerate(zip(a,b)) for x,(c,d) in enumerate(zip(aa,bb)) if c!=d]
assert delta==[dict(row=8,column=24,before='C',after='0')]
assert len(a)==len(b) and list(map(len,a))==list(map(len,b))
source_txt=candidate(txt,new,'working accepted TXT',delta)
candidate(R/'ibm360ald/ALD/A1 Socket Listing'/txt.name,new,'repository accepted TXT',delta)
proof=R/'tmp/ald-text/a1/A1232-01 columns reviewed.json'
cols=json.loads(proof.read_text(encoding='utf8')); assert cols[0][6]=='            A2 B03 '+OLD
cols[0][6]=cols[0][6].replace(OLD,NEW)
candidate(R/'tmp/ald-text/a1/A1232-01 columns reference correction.json',encode(cols),'successor columns proof',[{'pointer':'/0/6','before':'            A2 B03 '+OLD,'after':cols[0][6]}])

def replace_strings(v,p=''):
    changes=[]
    if isinstance(v,dict):
        for k in list(v):
            q=p+'/'+k.replace('~','~0').replace('/','~1')
            if isinstance(v[k],str) and OLD in v[k]:
                before=v[k];v[k]=before.replace(OLD,NEW);changes.append(dict(pointer=q,before=before,after=v[k]))
            else: changes+=replace_strings(v[k],q)
    elif isinstance(v,list):
        for i,x in enumerate(v):
            if isinstance(x,str) and OLD in x:
                v[i]=x.replace(OLD,NEW);changes.append(dict(pointer=p+'/'+str(i),before=x,after=v[i]))
            else: changes+=replace_strings(x,p+'/'+str(i))
    return changes

for rel in ['ALD_Visual_Transcriptions/A1 Socket Listing/A1232 BOARD 02B-C2.json',
            'ALD_Visual_Transcriptions/A1 Socket Listing/Socket reference.json',
            'ALD_Visual_Transcriptions/A1 Socket Listing/ALD references.json',
            'ibm360ald/json/A1 Socket Listing/Socket reference.json',
            'ibm360ald/json/A1 Socket Listing/ALD references.json',
            'tmp/ald-text/a1/references without scan filename.json']:
    p=R/rel;d=json.loads(p.read_text(encoding='utf-8-sig'));changes=replace_strings(d)
    assert changes,rel
    buckets=d.get('ALD_pages',d)
    if isinstance(buckets,dict) and 'REC41' in buckets:
        moved=buckets.pop('REC41');assert len(moved)==1 and moved[0]['ALD_reference']==NEW
        buckets.setdefault('RE041',[]).extend(moved)
        changes.append({'operation':'move_bucket_entries','before_key':'REC41','after_key':'RE041','count':1})
    candidate(p,encode(d),'current auxiliary reference mirror',changes)

note=('A1232-01 SOCKET LISTING - CONFIRMED REFERENCE CORRECTION\n\n'
      'The user confirmed the sole A2T/A2 B03 reference as RE041AY4: "Yes, certainly RE041AY4".\n'
      'One character changed at zero-based row 8, column 24: REC41AY4 -> RE041AY4.\n'
      'RE041 footer AY4 independently names B-C2A2B03, corroborating the connector endpoint.\n'
      'The original columns reviewed array and historical acceptance receipt remain unchanged.\n'
      'This note and the new preview are first-created review artifacts; no prior companion quartet is claimed.\n'
      'The successor columns proof records the same single literal correction.\n')
candidate(txt.with_name(txt.stem+' review notes.txt'),note.encode(),'new source review notes',[])
fontpath=R/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18)
cw=int(round(font.getlength('M')));lh=25
im=Image.new('RGB',(32+max(map(len,b))*cw,32+len(b)*lh),'white');dr=ImageDraw.Draw(im)
for y,line in enumerate(b): dr.text((16,16+y*lh),line,font=font,fill='black')
preview=O/'preview.png';im.save(preview)
candidate(txt.with_name(txt.stem+' preview.png'),preview.read_bytes(),'new source preview',[])
source=Path('D:/Reference Materials/IBM 360/IBM_360_ALD/A1 Socket Listing/A1232-01 SOCKET LISTING.tif')
crop=O.parent/'A1232-01 A2T reference crop.png'
re=R/'ALD_Visual_Transcriptions/ALD Diagrams/RE041 E REGISTER BITS 04-07.txt'
footer=[{'row':i,'literal':l} for i,l in enumerate(re.read_text(encoding='utf8').splitlines()) if 'AY4 B-C2A2B03' in l]
assert len(footer)==1
answer={'schema':'source-review-recorded-human-answer-v1','raw_answer':'Yes, certainly RE041AY4',
        'normalized_answer':NEW,'authority':'Direct human response relayed by coordinator /root in current task',
        'field':'A1232-01 A2T / A2 B03 ALD reference','source':bind(source),'crop':bind(crop)}
(O/'Human answer.json').write_bytes(encode(answer))
manifest={'schema':'socket-table-literal-correction-private-stage-v1','created_utc':datetime.now(timezone.utc).isoformat(),
          'publication_status':'PRIVATE CANDIDATE: independent review and guarded publication required',
          'artifact_schema':'reviewed-existing-A1-table-and-auxiliary-data-v1',
          'page':'A1232-01','source_scan_id':'119','source':bind(source),
          'human_authority':bind(O/'Human answer.json'),'source_crop':bind(crop),
          'predecessor_acceptance':bind(proof),
          'historical_repository_acceptance':bind(R/'ibm360ald/notes/A1 Socket Listing/A1232-01 acceptance receipt.json'),
          'corroboration':{'text':bind(re),'footer':footer},'render_font':bind(fontpath),
          'exact_meaningful_cell_changes':delta,'trailing_space_padding':[],
          'files':files,'preservation':[
              'Do not overwrite historical columns reviewed array or repository acceptance receipt.',
              'No prior notes, preview or JSON companion is invented.',
              'Historical a1232_data.py is not active accepted data and remains unchanged.',
              'Current adapter must bind guarded publication plus independent review before export eligibility.'],
          'checks':{'same_line_count':True,'same_row_lengths':True,'one_cell_only':True,'old_token_absent_from_candidates':True},
          'preparation_script':bind(Path(__file__))}
(O/'Stage manifest.json').write_bytes(encode(manifest))
print(json.dumps({'files':len(files),'manifest':bind(O/'Stage manifest.json'),'text_cells':delta,'grid':{'rows':len(b),'widths':sorted(set(map(len,b)))},'published':False},indent=2))
