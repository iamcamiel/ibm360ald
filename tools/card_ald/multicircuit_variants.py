"""Explicit manual-selected canonical IDs; independently witnessed literal IDs.

No circuit is selected by frequency or ordering. This first capability holds
different canonical manual truth-table forms, unknown IDs, stale observations,
and incomplete/changed physical topology. It does not equate circuit ratings.
"""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,re
import card_source as reader

SCHEMA='reviewed-multicircuit-preservation-v1'
MANUAL='notes/Card-ALD/Manual canonical circuit forms.json'
CODE=re.compile(r'[A-Z][0-9]{2}[A-Z]{2}\Z')
def implementation():return {'module':'multicircuit_variants','sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
def digest(value):
 return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def binding(path,root):
 p=Path(path).resolve();return {'path':p.relative_to(root).as_posix(),'sha256':sha256(p.read_bytes()).hexdigest()}
def read_bound(item,root):
 assert isinstance(item,dict)and set(item)=={'path','sha256'},'Malformed source binding'
 p=Path(item['path']);p=p if p.is_absolute()else root/p
 assert p.is_file()and sha256(p.read_bytes()).hexdigest()==item['sha256'],'Stale circuit evidence: '+str(p)
 return json.loads(p.read_bytes())
def manual_form(entry):
 assert entry.get('definition_status')in('definition_verified','index_definition_verified','definition_and_figure_verified','definition_and_exact_card_figure_verified'),'Circuit lacks accepted manual definition'
 form=entry.get('canonical_form',{})
 assert form.get('primary_function')in('A','OR','N','AR'),'Unsupported multi-circuit manual form'
 assert all(type(form.get(k))is bool for k in('all_input_triangles','all_output_triangles')),'Incomplete manual polarity'
 return {k:form[k]for k in('primary_function','all_input_triangles','all_output_triangles')}
def node_facts(node):
 # Exact literal terminal inventory, including aliases and decoration fields;
 # source context/provenance decorations are stored separately by the reader.
 return {'id':node.get('id'),'portion':node.get('portion'),'unit':node.get('unit',node.get('circuit_identifier')),
         'function':node.get('function',node.get('function_label')),'pins':deepcopy(node.get('pins',[]))}
def source_row(occurrence):
 return {'page':occurrence['page'],'node':occurrence['node'],'node_pointer':occurrence['node_pointer'],
         'model':deepcopy(occurrence['_model_binding']),'circuit_identifier':occurrence['circuit_identifier'],
         'portion':occurrence['portion']}
def source_key(row):return(row['page'],row['node'],row['node_pointer'],row['model']['sha256'])
def make_plan(card,catalog,observations,choices,root):
 """Validate an explicit policy against complete current occurrence inventory."""
 root=Path(root).resolve();groups=defaultdict(list)
 for o in observations:groups[o['portion']].append(o)
 multi={p:os for p,os in groups.items()if len({o.get('circuit_identifier')for o in os})>1}
 if not multi:
  assert not choices,'Unused multi-circuit choice'
  return None
 assert isinstance(choices,dict)and set(choices)==set(multi),'Every competing circuit group requires one exact manual choice'
 manual_path=root/MANUAL;manual=read_bound(binding(manual_path,root),root);selected={};source_rows=[]
 for portion,os in sorted(multi.items()):
  codes={o.get('circuit_identifier')for o in os}
  assert all(isinstance(c,str)and CODE.fullmatch(c)for c in codes),'Unreadable circuit remains source uncertainty'
  policy=choices[portion]
  assert set(policy)=={'canonical_circuit_identifier','observed_circuit_identifiers','manual','reason'},'Unknown choice field'
  assert isinstance(policy['reason'],str)and policy['reason'].strip(),'Explicit canonical reason required'
  assert policy['manual']==binding(manual_path,root),'Canonical choice manual binding is stale'
  assert sorted(codes)==policy['observed_circuit_identifiers'],'Changed literal circuit inventory'
  canonical=policy['canonical_circuit_identifier'];assert canonical in codes,'Canonical must be an explicitly selected observed exact manual code'
  forms={code:manual_form(manual['circuits'][code])for code in codes}
  assert all(f==forms[canonical]for f in forms.values()),'Different manual canonical forms require a separately reviewed capability'
  selected[portion]={'choice':deepcopy(policy),'manual_forms':forms}
  seen=set()
  for o in os:
   row=source_row(o);assert source_key(row)not in seen,'Duplicate source occurrence';seen.add(source_key(row))
   data=read_bound(row['model'],root);doc=reader.view(data,root)
   # Source pointers are original container ordinals; never select by unit text.
   nodes=[n for n in doc['nodes']if n.get('_source_pointer')==row['node_pointer']and n.get('id')==row['node']]
   assert len(nodes)==1,'Source occurrence not uniquely owned';node=nodes[0]
   assert node.get('unit')==row['circuit_identifier']and node.get('portion')==portion,'Source/catalogue identity disagreement'
   row['source_facts_sha256']=digest(node_facts(node));source_rows.append(row)
 return {'schema':SCHEMA,'implementation':implementation(),'card_type':card,'manual':binding(manual_path,root),
         'catalogue':binding(root/'json/Card types current'/f'{card}.json',root),'choices':selected,'source_rows':source_rows}
def topology(spec):
 return {'card_type':spec['card_type'],'boxes':[{'portion':b['portion'],'ports':[
  {k:p.get(k)for k in('id','side','pin','contact_role','border_control')}for p in b['ports']]}for b in spec['boxes']],
  'nets':deepcopy(spec['nets']),'power_contacts':deepcopy(spec['power_contacts'])}
def attach(spec,plan):
 if not plan:return spec
 result=deepcopy(spec);proof=deepcopy(plan);proof['topology_sha256']=digest(topology(result));result['multicircuit_preservation']=proof
 for box in result['boxes']:
  if box['portion']in proof['choices']:
   assert box['circuit_identifier']==proof['choices'][box['portion']]['choice']['canonical_circuit_identifier']
   box['_multicircuit_preservation']={'portion':box['portion'],'choice':deepcopy(proof['choices'][box['portion']]),
      'source_rows':[deepcopy(r)for r in proof['source_rows']if r['portion']==box['portion']]}
 return result
def check_spec(spec,root=None):
 proof=spec.get('multicircuit_preservation')
 if proof is None:return
 assert proof['schema']==SCHEMA and proof['card_type']==spec['card_type'],'Invalid circuit proof identity'
 assert proof.get('implementation')==implementation(),'Circuit proof implementation changed'
 assert proof['topology_sha256']==digest(topology(spec)),'Circuit variants cannot change physical topology'
 boxes={b['portion']:b for b in spec['boxes']}
 for portion,choice in proof['choices'].items():
  b=boxes[portion];assert b['circuit_identifier']==choice['choice']['canonical_circuit_identifier'],'Canonical circuit changed'
  codes=choice['choice']['observed_circuit_identifiers'];forms=choice['manual_forms']
  assert codes==sorted(set(codes))and set(codes)==set(forms)and all(isinstance(c,str)and CODE.fullmatch(c)for c in codes),'Malformed circuit inventory'
  assert all(f==forms[b['circuit_identifier']]for f in forms.values()),'Different manual forms cannot use this capability'
  assert choice['choice']['manual']==proof['manual'],'Canonical policy manual differs'
  expected={'portion':portion,'choice':choice,'source_rows':[r for r in proof['source_rows']if r['portion']==portion]}
  assert b.get('_multicircuit_preservation')==expected,'Box circuit proof differs'
 if root is not None:
  root=Path(root).resolve();manual=read_bound(proof['manual'],root);catalog=read_bound(proof['catalogue'],root)
  for portion,entry in proof['choices'].items():
   assert entry['manual_forms']=={c:manual_form(manual['circuits'][c])for c in entry['choice']['observed_circuit_identifiers']},'Manual circuit form changed'
   current={(o['page'],o['node'],o['node_pointer'],o['circuit_identifier'])for o in catalog['diagram_occurrences']if o.get('portion')==portion}
   captured={(r['page'],r['node'],r['node_pointer'],r['circuit_identifier'])for r in proof['source_rows']if r['portion']==portion}
   assert current==captured,'Incomplete or changed source circuit inventory'
  cache={}
  for row in proof['source_rows']:
   key=(row['model']['path'],row['model']['sha256'])
   if key not in cache:cache[key]=reader.view(read_bound(row['model'],root),root)
   nodes=[n for n in cache[key]['nodes']if n.get('_source_pointer')==row['node_pointer']and n.get('id')==row['node']]
   assert len(nodes)==1 and digest(node_facts(nodes[0]))==row['source_facts_sha256'],'Stale literal/port circuit proof'
def match_source(node,box):
 proof=box.get('_multicircuit_preservation')
 if not proof:return False
 row={'page':node.get('_source_page'),'node':node.get('id'),'node_pointer':node.get('_source_pointer'),
      'model':node.get('_source_model_binding',{})}
 if not row['model'].get('sha256'):return False
 matches=[r for r in proof['source_rows']if source_key(r)==source_key(row)]
 return len(matches)==1 and matches[0]['circuit_identifier']==node.get('unit',node.get('circuit_identifier'))and matches[0]['source_facts_sha256']==digest(node_facts(node))
def witness_for_variant(spec,variant,witnesses):
 changed={p:x['circuit_identifier']for p,x in variant.get('box_overrides',{}).items()if 'circuit_identifier'in x}
 if not changed:return None
 complete=[w for w in witnesses if w.get('complete_field_observation')is True and not w.get('fields_not_inferred')and not w.get('unobserved_portions_kept_canonical')]
 assert complete,'Alternate circuit literal needs a complete physical-card field witness'
 return {'schema':'complete-circuit-literal-witness-v1','topology_sha256':digest(topology(spec)),
         'overrides_sha256':digest(variant['box_overrides']),'literal_identifiers':changed,'complete_witnesses':deepcopy(complete)}
def check_variant(spec,variant):
 changed={p:x['circuit_identifier']for p,x in variant.get('box_overrides',{}).items()if 'circuit_identifier'in x}
 if not changed:return
 check_spec(spec);proof=variant.get('circuit_witness',{})
 assert proof.get('schema')=='complete-circuit-literal-witness-v1','Missing complete literal variant witness'
 assert proof['topology_sha256']==digest(topology(spec))and proof['overrides_sha256']==digest(variant['box_overrides']),'Variant topology/fields changed after witness'
 assert proof['literal_identifiers']==changed and proof['complete_witnesses'],'Literal witness does not match drawing'
 for portion,code in changed.items():
  assert CODE.fullmatch(code)and code in spec['multicircuit_preservation']['choices'][portion]['manual_forms'],'Unapproved circuit identifier'
 for w in proof['complete_witnesses']:
  assert w.get('complete_field_observation')is True and not w.get('fields_not_inferred')and not w.get('unobserved_portions_kept_canonical'),'Incomplete circuit witness'
  for portion,code in changed.items():
   assert w['observed_fields'][portion]['circuit_identifier']==code,'Witness literal differs'
   rows=spec['multicircuit_preservation']['source_rows']
   witnesses=w.get('nodes',[])
   assert any(r['portion']==portion and r['circuit_identifier']==code and any(
    n.get('page')==r['page']and n.get('node')==r['node']and n.get('node_pointer')==r['node_pointer']and n.get('model',{}).get('sha256')==r['model']['sha256']
    for n in witnesses)for r in rows),'Literal variant lacks an exactly bound source occurrence'
