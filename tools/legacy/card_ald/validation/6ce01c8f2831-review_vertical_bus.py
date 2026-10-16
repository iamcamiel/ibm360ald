"""Independent actual D10 staircase and negative fixture review for vertical buses."""
import datetime,hashlib,json,sys
from pathlib import Path
from copy import deepcopy
HERE=Path(__file__).parent;ROOT=Path('D:/Github/IBM360/ibm360ald')
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import vertical_fanout_order as V
import generate_card as G
import render_composite_card as R
from review_equivalent_inputs import geometry,back
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf8'))
def bind(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
    source=ROOT.parent/'tmp/ald-text/ald/card-data/4191-grouped-collectors/4191.json';spec=read(source);model,old=geometry(spec);R.verify(model,old)
    source_bindings=[bind(ROOT/'tools/card_ald'/name) for name in ['vertical_fanout_order.py','render_composite_card.py','generate_card.py','compact_terminations.py']]
    new,report=V.optimize(model,old);candidate=back(spec,new);G.build(candidate);checks=[]
    def ck(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    oldtrace,newtrace=trace(spec),trace(candidate);terms=next(n for n in oldtrace if 'PIN:D10' in n);net=spec['nets'].index(list(terms))
    def tracks(graph):return sorted({a[0] for a,b in graph['edge_set'] if a[0]==b[0] and a[1]!=b[1]})
    ck('Exact reported historical D10 staircase becomes one vertical trunk',len(tracks(oldtrace[terms]))>1 and len(tracks(newtrace[terms]))==1,dict(before=tracks(oldtrace[terms]),after=tracks(newtrace[terms])))
    ck('D10 retains all four portions and exterior contact',set(terms)=={'PIN:D10','PORT:12:output:3','PORT:31:input:3','PORT:32:input:3','PORT:35:input:1'} and terms in newtrace)
    ck('All62 independently traced electrical trees preserve exact terminal sets',set(oldtrace)==set(newtrace) and len(newtrace)==62 and all(n['cycle_rank']==0 for n in newtrace.values()))
    ck('All box port exterior metadata remains byte-equivalent',new[:3]==old[:3] and candidate['boxes']==spec['boxes'] and candidate['exterior_pins']==spec['exterior_pins'] and candidate['variants']==spec['variants'])
    changed={c['net'] for c in report['changes']}
    foreign=lambda router:{(point,net):frozenset(arms) for point,nets in router.wires.items() for net,arms in nets.items() if net not in changed}
    ck('All foreign net layers are exactly unchanged',foreign(new[3])==foreign(old[3]))
    ck('Every accepted bus strictly improves crossing/bend/length score',all(tuple(c['after'][k] for k in ['crossings','bends','routed_grid_steps'])<tuple(c['before'][k] for k in ['crossings','bends','routed_grid_steps']) for c in report['changes']) and net in changed)
    original=deepcopy(old[1]);assert original==old[1]
    ck('Input geometry not mutated by optimizer',old[1]==geometry(spec)[1][1] and old[2]==geometry(spec)[1][2])
    # Supply two declared outputs on the D10 net. It must be ineligible even
    # though other independent fanouts may still improve.
    conflict=deepcopy(old);driver=next((k,p) for k,p in conflict[1].items() if k[1]=='output' and p['net']==net)
    conflict[1][driver[0][0],'output','second-output']=deepcopy(driver[1]);_,excluded=V.optimize(model,conflict)
    ck('Multiple-driver D10 is excluded from consolidation',net not in {c['net'] for c in excluded['changes']})
    ck('Exact source bytes stable during fixture',all(hashlib.sha256(Path(b['path']).read_bytes()).hexdigest()==b['sha256'] for b in source_bindings))
    receipt=dict(schema='independent-vertical-fanout-review-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),failures=[c['name'] for c in checks if not c['passed']],checks=checks,report=report,candidate_bindings=source_bindings+[bind(source)],supporting_files=[bind(Path(__file__)),bind(HERE/'review_equivalent_inputs.py'),bind(HERE/'trace_compact.py')])
    (HERE/'Vertical bus independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(passed=receipt['passed'],failures=receipt['failures'],checks=len(checks))))
if __name__=='__main__':main()
