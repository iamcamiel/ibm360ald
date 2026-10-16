"""Read-only verification after guarded four-card compact/free-row publication."""
import datetime,hashlib,json,sys,csv
from pathlib import Path
HERE=Path(__file__).parent;ROOT=Path('D:/Github/IBM360/ibm360ald');STAGE=ROOT.parent/'tmp/ald-text/ald/card-data/compact-r-free-rows'
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import build_card_data as B
import generate_card as G
import compact_terminations as C
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def boxes_by_id(spec):
    return {b['portion']:{k:v for k,v in b.items() if k!='ports'}|{'ports':{p['id']:p for p in b['ports']}} for b in spec['boxes']}
def records(value):
    if isinstance(value,dict):
        if set(value)>={'path','sha256'}:yield value
        for v in value.values():yield from records(v)
    elif isinstance(value,list):
        for v in value:yield from records(v)
def main():
    checks=[];details={};expected={};bindings=[]
    def ck(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    frozen=STAGE/'Final cumulative four card previews freeze.json';freeze=read(frozen)
    fr_artifacts=[r for r in records(freeze) if Path(r['path']).is_relative_to(STAGE)]
    ck('Every frozen candidate/evidence/preview artifact remains byte-identical',all(sha(Path(r['path']))==r['sha256'] for r in fr_artifacts))
    for card,count in [('0141',0),('4191',8),('4633',0),('4634',13)]:
        accepted=STAGE/card/(card+'.json');definition=ROOT/'json/Card-ALD/definitions'/(card+'.json');overlay=ROOT/'json/Card-ALD/build-overrides'/(card+'.json')
        prior=read(accepted);current=read(definition);outputs,val=G.build(current);frozen_outputs=G.build(prior)[0];expected.update(frozen_outputs)
        ck(card+' all published canonical/variant bytes equal frozen accepted files',outputs==frozen_outputs and all((ROOT/'Card-ALD'/name).read_bytes()==raw==(STAGE/card/name).read_bytes() for name,raw in outputs.items()))
        actual,report=B.build(card)
        ck(card+' default source/catalog/model builder and renderer reproduce all published bytes',actual is not None and G.build(actual)[0]==frozen_outputs)
        again,compact_report=C.transform(current)
        ck(card+' compact regeneration is idempotent after publication',G.build(again)[0]==frozen_outputs)
        ck(card+' compact metadata/reserved fields and all numbered variants preserved',val['compact_terminations']==count and boxes_by_id(current)==boxes_by_id(prior) and current['variants']==prior['variants'] and current['canvas']==prior['canvas'] and current['canvas']['grid_step']==1)
        net=trace(current);ck(card+' independently traced electrical net trees remain accepted',set(net)=={tuple(n) for n in prior['nets']} and all(n['cycle_rank']==0 for n in net.values()))
        genpath=ROOT/'notes/Card-ALD/Generation'/(card+'.json');gen=read(genpath)
        ck(card+' generation receipt binds current definition renderer and every drawing',sha(ROOT/gen['definition']['path'])==gen['definition']['sha256'] and sha(ROOT/gen['renderer']['path'])==gen['renderer']['sha256'] and all(sha(ROOT/e['path'])==e['sha256'] for e in gen['files']) and len(gen['files'])==len(outputs) and gen['diagram_sha256']==hashlib.sha256(outputs[card+'.txt']).hexdigest())
        modelpath=ROOT/'json/Card-ALD'/(card+'.json');model=read(modelpath)
        ck(card+' current model points to the verified canonical drawing',model['drawing_sha256']==gen['diagram_sha256'] and model['render_definition']==gen['definition'])
        details[card]=dict(drawings=len(outputs),compact_terminations=count,canvas=current['canvas'],nets=len(net))
        bindings.extend([accepted,definition,overlay,genpath,modelpath]+[ROOT/'Card-ALD'/name for name in outputs])
    sourcebaseline=HERE/'ALD source baseline before card promotion.json';baseline=read(sourcebaseline);now={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in (ROOT/'ALD').rglob('*') if p.is_file()}
    ck('All2329 source ALD files remain exactly unchanged',now=={e['path']:e['sha256'] for e in baseline['files']},dict(files=len(now)))
    inventorypath=ROOT/'notes/Card-ALD/Universal card diagrams publication.json';inventory=read(inventorypath)
    ck('Current inventory binds all124 accepted drawings',len(inventory['published_files'])==len(expected)==124 and all(sha(ROOT/e['path'])==e['sha256'] for e in inventory['published_files']))
    csvpath=ROOT/'csv/Card-ALD/Notation variants.csv'
    with csvpath.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    ck('Notation CSV hashes match every listed current variant',all(row['file'] in expected and row['sha256']==hashlib.sha256(expected[row['file']]).hexdigest() for row in rows),dict(rows=len(rows)))
    bindings.extend([frozen,sourcebaseline,inventorypath,csvpath]+[ROOT/'tools/card_ald'/name for name in ['build_card_data.py','generate_card.py','compact_terminations.py','graph_card_layout.py','render_composite_card.py','equivalent_input_order.py','vertical_fanout_order.py','card_canvas.py']]+[Path(r['path']) for r in fr_artifacts])
    receipt=dict(schema='independent-published-cumulative-card-review-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),failures=[c['name'] for c in checks if not c['passed']],checks=checks,cards=details,candidate_bindings=[bind(p) for p in bindings],supporting_files=[bind(Path(__file__)),bind(HERE/'trace_compact.py'),bind(sourcebaseline)],scope='Read-only published verification; only this private proof file is written.')
    (HERE/'Published cumulative card independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(passed=receipt['passed'],failures=receipt['failures'],checks=len(checks))))
if __name__=='__main__':main()
