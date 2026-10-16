"""Load all accepted socket-listing records with current source-model repairs.

The complete compiled logical table provides coverage and explicit continuation
links. Manifest-bound current models supersede repaired fields without silently
turning stale compiled uncertainty into new transcription findings.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re


def _read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def _require(ok,message):
    if not ok:raise ValueError(message)
def _hash(path):return sha256(Path(path).read_bytes()).hexdigest()
def _kind(value):return re.sub('[^a-z]','',str(value).lower())
def _card(record):return _kind(record.get('kind')) in {'single','singlecard','double','doublecard'}
def _sockets(record):
    values=record.get('occupied_sockets') or record.get('sockets') or [record.get('socket',record.get('continues_socket'))]
    return sorted({str(x) for x in values if x is not None})
def _key(board,sockets):return str(board),tuple(sockets)
def _refs(record,evidence):
    result=[]
    for ref in record.get('references',[]):
        page=ref.get('ALD_page',ref.get('ald_page',ref.get('page')))
        portions=ref.get('printed_portions',ref.get('portions',[]))
        if page is not None:result.append({'page':str(page),'portions':[str(x) for x in portions],'evidence':deepcopy(evidence)})
    return result

def _mask_matches(mask,text):
    return len(mask)==len(text) and all(a==b or a in '�?' for a,b in zip(mask,text))

def _page_name(value):
    value=str(value)
    return value if value.endswith(' SOCKET LISTING') else value+' SOCKET LISTING'


def load_listings(repo):
    repo=Path(repo).resolve();bindings={};issues=[];stale=[]
    def bind(path,expected=None):
        path=Path(path).resolve();_require(path.is_relative_to(repo),'Listing input escapes repository')
        actual=_hash(path)
        if expected is not None:_require(actual==expected,'Stale accepted listing input: '+str(path))
        item={'path':str(path),'sha256':actual};bindings[str(path)]=item;return item
    content_path=repo/'notes/Content data manifest.json';export_path=repo/'notes/Reviewed export provenance.json'
    bind(content_path);bind(export_path);content=_read(content_path);export=_read(export_path)
    _require(not export.get('conflicts') and not export.get('export_in_progress'),'Incomplete/conflicted reviewed export')
    files={item['path'].replace('\\','/'):item for item in content['files']}
    compiled_relative='json/A1 Socket Listing/Socket reference.json'
    _require(compiled_relative in files,'Complete socket reference is absent from accepted content manifest')
    compiled_path=repo/compiled_relative;compiled_binding=bind(compiled_path,files[compiled_relative]['sha256']);compiled=_read(compiled_path)
    delivered=set(compiled.get('delivered_pages',[]));accepted={};texts={}
    for entry in export['exported']:
        relative=entry['source_relative'].replace('\\','/');name=relative.rsplit('/',1)[-1].rsplit('.',1)[0]
        if name not in delivered:continue
        filename=str(entry['destination']).replace('\\','/').rsplit('/',1)[-1]
        folder=relative.rsplit('/',1)[0] if '/' in relative else ''
        path=repo/'ALD'/folder/filename
        texts[name]=bind(path,entry['text_sha256']);accepted[name]=entry
    _require(set(accepted)==delivered,'Compiled source coverage differs from accepted TXT inventory: '+str(sorted(delivered-set(accepted))))
    records=[];by_key=defaultdict(list)
    raw=compiled.get('records',[])
    for i,record in enumerate(compiled['logical_records']):
        evidence=[{'model':compiled_binding,'pointer':f'/logical_records/{i}','listing_page':record.get('source_listing')}]
        for index in record.get('source_section_indices',[]):
            _require(isinstance(index,int) and 0<=index<len(raw),'Invalid explicit continuation section index')
            section=raw[index]
            evidence.append({'model':compiled_binding,'pointer':f'/records/{index}','raw_section_index':index,'listing_page':section.get('source_listing'),
                             'source_column':section.get('source_column'),'source_row':section.get('source_row'),'source_y':section.get('source_y')})
        item={**deepcopy(record),'sockets':_sockets(record),'references':_refs(record,evidence),'evidence':evidence,'issues':[]}
        records.append(item)
        if _card(record):by_key[_key(record['board'],item['sockets'])].append(item)
    direct=defaultdict(list);fragments=[];direct_coverage=set();shared_models=0;schema_counts=defaultdict(int)
    for relative,entry in files.items():
        name=Path(relative).stem
        is_a1=relative.startswith('json/A1 Socket Listing/')
        is_ef=name.startswith('EF') and name.endswith('SOCKET LISTING')
        if not (is_a1 or is_ef) or relative==compiled_relative:continue
        if entry.get('role') not in {'Published page content model','Accepted existing A1 board model or source-column table'}:continue
        path=repo/relative;model_binding=bind(path,entry['sha256']);doc=_read(path)
        if not isinstance(doc,dict):continue
        pages={_page_name(x) for x in doc.get('pages',[])} or {name}
        direct_coverage.update(pages&delivered)
        if 'socket_records' in doc:shared_models+=1
        for container in ('sockets','sections','records','socket_records'):
            for index,record in enumerate(doc.get(container,[])):
                if not isinstance(record,dict):continue
                if not _card(record) and 'continuation' not in _kind(record.get('kind')):continue
                schema_counts[container]+=1
                evidence={'model':model_binding,'pointer':f'/{container}/{index}','listing_page':name,
                          'source_column':record.get('source_column'),'source_row':record.get('source_row'),'source_y':record.get('source_y')}
                board=record.get('board',doc.get('board'));sockets=_sockets(record)
                if not board:
                    issues.append({'kind':'current_record_board_missing','evidence':evidence});continue
                data={'record':record,'board':board,'sockets':sockets,'evidence':evidence,'references':_refs(record,[evidence])}
                if _card(record):direct[_key(board,sockets)].append(data)
                else:fragments.append(data)
    # Continuations join only a uniquely identified same-board physical card;
    # never attach a blank top fragment to its visually nearest neighbour.
    for fragment in fragments:
        candidates=[key for key in direct if key[0]==fragment['board'] and set(fragment['sockets'])<=set(key[1])]
        if len(candidates)==1:direct[candidates[0]].append(fragment)
        elif fragment['references']:
            issues.append({'kind':'ambiguous_current_continuation','evidence':fragment['evidence'],'candidate_keys':candidates})
    overlay_count=0
    for identity,observations in direct.items():
        candidates=by_key.get(identity,[])
        if len(candidates)!=1:
            issues.append({'kind':'current_card_not_uniquely_located_in_compiled_table','board':identity[0],'sockets':list(identity[1]),'matches':len(candidates),'evidence':[o['evidence'] for o in observations]})
            continue
        target=candidates[0];overlay_count+=1
        target['evidence'].extend(o['evidence'] for o in observations)
        for field in ('card_type','part_number'):
            values={str(o['record'][field]) for o in observations if o['record'].get(field) is not None}
            readable={v for v in values if '�' not in v and '?' not in v}
            if len(readable)>1:
                problem={'kind':'incompatible_current_card_identity','field':field,'values':sorted(readable),'board':identity[0],'sockets':list(identity[1])}
                target['issues'].append(problem);issues.append(problem);continue
            if len(readable)==1:
                current=next(iter(readable))
                if current!=str(target.get(field)):
                    stale.append({'kind':'stale_compiled_field','field':field,'board':identity[0],'sockets':list(identity[1]),'compiled':target.get(field),'current':current,'evidence':[o['evidence'] for o in observations]})
                    target[field]=current
        old_groups=defaultdict(set);old_evidence=defaultdict(list)
        for ref in target['references']:old_groups[ref['page']].update(ref['portions']);old_evidence[ref['page']].extend(ref['evidence'])
        current_groups=defaultdict(set);new_evidence=defaultdict(list)
        for observation in observations:
            for ref in observation['references']:current_groups[ref['page']].update(ref['portions']);new_evidence[ref['page']].extend(ref['evidence'])
        # A damaged page token can be replaced only by one exact readable mask
        # fit in the current same-card reference set.
        for page in list(old_groups):
            if '�' not in page and '?' not in page:continue
            matches=[p for p in current_groups if _mask_matches(page,p)]
            if len(matches)==1:
                fixed=matches[0];stale.append({'kind':'stale_compiled_page','board':identity[0],'sockets':list(identity[1]),'compiled':page,'current':fixed,'evidence':new_evidence[fixed]})
                old_groups[fixed].update(old_groups.pop(page));old_evidence[fixed].extend(old_evidence.pop(page))
        for page,current in current_groups.items():
            previous=old_groups.get(page,set());merged=set(previous)
            # Preserve base-only continuation portions unless a current full
            # group has enough explicit members to supersede that same group.
            if current-previous:
                malformed={p for p in previous if not re.fullmatch(r'[A-Z0-9]{2}',p)}
                if malformed:merged-=malformed
                elif len(current)>=len(previous):merged=set()
                merged.update(current)
            if merged!=previous:
                stale.append({'kind':'stale_compiled_references','board':identity[0],'sockets':list(identity[1]),'page':page,
                              'compiled':sorted(previous),'current':sorted(merged),'evidence':new_evidence[page]})
            old_groups[page]=merged;old_evidence[page].extend(new_evidence[page])
        target['references']=[{'page':p,'portions':sorted(ps),'evidence':old_evidence[p]} for p,ps in sorted(old_groups.items())]
    claims=[(r['board'],tuple(r['sockets']),r.get('card_type'),ref['page'],portion) for r in records if _card(r) for ref in r['references'] for portion in ref['portions']]
    coverage={'accepted_listing_scans':len(accepted),'A1_scans':sum(x.startswith('A1') for x in accepted),'EF_supplement_scans':sum(x.startswith('EF') for x in accepted),
              'compiled_raw_sections':len(raw),'compiled_logical_records':len(records),'explicit_continuation_links':len(compiled.get('continuation_links',[])),
              'logical_card_records':sum(_card(x) for x in records),'current_direct_covered_scans':len(direct_coverage),
              'compiled_plus_TXT_fallback_scans':sorted(delivered-direct_coverage),'current_shared_board_models':shared_models,
              'current_record_schemas':dict(schema_counts),'current_card_records_overlaid':overlay_count,
              'atomic_card_portion_references':len(claims),'unique_card_portion_references':len(set(claims)),
              'stale_compiled_differences':len(stale),'current_issues':len(issues),
              'zero_section_listing_scans':sorted(delivered-{r.get('source_listing') for r in raw})}
    return {'records':records,'coverage':coverage,'bindings':list(bindings.values()),'issues':issues,'stale_compiled_differences':stale}
