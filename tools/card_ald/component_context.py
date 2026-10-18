"""Prove occurrence-scoped K net origins on explicitly approved passive components.

This reader adds runtime certificates only. It never edits sources, changes a
printed terminal role, merges contacts, or infers an intrinsic card connection.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib,json,re
import card_source as source

CAPABILITY='occurrence_net_origin'
CAPABILITY_SCHEMA='reviewed-passive-component-net-origin-v1'

def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _binding(path,root):
 path=Path(path).resolve()
 try:label=path.relative_to(root).as_posix()
 except ValueError:label=str(path)
 return {'path':label,'sha256':_sha(path)}
def _require(value,message):
 if not value:raise ValueError(message)
def _primary(label):return str(label or '').strip().split()[0]if str(label or '').strip()else''
def _node(document,occurrence):
 node,pointer,problem=source.exact_source_node(document,occurrence)
 _require(node is not None and not problem and pointer==occurrence.get('node_pointer'),'Exact source object is absent or ambiguous')
 return node
def _ports(node):return [p for p in node.get('pins',[])if isinstance(p,dict)]
def _matching_port(node,terminal_id):
 choices=[p for p in _ports(node)if p.get('_terminal_id')==terminal_id]
 _require(len(choices)==1,'Exact current terminal is absent or ambiguous')
 return choices[0]
def _physical_endpoint(document,reference):
 _require(isinstance(reference,str)and reference.count('.')==1,'Common-net endpoint is not one exact local physical reference')
 node_id=reference.split('.',1)[0]
 nodes=[n for n in document.get('nodes',[])if isinstance(n,dict)and n.get('id')==node_id]
 _require(len(nodes)==1,'Common-net endpoint object is absent or ambiguous')
 node=nodes[0];resolved=source.resolve_net_port(node,reference,'output')
 _require(resolved.get('status')=='numbered'and not resolved.get('input_only_alias'),'Common-net endpoint terminal is absent, ambiguous or an input-only alias')
 terminal=_matching_port(node,resolved['raw_port']['_terminal_id'])
 _require(source.terminal_contact(terminal)is not None,'Common-net endpoint has no exact physical contact')
 _require(node.get('source_reviewed')is True,'Common-net endpoint lacks accepted source review')
 _require(bool(node.get('location')),'Common-net endpoint lacks a physical site')
 return node,terminal
def _terminal_identity(port):
 return {key:deepcopy(port.get(key))for key in ('side','pin','row','triangle','_terminal_id','_pin_number','_pin_number_status','_border_decorations','_symbols')}

def apply_context(root,catalog,models,model_bindings,authority_path=None):
 """Validate passive mixed plain/K contexts; attach sealed runtime proofs.

 Models are detached current card_source views keyed by page. A binding is an
 exact current uniform JSON model, already owned by the accepted checkpoint.
 The supplied source views and catalogue are never trusted over those bytes.
 """
 root=Path(root).resolve();path=Path(authority_path)if authority_path is not None else root/'json/Card-ALD/component-forms.json'
 # Revalidate rather than carrying a certificate through a failed new call.
 for document in models.values():
  for node in document.get('nodes',[]):
   if isinstance(node,dict):
    for port in _ports(node):port.pop('_occurrence_net_role',None)
 for occurrence in catalog.get('diagram_occurrences',[]):
  for port in occurrence.get('pins',[]):port.pop('_occurrence_net_role',None)
 if not path.is_file():return {'proofs':[],'holds':[]}
 try:
  authority=source.json_read(path);forms=authority.get('circuits',{})
  _require(isinstance(forms,dict),'Component circuit authority is not an object')
 except (ValueError,TypeError,OSError)as error:return {'proofs':[],'holds':[{'reason':str(error)}]}
 enabled={code:p for code,p in forms.items()if isinstance(p,dict)and CAPABILITY in p}
 relevant=[o for o in catalog.get('diagram_occurrences',[])if o.get('circuit_identifier')in enabled]
 if not relevant:return {'proofs':[],'holds':[]}
 result={'proofs':[],'holds':[]};documents={};bindings={};groups=defaultdict(list)
 try:
  authority_binding=_binding(path,root)
  _require(authority.get('schema')=='reviewed-component-forms-v3','Passive context capability requires component authority v3')
  epoch=source.source_epoch(root);_require(epoch is not None,'No accepted source checkpoint is available')
  parts=catalog.get('full_part_numbers_observed',[]);widths=catalog.get('physical_card_widths_observed',[])
  _require(bool(parts)and len(widths)==1,'Component context lacks exact part mechanics')
  for part in parts:
   mechanics=authority.get('card_parts',{}).get(part,{})
   _require(mechanics.get('card_width')==widths[0]and mechanics.get('supply_connection_inference_allowed')is False,'Component context exact-part mechanics differ')
  capabilities={}
  for code in {o['circuit_identifier']for o in relevant}:
   profile=enabled[code];cap=profile[CAPABILITY]
   _require(profile.get('approved_source_form')is True and profile.get('authority'),'Component display form is not explicitly approved')
   _require(isinstance(cap,dict)and cap.get('schema')==CAPABILITY_SCHEMA and cap.get('passive_component')is True
    and cap.get('marker')=='K'and cap.get('requires_plain_same_portion')is True
    and cap.get('requires_explicit_page_common_net')is True
    and cap.get('intrinsic_connection_inference_allowed')is False
    and cap.get('complete_K_variant_policy')=='hold_until_renderer_support'
    and isinstance(cap.get('component_class'),str)and bool(cap['component_class']),'Invalid or unreviewed passive net-origin capability')
   evidence=cap.get('manual_evidence',[]);_require(bool(evidence),'Passive context capability has no bound manual evidence')
   for proof in evidence:
    manual=Path(proof['path']);manual=manual if manual.is_absolute()else root/manual
    _require(manual.is_file()and _sha(manual)==proof['sha256'],'Passive context manual evidence changed')
   capabilities[code]=deepcopy(cap)
  for occurrence in relevant:
   page=occurrence['page'];code=occurrence['circuit_identifier'];profile=enabled[code]
   _require(occurrence.get('source_reviewed')is True,'Occurrence is not independently source reviewed')
   if page not in documents:
    binding=model_bindings.get(page);_require(isinstance(binding,dict),'Occurrence has no exact model binding')
    target=Path(binding['path']);target=(target if target.is_absolute()else root/target).resolve()
    _require(target.is_relative_to(root/'json')and target.is_file(),'Context model is outside current repository JSON')
    digest=_sha(target);_require(digest==binding.get('sha256')and epoch['models'].get(target)==digest,'Context model does not match the accepted current checkpoint')
    raw=source.json_read(target);_require(raw.get('schema')==source.SCHEMA,'Context model is not uniform current JSON')
    documents[page]=source.view(raw,root);bindings[page]=_binding(target,root)
   original=_node(documents[page],occurrence);runtime=_node(models.get(page,{}),occurrence)
   for field,expected in [('card_type',catalog['card_type']),('portion',occurrence['portion']),('unit',code),('id',occurrence['node'])]:
    _require(original.get(field)==runtime.get(field)==expected,'Context object identity/circuit differs: '+field)
   _require(original.get('source_reviewed')is True,'Current source object is not reviewed')
   _require(_primary(original.get('function'))==profile['printed_function'],'Passive component primary function differs')
   for port in _ports(original):
    pin=source.terminal_contact(port)
    if port.get('side')!='output'or pin is None:continue
    runtime_port=_matching_port(runtime,port.get('_terminal_id'))
    _require(_terminal_identity(runtime_port)==_terminal_identity(port),'Runtime terminal differs from accepted current source')
    groups[(occurrence['portion'],code,'output',pin)].append({'occurrence':occurrence,'node':original,'port':port,'runtime_port':runtime_port})
 except (ValueError,KeyError,TypeError,OSError)as error:
  return {'proofs':[],'holds':[{'reason':str(error)}]}
 for (portion,code,side,pin),members in sorted(groups.items()):
  marked=[m for m in members if source.terminal_contact_role(m['port'])=='nonlogical_common']
  plain=[m for m in members if source.terminal_contact_role(m['port'])=='logical']
  if not marked or not plain:continue # Preserve K-only policies and ordinary plain contacts.
  pending=[]
  try:
   witnesses=[]
   for m in plain:
    o=m['occurrence'];witnesses.append({'page':o['page'],'node':o['node'],'node_pointer':o['node_pointer'],
     'terminal_id':m['port']['_terminal_id'],'side':side,'pin':pin,'circuit_identifier':code,'model_binding':bindings[o['page']]})
   for member in marked:
    o=member['occurrence'];document=documents[o['page']];port=member['port']
    _require(source.wedge(port)is False,'K/common-net marker has ambiguous or conflicting source polarity')
    references={v for k in ('reference','ref')if isinstance((v:=port.get(k)),str)}
    references.add(o['node']+'.'+pin)
    candidates=[]
    for net in document.get('nets',[]):
     if not isinstance(net,dict):continue
     extra=net.get('additional_source_drivers',[])
     if not isinstance(extra,list)or not any(ref in extra for ref in references):continue
     _require(net.get('source_reviewed')is True,'Commoned-source page net lacks accepted source review')
     matches=[ref for ref in extra if ref in references]
     _require(len(matches)==1,'K terminal has ambiguous commoned-source incidence')
     node,terminal=_physical_endpoint(document,matches[0])
     _require(node['id']==o['node']and terminal['_terminal_id']==port['_terminal_id'],'Commoned-source incidence maps to another terminal')
     origin_node,origin_port=_physical_endpoint(document,net.get('driver'))
     _require(source.terminal_contact_role(origin_port)=='logical','Commoned page net has no unmarked named origin')
     _require((origin_node['id'],origin_port['_terminal_id'])!=(node['id'],terminal['_terminal_id']),'K endpoint is its own page-net origin')
     _require(all(isinstance(ref,str)for ref in extra)and len(extra)==len(set(extra)),'Ambiguous additional commoned-source list')
     candidates.append({'net_id':net.get('id'),'named_origin':{'reference':net['driver'],'node':origin_node['id'],
      'terminal_id':origin_port['_terminal_id'],'pin':source.terminal_contact(origin_port),'side':'output',
      'circuit_identifier':origin_node.get('unit'),'physical_site':origin_node.get('location')},
      'commoned_reference':matches[0],'additional_source_drivers':deepcopy(extra),
      'installation_condition':deepcopy(net.get('driver_condition'))})
    _require(len(candidates)==1,'K terminal lacks one unique explicit commoned-source page-net witness')
    proof={'schema':'validated-passive-component-net-origin-v1','role':'commoned_nonorigin','marker':'K',
     'page':o['page'],'node':o['node'],'node_pointer':o['node_pointer'],'portion':portion,
     'circuit_identifier':code,'side':side,'pin':pin,'terminal_id':port['_terminal_id'],
     'physical_site':member['node'].get('location'),'model_binding':bindings[o['page']],
     'plain_same_portion_witnesses':witnesses,'page_net':candidates[0],
     'component_capability':deepcopy(capabilities[code]),'component_authority':authority_binding,
     'validator':_binding(Path(__file__),root),'source_checkpoint':epoch['binding'],
     'intrinsic_connection_inference_applied':False,'active_driver_inference_applied':False,
     'rendered_K_variant_support':False}
    pending.append((member,proof))
   # Register only after the complete mixed-contact group has passed.
   _require(_binding(path,root)==authority_binding,'Component capability changed during context validation')
   _require(_sha(epoch['binding']['path'])==epoch['binding']['sha256'],'Accepted checkpoint changed during context validation')
   for current in bindings.values():
    _require(_sha(root/current['path'])==current['sha256'],'Current source changed during context validation')
   for member,proof in pending:
    sealed=source.register_occurrence_net_role(proof,member['runtime_port'],root);member['runtime_port']['_occurrence_net_role']=sealed
    source.attach_typed_terminals(member['occurrence'],member['node'])
    # Attach only by exact stable terminal identity, never by contact text alone.
    for target in member['occurrence'].get('pins',[]):
     if target.get('_terminal_id')==sealed['terminal_id']and target.get('side')==side and source.terminal_contact(target)==pin:
      target['_occurrence_net_role']=source.register_occurrence_net_role(proof,target,root)
    result['proofs'].append(sealed)
  except (ValueError,KeyError,TypeError,OSError)as error:
   result['holds'].append({'portion':portion,'circuit_identifier':code,'side':side,'pin':pin,'reason':str(error)})
 return result
