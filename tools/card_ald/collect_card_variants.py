"""Collect witnessed card notation patterns without changing circuits or sources.

python tools/card_ald/collect_card_variants.py 3308 --definition PRIVATE.json

Each pattern comes from one physical card when all overlapping observations
agree. Conflicting card observations remain separate page/socket contexts.
Missing portions and unmapped fields retain canonical symbols explicitly.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import card_source as page_reader
from card_source import (accepted_page_context,identity_document,selected_source_nodes,source_identity_issues,catalogue_source_coverage,recheck_identity_context)

ROOT=Path(__file__).resolve().parents[2]
CONTACT=re.compile(r'\d*([BDGJ](?:0[2-9]|1[0-3]))(?:[✲*]?T?|[✲*])\Z')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def binding(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
physical_readings=page_reader.physical_readings
physical=page_reader.terminal_contact
wedge=page_reader.wedge


def primary(function):
    words=str(function).strip().lstrip('✲*').split()
    return words[0] if words else ''
def location_key(literal,node_id):
    match=re.fullmatch(r'(?:02)?([ABCEKL])-([A-Z]\d)([A-Z]\d)(?:[BT])?',str(literal))
    return ('02'+match[1]+'-'+match[2]+match[3],True) if match else (str(literal)+'|NODE:'+node_id,False)
def key(overrides):return json.dumps(overrides,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def observed_form(node,box,power):
    """Map only readable source fields onto stable common semantic port IDs."""
    function=str(node.get('function','')).strip()
    form={'function':box['function'],'port_triangles':{p['id']:p['triangle'] for p in box['ports']}}
    observed={};unmapped=[];ignored=[]
    if node.get('unit',node.get('circuit_identifier'))!=box['circuit_identifier']:
        return form,observed,[{'field':'circuit_identifier','literal':node.get('unit',node.get('circuit_identifier')),
                              'reason':'Circuit identity differs from the common portion; no notation substitutions inferred.'}],ignored
    if function and '�' not in function and len(function)<=6:
        form['function']=function;observed['function']=function
    else:unmapped.append({'field':'function','literal':function,'reason':'Missing, unreadable or wider than six cells.'})
    source_by_side=defaultdict(list)
    for index,port in enumerate(node.get('pins',[])):
        readings=physical_readings(port)
        if len(set(readings.values()))>1:
            unmapped.append({'field':str(port.get('side'))+'_decoration','source_pin_index':index,
                             'physical_contact_readings':readings,
                             'reason':'Contradictory physical/printed pin mirrors; no contact or decoration selected.'})
            continue
        pin=physical(port)
        if pin in power:
            ignored.append({'source_pin_index':index,'physical_pin':pin,'reason':'Supply tie is not an extra card signal input.'});continue
        source_by_side[port.get('side')].append((index,port,pin))
    mapped=set();ambiguous=set()
    for side in ('input','output'):
        targets=[p for p in box['ports'] if p['side']==side]
        source=source_by_side[side]
        for index,port,pin in source:
            if pin is None:continue
            choices=[p for p in targets if p.get('pin')==pin]
            if len(choices)!=1:
                unmapped.append({'field':side+'_decoration','source_pin_index':index,'literal':port.get('pin'),
                                 'reason':'No unique common physical contact on this side.'});continue
            target=choices[0]
            if target['id'] in ambiguous:continue
            mark=wedge(port)
            if mark is None:
                unmapped.append({'field':side+'_decoration','source_pin_index':index,'reason':'Decoration is absent from both supported source schemas.'});continue
            if target['id'] in mapped and form['port_triangles'][target['id']]!=mark:
                unmapped.append({'field':side+'_decoration','source_pin_index':index,'port_id':target['id'],
                                 'reason':'Conflicting source uses of one physical contact; canonical decoration retained.'})
                ambiguous.add(target['id']);mapped.discard(target['id']);observed.pop(target['id'],None)
                form['port_triangles'][target['id']]=target['triangle']
                continue
            form['port_triangles'][target['id']]=mark;mapped.add(target['id'])
            observed[target['id']]={'triangle':mark,'physical_pin':pin,'source_pin_index':index,'mapping':'physical_contact'}
        pinless=[(i,p) for i,p,pin in source if pin is None and p.get('pin') in (None,'','IN','OUT')]
        common_pinless=[p for p in targets if p.get('pin') is None]
        if pinless and len(pinless)==len(common_pinless) and (len(pinless)==1 or (side=='input' and primary(function) in ('A','OR'))):
            ordered=zip(sorted(pinless,key=lambda pair:pair[1].get('row',0)),sorted(common_pinless,key=lambda p:p['row']))
            for (index,port),target in ordered:
                mark=wedge(port)
                if mark is not None:
                    form['port_triangles'][target['id']]=mark;mapped.add(target['id'])
                    observed[target['id']]={'triangle':mark,'source_pin_index':index,
                        'mapping':'unique_pinless_port' if len(pinless)==1 else 'visual_order_of_equivalent_pinless_inputs'}
        for target in targets:
            if target['id'] not in mapped:
                unmapped.append({'field':side+'_decoration','port_id':target['id'],
                                 'reason':'Source omission or ambiguous mapping; canonical decoration retained.'})
    return form,observed,unmapped,ignored


def collect(card,definition,root=ROOT,grouping="physical-card",publication_policy="all-observed"):
    root=Path(root).resolve();definition=Path(definition).resolve();spec=read(definition)
    assert spec['card_type']==card
    boxes={b['portion']:b for b in spec['boxes']};groups=defaultdict(list);model_bindings=[];occurrences=0
    source_bindings={};pages=set();unmatched=[];documents={};source_context=accepted_page_context(root);coverage_issues=[]
    # Only page models have nodes; generated card catalogs and archived note
    # snapshots are outside this tree or excluded explicitly.
    for path,entry in page_reader.iter_documents(root,card):
        original=entry['document'];doc=identity_document(root,path,original,source_context)
        nodes=selected_source_nodes(doc,card)
        issues=source_identity_issues(doc,card)
        if not nodes and not issues:continue
        documents[path.resolve()]={'document':doc,'sha256':binding(path)['sha256'],'original':original}
        coverage_issues.extend(issues)
        model_binding=binding(path);model_bindings.append(model_binding)
        source=doc.get('source');source=source.get('source') if isinstance(source,dict) else source
        source_binding=None
        if source and Path(source).is_file():
            if source not in source_bindings:source_bindings[source]=page_reader.source_binding(source)
            source_binding=source_bindings[source]
            expected=doc.get('source_sha256')
            if expected:assert source_binding['sha256']==expected,('Stale source binding',path)
        page=doc.get('page',doc.get('ALD_page',path.stem.split()[0]));pages.add(page)
        for node in nodes:
            occurrences+=1
            fallback=str(node.get('id'))if node.get('id')not in(None,'')else str(path.resolve())+'|'+node['_source_pointer']
            location,known=location_key(node.get('location'),fallback)
            group_key=(page,location,str(path))
            groups[group_key].append({'node':node,'model':model_binding,'source':source_binding,
                                      'location_verified_format':known,'literal_location':node.get('location')})
    catalog_path=root/'json/Card types current'/f'{card}.json'
    identity_coverage={'catalogue_present':catalog_path.is_file(),'source_observations':occurrences}
    if catalog_path.is_file():
        extra,identity_coverage=catalogue_source_coverage(root,read(catalog_path),documents);coverage_issues.extend(extra)
    # Compare only fields actually observed: omitted ports must not falsely
    # contradict an explicit mark from another page of the same physical card.
    def observed_signature(items):
        fields={};conflicts=[]
        for item in items:
            node=item['node'];portion=node.get('portion')
            if portion not in boxes:continue
            form,observed,missing,ignored=observed_form(node,boxes[portion],spec['power_contacts'])
            for field,value in observed.items():
                value=value if field=='function' else value['triangle']
                slot=(portion,field)
                if slot in fields and fields[slot]!=value:conflicts.append({'portion':portion,'field':field,'values':[fields[slot],value]})
                fields[slot]=value
        return fields,conflicts
    physical_groups=defaultdict(list)
    for context,items in groups.items():physical_groups[context[1]].append((context,items))
    selected=[];conflict_sites=[]
    for location,contexts in sorted(physical_groups.items()):
        all_items=[item for context,items in contexts for item in items]
        fields,conflicts=observed_signature(all_items)
        if grouping=='physical-card' and not conflicts and all(i['location_verified_format'] for i in all_items):
            selected.append((location,contexts,all_items))
        else:
            if conflicts:conflict_sites.append({'location':location,'conflicts':conflicts,'pages':sorted({c[0] for c,i in contexts}),
                                               'policy':'Preserve separate page/socket contexts; no majority selection.'})
            selected.extend((location,[(context,items)],items) for context,items in contexts)
    profiles={};canonical=[];uncertain=[];complete_count=0
    for location,contexts,items in selected:
        context_pages=sorted({context[0] for context,unused in contexts})
        observed_portions=sorted({i['node'].get('portion') for i in items},key=str)
        witness={'page':context_pages[0] if len(context_pages)==1 else None,'source_pages':context_pages,
                 'location':location,'source_locations':[location],
                 'literal_locations':sorted({str(i['literal_location']) for i in items}),
                 'models':list({i['model']['path']:i['model'] for i in items}.values()),
                 'sources':list({i['source']['path']:i['source'] for i in items if i['source']}.values()),
                 'nodes':[{'page':context[0],'node':item['node'].get('id'),'node_pointer':item['node']['_source_pointer'],'model':item['model'],'source_reviewed':item['node'].get('source_reviewed'),'identity_adaptation':item['node'].get('_identity_adaptation')} for context,context_items in contexts for item in context_items],
                 'page_socket_contexts':len(contexts),'observed_portions':observed_portions,
                 'unobserved_portions_kept_canonical':sorted(set(boxes)-set(observed_portions)),
                 'fields_not_inferred':[],'ignored_supply_ties':[], 'observed_fields':{}}
        if coverage_issues:witness['fields_not_inferred'].append({'field':'source_catalogue_coverage','reason':'Source identity/catalogue coverage is incomplete; a full publication witness is not certified.','issues':len(coverage_issues)})
        for item in items:
            if item['node'].get('source_reviewed')is not True:witness['fields_not_inferred'].append({'field':'source_review_acceptance','node':item['node'].get('id'),'node_pointer':item['node']['_source_pointer'],'literal':item['node'].get('source_reviewed'),'reason':'Explicit false/unknown review retained; not a complete reviewed field witness.'})
        changes={};merged,conflicts=observed_signature(items)
        if conflicts:
            witness['fields_not_inferred'].extend({'reason':'Conflicting observed fields within page/socket context.',**c} for c in conflicts)
            uncertain.append(witness);continue
        for item in items:
            node=item['node'];portion=node.get('portion')
            if portion not in boxes:
                witness['fields_not_inferred'].append({'portion':portion,'node':node.get('id'),'reason':'Portion absent from common definition.'});continue
            form,observed,missing,ignored=observed_form(node,boxes[portion],spec['power_contacts'])
            witness['ignored_supply_ties'].extend({'portion':portion,'node':node.get('id'),**m} for m in ignored)
            # A readable observation elsewhere can complete an omitted field;
            # identity mismatches remain explicit, never hidden by aggregation.
            witness['fields_not_inferred'].extend({'portion':portion,'node':node.get('id'),**m} for m in missing
                if m.get('field')=='circuit_identifier' or 'physical_contact_readings' in m or m.get('reason','').startswith('Conflicting source uses') or (portion,m.get('port_id',m.get('field'))) not in merged)
        for portion in sorted(set(observed_portions)&set(boxes)):
            box=boxes[portion];override={};known={field:value for (p,field),value in merged.items() if p==portion}
            witness['observed_fields'][portion]=known
            if 'function' in known and known['function']!=box['function']:override['function']=known['function']
            triangles={p['id']:known[p['id']] for p in box['ports'] if p['id'] in known and known[p['id']]!=p['triangle']}
            if triangles:override['port_triangles']=triangles
            if override:changes[portion]=override
        # Deduplicate repeated missing-field records from cross-page witnesses.
        witness['fields_not_inferred']=list({key(m):m for m in witness['fields_not_inferred']}.values())
        witness['complete_portion_observation']=not witness['unobserved_portions_kept_canonical']
        witness['complete_field_observation']=witness['complete_portion_observation'] and not witness['fields_not_inferred']
        complete_count+=witness['complete_field_observation']
        if witness['fields_not_inferred']:uncertain.append(witness)
        if not changes:canonical.append(witness);continue
        profile=profiles.setdefault(key(changes),{'box_overrides':changes,'witnesses':[]})
        profile['witnesses'].append(witness)
    # Preserve an existing witnessed numbering where its override pattern is
    # identical; assign all newly found patterns deterministic unused numbers.
    prior={key(v['box_overrides']):v['number'] for v in spec.get('variants',[])}
    used={number for signature,number in prior.items() if signature in profiles}
    next_number=1;variants=[]
    for signature,profile in sorted(profiles.items()):
        number=prior.get(signature)
        if number is None:
            while next_number in used:next_number+=1
            number=next_number;used.add(number)
        witnesses=profile['witnesses']
        variants.append({'number':number,'variant_definition':{'number':number,
            'box_overrides':profile['box_overrides'],'annotation_overrides':[],'line_ending':spec.get('canonical_line_ending','LF')},
            'witnesses':witnesses,'source_pages':sorted({p for w in witnesses for p in w['source_pages']}),
            'source_locations':sorted({w['location'] for w in witnesses}),'complete_witnesses':sum(w['complete_field_observation'] for w in witnesses),
            'partial_witnesses':sum(not w['complete_field_observation'] for w in witnesses)})
    variants.sort(key=lambda v:v['number'])
    counts={'occurrences':occurrences,'pages':len(pages),'page_socket_observations':len(groups),'physical_card_sites':len(physical_groups),
            'conflicting_physical_card_sites':len(conflict_sites),'installation_witnesses':len(selected),
            'complete_field_observation_witnesses':complete_count,'partial_observation_witnesses':len(selected)-complete_count,
            'distinct_observed_variants':len(variants),'variants_with_complete_witness':sum(v['complete_witnesses']>0 for v in variants),
            'variants_witnessed_only_partially':sum(v['complete_witnesses']==0 for v in variants),
            'canonical_pattern_witnesses':len(canonical),'witnesses_with_unmapped_or_omitted_fields':len(uncertain)}
    report = {'schema':'card-ald-observed-variant-candidates-v1','card_type':card,
            'definition':binding(definition),'collector':binding(Path(__file__)),'page_reader_tools':[binding(p) for p in page_reader.runtime_paths(root)],
            'grouping':grouping,'conflicting_physical_card_sites':conflict_sites,
            'rules':['Combine only compatible observations at the same normalized physical card identity; conflicting sites retain separate page contexts.',
                     'Unobserved portions and unmapped fields retain canonical symbols and are identified in each witness.',
                     'Only function text and mapped port triangles may change; all pins, circuits, geometry and nets remain canonical.',
                     'Preserve complete readable secondary function labels; supply ties are excluded from card signal ports.',
                     'Distinguish completely witnessed full-card profiles from partial observations with canonical fill.'],
            'identity_coverage':identity_coverage,'coverage_issues':coverage_issues,'source_review_bindings':source_context['bindings'],
            'counts':counts,'model_bindings':model_bindings,'source_bindings':list(source_bindings.values()),
            'canonical_pattern_witnesses':canonical,'profiles_left_uncertain':uncertain,
            'variants':variants,'source_or_repository_data_changes_applied':False}
    recheck_identity_context(source_context,documents)
    return apply_publication_policy(report, publication_policy)



def apply_publication_policy(report, policy="all-observed"):
    """Select complete witnessed profiles without renumbering or losing evidence."""
    assert policy in ("all-observed", "complete-witnesses"), "Unknown publication policy"
    result=deepcopy(report)
    profiles=sorted(result.get('variants', [])+result.get('excluded_partial_profiles', []),key=lambda v:v['number'])
    assert len({v['number'] for v in profiles})==len(profiles), "Duplicate observed profile number"
    selected=[v for v in profiles if policy=='all-observed' or v.get('complete_witnesses',0)>0]
    selected_numbers={v['number'] for v in selected}
    excluded=[v for v in profiles if v['number'] not in selected_numbers]
    result['publication_policy']=policy
    result['variants']=selected
    result['excluded_partial_profiles']=excluded
    result['counts']['selected_publication_variants']=len(selected)
    result['counts']['excluded_partial_profiles']=len(excluded)
    result['publication_interpretation']=(
        'Each selected full-card profile has at least one complete physical-card field witness; partial-only profiles remain evidence and are not published.'
        if policy=='complete-witnesses' else
        'Discovery includes partial observations with explicit canonical fill; these are candidates, not proof that a completed full-card pattern was used.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_number');parser.add_argument('--definition',type=Path)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--grouping',choices=('physical-card','page-socket'),default='physical-card')
    parser.add_argument('--publication-policy',choices=('all-observed','complete-witnesses'),default='all-observed',
                        help='Discovery retains all profiles; publication selects only profiles with a complete physical-card witness.')
    args=parser.parse_args();card=args.card_number
    if not re.fullmatch(r'\d{4}',card):parser.error('Use a four-digit card number.')
    definition=args.definition or args.root/'json/Card-ALD/definitions'/(card+'.json')
    out=args.output_dir or args.root.parent/'tmp/ald-text/ald/card-variants'/card
    report=collect(card,definition,args.root,args.grouping,args.publication_policy);out.mkdir(parents=True,exist_ok=True)
    path=out/(card+' observed variant candidates.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':binding(path),'counts':report['counts']},indent=2))


if __name__=='__main__':main()

