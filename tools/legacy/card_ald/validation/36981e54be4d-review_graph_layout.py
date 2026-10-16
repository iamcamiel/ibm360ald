import sys,json,copy,hashlib
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'));sys.path.insert(0,str(ROOT.parent/'tmp/ald-text/card-layout-deps'))
import graph_card_layout as L,build_card_data as B,generate_card as G
checks=[];failures=[];details={}
def check(name,result,detail=None):
    checks.append(dict(name=name,passed=bool(result),detail=detail))
    if not result:failures.append(name)
def node(function='A',ins=('B02','B03'),outs=(None,)):
    return {'function':function,'_inputs':[{'pin':p,'ref':p} for p in ins],'_outputs':[{'pin':p,'ref':p} for p in outs]}
def model(nodes,edges):return {'portions':nodes,'edges':[{'source':a,'target':b} for a,b in edges]}
def normalizednets(spec):return sorted(sorted(n) for n in spec['nets'])
def metrics(spec):
    cells={(x,s['y']):'─' for s in spec['wiring']['horizontal_segments'] for x in range(s['x1'],s['x2']+1)}
    cells.update({(m['x'],m['y']):m['symbol'] for m in spec['wiring']['marks']})
    return dict(width=spec['canvas']['width'],height=spec['canvas']['height'],crossings=sum(c=='┼' for c in cells.values()),bends=sum(c in '┌┐└┘' for c in cells.values()),wire_cells=len(cells))
def geometry_checks(card,spec,report):
    vertical=set()
    for m in spec['wiring']['marks']:
        if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and (set(m.get('arms',[]))&{'N','S'}):vertical.add((m['x'],m['y']))
    obstacles=[]
    for b in spec['boxes']:
        obstacles.extend((y,b['x'],b['x']+7) for y in range(b['top'],b['top']+b['height']))
        for p in b['ports']:
            if p.get('pin'):obstacles.append((p['row'],b['x']-3,b['x']-1) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10))
    bad=[(x,y,left,right) for x,y in vertical for yy,left,right in obstacles if y==yy and left-2<=x<=right+2]
    check(card+' independent wire/box/pinlabel clearance',not bad,bad[:10])
    check(card+' independent parallel vertical tracks gap',not any((x+1,y) in vertical for x,y in vertical))
    boxes={b['portion']:b for b in spec['boxes']}
    anchors=report['relayout']['layout_hints']['metrics']['termination_anchors']
    anchor_groups={a:sorted([r for r,aa in anchors.items() if aa==a],key=lambda r:boxes[r]['top']) for a in set(anchors.values())}
    step=spec['canvas'].get('grid_step',7);gap=report['relayout']['layout_hints'].get('row_gap',0)
    check(card+' terminating R contiguous underneath gate',all(boxes[r]['x']==boxes[a]['x'] and boxes[r]['top']==boxes[a]['top']+((boxes[a]['height']+gap+step-1)//step)*step+i*((7+gap+step-1)//step)*step for a,rs in anchor_groups.items() for i,r in enumerate(rs)))
def preview(card,rows):
    from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype('C:/Users/camie/AppData/Local/Microsoft/Windows/Fonts/JuliaMono-Regular.ttf',18)
    w=int(round(font.getlength('M')));h=24
    im=Image.new('RGB',(max(map(len,rows))*w+20,len(rows)*h+20),'white');draw=ImageDraw.Draw(im)
    for y,line in enumerate(rows):draw.text((10,10+y*h),line,font=font,fill='black')
    im.save(HERE/f'{card} graph visual.png')
def save():
    receipt={'passed':not failures,'failures':failures,'checks':checks,'details':details,'candidate_bindings':[{'path':str(ROOT/'tools/card_ald'/name),'sha256':hashlib.sha256((ROOT/'tools/card_ald'/name).read_bytes()).hexdigest()} for name in ['graph_card_layout.py','build_card_data.py','render_composite_card.py','generate_card.py','card_canvas.py','requirements.txt']]}
    (HERE/'Graph layout independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    translated=json.loads((ROOT/'json/Card-ALD/definitions/0141.json').read_text(encoding='utf-8'));translated['canvas']['height']+=1
    for b in translated['boxes']:
        b['top']+=1
        for p in b['ports']:p['row']+=1
    for segment in translated['wiring']['horizontal_segments']:segment['y']+=1
    for item in translated['wiring']['marks']:item['y']+=1
    for item in translated['exterior_pins']+translated['annotations']:item['row']+=1
    try:G.validate(translated);reject=False
    except AssertionError:reject=True
    check('Legacy absent grid_step preserves seven-row constraint',reject)
    translated['canvas']['grid_step']=1
    check('Explicit free-row layout accepts nonmultiples of seven',bool(G.validate(translated)))
    translated['canvas']['grid_step']=2
    try:G.validate(translated);reject=False
    except AssertionError:reject=True
    check('Unsupported row grid step rejected',reject)
    m=model({'01':node(),'02':node(),'03':node('AR',('B02',),('D02',))},[('01','02'),('02','03'),('03','01')]);before=copy.deepcopy(m);p=L.plan(m)
    check('Cycle SCC detected and feedback arc retained explicitly',len(p['metrics']['feedback_components'])==1 and bool(p['metrics']['feedback_edges']))
    check('Planner leaves electrical model unchanged',m==before)
    check('Planner deterministic across deep copies',p==L.plan(copy.deepcopy(m)))
    check('All synthetic tops on configured integer row grid',all(isinstance(y,int) and y%p.get('row_step',7)==0 for y in p['tops'].values()))
    m=model({'01':node('AR',('B02',)), '07':node(),'08':node(),'12':node('OR',(None,None)), '42':node('R',('B02',),())},[('01','08'),('07','12'),('08','12')]);p=L.plan(m)
    check('Clockless sibling gate aligned with clocked gate',p['ranks']['07']==p['ranks']['08'] and p['tops']['08']==p['tops']['07']+7)
    anchor=p['metrics']['termination_anchors']['42']
    check('Input terminating resistor immediately beneath related gate',p['ranks']['42']==p['ranks'][anchor] and p['tops']['42']==p['tops'][anchor]+7,{'anchor':anchor,'plan':p})
    m=model({f'{i:02}':node() for i in range(1,8)}, [('01','07'),('02','03'),('03','04'),('04','05'),('05','06'),('06','07')]);p=L.plan(m)
    check('Source-only driver deferred toward first consumer when space available',p['tops']['01']<=p['tops']['07'] and abs(p['tops']['01']-p['tops']['07'])<=14,p['metrics']['deferred_input_drivers'])
    for card in ['0141','4191','4633','4634']:
        spec,report=B.build(card,root=ROOT,relayout=True)
        check(card+' generic graph route produced validated candidate',spec is not None,report.get('relayout',{}).get('routing_attempts'))
        details[card]={'relayout':report.get('relayout'),'uncertainties':report['uncertainties']}
        if spec:
            old=json.loads((ROOT/'json/Card-ALD/definitions'/f'{card}.json').read_text(encoding='utf-8'))
            check(card+' exact terminal partition preserved',normalizednets(spec)==normalizednets(old))
            oldports={b['portion']:{p['id']:(p['side'],p['pin'],p['triangle']) for p in b['ports']} for b in old['boxes']}
            newports={b['portion']:{p['id']:(p['side'],p['pin'],p['triangle']) for p in b['ports']} for b in spec['boxes']}
            check(card+' stable canonical port IDs and meanings',oldports==newports)
            check(card+' box tops configured row grid',all((b['top']-spec['canvas']['grid_origin'])%spec['canvas'].get('grid_step',7)==0 for b in spec['boxes']))
            outputs,validation=G.build(spec)
            check(card+' full variants project to exact common geometry',len(outputs)==len(old.get('variants',[]))+1)
            geometry_checks(card,spec,report)
            (HERE/f'{card} graph candidate.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            (HERE/f'{card} graph candidate.txt').write_bytes(outputs[f'{card}.txt'])
            details[card]['new_canvas']=spec['canvas'];details[card]['old_canvas']=old['canvas'];details[card]['layout_validation']=spec['layout_validation']
            details[card]['independent_metrics']={'before':metrics(old),'after':metrics(spec)}
            preview(card,outputs[f'{card}.txt'].decode('utf-8').splitlines())
        save();print(card,bool(spec),flush=True)
    save();print(json.dumps({'passed':not failures,'failures':failures,'checks':len(checks)}))
if __name__=='__main__':main()
