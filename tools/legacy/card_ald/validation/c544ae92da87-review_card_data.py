import sys,json,hashlib,copy,shutil
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald'); HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import build_card_data as B, generate_card as G
FIX=HERE/'card-data-fixture/root'
checks=[]; failures=[]; details={}
def check(name,value,detail=None):
    checks.append({'name':name,'passed':bool(value),'detail':detail})
    if not value:failures.append(name)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    check('Fixture has no mutable renderer definitions',not (FIX/'json/Card-ALD/definitions').exists())
    for card in ['0141','4191','4633','4634']:
        spec,report=B.build(card,root=FIX)
        check(card+' definition generated with immutable supplements',spec is not None and report['reviewed_supplement_used'])
        if spec:
            outputs,_=G.build(spec);gold,_=G.build(read(ROOT/'json/Card-ALD/definitions'/f'{card}.json'))
            check(card+' every rendered byte equals current reviewed output',outputs==gold,{'outputs':len(outputs)})
            check(card+' provenance binds catalog and source models',len(report['provenance']['source_bindings'])>5)
        details[card]={'uncertainties':report['uncertainties'],'derived_portions':len(report['derived_model']['portions'])}
        print(card,len(report['uncertainties']),flush=True)
    # A single changed current catalog field must remain visible in fresh facts,
    # and cannot silently inherit the reviewed fact from the geometry supplement.
    path=FIX/'json/Card types current/0141.json';raw=path.read_bytes();catalog=read(path)
    occurrence=catalog['diagram_occurrences'][0];portion=occurrence['portion'];old=occurrence['circuit_identifier']
    occurrence['circuit_identifier']='U99ZZ';write(path,catalog)
    try:
        spec,report=B.build('0141',root=FIX)
        serialized=json.dumps(report)
        check('Changed catalog unit visible in raw evidence', 'U99ZZ' in serialized)
        check('Catalog versus current model mismatch flagged',any(x['kind']=='catalog facts differ from current hash-bound model' for x in report['uncertainties']))
        check('Conflicting fresh unit does not silently replace reviewed unit',next(b for b in spec['boxes'] if b['portion']==portion)['circuit_identifier']!='U99ZZ')
    finally:path.write_bytes(raw)
    catalog=read(path);new=copy.deepcopy(catalog['diagram_occurrences'][0]);new['portion']='ZZ';new['node']='ZZ';new['circuit_identifier']='U03AR';catalog['diagram_occurrences'].append(new);write(path,catalog)
    try:
        spec,report=B.build('0141',root=FIX)
        check('New catalog portion retained and flagged','ZZ' in report['derived_model']['portions'] and any('portion' in x['kind'] and 'reviewed' in x['kind'] for x in report['uncertainties']))
        check('Missing current model node explicitly flagged',any(x['kind']=='catalog node missing from current hash-bound model' for x in report['uncertainties']))
    finally:path.write_bytes(raw)
    # Change only a current page's actual net model, retaining the current
    # catalog. Rebind its private manifest to prove graph facts come from it.
    modelpath=next((FIX/'json').rglob('AP673 *.json'));modelraw=modelpath.read_bytes();manifestpath=FIX/'notes/Content data manifest.json';manifestraw=manifestpath.read_bytes()
    model=read(modelpath);model['nets'].append({'id':'INDEPENDENT_REVIEW_INJECTED','driver':'AV.output','targets':['BD.input1']});write(modelpath,model)
    manifest=read(manifestpath)
    for item in manifest['files']:
        if FIX/item['path']==modelpath:item['sha256']=hashlib.sha256(modelpath.read_bytes()).hexdigest()
    write(manifestpath,manifest)
    try:
        spec,report=B.build('0141',root=FIX)
        check('Changed hash-bound model wiring independently alters derived graph and review',any(e['source']=='A1' and e['target']=='B3' and any(v.get('page')=='AP673' for v in e['evidence']) for e in report['derived_model']['edges']) and any(u['kind']=='new derived internal connection outside reviewed nets' and u['source']=='A1' and u['target']=='B3' for u in report['uncertainties']))
    finally:modelpath.write_bytes(modelraw);manifestpath.write_bytes(manifestraw)
    overlaypath=FIX/'json/Card-ALD/build-overrides/0141.json';overlayraw=overlaypath.read_bytes();overlay=read(overlaypath)
    sample=read(FIX/'json/Card types current/0141.json')['diagram_occurrences'][0]
    correction={'page':sample['page'],'node':sample['node'],'set':{'/circuit_identifier':'U99ZZ'}}
    overlay.setdefault('source_corrections',[]).append(correction);write(overlaypath,overlay)
    try:
        spec,report=B.build('0141',root=FIX)
        check('Source correction without current model binding is rejected',any(x['kind']=='missing source correction model binding; not applied' for x in report['uncertainties']) and not any('U99ZZ' in str(c) for c in report['provenance']['source_corrections_applied']))
        correction['model_binding']={'path':str(modelpath.relative_to(FIX)).replace('\\','/'),'sha256':'0'*64};write(overlaypath,overlay)
        spec,report=B.build('0141',root=FIX)
        check('Source correction with stale model binding is rejected',any(x['kind']=='stale source correction binding; not applied' for x in report['uncertainties']) and not report['provenance']['source_corrections_applied'])
    finally:overlaypath.write_bytes(overlayraw)
    # A stale immutable supplement must be rejected, independently of current outputs.
    overlay=read(FIX/'json/Card-ALD/build-overrides/0141.json');bound=FIX/overlay['source_bindings'][0]['path'];raw=bound.read_bytes();bound.write_bytes(raw+b' ')
    try:
        spec,report=B.build('0141',root=FIX)
        check('Stale immutable reviewed input disables supplement',not report['reviewed_supplement_used'] and any(x['kind']=='reviewed supplement not applied' for x in report['uncertainties']))
    finally:bound.write_bytes(raw)
    # An actual additional family, untouched source evidence, generic route.
    for card in ['0006','0143']:
        spec,report=B.build(card,root=FIX)
        check(card+' additional family has honest private candidate or explicit review',not report['reviewed_supplement_used'] and (spec is not None or bool(report['uncertainties'])))
        if spec:
            check(card+' new spec actually renders',bool(G.build(spec)[0]))
        details[card]={'generated':bool(spec),'uncertainties':report['uncertainties']}
    spec,report=B.build('3315',root=ROOT)
    check('Real 3315 additional family derives and renders without supplements',spec is not None and not report['reviewed_supplement_used'] and bool(G.build(spec)[0]))
    details['3315']={'generated':bool(spec),'uncertainties':report['uncertainties']}
    receipt={'passed':not failures,'failures':failures,'checks':checks,'details':details,'candidate_bindings':[{'path':str(ROOT/'tools/card_ald'/n),'sha256':hashlib.sha256((ROOT/'tools/card_ald'/n).read_bytes()).hexdigest()} for n in ['build_card_data.py','generate_card.py','render_composite_card.py','card_canvas.py']]}
    write(HERE/'Card data independent preflight.json',receipt)
    print(json.dumps({'passed':not failures,'failures':failures,'checks':len(checks)}))
if __name__=='__main__':main()
