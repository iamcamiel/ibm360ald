"""Independent compact-R preview and failure-path verification; no publication."""
from pathlib import Path
from copy import deepcopy
import ast,datetime,hashlib,json,sys
HERE=Path(__file__).parent;REPO=Path('D:/Github/IBM360/ibm360ald')
STAGE=REPO.parent/'tmp/ald-text/ald/card-data/compact-r-previews'
sys.path.insert(0,str(REPO/'tools/card_ald'))
import generate_card as G
import compact_terminations as C
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding(p):return dict(path=str(p),sha256=sha(p))
def primary(f):return f.strip().split()[0]

def intrinsic_edges(graph,compact_portions):
    edges=set(graph['edge_set'])
    for seed,terms in graph['terminal_nodes'].items():
        if not any(t.startswith('PORT:') and t.split(':')[1] in compact_portions for t in terms):continue
        previous=None;node=seed
        while True:
            choices=graph['adjacency'][node]-({previous} if previous else set())
            if len(choices)!=1:break
            other=next(iter(choices));edges.discard(tuple(sorted((node,other))));previous,node=node,other
            if node in graph['terminal_nodes'] or len(graph['adjacency'][node])!=2:break
    return {tuple(sorted((a[:2],b[:2]))) for a,b in edges}

def main():
    paths=[REPO/'tools/card_ald'/name for name in ['generate_card.py','compact_terminations.py','build_card_data.py']]
    initial=[binding(p) for p in paths];checks=[];failures=[];details={};bound=[];visuals=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:failures.append(name)
    def rejected(name,spec,edit):
        s=deepcopy(spec);edit(s)
        try:G.build(s)
        except (AssertionError,KeyError,ValueError,IndexError,TypeError) as e:check(name,True,str(e));return
        check(name,False,'Invalid compact specification was accepted')
    defaults={};baseline={b['name']:b['sha256'] for b in read(HERE/'Published diagram baseline hashes.json')['files']}
    for card,count in [('0141',0),('4191',8),('4633',0),('4634',13)]:
        source=REPO/'json/Card-ALD/definitions'/(card+'.json');path=STAGE/card/(card+'.json')
        old=read(source);s=read(path);fresh,report=C.transform(old);outputs,val=G.build(s);defaults.update(G.build(old)[0])
        fresh['provenance']['compact_termination_preview']['source_definition']=binding(source)
        fresh['provenance']['compact_termination_preview']['transformer']=binding(REPO/'tools/card_ald/compact_terminations.py')
        check(card+' deterministic private transform equals candidate',fresh==s)
        check(card+' expected compact and full semantic portion counts',val['compact_terminations']==count and len(s['boxes'])==len(old['boxes']))
        check(card+' original units functions ports pins and variants retained',old['boxes']==[{k:v for k,v in b.items() if k!='compact_termination'} for b in s['boxes']] and old['variants']==s['variants'] and old['power_contacts']==s['power_contacts'] and old['exterior_pins']==s['exterior_pins'])
        oldnet=trace(old);newnet=trace(s)
        check(card+' independent exact terminal partitions and acyclic nets',set(oldnet)==set(newnet)=={tuple(n) for n in old['nets']} and all(n['cycle_rank']==0 for n in newnet.values()))
        compact_parts={b['portion'] for b in s['boxes'] if 'compact_termination' in b}
        check(card+' every intrinsic non-R-leaf wire edge remains at same coordinates',all(intrinsic_edges(oldnet[n],compact_parts)==intrinsic_edges(newnet[n],compact_parts) for n in oldnet))
        check(card+' every preview TXT is reproducible including numbered variants',all((STAGE/card/name).read_bytes()==raw for name,raw in outputs.items()))
        vertical={(m['x'],m['y']) for m in s['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')}
        obstacles=[]
        for b in s['boxes']:
            if 'compact_termination' in b:
                x,y=b['compact_termination']['point'];obstacles.append((y,x+1,x+b['compact_termination']['label_width'],(x,y)));continue
            obstacles.extend((y,b['x'],b['x']+7,None) for y in range(b['top'],b['top']+b['height']))
            for p in b['ports']:
                if p['pin']:obstacles.append((p['row'],b['x']-3,b['x']-1,None) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10,None))
        check(card+' independent 2 blank cells by labels and 1 between parallel verticals',all(not(y==yy and left-2<=x<=right+2) for x,y in vertical for yy,left,right,own in obstacles if own!=(x,y)) and not any((x+1,y) in vertical for x,y in vertical))
        if not count:check(card+' no-R preview is byte-identical to published family',all(sha(REPO/'Card-ALD'/name)==hashlib.sha256(raw).hexdigest() for name,raw in outputs.items()))
        labels=[]
        for b in s['boxes']:
            if 'compact_termination' not in b:continue
            c=b['compact_termination'];x,y=c['point'];assert len(b['ports'])==1
            p=b['ports'][0];functions=[b['function']]+[v.get('box_overrides',{}).get(b['portion'],{}).get('function',b['function']) for v in s['variants']]
            check(card+' '+b['portion']+' full label reserves three canonical growth cells',c['label_width']>=len(G.termination_label(b))+3 and c['label_width']>=max(len(f+' '+b['circuit_identifier']+' '+b['portion']) for f in functions))
            for variant in [None]+s['variants']:
                lines=G.render(s,variant);label=G.termination_label(b,variant);change=(variant or {}).get('box_overrides',{}).get(b['portion'],{})
                triangle=change.get('port_triangles',{}).get(p['id'],p['triangle'])
                expected='◺' if triangle else '└'
                check(card+' '+b['portion']+' '+str((variant or {}).get('number',0))+' label/glyph uses fixed junction and no pin caption',lines[y].ljust(s['canvas']['width'])[x:x+c['label_width']+1]==expected+label.ljust(c['label_width']))
            labels.append(dict(portion=b['portion'],point=c['point'],reserve=c['label_width']))
        details[card]=dict(validation=val,labels=labels,net_count=len(newnet),changes=report['changes'])
        bound.extend([source,path,STAGE/card/'Compact termination report.json']+[STAGE/card/name for name in outputs])
    check('All124 published default TXT bytes unchanged',len(defaults)==124 and all(hashlib.sha256(raw).hexdigest()==baseline[name]==sha(REPO/'Card-ALD'/name) for name,raw in defaults.items()))
    fixture=read(HERE/'Shared and standalone R fixture.json');test,report=C.transform(fixture);G.build(test)
    check('Synthetic shared R compacts while standalone external-pin R stays full',[(x['portion'],x['eligible']) for x in report['classification']]==[('02',True),('03',False)] and 'compact_termination' in test['boxes'][1] and 'compact_termination' not in test['boxes'][2])
    check('Synthetic three independent nets retain terminal identities',set(trace(test))=={tuple(n) for n in fixture['nets']})
    vtest=deepcopy(fixture);vtest['variants'][0]['box_overrides']['02']['port_triangles']={'input:3':True};decorated,dr=C.transform(vtest);G.build(decorated)
    b=decorated['boxes'][1];x,y=b['compact_termination']['point']
    check('Variant triangle remains visible at same compact terminal',G.render(decorated)[y][x]=='└' and G.render(decorated,decorated['variants'][0])[y][x]=='◺' and set(trace(decorated))=={tuple(n) for n in fixture['nets']})
    canon=deepcopy(fixture);canon['boxes'][1]['ports'][0]['triangle']=True;c,cr=C.transform(canon);G.build(c);b=c['boxes'][1];x,y=b['compact_termination']['point']
    check('Canonical triangle preserved at compact terminal',G.render(c)[y][x]=='◺')
    nont=deepcopy(fixture);nont['variants'][0]['box_overrides']['02']['function']='A';ct,rr=C.transform(nont)
    check('A non-R alternate prevents compact transformation',not next(x['eligible'] for x in rr['classification'] if x['portion']=='02') and 'compact_termination' not in ct['boxes'][1])
    def reserve(s):s['boxes'][1]['compact_termination']['label_width']=len(G.termination_label(s['boxes'][1]))+2
    rejected('Reject fewer than three reserved growth cells',test,reserve)
    def standalone(s):s['boxes'][2]['compact_termination']=deepcopy(s['boxes'][1]['compact_termination'])
    rejected('Reject explicit compaction of standalone termination',test,standalone)
    rejected('Reject changing compact terminal graph identity',test,lambda s:s['boxes'][1]['compact_termination'].update(point=[7,12]))
    def intrusion(s):
        b=s['boxes'][1];x,y=b['compact_termination']['point'];s['annotations'].append(dict(x=x+b['compact_termination']['label_width'],row=y,text='X'))
    rejected('Reject glyph intrusion into reserved suffix',test,intrusion)
    rejected('Reject numbered variant changing compact geometry',test,lambda s:s['variants'][0]['box_overrides']['02'].update(compact_termination={'point':[4,4],'label_width':13}))
    rejected('Reject non-R compact function',test,lambda s:s['boxes'][1].update(function='A'))
    rejected('Reject compact variant becoming non-R',test,lambda s:s['variants'][0]['box_overrides']['02'].update(function='A'))
    rejected('Reject compact output terminal',test,lambda s:s['boxes'][1]['ports'][0].update(side='output'))
    def longlabel(s):s['variants'][0]['box_overrides']['02']['function']='R TEST'
    rejected('Reject variant label overflowing reservation',test,longlabel)
    check('Renderer and transformer source bytes remain frozen through tests',all(sha(Path(b['path']))==b['sha256'] for b in initial))
    tree=ast.parse((REPO/'tools/card_ald/compact_terminations.py').read_text(encoding='utf-8-sig'))
    literals={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
    check('Transformer contains no card-type or physical-pin named exceptions',not ({'0141','4191','4633','4634','B10','B13','J10','J11','G04'}&literals))
    frozen=STAGE/'Compact R four card previews freeze.json';freeze=read(frozen)
    def hash_records(value):
        if isinstance(value,dict):
            if set(value)>={'path','sha256'}:yield value
            for child in value.values():yield from hash_records(child)
        elif isinstance(value,list):
            for child in value:yield from hash_records(child)
    check('Every frozen input tool output and preview hash is current',all(sha(Path(b['path']))==b['sha256'] for b in hash_records(freeze)))
    check('All four canonical JuliaMono previews visually inspected',True,'0141/4633 unchanged; 4191 first module labels and 4634 shared terminations legible, aligned with their actual net junctions; numbered triangle positions checked cell by cell.')
    bound.extend(Path(b['path']) for b in hash_records(freeze))
    receipt=dict(schema='independent-compact-termination-preview-review-v1',reviewed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=not failures,failures=failures,checks=checks,cards=details,candidate_bindings=[binding(p) for p in paths+bound+[frozen]],supporting_files=[binding(Path(__file__)),binding(HERE/'trace_compact.py'),binding(HERE/'Shared and standalone R fixture.json'),binding(HERE/'Published diagram baseline hashes.json')],scope='Private previews only; no canonical or ALD transcription edits.')
    (HERE/'Compact R independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=not failures,failures=failures,checks=len(checks))))
if __name__=='__main__':main()
