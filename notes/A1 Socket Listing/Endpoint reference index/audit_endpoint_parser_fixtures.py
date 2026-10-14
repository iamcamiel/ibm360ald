"""Bounded independent adversarial examples against the actual saved builder."""
import ast, importlib.util, json
from pathlib import Path
from collections import defaultdict
from audit_endpoint_reference_index import binding

OUT=Path(__file__).resolve().parent
path=OUT/'build_endpoint_reference_index.py'
spec=importlib.util.spec_from_file_location('endpoint_builder',path)
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
human={x:{'path':'fixture human authority','sha256':'fixture'} for x in 'ABCEKL'}
checks={}; detail={}

def check(name, passed, evidence=None):
    checks[name]=bool(passed)
    if evidence is not None:detail[name]=evidence

def extract(rows, model=None, page='AP001'):
    lines=[' '*160 for _ in range(103)];lines[0]=page.ljust(160)
    for row,text in rows:lines[row]=text.ljust(160)
    model=model or {'nodes':[{'id':x} for x in ['AB','AC','BH','A2']]}
    return builder.extract_entries(page,'fixture',lines,model,human,{})

for letter in 'ABCEKL':
    d=builder.parse_endpoint(letter+'-E4A3B05',human)
    check('authorized_bare_unit_'+letter,d['board']=='02'+letter+'-E4' and d['raw_board']==letter+'-E4' and bool(d['unit_rule_receipt']))
d=builder.parse_endpoint('03B-D4A3TD05',human)
check('explicit_other_unit_not_overwritten',d['board']=='03B-D4' and d['unit']=='03')
check('unlisted_bare_unit_not_expanded',builder.parse_endpoint('D-D4A3BD05',human)['board'] is None)
check('socket_terminal_only_not_pin',builder.parse_endpoint('02A-E4A3BB05',human)['socket_normalized']=='A3' and builder.parse_endpoint('02A-E4A3BB05',human)['pin']=='B05')
check('unknown_mask_exact_length',builder.mask_compatible('LS0\ufffd1AC4','LS051AC4') and not builder.mask_compatible('LS0\ufffd1AC4','LS0151AC4'))
check('FRAME_does_not_expand_unlisted_unit',not extract([(93,'AB4 D-E4A3B05'),(98,'FRAME 02')])[0]['fully_readable'])
check('pin_like_label_without_context_ineligible',not extract([(93,'B03 02A-E4A3B05')],{})[0]['eligible_exact_match'])
check('digit_bearing_node_ID_supported',extract([(93,'A24 02A-E4A3B05')])[0]['eligible_exact_match'])
es=extract([(93,'AB4 02A-E4A3B05             AC4 02A-E4A3B06'),(94,'    02A-E4A3B07                 02A-E4A3B08')])
check('parallel_columns_do_not_bleed',[d['governing_raw_code'] for d in es]==['AB4','AC4','AB4','AC4'])
es=extract([(93,'AB4 02A-E4A3B05 02A-E4A3B06'),(94,'    02A-E4A3B07')])
check('same_heading_multiple_endpoints',[d['governing_raw_code'] for d in es]==['AB4']*3)
es=extract([(93,'AB4 02A-E4A3B05'),(94,'A\ufffd4 02A-E4A3B06'),(95,'    02A-E4A3B07')])
check('masked_heading_resets_previous_carry',es[-1]['governing_raw_code']=='A\ufffd4' and not es[-1]['eligible_exact_match'])
es=extract([(93,'AB4 02A-E4A3B05'),(94,'AC4'),(95,'    02A-E4A3B07')])
check('standalone_heading_resets_carry',es[-1]['governing_raw_code']=='AC4')
es=extract([(90,'BH1 02A-E4A3B05'),(91,'    02A-E4A3B06')])
check('actual_WA150_row90_91_footer_start',es[-1]['governing_raw_code']=='BH1' and es[-1]['eligible_exact_match'])
es=extract([(90,'                 02A-E4A3B05'),(101,'AB4 02A-E4A3B06')],{'nodes':[{'id':'AB'}],'printed_labels':[{'row':90,'column':17,'text':'02A-E4A3B05'}]})
check('unproven_column_wrap_ineligible',not es[0]['eligible_exact_match'])
es=extract([(93,'AB4 02A-E4A3B05'),(94,' '),(95,'    02A-E4A3B07')],{'nodes':[{'id':'AB'},{'id':'AC'}],'printed_labels':[{'row':94,'column':0,'text':'AC4'}]})
check('stale_model_only_heading_not_used',es[-1]['governing_raw_code']!='AC4')

# Execute the actual main-loop candidate/ambiguity statements on controlled data.
tree=ast.parse(path.read_text(encoding='utf-8'))
main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
loop=next(x for x in main.body if isinstance(x,ast.For) and isinstance(x.target,ast.Name) and x.target.id=='q')
def assigns(stmt,name):
    return isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in stmt.targets)
first=next(i for i,s in enumerate(loop.body) if assigns(s,'candidates'))
last=next(i for i,s in enumerate(loop.body) if assigns(s,'r'))
snippet=compile(ast.Module(body=loop.body[first:last],type_ignores=[]),str(path),'exec')
def endpoint(token,reference=None,pattern=None,eligible=True,page='AP001'):
    d=builder.parse_endpoint(token,human)
    d.update(page=page,id=token+str(reference),eligible_exact_match=eligible and d['fully_readable'],governing_full_reference=reference,governing_reference_pattern=pattern if pattern is not None else reference)
    return d
def match(entries,ref='AP001A\ufffd4'):
    by=defaultdict(list)
    for d in entries:
        if d['board']:by[d['board'],d['socket_normalized'],d['pin']].append(d)
    ns={'by_physical':by,'all_entries':entries,'board':'02A-E4','chosen':'A3','pin':'B05','target_key_clear':True,'field_supported':True,'ref':ref,'normalize_socket':builder.normalize_socket,'mask_compatible':builder.mask_compatible,'masks_overlap':builder.masks_overlap,'socket_masks_overlap':builder.socket_masks_overlap}
    exec(snippet,ns)
    return ns
base=endpoint('02A-E4A3B05','AP001AB4')
ns=match([base,endpoint('02A-E4A3TB05','AP001AC4')])
check('T_B_alias_competing_references_not_High',ns['status']=='Tentative' and len(ns['eligible_values'])==2)
ns=match([base,endpoint('03A-E4A3B05','AP001AC4')])
check('other_explicit_unit_excluded',ns['status']=='High' and len(ns['candidates'])==1)
ns=match([base,endpoint('02A-E4A3B06','AP001AC4')])
check('other_pin_excluded',ns['status']=='High' and len(ns['candidates'])==1)
ns=match([base,endpoint('02A-E4A3BB05',pattern='AP001A\ufffd4',eligible=False)])
check('masked_governing_competitor_vetoes_High',ns['status']=='Tentative' and len(ns['competing'])==1)
ns=match([base,endpoint('02A-E4A3BB05',eligible=False)])
check('missing_governing_competitor_vetoes_High',ns['status']=='Tentative' and len(ns['competing'])==1)
ns=match([base,endpoint('02\ufffd-E4A3B05','AP001AC4',eligible=False)])
check('damaged_unit_physical_competitor_vetoes_High',ns['status']=='Tentative' and len(ns['candidates'])==2)
ns=match([base,endpoint('02A-E4A\ufffdB05','AP001AC4',eligible=False)])
check('damaged_socket_competitor_vetoes_High',ns['status']=='Tentative' and len(ns['candidates'])==2)
ns=match([base,endpoint('02A-E4A3\ufffdB05','AP001AC4',eligible=False)])
check('damaged_terminal_socket_position_retained_for_ambiguity',ns['status']=='Tentative' and len(ns['candidates'])==2)
ns=match([base,endpoint('02A-E4A3B\ufffd5','AP001AC4',eligible=False)])
check('damaged_pin_competitor_vetoes_High',ns['status']=='Tentative' and len(ns['candidates'])==2)
ns=match([base,endpoint('02A-E4A3BB05',eligible=False)],ref='\ufffd\ufffd001A\ufffd4')
check('unknown_page_mask_retains_competitor',ns['status']=='Tentative')
result={'passed':all(checks.values()),'checks':checks,'failed_checks':[k for k,v in checks.items() if not v],'builder':binding(path),'scope':'Adversarial bounded fixtures executed on actual saved parser and actual candidate/ambiguity code statements; no source transcription guesses.'}
audit=OUT/'Independent endpoint parser fixtures.json';audit.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'audit':binding(audit),'passed':result['passed'],'failed_checks':result['failed_checks'],'check_count':len(checks)}))
