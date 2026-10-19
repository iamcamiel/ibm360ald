"""Private semantic proposal: explicit unprinted, declared, located terminals.

This adds no contacts, endpoint aliases, source facts, or source normalization.
The owner-aware reader proves a source alias names one existing terminal.  A
catalogue projection may carry that proof only with its exact typed identity.
"""
from copy import deepcopy
import hashlib
import json
import re

KEY = '_explicit_unprinted_alias'
SCHEMA = 'explicit-unprinted-declared-terminal-v1'
PRINTED = ('printed_combined_label','raw_printed_pin_field','printed_pin_label',
           'printed_label','printed_pin','label','display_pin')
PHYSICAL = ('physical_pin','physical_pin_candidate','physical_candidate','contact')

def seal(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':')).encode()).hexdigest()

def declared_names(port,owner):
    result=set()
    if not isinstance(port,dict):return result
    for field in ('reference','terminal_id','ref','id','port_id','key','alias',
                  'aliases','references','terminal_ids'):
        value=port.get(field,[])
        for name in value if isinstance(value,(list,tuple)) else [value]:
            if isinstance(name,str) and name:
                result.add(name if name.startswith(owner+'.') else owner+'.'+name)
    return result

def proof_for(node,terminal,typed_terminals):
    """Return evidence only for an explicit blank presentation, never a guess."""
    p=terminal.get('source_literals',{})
    if not isinstance(p,dict) or p.get('source_reviewed') is not True:return None
    if 'printed_pin' not in p or p['printed_pin']!='':return None
    if any(p.get(k) not in (None,'') for k in PRINTED if k!='printed_pin'):return None
    if any(p.get(k) not in (None,'') for k in PHYSICAL):return None
    if any(p.get(k) is True for k in ('source_unknown_pin','pin_inferred')):return None
    label=p.get('pin')
    # Opaque alphabetic aliases only.  Corrupt numbered contacts, numeric wire
    # controls, single control letters and damaged text remain unresolved.
    if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z][A-Za-z_]{1,31}',label):return None
    if terminal.get('pin_number') is not None:return None
    owner=node.get('id'); side=p.get('side'); row=p.get('row'); point=p.get('point')
    if not isinstance(owner,str) or not owner or side not in ('input','output'):return None
    if p.get('reference')!=owner+'.'+label:return None
    if type(row) is not int or not isinstance(point,list) or len(point)!=2:return None
    if any(type(x) is not int for x in point) or point[1]!=row:return None
    if p.get('physical_border') not in ('left','right','top','bottom'):return None
    geometry=terminal.get('geometry',{})
    if geometry.get('point')!=point or geometry.get('row')!=row:return None
    tid=terminal.get('terminal_id'); object_id=node.get('_uniform_object_id')
    if not isinstance(tid,str) or not object_id or not tid.startswith(object_id+'/t:'):return None
    if terminal.get('side')!=side or terminal.get('occurrence_kind')!='primary':return None
    if sum(t.get('terminal_id')==tid for t in typed_terminals)!=1:return None
    names=[t for t in typed_terminals if t.get('side')==side and
           owner+'.'+label in declared_names(t.get('source_literals',{}),owner)]
    if len(names)!=1 or names[0].get('terminal_id')!=tid:return None
    # The normalized explicit alias must identify this same object and suffix.
    claims=[a.get('claim',{}) for a in terminal.get('endpoint_aliases',[]) if a.get('kind')=='reference']
    if len(claims)!=1 or claims[0].get('object_identifier')!=owner or claims[0].get('port_reference_text')!=label:return None
    proof={'schema':SCHEMA,'owner':owner,'terminal_id':tid,'alias':p['reference'],
           'side':side,'literal':label,'printed_pin':'','row':row,'point':point,
           'physical_border':p['physical_border'],'source_terminal_sha256':seal(terminal)}
    return {**proof,'proof_sha256':seal(proof)}

def decorate(node,uniform_object):
    """Attach runtime evidence; serialized source evidence cannot authorize it."""
    owner=deepcopy(node);owner['_uniform_object_id']=uniform_object['object_id']
    terminals=uniform_object['terminals'];byid={t['terminal_id']:t for t in terminals}
    for port in node.get('pins',[]):
        if not isinstance(port,dict):continue
        port.pop(KEY,None)
        terminal=byid.get(port.get('_terminal_id'))
        if terminal is None:continue
        proof=proof_for(owner,terminal,terminals)
        if proof:port[KEY]=proof
    return node

def valid(port):
    proof=port.get(KEY)
    if not isinstance(proof,dict) or proof.get('schema')!=SCHEMA:return False
    body={k:v for k,v in proof.items() if k!='proof_sha256'}
    if proof.get('proof_sha256')!=seal(body):return False
    if any(port.get(k) is True for k in ('source_unknown_pin','pin_inferred')):return False
    if any(port.get(k) not in (None,'') for k in PHYSICAL):return False
    if 'printed_pin' not in port or port['printed_pin']!='':return False
    if any(port.get(k) not in (None,'') for k in PRINTED if k!='printed_pin'):return False
    if port.get('_pin_number') is not None:return False
    if any(port.get(field)!=proof.get(key) for field,key in
           (('_terminal_id','terminal_id'),('pin','literal'),('side','side'),('row','row'))):return False
    # Catalogue projections legitimately omit original point/reference fields.
    return all(field not in port or port[field]==proof[field]
               for field in ('point','physical_border')) and (
               'reference' not in port or port['reference']==proof['alias'])
