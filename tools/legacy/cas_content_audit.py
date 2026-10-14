from pathlib import Path
import json,collections
D=Path(__file__).parent/'cas';OUT=D.parent.parent.parent/'ALD_Visual_Transcriptions/CAS Diagrams'
findings=[]
for p in sorted(D.glob('* reviewed.json')):
 s=json.loads(p.read_text(encoding='utf-8'));page=p.name.split()[0];by=collections.defaultdict(list)
 for n in s['nodes']:
  a=n['address'].zfill(4);by[a].append(n['box'])
  if all(ch in '0123456789ABCDEF' for ch in a) and int(a,16)>4095:findings.append({'page':page,'box':n['box'],'issue':'address outside 12-bit ROS','value':a})
  for f in n['fields']:
   if len(f)>14:findings.append({'page':page,'box':n['box'],'issue':'field extends over right border','value':f,'length':len(f)})
 for a,b in by.items():
  if len(b)>1 and all(ch in '0123456789ABCDEF' for ch in a):findings.append({'page':page,'issue':'duplicate address within page; source review needed','value':a,'boxes':b})
 for c,r,t in s.get('text',[]):
  if 'QV' in t:findings.append({'page':page,'issue':'possible QY prefix misread as QV','value':t})
(OUT/'Content audit.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
print(len(findings),'content findings')
print(json.dumps(findings,ensure_ascii=True))
