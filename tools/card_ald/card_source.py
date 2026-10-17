"""One current-page interface for card construction, variants and audits.

Current v2 identities and terminals are consumed directly. Current literal
extensions retain named pinless endpoints, K contacts and source geometry;
they are not alternate identity guesses. Legacy fixture inputs are normalized
once here, never reconstructed by each card consumer. No files are written.
"""
from collections import Counter, OrderedDict
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import sys

SCHEMA = 'ibm360-ald-page-v2'
_CACHE = OrderedDict()
_CACHE_LIMIT = 12
_CONTEXTS = {}
_NORMALIZATION = None
_EPOCHS = {}
_INDICES = {}
_SCAN_BINDINGS = {}


def configure(root):
    global _NORMALIZATION
    base = Path(root).resolve() / 'tools/normalization'
    if not base.is_dir():
        candidates=[Path(__file__).resolve().parents[1]/'normalization']
        candidates += [parent/'ibm360ald/tools/normalization' for parent in Path(__file__).resolve().parents]
        base=next((p for p in candidates if p.is_dir()),None)
        if base is None:raise ValueError('Normalization runtime is not available')
    if _NORMALIZATION is not None and _NORMALIZATION != base:
        raise ValueError('One process cannot mix normalization tool epochs')
    _NORMALIZATION = base
    if str(base) not in sys.path: sys.path.insert(0, str(base))


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_binding(path):
    """Hash a repeated immutable scan once per batch, retaining a final guard."""
    path=Path(path).resolve();stat=path.stat();stamp=(stat.st_size,stat.st_mtime_ns)
    cached=_SCAN_BINDINGS.get(path)
    if not cached or cached['stamp']!=stamp:
        cached={'stamp':stamp,'binding':{'path':str(path),'sha256':digest(path)}}
        _SCAN_BINDINGS[path]=cached
    return deepcopy(cached['binding'])


def _pairs(items):
    result = {}
    for k,v in items:
        if k in result: raise ValueError('Duplicate JSON key: '+k)
        result[k] = v
    return result


def json_read(path):
    def invalid(v): raise ValueError('Nonfinite JSON value: '+v)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=_pairs, parse_constant=invalid)


def source_epoch(root):
    """One current hash index, not another historical/raw page snapshot."""
    root=Path(root).resolve();path=root/'notes/Source status.json'
    if not path.is_file():return None
    stamp=(path.stat().st_size,path.stat().st_mtime_ns)
    if root not in _EPOCHS or _EPOCHS[root]['stamp']!=stamp:
        data=json_read(path)
        if data.get('schema')!='ald-current-source-checkpoint-v1':raise ValueError('Unknown source checkpoint')
        models={}
        for record in data['records']:
            item=record['repository'].get('json')
            if item:
                rel=Path(item['path'])
                if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe source checkpoint model path')
                target=(root/rel).resolve()
                if not target.is_relative_to(root) or target in models:raise ValueError('Invalid source model ownership')
                models[target]=item['sha256']
        _EPOCHS[root]={'stamp':stamp,'models':models,'binding':{'path':str(path),'sha256':digest(path)}}
    return _EPOCHS[root]


def _terminal(t):
    # Keep all literal/role aliases once, including explicit null/false and
    # non-contact named endpoints. Standard fields come from uniform data.
    result = deepcopy(t['source_literals'])
    if isinstance(result,str):result={'pin':result}
    if not isinstance(result,dict): return result
    result.update(deepcopy(t.get('extensions',{})))
    result.update(deepcopy(t['geometry']))
    if t.get('side') is not None: result['side'] = t['side']
    elif t.get('declared_container_role') is not None: result['side'] = t['declared_container_role']
    # Never manufacture a physical pin for a conflict or explicit-null contact.
    result['_pin_number_status'] = t['pin_number_status']
    result['_pin_number'] = t['pin_number']
    result['_terminal_id'] = t['terminal_id']
    result['_border_decorations'] = deepcopy(t['border_decorations'])
    result['_symbols'] = deepcopy(t['symbols'])
    return result


def _object(o):
    if o['source_form']['value_type'] != 'object': return deepcopy(o['current_value'])
    result = deepcopy(o['current_extensions'])
    result.update(deepcopy(o['source_literals']))
    result.update(deepcopy(o['geometry']))
    result.update(deepcopy(o['source_group_fields']))
    result.update(deepcopy(o['identifiers']))
    identity = o['card_identity']
    if identity['parse_status'] == 'resolved':
        result['card_type'],result['portion'] = identity['card_type'],identity['portion']
    elif identity['parse_status'] == 'conflict':
        result['_identity_conflict'] = deepcopy(identity)
    for key,section,field in [('function','function','label'),('unit','circuit','identifier'),('location','site','label')]:
        if field in o[section]: result[key] = deepcopy(o[section][field])
    form = o['source_form']
    result['_source_pointer'] = '/'+form['container']+'/'+str(form['ordinal'])
    if any(result.get(k) is True for k in ('symbol_only','annotation_only','annotation_block')):
        result['_annotation_excluded'] = True
    terminals = {t['terminal_id']:t for t in o['terminals']}
    for collection in form['terminal_collections']:
        members = [_terminal(terminals[m['terminal_id']]) if 'terminal_id' in m
                   else deepcopy(o['alias_relationships'][m['alias_index']]['source_literals'])
                   for m in collection['members']]
        result[collection['field']] = members if collection['representation']=='array' else members[0]
    # All semantic terminal shapes now share a pins collection. Primary input
    # multiplicity is retained; only explicitly declared aliases are excluded.
    if 'pins' not in result:
        result['pins'] = [_terminal(t) for t in o['terminals'] if t['occurrence_kind']=='primary']
    return result


def _net(n):
    if n['source_form']['value_type'] != 'object': return deepcopy(n['current_value'])
    result = deepcopy(n['extensions'])
    result.update(deepcopy(n['source_literals']))
    for section in ('routes','junctions','unresolved_current_claims'):
        for claim in n[section]: result[claim['kind']] = deepcopy(claim['value'])
    # Derived crossings are deliberately absent; routes and diamonds retained.
    return result


def view(data,root=None):
    """Detached stable card view; normalized objects remain independently owned."""
    if not isinstance(data,dict): raise ValueError('Page must be an object')
    if data.get('schema') != SCHEMA:
        if str(data.get('schema','')).startswith('ibm360-ald-page-'): raise ValueError('Unsupported page schema')
        configure(root or Path(__file__).resolve().parents[2])
        from pages import normalize_page
        data = normalize_page(data,'json/fixture.json','fixture')['data']
    result = deepcopy(data['current_extensions'])
    for k,v in data['page'].items():
        if k not in ('scan_id','kind'): result[k] = deepcopy(v)
    result['_uniform_source'] = True
    for o in data['objects']:
        form=o['source_form'];container=form['container']
        result.setdefault(container,[]).append(_object(o))
    for container in ('nets','junctions'):
        if container in data['source_containers']: result[container]=[_net(n) for n in data[container]]
    return result


def load(path,root=None,*,detached=True):
    path=Path(path).resolve();stat=path.stat();key=(stat.st_size,stat.st_mtime_ns)
    if path not in _CACHE or _CACHE[path]['stat'] != key:
        configure(root or Path(__file__).resolve().parents[2])
        raw=path.read_bytes()
        raw_sha=hashlib.sha256(raw).hexdigest()
        data=json_read(path)
        if isinstance(data,dict) and data.get('schema')==SCHEMA:
            epoch=source_epoch(root) if root else None
            if epoch:
                if epoch['models'].get(path)!=raw_sha:raise ValueError('Current normalized model differs from accepted source checkpoint: '+str(path))
            else:
                from pages import validate_current_page
                validate_current_page(data)
        if not isinstance(data,dict) or not(data.get('schema')==SCHEMA or isinstance(data.get('nodes'),list)):
            return None
        document=view(data,root)
        cards={n.get('card_type') for n in document.get('nodes',[]) if isinstance(n,dict)}
        for n in document.get('nodes',[]):
            if isinstance(n,dict):
                for field in ('card','part','printed_card_portion'):
                    m=re.fullmatch(r'([0-9]{4})[A-Z0-9]{2}',str(n.get(field,'')))
                    if m:cards.add(m[1])
        _CACHE[path]={'document':document,'sha256':raw_sha,'stat':key,'cards':cards}
        while len(_CACHE)>_CACHE_LIMIT:_CACHE.popitem(last=False)
    _CACHE.move_to_end(path)
    return deepcopy(_CACHE[path]) if detached else _CACHE[path]


def read(path,root=None):
    entry=load(path,root)
    return entry['document'] if entry else json_read(path)


def _source_paths(root):
    return sorted(p.resolve() for p in (root/'json').rglob('*.json')
                  if not any(x in ('Card-ALD','Card types','Card types current') for x in p.relative_to(root/'json').parts[:-1]))


def identity_index(root):
    """Lightweight exact occurrence inventory; no copied pins or wire cells."""
    root=Path(root).resolve();epoch=source_epoch(root)
    signature=epoch['binding']['sha256'] if epoch else None
    if not epoch or root not in _INDICES or _INDICES[root]['signature']!=signature:
        paths=_source_paths(root);cards={};models=[];documents={}
        for path in paths:
            # Current published model ownership is explicit. Auxiliary source
            # fact tables sometimes have nodes too; they are not another ALD
            # occurrence of those cards. Unbound fixture trees remain scanned.
            if epoch and path not in epoch['models']:continue
            data=json_read(path)
            if not isinstance(data,dict):continue
            if data.get('schema')==SCHEMA:
                if epoch and epoch['models'].get(path)!=digest(path):raise ValueError('Source index model is not current: '+str(path))
                doc={'page':data['page'].get('page'),'nodes':[]}
                for o in data['objects']:
                    if o['source_form']['container']!='nodes':continue
                    n={**o.get('source_literals',{}),**o.get('identifiers',{})}
                    identity=o.get('card_identity',{})
                    if identity.get('parse_status')=='resolved':n.update(card_type=identity['card_type'],portion=identity['portion'])
                    elif identity.get('parse_status')=='conflict':n['_identity_conflict']=identity
                    if any(o.get('current_extensions',{}).get(k) is True for k in ('symbol_only','annotation_only','annotation_block')):n['_annotation_excluded']=True
                    n['_source_pointer']='/nodes/'+str(o['source_form']['ordinal'])
                    doc['nodes'].append(n)
            elif isinstance(data.get('nodes'),list):doc=view(data,root)
            else:continue
            models.append(path);documents[path]={'document':doc,'sha256':digest(path)}
            mentioned={n.get('card_type') for n in doc.get('nodes',[]) if isinstance(n,dict)}
            for n in doc.get('nodes',[]):
                if not isinstance(n,dict):continue
                for field in ('card','part','printed_card_portion'):
                    m=re.fullmatch(r'([0-9]{4})[A-Z0-9]{2}',str(n.get(field,'')))
                    if m:mentioned.add(m[1])
            for value in mentioned:cards.setdefault(value,[]).append(path)
        _INDICES[root]={'signature':signature,'paths':paths,'models':models,'cards':cards,'documents':documents}
    return _INDICES[root]


def iter_documents(root,card=None):
    root=Path(root).resolve()
    # Bound production inventories are shared across a multi-card batch.
    # Unbound fixture/external trees are freshly inventoried on every call.
    index=identity_index(root)
    for path in index['models'] if card is None else index['cards'].get(card,[]):
        entry=load(path,root,detached=False)
        yield path,{'document':deepcopy(entry['document']),'sha256':entry['sha256']}


def card_nodes(document,card):
    return [n for n in document.get('nodes',[]) if isinstance(n,dict) and n.get('card_type')==card and not n.get('_identity_conflict') and not n.get('_annotation_excluded')]


def find_node(document,identifier,card=None):
    nodes=[n for n in document.get('nodes',[]) if isinstance(n,dict) and n.get('id')==identifier and (card is None or n.get('card_type')==card)]
    if len(nodes)!=1:raise ValueError('Source node identity is absent or ambiguous')
    return nodes[0]


def runtime_paths(root):
    configure(root)
    return [Path(__file__).resolve()]+[_NORMALIZATION/p for p in ('pages.py','identity.py','terminals.py')]


def finding(status,field,observed,expected,reason,**extra):
    return dict(status=status,field=field,observed=observed,expected=expected,reason=reason,**extra)


def resolve_path(root,value):
    p=Path(value);return p if p.is_absolute() else root/p


def _accepted_page_context(root):
    """Only exact current accepted model/TXT pairs may inherit page review."""
    root=Path(root).resolve();mp=root/'notes/Card types current/Build manifest.json'
    if not mp.is_file():return {'pages':{},'bindings':[]}
    manifest=json_read(mp);bindings=[{'path':str(mp),'sha256':digest(mp)}]
    expected=manifest.get('source_binding',{})
    documents={}
    for name,key in [('Reviewed export provenance.json','reviewed_export_provenance_sha256'),('Content data manifest.json','content_data_manifest_sha256')]:
        p=root/'notes'/name
        if not p.is_file() or digest(p)!=expected.get(key):raise ValueError('Current accepted-source binding is stale: '+str(p))
        bindings.append({'path':str(p),'sha256':digest(p)});documents[name]=json_read(p)
    accepted={}
    for entry in documents['Reviewed export provenance.json']['exported']:
        pieces=str(entry['destination']).replace('\\','/').split('/ALD/',1)
        if len(pieces)!=2:raise ValueError('Accepted source has no exact ALD path')
        text='ALD/'+pieces[1]
        if text in accepted:raise ValueError('Duplicate accepted source TXT')
        accepted[text]=entry['text_sha256']
    content={e['path']:e['sha256']for e in documents['Content data manifest.json']['files']if e.get('role')=='Published page content model'}
    pages={}
    for text,item in manifest.get('source_pages',{}).items():
        p=(root/item['model']).resolve();tp=(root/text).resolve()
        if not p.is_relative_to(root)or not tp.is_relative_to(root):raise ValueError('Accepted source path escapes repository')
        if accepted.get(text)!=item['text_sha256']or content.get(item['model'])!=item['model_sha256']:raise ValueError('Current catalogue and accepted page bindings disagree')
        pages[p]={'text':tp,'text_sha256':item['text_sha256'],'model_sha256':item['model_sha256']}
    return {'pages':pages,'bindings':bindings}


def accepted_page_context(root):
    root=Path(root).resolve()
    paths=[root/'notes/Card types current/Build manifest.json',root/'notes/Reviewed export provenance.json',root/'notes/Content data manifest.json',root/'notes/Source status.json']
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) if p.is_file() else (str(p),None,None) for p in paths)
    if root not in _CONTEXTS or _CONTEXTS[root][0]!=signature:
        context=_accepted_page_context(root)
        epoch=source_epoch(root)
        if epoch:context['bindings'].append(deepcopy(epoch['binding']))
        _CONTEXTS[root]=(signature,context)
    return deepcopy(_CONTEXTS[root][1])


def exact_source_node(document,record):
    """Pointer first; optional ID corroboration; no anonymous-ID fallback."""
    nodes=document.get('nodes',[]);pointer=record.get('node_pointer');expected=record.get('node')
    if pointer is not None:
        match=re.fullmatch(r'/nodes/(0|[1-9][0-9]*)',pointer)if isinstance(pointer,str)else None
        if not match:return None,None,'Invalid explicit source node pointer.'
        i=int(match[1])
        if i>=len(nodes)or not isinstance(nodes[i],dict):return None,None,'Source node pointer is absent or not an object.'
        node=nodes[i]
        if expected not in(None,'')and node.get('id')!=expected:return None,None,'Source pointer and optional declared ID disagree.'
        return node,pointer,None
    if expected in(None,''):return None,None,'No pointer or unique non-null source ID.'
    matches=[(i,n)for i,n in enumerate(nodes)if isinstance(n,dict)and n.get('id')==expected]
    if len(matches)!=1:return None,None,'Source ID fallback is absent or ambiguous.'
    i,node=matches[0];return node,f'/nodes/{i}',None


def node_mentions_card(node,card):
    return node.get('card_type')==card or any(isinstance(node.get(k),str)and re.fullmatch(r'[0-9]{4}[A-Z0-9]{2}',node[k])and node[k][:4]==card for k in('card','part','printed_card_portion'))


def identity_document(root,path,document,context):
    """Apply accepted-page review only; current identity was resolved once."""
    result=deepcopy(document);accepted=context['pages'].get(Path(path).resolve())
    inheritable=False
    if accepted:
        if digest(path)!=accepted['model_sha256'] or digest(accepted['text'])!=accepted['text_sha256']:
            raise ValueError('Current source model/TXT changed: '+str(path))
        inheritable=document.get('source_reviewed') is True
    for i,node in enumerate(result.get('nodes',[])):
        if not isinstance(node,dict):continue
        node.setdefault('_source_pointer',f'/nodes/{i}')
        if 'source_reviewed' not in node and inheritable:
            node['source_reviewed']=True;node['_source_review_inherited']=True
    return result


def selected_source_nodes(document,card):
    return card_nodes(document,card)


def source_identity_issues(document,card):
    issues=[]
    for node in document.get('nodes',[]):
        if not isinstance(node,dict)or node.get('_annotation_excluded')or not node_mentions_card(node,card):continue
        if node.get('_identity_conflict'):issues.append(dict(page=document.get('page'),block=node.get('id'),node_pointer=node.get('_source_pointer'),**finding('source_uncertainty','source_identity',node['_identity_conflict'],card,'Explicit source identity aliases disagree; no identity selected.')))
    return issues


def catalogue_source_coverage(root,catalog,documents):
    """Count by model path and source pointer; repeated/anonymous IDs stay distinct."""
    expected=Counter();issues=[];card=catalog['card_type']
    for obs in catalog.get('diagram_occurrences',[]):
        rel=Path(obs['source_text']);parts=list(rel.parts)
        if parts and parts[0]=='ALD':parts[0]='json'
        p=resolve_path(root,Path(*parts).with_suffix('.json')).resolve();entry=documents.get(p)
        if not entry:
            issues.append(dict(page=obs.get('page'),block=obs.get('node'),node_pointer=obs.get('node_pointer'),**finding('source_uncertainty','catalog_coverage','catalog model absent',None,'Catalogue observation is not represented in the loaded current source models.')));continue
        node,pointer,problem=exact_source_node(entry['document'],obs)
        if problem or node.get('_identity_conflict')or node.get('card_type')!=card or str(node.get('portion'))!=str(obs.get('portion')):
            issues.append(dict(page=obs.get('page'),block=obs.get('node'),node_pointer=obs.get('node_pointer'),**finding('source_uncertainty','catalog_coverage',obs,None,problem or 'Catalogue source pointer has a conflicting card/portion identity.')));continue
        expected[(str(p),pointer)]+=1
    live=Counter((str(p),n['_source_pointer'])for p,e in documents.items()for n in selected_source_nodes(e['document'],card))
    for key in sorted(set(expected)|set(live)):
        if expected[key]!=live[key]:issues.append(dict(model=key[0],node_pointer=key[1],**finding('source_uncertainty','catalog_coverage',{'catalogue':expected[key],'source':live[key]},None,'Catalogue and source occurrence multiplicities differ; no observation is silently omitted.')))
    return issues,{'catalogue_observations':len(catalog.get('diagram_occurrences',[])),'resolved_catalogue_observations':sum(expected.values()),'source_observations':sum(live.values()),'exact_model_pointer_keys':len(live),'catalogue_coverage_issues':len(issues)}


def unambiguous_wiring_documents(documents,card):
    """Keep core wiring policy; unnamed/duplicate IDs cannot identify wire endpoints."""
    result=deepcopy(documents);issues=[]
    for path,entry in result.items():
        doc=entry['document'];counts=Counter(n.get('id')for n in doc.get('nodes',[])if isinstance(n,dict)and not n.get('_annotation_excluded'))
        kept=[]
        for n in doc.get('nodes',[]):
            if not isinstance(n,dict):continue
            if n.get('_annotation_excluded'):continue
            if n.get('id')in(None,'')or counts[n.get('id')]!=1:
                if n.get('card_type')==card:issues.append(dict(page=doc.get('page'),block=n.get('id'),node_pointer=n.get('_source_pointer'),**finding('source_uncertainty','source_block_identity_for_wiring',n.get('id'),None,'Occurrence is compared by exact model/pointer, but unnamed or duplicate block IDs cannot certify named source-wire endpoints.')))
                continue
            kept.append(n)
        doc['nodes']=kept
    return result,issues


def recheck_identity_context(context,documents):
    for b in context['bindings']:
        if digest(b['path'])!=b['sha256']:raise ValueError('Accepted source metadata changed during read-only analysis')
    for path,e in documents.items():
        if digest(path)!=e['sha256']:raise ValueError('Source model changed during read-only analysis')
        accepted=context['pages'].get(Path(path).resolve())
        if accepted and digest(accepted['text'])!=accepted['text_sha256']:raise ValueError('Accepted source TXT changed during read-only analysis')


def recheck_epoch(root):
    """Finish a multi-card batch with one complete current source-byte guard.

    This includes excluded and not-requested cards so a changed model cannot
    hide behind an earlier cached per-card membership decision.
    """
    root=Path(root).resolve();epoch=source_epoch(root)
    if not epoch:return {'source_models':0,'current_checkpoint':False}
    if digest(epoch['binding']['path'])!=epoch['binding']['sha256']:raise ValueError('Source checkpoint changed during batch')
    index=_INDICES.get(root)
    if index and _source_paths(root)!=index['paths']:raise ValueError('Current source inventory changed during batch')
    for path,expected in epoch['models'].items():
        if digest(path)!=expected:raise ValueError('Normalized source model changed during batch: '+str(path))
    for path,cached in _SCAN_BINDINGS.items():
        if digest(path)!=cached['binding']['sha256']:raise ValueError('Original scan changed during batch: '+str(path))
    return {'source_models':len(epoch['models']),'current_checkpoint':True,'source_scans':len(_SCAN_BINDINGS)}




def physical_contact(raw):
    """Parse a physical name without interpreting its numeric annotation."""
    if raw is None:
        return None
    text = str(raw).strip()
    match = re.fullmatch(r"\d*(?P<pin>[BDGJ](?:0[2-9]|1[0-3]))[XT✲*]*", text)
    return match.group("pin") if match else None


def physical_readings(port):
    """Current physical contact separately from preserved printed symbols.

    Uniform terminals already distinguish physical identity from literal marks.
    A reviewed corrected active pin can coexist with a damaged printed mirror.
    Conflicting active physical fields still return all candidates. Legacy
    external fixtures retain strict printed/physical mirror comparison.
    """
    if '_pin_number_status' in port:
        if port['_pin_number_status']=='observed' and physical_contact(port.get('_pin_number')):
            return {'uniform_pin_number':physical_contact(port['_pin_number'])}
        if any(port.get(k) is True for k in ('source_unknown_pin','pin_inferred')):return {}
        fields=('physical_pin','physical_pin_candidate','pin')
    else:fields=('physical_pin','physical_pin_candidate','printed_pin','printed_label','pin')
    return {field:pin for field in fields if (pin:=physical_contact(port.get(field))) is not None}


def terminal_contact(port):
    values=set(physical_readings(port).values())
    return next(iter(values)) if len(values)==1 else None


def wedge(port):
    """Return an observed border triangle, false, or genuinely unknown."""
    decorations=port.get('_border_decorations')
    if decorations is not None:
        marks=[]
        for decoration in decorations:
            value=decoration.get('observed_value')
            if decoration.get('kind')=='triangle' and type(value)is bool:marks.append(value)
            elif decoration.get('glyph')=='◺':marks.append(True)
        if marks:return marks[0] if len(set(marks))==1 else None
    if port.get('border_marker')=='◺':return True
    if 'triangle' in port and port['triangle'] is not None:return bool(port['triangle'])
    if 'border_marker' in port:return False
    return None

def resolve_net_port(node, endpoint, side, adapted_pins=None):
    """Resolve local terminal identity before its printed contact label.

    Explicit source aliases take precedence over synthesized label aliases.
    Failed lookup is unresolved, never evidence of an anonymous terminal.
    """
    node_id = str(node.get("id", node.get("node", "")))
    if not isinstance(endpoint, str) or not endpoint.startswith(node_id + "."):
        return {"status": "unresolved", "reason": "endpoint outside scoped node"}
    suffix = endpoint[len(node_id) + 1:]
    raw_ports = node.get("pins", [])
    if not isinstance(raw_ports, list) or any(not isinstance(port, dict) for port in raw_ports):
        return {"status": "unresolved", "reason": "unsupported raw terminal schema"}
    ports = [(i, p) for i, p in enumerate(raw_ports) if p.get("side") == side]

    def k_marked(port):
        return any(port.get(k) == "K" for k in
                   ("border_marker", "border_control", "border_qualifier", "printed_qualifier", "marker"))

    def contact_label(port, value):
        contact = physical_contact(value)
        if contact is None and k_marked(port) and isinstance(value, str):
            match = re.fullmatch(r"K([BDGJ](?:0[2-9]|1[0-3]))[✲*]?", value.strip())
            if match:
                contact = match.group(1)
        return contact

    def declared_aliases(port):
        names = set()
        for field in ("reference", "terminal_id", "ref", "id", "port_id", "key", "alias",
                      "aliases", "references", "terminal_ids"):
            values = port.get(field, [])
            for value in values if isinstance(values, (list, tuple)) else [values]:
                if isinstance(value, int) and not isinstance(value, bool):
                    value = str(value)
                if isinstance(value, str) and value:
                    names.add(value if value.startswith(node_id + ".") else node_id + "." + value)
        return names

    def label_aliases(port):
        names = {node_id + "." + port[k] for k in ("pin", "printed_pin")
                 if isinstance(port.get(k), str) and port[k]}
        if k_marked(port):
            for value in list(names | declared_aliases(port)):
                tokens = value.split(".")
                for token in tokens:
                    if token.startswith("K") and contact_label(port, token):
                        names.add(".".join(token[1:] if t == token else t for t in tokens))
        return names

    matches = [(i, port) for i, port in ports if endpoint in declared_aliases(port)]
    basis = "exact side-scoped declared terminal alias"
    if not matches:
        matches = [(i, port) for i, port in ports if endpoint in label_aliases(port)]
        basis = "exact side-scoped printed-label alias"
    if not matches:
        # Some source models explicitly qualify endpoint labels with a row.
        qualified = re.fullmatch(r"(.+)@(\d+)", suffix)
        row = int(qualified.group(2)) if qualified else None
        label = qualified.group(1) if qualified else suffix
        named_contact = physical_contact(label)
        if named_contact:
            matches = [(i, port) for i, port in ports
                       if contact_label(port, port.get("pin")) == named_contact
                       and (row is None or port.get("absolute_row", port.get("row")) == row)]
            basis = "exact side-scoped physical label" + (" and row" if row is not None else "")
        elif qualified and label.lower() in ({"in", "input"} if side == "input" else {"out", "output"}):
            matches = [(i, port) for i, port in ports
                       if port.get("absolute_row", port.get("row")) == row]
            basis = "exact side-scoped terminal row"
        elif suffix == '':
            # Some accepted pages name a truly unlabelled terminal as AA.
            # Certify it only when one side-scoped anonymous port exists;
            # an unreadable or numbered pin is never an anonymous fallback.
            matches = [(i,port) for i,port in ports
                       if port.get('pin') in (None,'')
                       and not any(port.get(k) not in (None,'') for k in ('physical_pin','printed_pin','printed_label'))
                       and not any(port.get(k) is True for k in ('source_unknown_pin','pin_inferred'))]
            basis = 'single side-scoped anonymous terminal for explicit empty reference'
        else:
            # Unqualified numbered forms are rows only when an ordinal index
            # is impossible. Ambiguous zero/one-based ordinals stay unresolved.
            numeric = re.fullmatch(r"(?:in|input)(\d+)" if side == "input" else r"(?:out|output)(\d+)", suffix, re.I)
            if numeric and int(numeric.group(1)) > len(ports):
                row = int(numeric.group(1))
                matches = [(i, port) for i, port in ports
                           if port.get("absolute_row", port.get("row")) == row]
                basis = "unambiguous local terminal row convention"
            elif suffix.lower() in ({"in", "input"} if side == "input" else {"out", "output"}):
                matches = ports
                basis = "single local side-specific generic endpoint"
    if len(matches) != 1:
        return {"status": "unresolved", "reason": "ambiguous terminal alias" if matches else "terminal alias not found",
                "candidate_indices": [i for i, _ in matches]}
    index, raw = matches[0]
    effective = raw
    if adapted_pins is not None:
        if index >= len(adapted_pins) or any(adapted_pins[index].get(k) != raw.get(k) for k in ("side", "row")):
            return {"status": "unresolved", "reason": "adapted/raw port identity differs", "port_index": index}
        effective = adapted_pins[index]
    label = effective.get("pin")
    contact = contact_label(raw, label)
    raw_contact = contact_label(raw, raw.get("pin"))
    mirrors = {contact_label(raw, raw.get(k)) for k in ("physical_pin", "printed_pin", "printed_label")}
    mirrors.discard(None)
    semantic = bool(re.fullmatch(
        r"(?:(?:[A-Z][A-Z0-9]*_)?(?:IN|OUT)(?:[_-].*)?|INPUT|OUTPUT|TIE|TERMINAL|FEEDTHROUGH)", str(label), re.I))
    if contact is None and semantic and len(mirrors) == 1:
        contact = next(iter(mirrors))
    result = {"port_index": index, "basis": basis, "raw_port": deepcopy(raw),
              "effective_label": label, "physical_contact": contact}
    if len(mirrors) > 1 or (raw_contact and mirrors and mirrors != {raw_contact}):
        return {**result, "status": "unresolved", "reason": "conflicting raw physical contact mirrors"}
    if contact:
        return {**result, "status": "numbered"}
    placeholder = label is None or str(label).strip() == "" or re.fullmatch(
        r"(?:IN|OUT)\d*|[AB]|(?:input|output)\d*", str(label), re.I)
    if placeholder and not mirrors:
        return {**result, "status": "pinless"}
    return {**result, "status": "unresolved", "reason": "unreadable or unsupported printed contact label"}

