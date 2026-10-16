"""Independently review cumulative NetworkX free rows then compact termination previews."""
import datetime,hashlib,json,sys
from copy import deepcopy
from pathlib import Path
HERE=Path(__file__).parent;ROOT=Path('D:/Github/IBM360/ibm360ald');STAGE=ROOT.parent/'tmp/ald-text/ald/card-data/compact-r-free-rows'
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import compact_terminations as C
import generate_card as G
import build_card_data as B
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def semantics(s):
    return sorted((b['portion'],b['function'],b['circuit_identifier'],tuple(sorted((p['id'],p['side'],p['pin'],p['triangle']) for p in b['ports']))) for b in s['boxes'])
def records(v):
    if isinstance(v,dict):
        if set(v)>={'path','sha256'}:yield v
        for c in v.values():yield from records(c)
    elif isinstance(v,list):
        for c in v:yield from records(c)

def core_edges(graph,compact_parts):
    edges=set(graph['edge_set'])
    for seed,terms in graph['terminal_nodes'].items():
        if not any(t.startswith('PIN:') or t.startswith('PORT:') and t.split(':')[1] in compact_parts for t in terms):continue
        previous=None;node=seed
        while True:
            onward=graph['adjacency'][node]-({previous} if previous else set())
            if len(onward)!=1:break
            other=next(iter(onward));edges.discard(tuple(sorted((node,other))));previous,node=node,other
            if node in graph['terminal_nodes'] or len(graph['adjacency'][node])!=2:break
    return {tuple(sorted((a[:2],b[:2]))) for a,b in edges}

def main():
    tools=[ROOT/'tools/card_ald'/n for n in ['generate_card.py','compact_terminations.py','build_card_data.py','graph_card_layout.py','render_composite_card.py','card_canvas.py','equivalent_input_order.py','vertical_fanout_order.py']]
    before=[bind(p) for p in tools];checks=[];fail=[];bindings=[];details={};all_outputs={};defaults={}
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:fail.append(name)
    for card,expected in [('0141',0),('4191',8),('4633',0),('4634',13)]:
        source=ROOT/'json/Card-ALD/definitions'/(card+'.json');intermediate=STAGE/card/(card+' relayout input.json');final=STAGE/card/(card+'.json');evidence=STAGE/card/(card+' relayout evidence.json')
        old=read(source);base=read(intermediate);s=read(final);e=read(evidence);built,val=G.build(s);all_outputs.update(built);defaults.update(G.build(old)[0])
        fresh,report=C.transform(base)
        check(card+' fresh compact transform reproduces all cumulative preview bytes',G.build(fresh)[0]==built and all(s['provenance']['compact_termination_preview'][k]==v for k,v in report.items()))
        again,again_report=C.transform(s)
        check(card+' already-compact definition regenerates idempotently',G.build(again)[0]==built and again['boxes']==s['boxes'] and again['nets']==s['nets'])
        cleanup=report['exterior_termination_cleanup']['changes']
        check(card+' passive-leaf cleanup keeps only strict visible improvements',all(tuple(c['after_crossings_bends_cells'])<tuple(c['before_crossings_bends_cells']) and all(stub['point'][1]==c['row']+1 for stub in c['stubs']) for c in cleanup),cleanup)
        check(card+' retains published electrical units/functions/ports/polarities',semantics(old)==semantics(base)==semantics(s))
        check(card+' all stable terminal partitions and canonical/variant metadata retained',old['nets']==base['nets']==s['nets'] and old['variants']==base['variants']==s['variants'] and old['power_contacts']==base['power_contacts']==s['power_contacts'] and sorted((p['pin'],p['side']) for p in old['exterior_pins'])==sorted((p['pin'],p['side']) for p in s['exterior_pins']))
        offgrid=[dict(portion=b['portion'],top=b['top']) for b in s['boxes'] if (b['top']-s['canvas']['grid_origin'])%7]
        check(card+' seven-high boxes actually occupy free rows, not former grid',base['canvas']['grid_step']==s['canvas']['grid_step']==1 and bool(offgrid) and all(b['height']==max(7,sum(p['side']=='input' for p in b['ports'])+2) for b in s['boxes']),offgrid)
        if old['canvas'].get('grid_step',7)==1:
            check(card+' accepted free-row geometry reused exactly',all(old[k]==base[k] for k in ['canvas','boxes','wiring','exterior_pins','nets','variants']))
        else:
            check(card+' legacy grid upgraded by universal v2 planner with row_step1',e['relayout']['layout_hints']['algorithm']=='networkx-layered-ald-v2' and e['relayout']['layout_hints']['row_step']==1 and e['relayout']['terminal_partition_identity_verified'])
        check(card+' compact notation preserves planned boxes/ports and exterior identities',base['boxes']==[{k:v for k,v in b.items() if k!='compact_termination'} for b in s['boxes']] and base['canvas']==s['canvas'] and sorted((p['pin'],p['side'],p['x']) for p in base['exterior_pins'])==sorted((p['pin'],p['side'],p['x']) for p in s['exterior_pins']))
        check(card+' expected shared termination count and124family outputs reproducible',val['compact_terminations']==expected and all((STAGE/card/name).read_bytes()==raw for name,raw in built.items()))
        overlay_path=ROOT/'json/Card-ALD/build-overrides'/(card+'.json');overlay=read(overlay_path)
        overlay['layout']={k:deepcopy(s[k]) for k in ['canvas','boxes','wiring','exterior_pins','annotations']}
        overlay['approved_variants']=deepcopy(s['variants']);overlay['canonical_line_ending']=s['canonical_line_ending']
        overlay['source_bindings'].append(bind(final))
        private=HERE/'private-build-roundtrips'/(card+' reviewed layout.json');private.parent.mkdir(exist_ok=True);private.write_text(json.dumps(overlay,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        regenerated,build_report=B.build(card,overrides_path=private)
        check(card+' full source-catalog/model builder reproduces every compact preview byte',regenerated is not None and G.build(regenerated)[0]==built)
        bindings.extend([overlay_path,private])
        a,b=trace(base),trace(s);parts={x['portion'] for x in s['boxes'] if 'compact_termination' in x}
        check(card+' independently separated acyclic nets retain exact identities',set(a)==set(b)=={tuple(n) for n in old['nets']} and all(n['cycle_rank']==0 for n in b.values()))
        functional=lambda terms:[t for t in terms if t.startswith('PORT:') and t.split(':')[1] not in parts]
        check(card+' all multi-gate core routes preserved outside R/exterior leaves',all(core_edges(a[n],parts)==core_edges(b[n],parts) for n in a if len(functional(n))>1))
        labels=0;triangles=0
        for box in s['boxes']:
            if 'compact_termination' not in box:continue
            c=box['compact_termination'];x,y=c['point'];p=box['ports'][0]
            check(card+' '+box['portion']+' reserves3variantgrowthcells',c['label_width']>=len(G.termination_label(box))+3)
            for variant in [None]+s['variants']:
                text=G.termination_label(box,variant);change=(variant or {}).get('box_overrides',{}).get(box['portion'],{});tri=change.get('port_triangles',{}).get(p['id'],p['triangle']);label=('◺' if tri else '└')+text.ljust(c['label_width'])
                check(card+' '+box['portion']+' variant'+str((variant or {}).get('number',0))+' same terminal, full text and preserved triangle',G.render(s,variant)[y].ljust(s['canvas']['width'])[x:x+len(label)]==label)
                labels+=1;triangles+=bool(tri)
        vertical={(m['x'],m['y']) for m in s['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')};obs=[]
        for box in s['boxes']:
            if 'compact_termination' in box:
                c=box['compact_termination'];x,y=c['point'];obs.append((y,x+1,x+c['label_width'],(x,y)));continue
            obs.extend((y,box['x'],box['x']+7,None) for y in range(box['top'],box['top']+box['height']))
            for p in box['ports']:
                if p['pin']:obs.append((p['row'],box['x']-3,box['x']-1,None) if p['side']=='input' else (p['row'],box['x']+8,box['x']+10,None))
        check(card+' independent2blanklabel and1parallelverticalclearance',all(not(y==yy and l-2<=x<=r+2) for x,y in vertical for yy,l,r,own in obs if own!=(x,y)) and not any((x+1,y) in vertical for x,y in vertical))
        if card=='4191':
            meta=e['relayout']['layout_hints']['metrics'];boxes={b['portion']:b for b in s['boxes']};profiles=[]
            for m in meta['convergent_modules']:
                sources=[boxes[p] for p in m['parallel_sources']];collector=boxes[m['collector']]
                profiles.append(dict(collector=m['collector'],center=collector['top']+3,span_center=(min(p['top'] for p in sources)+max(p['top']+p['height']-1 for p in sources))/2))
            check('4191 four nested gate/collector modules remain centered and separate',len(profiles)==4 and all(p['center']==p['span_center'] for p in profiles) and not any({'12','18','24'}<=set(group) for group in meta['sibling_groups']),profiles)
            followers={'12':['31','32'],'18':['33','34'],'24':['36','37'],'30':['38','39']}
            followercenters={part:(min(boxes[f]['top'] for f in fs)+max(boxes[f]['top']+boxes[f]['height']-1 for f in fs))/2 for part,fs in followers.items()}
            check('4191 output-buffer pairs remain beside their own collectors',all(abs(center-(boxes[part]['top']+3))<=1 for part,center in followercenters.items()),followercenters)
            def pin_nodes(pin):
                component=next(graph for terms,graph in b.items() if 'PIN:'+pin in terms)
                return {node[:2] for edge in component['edge_set'] for node in edge}
            check('4191 B08/B10 exterior-wire crossing removed without swapping pins',not pin_nodes('B08')&pin_nodes('B10') and next(p['pin'] for p in next(z for z in s['boxes'] if z['portion']=='03')['ports'] if p['side']=='input')=='B08' and 'B10' in {p['pin'] for p in next(z for z in s['boxes'] if z['portion']=='08')['ports']})
            first=boxes['07'];arrival={p['pin']:p['row'] for p in first['ports'] if p['side']=='input'};rows=G.render(s)
            check('4191 portion07 equivalent inputs reordered with straight final approaches',arrival['J12']<arrival['D12'] and all(set(rows[arrival[pin]][first['x']-12:first['x']-3])<=set('─◇┼') for pin in ['J12','D12']),arrival)
            check('4191 R01 hangs directly beneath the straight D12 input net',boxes['01']['compact_termination']['point'][1]==arrival['D12']+1)
            d10terms,d10graph=next((terms,graph) for terms,graph in b.items() if 'PIN:D10' in terms)
            tracks=sorted({left[0] for left,right in d10graph['edge_set'] if left[0]==right[0] and left[1]!=right[1]})
            check('4191 exact reported D10 fanout has one vertical trunk and every original branch',tracks and len(tracks)==1 and {'PORT:12:output:3','PORT:31:input:3','PORT:32:input:3','PORT:35:input:1','PIN:D10'}==set(d10terms),tracks)
        provenance=base['provenance'];check(card+' boundary and upper/lower fanout optimization remain in pipeline','boundary_pin_optimization' in provenance and 'fanout_trunk_optimization' in provenance)
        details[card]=dict(canvas=s['canvas'],validation=val,off_grid_box_tops=offgrid,label_variant_checks=labels,triangle_variants=triangles,net_count=len(b))
        bindings.extend([source,intermediate,final,evidence,STAGE/card/'Compact termination report.json']+[STAGE/card/name for name in built])
    golden={p['name']:p['sha256'] for p in read(HERE/'Published diagram baseline hashes.json')['files']}
    check('All124 published diagrams unchanged and all124 cumulative previews generated',len(defaults)==len(all_outputs)==124 and all(hashlib.sha256(raw).hexdigest()==golden[name]==sha(ROOT/'Card-ALD'/name) for name,raw in defaults.items()))
    fixture=read(HERE/'Shared and standalone R fixture.json');f,report=C.transform(fixture);G.build(f)
    check('Shared/standalone conditional fixture still respected', 'compact_termination' in f['boxes'][1] and 'compact_termination' not in f['boxes'][2] and set(trace(f))=={tuple(n) for n in fixture['nets']})
    def rejection(name,edit):
        altered=deepcopy(f);edit(altered)
        try:G.build(altered)
        except (AssertionError,ValueError,KeyError,IndexError,TypeError) as error:check(name,True,str(error));return
        check(name,False,'Invalid compact fixture accepted')
    rejection('Reservation smaller than canonical label plus3 rejected',lambda s:s['boxes'][1]['compact_termination'].update(label_width=len(G.termination_label(s['boxes'][1]))+2))
    rejection('Compact geometry override in numbered variant rejected',lambda s:s['variants'][0]['box_overrides']['02'].update(compact_termination={'point':[1,2],'label_width':15}))
    def intrude(s):
        compact=s['boxes'][1]['compact_termination'];x,y=compact['point'];s['annotations'].append(dict(x=x+compact['label_width'],row=y,text='X'))
    rejection('Other text cannot occupy reserved variant growth cells',intrude)
    rejection('Explicit compaction of standalone R rejected',lambda s:s['boxes'][2].update(compact_termination=deepcopy(s['boxes'][1]['compact_termination'])))
    incompatible=deepcopy(fixture);incompatible['variants'][0]['box_overrides']['02']['function']='A';non,r=C.transform(incompatible)
    check('Canonical R with non-R alternate remains a full box',not next(c['eligible'] for c in r['classification'] if c['portion']=='02') and 'compact_termination' not in non['boxes'][1])
    legacy=deepcopy(fixture);free=deepcopy(fixture);free['canvas']['grid_step']=1
    check('Automatic layout policy upgrades grid7 but preserves accepted grid1',C.layout_policy(legacy)['action']=='relayout' and C.layout_policy(free)['action']=='reuse-free')
    check('Explicit force and keep behavior is universal',C.layout_policy(free,'force')['action']=='relayout' and C.layout_policy(legacy,'keep')['action']=='keep-explicit')
    calls=[];original=B.build
    def planned(card_type,root=None,relayout=False):
        calls.append((card_type,root,relayout));return deepcopy(free),{'independent_fixture':True}
    try:
        B.build=planned
        auto,e,origin=C.prepare_layout('9902',legacy);auto_free,_,_=C.prepare_layout('9902',free);forced,_,_=C.prepare_layout('9902',free,'force');kept,_,_=C.prepare_layout('9902',legacy,'keep')
        check('Unknown-card prepare pipeline calls builder only for legacy/forced planning',calls==[('9902',C.ROOT,True),('9902',C.ROOT,True)] and auto==forced==free and auto_free==free and kept==legacy and auto_free is not free and kept is not legacy)
    finally:B.build=original
    check('All current source bytes stable throughout review',all(sha(Path(b['path']))==b['sha256'] for b in before))
    inputproof=read(HERE/'Equivalent input independent review.json');check('Independent fixed-driver input-order fixture passes8checks on current sources',inputproof['passed'] and len(inputproof['checks'])==8 and all(sha(Path(b['path']))==b['sha256'] for b in inputproof['candidate_bindings']))
    verticalproof=read(HERE/'Vertical bus independent review.json');check('Independent actual historical D10 fixture passes9checks on current sources',verticalproof['passed'] and len(verticalproof['checks'])==9 and all(sha(Path(b['path']))==b['sha256'] for b in verticalproof['candidate_bindings']))
    freeze_paths=list(STAGE.glob('*freeze.json'));assert len(freeze_paths)==1,freeze_paths
    frozen=freeze_paths[0];fr=read(frozen);check('Final candidate freeze all hashes current',all(sha(Path(r['path']))==r['sha256'] for r in records(fr)));bindings.extend([frozen]+[Path(r['path']) for r in records(fr)])
    histories=sorted(p for p in (HERE/'history').rglob('*') if p.is_file())
    receipt=dict(schema='independent-cumulative-free-row-compact-R-review-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=not fail,failures=fail,checks=checks,cards=details,candidate_bindings=[bind(p) for p in tools+bindings],supporting_files=[bind(Path(__file__)),bind(HERE/'trace_compact.py'),bind(HERE/'review_equivalent_inputs.py'),bind(HERE/'Equivalent input crossed fixture.json'),bind(HERE/'Equivalent input independent review.json'),bind(HERE/'review_vertical_bus.py'),bind(HERE/'Vertical bus independent review.json'),bind(HERE/'Shared and standalone R fixture.json'),bind(HERE/'Published diagram baseline hashes.json')]+[bind(p) for p in histories],scope='Private cumulative previews only. Published diagrams unchanged.')
    (HERE/'Cumulative free row compact R independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(passed=not fail,failures=fail,checks=len(checks))))
if __name__=='__main__':main()
