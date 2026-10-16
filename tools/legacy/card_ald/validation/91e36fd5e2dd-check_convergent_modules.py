"""Small independent planner counterexample: collectors must stay with fan-ins."""
import sys,json,copy,hashlib
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'));sys.path.insert(0,str(ROOT.parent/'tmp/ald-text/card-layout-deps'))
import graph_card_layout as L
def gate(fn):return {'function':fn,'_inputs':[{'pin':None,'ref':'i0'},{'pin':None,'ref':'i1'}],'_outputs':[{'pin':None,'ref':'o'}]}
nodes={};edges=[];families={}
for i in range(3):
 collector=f'collector_{i}';sources=[f'source_{i}_a',f'source_{i}_b'];families[collector]=sources;nodes[collector]=gate('OR')
 for s in sources:nodes[s]=gate('A');edges.append({'source':s,'target':collector})
 edges.append({'source':collector,'target':'parent'})
nodes['parent']=gate('A');model={'portions':nodes,'edges':edges};before=copy.deepcopy(model);p=L.plan(model)
checks=[]
checks.append({'name':'Planner leaves electrical model unchanged','passed':model==before})
checks.append({'name':'Three convergent collectors retain independent sibling-source modules','passed':all(any(m['collector']==c and set(m['parallel_sources'])==set(ss) for m in p['metrics']['convergent_modules']) for c,ss in families.items())})
checks.append({'name':'Collectors are never grouped as bare siblings merely because they feed a parent','passed':not any(set(families)<=set(g) for g in p['metrics']['sibling_groups'])})
checks.append({'name':'Each collector center lies within its own pair of source centers','passed':all(min(p['tops'][s]+3 for s in ss)<=p['tops'][c]+3<=max(p['tops'][s]+3 for s in ss) for c,ss in families.items())})
centers=sorted(p['tops'][c]+3 for c in families)
checks.append({'name':'Independent collector modules separated by their14row source spans','passed':all(b-a>=14 for a,b in zip(centers,centers[1:]))})
result={'passed':all(c['passed'] for c in checks),'failures':[c['name'] for c in checks if not c['passed']],'checks':checks,'synthetic_plan':p,'candidate_bindings':[{'path':str(ROOT/'tools/card_ald/graph_card_layout.py'),'sha256':hashlib.sha256((ROOT/'tools/card_ald/graph_card_layout.py').read_bytes()).hexdigest()}]}
(HERE/'Convergent module synthetic review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':result['passed'],'failures':result['failures'],'centers':centers}))
