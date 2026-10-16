"""Independent fixed-driver crossing fixture for generic equivalent-input ordering."""
import datetime,hashlib,json,sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
HERE=Path(__file__).parent;ROOT=Path('D:/Github/IBM360/ibm360ald')
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import equivalent_input_order as E
import render_composite_card as R
import compact_terminations as C
import generate_card as G
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf8'))
def bind(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def geometry(spec):
    netof={t:i for i,n in enumerate(spec['nets']) for t in n}
    positions={b['portion']:{'x':b['x'],'top':b['top'],'height':b['height']} for b in spec['boxes']}
    ports={}
    for b in spec['boxes']:
        for p in b['ports']:
            point=(b['x']-(4 if p['pin'] else 1) if p['side']=='input' else b['x']+(11 if p['pin'] else 8),p['row'])
            ports[b['portion'],p['side'],p['id']]=dict(point=point,pin=p['pin'],triangle=p['triangle'],net=netof['PORT:'+b['portion']+':'+p['id']],id=p['id'])
    ext={p['pin']:dict(side=p['side'],row=p['row'],net=netof['PIN:'+p['pin']]) for p in spec['exterior_pins']}
    blocked,clearance,reserved,_=E._obstacles(positions,ports,ext,spec['canvas']['width'])
    router=R.Router(spec['canvas']['width'],spec['canvas']['height'],blocked,reserved,{(x+d,y) for x,y in clearance for d in range(-2,3)},clearance)
    _,_,layers,_=C.graph(spec)
    for key,p in ports.items():router.virtual_endpoint_directions[p['point']][p['net']].add(0 if key[1]=='input' else 2)
    for p in ext.values():router.virtual_endpoint_directions[3 if p['side']=='input' else router.width-4,p['row']][p['net']].add(2 if p['side']=='input' else 0)
    for point,nets in layers.items():
        for net,arms in nets.items():
            for arm in arms:
                dx,dy=C.D[arm];q=point[0]+dx,point[1]+dy
                if net in layers.get(q,{}):router.wires[point].setdefault(net,set()).add(R.DIRS.index((dx,dy)))
            router.by_net[net].add(point)
    model={'card_type':spec['card_type'],'portions':{b['portion']:dict(function=b['function']) for b in spec['boxes']},'signal_pins':{p['pin']:{} for p in spec['exterior_pins']},'layout_hints':{'row_step':1}}
    return model,(positions,ports,ext,router)

def back(spec,result):
    out=deepcopy(spec);_,ports,ext,router=result
    for b in out['boxes']:
        for p in b['ports']:p['row']=ports[b['portion'],p['side'],p['id']]['point'][1]
    layers=defaultdict(dict)
    for point,nets in router.wires.items():
        for net,arms in nets.items():
            if arms:layers[point][net]={['E','S','W','N'][d] for d in arms|router.virtual_endpoint_directions[point].get(net,set())}
    C.rewrite(out,layers);return out

def main():
    path=HERE/'Equivalent input crossed fixture.json';s=read(path);model,old=geometry(s);R.verify(model,old)
    result,report=E.optimize(model,old);new=back(s,result);G.build(new);checks=[]
    def ck(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    ck('Fixed internal driver fixture improves from crossing/doglegs to straight inputs',report['accepted'] and report['before']['crossings']==1 and report['after']['crossings']==0 and all(len({y for x,y in result[3].by_net[p['net']]})==1 for key,p in result[1].items() if key[0]=='A1' and key[1]=='input'),report)
    ck('Input IDs retain every pin net and decoration while only rows change',all({k:v for k,v in p.items() if k!='point'}=={k:v for k,v in old[1][key].items() if k!='point'} and p['point'][0]==old[1][key]['point'][0] for key,p in result[1].items()))
    ck('All box locations and output coordinates unchanged',result[0]==old[0] and all(p==old[1][key] for key,p in result[1].items() if key[1]=='output'))
    ck('Independent rendered terminal graph retains all four exact nets',set(trace(s))==set(trace(new)) and all(n['cycle_rank']==0 for n in trace(new).values()))
    p=next(p for b in new['boxes'] if b['portion']=='A1' for p in b['ports'] if p['id']=='input:5');b=next(b for b in new['boxes'] if b['portion']=='A1')
    ck('Unequal variant triangle follows stable input ID into new row',p['row']==9 and G.render(new,new['variants'][0])[p['row']][b['x']]=='◺' and G.render(new)[p['row']][b['x']]=='│')
    non=deepcopy(model);non['portions']['A1']['function']='AR';unchanged,r=E.optimize(non,old)
    ck('Noncommutative-labelled portion retains original input slots',not r['accepted'] and unchanged is old)
    star=deepcopy(model);star['portions']['A1']['function']='✲OR';_,r=E.optimize(star,old);ck('Open-asterisk OR uses the same generic equivalent-input rule',r['accepted'])
    ck('Input optimizer does not mutate original model or geometry',old[1]==geometry(s)[1][1] and model['portions']['A1']['function']=='A')
    receipt=dict(passed=all(c['passed'] for c in checks),failures=[c['name'] for c in checks if not c['passed']],checks=checks,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidate_bindings=[bind(ROOT/'tools/card_ald'/n) for n in ['equivalent_input_order.py','render_composite_card.py','generate_card.py','compact_terminations.py']],supporting_files=[bind(Path(__file__)),bind(path),bind(HERE/'trace_compact.py')])
    (HERE/'Equivalent input independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(passed=receipt['passed'],failures=receipt['failures'],checks=len(checks))))
if __name__=='__main__':main()
