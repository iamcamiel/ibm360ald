"""Closed catalogue auxiliary formats. Structural validation only; no identity resolution."""
from pathlib import Path
import json,re,hashlib
SCHEMA_PATH=Path(__file__).with_name('catalogue_identity.schema.json')
UNRESOLVED_POLICY="Conflicting source identity is retained without choosing a card portion; excluded from resolved occurrences and profiles, never reclassified as annotation."
COUNT_KEYS=('models','diagram_nodes','card_occurrences','nodes_without_card_type','annotation_nodes_excluded','listing_records','physical_card_records','unclassified_listing_records','unresolved_identity_occurrences')
def _need(ok,message):
 if not ok:raise ValueError(message)
def _validate(value,spec,path='$',root=None):
 root=root or json.loads(SCHEMA_PATH.read_bytes())
 if '$ref' in spec:return _validate(value,root['$defs'][spec['$ref'].split('/')[-1]],path,root)
 if 'oneOf' in spec:
  matched=0
  for child in spec['oneOf']:
   try:_validate(value,child,path,root);matched+=1
   except ValueError:pass
  _need(matched==1,path+': expected exactly one schema');return
 if 'const' in spec:_need(type(value)==type(spec['const'])and value==spec['const'],path+': wrong constant')
 if 'enum' in spec:_need(value in spec['enum'],path+': unknown enum value')
 t=spec.get('type');types=t if isinstance(t,list)else [t] if t else[]
 def match(k):return {'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),'integer':type(value)is int,'boolean':type(value)is bool,'null':value is None}.get(k,False)
 if types:_need(any(match(k)for k in types),path+': wrong type')
 if isinstance(value,dict):
  props=spec.get('properties',{});_need(set(spec.get('required',[]))<=set(value),path+': missing keys')
  for k,v in value.items():
   if k in props:_validate(v,props[k],path+'/'+k,root)
   else:
    extra=spec.get('additionalProperties',True);_need(extra is not False,path+': unknown key '+k)
    if isinstance(extra,dict):_validate(v,extra,path+'/'+k,root)
 if isinstance(value,list):
  _need(len(value)>=spec.get('minItems',0),path+': insufficient entries')
  if spec.get('uniqueItems'):_need(len({json.dumps(x,sort_keys=True)for x in value})==len(value),path+': duplicate entries')
  for i,v in enumerate(value):_validate(v,spec.get('items',{}),path+'/'+str(i),root)
 if isinstance(value,str)and 'pattern'in spec:_need(re.search(spec['pattern'],value)is not None,path+': invalid syntax')
 if type(value)is int and 'minimum'in spec:_need(value>=spec['minimum'],path+': below minimum')
def _unique_pairs(items):
 result={}
 for key,value in items:
  _need(key not in result,'Duplicate JSON source-node key: '+key);result[key]=value
 return result
def _finite_constant(value):raise ValueError('Non-finite JSON source-node value: '+value)
def validate_unresolved_occurrence(obs):
 _validate(obs,{'$ref':'#/$defs/unresolved_occurrence'})
 raw=json.loads(obs['source_node_json'],object_pairs_hook=_unique_pairs,parse_constant=_finite_constant);_need(isinstance(raw,dict),'source_node_json is not an object')
 _need(json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':'))==obs['source_node_json'],'noncanonical source_node_json')
 _need(obs['source_fields']=={k:raw.get(k)for k in ('card_type','portion','card','part','printed_card_portion','unit')},'source fields differ from preserved node')
 _need(obs['reason_codes']==sorted(obs['reason_codes']),'reason codes not sorted')
 return True
def validate_partition(partition,counts):
 _need(set(counts)==set(COUNT_KEYS),'unknown/missing count keys');seen=set();buckets={k:0 for k in ('resolved','unresolved_identity','annotation','no_card_type')}
 for row in partition:
  _validate(row,{'$ref':'#/$defs/partition_entry'});key=(row['source_model'],row['node_pointer']);_need(key not in seen,'duplicate partition source node');seen.add(key);buckets[row['bucket']]+=1
  _need((isinstance(row['card_type'],str)and re.fullmatch('[0-9]{4}',row['card_type'])is not None)if row['bucket']=='resolved'else row['card_type']is None,'partition chooses unresolved identity')
 expected={'resolved':counts['card_occurrences'],'unresolved_identity':counts['unresolved_identity_occurrences'],'annotation':counts['annotation_nodes_excluded'],'no_card_type':counts['nodes_without_card_type']}
 _need(buckets==expected and sum(buckets.values())==counts['diagram_nodes'],'incomplete node count partition')
 return True
def family_index_for_observations(observations):
 families={}
 for obs in observations:
  fields=obs['source_fields'];claims=set()
  card=fields['card_type']
  if isinstance(card,str)and re.fullmatch('[0-9]{4}',card):claims.add(card)
  for field in ('card','part','printed_card_portion'):
   literal=fields[field];match=re.fullmatch(r'([0-9]{4})[A-Z0-9]{2}',literal)if isinstance(literal,str)else None
   if match:claims.add(match.group(1))
  for claim in claims:families.setdefault(claim,set()).add((obs['source_model'],obs['node_pointer']))
 return [{'card_type':card,'occurrences':[{'source_model':m,'node_pointer':p}for m,p in sorted(keys)]}for card,keys in sorted(families.items())]
def validate_document(doc):
 _validate(doc,json.loads(SCHEMA_PATH.read_bytes()))
 if doc['schema']=='current-card-catalog-unresolved-identities-v1':
  _need(doc['count']==len(doc['observations']),'unresolved count mismatch');_need(doc['family_index']==family_index_for_observations(doc['observations']),'unresolved family index differs');seen=set()
  for o in doc['observations']:
   validate_unresolved_occurrence(o);key=(o['source_model'],o['node_pointer']);_need(key not in seen,'duplicate unresolved occurrence');seen.add(key)
 else:
  validate_partition(doc['node_partition'],doc['counts'])
  for field in ('source_inputs','files'):_need(len({x['path']for x in doc[field]})==len(doc[field]),'duplicate '+field+' path')
 return True
