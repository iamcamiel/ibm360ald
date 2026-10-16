"""Adopt an independently reviewed layout without changing its card circuit."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import build_card_data
from generate_card import ROOT, build, digest, read, write_protected


def write_json(path,value):
    write_protected(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def semantics(spec):
    return {b['portion']:{'unit':b['circuit_identifier'],'function':b['function'],
            'ports':sorted((p['id'],p['side'],p['pin'],p['triangle']) for p in b['ports'])} for b in spec['boxes']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_type');parser.add_argument('--definition',type=Path,required=True)
    parser.add_argument('--review',type=Path,required=True)
    args=parser.parse_args();candidate=read(args.definition);card=candidate['card_type']
    assert args.card_type==card
    approval=read(args.review)
    assert approval['passed'] is True and not approval['failures']
    bindings=approval['candidate_bindings']
    if isinstance(bindings,dict):bindings=list(bindings.values())
    assert any(Path(e['path']).resolve()==args.definition.resolve() and e['sha256']==digest(args.definition.read_bytes()) for e in bindings)
    for binding in bindings:
        assert digest(Path(binding['path']).read_bytes())==binding['sha256'],binding['path']
    definition_path=ROOT/f'json/Card-ALD/definitions/{card}.json'
    overlay_path=ROOT/f'json/Card-ALD/build-overrides/{card}.json'
    previous=read(definition_path);overlay=read(overlay_path)
    assert semantics(candidate)==semantics(previous),'Layout adoption must not change card symbols or available ports'
    assert candidate['nets']==previous['nets'] and candidate['power_contacts']==previous['power_contacts']
    expected,_=build(candidate)
    before={definition_path:definition_path.read_bytes(),overlay_path:overlay_path.read_bytes()}
    for name in expected:
        path=ROOT/'Card-ALD'/name;before[path]=path.read_bytes()
    for relative in [f'json/Card-ALD/{card}.json',f'notes/Card-ALD/{card} drawing provenance.json',f'notes/Card-ALD/{card} diagram publication receipt.json',f'notes/Card-ALD/Generation/{card}.json','notes/Card-ALD/Universal card diagrams publication.json','csv/Card-ALD/Notation variants.csv']:
        path=ROOT/relative
        if path.exists():before[path]=path.read_bytes()
    history=ROOT/f'notes/Card-ALD/history/Before graph layout/{card}'
    preserved=[]
    for path,raw in before.items():
        target=history/path.relative_to(ROOT)
        assert not target.exists() or target.read_bytes()==raw
        write_protected(target,raw)
        preserved.append({'path':target.relative_to(ROOT).as_posix(),'sha256':digest(raw),'original_path':str(path)})
    accepted_root=ROOT/f'notes/Card-ALD/Generation/Accepted layouts/{card}'
    accepted_path=accepted_root/'Definition.json';accepted_review=accepted_root/'Independent review.json'
    write_protected(accepted_path,args.definition.read_bytes());write_protected(accepted_review,args.review.read_bytes())
    new_overlay=deepcopy(overlay)
    new_overlay['layout']={
        'canvas':candidate['canvas'],'wiring':candidate['wiring'],
        'exterior_pins':candidate['exterior_pins'],'annotations':candidate['annotations'],
        'boxes':[{k:b[k] for k in ['portion','x','top','height']}|{'ports':[{'id':p['id'],'row':p['row']} for p in b['ports']]} for b in candidate['boxes']]}
    new_overlay['approved_variants']=candidate['variants']
    new_overlay['canonical_line_ending']=candidate['canonical_line_ending']
    new_overlay['source_bindings'] += [{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p.read_bytes())} for p in [accepted_path,accepted_review]]
    new_overlay['layout_authority']={'review':accepted_review.relative_to(ROOT).as_posix(),'algorithm':'NetworkX dependency placement and orthogonal grid routing','free_start_rows':True}
    private=ROOT.parent/f'tmp/ald-text/ald/card-layout-adoption/{card} reviewed supplement.json'
    write_json(private,new_overlay)
    preflight,preflight_report=build_card_data.build(card,overrides_path=private)
    assert preflight is not None
    assert build(preflight)[0]==expected,'Private data-pipeline preflight differs from independently accepted layout'
    write_json(overlay_path,new_overlay)
    regenerated,report=build_card_data.build(card)
    assert regenerated is not None
    actual,_=build(regenerated)
    assert actual==expected,'Updated data pipeline must reproduce all independently accepted layouts exactly'
    write_json(definition_path,regenerated)
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/card_ald/generate_card.py'),card],check=True)
    for name,raw in expected.items():assert (ROOT/'Card-ALD'/name).read_bytes()==raw
    receipt={'schema':'reviewed-card-layout-adoption-v1','card_type':card,
             'candidate':{'path':accepted_path.relative_to(ROOT).as_posix(),'sha256':digest(accepted_path.read_bytes())},
             'independent_review':{'path':accepted_review.relative_to(ROOT).as_posix(),'sha256':digest(accepted_review.read_bytes())},
             'definition':{'path':definition_path.relative_to(ROOT).as_posix(),'sha256':digest(definition_path.read_bytes())},
             'reviewed_supplement':{'path':overlay_path.relative_to(ROOT).as_posix(),'sha256':digest(overlay_path.read_bytes())},
             'exact_default_builder_and_renderer_roundtrip':True,'unchanged_circuit_and_port_identities':True,
             'preserved_predecessors':preserved,'build_evidence':report}
    write_json(accepted_root/'Publication receipt.json',receipt)
    print(json.dumps({'card_type':card,'drawings':len(expected),'canvas':regenerated['canvas'],'published':True}))


if __name__=='__main__':main()
