from pathlib import Path
import json,hashlib,copy,os
base=Path(r'D:\Github\IBM360\ibm360ald\json\RT T Register');p=Path(r'D:\Github\IBM360\tmp\ald-team-resume530\team5\ALD batch1258\RT421 independent reconstruction1258');d=p/'Private BT line2 candidate';model=base/'RT421 T REGISTER BITS 42 AND 43.json';reviewfile=base/'review/RT/RT421.json';h=lambda b:hashlib.sha256(b).hexdigest();mb=model.read_bytes();rb=reviewfile.read_bytes();assert h(mb)=='00f6e93eb16b212cc925b70d77615c1f787dad863104a8821fc926babf4e0145';assert h(rb)=='a6ad40a0a0f48b5145672de2d6dd066449f4cab316dd3ce14a4c0eca4bf24104';v=json.loads(mb);rv=json.loads(rb);oldref='blocks/BT/pins/L/4';newref='blocks/BT/pins/L/2'
def digest(x):return h(json.dumps({k:v for k,v in x.items() if k!='review'},ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
assert rv['content sha256']==digest(v) and v['review']['approved'] is False and v['review']['unresolved discrepancies'] is True
assert v['blocks'][35]['serial']=='BT';pins=v['blocks'][35]['pins'];assert sum(x.get('side')=='L' and x.get('line')==4 for x in pins)==1 and not any(x.get('side')=='L' and x.get('line')==2 for x in pins)
assert v['nets'][45]['net number']=='RT421BJ4' and v['nets'][45]['nodes']==['blocks/BJ/pins/R/4',oldref];assert v['nets'][45]['routing']==[[[130,75],[138,75],[138,82],[141,82]]]
def walk(o,path=''):
 if isinstance(o,dict):
  for k,x in o.items():yield from walk(x,path+'/'+k.replace('~','~0').replace('/','~1'))
 elif isinstance(o,list):
  if o in ([138,82],[141,82],[138,80],[141,80]):yield {'pointer':path,'kind':'coordinate-array','value':o}
  for i,x in enumerate(o):yield from walk(x,path+'/'+str(i))
 elif isinstance(o,str) and (oldref in o or newref in o):yield {'pointer':path,'kind':'terminal-reference','value':o}
inv={'model':list(walk(v)),'review':list(walk(rv))};model_oldrefs=[x['pointer'] for x in inv['model'] if x['kind']=='terminal-reference' and oldref in x['value']];model_newrefs=[x for x in inv['model'] if x['kind']=='terminal-reference' and newref in x['value']];assert model_oldrefs==['/nets/45/nodes/1'] and not model_newrefs
assert {x['pointer'] for x in inv['model'] if x['kind']=='coordinate-array' and x['value'] in ([138,82],[141,82])}=={'/nets/45/routing/0/2','/nets/45/routing/0/3'}
# Enumerate every unrelated route segment crossing proposed endpoints/approach; guard fails on any other net.
def segment(a,b):
 x,y=a;X,Y=b
 if x==X:return {(x,z) for z in range(min(y,Y),max(y,Y)+1)}
 if y==Y:return {(z,y) for z in range(min(x,X),max(x,X)+1)}
 raise ValueError('nonorthogonal')
probe=segment([138,75],[138,80]);conflicts=[]
for i,n in enumerate(v['nets']):
 if i==45:continue
 for j,path in enumerate(n.get('routing',[])):
  for k,(a,b) in enumerate(zip(path,path[1:])):
   shared=sorted(probe & segment(a,b))
   if shared:conflicts.append({'net_pointer':f'/nets/{i}','route_pointer':f'/nets/{i}/routing/{j}/{k}','shared':shared})
assert not conflicts
new=copy.deepcopy(v);newrv=copy.deepcopy(rv);new['blocks'][35]['pins'][0]['line']=2;new['nets'][45]['nodes'][1]=newref;new['nets'][45]['routing'][0]=[[130,75],[138,75],[138,80]]
newrv['content sha256']=digest(new);newrv['private proposed BT row correction']={'status':'proposed; unresolved','original terminal':oldref,'proposed terminal':newref,'old route':[[130,75],[138,75],[138,82],[141,82]],'proposed route':[[130,75],[138,75],[138,80]],'native evidence':str(p/'RT421 three-case native landmark adjudication.json'),'native evidence sha256':'f1faf4414833ea55f51d800bddf43d0e00c9799962cd099705ae8f1feb7113b9','limitations':'Candidate only; preserves height7, footer, lower input, output, net identity and all existing unresolved findings. No runtime validation, electrical approval, or inferred ownership. Old V3 point [141,82] and raw route start [127,75] remain historical; current V4 start [130,75] preserved.'}
def diffs(a,b,path=''):
 if type(a)!=type(b):return [{'pointer':path,'before':a,'after':b}]
 if isinstance(a,dict):
  result=[]
  for k in sorted(set(a)|set(b)):
   x=path+'/'+k.replace('~','~0').replace('/','~1')
   if k not in a:result.append({'pointer':x,'before_missing':True,'after':b[k]})
   elif k not in b:result.append({'pointer':x,'before':a[k],'after_missing':True})
   else:result.extend(diffs(a[k],b[k],x))
  return result
 if isinstance(a,list):
  if len(a)!=len(b):return [{'pointer':path,'before':a,'after':b}]
  return sum((diffs(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b))),[])
 return [] if a==b else [{'pointer':path,'before':a,'after':b}]
md=diffs(v,new);rd=diffs(rv,newrv);expected={'/blocks/35/pins/0/line','/nets/45/nodes/1','/nets/45/routing/0'};assert {x['pointer'] for x in md}==expected;assert {x['pointer'] for x in rd}=={'/content sha256','/private proposed BT row correction'};assert new['blocks'][35]['height']==7 and new['review']==v['review'];assert newrv['human-confirmed transcription follow-up']==rv['human-confirmed transcription follow-up']
def write(path,b):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
write(d/'Current model preimage.json',mb);write(d/'Current review preimage.json',rb)
outm=(json.dumps(new,ensure_ascii=False,indent=2)+'\n').encode();outr=(json.dumps(newrv,ensure_ascii=False,indent=2)+'\n').encode();write(d/'RT421 candidate.json',outm);write(d/'review/RT/RT421.json',outr)
proof={'page':'RT421','status':'private SOURCE-only candidate; not runtime validated, approved false','inputs':{'current_model_path':str(model),'current_model_sha256':h(mb),'current_review_path':str(reviewfile),'current_review_sha256':h(rb),'historical_raw_sha256':h((p/'Inputs/Page.raw.json').read_bytes()),'historical_typed_v3_sha256':h((p/'Inputs/Baseline model.json').read_bytes()),'historical_original_seal_sha256':h((p/'Immutable final manifest1258.json').read_bytes())},'candidate_model_sha256':h(outm),'candidate_review_sha256':h(outr),'candidate_content_sha256':digest(new),'reference_inventory':inv,'candidate_probe_other_net_conflicts':conflicts,'candidate_BT_L2_unused_in_current_block':True,'model_forward_complete':md,'model_inverse_complete':diffs(new,v),'review_forward_complete':rd,'review_inverse_complete':diffs(newrv,rv),'complement_equal':True,'retained_original_findings':True,'native_support':'f1faf4414833ea55f51d800bddf43d0e00c9799962cd099705ae8f1feb7113b9','limitations':'Source-only. No converter, renderer, validator, runtime test, external schema, electrical ownership or continuity conclusion. Proposed BT coordinates derive from approximate landmark alignment; height7/footer uncertainty remains. No BH/AN edits; no canonical or status/cache mutation.'};write(d/'Candidate proof and full reference inventory.json',(json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({'proof_sha256':h((d/'Candidate proof and full reference inventory.json').read_bytes()),'model':h(outm),'review':h(outr),'content':digest(new),'model_diff':md,'review_diff_pointers':[x['pointer'] for x in rd],'conflicts':conflicts},ensure_ascii=False))