#!/usr/bin/env python3
"""Convert canonical v3 or plain legacy ALD diagrams to the functional proposal.

Pure Python 3.10+, standard library only. No production modules are imported.
Source files are read-only; output must be in a separate directory. Unresolved
representations are reported, never repaired by guessing or extending the format.
Run with --help. See README.txt for the conversion and correction contracts.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0,str(Path(__file__).resolve().parent))
from ald_render import render_page, wire_graph, input_display_literal, singleton_output_hanging_row
from pin_annotations import normalize_annotation_leads

PAGE_REF = re.compile(r'[A-Z]{2}\d{3}[A-Z]{2}\d+')
PAGE_ID = re.compile(r'[A-Z]{2}\d{3}')
PRINTED_NET = re.compile(r'[A-Z]{2}\d+')
WIRE = set(' ─│┌┐└┘├┤┬┴┼◇')
LETTERS = 'ABCDEFGHJKLMN'
SCHEMA = 'https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json'


def caption_tail_owner(path, paths, nets, labels):
    """Resolve the legacy right-caption placeholder only with a unique wire.

    The ordinary output layout puts the incoming wire at column 204, the
    signal name at 211, and the output number at 242. The line after the
    name continues that incoming wire. Keep both recorded polylines intact.
    """
    tag=path.get('net')
    match=re.fullmatch(r'RIGHT_CAPTION_TAIL_(\d+)',tag) if isinstance(tag,str) else None
    points=path.get('points')
    if not match or not isinstance(points,list) or len(points)!=2:return None
    y=int(match.group(1))
    if not (0<=y<93 and all(isinstance(p,list) and len(p)==2 and
            all(type(v) is int for v in p) for p in points)):return None
    if points[0][1]!=y or points[1]!=[241,y] or not 211<=points[0][0]<241:return None
    names=[l for l in labels if l.get('row')==y and l.get('column')==211 and isinstance(l.get('text'),str) and l['text'].strip()]
    outputs=[l for l in labels if l.get('row')==y and l.get('column')==242 and isinstance(l.get('text'),str) and PRINTED_NET.fullmatch(l['text'])]
    if len(names)!=1 or len(outputs)!=1:return None
    tails=[p for p in paths if p.get('net')==tag]
    if len(tails)!=1:return None
    owners=set()
    for other in paths:
        route=other.get('points')
        if other.get('net') in nets and isinstance(route,list) and len(route)>1 and [204,y] in (route[0],route[-1]):
            owners.add(other['net'])
    if len(owners)!=1:return None
    owner=next(iter(owners))
    for other in paths:
        if other.get('net') not in nets or other.get('net')==owner:continue
        route=other.get('points')
        if not isinstance(route,list):continue
        for a,b in zip(route,route[1:]):
            if (isinstance(a,list) and isinstance(b,list) and len(a)==len(b)==2 and
                all(type(v) is int for v in a+b) and a[1]==b[1]==y and
                max(min(a[0],b[0]),points[0][0])<min(max(a[0],b[0]),241)):
                return None
    return owner


def ordinary_vertical_select_line(pin, side, marker):
    """Treat a typed select contact's vertical conductor as geometry only."""
    if not isinstance(pin,dict) or side!='L' or marker!='│':return False
    literal=pin.get('source_literals');geometry=pin.get('geometry')
    if not isinstance(literal,dict) or not isinstance(geometry,dict):return False
    number=pin.get('pin_number');point=geometry.get('point')
    if (pin.get('occurrence_kind')!='primary' or pin.get('side')!='input'
            or pin.get('role')!='select' or pin.get('pin_number_status')!='observed'
            or not isinstance(number,str) or not re.fullmatch(r'[A-Z][0-9]+',number)
            or literal.get('border_marker')!='│' or literal.get('side')!='input'
            or literal.get('pin')!=number or literal.get('printed_label')!=number
            or literal.get('pin_status')!='observed' or literal.get('triangle') is not False
            or literal.get('border_point') is not None
            or geometry.get('border_point') is not None
            or not isinstance(point,list) or len(point)!=2
            or any(type(value)is not int for value in point)
            or geometry.get('row')!=point[1] or literal.get('point')!=point
            or literal.get('row')!=point[1]):return False
    source_roles=[item.get('value') for item in literal.get('source_observations',[])
                  if isinstance(item,dict) and item.get('field')=='role']
    normalized_roles=[item.get('value') for item in pin.get('role_observations',[])
                      if isinstance(item,dict) and item.get('kind')=='role']
    if source_roles!=['select'] or normalized_roles!=['select']:return False
    decorations=pin.get('border_decorations')
    if not isinstance(decorations,list):return False
    marks=[item for item in decorations if isinstance(item,dict)
           and item.get('kind')=='literal-border-mark']
    if (len(marks)!=1 or marks[0].get('glyph')!='│'
            or marks[0].get('observed_value')!='│'
            or marks[0].get('edge') is not None
            or marks[0].get('edge_status')!='unspecified'
            or marks[0].get('position_observations')!=[
                {'kind':'border_point','value':None}]):
        return False
    triangles=[item for item in decorations if isinstance(item,dict)
               and item.get('kind')=='triangle']
    return (len(decorations)==2 and len(triangles)==1
            and triangles[0].get('observed_value') is False
            and triangles[0].get('glyph') is None
            and triangles[0].get('edge') is None
            and triangles[0].get('edge_status')=='unspecified'
            and triangles[0].get('position_observations')==[
                {'kind':'border_point','value':None}])


def _source_bound_branch_attachment(point, graph, node, matching, terminals,
                                   owner, selector, literal, logical,
                                   owner_target_claims, physical):
    """Qualify one exact interior route vertex from explicit same-net source claims."""
    if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(v)is not int for v in point):return False
    vertex=tuple(point);neighbors=graph.get(vertex) if isinstance(graph,dict) else None
    if not isinstance(neighbors,(set,list,tuple)) or len(neighbors)<2:return False
    if (matching != [node] or not isinstance(literal,dict)
            or not isinstance(owner_target_claims,list) or not isinstance(physical,list)
            or not isinstance(logical,list)):return False
    if owner+'.'+selector not in literal.get('ports',[]):return False
    targets=literal.get('targets')
    if not isinstance(targets,list) or any(not isinstance(target,str) for target in targets):return False
    owner_targets=[target for target in targets if target.startswith(owner+'.')]
    if len(owner_targets)!=1:return False
    target_match=re.fullmatch(re.escape(owner)+r'\.([A-Z][0-9]+)',owner_targets[0])
    if target_match is None or len(owner_target_claims)!=1 or len(physical)!=1:return False
    if len(logical)!=1:return False
    logical_claim=logical[0]
    logical_ref=logical_claim.get('reference') if isinstance(logical_claim,dict) else None
    if (not isinstance(logical_claim,dict)
            or logical_claim.get('relationship')!='ports'
            or logical_claim.get('role_category')!='declared-membership-or-reference'
            or logical_claim.get('resolution_status')!='source-claim-unresolved'
            or not isinstance(logical_ref,dict)
            or logical_ref.get('kind')!='unparsed-object-reference'
            or logical_ref.get('object_identifier')!=owner
            or logical_ref.get('port_reference_text')!=selector):return False
    pin_number,claim=physical[0]
    reference=claim.get('reference') if isinstance(claim,dict) else None
    source_terminal=reference.get('terminal') if isinstance(reference,dict) else None
    if (not isinstance(claim,dict)
            or claim.get('relationship')!='targets'
            or claim.get('role_category')!='declared-target'
            or claim.get('resolution_status')!='source-claim-unresolved'
            or not isinstance(reference,dict)
            or reference.get('kind')!='terminal-reference'
            or reference.get('parse_status')!='source-contact-syntax'
            or reference.get('object_identifier')!=owner
            or not isinstance(source_terminal,dict)
            or source_terminal.get('pin_number_status')!='observed'
            or source_terminal.get('pin_number')!=target_match.group(1)
            or pin_number!=target_match.group(1)):return False
    terminal=terminals.get(node) if isinstance(terminals,dict) else None
    geometry=terminal.get('geometry') if isinstance(terminal,dict) else None
    terminal_point=geometry.get('point') if isinstance(geometry,dict) else None
    if (not isinstance(terminal,dict) or terminal.get('occurrence_kind')!='primary'
            or terminal.get('side')!='input' or terminal.get('role')!=selector
            or terminal.get('pin_number_status')!='observed'
            or terminal.get('pin_number')!=pin_number
            or not isinstance(terminal_point,(list,tuple)) or len(terminal_point)!=2
            or tuple(terminal_point)!=vertex):return False
    # A second recorded terminal at the same point makes the physical attachment ambiguous.
    at_point=[]
    for occurrence,pin in terminals.items():
        pin_geometry=pin.get('geometry') if isinstance(pin,dict) else None
        pin_point=pin_geometry.get('point') if isinstance(pin_geometry,dict) else None
        if isinstance(pin_point,(list,tuple)) and len(pin_point)==2 and tuple(pin_point)==vertex:
            at_point.append(occurrence)
    return at_point==[node]


def _source_bound_output_role_alias(ref, role, net, owner, selector, literal,
                                    claims, terminals, owner_serial, auxiliary):
    """Bind output-port membership to one exact typed same-net driver occurrence."""
    if (role!='target' or selector!='output' or not isinstance(net,str) or not net
            or ref!=owner+'.output' or not isinstance(literal,dict)
            or not isinstance(claims,list) or not isinstance(terminals,dict)
            or not isinstance(auxiliary,set)):
        return None
    ports=literal.get('ports');targets=literal.get('targets')
    if (not isinstance(ports,list) or ports!=[ref]
            or not isinstance(targets,list) or any(not isinstance(target,str) for target in targets)
            or any(target.startswith(owner+'.') for target in targets)):
        return None
    if literal.get('drivers') not in (None,[]):return None
    driver=literal.get('driver')
    driver_match=re.fullmatch(re.escape(owner)+r'\.([A-Z][0-9]+)',driver) if isinstance(driver,str) else None
    if driver_match is None:return None
    pin_number=driver_match.group(1)
    port_claims=[];driver_claims=[]
    for claim in claims:
        if not isinstance(claim,dict):return None
        reference=claim.get('reference')
        if claim.get('relationship')=='ports':port_claims.append(claim)
        if claim.get('relationship') in ('driver','drivers'):driver_claims.append(claim)
    if (len(port_claims)!=1 or len(driver_claims)!=1
            or not isinstance(port_claims[0].get('reference'),dict)
            or port_claims[0]['reference'].get('object_identifier')!=owner
            or not isinstance(driver_claims[0].get('reference'),dict)
            or driver_claims[0]['reference'].get('object_identifier')!=owner):
        return None
    port_claim=port_claims[0];port_ref=port_claim.get('reference')
    if (port_claim.get('role_category')!='declared-membership-or-reference'
            or port_claim.get('resolution_status')!='source-claim-unresolved'
            or port_ref.get('kind')!='terminal-reference'
            or port_ref.get('parse_status')!='source-semantic-id-syntax'
            or port_ref.get('port_semantic_id')!='output'):
        return None
    driver_claim=driver_claims[0];driver_ref=driver_claim.get('reference')
    driver_terminal=driver_ref.get('terminal') if isinstance(driver_ref,dict) else None
    if (driver_claim.get('role_category')!='declared-driver'
            or driver_claim.get('resolution_status')!='source-claim-unresolved'
            or driver_ref.get('kind')!='terminal-reference'
            or driver_ref.get('parse_status')!='source-contact-syntax'
            or not isinstance(driver_terminal,dict)
            or driver_terminal.get('pin_number')!=pin_number
            or driver_terminal.get('pin_number_status')!='observed'):
        return None
    if not isinstance(owner_serial,str) or not owner_serial:return None
    owner_outputs=[];matching=[]
    for node,pin in terminals.items():
        if not isinstance(node,str) or len(node.split('/'))<3 or node.split('/')[1]!=owner_serial:continue
        if not isinstance(pin,dict):return None
        if pin.get('side')=='output' or pin.get('role')=='output':owner_outputs.append((node,pin))
        if (pin.get('side')=='output' and pin.get('role')=='output'
                and pin.get('pin_number')==pin_number
                and pin.get('pin_number_status')=='observed'):
            matching.append((node,pin))
    if len(matching)!=1 or len(owner_outputs)!=1:return None
    node,pin=matching[0]
    if (node in auxiliary or pin.get('occurrence_kind')!='primary'
            or pin.get('declared_container_role') not in (None,'output')):
        return None
    geometry=pin.get('geometry');point=geometry.get('point') if isinstance(geometry,dict) else None
    if (not isinstance(point,(list,tuple)) or len(point)!=2
            or any(type(value)is not int for value in point)):
        return None
    at_point=[]
    for occurrence,other in terminals.items():
        other_geometry=other.get('geometry') if isinstance(other,dict) else None
        other_point=other_geometry.get('point') if isinstance(other_geometry,dict) else None
        if (isinstance(other_point,(list,tuple)) and len(other_point)==2
                and tuple(other_point)==tuple(point)):
            at_point.append(occurrence)
    if at_point!=[node]:return None
    source_literals=pin.get('source_literals')
    if not isinstance(source_literals,dict):return None
    own_reference=source_literals.get('reference')
    if own_reference not in (None,owner+'.'+pin_number):return None
    own_references=source_literals.get('references',[])
    if not isinstance(own_references,list) or any(value!=owner+'.'+pin_number for value in own_references):return None
    # Preserve source null aliases; accept only null history or the exact same typed pin.
    aliases=pin.get('endpoint_aliases',[])
    if not isinstance(aliases,list):return None
    for alias in aliases:
        alias_claim=alias.get('claim') if isinstance(alias,dict) else None
        if not isinstance(alias_claim,dict):return None
        if (alias_claim.get('kind')=='opaque-reference-value'
                and alias_claim.get('raw_type')=='null' and alias_claim.get('value') is None):continue
        alias_terminal=alias_claim.get('terminal')
        if (alias_claim.get('kind')!='terminal-reference'
                or alias_claim.get('parse_status')!='source-contact-syntax'
                or alias_claim.get('object_identifier')!=owner
                or not isinstance(alias_terminal,dict)
                or alias_terminal.get('pin_number')!=pin_number
                or alias_terminal.get('pin_number_status')!='observed'):
            return None
    return node


class ConversionError(ValueError):
    def __init__(self, code, message, **context):
        super().__init__(message)
        self.finding = {'code':code, 'message':message, **context}


def require(ok, code, message, **context):
    if not ok:raise ConversionError(code,message,**context)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def content_digest(document):
    value={k:v for k,v in document.items() if k!='review'}
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,
                             separators=(',',':'),allow_nan=False).encode('utf-8'))


def json_bytes(value):
    text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    text=re.sub(r'\[\n\s+(-?\d+),\n\s+(-?\d+)\n\s*\]',r'[\1, \2]',text)
    return (text+'\n').encode('utf-8')


def strict_json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,'duplicate_json_key','Duplicate JSON key',key=key)
            value[key]=item
        return value
    def constant(value):raise ConversionError('nonfinite_json','Non-finite JSON number',value=value)
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=constant)


def binding(path):return {'path':str(path.resolve()),'sha256':digest(path.read_bytes())}


def local_net_id(page,nodes,kind):
    """Human-approved naming for straps, unused rails and known constants."""
    require(kind in ('strap','unused','spare','gnd','+3v','no-source'),'local_net_kind','Unapproved local net suffix',kind=kind)
    eligible=[n for n in nodes if re.fullmatch(r'blocks/[A-Z]{2}/pins/L/[1-9]\d*',n)]
    require(bool(eligible),'local_net_anchor','No explicitly attached input terminal for local net naming',kind=kind)
    first=min(eligible,key=lambda n:(n.split('/')[1],int(n.split('/')[-1])))
    return page+first.split('/')[1]+'L'+first.split('/')[-1]+'-'+kind


def simplify(points):
    """Remove repeated and collinear intermediate vertices, preserving edges."""
    result=[]
    for point in points:
        require(isinstance(point,list) and len(point)==2 and all(type(v)is int for v in point),
                'route_coordinate','Route points must be integer [column,row]',point=point)
        require(0<=point[0]<245 and 0<=point[1]<103,'route_bounds','Route point is outside the approved template',point=point)
        if result and point==result[-1]:continue
        if result:
            require(point[0]==result[-1][0] or point[1]==result[-1][1],
                    'diagonal_route','Non-orthogonal route cannot be silently changed',point=point,previous=result[-1])
        result.append(point[:])
        if len(result)>=3:
            a,b,c=result[-3:]
            # Only remove a monotone collinear point; a reversal is significant.
            if ((a[0]==b[0]==c[0] and min(a[1],c[1])<=b[1]<=max(a[1],c[1])) or
                (a[1]==b[1]==c[1] and min(a[0],c[0])<=b[0]<=max(a[0],c[0]))):
                result.pop(-2)
    return result


def legacy_adapter(raw):
    """Adapt explicit legacy nodes/pins only; do not infer absent physical facts."""
    require(isinstance(raw.get('nodes'),list),'input_schema','Input is not a supported ALD diagram')
    page=raw.get('page')
    if isinstance(page,dict):page=page.get('page')
    if not page:page=raw.get('page_identifier')
    require(isinstance(page,str) and PAGE_ID.fullmatch(page),'page_identity','Missing explicit page ID')
    objects=[]
    for ordinal,node in enumerate(raw['nodes']):
        require(isinstance(node,dict) and 'CAS_box' not in node,'document_kind','CAS and non-ALD nodes require their own approved format')
        pins=node.get('pins',[])
        require(isinstance(pins,list),'legacy_pin_collection','Only explicit legacy pin arrays are supported')
        terminals=[]
        for i,pin in enumerate(pins):
            require(isinstance(pin,dict),'legacy_pin_record','Legacy pin must be an explicit object')
            number=pin.get('pin');status=pin.get('pin_status')
            if status is None:status='observed' if number else 'unlabeled'
            if number is not None:
                require(isinstance(number,str) and re.fullmatch(r'[A-Z]\d{2}',number),
                        'legacy_pin_identity','Legacy pin identity must already be separated from annotations',pin=number)
            literal=dict(pin)
            literal.setdefault('printed_label',number or '')
            literal.setdefault('references',[])
            literal.setdefault('reference',None)
            terminals.append({'pin_number':number,'pin_number_status':status,
                'side':pin.get('side'),'occurrence_kind':pin.get('occurrence_kind','primary'),
                'source_literals':literal,'geometry':{k:pin.get(k) for k in ('row','point','label_column','border_point')},
                'terminal_id':f'nodes:{ordinal}/t:{i}'})
        card=node.get('card_type','');portion=node.get('portion','')
        objects.append({'identifiers':{'id':node.get('id'),'grid':node.get('grid')},
            'geometry':{k:node.get(k) for k in ('column','row','height')},
            'function':{'label':node.get('function','')},'circuit':{'identifier':node.get('unit','')},
            'card_identity':{'card_type':card,'portion':portion},'site':{'label':node.get('location','')},
            'source_literals':copy.deepcopy(node),'terminals':terminals,
            'current_extensions':{'socket_listing_evidence':node.get('socket_listing_evidence',{})},
            'source_form':{'container':'nodes','ordinal':ordinal}})
    return {'schema':'legacy-explicit-adapter','page':{'page':page,'kind':'ald-diagram'},
            'objects':objects,'nets':[{'literal_id':n.get('id'),'source_literals':copy.deepcopy(n)} for n in raw.get('nets',[])],
            'junctions':raw.get('junctions',[]),'review':raw.get('review',{}),
            'current_extensions':{k:copy.deepcopy(v) for k,v in raw.items() if k not in ('nodes','nets','junctions','review')}}


def normalized(raw):
    require(isinstance(raw,dict),'input_type','Input must be a JSON object')
    if raw.get('schema')=='ibm360-ald-page-v3':
        require(raw.get('page',{}).get('kind')=='ald-diagram','document_kind',
                'Only ALD diagrams are covered by the approved functional format',kind=raw.get('page',{}).get('kind'))
        return copy.deepcopy(raw)
    require(not str(raw.get('schema','')).startswith('ibm360-ald-page-'),
            'input_schema','Unsupported canonical schema',schema=raw.get('schema'))
    return legacy_adapter(raw)


def choose_text(path,explicit=None,text_root=None):
    if explicit:return Path(explicit)
    if text_root:
        root=Path(text_root)
        matches=list(root.rglob(path.with_suffix('.txt').name))
        require(len(matches)==1,'text_lookup','Expected exactly one matching UTF-8 file',matches=[str(p) for p in matches])
        return matches[0]
    for parent in path.parents:
        if parent.name=='json':
            candidate=parent.parent/'ALD'/path.relative_to(parent).with_suffix('.txt')
            if candidate.is_file():return candidate
            break
    candidate=path.with_suffix('.txt')
    return candidate if candidate.is_file() else None


def get_pointer(value,pointer):
    require(isinstance(pointer,str) and pointer.startswith('/') and not re.search(r'~(?![01])',pointer),
            'correction_pointer','Invalid JSON pointer',pointer=pointer)
    for part in pointer[1:].split('/'):
        key=part.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def replace_pointer(value,pointer,old,new):
    current=get_pointer(value,pointer)
    require(type(current)==type(old) and current==old,'correction_preimage','Correction preimage mismatch',pointer=pointer)
    parent,piece=pointer.rsplit('/',1);container=get_pointer(value,parent) if parent else value
    key=piece.replace('~1','/').replace('~0','~')
    container[int(key) if isinstance(container,list) else key]=copy.deepcopy(new)


"""Private proposal: cover an exactly correlated physical-pin + X observation."""


def covers_exact_pin_x_suffix(label, terminal):
    """Return true only for a source label proved as pin text followed by X.

    This helper does not infer a pin or route. It requires the exact observed
    source fields, marker decoration, physical pin number and adjacent input
    label position. All other labels remain available for normal review.
    """
    if not isinstance(label, dict) or not isinstance(terminal, dict):
        return False
    lit = terminal.get("source_literals")
    geom = terminal.get("geometry")
    point = geom.get("point") if isinstance(geom, dict) else None
    if not isinstance(lit, dict) or not isinstance(point, list) or len(point) != 2:
        return False
    if (any(type(v) is not int for v in point)
            or type(label.get("column")) is not int
            or type(label.get("row")) is not int):
        return False
    if (geom.get("row") is not None and geom["row"] != point[1]
            or geom.get("column") is not None and geom["column"] != point[0]):
        return False
    pin = terminal.get("pin_number")
    marker = lit.get("border_marker")
    if (terminal.get("pin_number_status") != "observed" or not isinstance(pin, str)
            or not pin or marker != "X" or lit.get("pin") != pin
            or lit.get("printed_label") != pin or lit.get("pin_status") != "observed"
            or terminal.get("side") != "input" or lit.get("side") != "input"):
        return False
    decorations = terminal.get("border_decorations")
    if not isinstance(decorations, list) or not any(
        isinstance(d, dict) and d.get("kind") == "literal-border-mark"
        and d.get("glyph") == "X" and d.get("observed_value") == "X"
        for d in decorations
    ):
        return False
    # Contradictory border observations remain available for source review.
    for decoration in decorations:
        if not isinstance(decoration, dict):
            return False
        if decoration.get("kind") == "literal-border-mark":
            if any(decoration.get(k) not in (None, "X") for k in ("glyph", "observed_value")):
                return False
    return (label.get("text") == pin + "X"
            and label.get("row") == point[1]
            and label.get("column") == point[0] + 1)


def structured_printed_label_groups(value):
    """Validate grouped semantic labels without inventing coordinates.

    The grouped records are preserved in current_extensions. They are not
    projected into geometric labels because the records have no row/column.
    """
    if isinstance(value, list):
        return value
    require(isinstance(value, dict), 'labels', 'Printed labels must be an array or supported grouped object')
    require(set(value) == {'drive', 'inputs', 'outputs'}, 'labels', 'Grouped printed labels must contain exactly drive, inputs, and outputs')
    allowed = {'drive': [{'native_reviewed', 'origin', 'signal'}, {'native_reviewed', 'origin', 'polarity', 'signal'}], 'inputs': [{'native_reviewed', 'origin', 'selection', 'signal', 'suffix', 'text'}], 'outputs': [{'designation', 'destination', 'gate', 'native_reviewed', 'signal'}]}
    for group, records in value.items():
        require(isinstance(records, list), 'labels', 'Grouped label family must be an array', group=group)
        for i, record in enumerate(records):
            require(isinstance(record, dict) and set(record) in allowed[group], 'labels', 'Grouped label record has an unsupported shape', group=group, index=i)
            require(type(record.get('native_reviewed')) is bool, 'labels', 'Grouped label review marker must be boolean', group=group, index=i)
            require(all((isinstance(record.get(k), str) and record.get(k) for k in record if k != 'native_reviewed' and k != 'selection')), 'labels', 'Grouped label textual fields must be nonempty strings', group=group, index=i)
            if group == 'drive' and 'polarity' in record:
                require(record['polarity'] in ('even', 'odd'), 'labels', 'Grouped drive polarity is unsupported', index=i)
            if group == 'inputs':
                require(type(record.get('selection')) is int and record['selection'] >= 0, 'labels', 'Grouped input selection must be a nonnegative integer', index=i)
                require(record['text'] == record['signal'] + ' ' + record['suffix'], 'labels', 'Grouped input text must preserve signal and suffix exactly', index=i)
    return []

def grouped_output_projection_issue(value):
    """Keep unplaced semantic output destinations as an explicit technical hold."""
    if isinstance(value, dict) and value.get('outputs'):
        return {'field': 'outputs', 'kind': 'missing', 'visible text': '',
                'status': 'unresolved',
                'detail': 'Grouped source output destinations are retained in external conversion evidence but have no established functional output placement or node mapping. Source claims are not complete functional outputs; this is unfinished converter projection, not source ambiguity or a format decision.'}
    return None

def located_external_output_rows(nets, rows, net_names, existing_outputs):
    """Project only outgoing targets whose source coordinates and printed labels agree.

    The resulting output record preserves the visible source row and location.
    Its sink list stays empty because the source does not identify a recipient
    page pin. The unresolved endpoint claim remains in external evidence.
    """
    if (not isinstance(nets, dict) or not isinstance(rows, list)
            or not isinstance(net_names, dict) or not isinstance(existing_outputs, list)):
        return [], []
    occupied_numbers = {row.get('net number') for row in existing_outputs if isinstance(row, dict)}
    occupied_lines = {row.get('line') for row in existing_outputs if isinstance(row, dict)}
    projected = []; source_ids = []; used_lines = set(); used_numbers = set()
    for literal_id, record in nets.items():
        if not isinstance(literal_id, str) or not isinstance(record, dict) or record.get('literal_id') != literal_id:
            continue
        source = record.get('source_literals'); claims = record.get('endpoint_claims')
        if not isinstance(source, dict) or not isinstance(claims, list):
            continue
        targets = source.get('targets'); points = source.get('external')
        if not isinstance(targets, list) or not isinstance(points, list) or len(points) != 1:
            continue
        typed = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            ref = claim.get('reference')
            if (claim.get('relationship') == 'targets'
                    and claim.get('role_category') == 'declared-target'
                    and claim.get('resolution_status') == 'source-claim-unresolved'
                    and isinstance(ref, dict)
                    and ref.get('kind') == 'unparsed-object-reference'
                    and ref.get('object_identifier') == 'external'
                    and ref.get('parse_status') == 'unresolved-source-syntax'
                    and isinstance(ref.get('port_reference_text'), str)):
                typed.append(ref['port_reference_text'])
        if len(typed) != 1:
            continue
        port = typed[0]
        if targets != ['external.' + port]:
            continue
        point = points[0]
        if (not isinstance(point, list) or len(point) != 2 or point[0] != 204
                or type(point[1]) is not int or not 0 <= point[1] < 93):
            continue
        route_adjacency = {}
        for route in record.get('routes', []):
            if not isinstance(route, dict) or route.get('kind') != 'edges' or not isinstance(route.get('value'), list):
                continue
            for edge in route['value']:
                if (not isinstance(edge, list) or len(edge) != 2
                        or any(not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p) for p in edge)):
                    continue
                a, b = tuple(edge[0]), tuple(edge[1])
                route_adjacency.setdefault(a, set()).add(b)
                route_adjacency.setdefault(b, set()).add(a)
        if len(route_adjacency.get(tuple(point), ())) != 1:
            continue
        line = point[1]
        if line >= len(rows) or not isinstance(rows[line], str) or len(rows[line]) < 245:
            continue
        if rows[line][242:245] != port:
            continue
        number = net_names.get(literal_id)
        if (not isinstance(number, str) or not number or number in occupied_numbers
                or number in used_numbers or line in occupied_lines or line in used_lines):
            continue
        name = rows[line][211:242].rstrip('─ ').rstrip()
        if not name:
            continue
        projected.append({'net number': number, 'name': name, 'line': line, 'sinks': []})
        source_ids.append(literal_id); used_lines.add(line); used_numbers.add(number)
    return projected, source_ids

def unlocated_external_output_projection_issue(nets, outputs, net_names, rows):
    """Hold a typed external target unless its exact source-backed output row exists.

    A mapped output on the same source net satisfies the technical projection
    requirement only when its existing output fields match the uniquely located
    outgoing row, its printed label, and the retained source route endpoint.
    The historical endpoint claim remains in the source evidence either way.
    """
    if (not isinstance(nets, dict) or not isinstance(outputs, list)
            or not isinstance(net_names, dict) or not isinstance(rows, list)):
        return None
    for literal_id, record in nets.items():
        if not isinstance(literal_id, str) or not isinstance(record, dict):
            continue
        if record.get('literal_id') != literal_id:
            continue
        claims = record.get('endpoint_claims')
        source = record.get('source_literals')
        if not isinstance(claims, list) or not isinstance(source, dict):
            continue
        declared_targets = source.get('targets')
        if not isinstance(declared_targets, list):
            continue
        typed = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            ref = claim.get('reference')
            if (claim.get('relationship') == 'targets'
                    and claim.get('role_category') == 'declared-target'
                    and claim.get('resolution_status') == 'source-claim-unresolved'
                    and isinstance(ref, dict)
                    and ref.get('kind') == 'unparsed-object-reference'
                    and ref.get('object_identifier') == 'external'
                    and ref.get('parse_status') == 'unresolved-source-syntax'
                    and isinstance(ref.get('port_reference_text'), str)
                    and ref.get('port_reference_text')):
                typed.append(ref['port_reference_text'])
        if not typed:
            continue
        port = typed[0]
        located = (len(typed) == 1 and declared_targets == ['external.' + port])
        points = source.get('external')
        located = located and isinstance(points, list) and len(points) == 1
        point = points[0] if located else None
        located = (located and isinstance(point, list) and len(point) == 2
                   and point[0] == 204 and type(point[1]) is int
                   and 0 <= point[1] < 93 and point[1] < len(rows))
        if located:
            route_adjacency = {}
            for route in record.get('routes', []):
                if not isinstance(route, dict) or route.get('kind') != 'edges' or not isinstance(route.get('value'), list):
                    continue
                for edge in route['value']:
                    if (not isinstance(edge, list) or len(edge) != 2
                            or any(not isinstance(p, list) or len(p) != 2
                                   or any(type(v) is not int for v in p) for p in edge)):
                        continue
                    a, b = tuple(edge[0]), tuple(edge[1])
                    route_adjacency.setdefault(a, set()).add(b)
                    route_adjacency.setdefault(b, set()).add(a)
            located = len(route_adjacency.get(tuple(point), ())) == 1
        line = point[1] if located else None
        if located:
            located = (isinstance(rows[line], str) and len(rows[line]) >= 245
                       and rows[line][242:245] == port)
        number = net_names.get(literal_id)
        name = rows[line][211:242].rstrip('─ ').rstrip() if located else ''
        located = (located and isinstance(number, str) and bool(number)
                   and bool(name))
        matching = []
        if located:
            matching = [row for row in outputs if isinstance(row, dict)
                        and row.get('net number') == number
                        and row.get('line') == line
                        and row.get('name') == name
                        and row.get('sinks') == []]
        if located and len(matching) == 1:
            continue
        return {'field': 'outputs', 'kind': 'missing', 'visible text': port,
                'status': 'unresolved',
                'detail': 'The typed external target remains in source history, but its exact source-backed output row is absent or conflicting. The output projection remains unresolved; no output row, recipient pin, or destination is inferred.'}
    return None

def attach_grouped_label_evidence(review, value):
    """Copy grouped semantic label records to external conversion evidence."""
    if isinstance(value, dict):
        review['conversion evidence']['source printed label groups'] = copy.deepcopy(value)
    return review

def terminal_span_label(label, printed, side, border, row):
    """Recognize exact split observations inside an established printed span.

    A number or control substring is not interpreted. The caller has already
    established the terminal identity and complete printed presentation.
    """
    if not printed or side not in ('L', 'R') or label.get('row') != row:
        return False
    x = label.get('column'); text = label.get('text', '')
    if type(x) is not int or not text:
        return False
    start = border-len(printed) if side == 'L' else border
    expected = printed+'│' if side == 'L' else '│'+printed
    offset = x-start
    return 0 <= offset and offset+len(text) <= len(expected) and expected[offset:offset+len(text)] == text

def sink_prefix_label(label, sink, column, row, graph):
    """Cover a parsed output sink plus its explicitly owned graphical prefix."""
    x = label.get('column'); text = label.get('text', '')
    if type(x) is not int or label.get('row') != row or not x < column:
        return False
    prefix = text[:column-x]
    return (bool(prefix) and set(prefix) <= WIRE and text == prefix + sink
            and all((xx, row) in graph for xx in range(x, column))
            and all((xx+1, row) in graph.get((xx, row), set())
                    for xx in range(x, column-1)))


def explicitly_unprinted_terminal(pin):
    """Use positive source declarations, never an absent/empty label alone."""
    if pin.get('pin_number_status') not in ('unparsed-or-control','unlabeled','explicit-none'):return False
    lit=pin.get('source_literals',{})
    printed_label=lit.get('printed_label')
    if pin.get('pin_number') is not None or not isinstance(printed_label,str):return False
    if printed_label and printed_label!=(lit.get('printed_prefix') or '')+(lit.get('printed_suffix') or ''):return False
    observations=lit.get('source_observations',[])
    printed=[o.get('value') for o in observations if o.get('field')=='printed_pin']
    if any(value!='' for value in printed):return False
    if printed:return True
    return (lit.get('border_marker') in ('K','E','X','◺') and
            any(o.get('field')=='border_only_label' and o.get('value') is True
                for o in observations))


def neutral_k_observation_marker(pin, node, marker, observed):
    """Read existing K spellings only for an explicitly neutral auxiliary.

    Geometry, projected decoration and passive membership remain subject to
    the qualified auxiliary reader. No source fact is replaced or invented.
    """
    literal=pin.get('source_literals',{})
    observations=literal.get('source_observations',[])
    require(isinstance(observations,list) and all(isinstance(o,dict) for o in observations),
            'auxiliary_marker','K observations must be an array of objects',node=node)
    fields=('marker','printed_qualifier','border_qualifier','border_control')
    qualifiers=[o for o in observations if o.get('field') in fields]
    if not qualifiers:return marker
    require(all(set(o)=={'field','value'} and o['value']=='K' for o in qualifiers)
            and all(sum(o.get('field')==field for o in qualifiers)<=1 for field in fields),
            'auxiliary_marker','K spelling needs exact, unique, coherent observations',node=node)
    role='auxiliary-output-modifier'
    require([o.get('value') for o in observations if o.get('field')=='role']==[role]
            and 'role' not in literal and pin.get('role') in (None,role)
            and 'side' in pin and pin['side'] is None
            and 'side' in literal and literal['side'] is None,
            'auxiliary_role','K spelling requires the canonical neutral auxiliary role',node=node)
    mirrored=pin.get('extensions',{}).get('source_observations',[])
    require(isinstance(mirrored,list) and all(isinstance(o,dict) for o in mirrored),
            'auxiliary_marker','Mirrored K observations must be objects',node=node)
    for field in fields+('role','native_commoned_contact'):
        values=[o for o in observations if o.get('field')==field]
        mirror=[o for o in mirrored if o.get('field')==field]
        require(not mirror or mirror==values,'auxiliary_marker','Mirrored K facts conflict',node=node,field=field)
        if field=='native_commoned_contact':
            native=[o.get('value') for o in pin.get('role_observations',[])
                    if o.get('kind')=='native_commoned_contact']
            require(bool(values) or not native,'auxiliary_role','Native role evidence lacks its exact source observation',node=node)
        if field=='native_commoned_contact' and values:
            require(len(values)==1 and set(values[0])=={'field','value'}
                    and type(values[0]['value']) is bool,
                    'auxiliary_role','Native contact observation must be one explicit boolean',node=node)
            native=[o.get('value') for o in pin.get('role_observations',[])
                    if o.get('kind')=='native_commoned_contact']
            require(not native or native==[values[0]['value']],
                    'auxiliary_role','Native contact role observations conflict',node=node)
    require(marker in (None,'K') and observed <= {'K'}
            and all(o.get('value')=='K' for o in observations
                    if o.get('field') in ('border_control','border_qualifier'))
            and (literal.get('triangle') is None or literal.get('triangle') is False),
            'auxiliary_marker','K spelling conflicts with another border modifier',node=node)
    decorations=pin.get('border_decorations',[])
    require(isinstance(decorations,list) and all(isinstance(d,dict) for d in decorations),
            'auxiliary_marker','K decorations must be an array of objects',node=node)
    for decoration in decorations:
        positions=decoration.get('position_observations',[])
        require(isinstance(positions,list) and all(isinstance(o,dict) for o in positions)
                and not any(o.get('kind')=='border_point' and o.get('value') is not None
                            and o.get('value')!=pin.get('geometry',{}).get('border_point') for o in positions),
                'auxiliary_placement','K decoration conflicts with the exact right border point',node=node)
        if decoration.get('kind')=='literal-border-mark':
            require(decoration.get('glyph') in (None,'K')
                    and decoration.get('observed_value') in (None,'K')
                    and decoration.get('edge') in (None,'output','right','R'),
                    'auxiliary_marker','K spelling conflicts with a projected border decoration',node=node)
        if decoration.get('kind')=='triangle':
            require(decoration.get('glyph') is None
                    and (decoration.get('observed_value') is None or decoration.get('observed_value') is False),
                    'auxiliary_marker','K spelling conflicts with a projected triangle',node=node)
    return 'K'


def auxiliary_modifier(pin,block):
    """Recognize only an explicit neutral K role with exact drawn placement.

    This is an attachment, never a signal direction or a net-origin claim.
    """
    role='auxiliary-output-modifier';lit=pin.get('source_literals',{});g=pin.get('geometry',{});bg=block.get('geometry',{})
    observations=lit.get('source_observations',[])
    roles=[o.get('value') for o in observations if o.get('field')=='role']
    if any(o.get('field') in ('marker','printed_qualifier') and o.get('value')=='K' for o in observations):
        neutral_k_observation_marker(pin,pin.get('terminal_id'),lit.get('border_marker'),set())
    border_k=(lit.get('border_marker')=='K'
              or any(o.get('field') in ('border_qualifier','border_control') and o.get('value')=='K' for o in observations)
              or any(d.get('kind')=='literal-border-mark' and d.get('glyph')=='K'
                     for d in pin.get('border_decorations',[])))
    require(not border_k or roles==[role],
            'auxiliary_role','K border attachment requires its canonical neutral auxiliary role',terminal=pin.get('terminal_id'))
    if role not in roles and pin.get('role')!=role:return False
    require(roles==[role] and 'role' not in lit and pin.get('role') in (None,role)
            and all(o.get('value')==role for o in pin.get('role_observations',[]) if o.get('kind')=='role'),
            'auxiliary_role','One exact canonical role observation is required without contradictory role facts',terminal=pin.get('terminal_id'))
    row=g.get('row');column=bg.get('column')
    require('side' in pin and 'side' in lit and pin['side'] is None and lit['side'] is None,
            'auxiliary_role','Auxiliary modifier must have explicit neutral source side',terminal=pin.get('terminal_id'))
    require(type(column)is int and type(row)is int and g.get('border_point')==[column+7,row]
            and lit.get('border_point')==g.get('border_point'),
            'auxiliary_placement','Auxiliary K needs the exact observed right border point',terminal=pin.get('terminal_id'))
    marker=typed_border_qualifier(pin,pin.get('terminal_id'),lit.get('border_marker'),set())
    require(neutral_k_observation_marker(pin,pin.get('terminal_id'),marker,set())=='K','auxiliary_marker','Auxiliary role needs explicit K border evidence',terminal=pin.get('terminal_id'))
    observations=lit.get('source_observations',[])
    mirrored_sides=pin.get('extensions',{}).get('source_observations',[])
    require(isinstance(mirrored_sides,list) and all(isinstance(o,dict) for o in mirrored_sides),
            'auxiliary_placement','Mirrored side evidence must be an array of objects',terminal=pin.get('terminal_id'))
    require(not any(o.get('field') in ('physical_side','native_physical_side','layout_side','border_side')
                    and o.get('value') not in ('output','right','R') for o in observations+mirrored_sides),
            'auxiliary_placement','Auxiliary role has conflicting side evidence',terminal=pin.get('terminal_id'))
    decorations=[d for d in pin.get('border_decorations',[]) if d.get('kind')=='literal-border-mark' and d.get('glyph') is not None]
    require((bool(decorations) or any(o.get('field') in ('marker','printed_qualifier') for o in observations)) and all(d.get('glyph')=='K'
            and (d.get('edge') in ('output','right','R') or (d.get('edge') is None and any(
                o.get('kind')=='border_point' and o.get('value')==g.get('border_point') for o in d.get('position_observations',[]))))
            and not any(o.get('kind')=='border_point' and o.get('value') is not None and o.get('value')!=g.get('border_point')
                        for o in d.get('position_observations',[])) for d in decorations),
            'auxiliary_marker','Auxiliary role has missing or conflicting projected K evidence',terminal=pin.get('terminal_id'))
    printed=lit.get('printed_label');span=printed
    border_glyph=[o for o in observations if o.get('field')=='border_glyph']
    mirrored_glyph=[o for o in pin.get('extensions',{}).get('source_observations',[]) if o.get('field')=='border_glyph']
    if isinstance(printed,str) and printed.startswith('K'):
        require(len(border_glyph)<=1 and all(set(o)=={'field','value'} and o['value']=='K' for o in border_glyph)
                and (not mirrored_glyph or mirrored_glyph==border_glyph),
                'auxiliary_marker','K prefix conflicts with border glyph evidence',terminal=pin.get('terminal_id'))
    explicit_border=(lit.get('border_marker')=='K' and bool(decorations)
        and all(d.get('edge') in ('right','R','output') and any(o.get('kind')=='border_point' and o.get('value')==g.get('border_point') for o in d.get('position_observations',[])) for d in decorations)
        and len(border_glyph)<=1 and all(set(o)=={'field','value'} and o['value']=='K' for o in border_glyph)
        and (not mirrored_glyph or mirrored_glyph==border_glyph))
    if (isinstance(printed,str) and printed.startswith('K')
            and (any(o.get('field') in ('marker','printed_qualifier') for o in observations) or explicit_border)):
        number=pin.get('pin_number')
        require(pin.get('pin_number_status')=='observed' and isinstance(number,str)
                and bool(number) and printed=='K'+number,
                'auxiliary_placement','Border-prefix K requires its exact observed physical contact label',terminal=pin.get('terminal_id'))
        span=number  # K occupies the positively bound right border cell.
    require(isinstance(span,str) and g.get('point')==[column+8+len(span),row],
            'auxiliary_placement','Auxiliary attachment does not match its exact existing printed span',terminal=pin.get('terminal_id'))
    return True


def _source_bound_existing_net_membership(node, net, membership, terminals, auxiliary):
    """Reuse one terminal already resolved onto this net; infer no route point."""
    if (not isinstance(node, str) or not isinstance(net, str) or not net
            or not isinstance(membership, dict) or membership.get(node) != net
            or not isinstance(terminals, dict) or not isinstance(auxiliary, set)
            or node in auxiliary):
        return None
    pin = terminals.get(node)
    if (not isinstance(pin, dict) or pin.get('side') != 'input'
            or pin.get('occurrence_kind') != 'primary'
            or pin.get('pin_number_status') != 'observed'
            or not isinstance(pin.get('pin_number'), str)):
        return None
    return node


def typed_border_qualifier(pin, node, marker, observed):
    """Project an explicit typed K border qualifier; preserve signal/pin facts."""
    literal = pin.get('source_literals', {})
    observations = literal.get('source_observations', [])
    require(isinstance(observations, list)
            and all(isinstance(item, dict) for item in observations),
            'pin_edge', 'Terminal source observations must be an array of objects', node=node)
    qualifiers = [item for item in observations if item.get('field') == 'border_qualifier']
    if not qualifiers:
        return marker
    require(len(qualifiers) == 1 and set(qualifiers[0]) == {'field', 'value'}
            and qualifiers[0]['value'] == 'K',
            'pin_edge', 'Border qualifier needs one exact typed K observation', node=node)
    controls = [item.get('value') for item in observations if item.get('field') == 'border_control']
    require(marker in (None, 'K') and observed <= {'K'}
            and all(value == 'K' for value in controls)
            and (literal.get('triangle') is None or literal.get('triangle') is False),
            'pin_edge', 'Typed K border qualifier conflicts with another border modifier', node=node)
    return 'K'


def hanging_origin_suffix_annotation(label, rows, labels, inputs, newnets):
    """Retain an exact trailing hanging-origin star as existing net annotation.

    Both printed origin labels, the established input record and its owned
    entry route must agree. This carries no pin or connector interpretation.
    """
    x,y,text=label.get('column'),label.get('row'),label.get('text','')
    match=re.fullmatch(r'✲([A-Z]{2}\d{3}[A-Z]{2}\d+)✲',text)
    if x!=1 or type(y)is not int or not 0<y<min(93,len(rows)) or not match:return None
    if rows[y][x:x+len(text)]!=text:return None
    if sum(l==label for l in labels)!=1:return None
    entries=[i for i in inputs if i.get('reference style')=='hanging' and i.get('line')==y-1
             and i.get('real net number',i.get('net number'))==match[1]]
    if len(entries)!=1:return None
    identity=entries[0]['net number']
    printed=[l for l in labels if l.get('row')==y and l.get('text')==identity
             and type(l.get('column'))is int and 20<=l['column']<=45
             and rows[y][l['column']:l['column']+len(identity)]==identity]
    if len(printed)!=1:return None
    owners=[n for n in newnets if 'inputs/'+identity in n['nodes']]
    if len(owners)!=1:return None
    net=owners[0];graph=wire_graph(net['routing']);column=printed[0]['column']
    if not any((column+len(identity)+delta,y) in graph for delta in (-1,0)):return None
    end=x+len(text)-1
    if any(l is not label and l.get('row')==y and type(l.get('column'))is int
           and l['column']<=end<l['column']+len(l.get('text','')) for l in labels):return None
    anchors=[(abs(end-px)+abs(y-py),i,j,px,py) for i,line in enumerate(net['routing'])
             for j,(px,py) in enumerate(line)]
    if not anchors:return None
    _,i,j,px,py=min(anchors)
    return net,{'at':{'polyline':i,'point':j},'offset':[end-px,y-py],'text':'✲'}


def output_name_covers_token(labels, rows, row, column, token):
    """Exclude only a token proved to be inside the explicit inline name span."""
    if column <= 205 or not PAGE_ID.fullmatch(token):return False
    candidates=[l for l in labels if l.get('row')==row and l.get('column')==211
                and isinstance(l.get('text'),str)
                and 211+len(l['text'])<=242
                and 211<=column and column+len(token)<=211+len(l['text'])
                and rows[row][211:211+len(l['text'])]==l['text']]
    if len(candidates)!=1:return False
    owner=candidates[0]
    for label in labels:
        if label is owner or label.get('row')!=row:continue
        start=label.get('column');text=label.get('text')
        if type(start)is int and isinstance(text,str) and text.strip():
            if max(start,column)<min(start+len(text),column+len(token)):return False
    return True


def source_function_offset(block, placement, rows, layout_rows, external_text_binding=None):
    """Preserve explicit canonical function geometry with exact display evidence.

    Exact field bindings keep their established priority. The fallback only
    interprets function_column_offset (from the left border), not other
    historical offset aliases. Both embedded source layout and supplied TXT
    must corroborate the complete ordinary block interior.
    """
    geometry=block['geometry'];x=geometry.get('column')
    if placement is not None:
        return placement['column']-x-1
    literal=block['source_literals']
    if 'function_column_offset' not in geometry:
        return literal.get('function_offset',0)
    serial=block['identifiers']['id'];offset=geometry['function_column_offset']
    require(isinstance(external_text_binding,dict)
            and set(external_text_binding)=={'path','sha256'}
            and isinstance(external_text_binding['path'],str)
            and bool(external_text_binding['path'])
            and isinstance(external_text_binding['sha256'],str)
            and re.fullmatch(r'[0-9a-f]{64}',external_text_binding['sha256']) is not None,
            'function_offset_external_text',
            'Explicit function geometry fallback requires a bound external TXT',block=serial)
    label=block['function'].get('label');row=geometry.get('row')
    form=block.get('source_form',{})
    require(form.get('container')=='nodes' and type(form.get('ordinal')) is int
            and form['ordinal']>=0,'function_offset_evidence',
            'Explicit function geometry requires a canonical node source form',block=serial)
    require(type(x) is int and type(row) is int and type(offset) is int
            and isinstance(label,str) and bool(label) and label==label.strip()
            and all(ord(character)>=32 for character in label)
            and literal.get('function')==label,
            'function_offset_evidence','Function geometry has missing or untyped source evidence',block=serial)
    require(not any(key in geometry or key in literal for key in
                    ('function_offset','function_column','function_indent')),
            'function_offset_conflict','Function geometry has competing offset claims',block=serial)
    if 'function_column_offset' in literal:
        require(type(literal['function_column_offset']) is int
                and literal['function_column_offset']==offset,
                'function_offset_conflict','Literal and projected function geometry disagree',block=serial)
    require(0<=x and x+7<245 and 1<=offset and offset+len(label)<=7 and 0<=row+1<len(rows)
            and row+1<len(layout_rows),'function_offset_bounds',
            'Function displacement does not fit the ordinary block interior',block=serial)
    expected=' '*(offset-1)+label+' '*(7-offset-len(label))
    require(all(isinstance(table[row+1],str) and table[row+1][x+1:x+7]==expected
                for table in (rows,layout_rows)),
            'function_offset_evidence','Function geometry disagrees with exact source layout or selected TXT',block=serial)
    return offset-1


def ordinary_input_reference_occurrences(rows, reference, graph, labels):
    """Read a unique full ordinary entry attached to this net's recorded route."""
    if not isinstance(reference,str) or PAGE_REF.fullmatch(reference) is None:return []
    pattern=re.compile(r'(?<![A-Za-z0-9_])'+re.escape(reference)+r'(?![A-Za-z0-9_])')
    found=[{'row':y,'column':m.start(),'text':reference}
           for y,row in enumerate(rows[:93]) for m in pattern.finditer(row)
           if 20<=m.start()<=45]
    # Return all conflicts so the caller's exact-one guard remains authoritative.
    if len(found)!=1:return found
    entry=found[0];x=entry['column'];y=entry['row'];end=x+len(reference)
    require(any((end+gap,y) in graph for gap in (0,1)),
            'input_reference','Ordinary input reference lacks its explicitly owned route endpoint',
            reference=reference,occurrences=found)
    overlapping=[]
    for label in labels:
        if label.get('row')!=y:continue
        lx=label.get('column');literal=label.get('text','')
        if not(type(lx)is int and isinstance(literal,str) and literal.strip()):continue
        if max(x,lx)<min(end,lx+len(literal)):overlapping.append(label)
    for label in overlapping:
        lx=label['column'];literal=label['text']
        if lx==x and literal==reference:continue
        offset=x-lx;prefix=literal[:offset];suffix=literal[offset+len(reference):]
        wrapped=(len(overlapping)==1 and 0<=lx and offset>0 and literal.count(reference)==1
                 and literal[offset:offset+len(reference)]==reference
                 and re.fullmatch(r'─+',prefix) is not None
                 and re.fullmatch(r'─+┘',suffix) is not None
                 and rows[y][lx:lx+len(literal)]==literal
                 and all((xx,y) in graph for xx in list(range(lx,x))+list(range(end,lx+len(literal)))))
        require(wrapped,'input_reference','Ordinary input reference overlaps a conflicting recorded label',
                reference=reference,occurrences=found,label=label)
    return found


def source_bound_spare_label(path, paths, nets, labels, text_path):
    """Bind only a complete, uniquely witnessed SPARE/numbered-source pair.

    The two recorded route components stay separate; this does not add an edge.
    """
    if path.get('net')!='SPARE-label' or text_path is None:return None
    if sum(p.get('net')=='SPARE-label' for p in paths)!=1:return None
    net=nets.get('SPARE')
    if not isinstance(net,dict):return None
    literal=net.get('source_literals',{});driver=literal.get('driver');targets=literal.get('targets')
    if not (isinstance(driver,str) and re.fullmatch(r'external\.\d{3}',driver)
            and isinstance(targets,list) and targets and all(isinstance(x,str) and x for x in targets)
            and len(set(targets))==len(targets)):return None
    for key,record in nets.items():
        source=record.get('source_literals',{})
        if not isinstance(source,dict):return None
        for field,value in source.items():
            if 'driver' not in field.lower() or (key=='SPARE' and field=='driver'):continue
            values=value if isinstance(value,list) else [value]
            if driver in values:return None
        if key=='SPARE' and any('driver' in field.lower() and field!='driver' and value not in (None,[]) for field,value in source.items()):return None
    mark=[l for l in labels if l.get('text')=='SPARE']
    number=driver.split('.',1)[1];numbered=[l for l in labels if l.get('text')==number]
    if len(mark)!=1 or len(numbered)!=1:return None
    a=mark[0];b=numbered[0];x=a.get('column');y=a.get('row');nx=b.get('column')
    if not(type(x)is int and type(y)is int and type(nx)is int and x==1 and 0<=y<93 and b.get('row')==y and x+len('SPARE')<nx<=45):return None
    points=path.get('points');owned=[p for p in paths if p.get('net')=='SPARE']
    if not (isinstance(points,list) and len(points)==2 and points[0]==[0,y] and points[1][1]==y
            and type(points[1][0])is int and x+len('SPARE')<=points[1][0]<nx and owned):return None
    try:
        graph=wire_graph([simplify(p.get('points',[])) for p in owned]);rows=Path(text_path).read_text(encoding='utf-8-sig').splitlines()
    except (OSError,UnicodeError,ValueError,TypeError,IndexError):return None
    if (nx,y) not in graph or y>=len(rows) or rows[y][x:x+5]!='SPARE' or rows[y][nx:nx+3]!=number:return None
    for other in labels:
        if other is a or other is b or other.get('row')!=y:continue
        ox=other.get('column');ot=other.get('text','')
        if type(ox)is int and isinstance(ot,str) and ot.strip() and (max(x,ox)<min(x+5,ox+len(ot)) or max(nx,ox)<min(nx+3,ox+len(ot))):return None
    right=max(xx for xx,yy in graph if yy==y and xx>=nx)
    row=rows[y]
    if (right>=len(row) or row[0] not in (' ','─')
            or any(row[xx]!='─' for xx in range(x+5,points[1][0]+1))
            or any(row[xx]!=' ' for xx in range(points[1][0]+1,nx))
            or any(row[xx] not in WIRE-{' '} for xx in range(nx+3,right+1))):return None
    for other in paths:
        if other is path or other.get('net')=='SPARE':continue
        try:other_graph=wire_graph([simplify(other.get('points',[]))])
        except (ValueError,TypeError,IndexError):return None
        if any((xx,y) in other_graph for xx in range(0,right+1)):return None
    return {'net':'SPARE','source path':copy.deepcopy(path),'label':copy.deepcopy(a),'number label':copy.deepcopy(b),'driver':driver}


class Converter:
    def normalize_terminal_row(self,pin,block,serial):
        g=pin.get('geometry',{});top=block.get('geometry',{}).get('row');row=g.get('row')
        require(type(top)is int and type(row)is int,'terminal_position',
                'Terminal and block rows must be exact integers',block=serial,terminal=pin.get('terminal_id'))
        observation_values=[]
        for container_name,container in (('extensions',pin.get('extensions',{})),
                                         ('source_literals',pin.get('source_literals',{}))):
            require(isinstance(container,dict),'terminal_position',
                    'Terminal observation container must be an object',block=serial,terminal=pin.get('terminal_id'),container=container_name)
            observation_list=container.get('source_observations',[])
            require(isinstance(observation_list,list),'terminal_position',
                    'Terminal source_observations must be an array',block=serial,terminal=pin.get('terminal_id'),container=container_name)
            require(all(isinstance(item,dict) for item in observation_list),'terminal_position',
                    'Terminal source observations must be objects',block=serial,terminal=pin.get('terminal_id'),container=container_name)
            values=[item.get('value') for item in observation_list if item.get('field')=='absolute_row']
            require(len(values)<=1,'terminal_position',
                    'A source observation container repeats absolute_row',block=serial,terminal=pin.get('terminal_id'),container=container_name,count=len(values))
            if values:
                require(type(values[0]) is int,'terminal_position',
                        'absolute_row observation must be an exact integer',block=serial,terminal=pin.get('terminal_id'),container=container_name)
                observation_values.append((container_name,values[0]))
        require(len({value for _,value in observation_values})<=1,'terminal_position',
                'Mirrored absolute_row observations contradict one another',block=serial,terminal=pin.get('terminal_id'),observations=observation_values)
        explicit_rows=[]
        for container in (g,pin.get('source_literals',{})):
            for key in ('point','border_point'):
                point=container.get(key) if isinstance(container,dict) else None
                if point is not None:
                    require(isinstance(point,list) and len(point)==2 and type(point[0]) is int and type(point[1]) is int,
                            'terminal_position','Explicit point must be an integer coordinate pair',block=serial,terminal=pin.get('terminal_id'),field=key)
                    explicit_rows.append((key,point[1]))
        abs_value=observation_values[0][1] if observation_values else None
        if observation_values:
            local_value=top+row
            require(row==abs_value or local_value==abs_value,
                    'terminal_position','absolute_row contradicts terminal geometry row',block=serial,terminal=pin.get('terminal_id'),geometry_row=row,block_top=top,absolute_row=abs_value)
            for field,point_row in explicit_rows:
                require(point_row==abs_value,'terminal_position','Explicit point row contradicts absolute_row',block=serial,terminal=pin.get('terminal_id'),field=field,point_row=point_row,absolute_row=abs_value)
            effective=abs_value
            basis='absolute_geometry' if row==abs_value else 'block_local_geometry'
        elif explicit_rows:
            values={value for _,value in explicit_rows}
            require(len(values)==1,'terminal_position','Explicit point rows contradict one another',block=serial,terminal=pin.get('terminal_id'),point_rows=explicit_rows)
            point_row=next(iter(values));absolute_match=(row==point_row);local_match=(top+row==point_row)
            require(absolute_match or local_match,'terminal_position','Explicit point row does not agree with terminal geometry',block=serial,terminal=pin.get('terminal_id'),geometry_row=row,block_top=top,point_row=point_row)
            effective=point_row;basis='absolute_geometry' if absolute_match else 'block_local_geometry'
        else:
            # Retain the converter's existing absolute-row convention only
            # where it yields a valid within-block line. A lower row without
            # independent evidence is held rather than guessed to be local.
            require(row>=top,'terminal_position','Local-looking geometry row has no absolute-row evidence',block=serial,terminal=pin.get('terminal_id'),geometry_row=row,block_top=top)
            effective=row;basis='preserved_absolute_geometry'
        require(effective>=top,'terminal_position','Terminal is above its block',block=serial,terminal=pin.get('terminal_id'),page_row=effective,block_top=top)
        evidence={'block':serial,'terminal':pin.get('terminal_id'),'source_geometry_row':row,'block_top':top,
                  'absolute_row_observation':abs_value,'explicit_point_rows':explicit_rows,'effective_page_row':effective,'basis':basis}
        g['row']=effective
        return evidence

    def __init__(self,document,source_path,source_hash,text_path=None,*,allow_partial=False):
        self.source=normalized(document);self.path=source_path;self.source_hash=source_hash
        self.e=self.source['current_extensions'];self.pid=self.source['page']['page']
        require(isinstance(self.pid,str) and PAGE_ID.fullmatch(self.pid),'page_identity','Invalid page identifier',page=self.pid)
        self.issues=[];self.warnings=[];self.gaps=[];self.annotations=defaultdict(list);self.membership={}
        self.allow_partial=allow_partial;self.diagnostic_inputs={};self.coordinate_views=[];self.semantic_input_resolutions=[]
        self.labels=structured_printed_label_groups(self.e.get('printed_labels',[]))
        require(isinstance(self.labels,list),'labels','Printed labels must be an array')
        self.owners={};self.terminals={};self.aliases=defaultdict(list);self.primary_aliases=defaultdict(list);self.object_ids={};self.auxiliary=set();self.auxiliary_history=[]
        for block in self.source['objects']:
            identifier=block['identifiers'].get('id')
            require(isinstance(identifier,str) and bool(identifier),
                    'block_identity','Stable block identifier must be a nonempty string',identifier=identifier)
            require(identifier not in self.object_ids,'duplicate_object_identifier',
                    'Duplicate stable block identifier',identifier=identifier)
            # Both retained explicit readings are evidence; neither may mask the other.
            explicit_readings=[(field,record['printed_id'])
                    for field,record in (('identifiers',block['identifiers']),
                                         ('source_literals',block['source_literals']))
                    if 'printed_id' in record]
            for field,explicit in explicit_readings:
                require(isinstance(explicit,str) and re.fullmatch(r'[A-Z]{2}',explicit),
                        'block_identity','Explicit printed block serial is not an unambiguous two-letter reading',
                        identifier=identifier,field=field,serial=explicit)
            require(len({value for field,value in explicit_readings})<=1,
                    'conflicting_block_identity','Retained explicit printed block identities disagree',
                    identifier=identifier,readings=dict(explicit_readings))
            serial=explicit_readings[0][1] if explicit_readings else identifier
            require(isinstance(serial,str) and re.fullmatch(r'[A-Z]{2}',serial),'block_identity','Block needs an unambiguous two-letter serial',serial=serial)
            require(serial not in self.owners,'duplicate_block','Duplicate block serial',serial=serial)
            self.object_ids[identifier]=serial
            self.owners[serial]=block
            for source_pin in block['terminals']:
                require(source_pin.get('occurrence_kind','primary')=='primary','alternate_terminal',
                        'Unresolved alternate terminal observations need an explicit source decision',block=serial)
                # Keep the source owner record untouched; all converter row consumers use this interpreted copy.
                pin=copy.deepcopy(source_pin)
                side=pin.get('side');g=pin['geometry'];top=block['geometry'].get('row')
                self.coordinate_views.append(self.normalize_terminal_row(pin,block,serial))
                auxiliary=auxiliary_modifier(pin,block)
                if auxiliary:side='output'  # R is physical presentation only; source side stays null.
                elif side=='input':
                    right=[block['geometry'].get('column',-1000)+7,g.get('row')]
                    require(g.get('border_point')!=right and pin.get('source_literals',{}).get('border_point')!=right,
                            'right_signal_input','Ordinary right-border input is a source classification error',terminal=pin.get('terminal_id'))
                require(side in ('input','output') and type(g.get('row')) is int and type(top)is int,
                        'terminal_position','Terminal side or row is unresolved',block=serial,terminal=pin.get('terminal_id'))
                # All downstream geometry consumers see one page-row view.
                # The source copy and its original row are retained in the
                # conversion evidence; no source file is modified.
                line=g['row']-top+1
                require(line>=1,'terminal_position','Terminal is above its block',block=serial)
                node=f"blocks/{serial}/pins/{'L' if side=='input' else 'R'}/{line}"
                require(node not in self.terminals,'duplicate_terminal','Several terminals occupy the same side and line',node=node)
                self.terminals[node]=pin
                if auxiliary:self.auxiliary.add(node)
                lit=pin['source_literals']
                refs=[lit.get('reference')]+lit.get('references',[])
                primary=lit.get('reference')
                if isinstance(primary,str):self.primary_aliases[primary].append(node)
                # These are aliases of explicitly recorded terminals, not pin
                # identities inferred from geometry or neighbouring cards.
                stems={identifier,serial}
                for stem in stems:
                    if pin.get('pin_number'):
                        refs.extend((stem+'.'+pin['pin_number'],stem+'.'+side+'.'+pin['pin_number']))
                    if lit.get('printed_label'):
                        refs.extend((stem+'.'+lit['printed_label'],stem+'.'+side+'.'+lit['printed_label']))
                for ref in refs:
                    if isinstance(ref,str) and node not in self.aliases[ref]:self.aliases[ref].append(node)
        self.nets={}
        for n in self.source['nets']:
            old=n['literal_id'];require(isinstance(old,str) and old not in self.nets,'net_identity','Missing or duplicate legacy net ID',net=old)
            self.nets[old]=n
        self.paths=defaultdict(list)
        self.spare_bindings=[]
        wire_paths=self.e.get('wire_paths',[])
        for p in wire_paths:
            if p.get('net') not in self.nets and p.get('points') and all(210<=x<=241 and 93<=y<=102 for x,y in p['points']):
                self.warnings.append({'code':'title_frame_path','message':'Decorative title-frame path is reproduced by the ordinary template, not stored as an electrical net.'})
                continue
            owner=p.get('net')
            if owner not in self.nets:
                spare=source_bound_spare_label(p,wire_paths,self.nets,self.labels,text_path)
                if spare is not None:
                    self.spare_bindings.append(spare);owner=spare['net']
            if owner not in self.nets:
                resolved=caption_tail_owner(p,wire_paths,self.nets,self.labels)
                if resolved is not None:
                    self.warnings.append({'code':'caption_tail_owner','source net':owner,'net':resolved,
                        'message':'Caption tail continues the uniquely identified incoming output wire; recorded polylines remain unchanged.'})
                    owner=resolved
            require(owner in self.nets,'route_owner','Wire path has no declared net',net=p.get('net'))
            points=simplify(p.get('points',[]))
            if len(points)>1:self.paths[owner].append(points)
        self.graphs={n:wire_graph(self.paths[n]) for n in self.nets}
        for old,record in self.nets.items():
            recorded=[]
            for route in record.get('routes',[]):
                if route.get('kind')=='edges':recorded.extend(simplify(edge) for edge in route['value'])
                elif route.get('kind')=='paths':recorded.extend(simplify(points) for points in route['value'])
            claimed=wire_graph(recorded)
            if not self.graphs[old] and claimed:
                self.paths[old]=recorded;self.graphs[old]=claimed
            elif claimed:
                require(all(p in self.graphs[old] and adjacent<=self.graphs[old][p] for p,adjacent in claimed.items()),
                    'route_claim_conflict','Explicit net routes disagree with the drawing wire paths; a source decision is required',net=old)
        self.rows=[];self.text_binding=None;self.newline='\n';self.trim=False
        if text_path:
            raw=text_path.read_bytes();body=raw.decode('utf-8-sig')
            self.rows=body.splitlines();self.text_binding=binding(text_path)
            endings=re.findall(r'\r\n|\r|\n',body)
            if endings and len(set(endings))==1:self.newline=endings[0]
            else:self.warnings.append({'code':'mixed_line_endings','message':'Output uses LF; source has mixed or absent line endings'})
            self.trim=all(r==r.rstrip() for r in self.rows)
        else:self.rows=self.restore_text_rows()
        require(len(self.rows)==103 and max(map(len,self.rows),default=0)<=245,
                'page_template','Page dimensions are outside the approved ordinary ALD template',rows=len(self.rows),columns=max(map(len,self.rows),default=0))
        self.bindings={v['pointer']:v for v in self.e.get('text_layout',{}).get('bindings',[])}
        self.page=self.page_fields();self.names={};self.inputs=[];self.input_nodes={};self.nodes=defaultdict(list);self.no_source=set()
        self.logical_output_partitions=[]
        self.partition_repeated_outputs()

    def issue(self,field,kind,visible,detail,**extra):
        self.issues.append({'field':field,'kind':kind,'visible text':visible,'status':'unresolved','detail':detail,**extra})

    def restore_text_rows(self):
        """Resolve source layout bindings as data; never execute source code."""
        layout=self.e.get('text_layout',{});rows=layout.get('rows',[])
        require(bool(rows),'text_required','No adjacent UTF-8 file or embedded text layout; supply --text or --text-root')
        objects={b['source_form']['ordinal']:b for b in self.owners.values() if b['source_form'].get('container')=='nodes'}
        def scalar(pointer):
            parts=pointer[1:].split('/')
            if parts[0]=='nodes':
                obj=objects[int(parts[1])]
                if len(parts)==3:
                    key=parts[2]
                    if key in obj['source_literals']:return obj['source_literals'][key]
                    if key in obj['geometry']:return obj['geometry'][key]
                if len(parts)==5 and parts[2]=='pins':
                    source_form=obj['source_form'].get('terminal_collections',[])
                    collection=next((c for c in source_form if c['field']=='pins'),None)
                    require(collection is not None,'text_binding','Pin binding has no explicit collection map')
                    tid=collection['members'][int(parts[3])]['terminal_id']
                    return next(p for p in obj['terminals'] if p['terminal_id']==tid)['source_literals'][parts[4]]
            return get_pointer(self.e,pointer)
        bindings=layout.get('bindings',[]);values=[]
        try:
            for b in bindings:
                value=scalar(b['pointer'])
                require(isinstance(value,str) and len(value)<=b['width'],'text_binding','Source text binding is not a fitting string',pointer=b['pointer'])
                values.append(value.ljust(b['width']))
            result=[]
            for row in rows:
                chars=[' ']*row['width']
                for run in row['runs']:
                    kind=run['kind'];column=run['column']
                    if kind=='field':text=values[run['binding']]
                    elif kind=='glyphs':text=run['text']
                    elif kind=='spaces':text=' '*run['count']
                    else:raise ConversionError('text_run','Unsupported source text run',kind=kind)
                    chars[column:column+len(text)]=text
                result.append(''.join(chars))
            endings={r.get('eol','') for r in rows};self.newline=next(iter(endings)) if len(endings)==1 and '' not in endings else '\n'
            self.trim=all(r==r.rstrip() for r in result)
            return result
        except (KeyError,IndexError,StopIteration) as exc:
            raise ConversionError('text_binding','Embedded layout cannot be reconstructed without a source UTF-8 file',detail=str(exc)) from exc

    def cell(self,x,y,width):return self.rows[y][x:x+width].strip()

    def page_fields(self):
        p={'page':self.pid,'page-type':'ALD','origin':'scan'}
        header=self.cell(235,0,10)
        if re.fullmatch(r'\d{3}\s+'+self.pid,header):
            version=header[:3]
            if version!='000':p['version']=version
        title=[self.cell(211,y,30) for y in (94,95)]
        p['title']=[s for s in title if s]
        for key,(x,y,width) in {'date':(218,96,8),'machine':(233,96,7),'log':(214,98,11),
                'frame':(239,98,2),'p/n':(233,100,7),'ibm division':(223,102,3),'next block':(239,102,2)}.items():
            value=self.cell(x,y,width)
            if not value or '\ufffd' in value:
                p[key]=None;self.issue('page/'+key,'missing',value,'Field is absent or unresolved in the existing transcription; no original-scan reading is inferred.')
            else:p[key]=value
        revisions=[]
        for row in self.rows[93:]:
            m=re.match(r'(\d\d-\d\d-\d\d) (\d{6})',row[175:])
            if m:revisions.append({'date':m[1],'num':m[2]})
        if revisions:p['revisions']=revisions
        return p

    def reference_owner_serial(self,owner):
        serial=self.object_ids.get(owner,owner)
        require(owner not in self.owners or serial==owner,
                'ambiguous_object_reference','Owner spelling identifies distinct stable and printed objects',
                reference=owner,candidates=sorted({owner,serial}))
        return serial

    def terminal_candidates(self,ref,role,net=None):
        """Return recorded occurrences, retaining physical-pin aliases as aliases."""
        require(isinstance(ref,str),'terminal_reference','Terminal reference must be a string',reference=ref)
        require(role in ('driver','target'),'endpoint_role','Unsupported terminal reference role',reference=ref,role=role)
        side='output' if role=='driver' else 'input'
        qualified=re.fullmatch(r'(?:(?P<page>[A-Z]{2}[0-9]{3}))?(?P<owner>[A-Z][A-Z0-9_]*)\.(?P<label>[^@\s]+)@(?P<row>[0-9]+)',ref)
        require('@' not in ref or qualified is not None,'terminal_reference',
                'Malformed row-qualified terminal reference',reference=ref)
        if qualified:
            page,owner,label,row_text=qualified.group('page','owner','label','row')
            require(page is None or page==self.pid,'terminal_reference',
                    'Qualified terminal reference names another page',reference=ref,page=page)
            try:row=int(row_text)
            except ValueError:
                raise ConversionError('terminal_reference','Invalid row-qualified terminal reference',reference=ref)
            serials={self.object_ids.get(owner,owner),owner}
            # An explicit alias is evidence subject to the declared occurrence;
            # it cannot override owner, role or row constraints.
            aliases=self.aliases.get(ref,[])
            for node in aliases:
                pin=self.terminals[node]
                require(node.split('/')[1] in serials
                        and pin.get('side')==side
                        and type(pin.get('geometry',{}).get('row')) is int
                        and pin['geometry']['row']==row,
                        'terminal_reference','Qualified alias contradicts its owner, role or recorded row',
                        reference=ref,role=role,candidate=node,
                        recorded_row=pin.get('geometry',{}).get('row'))
            selected=[node for node,pin in self.terminals.items()
                    if node.split('/')[1] in serials and pin.get('side')==side
                    and pin.get('geometry',{}).get('row')==row
                    and (label==pin.get('pin_number') or label==pin.get('source_literals',{}).get('printed_label')
                         or label==side or ref==pin.get('source_literals',{}).get('reference')
                         or ref in pin.get('source_literals',{}).get('references',[]))]
            selected=list(dict.fromkeys(selected+aliases))
            require(len({node.split('/')[1] for node in selected})<=1,
                    'ambiguous_terminal_alias','Qualified reference aliases terminals on distinct objects',
                    reference=ref,candidates=selected)
            require(owner not in self.object_ids or not selected
                    or all(node.split('/')[1]==self.object_ids[owner] for node in selected),
                    'conflicting_terminal_owner','Qualified alias disagrees with its stable object identifier',
                    reference=ref,stable_owner=self.object_ids.get(owner),candidates=selected)
            return selected
        candidates=self.aliases.get(ref,[])
        # A preferred spelling cannot hide another object's terminal.
        require(len({node.split('/')[1] for node in candidates})<=1,
                'ambiguous_terminal_alias','Reference aliases terminals on distinct objects',
                reference=ref,candidates=candidates)
        owner=ref.split('.',1)[0]
        require(owner not in self.object_ids or not candidates
                or all(node.split('/')[1]==self.object_ids[owner] for node in candidates),
                'conflicting_terminal_owner','Terminal alias disagrees with its stable object identifier',
                reference=ref,stable_owner=self.object_ids.get(owner),candidates=candidates)
        role_port=False
        role_match=re.fullmatch(r'([A-Z]{2})\.(select|drive|output)',ref)
        if role_match and role=='target' and net is not None:
            role_record=self.nets.get(net)
            role_literal=role_record.get('source_literals') if isinstance(role_record,dict) else None
            role_port=isinstance(role_literal,dict) and ref in (role_literal.get('ports') or [])
        if candidates:
            if not role_port:
                return [n for n in candidates if self.terminals[n]['side']==side] or candidates
        # Some source nets use semantic ports such as AN.input1 even when the
        # ordered source pin array records the corresponding physical terminal
        # without a printed pin number. Resolve this only when the v3 source
        # explicitly preserves one complete `pins` array, whose terminal IDs
        # match the block's recorded terminals exactly. The ordinal is among
        # input-side terminals in that source order; it is never a geometry,
        # row-neighbor, or cross-page inference.
        indexed=re.fullmatch(r'([A-Z]{2})\.input([1-9][0-9]*)',ref)
        if indexed and role=='target':
            owner,index=indexed.groups();serial=self.reference_owner_serial(owner)
            block=self.owners.get(serial)
            if block is None:return []
            source_form=block.get('source_form',{})
            collections=source_form.get('terminal_collections',[])
            if not isinstance(collections,list) or any(not isinstance(c,dict) for c in collections):return []
            pins=[c for c in collections if c.get('field')=='pins' and c.get('representation')=='array']
            if len(pins)!=1:return []
            members=pins[0].get('members',[])
            if not isinstance(members,list):return []
            if any(not isinstance(m,dict) for m in members):return []
            ordered_ids=[m.get('terminal_id') for m in members]
            block_pins=block.get('terminals',[])
            if not isinstance(block_pins,list) or any(not isinstance(p,dict) for p in block_pins):return []
            block_ids=[p.get('terminal_id') for p in block_pins]
            if (any(not isinstance(tid,str) or not tid for tid in ordered_ids+block_ids)
                    or len(set(ordered_ids))!=len(ordered_ids)
                    or len(set(block_ids))!=len(block_ids)
                    or ordered_ids!=block_ids):
                return []
            ordered_set=set(ordered_ids)
            by_id={p.get('terminal_id'):node for node,p in self.terminals.items()
                   if node.split('/')[1]==serial and p.get('terminal_id') in ordered_set}
            if set(by_id)!=set(ordered_ids):return []
            inputs=[by_id[tid] for tid in ordered_ids if self.terminals[by_id[tid]].get('side')=='input']
            ordinal=int(index)-1
            if ordinal>=len(inputs) or net is None:return []
            # Array order alone does not establish a universal inputN contract.
            # Require a unique exact recorded input at an endpoint of THIS
            # source-owned net route, agreeing with the ordered source array.
            endpoints={tuple(point) for path in self.paths.get(net,[]) if path
                       for point in (path[0],path[-1])}
            anchored=[node for node,pin in self.terminals.items()
                      if node.split('/')[1]==serial and pin.get('side')=='input'
                      and node not in self.auxiliary
                      and self.recorded_route_anchors(node).intersection(endpoints)]
            if anchored!=[inputs[ordinal]]:return []
            proof={'kind':'source ordered input selector with exact route corroboration',
                   'source net ID':net,'reference':ref,'terminal':inputs[ordinal],
                   'source terminal ID':self.terminals[inputs[ordinal]].get('terminal_id'),
                   'recorded route endpoints':sorted(self.recorded_route_anchors(inputs[ordinal]).intersection(endpoints))}
            if proof not in self.semantic_input_resolutions:self.semantic_input_resolutions.append(proof)
            return [inputs[ordinal]]
        # Alphabetic input aliases are not ordinals. Resolve only when the
        # exact same-net claim, complete source array, and one nonconflicting
        # route endpoint all agree on one recorded input occurrence.
        named=re.fullmatch(r'([A-Z]{2})\.input([A-Z]{2})',ref)
        if named and role=='target':
            owner,selector=named.groups()
            object_ids=getattr(self,'object_ids',None); owners=getattr(self,'owners',None)
            terminals=getattr(self,'terminals',None); nets=getattr(self,'nets',None)
            paths=getattr(self,'paths',None); auxiliary=getattr(self,'auxiliary',None)
            proofs=getattr(self,'semantic_input_resolutions',None)
            if (not isinstance(object_ids,dict) or not isinstance(owners,dict)
                    or not isinstance(terminals,dict) or not isinstance(nets,dict)
                    or not isinstance(paths,dict) or not isinstance(auxiliary,set)
                    or not isinstance(proofs,list) or net is None or net!=selector):return []
            serial=self.reference_owner_serial(owner); block=owners.get(serial)
            record=nets.get(net)
            if not isinstance(block,dict) or not isinstance(record,dict):return []
            source_literals=record.get('source_literals')
            if (record.get('literal_id')!=selector or not isinstance(source_literals,dict)
                    or source_literals.get('id')!=selector):return []
            declared=source_literals.get('targets')
            target_ref=owner+'.input'+selector
            if not isinstance(declared,list) or target_ref not in declared:return []
            raw_claims=record.get('endpoint_claims',[])
            if not isinstance(raw_claims,list):return []
            claims=[]
            for claim in raw_claims:
                if not isinstance(claim,dict):continue
                reference=claim.get('reference')
                if (isinstance(reference,dict)
                        and claim.get('relationship')=='targets'
                        and claim.get('role_category')=='declared-target'
                        and claim.get('resolution_status')=='source-claim-unresolved'
                        and reference.get('kind')=='unparsed-object-reference'
                        and reference.get('object_identifier')==owner
                        and reference.get('port_reference_text')=='input'+selector):claims.append(claim)
            # Identical repeated observations are historical evidence, not
            # another terminal. Conflicting claims remain unresolved.
            if not claims or len({json.dumps(c,sort_keys=True,separators=(',',':')) for c in claims})!=1:return []
            source_form=block.get('source_form',{})
            if not isinstance(source_form,dict):return []
            collections=source_form.get('terminal_collections',[])
            if not isinstance(collections,list) or any(not isinstance(c,dict) for c in collections):return []
            pins=[c for c in collections if c.get('field')=='pins' and c.get('representation')=='array']
            if len(pins)!=1:return []
            members=pins[0].get('members',[])
            if not isinstance(members,list) or any(not isinstance(m,dict) for m in members):return []
            ordered_ids=[m.get('terminal_id') for m in members]
            block_pins=block.get('terminals',[])
            if not isinstance(block_pins,list) or any(not isinstance(p,dict) for p in block_pins):return []
            block_ids=[p.get('terminal_id') for p in block_pins]
            if (any(not isinstance(tid,str) or not tid for tid in ordered_ids+block_ids)
                    or len(set(ordered_ids))!=len(ordered_ids)
                    or len(set(block_ids))!=len(block_ids)
                    or ordered_ids!=block_ids):return []
            ordered_set=set(ordered_ids)
            by_id={pin.get('terminal_id'):node for node,pin in terminals.items()
                   if isinstance(pin,dict) and isinstance(node,str)
                   and len(node.split('/'))>2 and node.split('/')[1]==serial
                   and pin.get('terminal_id') in ordered_set}
            if set(by_id)!=ordered_set:return []
            inputs=[by_id[tid] for tid in ordered_ids
                    if terminals[by_id[tid]].get('side')=='input']
            owner_inputs=[node for node,pin in terminals.items()
                          if isinstance(pin,dict) and isinstance(node,str)
                          and len(node.split('/'))>2 and node.split('/')[1]==serial
                          and pin.get('side')=='input']
            if set(owner_inputs)!=set(inputs):return []
            endpoints=set(); route_paths=paths.get(net)
            if not isinstance(route_paths,list) or not route_paths:return []
            for path in route_paths:
                if not isinstance(path,(list,tuple)) or len(path)<2:return []
                for point in (path[0],path[-1]):
                    if (not isinstance(point,(list,tuple)) or len(point)!=2
                            or any(type(v)is not int for v in point)):return []
                    endpoints.add(tuple(point))
            anchors={}
            for node in owner_inputs:
                geometry=terminals[node].get('geometry')
                if not isinstance(geometry,dict):return []
                point=geometry.get('point'); col=geometry.get('column'); row=geometry.get('row')
                observed=set()
                if point is not None:
                    if (not isinstance(point,(list,tuple)) or len(point)!=2
                            or any(type(v)is not int for v in point)):return []
                    observed.add(tuple(point))
                if col is not None or row is not None:
                    if type(col)is not int or type(row)is not int:return []
                    observed.add((col,row))
                if len(observed)>1:return []
                anchors[node]=observed
            # Count every same-owner input observation before accepting uniqueness.
            anchored=[node for node in owner_inputs if anchors[node].intersection(endpoints)]
            if len(anchored)!=1:return []
            selected=anchored[0]
            anchor=sorted(anchors[selected].intersection(endpoints))
            proof={'kind':'source named input alias with exact route corroboration',
                   'source net ID':net,'reference':ref,'source target claim':claims[0],
                   'terminal':selected,
                   'source terminal ID':terminals[selected].get('terminal_id'),
                   'source input order':inputs.index(selected)+1,
                   'recorded route endpoints':anchor}
            if len(claims)>1:proof['source target claim observations']=copy.deepcopy(claims)
            if proof not in proofs:proofs.append(proof)
            return [selected]
        named_role=re.fullmatch(r'([A-Z]{2})\.([a-z]+)',ref)
        # A `ports` claim is enumerated through the generic target path, but
        # output membership must follow the terminal's actual output role.
        if named_role and role=='target' and named_role.group(2)=='output' and net is not None:
            owner,selector=named_role.groups();serial=self.reference_owner_serial(owner)
            record=self.nets.get(net);literal=record.get('source_literals') if isinstance(record,dict) else None
            claims=record.get('endpoint_claims') if isinstance(record,dict) else None
            selected=_source_bound_output_role_alias(
                ref,role,net,owner,selector,literal,claims,self.terminals,serial,self.auxiliary)
            if selected is None:return []
            owner_port_claim=next(c for c in claims if c.get('relationship')=='ports')
            owner_driver_claim=next(c for c in claims if c.get('relationship') in ('driver','drivers'))
            proof={'kind':'source output role alias with same-net semantic membership and typed physical driver',
                   'source net ID':net,'reference':ref,
                   'source logical port claim':owner_port_claim,
                   'source physical driver claim':owner_driver_claim,
                   'terminal':selected,'source terminal ID':self.terminals[selected].get('terminal_id')}
            if proof not in self.semantic_input_resolutions:self.semantic_input_resolutions.append(proof)
            return [selected]
        # Input role aliases require same-net claims and one recorded input.
        if named_role and role=='target' and net is not None:
            owner,selector=named_role.groups(); serial=self.reference_owner_serial(owner)
            record=self.nets.get(net); block=self.owners.get(serial)
            if not isinstance(record,dict) or not isinstance(block,dict):return []
            literal=record.get('source_literals')
            if not isinstance(literal,dict) or ref not in (literal.get('ports') or []):return []
            claims=record.get('endpoint_claims',[])
            if not isinstance(claims,list):return []
            owner_ports=[c for c in claims if isinstance(c,dict)
                         and c.get('relationship')=='ports'
                         and isinstance(c.get('reference'),dict)
                         and c['reference'].get('kind')=='unparsed-object-reference'
                         and c['reference'].get('object_identifier')==owner]
            logical=[c for c in owner_ports
                     if c.get('role_category')=='declared-membership-or-reference'
                     and c.get('resolution_status')=='source-claim-unresolved'
                     and c['reference'].get('port_reference_text')==selector]
            if (not logical or len(owner_ports)!=len(logical)
                    or len({json.dumps(c,sort_keys=True,separators=(',',':')) for c in logical})!=1):return []
            declared_targets=literal.get('targets')
            if not isinstance(declared_targets,list) or any(not isinstance(x,str) for x in declared_targets):return []
            owner_targets={x for x in declared_targets if x.startswith(owner+'.')}
            if len(owner_targets)!=1:return []
            declared_pin=re.fullmatch(re.escape(owner)+r'\.([A-Z][0-9]+)',next(iter(owner_targets)))
            if declared_pin is None:return []
            physical=[]
            owner_target_claims=[]
            for c in claims:
                r=c.get('reference') if isinstance(c,dict) else None
                if (isinstance(r,dict) and c.get('relationship')=='targets'
                        and r.get('object_identifier')==owner):
                    owner_target_claims.append(c)
                    t=r.get('terminal')
                    if (r.get('kind')=='terminal-reference'
                            and c.get('role_category')=='declared-target'
                            and c.get('resolution_status')=='source-claim-unresolved'
                            and isinstance(t,dict) and isinstance(t.get('pin_number'),str)):
                        physical.append((t['pin_number'],c))
            # The literal, structured claims, and recorded terminal must name
            # one same physical target. Any second identity remains unresolved.
            if (not owner_target_claims or len(physical)!=len(owner_target_claims)
                    or {pin for pin,_ in physical}!={declared_pin.group(1)}):return []
            role_nodes=[node for node,pin in self.terminals.items()
                        if isinstance(pin,dict) and isinstance(node,str)
                        and len(node.split('/'))>2 and node.split('/')[1]==serial
                        and pin.get('side')=='input' and pin.get('role')==selector
                        and node not in self.auxiliary]
            matching=[]
            for node in role_nodes:
                pin=self.terminals[node]
                recorded=pin.get('pin_number')
                if (isinstance(recorded,str) and pin.get('pin_number_status')=='observed'
                        and any(claim_pin==recorded for claim_pin,_ in physical)):
                    matching.append(node)
            if len(matching)!=1:return []
            existing=_source_bound_existing_net_membership(
                matching[0],net,getattr(self,'membership',None),self.terminals,self.auxiliary)
            if existing is not None:
                proof={'kind':'source role alias reuses same-net typed physical target membership',
                       'source net ID':net,'reference':ref,'terminal':existing,
                       'source terminal ID':self.terminals[existing].get('terminal_id'),
                       'route completeness':'unresolved independently'}
                if proof not in self.semantic_input_resolutions:self.semantic_input_resolutions.append(proof)
                return [existing]
            graph=self.graphs.get(net)
            if not isinstance(graph,dict) or not graph:return []
            # Edge-form source routes are stored as many two-point paths, so
            # their individual edge endpoints include interior vertices.
            # An interior vertex needs stronger source binding than an endpoint.
            endpoints={point for point,adjacent in graph.items() if len(adjacent)==1}
            node=matching[0]; geometry=self.terminals[node].get('geometry',{})
            point=geometry.get('point') if isinstance(geometry,dict) else None
            if (not isinstance(point,(list,tuple)) or len(point)!=2
                    or any(type(v)is not int for v in point)):return []
            physical_matches=[c for pin,c in physical if pin==self.terminals[node].get('pin_number')]
            if not physical_matches:return []
            if tuple(point) not in endpoints:
                if not _source_bound_branch_attachment(
                        point,graph,node,matching,self.terminals,owner,selector,literal,
                        logical,owner_target_claims,physical):return []
                proof_kind='source role alias with same-net claim and exact interior terminal attachment'
            else:
                proof_kind='source role alias with same-net claim and exact route endpoint'
            proof={'kind':proof_kind,
                   'source net ID':net,'reference':ref,'source logical port claim':logical[0],
                   'source physical target claim':physical_matches[0],'terminal':node,
                   'source terminal ID':self.terminals[node].get('terminal_id')}
            if tuple(point) in endpoints:proof['recorded route endpoints']=[list(point)]
            if proof not in self.semantic_input_resolutions:self.semantic_input_resolutions.append(proof)
            return [node]
        return []


    def repeated_output_pair(self,candidates):
        """The two logical rows can intentionally share one physical pin."""
        if len(candidates)!=2:return False
        if any(len(n.split('/'))!=5 for n in candidates):return False
        if {n.split('/')[3] for n in candidates}!={'R'} or {n.split('/')[-1] for n in candidates}!={'2','4'}:return False
        if len({n.split('/')[1] for n in candidates})!=1 or any(n in self.auxiliary for n in candidates):return False
        numbers=[self.terminals[n].get('pin_number') for n in candidates]
        return isinstance(numbers[0],str) and bool(numbers[0]) and numbers[0]==numbers[1]

    def recorded_route_anchors(self,node):
        """Only exact source observations; no nearby-cell or pin-number guesses."""
        geometry=self.terminals[node].get('geometry',{});result=set()
        point=geometry.get('point')
        if isinstance(point,list) and len(point)==2 and all(type(v)is int for v in point):result.add(tuple(point))
        if type(geometry.get('column'))is int and type(geometry.get('row'))is int:
            result.add((geometry['column'],geometry['row']))
        return result

    def resolve(self,ref,role,net=None):
        selected=self.terminal_candidates(ref,role,net)
        if role=='driver' and net is not None and self.repeated_output_pair(selected):
            graph=self.graphs.get(net,{})
            # A pin shared electrically is not a reason to merge the drawn nets.
            selected=[n for n in selected if self.recorded_route_anchors(n).intersection(graph)]
        require(len(selected)==1,'terminal_reference','Reference does not select exactly one recorded terminal',reference=ref,role=role,candidates=selected)
        require(role!='driver' or selected[0] not in self.auxiliary,
                'auxiliary_driver','Auxiliary attachment cannot be selected as a driver or net origin',reference=ref)
        return selected[0]

    def partition_repeated_outputs(self):
        """Project a legacy physical-net grouping into its two drawn logical nets.

        Split only two disjoint recorded route components, one per explicitly
        recorded same-pin R/2 and R/4 occurrence. Preserve every original edge
        and assign targets only when their recorded occurrence is unambiguous.
        The original grouping is retained in external conversion evidence.
        """
        for old,record in list(self.nets.items()):
            literal=record['source_literals'];driver=literal.get('driver')
            if not isinstance(driver,str):continue
            candidates=self.terminal_candidates(driver,'driver')
            if not self.repeated_output_pair(candidates):continue
            graph=self.graphs[old];remaining=set(graph);components=[]
            while remaining:
                todo=[min(remaining)];component=set()
                while todo:
                    point=todo.pop()
                    if point in component:continue
                    component.add(point);todo.extend(graph[point]-component)
                remaining-=component;components.append(component)
            if len(components)!=2:continue
            owner_components={}
            for node in candidates:
                matches=[i for i,component in enumerate(components)if self.recorded_route_anchors(node).intersection(component)]
                if len(matches)!=1:break
                owner_components[node]=matches[0]
            if len(owner_components)!=2 or len(set(owner_components.values()))!=2:continue
            # Extra driver/relationship forms need their own explicit handling.
            fields={'id','driver','targets','external','external_references','semantic_driver'}
            if set(literal)-fields:continue
            if any(c.get('relationship') not in fields for c in record.get('endpoint_claims',[])):continue
            target_components={};safe=True
            for target in literal.get('targets',[]):
                if not isinstance(target,str):safe=False;break
                # A physical grouping does not establish which drawn output
                # owns an unanchored remote claim. Never duplicate it into both.
                if target.split('.',1)[0] not in self.object_ids:safe=False;break
                targets=self.terminal_candidates(target,'target',old)
                if len(targets)!=1:safe=False;break
                matches=[i for i,component in enumerate(components)if self.recorded_route_anchors(targets[0]).intersection(component)]
                if len(matches)!=1:safe=False;break
                target_components[target]=matches[0]
            if not safe:continue
            partitions=[]
            for node in sorted(candidates,key=lambda n:int(n.split('/')[-1])):
                index=owner_components[node];component=components[index];key=old+'@'+node
                require(key not in self.nets,'net_identity','Logical partition identifier collides',net=key)
                paths=[copy.deepcopy(p)for p in self.paths[old]if tuple(p[0])in component]
                require(wire_graph(paths)=={p:graph[p] for p in component},'route_partition','Logical partition must preserve every source edge',net=old)
                projected=copy.deepcopy(record);projected['literal_id']=key
                projected['source_literals']['targets']=[r for r in literal.get('targets',[])if r not in target_components or target_components[r]==index]
                self.nets[key]=projected;self.paths[key]=paths;self.graphs[key]=wire_graph(paths)
                partitions.append({'projection ID':key,'output terminal':node,'source route graph vertices':len(component)})
            self.logical_output_partitions.append({'source net ID':old,'original source record':copy.deepcopy(record),'partitions':partitions,
                'reason':'Human-confirmed repeated physical pin on separate logical output rows; disjoint source route components preserved, no electrical join inferred.'})
            del self.nets[old];del self.paths[old];del self.graphs[old]

    def external_input(self,old,literal):
        driver=literal.get('driver','')
        normalized_driver=re.sub(r'([A-Z]{2}\d{3})\.([A-Z]{2}\d+)',r'\1\2',driver) if isinstance(driver,str) else ''
        refs=PAGE_REF.findall(normalized_driver)
        ports=[p for p in self.e.get('external_ports',[]) if isinstance(p,dict) and p.get('direction')=='input' and p.get('net')==old]
        if not refs and len(ports)==1:refs=[ports[0].get('reference')]
        refs=list(dict.fromkeys(r for r in refs if isinstance(r,str) and PAGE_REF.fullmatch(r)))
        # Read a reference on this net's explicitly owned left-side route.
        # This establishes a printed entry identity, never physical membership.
        graph=self.graphs[old]
        entries=[l for l in self.labels if PAGE_REF.fullmatch(l.get('text','')) and 20<=l.get('column',999)<=45
                 and any((x,l['row']) in graph for x in range(0,46))]
        if not refs and len(entries)==1:refs=[entries[0]['text']]
        require(len(refs)==1,'external_origin','External net requires one explicit full origin reference',net=old,references=refs)
        ref=refs[0]
        # Every ordinary reference goes through the same lexical, unique,
        # in-column, owned-endpoint and overlap checks, even with one label.
        found=ordinary_input_reference_occurrences(self.rows,ref,graph,self.labels)
        if not found and len(entries)==1 and entries[0]['text']!=ref:
            # Indirect hanging references retain the actual full origin after
            # the star and a separately recorded ordinary displayed reference.
            indirect=entries[0];row=self.rows[indirect['row']]
            real=PAGE_REF.match(row[2:]) if row[1:2]=='✲' else None
            if (real is not None and real[0]==ref
                    and (2+len(ref)==len(row) or re.match(r'[A-Za-z0-9_]',row[2+len(ref)]) is None)):
                display=ordinary_input_reference_occurrences(self.rows,indirect['text'],graph,self.labels)
                if len(display)==1:
                    require(display[0]['row']==indirect['row'] and display[0]['column']==indirect['column'],
                            'input_reference','Indirect displayed reference disagrees with its recorded label',
                            reference=ref,occurrences=display,label=indirect)
                found=display
        diagnostic=False
        if not found and self.allow_partial:
            # Diagnostic-only recovery: both literal observations were already
            # explicitly recorded on this net. Never infer a malformed origin.
            display=self.nets[old].get('extensions',{}).get('additional_printed_origin')
            if input_display_literal(display) and display!=ref:
                candidates=[]
                for label in self.labels:
                    x=label.get('column');y=label.get('row')
                    if not(type(x)is int and type(y)is int and 20<=x<=45 and 0<y<93 and label.get('text')==display):continue
                    row=self.rows[y];real=PAGE_REF.match(row[2:]) if row[1:2]=='✲' else None
                    if not real or real[0]!=ref or (2+len(ref)<len(row) and not row[2+len(ref)].isspace()):continue
                    if row[x:x+len(display)]!=display:continue
                    if x<2+len(ref):continue
                    if not any((x+len(display)+gap,y) in graph for gap in (0,1)):continue
                    overlap=False
                    for other in self.labels:
                        if other is label or other.get('row')!=y:continue
                        ox=other.get('column');ot=other.get('text','')
                        if type(ox)is int and ot.strip() and max(x,ox)<min(x+len(display),ox+len(ot)):overlap=True
                    if not overlap:candidates.append(label)
                require(len(candidates)==1,'input_reference','Diagnostic input literal has no unique nonoverlapping source/star/owned-route binding',reference=ref,occurrences=candidates)
                found=candidates;diagnostic=True
        require(len(found)==1,'input_reference','Printed input reference is absent or ambiguous',reference=ref,occurrences=found)
        found=found[0];y=found['row'];row=self.rows[y]
        hanging=row[1:2]=='✲'
        name_row=y-1 if hanging else y
        name=self.rows[name_row][1:32].rstrip('─ ').strip()
        require(bool(name),'input_name','Input signal name is missing',reference=ref)
        if diagnostic:
            self.diagnostic_inputs[ref]={'column':found['column'],'row':y,'literal':found['text']}
            self.issue('inputs/'+ref+'/net number','conflicting',found['text'],
                'Diagnostic only: explicit starred real origin is retained as identity; separately recorded conflicting printed entry is a source-bound display literal, not a corrected origin.',
                **{'at':[found['column'],y],'original net ID':old,'real starred origin':ref})
        else:ref=found['text']
        result={'net number':ref,'name':name,'line':name_row}
        actual=ref
        if hanging:
            result['reference style']='hanging'
            m=PAGE_REF.match(row[2:])
            require(m is not None and (2+m.end()==len(row) or re.match(r'[A-Za-z0-9_]',row[2+m.end()]) is None),
                    'input_origin','Hanging input has no readable full origin token',reference=ref)
            actual=m[0]
            if actual!=ref:result['real net number']=actual
        offset=found['column']-32
        return result,actual,offset

    def output_destination_driver(self,old,literal):
        """Recognize a destination page accidentally recorded as an origin.

        Only a unique explicitly claimed local driver connected to the
        matching ordinary output is eligible. No source object is rewritten.
        """
        ref=literal.get('driver')
        if not isinstance(ref,str) or not PAGE_REF.fullmatch(ref):return None
        if any(l.get('text')==ref and 0<=l.get('column',999)<=45 for l in self.labels):return None
        if any(ref in row[:46] for row in self.rows):return None
        additional=literal.get('additional_drivers')
        if not isinstance(additional,list) or len(additional)!=1 or not isinstance(additional[0],str):return None
        if literal.get('drivers'):return None
        candidate=additional[0]
        if candidate.split('.',1)[0] not in self.object_ids:return None
        try:node=self.resolve(candidate,'driver',old)
        except ConversionError:return None
        if node.split('/')[3]!='R':return None
        suffix=node.split('/')[1]+node.split('/')[-1]
        if ref[5:]!=suffix:return None
        graph=self.graphs[old]
        output_labels=[l for l in self.labels if l.get('column')==242 and l.get('text')==suffix
                       and type(l.get('row')) is int and 0<=l['row']<93 and (241,l['row']) in graph]
        if len(output_labels)!=1:return None
        row=output_labels[0]['row']
        if sum((241,row) in g for g in self.graphs.values())!=1:return None
        names=[l for l in self.labels if l.get('row')==row and l.get('column')==211 and l.get('text','').strip()]
        if len(names)!=1:return None
        destinations=[l for l in self.labels if l.get('text')==ref[:5] and l.get('row') in (row,row+1)
                      and l.get('column') in (205,215,224,234)]
        if len(destinations)!=1:return None
        dest=destinations[0];x=dest['column'];y=dest['row']
        if self.rows[y][x:x+5]!=ref[:5] or (204,y) not in graph:return None
        # The claimed local pin and the output's incoming wire must already
        # belong to one recorded component; never add edges to make this true.
        anchors=self.recorded_route_anchors(node).intersection(graph)
        if not anchors or (204,row) not in graph:return None
        todo=[(204,row)];visited=set()
        while todo:
            point=todo.pop()
            if point in visited:continue
            visited.add(point);todo.extend(graph[point]-visited)
        if not anchors.intersection(visited) or (204,y) not in visited:return None
        return {'reference':ref,'local driver':candidate,'terminal':node,
                'output row':row,'destination at':[x,y]}

    def memberships(self):
        # Validate exact neutral membership before choosing any origin or naming anchor.
        seen=set()
        for old,record in self.nets.items():
            literal=record['source_literals']
            fields={'driver','drivers','targets','passive_terminals'}|{c.get('relationship') for c in record.get('endpoint_claims',[])}
            for field in fields:
                value=literal.get(field);values=value if isinstance(value,list) else [value]
                for ref in values:
                    if not isinstance(ref,str):continue
                    for node in self.aliases.get(ref,[]):
                        if node not in self.auxiliary:continue
                        require(field=='passive_terminals' and isinstance(value,list),
                                'auxiliary_membership','Auxiliary attachment must be neutral passive_terminals membership, never an active endpoint',net=old,reference=ref,field=field)
                        seen.add(node)
                        self.auxiliary_history.append({'kind':'auxiliary attachment source observation','source net ID':old,
                            'reference':ref,'source field':field,'terminal':copy.deepcopy(self.terminals[node]),
                            'interpretation':'Nondirectional auxiliary membership only; retained reference syntax is not a signal-input or net-driver claim.'})
        require(seen==self.auxiliary,'auxiliary_membership','Auxiliary attachment has no explicit neutral membership',terminals=sorted(self.auxiliary-seen))
        offsets=set();ordinary_offsets=set();extras=[]
        # Endpoint claim categories let the adapter preserve aliases such as
        # additional_driver_outputs without assuming that every metadata list
        # declares electrical membership.
        for old,record in self.nets.items():
            literal=record['source_literals'];driver=literal.get('driver')
            destination=self.output_destination_driver(old,literal)
            if destination is not None:
                driver=destination['local driver']
                self.issue('nets/'+old+'/source','conflicting',destination['reference'],
                    'The recorded external driver is printed as an output destination; the existing uniquely routed local driver is used for conversion. The original source claim is retained for review.',
                    **{'original net ID':old,'destination interpretation':destination})
            words=(str(literal.get('id',''))+' '+str(driver)).upper()
            kind=None
            if old=='SPARE' and len(self.spare_bindings)==1:kind='spare'
            elif re.search(r'(?:^|[^A-Z])UNUSED(?:$|[^A-Z])',words):kind='unused'
            elif re.search(r'(?:^|[^A-Z])(?:GND|GROUND)(?:$|[^A-Z])',words):kind='gnd'
            elif re.search(r'\+3V(?:$|[^A-Z0-9])',words):kind='+3v'
            explicit_strap=record.get('extensions',{}).get('documented_local_jumper') or record.get('extensions',{}).get('documented_unused_local_jumper')
            strap=explicit_strap or (isinstance(driver,str) and any(word in driver.lower() for word in ('strap','tie','local.')))
            require(driver is None or isinstance(driver,str),'net_driver','Primary driver is not a string or null',net=old)
            local=isinstance(driver,str) and driver.split('.',1)[0] in self.object_ids
            if local:
                node=self.resolve(driver,'driver',old);self.names[old]=self.pid+node.split('/')[1]+node.split('/')[-1]
            elif kind:
                targets=literal.get('targets',[])
                if kind=='spare':
                    require(isinstance(targets,list) and bool(targets) and all(isinstance(r,str) and r.split('.',1)[0] in self.object_ids for r in targets),
                            'spare_target','SPARE targets require uniquely recorded local terminal evidence',net=old)
                nodes=[self.resolve(r,'target',old) for r in targets if isinstance(r,str) and r.split('.',1)[0] in self.object_ids]
                if kind=='spare':
                    graph=self.graphs[old]
                    label=self.spare_bindings[0]['number label']
                    start=(label['column'],label['row'])
                    reachable=set();pending=[start]
                    while pending:
                        point=pending.pop()
                        if point in reachable:continue
                        reachable.add(point);pending.extend(graph.get(point,set())-reachable)
                    require(start in graph and all(self.recorded_route_anchors(node).intersection(reachable) for node in nodes),
                            'spare_target','SPARE targets must meet the numbered source route component',net=old)
                self.names[old]=local_net_id(self.pid,nodes,kind)
                if kind=='spare':
                    self.issue('nets/'+self.names[old]+'/source','conflicting',driver,
                        'Human identifies SPARE as connected like UNUSED; the uniquely bound source label and numbered route remain separate polylines. Original driver, targets and label observations are retained; no physical edge across the printed gap is inferred.',
                        **{'original net ID':old,'source binding':copy.deepcopy(self.spare_bindings[0])})
            elif strap:
                targets=literal.get('targets',[])
                require(len(targets)>=2,'strap_scope','Undriven strap must have at least two explicit attached inputs',net=old)
                nodes=[self.resolve(r,'target',old) for r in targets]
                require(all(n.split('/')[3]=='L' for n in nodes) and len({n.split('/')[1] for n in nodes})==1,
                        'strap_scope','Approved strap naming applies to input-to-input straps on one block',net=old)
                self.names[old]=local_net_id(self.pid,nodes,'strap')
            else:
                try:entry,actual,offset=self.external_input(old,literal)
                except ConversionError as exc:
                    if exc.finding['code']!='external_origin':raise
                    attached=[self.resolve(r,'target',old) for r in literal.get('targets',[]) if isinstance(r,str) and r.split('.',1)[0] in self.object_ids]
                    number=local_net_id(self.pid,attached,'no-source');self.names[old]=number;self.no_source.add(old)
                    self.issue('nets/'+number+'/source','missing' if not driver else 'conflicting',driver,
                        'Source is not established. Human-authorized no-source ID anchors this net to its first known driven input. Original driver claim is retained for resolution.',
                        **{'original net ID':old,'source finding':exc.finding})
                else:
                    offsets.add(offset)
                    if entry['net number'] not in self.diagnostic_inputs:ordinary_offsets.add(offset)
                    self.inputs.append(entry);self.names[old]=actual;self.input_nodes[old]='inputs/'+entry['net number']
            claims=[]
            if local:claims.append(('driver',driver))
            claims.extend(('target',v) for v in literal.get('targets',[]))
            if 'drivers' in literal:
                require(isinstance(literal['drivers'],list),'driver_collection','drivers must be an array',net=old)
                claims.extend(('driver',v) for v in literal['drivers'])
            for claim in record.get('endpoint_claims',[]):
                field=claim.get('relationship');category=claim.get('role_category','')
                if field in ('driver','drivers','targets','semantic_driver'):continue
                value=literal.get(field)
                values=value if isinstance(value,list) else [value]
                for v in values:
                    if isinstance(v,str) and v.split('.',1)[0] in self.object_ids:
                        require(any(word in category for word in ('driver','target','port','passive')) or category=='declared-membership-or-reference',
                                'endpoint_role','Additional endpoint has no retained role',net=old,field=field)
                        claims.append(('driver' if 'driver' in category else 'target',v))
            if not record.get('endpoint_claims'):
                unexpected=set(literal)-{'id','driver','drivers','targets','semantic_driver','external','external_references'}
                require(not unexpected,'legacy_net_fields','Legacy net has unsupported relationship fields',net=old,fields=sorted(unexpected))
            if old in self.input_nodes:self.nodes[old].append(self.input_nodes[old])
            for role,ref in claims:
                if not isinstance(ref,str) or ref.split('.',1)[0] not in self.object_ids:
                    if role=='target':extras.append({'net':old,'reference':ref})
                    continue
                node=self.resolve(ref,role,old)
                require(node not in self.membership or self.membership[node]==old,'multiple_net_owners','One terminal belongs to distinct nets',node=node)
                self.membership[node]=old
                if node not in self.nodes[old]:self.nodes[old].append(node)
        require(len(set(self.names.values()))==len(self.names),'net_id_collision','Origin-based net IDs collide; source decision required')
        if len(offsets)>1 and self.allow_partial and self.diagnostic_inputs and len(ordinary_offsets)==1:
            supported=next(iter(ordinary_offsets))
            for identity,observation in self.diagnostic_inputs.items():
                if observation['column']!=32+supported:
                    self.gaps.append({'code':'unrepresented_input_reference_placement','reference':identity,
                        'source column':observation['column'],'source row':observation['row'],
                        'supported diagnostic display column':32+supported,'literal':observation['literal'],
                        'status':'unresolved','detail':'Diagnostic draft does not represent this conflicting placement. Source coordinates are unchanged; no source correction, normalization or new per-input layout field is inferred.'})
            offsets={supported}
        require(len(offsets)<=1,'input_layout','Input references have inconsistent column offsets',offsets=sorted(offsets))
        require(set(self.membership)==set(self.terminals),'unowned_terminals','Terminals without a declared net cannot be silently discarded',terminals=sorted(set(self.terminals)-set(self.membership)))
        return next(iter(offsets),0),extras

    def location(self,block,value):
        if not value:return ''
        if re.match(r'^\d{2}[A-Z]-',value):return value
        def evidence_records(owner):
            entries=owner.get('current_extensions',{}).get('socket_listing_evidence',{})
            if isinstance(entries,dict):return [entries]
            return [entry for entry in entries if isinstance(entry,dict)] if isinstance(entries,list) else []
        frames={entry.get('board','')[:2] for entry in evidence_records(block)
                if re.match(r'^\d{2}[A-Z]-',entry.get('board','')) and value.startswith(entry['board'][2:])}
        if len(frames)==1:return next(iter(frames))+value
        frames={entry.get('board','')[:2] for other in self.owners.values() for entry in evidence_records(other)
                if entry.get('board','')[2:]==value[:4]}
        frames={f for f in frames if re.fullmatch(r'\d{2}',f)}
        if len(frames)==1:return next(iter(frames))+value
        frame=self.page.get('frame')
        if isinstance(frame,str) and re.fullmatch(r'\d{2}',frame):return frame+value
        node='blocks/'+self.object_ids[block['identifiers']['id']]+'/socket'
        self.issue(node,'missing',value,'Socket frame is not established by the printed page or explicit socket evidence.')
        return None

    def blocks(self):
        result=[];deviations={};self.covered=set();self.deferred=[]
        function_rows=None
        for serial,block in self.owners.items():
            g=block['geometry'];grid=block['identifiers'].get('grid')
            require(isinstance(grid,str) and re.fullmatch(r'[1-9][A-HJ-N]',grid),'block_grid','Block grid is outside the approved template',block=serial,grid=grid)
            column=int(grid[:-1]);top=2+7*LETTERS.index(grid[-1]);x=g.get('column');y=g.get('row')
            require(type(x)is int and y==top,'block_grid','Explicit block geometry disagrees with its grid row',block=serial,row=y,expected=top)
            deviation=x-(27+23*column)
            require(column not in deviations or deviations[column]==deviation,'block_column','Blocks in one column have incompatible offsets',block=serial)
            deviations[column]=deviation
            height=g.get('height')
            if height is None:height=6
            require(type(height)is int and height>=6,'block_height','Unsupported block height',block=serial,height=height)
            r={'serial':serial,'grid position':grid,'function':block['function'].get('label',''),'circuit':block['circuit'].get('identifier','')}
            ordinal=block['source_form']['ordinal'];placement=self.bindings.get(f'/nodes/{ordinal}/function')
            if placement is None and 'function_column_offset' in g and function_rows is None:
                function_rows=self.restore_text_rows()
            offset=source_function_offset(block,placement,self.rows,function_rows or [],self.text_binding)
            require(type(offset)is int,'function_offset','Function offset is not an integer',block=serial)
            if offset:r['function offset']=offset
            if height!=6:r['height']=height
            for old,new in (('card_type','card'),('portion','portion')):
                value=block['card_identity'].get(old)
                if value:r[new]=value
            site=block['site'].get('label')
            if site:r['socket']=self.location(block,site)
            else:
                boards=[v for row,v in block['source_literals'].get('body_fields',[]) if isinstance(v,str) and re.fullmatch(r'[A-Z]-[A-Z]\d',v)]
                if len(set(boards))==1:
                    location=self.location(block,boards[0]);r['board']=location
            pins=[]
            for node,pin in self.terminals.items():
                if node.split('/')[1]!=serial:continue
                lit=pin['source_literals'];side=node.split('/')[3];line=int(node.split('/')[-1]);q={'side':side,'line':line}
                number=pin.get('pin_number');printed=lit.get('printed_label') or ''
                original_printed=printed
                marker=lit.get('border_marker');border=x if side=='L' else x+7
                controls=[v['value'] for v in lit.get('source_observations',[]) if v.get('field')=='border_control' and v.get('value') in ('K','E','X')]
                if not marker and len(set(controls))==1:marker=controls[0]
                observed={l['text'] for l in self.labels if l.get('column')==border and l.get('row')==pin['geometry']['row'] and l.get('text') in ('K','E','X')}
                require(len(observed)<=1,'pin_edge','Conflicting border marks',node=node)
                marker=typed_border_qualifier(pin,node,marker,observed)
                if node in self.auxiliary:marker=neutral_k_observation_marker(pin,node,marker,observed)
                if observed:marker=next(iter(observed))
                if ordinary_vertical_select_line(pin,side,marker):marker=None
                # The user identifies an exact leading K on an otherwise normal
                # right-side pin as the auxiliary edge mark, not pin text.
                # Keep existing source role and net claims for review: a legacy
                # output/driver claim does not become neutral merely by parsing K.
                prefix_aux=(side=='R' and isinstance(number,str)
                            and re.fullmatch(r'[A-Z]\d{2}',number) is not None
                            and printed.startswith('K'+number)
                            and printed.count(number)==1)
                if prefix_aux:
                    require(marker in (None,'K') and not lit.get('triangle'),
                            'pin_edge','K prefix conflicts with an existing edge mark',node=node)
                    marker='K'
                    if node not in self.auxiliary:
                        self.issue(node+'/edge','conflicting',original_printed,
                            'K is an auxiliary edge mark, but the source retains an ordinary output role or driver claim. Preserve the source net claims and review the role; no neutral membership or driver change is inferred.')
                if marker:
                    require(marker in ('K','E','X','◺'),'pin_edge','Unapproved border-mark notation',node=node,marker=marker)
                    q['edge']={'K':'aux','E':'extension','X':'non-logic','◺':'negative'}[marker]
                    if marker in ('K','E','X','◺') and printed.startswith(marker):printed=printed[len(marker):]
                elif lit.get('triangle'):q['edge']='negative'
                # Exact standalone control labels are net annotations, not
                # physical pin identities. Membership has already been checked;
                # never choose a net or infer a contact from the label itself.
                standalone_annotation=(printed in ('2','3','8','L') and number in (None,printed))
                if standalone_annotation:
                    mark=printed
                elif number is not None:
                    require(isinstance(number,str) and printed.count(number)==1,'pin_presentation','Printed terminal does not uniquely contain its established pin',node=node,pin=number,printed=printed)
                    q['pin']=number;before,after=printed.split(number);mark=before+after
                    require(not(before and after),'pin_annotation','Annotations occur on both sides of a pin; source placement needs review',node=node)
                    require(not mark or (side=='L' and before) or (side=='R' and after),
                            'pin_annotation','Annotation on the nondefault side needs bend-relative placement',node=node)
                elif node in self.auxiliary:
                    if printed=='':
                        require(not any(o.get('field')=='printed_pin' and o.get('value')!=''
                                        for o in lit.get('source_observations',[])),
                                'auxiliary_printed_pin','Blank auxiliary span conflicts with a printed-pin observation',node=node)
                    if explicitly_unprinted_terminal(pin):mark=''
                    else:
                        q['pin']=None;mark='';self.issue(node+'/pin','illegible',printed,'Printed auxiliary contact remains unresolved in the selected source; no contact is inferred from K.')
                elif pin.get('pin_number_status') in ('unlabeled','explicit-none') or explicitly_unprinted_terminal(pin):
                    mark=printed
                else:
                    q['pin']=None;mark='';self.issue(node+'/pin','illegible',printed,'Printed pin identity remains unresolved; no physical identity is inferred.')
                expected=x-len(printed) if side=='L' else x+8
                presentation=[l for l in self.labels if l.get('row')==pin['geometry']['row'] and l.get('text')==printed]
                if not standalone_annotation and number is None and mark and len(presentation)==1 and presentation[0]['column']!=expected:
                    self.deferred.append(presentation[0]);mark=''
                if mark:self.annotations[self.membership[node]].append({'at':node,'text':mark})
                pins.append(q)
                # Source terminal-label fields sometimes include the border wedge.
                for label in self.labels:
                    if label.get('row')==pin['geometry']['row'] and x-8<=label.get('column',-999)<=x+15:
                        if label not in self.deferred and (label.get('text','').replace('◺','') in (printed,original_printed) or label.get('text') in ('K','E','X','◺') or (number is not None and terminal_span_label(label, original_printed, side, border, pin['geometry']['row'])) or (side=='L' and q.get('edge')=='non-logic' and covers_exact_pin_x_suffix(label,pin))):
                            self.covered.add((label['column'],label['row'],label['text']))
            r['pins']=pins;result.append(r)
        return sorted(result,key=lambda r:r['serial']),[{'type':'block','num':n,'deviation':v} for n,v in sorted(deviations.items()) if v]

    def outputs(self):
        result=[];printed_to_old={};fanouts=defaultdict(list)
        self.assumed_singleton_hangers={}
        # Only the two explicitly supported output-reference columns are
        # recognized; never silently discard a nearby unsupported heading.
        headings=[l for l in self.labels if l.get('column') in (240,241,242,243)
                  and type(l.get('row')) is int and 0<=l['row']<93
                  and isinstance(l.get('text'),str)
                  and (PRINTED_NET.fullmatch(l['text']) or
                       (re.fullmatch(r'[A-Z?\ufffd]{2}\d+',l['text']) and
                        any(c in l['text'] for c in ('?', '\ufffd')) and
                        sum((242,l['row']) in g or (241,l['row']) in g
                            for g in self.graphs.values())==1))]
        for label in headings:
            y=label['row'];column=label['column'];printed=label['text']
            require(column in (241,242),'output_reference_offset',
                    'Output reference uses an unsupported source column',row=y,column=column,reference=printed)
            require(sum(l['row']==y for l in headings)==1,'output_reference_ambiguity',
                    'Multiple output-reference headings share a source row',row=y)
            if column==241:
                require(self.rows[y][column:column+len(printed)]==printed,
                        'output_reference_span','Recorded output reference conflicts with the source text span',row=y,column=column,reference=printed)
                names=[l for l in self.labels if l.get('row')==y and l.get('column')==211 and isinstance(l.get('text'),str) and l['text'].strip()]
                require(len(names)==1 and self.rows[y][211:211+len(names[0]['text'])]==names[0]['text'] and 211+len(names[0]['text'])<=column,
                        'output_caption_span','Output caption lacks one exact recorded source span',row=y,column=column)
        refs=sorted(headings,key=lambda l:l['row'])
        for i,label in enumerate(refs):
            y=label['row'];printed=label['text']
            candidates=[old for old,g in self.graphs.items() if (242,y) in g or (241,y) in g]
            if not candidates and label['column']==242:candidates=[old for old,g in self.graphs.items() if self.names[old]==self.pid+printed and any(yy==y and xx>=200 for xx,yy in g)]
            require(len(candidates)==1,'output_owner','Printed output has no unique declared routed owner',reference=printed,row=y,candidates=candidates)
            old=candidates[0];number=self.names[old]
            require(number.startswith(self.pid),'output_origin','Nonlocal output identity needs an approved display rule',net=number)
            require(not any(r['net number']==number for r in result),'duplicate_output','Several output appearances need a source/format decision',net=number)
            end=refs[i+1]['row'] if i+1<len(refs) else 93;sinks=[]
            for yy in range(y,end):
                for xx in (205,215,224,234):
                    token=self.rows[yy][xx:xx+5]
                    if PAGE_ID.fullmatch(token):
                        if yy==y and output_name_covers_token(self.labels,self.rows,y,xx,token):continue
                        sinks.append((xx,yy,token))
            r={'net number':number,'name':self.rows[y][211:label['column']].rstrip('─ ').rstrip(),'line':y,'sinks':[s[2] for s in sinks]}
            if label['column']==241:
                self.issue('outputs/'+number+'/net number','conflicting',printed,
                    'Output reference is recorded at column 241; the V4 renderer uses column 242. Check the source position against the scan.',
                    **{'source position':[241,y],'render position':[242,y]})
            if printed!=number[len(self.pid):]:self.issue('outputs/'+number+'/net number','conflicting',printed,'Printed output ID disagrees with its explicitly routed source. Conversion preserves that discrepancy for scan review.',**{'possible readings':[printed,number[len(self.pid):]],'at':[label['column'],y]})
            layout_sinks=sinks
            # Some V3 pages put the first destination inline and the rest in
            # the ordinary hanging positions. V4 uses one hanging list. Keep
            # the observed names and order and disclose each moved position.
            if (len(sinks)>1 and sinks[0][:2]==(205,y) and
                all((xx,yy)==((205,215,224,234)[(k-1)%4],y+1+(k-1)//4)
                    for k,(xx,yy,_) in enumerate(sinks[1:],1)) and
                all(sum(l.get('column')==xx and l.get('row')==yy and l.get('text')==text
                        for l in self.labels)==1 for xx,yy,text in sinks)):
                projected=[((205,215,224,234)[k%4],y+1+k//4,text) for k,(_,_,text) in enumerate(sinks)]
                if all(yy<end for _,yy,_ in projected):
                    layout_sinks=projected
                    self.issue('outputs/'+number+'/sinks','conflicting','',
                        'Mixed inline and hanging destination positions were projected to a V4 hanging list. Check the original positions against the scan.',
                        **{'source positions':[{'page':text,'at':[xx,yy]} for xx,yy,text in sinks],
                           'projected positions':[{'page':text,'at':[xx,yy]} for xx,yy,text in projected]})
            assumed_hanger=False
            if len(sinks)>1 or (len(sinks)==1 and sinks[0][1]==y+1):
                require(all((xx,yy)==((205,215,224,234)[k%4],y+1+k//4) for k,(xx,yy,t) in enumerate(layout_sinks)),
                        'output_fanout_layout','Destination list does not use the approved ordinary hanging layout',net=number)
                lengths=set()
                for x in range(195,205):
                    if (x,y+1) in self.graphs[old].get((x,y),set()) and (x==204 or (x+1,y+1) in self.graphs[old].get((x,y+1),set())):
                        lengths.add(204-x)
                for points in self.paths[old]:
                    if len(points)>1 and points[-1] in ([204,y+1],[205,y+1]) and points[-2][1]==y+1 and points[-2][0]<=204 and (points[-2][0],y+1) in self.graphs[old].get((points[-2][0],y),set()):
                        lengths.add(205-points[-2][0]-1)
                    if len(points)>1 and points[0] in ([204,y+1],[205,y+1]) and points[1][1]==y+1 and points[1][0]<=204 and (points[1][0],y+1) in self.graphs[old].get((points[1][0],y),set()):
                        lengths.add(205-points[1][0]-1)
                if not lengths and not any((x,y+1) in self.graphs[old] for x in range(195,206)):
                    length=1
                    assumed_hanger=True
                    self.issue('outputs/'+number+'/hanging wire length','missing','',
                        'The first destination branch is not recorded; assumed one wire character excluding the corner. Check its length against the scan.',
                        **{'assumed length':1,'output row':y})
                else:
                    require(len(lengths)==1,'hanging_wire_length','Cannot establish one first-column hanging-wire length',net=number,lengths=sorted(lengths))
                    length=lengths.pop()
                require(length>=0,'hanging_wire_length','Hanging wire has invalid length',net=number)
                if length!=1:r['hanging wire length']=length
                for k,(xx,yy,t) in enumerate(layout_sinks):
                    if k%4==0:fanouts[old].append([[205-length-1,y],[205-length-1,yy],[205,yy]])
            elif sinks:require(sinks[0][1]==y,'singleton_output_layout','A single sink is not inline',net=number)
            if len(sinks)==1:
                graph=self.graphs[old]
                if assumed_hanger:
                    # The renderer derives singleton sink placement from the
                    # route itself. Explicitly carry the assumed branch and
                    # the ordinary output continuation across its caption.
                    generated=fanouts[old]+[[[204,y],[241,y]]]
                    graph=wire_graph(self.paths[old]+generated)
                    self.assumed_singleton_hangers[old]=generated
                try:
                    inferred_row=singleton_output_hanging_row(r,graph)
                except ValueError as error:
                    raise ConversionError('singleton_output_render_contract',str(error),net=number)
                display_row=y if inferred_row is None else inferred_row
                require(display_row==sinks[0][1],'singleton_output_render_contract',
                        'Recorded source sink placement disagrees with route-inferred display; source and routing remain unchanged',
                        net=number,source_row=sinks[0][1],inferred_row=display_row)
            # These sinks already passed the explicit ordinary output layout checks.
            for xx, yy, sink in sinks:
                for source_label in self.labels:
                    if sink_prefix_label(source_label, sink, xx, yy, self.graphs[old]):
                        self.covered.add((source_label['column'], source_label['row'], source_label['text']))
            result.append(r);self.nodes[old].append('outputs/'+number);printed_to_old[printed]=old
        return result,printed_to_old,fanouts

    def connectors(self,printed_to_old):
        connectors=defaultdict(list);active=None;positions=[]
        # Parse field content; use columns only for table reading order, never
        # infer physical pin identities or electrical net joins from coordinates.
        candidates=[]
        for column in range(35,162,14):
            for row in range(93,103):
                text=self.rows[row][column:column+14].strip()
                parsed = bool(re.fullmatch(r'(?:[A-Z]{2}\d+\s+)?(?:\d{2})?[A-Z]-[A-Z]\d[A-Z]\d.{3}',text))
                heading = re.match(r'([A-Z]{2}\d+)(?:\s|$)',text)
                require(heading is None or parsed, 'unsupported_connector_heading',
                        'Connector heading has unsupported location text; ownership cannot carry over',
                        text=text, at=[column,row], reference=heading.group(1) if heading else None)
                if parsed:
                    candidates.append({'column':column,'row':row,'text':text})
        for l in candidates:
            text=l['text'].strip();m=re.fullmatch(r'([A-Z]{2}\d+)\s+(.+)',text)
            if m:
                code,text=m.groups()
                same=[old for old,num in self.names.items() if num==self.pid+code]
                active=printed_to_old.get(code) or (same[0] if len(same)==1 else None)
                require(active is not None,'connector_net','Connector table reference has no unique net',reference=code)
            require(active is not None,'connector_table','Connector continuation precedes a net heading',text=text)
            frame=self.page.get('frame')
            if re.match(r'^\d{2}[A-Z]-',text):full=text
            else:
                entries=[b.get('current_extensions',{}).get('socket_listing_evidence',{}) for b in self.owners.values()]
                entries=[entry for value in entries for entry in (value if isinstance(value,list) else [value]) if isinstance(entry,dict)]
                frames={entry.get('board','')[:2] for entry in entries}
                frames={f for f in frames if re.fullmatch(r'\d{2}',f)}
                if not(isinstance(frame,str) and re.fullmatch(r'\d{2}',frame)):
                    require(len(frames)==1,'connector_frame','Abbreviated connector frame is unresolved',text=text)
                    frame=next(iter(frames))
                full=frame+text
            connectors[active].append(full);positions.append([l['column'],l['row']])
            if '\ufffd' in full:self.issue('nets/'+self.names[active]+'/connectors','illegible',full,'Connector contains unresolved source text; no contact identity is guessed.')
        return connectors,positions

    def external_reference_observations(self,outputs):
        """Carry source observational claims outside compact functional data.

        No reference suffix is promoted to a directed remote terminal. Preserve
        missing, explicit null and ordered lists as distinct source states.
        """
        by_number={row['net number']:row for row in outputs}
        records=[]
        for old,record in self.nets.items():
            literal=record['source_literals']
            observation={'kind':'source external reference observation',
                'source net ID':old,'new net number':self.names[old],
                'field':'external_references','present':'external_references' in literal,
                'source endpoint claims':copy.deepcopy([claim for claim in record.get('endpoint_claims',[])
                    if claim.get('relationship')=='external_references']),
                'printed sink pages':copy.deepcopy(by_number.get(self.names[old],{}).get('sinks',[])),
                'directed terminal inference':False}
            if observation['present']:
                observation['value']=copy.deepcopy(literal['external_references'])
            records.append(observation)
        return records

    def annotate(self,blocks,newnets):
        byserial={b['serial']:b for b in blocks};graphs={n['net number']:wire_graph(n['routing']) for n in newnets}
        for label in self.labels:
            suffix=hanging_origin_suffix_annotation(label,self.rows,self.labels,self.inputs,newnets)
            if suffix is not None:
                net,annotation=suffix
                net.setdefault('annotations',[]).append(annotation)
                continue
            x,y,text=label.get('column'),label.get('row'),label.get('text','')
            rail_label=bool(re.fullmatch(r'(?:UNUSED|GND|GROUND|\+3V)[─ ]*',text,re.I)) or any(x==v['label'].get('column') and y==v['label'].get('row') and text==v['label'].get('text') for v in getattr(self,'spare_bindings',[]))
            spare_number=any(x==v['number label'].get('column') and y==v['number label'].get('row') and text==v['number label'].get('text') for v in getattr(self,'spare_bindings',[]))
            unresolved_entry=type(x)is int and 0<=x<=40 and any(any((xx,y) in self.graphs[old] for xx in range(x,x+len(text))) for old in self.no_source)
            if not(type(x)is int and type(y)is int and text.strip() and (40<x<205 or ((rail_label or spare_number or unresolved_entry) and 0<=x<=40)) and y<93):continue
            if rail_label:text=text.rstrip('─ ')
            if (x,y,text) in self.covered or set(text)<=WIRE|set('◺'):continue
            observed=text.replace('◺','')
            if re.fullmatch(r'[0-9]*[A-Z][0-9A-Z\ufffd?]{2}[✲]*',observed):
                candidates=[]
                for node,pin in self.terminals.items():
                    point=pin['geometry'].get('point')
                    printed=pin['source_literals'].get('printed_label','')
                    start=(point[0]+1 if pin['side']=='input' else point[0]-len(printed)) if point else None
                    actual_start=x+int(text.startswith('◺'))
                    exact_label = start==actual_start and len(printed)==len(observed)
                    # A bare observation of an established physical pin may
                    # omit only its separately printed star annotation. This
                    # does not resolve an unknown pin or accept another pin.
                    bare_star_contact = (bool(point) and pin.get('pin_number')==observed
                        and printed.startswith(observed) and bool(printed[len(observed):])
                        and set(printed[len(observed):])=={'✲'}
                        and actual_start==(point[0]+1 if pin['side']=='input' else point[0]-len(observed)))
                    if point and point[1]==y and (exact_label or bare_star_contact) and pin.get('pin_number'):
                        candidates.append(node)
                if len(candidates)==1:
                    node=candidates[0]
                    selected_printed=self.terminals[node]['source_literals'].get('printed_label','')
                    known_star_omission=(observed==self.terminals[node].get('pin_number')
                        and selected_printed.startswith(observed) and bool(selected_printed[len(observed):])
                        and set(selected_printed[len(observed):])=={'✲'})
                    if observed!=selected_printed and not known_star_omission:
                        self.issue(node+'/pin','conflicting',text,'Printed-label observation conflicts with the retained normalized terminal identity. Both original claims are preserved; no physical pin is guessed.',**{'possible readings':[text,self.terminals[node]['pin_number']]})
                    continue
            inside=False
            for b in self.owners.values():
                g=b['geometry'];h=g.get('height') or 6
                if g['column']<=x<=g['column']+7 and g['row']<=y<=g['row']+h:inside=True;break
            if inside:continue
            candidates=[b for b in self.owners.values() if 1<=b['geometry']['row']-y<=2 and -7<=x-b['geometry']['column']<=8]
            # A printed pin label that begins outside the border is not a new
            # free annotation if it reaches an established terminal on that row.
            if candidates:
                b=min(candidates,key=lambda b:(b['geometry']['row']-y,abs(x-b['geometry']['column'])))
                record=byserial[self.object_ids[b['identifiers']['id']]]
                if 'annotation' not in record:
                    record['annotation']=text;offset=[x-b['geometry']['column'],y-b['geometry']['row']]
                    if offset!=[0,-1]:record['annotation offset']=offset
                    continue
            containing=[n for n in newnets if (x,y) in graphs[n['net number']] or (unresolved_entry and any((xx,y) in graphs[n['net number']] for xx in range(x,x+len(text))))]
            if len(containing)==1:
                n=containing[0];anchors=[];bends=[]
                for i,points in enumerate(n['routing']):
                    for j,(px,py) in enumerate(points):
                        a=(abs(x-px)+abs(y-py),i,j,px,py);anchors.append(a)
                        if 0<j<len(points)-1:bends.append(a)
                require(bool(anchors),'net_annotation','No route anchor for printed net annotation',text=text)
                _,i,j,px,py=min(bends or anchors)
                n.setdefault('annotations',[]).append({'at':{'polyline':i,'point':j},'offset':[x-px,y-py],'text':text})
            else:self.gaps.append({'code':'unplaced_annotation','text':text,'at':[x,y],'candidate nets':[n['net number'] for n in containing]})

    def convert(self):
        reference_offset,extra_endpoints=self.memberships();blocks,deviations=self.blocks()
        if reference_offset:deviations.append({'type':'entry-reference','deviation':reference_offset})
        outputs,printed_to_old,fanouts=self.outputs();connectors,footer_positions=self.connectors(printed_to_old)
        # A singleton hanger is drawn from its own recorded route, rather
        # than regenerated as a multi-sink list. Retain those source edges.
        singleton_hanger_nets={item['net number'] for item in outputs
            if len(item.get('sinks',[]))==1 and any(
                self.rows[item['line']+1][xx:xx+5]==item['sinks'][0]
                for xx in (205,215,224,234))}
        newnets=[]
        for old in self.nets:
            route=[]
            preserve_singleton_hanger=self.names[old] in singleton_hanger_nets
            for points in self.paths[old]:
                # Remove only paths whose complete edges are supplied by the
                # approved hanging-list rule; never discard arbitrary right-side wires.
                graph=wire_graph([points]);derived=wire_graph(fanouts[old])
                if not preserve_singleton_hanger and graph and all(p in derived and v<=derived[p] for p,v in graph.items()):continue
                route.append(points)
            if wire_graph(route+fanouts[old])!=self.graphs[old]:
                # Some sources end the lead immediately before the sink text,
                # others underneath its first cell. Keep every original edge
                # when the implicit list rule cannot replace it exactly.
                route=copy.deepcopy(self.paths[old])
                self.warnings.append({'code':'explicit_fanout_retained','net':self.names[old],
                    'message':'Original routes retained; generated hanging-list lead also reaches its covered first text cell.'})
            if old in self.assumed_singleton_hangers:
                route.extend(copy.deepcopy(self.assumed_singleton_hangers[old]))
            record={'net number':self.names[old],'nodes':self.nodes[old],'routing':route}
            if self.annotations[old]:record['annotations']=self.annotations[old]
            if connectors[old]:record['connectors']=connectors[old]
            newnets.append(record)
        self.annotate(blocks,newnets)
        located_outputs, located_source_ids = located_external_output_rows(
            self.nets, self.rows, self.names, outputs)
        outputs.extend(located_outputs)
        for output, source_id in zip(located_outputs, located_source_ids):
            node = 'outputs/' + output['net number']
            if node not in self.nodes[source_id]:
                self.nodes[source_id].append(node)
        outputs.sort(key=lambda item: (item['line'], item['net number']))
        grouped_output_hold = grouped_output_projection_issue(self.e.get('printed_labels', []))
        if grouped_output_hold is not None:
            self.issues.append(grouped_output_hold)
        external_output_hold = unlocated_external_output_projection_issue(self.nets, outputs, self.names, self.rows)
        if external_output_hold is not None and external_output_hold not in self.issues:
            self.issues.append(external_output_hold)
        data={'$schema':SCHEMA,'page':self.page,'review':{'status':'partial','approved':False,'unresolved discrepancies':bool(self.issues or self.gaps),'details':f'review/{self.pid[:2]}/{self.pid}.json'},
              'blocks':blocks,'inputs':sorted(self.inputs,key=lambda v:v['line']),'outputs':outputs,'nets':newnets}
        if deviations:data['column deviations']=deviations
        lead_changes, lead_holds = normalize_annotation_leads(data, {'uncertainties':self.issues})
        if lead_changes:
            self.warnings.append({'code':'standalone_annotation_lead_normalized',
                'message':'Terminal routes use the cell outside a fixed three-character pin slot; existing net ownership is unchanged.',
                'changes':lead_changes})
        self.gaps.extend({'code':'annotation_terminal_lead', **hold} for hold in lead_holds)
        if lead_holds:data['review']['unresolved discrepancies']=True
        notes=source_note_labels(self.labels,self.pid)
        if notes:
            note_origin=min(4,min(l['column'] for l in notes))
            byrow=defaultdict(list)
            for l in notes:byrow[l['row']].append(l)
            lines=[]
            for y in range(93,max(byrow)+1):
                chars=[]
                for l in sorted(byrow[y],key=lambda l:l['column']):
                    start=l['column']-note_origin
                    if len(chars)<start:chars.extend(' '*(start-len(chars)))
                    chars[start:start+len(l['text'])]=l['text']
                lines.append(''.join(chars))
            data['note']=lines
            if note_origin==2:
                self.issue('note','ambiguous',' | '.join(lines),'Column-two note grouping and normalization require source review; separate page identifier is retained.')
                data['review']['unresolved discrepancies']=True
        review={'page':self.pid,'review date':dt.date.today().isoformat(),'reviewer':'Functional ALD format converter',
            'content sha256':content_digest(data),'sources':[{'path':str(self.path.resolve()),'sha256':self.source_hash}],
            'inherited review':self.source.get('review',{}),'original scan':self.e.get('source'),
            'uncertainties':self.issues,'format questions':self.gaps,'warnings':self.warnings,
            'conversion evidence':{'old to new net IDs':self.names,'all terminal references retained':True,
                'original per-net route graphs retained':not bool(self.logical_output_partitions or self.spare_bindings),
                'original route graph unions retained':True,'logical output partitions':self.logical_output_partitions,
                'blocks':len(blocks),'terminals':len(self.terminals),'nets':len(newnets),'terminal coordinate views':self.coordinate_views,'external endpoint observations':extra_endpoints+self.external_reference_observations(outputs)+self.auxiliary_history+self.semantic_input_resolutions},
            'writer options':{'line ending':'CRLF' if self.newline=='\r\n' else 'LF','trim trailing spaces':self.trim},
            'scope':'Data conversion only. No original-pixel reading, source correction, approval or publication is inferred.'}
        if self.spare_bindings:
            review['conversion evidence']['spare label source bindings']=copy.deepcopy(self.spare_bindings)
        attach_grouped_label_evidence(review,self.e.get('printed_labels',[]))
        if self.text_binding:review['sources'].append(self.text_binding)
        if footer_positions and min(y for x,y in footer_positions)==93:
            review['approved normalization']='Connector table begins on standard row94, per direct human format decision.'
            self.normalize_footer=all(y<=101 for x,y in footer_positions)
        return data,review


def apply_corrections(data,review,manifest,source_hash):
    if not manifest:return
    pages=manifest.get('pages',{})
    row=pages.get(data['page']['page'])
    if row is None:return
    require(row.get('source sha256')==source_hash,'correction_source','Correction manifest source hash mismatch')
    for change in row.get('replacements',[]):
        require(isinstance(change.get('authority'),str) and bool(change['authority'].strip()),'correction_authority','Every correction needs an evidence/authority description')
        replace_pointer(data,change['pointer'],change['before'],change['after'])
    for resolution in row.get('resolutions',[]):
        require(isinstance(resolution.get('authority'),str) and bool(resolution['authority'].strip()),'correction_authority','Every resolution needs an evidence/authority description')
        matches=[u for u in review['uncertainties'] if u['field']==resolution['field']]
        require(bool(matches),'correction_resolution','Resolved field was not an emitted uncertainty',field=resolution['field'])
        for u in matches:u.update(status='resolved',resolution=resolution['value'],authority=resolution['authority'])
    review['explicit source corrections']=copy.deepcopy(row)
    review['conversion evidence']['original per-net route graphs retained']=(review['conversion evidence']['original per-net route graphs retained'] and not any('/routing' in v['pointer'] for v in row.get('replacements',[])))
    review['content sha256']=content_digest(data)


def validate_new(data):
    require(set(data)<= {'$schema','page','review','blocks','inputs','outputs','nets','note','column deviations'},'new_fields','Unapproved root field')
    require(data['$schema']==SCHEMA,'new_schema','Unexpected schema identifier')
    require(set(data['page'])<={'page','version','subpage','page-type','origin','title','date','machine','log','frame','p/n','ibm division','next block','revisions'},'new_fields','Unapproved page field')
    require(set(data['review'])=={'status','approved','unresolved discrepancies','details'},'review_fields','Review record must stay compact')
    require(type(data['review']['unresolved discrepancies'])is bool,'review_fields','Discrepancy flag must be boolean')
    require(data['review']['approved'] is False,'approval_transfer','Conversion cannot transfer approval')
    require([b['serial'] for b in data['blocks']]==sorted(b['serial'] for b in data['blocks']),'block_order','Blocks are not in serial order')
    nodes=set()
    for b in data['blocks']:
        require(set(b)<= {'serial','grid position','function','function offset','circuit','card','portion','socket','board','pins','height','annotation','annotation offset'},'new_fields','Unapproved block field',block=b['serial'])
        if 'annotation offset' in b:require(len(b['annotation offset'])==2 and all(type(v)is int for v in b['annotation offset']),'annotation_offset','Annotation offset must be an integer pair')
        for p in b['pins']:
            require(set(p)<= {'side','line','pin','edge'} and type(p['line'])is int,'new_pin_fields','Invalid pin record')
            require(p['side'] in ('L','R') and p['line']>=1,'new_pin_fields','Invalid pin side or line')
            require('edge' not in p or p['edge'] in ('negative','aux','extension','non-logic'),'new_pin_fields','Invalid pin edge')
            node=f"blocks/{b['serial']}/pins/{p['side']}/{p['line']}"
            require(node not in nodes,'duplicate_terminal','Duplicate functional terminal',node=node);nodes.add(node)
    nodes.update('inputs/'+p['net number'] for p in data['inputs'])
    nodes.update('outputs/'+p['net number'] for p in data['outputs'])
    for p in data['inputs']:
        require(set(p)<={'net number','name','line','reference style','real net number'},'new_fields','Unapproved input field')
        require(type(p['line'])is int and 0<=p['line']<93,'port_line','Invalid input line')
        require(p.get('reference style','inline')in ('inline','hanging'),'input_style','Invalid reference style')
    for p in data['outputs']:
        require(set(p)<={'net number','name','line','sinks','hanging wire length'},'new_fields','Unapproved output field')
        require(type(p['line'])is int and 0<=p['line']<93,'port_line','Invalid output line')
        require(type(p.get('hanging wire length',1))is int and p.get('hanging wire length',1)>=0,'hanging_wire_length','Invalid hanging wire length')
    used=[];numbers=[]
    for n in data['nets']:
        require(set(n)<= {'net number','nodes','routing','annotations','connectors'},'new_fields','Unapproved net field')
        numbers.append(n['net number']);used.extend(n['nodes'])
        for points in n['routing']:simplify(points)
        wire_graph(n['routing'])
        for a in n.get('annotations',[]):
            require(set(a)<={'at','offset','text'} and isinstance(a.get('text'),str),'new_fields','Invalid annotation record')
            at=a['at']
            if isinstance(at,str):require(at in n['nodes'],'annotation_reference','Annotation terminal is not on its net',reference=at)
            else:
                require(set(at)=={'polyline','point'} and all(type(v)is int and v>=0 for v in at.values()),'annotation_reference','Invalid route-point indices')
                try:n['routing'][at['polyline']][at['point']]
                except (KeyError,IndexError,TypeError):raise ConversionError('annotation_reference','Invalid route-point annotation reference')
    require(len(numbers)==len(set(numbers)),'net_id_collision','Duplicate new-format net ID')
    require(set(used)==nodes and len(used)==len(nodes),'terminal_membership','Every port/terminal must occur exactly once')


def source_note_labels(labels,pid):
    """Select standard notes, plus a uniquely anchored column-two NOTE group."""
    standard=[l for l in labels if l.get('row',-1)>=93 and 3<=l.get('column',-1)<30 and l.get('text','').strip()]
    headings=[l for l in labels if l.get('row')==93 and l.get('column')==2 and isinstance(l.get('text'),str) and re.match(r'NOTE\b',l['text'],re.I)]
    if not headings:
        return standard
    require(len(headings)==1,'note_group','Ambiguous column-two note heading')
    singles=[l for l in labels if l.get('column')==2 and l.get('row',-1)>=93 and isinstance(l.get('text'),str) and len(l['text'].strip())==1]
    require(all(95<=l['row']<100 and isinstance(pid,str) and len(pid)==5 and l['text']==pid[l['row']-95] for l in singles),
            'note_group','Column-two singleton is not the observed vertical page identifier')
    extra=[l for l in labels if l.get('column')==2 and l.get('row',-1)>=93 and isinstance(l.get('text'),str) and len(l['text'].strip())>1]
    end=max([93]+[l['row'] for l in standard+extra])
    for y in range(93,end+1):
        at=[l for l in standard+extra if l['row']==y]
        require(len(at)==1,'note_group','Column-two note group must have one unique label per row',row=y)
    return standard+extra


def compare_render(data,review,converter):
    expected=converter.rows[:];findings=[];wiring=[];count=0;wire_count=0;unresolved_count=0
    resolved=[u for u in review['uncertainties'] if u.get('status')=='resolved' and 'at'in u]
    normalizations=[]
    if getattr(converter,'normalize_footer',False):
        table=[r.ljust(245)[35:175] for r in expected[93:102]]
        expected=[r.ljust(245) for r in expected]
        for y in range(93,103):expected[y]=expected[y][:35]+' '*140+expected[y][175:]
        for i,text in enumerate(table):expected[94+i]=expected[94+i][:35]+text+expected[94+i][175:]
        if converter.trim:expected=[r.rstrip() for r in expected]
        normalizations.append('Connector table row93 to default row94')
    note_labels=source_note_labels(converter.labels,converter.pid)
    note_origin=min([4]+[l['column'] for l in note_labels])
    if note_origin<4 and data.get('note'):
        expected=[list(row) for row in expected]
        for label in note_labels:
            y=label['row'];x=label['column'];text=label['text']
            require(y<len(expected) and ''.join(expected[y][x:x+len(text)])==text,'note_source_span','Original note label does not match exact source text')
            expected[y][x:x+len(text)]=' '*len(text)
        for i,text in enumerate(data['note']):
            y=93+i
            while len(expected)<=y:expected.append([])
            if len(expected[y])<4+len(text):expected[y].extend(' '*(4+len(text)-len(expected[y])))
            require(all(c==' ' for c in expected[y][4:4+len(text)]),'note_overlap','Normalized note would overwrite non-note source content')
            expected[y][4:4+len(text)]=text
        expected=[''.join(row) for row in expected]
        normalizations.append('Human-approved note group origin to column4, exact content and relative indentation retained; original absolute coordinate not certified')
    try:rendered=render_page(data,review,converter.trim,converter.newline)
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        return None,{'rendered':False,'error':str(exc),'code':'render_unsupported'}
    actual=rendered.decode('utf-8').splitlines()
    # Preserve the complete raw comparison before any approved layout normalization.
    raw_differences=[]
    for y in range(max(len(actual),len(converter.rows))):
        a=actual[y] if y<len(actual) else '';b=converter.rows[y] if y<len(converter.rows) else ''
        for x in range(max(len(a),len(b))):
            av=a[x] if x<len(a) else None;bv=b[x] if x<len(b) else None
            if av!=bv:raw_differences.append({'at':[x,y],'source':bv,'inferred':av,'source present':x<len(b),'render present':x<len(a)})
    for y in range(max(len(actual),len(expected))):
        a=actual[y] if y<len(actual) else '';b=expected[y] if y<len(expected) else ''
        for x in range(max(len(a),len(b))):
            av=a[x] if x<len(a) else ' ';bv=b[x] if x<len(b) else ' '
            if av==bv:continue
            count+=1
            explained=any(y==u['at'][1] and u['at'][0]<=x<u['at'][0]+len(u.get('visible text')or '') for u in resolved)
            if not explained:unresolved_count+=1
            wire=(av in WIRE-{' '} or bv in WIRE-{' '}) and x<205 and y<93
            finding={'at':[x,y],'source':bv,'inferred':av,'kind':'wiring glyph discrepancy' if wire else 'text or placement discrepancy','status':'resolved' if explained else 'unresolved'}
            if wire:wire_count+=1;wiring.append(finding)
            if len(findings)<120:findings.append(finding)
    return rendered,{'rendered':True,'different cells':count,'wire glyph differences':wire_count,
        'unresolved different cells':unresolved_count,
        'byte identical':rendered==((converter.newline.join(converter.rows)+converter.newline).encode('utf-8')),
        'wiring findings':wiring,
        'raw source render differences':raw_differences,'all raw differences included':True,
        'approved normalizations':normalizations,
        'first differences':findings,'all differences included':count<=len(findings),
        'interpretation':'Differences trigger source review. Never modify routes or add glyph overrides merely to match old text.',
        'rendered sha256':digest(rendered),'source text used by renderer':False}


def finalize_review(data,review,comparison):
    review['render comparison']=comparison
    data['review']['unresolved discrepancies']=bool(
        any(u.get('status')=='unresolved' for u in review['uncertainties'])
        or review['format questions'] or not comparison.get('rendered')
        or comparison.get('unresolved different cells',comparison.get('different cells',0)))
    review['content sha256']=content_digest(data)


def atomic_write(path,raw,overwrite):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():require(overwrite,'output_exists','Output already exists; explicit --overwrite is required',path=str(path))
    handle,temp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(handle,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        if overwrite:os.replace(temp,path)
        else:
            # Exclusive target creation prevents a concurrent output overwrite.
            with path.open('xb') as f:f.write(Path(temp).read_bytes())
    finally:
        if Path(temp).exists():Path(temp).unlink()


def run(args):
    files=[]
    for spec in args.inputs:
        p=Path(spec).resolve()
        if p.is_dir():files.extend(sorted(p.rglob('*.json') if args.recursive else p.glob('*.json')))
        elif p.is_file():files.append(p)
        else:raise ConversionError('input_path','Input does not exist',path=str(p))
    files=list(dict.fromkeys(p.resolve() for p in files))
    require(bool(files),'input_empty','No JSON files selected')
    require(not args.text or len(files)==1,'text_scope','--text applies to a single input')
    output=Path(args.output).resolve() if args.output else None
    require(output is not None or args.dry_run,'output_required','Supply --output or --dry-run')
    destination=Path(args.report).resolve() if args.report else (output/'conversion-report.json' if output and not args.dry_run else None)
    protected=set(files)
    if args.corrections:protected.add(Path(args.corrections).resolve())
    for path in files:
        try:text=choose_text(path,args.text,args.text_root)
        except ConversionError:continue  # Per-file lookup failure is reported below.
        if text:protected.add(text.resolve())
    require(destination not in protected,'report_source','Report cannot overwrite an input, projection or correction manifest')
    source_roots={parent.parent for p in files for parent in p.parents if parent.name=='json'}
    for target in (output,destination):
        if target:require(all(not target.is_relative_to(root) for root in source_roots),'output_source','Use destinations outside the source repository',path=str(target))
    if destination:require(not destination.exists() or args.overwrite,'output_exists','Report already exists; use a fresh destination or explicit --overwrite',path=str(destination))
    if output:
        require(all(not p.is_relative_to(output) for p in files),'output_source','Output cannot contain source inputs')
        # Source repository's JSON and ALD trees are never valid destinations.
        for p in files:
            for parent in p.parents:
                if parent.name=='json':
                    require(not output.is_relative_to(parent.parent),'output_source','Use an output directory outside the source repository',output=str(output));break
    manifest=strict_json(Path(args.corrections).read_bytes()) if args.corrections else None
    if manifest:require(manifest.get('schema')=='ald-functional-conversion-corrections-v1','correction_schema','Unknown correction manifest schema')
    report={'tool':'convert_ald_json','date':dt.datetime.now(dt.timezone.utc).isoformat(),'dry run':args.dry_run,
        'source writes':0,'pages':[],'scope':'Canonical v3 and explicit legacy ALD diagrams; other document kinds are reported unsupported.'}
    reserved=set()
    for path in files:
        item={'source':str(path)}
        try:
            raw=path.read_bytes();source_hash=digest(raw);original=strict_json(raw)
            text=choose_text(path,args.text,args.text_root)
            converter=Converter(original,path,source_hash,text,allow_partial=args.allow_partial);data,review=converter.convert()
            apply_corrections(data,review,manifest,source_hash);validate_new(data)
            rendered,comparison=compare_render(data,review,converter)
            finalize_review(data,review,comparison)
            require(not review['format questions'] or args.allow_partial,'notation_gaps','Source annotations require an explicit format/source decision',questions=review['format questions'])
            name=data['page']['page']
            if 'version' in data['page']:name+='-v'+data['page']['version']
            require(name not in reserved,'output_collision','Several inputs produce the same output name',name=name)
            reserved.add(name)
            if name!=data['page']['page']:data['review']['details']=f'review/{name[:2]}/{name}.json'
            review['content sha256']=content_digest(data)
            item.update(page=data['page']['page'],status='converted with findings' if comparison.get('different cells') or any(u.get('status') != 'resolved' for u in review['uncertainties']) or review['format questions'] or rendered is None else 'converted',
                blocks=len(data['blocks']),terminals=len(converter.terminals),nets=len(data['nets']),
                uncertainties=len(review['uncertainties']),**{'format questions':review['format questions'],'render comparison':comparison})
            if not args.dry_run:
                targets=[(output/(name+'.json'),json_bytes(data)),(output/data['review']['details'],json_bytes(review))]
                if args.render and rendered is not None:targets.append((output/(name+'.txt'),rendered))
                for target,content in targets:require(target.resolve() not in protected and target.resolve()!=destination,'output_source','Output collides with an input or report',path=str(target))
                for target,content in targets:require(not target.exists() or args.overwrite,'output_exists','Output already exists',path=str(target))
                require(path.read_bytes()==raw,'source_changed','Source changed during conversion; nothing was written',path=str(path))
                for target,content in targets:atomic_write(target,content,args.overwrite)
                item['output']=str(output/(name+'.json'))
            require(path.read_bytes()==raw,'source_changed','Source changed during conversion; output requires revalidation',path=str(path))
        except ConversionError as exc:item.update(status='blocked',finding=exc.finding)
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:item.update(status='blocked',finding={'code':'input_io','message':str(exc)})
        except (KeyError,TypeError,IndexError,StopIteration,ValueError,AttributeError) as exc:
            item.update(status='blocked',finding={'code':'source_shape','message':f'{type(exc).__name__}: {exc}'})
        report['pages'].append(item)
        if not args.quiet:print(f"{item.get('page',path.name)}: {item['status']}"+((' — '+item['finding']['code']) if 'finding'in item else ''),file=sys.stderr)
    report['counts']={k:sum(p['status']==k for p in report['pages']) for k in ('converted','converted with findings','blocked')}
    if destination:
        require(destination not in files,'report_source','Report cannot overwrite an input')
        atomic_write(destination,json_bytes(report),args.overwrite)
    print(json.dumps({'counts':report['counts'],'report':str(destination) if destination else None},ensure_ascii=False))
    return 2 if report['counts']['blocked'] else 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',nargs='+',help='JSON file(s) or directory/directories')
    parser.add_argument('-o','--output',help='Separate destination directory; sources are never overwritten')
    parser.add_argument('-r','--recursive',action='store_true',help='Search input directories recursively')
    parser.add_argument('--text',help='Existing UTF-8 projection for a single input')
    parser.add_argument('--text-root',help='Directory tree containing corresponding UTF-8 files')
    parser.add_argument('--render',action='store_true',help='Also write independently rendered UTF-8 output')
    parser.add_argument('--dry-run',action='store_true',help='Convert and inspect without writing page artifacts')
    parser.add_argument('--report',help='Write machine-readable batch report, including dry runs')
    parser.add_argument('--corrections',help='Explicit source-hash/preimage-bound correction manifest')
    parser.add_argument('--allow-partial',action='store_true',help='Emit marked drafts with external notation questions; default blocks them')
    parser.add_argument('--overwrite',action='store_true',help='Explicitly replace existing destination artifacts only')
    parser.add_argument('--quiet',action='store_true',help='Suppress per-file progress on stderr')
    args=parser.parse_args(argv)
    try:return run(args)
    except (ConversionError,OSError,json.JSONDecodeError) as exc:
        print(json.dumps({'error':exc.finding if isinstance(exc,ConversionError) else str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())



