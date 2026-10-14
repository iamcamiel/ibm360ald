"""Build a read-only card/portion reference from an accepted ALD repository.

Python 3.10+, standard library only. Never modifies input files. Repository-relative
paths, compact source IDs and JSON pointers make the generated data portable.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0"
UNITS = {x: "02" + x for x in "ABCEKL"}
CARD = re.compile(r"^[0-9]{4}$")
PORTION = re.compile(r"^[A-Z0-9]{2}$")
CARDPORTION = re.compile(r"^([0-9]{4})([A-Z0-9]{2})$")
PIN = re.compile(r"^([0-9]*)([A-Z][0-9]{2})([✲*]?)$")
LOCATION = re.compile(r"^(02[ABCEKL]|[ABCEKL])-([A-Z][0-9])([A-Z][0-9])([BT]?)$")

def read(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def norm(value):
    return " ".join(str(value).replace("*", "✲").split()) if value is not None else None
def sid(prefix, value): return prefix + hashlib.sha256(value.encode()).hexdigest()[:16]
def slashes(value): return str(value).replace("\\", "/")
def csvwrite(p, fields, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row.get(k), (list, dict)) else row.get(k) for k in fields})
def page_from_stem(stem): return stem.split(" ")[0]
def repo_path_from_absolute(value, repo, category):
    value = slashes(value)
    marker = "/" + category + "/"
    if marker not in value: raise ValueError("Missing repository category in " + value)
    tail = value.rsplit(marker, 1)[1]
    return category + "/" + tail
def board_norm(board):
    if not isinstance(board, str): return None
    b = board.strip(); match = re.fullmatch(r"(02[ABCEKL]|[ABCEKL])-([A-Z][0-9])", b)
    return (UNITS.get(match[1], match[1]) + "-" + match[2]) if match else None
def location_norm(value):
    match = LOCATION.fullmatch(str(value or "").strip())
    return (UNITS.get(match[1], match[1]) + "-" + match[2], match[3]) if match else (None, None)
def sockets_norm(raw):
    if isinstance(raw, str): raw = [raw]
    result = []
    for value in raw or []:
        match = re.fullmatch(r"([A-Z][0-9])(?:[BT])?", str(value))
        if match: result.append(match[1])
    return sorted(set(result))
def width_norm(raw):
    word = norm(raw)
    return "double" if word in ("DOUBLE", "DOUBLE CARD", "double_card") else "single" if word in ("SINGLE", "SINGLE CARD", "single_card") else None
def pin_label(pin):
    for k in ("raw_printed_pin_field", "printed_combined_label", "printed_pin", "printed_pin_label", "printed_label", "pin", "label"):
        if k in pin and pin[k] is not None: return pin[k], k
    return None, "pin" if "pin" in pin else None
def pin_parse(label):
    match = PIN.fullmatch(str(label or "").strip())
    return {"physical_pin": match[2], "numeric_prefix": match[1] or None, "adjacent_asterisk": norm(match[3]) or None} if match else {"physical_pin": None, "numeric_prefix": None, "adjacent_asterisk": None}
def direction(pin):
    for key in ("electrical_direction", "logical_direction", "semantic_direction", "printed_direction", "side"):
        value = pin.get(key)
        if value in ("input", "output"): return value
    return None
def compatible(mask, value):
    mask, value = norm(mask), norm(value)
    return mask is not None and value is not None and len(mask) == len(value) and all(a == "�" or a == b for a, b in zip(mask, value))
def canvas_candidate(mask,value):
    """Retain every existing layout space while supplying matched semantic tokens."""
    tokens=list(re.finditer(r'\S+',mask)); desired=norm(value).split();result=list(mask)
    if len(tokens)!=len(desired):return None
    for token,replacement in zip(tokens,desired):
        if len(token[0])!=len(replacement):return None
        for j,char in enumerate(replacement):
            before=token[0][j]
            if before!='�' and norm(before)!=norm(char):return None
            result[token.start()+j]=char if before=='�' else before
    return ''.join(result)

def build(args):
    repo = args.repo_root.resolve(); out = args.output_root.resolve()
    if out == repo or repo in out.parents: raise ValueError("Private output must be outside the input repository")
    export_path = repo / "notes/Reviewed export provenance.json"
    manifest_path = repo / "notes/Content data manifest.json"
    export, manifest = read(export_path), read(manifest_path)
    initial_hashes = {str(p): sha(p) for p in (export_path, manifest_path, args.human_facts)}
    if args.question_manifest: initial_hashes[str(args.question_manifest)] = sha(args.question_manifest)
    sources, pages, file_sources = {}, {}, {}
    original_stats = {}
    def add_source(rel, role, expected=None, **extra):
        path = repo / rel; actual = sha(path)
        if expected is not None and actual != expected: raise ValueError("Accepted input hash mismatch: " + rel)
        key = sid("s", rel)
        sources[key] = {"path": rel, "sha256": actual, "role": role, **extra}
        file_sources[rel] = key
        return key
    add_source("notes/Reviewed export provenance.json", "Accepted text snapshot")
    add_source("notes/Content data manifest.json", "Accepted content manifest")
    for entry in export["exported"]:
        rel = repo_path_from_absolute(entry["destination"], repo, "ALD")
        text_id = add_source(rel, "Accepted page UTF-8 text", entry["text_sha256"], scan_id=str(entry["source_scan_id"]), page=entry["page"])
        scan = str(entry["source_scan_id"])
        pages[scan] = {"scan_id": scan, "page": entry["page"], "text_source_id": text_id, "text_path": rel,
                       "source_relative": slashes(entry["source_relative"]), "acceptance_record": slashes(entry.get("review_record", "")),
                       "original_scan_name": entry.get("original_scan_name"), 'scan_timestamp':entry.get('scan_timestamp'), "model_source_ids": []}
        original = args.source_root / slashes(entry["source_relative"])
        original_id = "t" + scan
        sources[original_id] = {"path": slashes(entry["source_relative"]), "sha256": sha(original), "role": "Build-time observed original TIFF hash; accepted TXT/model snapshot is separate", "source_archive": True,
                                "scan_id": scan, "original_scan_name": entry.get("original_scan_name")}
        pages[scan]["original_source_id"] = original_id
        original_stats[str(original)] = (original.stat().st_size, original.stat().st_mtime_ns)
    text_stems = {str(Path(p["text_path"]).with_suffix(""))[4:]: p for p in pages.values()}
    page_names = defaultdict(list)
    for p in pages.values():
        page_names[p["page"]].append(p)
        page_names[Path(p["text_path"]).stem].append(p)
    documents = []
    for file in manifest["files"]:
        rel = slashes(file["path"])
        source_id = add_source(rel, file["role"], file["sha256"])
        if not rel.lower().endswith(".json"): continue
        model = read(repo / rel)
        key = str(Path(rel).with_suffix(""))[5:]
        page = text_stems.get(key)
        if page:
            page["model_source_ids"].append(source_id)
            if isinstance(model, dict):
                nested = model.get("source")
                declared = model.get("source_sha256") or (nested.get("source_sha256") if isinstance(nested, dict) else None)
                page["source_TIFF_sha256_declared_by_accepted_model"] = declared
                if declared and sources[page["original_source_id"]]["sha256"] != declared: raise ValueError("Original TIFF disagrees with accepted model: " + rel)
        documents.append((rel, source_id, model, page))
    human_id = "human-card-type-request"
    human_copy = out / "notes/Card types/Direct human card-type observations.json"
    human_copy.parent.mkdir(parents=True, exist_ok=True); human_copy.write_bytes(args.human_facts.read_bytes())
    sources[human_id] = {"path": human_copy.relative_to(out).as_posix(), "sha256": sha(args.human_facts), "role": "Direct human observations; independent of model readings", "external_input": True}
    normalization_authorities=[]
    for authority in args.function_authority:
        original=read(authority); copied=out/'notes/Card types'/authority.name
        copied.parent.mkdir(parents=True,exist_ok=True);copied.write_bytes(authority.read_bytes())
        aid=sid('h',authority.name)
        sources[aid]={'path':copied.relative_to(out).as_posix(),'sha256':sha(authority),'role':'Direct human function correction/normalization authority','external_input':True}
        statements={k:original[k] for k in ('raw_statement','raw_statements') if k in original}
        if not statements:raise ValueError('Function authority lacks its exact raw human statement: '+str(authority))
        normalization_authorities.append({'source_id':aid,**statements,'semantic_whitespace_rule':original.get('semantic_whitespace_rule'),'active_JSON_rule':original.get('active_JSON_rule')})
        initial_hashes[str(authority)]=sha(authority)
    recovery_by_page=defaultdict(list)
    post_answer_ids=set(); post_answer_inputs=[]
    question_by_id={}
    if args.question_manifest:
        qm=read(args.question_manifest)
        question_by_id={q['id']:q for q in qm.get('questions',[])}
        for collection in ('recorded','recovered','recovered_history'):
            for q in qm.get(collection,[]):
                original=q.get('original_question') if isinstance(q.get('original_question'),dict) else q
                recovery_by_page[q.get('page',original.get('page'))].append({'question_id':q.get('id',original.get('id')),'kind':q.get('_kind',original.get('_kind')),
                    'row':q.get('row',original.get('row')),'column':q.get('column',original.get('column')),'covered_cells':q.get('covered_cells',original.get('covered_cells',[])),
                    'status':collection,'location':q.get('location',original.get('location')),
                    'source_scan_id':str(q.get('source_scan_id',original.get('source_scan_id'))) if q.get('source_scan_id',original.get('source_scan_id')) is not None else None})
    for ledger in args.additional_answer_ledger:
        original=read(ledger); copied=out/'notes/Card types'/ledger.name
        copied.parent.mkdir(parents=True,exist_ok=True);copied.write_bytes(ledger.read_bytes())
        ledger_id=sid('h',ledger.name)
        sources[ledger_id]={'path':copied.relative_to(out).as_posix(),'sha256':sha(ledger),'role':'Immutable additional recorded human answers; not a new native observation','external_input':True}
        initial_hashes[str(ledger)]=sha(ledger)
        post_answer_inputs.append({'source_id':ledger_id,'sha256':sha(ledger)})
        for i,answer in enumerate(original.get('answers',[])):
            q=question_by_id.get(answer.get('id'),{})
            scan=str(answer.get('source_scan_id') or q.get('source_scan_id') or '')
            if q and (answer.get('page')!=q.get('page') or (q.get('source_scan_id') is not None and scan!=str(q['source_scan_id']))):
                raise ValueError('Additional answer disagrees with immutable question identity: '+str(answer.get('id')))
            row,column=q.get('row'),q.get('column'); literal=q.get('current_reading','')
            cells=[[row,column+j] for j in range(len(literal))] if isinstance(row,int) and isinstance(column,int) else []
            recovery_by_page[answer.get('page')].append({'question_id':answer.get('id'),'kind':q.get('_kind'),
                'row':row,'column':column,'covered_cells':cells,'status':'additional recorded human answer',
                'location':q.get('location'),'source_scan_id':scan,'answer':answer.get('answer'),
                'source_id':ledger_id,'JSON_pointer':f'/answers/{i}','binding_status':'Immutable issued question coordinates' if cells else 'No exact cell binding available'})
            post_answer_ids.add(answer.get('id'))
    def repairs_for_page(page):
        return [r for r in recovery_by_page[page['page']] if not r.get('source_scan_id') or r['source_scan_id']==page['scan_id']]
    cards = {}
    def card(code):
        if code not in cards:
            cards[code] = {"card_type": code, "full_part_number_facts": [], "card_width_facts": [], "observed_portions": [],
                           "observed_portion_inventory_complete": False, "physical_pinout_complete": False,
                           "listing_observations": [], "diagram_observations": [], "human_observations": [], "physical_instances": [], "portions": {}, "conflicts": []}
        return cards[code]
    skipped = Counter(); listing_records = []; coverage_ledger = []
    def listing_page(record, docpage, model, rel):
        if docpage: return docpage
        name = record.get("source_listing", record.get("source_files", record.get("listing_page")))
        if isinstance(name, list): name = next((x for x in name if isinstance(x, str) and x.startswith("A1")), None)
        if not name and record.get("source"): name = Path(slashes(record["source"])).stem
        if isinstance(name, str) and re.fullmatch(r"[0-9]{2}", name):
            base = Path(rel).stem.split(" ")[0]
            name = base + "-" + name
        if isinstance(name, str):
            candidates = page_names.get(name, page_names.get(page_from_stem(name), []))
            unique = {x["scan_id"]: x for x in candidates}
            if len(unique) == 1: return next(iter(unique.values()))
        return None
    # Per-page models are primary; shared records remain supplements, with one printed dependency per source section.
    listing_documents = sorted(documents, key=lambda d: (Path(d[0]).name in ("Socket reference.json", "ALD references.json"), d[0]))
    primary_headers = defaultdict(list)
    for rel, source_id, model, docpage in listing_documents:
        if not rel.startswith("json/A1 Socket Listing/") or not isinstance(model, dict): continue
        for collection in ("sockets", "records", "sections", "socket_records"):
            if not isinstance(model.get(collection), list): continue
            for i, record in enumerate(model[collection]):
                if not isinstance(record, dict): continue
                code = str(record.get("card_type", ""))
                if not CARD.fullmatch(code):
                    if record.get('card_type') is not None: coverage_ledger.append({"source_id":source_id,"JSON_pointer":f"/{collection}/{i}","card_type_literal":record.get('card_type'),"reason":"Unreadable/non-numeric card identity; not assigned to a type"})
                    continue
                kind = record.get("kind"); width = width_norm(kind)
                if width is None and norm(kind) != "CONTINUATION": skipped["A1 non-card or unknown-kind record"] += 1; continue
                page = listing_page(record, docpage, model, rel)
                if page is None:
                    skipped["A1 record not bound to current accepted page"] += 1
                    coverage_ledger.append({"source_id":source_id,"JSON_pointer":f"/{collection}/{i}","reason":"Shared/aggregate record lacks a unique current accepted listing page"});continue
                board_literal = record.get("board", model.get("board")); board = board_norm(board_literal)
                socket_literals = record.get("sockets", [record.get("socket")] if record.get("socket") else [])
                occupied_socket_literals=record.get('occupied_sockets')
                sockets = sockets_norm(occupied_socket_literals if width=='double' and occupied_socket_literals else socket_literals)
                if not board or not sockets: skipped["A1 incomplete physical location"] += 1; continue
                pointer = f"/{collection}/{i}"; obs_id = sid("l", source_id + pointer)
                dependency = sid("d", page["scan_id"] + ":" + board + ":" + ",".join(sockets))
                refs = []
                for j, ref in enumerate(record.get("references", [])):
                    if not isinstance(ref, dict): continue
                    portions = ref.get("printed_portions", ref.get("portions", []))
                    if isinstance(portions, str): portions = portions.split()
                    refs.append({"JSON_pointer": pointer + f"/references/{j}", "ALD_page_literal": ref.get("ALD_page", ref.get("ald_page")),
                                 "portion_literals": portions, "readable_portions": [str(x) for x in portions if PORTION.fullmatch(str(x))]})
                part = record.get("part_number")
                obs = {"observation_id": obs_id, "source_id": source_id, "text_source_id": page["text_source_id"], "scan_id": page["scan_id"], "page": page["page"],
                       "JSON_pointer": pointer, "printed_dependency_id": dependency, "board_literal": board_literal, "board_match_key": board,
                       "socket_literals": socket_literals, 'printed_start_socket_literal':record.get('socket'),'occupied_socket_literals':occupied_socket_literals,
                       'pair_membership_JSON_pointer':pointer+'/occupied_sockets' if width=='double' and occupied_socket_literals else pointer+'/sockets',
                       "socket_match_keys": sockets, "card_type_literal": code, "card_size_literal": kind, "card_width": width,
                       "part_number_literal": part, "source_column": record.get("source_column"), "source_row": record.get("source_row", record.get("source_y")),
                       "references": refs, "unused_portion_literals": record.get("unused_portions", []), "printed_lines": record.get("printed_lines"),
                       "origin": "per-page listing model" if docpage else "shared supplementary listing record; same printed dependency"}
                obs['embedded_repair_dependency_pointers']=['/'+k for k in model if any(word in k for word in ('firm_resolution','recover','human','source_derived'))]
                obs['field_repair_dependencies']=[]
                for repair in repairs_for_page(page):
                    text=repair.get('location') or ''
                    matched=re.search(r'\bsocket\s+([A-Z][0-9])(?:[BT])?\b',text,re.IGNORECASE)
                    if matched and matched[1].upper() in sockets:obs['field_repair_dependencies'].append(repair)
                obs['provenance_status']='Current accepted structured listing assertion; inherited repair dependencies retained, no new independent native vote'
                header = (page["scan_id"], board, tuple(sockets))
                if Path(rel).name == "Socket reference.json":
                    def assertion(o):
                        return (o['card_type_literal'],str(o['part_number_literal']),o['card_width'],sorted((str(r['ALD_page_literal']),tuple(r['portion_literals'])) for r in o['references']))
                    if not any(assertion(p)==assertion(obs) for p in primary_headers[header]):
                        skipped['Stale/unvalidated copied A1 index record']+=1
                        coverage_ledger.append({'source_id':source_id,'JSON_pointer':pointer,'printed_dependency_id':dependency,'reason':'Legacy derived index does not exactly match a current accepted per-page/shared-table card assertion','literal_card_type':code});continue
                    obs['origin']='Legacy shared index verified against current primary listing assertion; not independent'
                else: primary_headers[header].append(obs)
                card(code)["listing_observations"].append(obs); listing_records.append(obs)
    pair_candidates = defaultdict(set)
    for obs in listing_records:
        if obs["card_width"] == "double" and len(obs["socket_match_keys"]) == 2:
            for socket in obs["socket_match_keys"]:
                pair_candidates[(obs["board_match_key"], socket, obs["card_type_literal"])].add(tuple(obs["socket_match_keys"]))
    observed_rows, pin_rows, depiction_by_page = [], [], defaultdict(list)
    for rel, source_id, model, page in documents:
        if not page or not isinstance(model, dict) or rel.startswith("json/A1 Socket Listing/"): continue
        collection = "nodes" if isinstance(model.get("nodes"), list) else "blocks" if isinstance(model.get("blocks"), list) else None
        if collection is None: continue
        text_lines = (repo/page['text_path']).read_text(encoding='utf-8-sig').splitlines()
        for ni, node in enumerate(model[collection]):
            if not isinstance(node, dict) or "printed_card_portion" not in node: continue
            literal = node.get("printed_card_portion"); match = CARDPORTION.fullmatch(str(literal or ""))
            code = match[1] if match else str(literal or "")[:4]
            if not CARD.fullmatch(code):
                skipped["ALD unreadable literal card type"] += 1
                coverage_ledger.append({'source_id':source_id,'JSON_pointer':f'/{collection}/{ni}','printed_card_portion_literal':literal,'reason':'Unreadable printed card type; no model-derived completion promoted'});continue
            portion = match[2] if match else None
            pointer = f"/{collection}/{ni}"; obs_id = sid("n", source_id + pointer)
            location = node.get("location", node.get("socket")); board, socket = location_norm(location)
            pairs = pair_candidates.get((board, socket, code), set())
            pair = list(next(iter(pairs))) if len(pairs) == 1 else None
            instance_key = board + ":" + ",".join(pair or [socket]) if board and socket else None
            obs = {"observation_id": obs_id, "source_id": source_id, "text_source_id": page["text_source_id"], "scan_id": page["scan_id"], "page": page["page"],
                   "JSON_pointer": pointer, "card_type_literal": code, "portion_literal": portion, "printed_card_portion_literal": literal,
                   "identity_complete": bool(match), "model_card_type": node.get("card_type"), "model_portion": node.get("portion"),
                   "node_identifier": node.get("id"), "printed_node_identifier": node.get("printed_id", node.get("id")),
                   "station": node.get("grid", node.get("station")), "box_bounds": {k: node[k] for k in ("row", "column", "width", "height") if k in node},
                   "function_literal": node.get("function"), "function_layout":node.get('function_layout'),
                   "printed_function_literal":node.get('function_layout',{}).get('printed_function_literal',node.get('function')) if isinstance(node.get('function_layout',{}),dict) else node.get('function'),
                   "existing_function_offset_fields":{k:node[k] for k in ('function_offset','function_column_offset') if k in node},
                   "function_normalized": (norm(node.get("function")) or None) if isinstance(node.get('function'),str) else None, "unit_code_literal": node.get("unit"),
                   "unit_code_normalized": (norm(node.get("unit")) or None) if isinstance(node.get('unit'),str) else None, "location_literal": location, "board_match_key": board, "socket_match_key": socket,
                   "verified_socket_pair": pair, "socket_pair_ambiguous": len(pairs) > 1, "physical_instance_key": instance_key,
                   "pins": [], "connected_counts_complete_physical_pinout": False}
            obs['function_readability']='unprinted/missing' if not obs['function_normalized'] else 'damaged' if '�' in obs['function_normalized'] else 'readable accepted model value'
            obs['unit_code_readability']='unprinted/missing' if not obs['unit_code_normalized'] else 'damaged' if '�' in obs['unit_code_normalized'] else 'readable accepted model value'
            rr, cc, width = node.get('row'),node.get('column'),node.get('width',8)
            bounds_valid=isinstance(rr,int) and isinstance(cc,int) and isinstance(width,int)
            def field_cells(value,role):
                matches=[]
                if not bounds_valid or not isinstance(value,str) or not value:return matches
                layout=node.get('function_layout',{})
                if role=='function' and isinstance(layout,dict) and isinstance(layout.get('text_row'),int) and isinstance(layout.get('text_column'),int):
                    tr,tc=layout['text_row'],layout['text_column']
                    if rr<=tr<=rr+node.get('height',6) and 0<=tr<len(text_lines) and text_lines[tr][tc:tc+len(value)]==value:
                        return [{'row':tr,'column':tc,'literal':value}]
                rows=range(rr+1,min(rr+3,len(text_lines))) if role=='function' else range(rr,min(rr+node.get('height',6)+1,len(text_lines)))
                for tr in rows:
                    inner=text_lines[tr][cc+1:cc+width-1]
                    if role=='function' and norm(inner)!=norm(value):continue
                    if value in inner and inner.count(value)==1:matches.append({'row':tr,'column':cc+1+inner.index(value),'literal':value})
                return matches
            obs['literal_text_bindings']={key:field_cells(value,key) for key,value in [('printed_card_portion',literal),('function',node.get('function')),('unit',node.get('unit'))]}
            obs['field_recovery_dependencies']={}
            for field,positions in obs['literal_text_bindings'].items():
                occupied={(p['row'],p['column']+j) for p in positions for j in range(len(p['literal']))}
                deps=[]
                for recovered in repairs_for_page(page):
                    if occupied & {tuple(x) for x in recovered['covered_cells']}:deps.append(recovered)
                obs['field_recovery_dependencies'][field]=deps
            obs['embedded_history_dependency_pointers']=['/'+k for k in model if any(s in k for s in ('recover','human_','source_derived','firm_resolution'))]
            counts, named_counts, unknown_counts = Counter(), Counter(), Counter()
            for pi, pin in enumerate(node.get("pins", [])):
                if not isinstance(pin, dict): continue
                label, labelkey = pin_label(pin); parsed = pin_parse(label); side = direction(pin)
                parsed['physical_pin_basis']='Complete literal physical label' if parsed['physical_pin'] else None
                parsed['printed_control_prefix_literal']=parsed['numeric_prefix']
                declared=pin.get('physical_pin')
                if not parsed['physical_pin'] and isinstance(declared,str) and re.fullmatch(r'[A-Z][0-9]{2}',declared) and isinstance(label,str):
                    literal=label.strip();suffix=declared+('✲' if literal.endswith('✲') else '*' if literal.endswith('*') else '')
                    if literal.endswith(suffix) and literal.count(declared)==1:
                        prefix=literal[:-len(suffix)]
                        if prefix and (all(ch in '0123456789�' for ch in prefix) or any(k in pin for k in ('printed_control_prefix','printed_prefix','numeric_control_prefix','control_prefix','border_operator'))):
                            parsed['physical_pin']=declared;parsed['printed_control_prefix_literal']=prefix
                            parsed['physical_pin_basis']='Explicit model physical pin matches intact literal suffix; damaged/control prefix remains separate'
                unused = any(pin.get(k) is True for k in ("source_unused", "source_supported_unused", "printed_unconnected"))
                drawn = pin.get("drawn_wire")
                connected = False if unused or drawn is False else True if drawn is True and side else None
                connection_basis='Explicit reviewed drawn_wire flag' if connected else 'Explicit unused/unconnected' if connected is False else 'No proven wire/border intersection'
                contact=None;pr=pin.get('row')
                candidate_rows=[]
                if isinstance(pin.get('absolute_row'),int):candidate_rows=[pin['absolute_row']]
                else:
                    for key in ('box_border_point','border_point','triangle_border_point','point'):
                        point=pin.get(key)
                        if isinstance(point,list) and len(point)==2 and isinstance(point[1],int):candidate_rows=[point[1]];break
                if not candidate_rows and isinstance(pr,int):candidate_rows=list(dict.fromkeys((pr,rr+pr))) if bounds_valid else [pr]
                if connected is None and bounds_valid and side and isinstance(pr,int):
                    for tr in candidate_rows:
                        if not rr<=tr<=rr+node.get('height',6) or not 0<=tr<len(text_lines):continue
                        border=cc if side=='input' else cc+width-1
                        border_char=text_lines[tr][border:border+1]
                        if not border_char or border_char not in '│◺┌┐└┘┼':continue
                        segment=text_lines[tr][max(0,border-5):border] if side=='input' else text_lines[tr][border+1:border+6]
                        adjacent=text_lines[tr][border-1:border] if side=='input' else text_lines[tr][border+1:border+2]
                        # Require actual wire glyph next to the border, or a physical pin label immediately against it with an exterior wire.
                        physical=parsed['physical_pin']
                        named_contact=False
                        if isinstance(label,str) and label and not any(ch.isspace() for ch in label):
                            start=border-len(label) if side=='input' else border+1
                            if text_lines[tr][start:start+len(label)]==label:
                                wc=text_lines[tr][start-1:start] if side=='input' else text_lines[tr][start+len(label):start+len(label)+1]
                                named_contact=bool(wc) and wc in '─┌┐└┘┼◇'
                        if physical:
                            if side=='input':
                                labelmatch=re.search(r'([0-9]*'+re.escape(physical)+r'✲?)$',text_lines[tr][max(0,border-8):border])
                                if labelmatch:
                                    start=border-len(labelmatch[1]);named_contact=named_contact or start>0 and text_lines[tr][start-1] in '─┌┐└┘┼◇'
                            else:
                                labelmatch=re.match(r'([0-9]*'+re.escape(physical)+r'✲?)',text_lines[tr][border+1:border+9])
                                if labelmatch:
                                    end=border+1+len(labelmatch[1]);wirechar=text_lines[tr][end:end+1];named_contact=named_contact or bool(wirechar) and wirechar in '─┌┐└┘┼◇'
                        if any(x in adjacent for x in '─┌┐└┘┼◇') or named_contact:
                            contact={'row':tr,'column':border,'exterior_literal':segment};connected=True;connection_basis='Actual current accepted UTF-8 wire/border intersection';break
                port = {"JSON_pointer": pointer + f"/pins/{pi}", "direction": side, "raw_side": pin.get("side"), "printed_label_literal": label,
                        "printed_label_field": labelkey, **parsed, "pin_name_readability": "physical name" if parsed['physical_pin'] else "unprinted" if label is None or norm(label)=='' else "damaged" if "�" in str(label) else "other terminal/control label",
                        'printed_label_readability':'unprinted' if label is None or norm(label)=='' else 'damaged' if '�' in str(label) else 'readable',
                        'control_prefix_readability':'damaged' if '�' in str(parsed['printed_control_prefix_literal']) else 'readable' if parsed['printed_control_prefix_literal'] else 'unprinted/not applicable',
                        "drawn_connected_port": connected, "connection_basis": connection_basis, 'wire_boundary_text_binding':contact,
                        "model_physical_pin": pin.get("physical_pin"), "triangle_glyph": pin.get("triangle"), "output_negated": None,
                        "raw_printed_and_geometry_fields": {k: v for k, v in pin.items() if k not in ("native_evidence", "source_evidence", "evidence", "source_note", "note", "source_review_note", "output_route_audit")}}
                port['literal_text_bindings']=[]
                if bounds_valid and isinstance(pr,int) and isinstance(label,str) and label:
                    for tr in candidate_rows:
                        if not rr<=tr<=rr+node.get('height',6) or not 0<=tr<len(text_lines):continue
                        border=cc if side=='input' else cc+width-1
                        border_char=text_lines[tr][border:border+1]
                        if not border_char or border_char not in '│◺┌┐└┘┼':continue
                        lc=border-len(label) if side=='input' else border+1
                        if text_lines[tr][lc:lc+len(label)]==label:port['literal_text_bindings'].append({'row':tr,'column':lc,'literal':label})
                occupied={(p['row'],p['column']+j) for p in port['literal_text_bindings'] for j in range(len(p['literal']))}
                port['field_recovery_dependencies']=[q for q in repairs_for_page(page) if occupied & {tuple(x) for x in q['covered_cells']}]
                obs["pins"].append(port)
                if connected and side: counts[side] += 1
                if connected is None and side:unknown_counts[side]+=1
                if parsed["physical_pin"] and side: named_counts[side] += 1
                pin_rows.append({"card_type": code, "portion": portion, "observation_id": obs_id, "page": page["page"], "scan_id": page["scan_id"],
                                 "source_id": source_id, "JSON_pointer": port["JSON_pointer"], "direction": side, "printed_label": label, "physical_pin": parsed["physical_pin"],
                                 "numeric_control_prefix": parsed["numeric_prefix"], "drawn_connected_port": connected, "triangle_glyph": pin.get("triangle"), "output_negated": None})
            obs["observed_connected_port_counts"] = {x: counts[x] for x in ("input", "output")}
            obs['ports_with_unknown_connection_counts']={x:unknown_counts[x] for x in ('input','output')}
            obs["observed_named_pin_counts"] = {x: named_counts[x] for x in ("input", "output")}
            obs['distinct_observed_physical_pin_names']={side:sorted({p['physical_pin'] for p in obs['pins'] if p['direction']==side and p['physical_pin']}) for side in ('input','output')}
            card(code)["diagram_observations"].append(obs); depiction_by_page[page["page"]].append(obs)
            observed_rows.append({"card_type": code, "portion": portion, "observation_id": obs_id, "page": page["page"], "scan_id": page["scan_id"], "source_id": source_id,
                                  "JSON_pointer": pointer, "printed_card_portion": literal, "function_literal": node.get("function"), "unit_literal": node.get("unit"),
                                  "location_literal": location, "physical_instance_key": instance_key, "observed_input_connections": counts["input"], "observed_output_connections": counts["output"],
                                  'inputs_connection_unknown':unknown_counts['input'],'outputs_connection_unknown':unknown_counts['output']})
    human = read(args.human_facts); human_code = str(human["card_type"])
    for i, observation in enumerate(human["observations"]):
        ho={"observation_id": f"h{i}", "source_id": human_id, "JSON_pointer": f"/observations/{i}", "raw_observation": observation}
        if observation.get('source_page'):
            ho['matching_diagram_observation_ids']=[o['observation_id'] for o in card(human_code)['diagram_observations'] if o['page']==observation['source_page'] and o['portion_literal']==observation.get('portion')]
        else:
            ho['interpretation_scope']='Specific AP211 physical card membership, not an exhaustive type capability claim'
            ho['matching_listing_observation_ids']=[o['observation_id'] for o in card(human_code)['listing_observations'] if o['board_match_key']=='02B-D1' and o['socket_match_keys']==['D4','D5']]
        card(human_code)["human_observations"].append(ho)
    portion_rows, conflict_rows = [], []
    def variants(obs, key):
        result = defaultdict(list)
        for o in obs:
            value = o.get(key)
            if value not in (None,'') and "�" not in str(value): result[str(value)].append(o["observation_id"])
        rawfield='function' if key=='function_normalized' else 'unit' if key=='unit_code_normalized' else None
        byid={o['observation_id']:o for o in obs}
        return [{"value": k, "observation_ids": v,'text_bound_observation_ids':[oid for oid in v if rawfield and len(byid[oid]['literal_text_bindings'][rawfield])==1],
                 'confidence':'Accepted model literal observations; exact text-binding status kept per observation; native shape not newly verified'} for k, v in sorted(result.items())]
    for code, data in sorted(cards.items()):
        memberships = defaultdict(list); instances = defaultdict(lambda: {"listing_observation_ids": [], "diagram_observation_ids": []})
        for o in data["listing_observations"]:
            listing_pair=set()
            if o['card_width']=='double' and len(o['socket_match_keys'])==1:
                listing_pair=pair_candidates.get((o['board_match_key'],o['socket_match_keys'][0],code),set())
            paired_sockets=list(next(iter(listing_pair))) if len(listing_pair)==1 else o['socket_match_keys']
            key = o["board_match_key"] + ":" + ",".join(paired_sockets)
            instances[key]["listing_observation_ids"].append(o["observation_id"])
            if o["part_number_literal"] is not None and "�" not in str(o["part_number_literal"]): data["full_part_number_facts"].append({"value": str(o["part_number_literal"]), "observation_id": o["observation_id"], "printed_dependency_id": o["printed_dependency_id"],'field_repair_dependencies':o['field_repair_dependencies'],'embedded_repair_dependency_pointers':o['embedded_repair_dependency_pointers']})
            if o['card_width']:data["card_width_facts"].append({"value": o["card_width"], "observation_id": o["observation_id"], "printed_dependency_id": o["printed_dependency_id"], "instance_key": key,'field_repair_dependencies':o['field_repair_dependencies'],'embedded_repair_dependency_pointers':o['embedded_repair_dependency_pointers']})
            for ref in o["references"]:
                for p in ref["readable_portions"]: memberships[p].append({"observation_id": o["observation_id"], "JSON_pointer": ref["JSON_pointer"], "ALD_page": ref["ALD_page_literal"], "instance_key": key})
            for ui,unused in enumerate(o['unused_portion_literals']):
                if isinstance(unused,str) and PORTION.fullmatch(unused): memberships[unused].append({'observation_id':o['observation_id'],'JSON_pointer':o['JSON_pointer']+'/unused_portions/'+str(ui),'unused':True,'instance_key':key})
        for o in data["diagram_observations"]:
            if o["portion_literal"]: memberships.setdefault(o["portion_literal"], [])
            if o["physical_instance_key"]: instances[o["physical_instance_key"]]["diagram_observation_ids"].append(o["observation_id"])
        data["physical_instances"] = [{"instance_key": k, **v} for k, v in sorted(instances.items())]
        data["observed_portions"] = sorted(memberships)
        for p in data["observed_portions"]:
            obs = [o for o in data["diagram_observations"] if o["portion_literal"] == p]
            funcs, units = variants(obs, "function_normalized"), variants(obs, "unit_code_normalized")
            pins = {side: defaultdict(list) for side in ("input", "output")}
            counts = defaultdict(list)
            for o in obs:
                counts[json.dumps(o["observed_connected_port_counts"], sort_keys=True)].append(o["observation_id"])
                for port in o["pins"]:
                    if port["direction"] in pins and port["physical_pin"]:
                        pins[port["direction"]][port["physical_pin"]].append({"observation_id": o["observation_id"], "JSON_pointer": port["JSON_pointer"]})
            portiondata = {"portion": p, "function_facts": funcs, "unit_code_facts": units, "listing_memberships": memberships[p],
                           "observed_pin_names": {side: [{"value": k, "observations": v} for k, v in sorted(names.items())] for side, names in pins.items()},
                           "observed_connected_count_variants": [{"value": json.loads(k), "observation_ids": v} for k, v in counts.items()],
                           "physical_pinout_complete": False, "diagram_observation_ids": [o["observation_id"] for o in obs], "conflicts": []}
            portiondata['human_confirmed_facts']=[{'human_observation_id':h['observation_id'],'source_id':h['source_id'],'JSON_pointer':h['JSON_pointer'],
                                                  'value':h['raw_observation'],'matching_diagram_observation_ids':h.get('matching_diagram_observation_ids',[])}
                                                 for h in data['human_observations'] if h['raw_observation'].get('portion')==p]
            for role, facts in (("function", funcs), ("unit", units)):
                if len(facts) > 1:
                    conflict = {"subject": code + p, "field": role, "alternatives": facts, "manual_review_required": True, "reason": "Readable accepted literal alternatives; no majority selection"}
                    portiondata["conflicts"].append(conflict); conflict_rows.append(conflict)
            for name in set(pins["input"]) & set(pins["output"]):
                conflict = {"subject": code + p, "field": "pin direction", "pin": name, "alternatives": ["input", "output"], "manual_review_required": True, "reason": "Same physical pin observed on opposite logical sides; no silent direction inference"}
                portiondata["conflicts"].append(conflict); conflict_rows.append(conflict)
            data["portions"][p] = portiondata
            portion_rows.append({"card_type": code, "portion": p, "function_variants": [f["value"] for f in funcs], "unit_variants": [f["value"] for f in units],
                                 "diagram_observations": len(obs), "physical_instances": len({o["physical_instance_key"] for o in obs if o["physical_instance_key"]}),
                                 "observed_input_pin_names": list(sorted(pins["input"])), "observed_output_pin_names": list(sorted(pins["output"])), "physical_pinout_complete": False, "conflicts": len(portiondata["conflicts"])})
        for role, facts in (("full part number", data["full_part_number_facts"]), ("card width", data["card_width_facts"])):
            values = sorted({x["value"] for x in facts})
            if len(values) > 1:
                conflict = {"subject": code, "field": role, "alternatives": values, "facts": facts, "manual_review_required": True, "reason": "Distinct accepted listing assertions remain separate"}
                data["conflicts"].append(conflict); conflict_rows.append(conflict)
        write(out / "json/Card types" / (code + ".json"), data)
    report = question_report(args.question_manifest, pages, cards, depiction_by_page, repo, post_answer_ids) if args.question_manifest else None
    if report: write(out / "notes/Card types/Question candidates.json", report)
    index = {"schema_version": VERSION, "snapshot_utc": export.get("created_utc"), "sources": sources, "pages": pages,
             'function_normalization':{'raw_literals_preserved':True,'surrounding_layout_spaces_removed_from_normalized_values_only':True,'internal_whitespace_collapsed':True,
                                       'asterisk_equivalence':'ASCII * and previously approved U+2732 ✲','semantic_token_corrections_applied_by_builder':False,'human_authorities':normalization_authorities},
             "card_types": [{"card_type": c, "file": "json/Card types/" + c + ".json", "diagram_observations": len(d["diagram_observations"]), "listing_observations": len(d["listing_observations"]),
                             "observed_portions": len(d["observed_portions"]), "located_physical_instances": len(d["physical_instances"]), "conflicts": len(d["conflicts"]) + sum(len(p["conflicts"]) for p in d["portions"].values())} for c, d in sorted(cards.items())]}
    write(out / "json/Card types/Card type index.json", index)
    csvwrite(out / "csv/Card types/Card portions.csv", list(portion_rows[0]) if portion_rows else [], portion_rows)
    csvwrite(out / "csv/Card types/Card observations.csv", list(observed_rows[0]) if observed_rows else [], observed_rows)
    csvwrite(out / "csv/Card types/Pin observations.csv", list(pin_rows[0]) if pin_rows else [], pin_rows)
    write(out / "notes/Card types/Conflicts.json", conflict_rows)
    # Detect concurrent snapshot changes rather than publish a mixed view.
    for path, before in initial_hashes.items():
        if sha(path) != before: raise ValueError("Input changed during build: " + path)
    for source in sources.values():
        if not source.get("external_input") and not source.get('source_archive') and sha(repo / source["path"]) != source["sha256"]:
            raise ValueError("Accepted file changed during build: " + source["path"])
    for path, stat in original_stats.items():
        p=Path(path)
        if (p.stat().st_size,p.stat().st_mtime_ns)!=stat:raise ValueError('Original TIFF changed during read-only build: '+path)
    write(out / 'notes/Card types/Coverage exclusions.json',coverage_ledger)
    original_registry={"status":"Build-time read-only observed original-source bindings; not retroactive native acceptance","sources":{k:v for k,v in sources.items() if v.get('source_archive')}}
    write(out / 'notes/Card types/Original source registry.json',original_registry)
    toolcopy=out/'tools/references/build_card_type_database.py';toolcopy.parent.mkdir(parents=True,exist_ok=True);toolcopy.write_bytes(Path(__file__).read_bytes())
    counts = {"accepted_text_pages_bound": len(pages), "accepted_content_files_bound": len(manifest['files']), "original_TIFF_hashes_bound":len(original_stats), "card_types": len(cards), "diagram_observations": len(observed_rows),
              "listing_observations": len(listing_records), "pin_observations": len(pin_rows), "card_portions": len(portion_rows), "conflicts": len(conflict_rows), "skipped": dict(skipped)}
    build_manifest = {"schema_version": VERSION, "status": "PRIVATE; awaits independent review", "created_utc": datetime.now(timezone.utc).isoformat(), "snapshot_utc": export.get("created_utc"),
                      "input_manifests": [{"path": "notes/Reviewed export provenance.json", "sha256": sha(export_path)}, {"path": "notes/Content data manifest.json", "sha256": sha(manifest_path)}],
                      "human_facts_sha256": sha(args.human_facts), 'additional_recorded_answer_inputs':post_answer_inputs, "builder_sha256": sha(Path(__file__)), "counts": counts, "question_report_counts": report["counts"] if report else None,
                      "original_TIFF_bytes_rehashed": True, "original_source_scope": "Every accepted original TIFF read-hashed and checked against available accepted model declarations; sources never modified",
                      "outputs": [{"path": p.relative_to(out).as_posix(), "sha256": sha(p)} for p in sorted(out.rglob("*")) if p.is_file() and p.name not in ("Build manifest.json", "Database notes.txt")]}
    notes = "Card type reference database\n\nPRIVATE, pending independent review. Snapshot: " + str(export.get("created_utc")) + "\n\n" + json.dumps(counts, ensure_ascii=False, indent=2) + "\n\n" + (
        "All accepted text and content-file hashes are verified before and after extraction.\n"
        "Observations retain source IDs and exact JSON pointers. Repeated depictions are not distinct physical cards.\n"
        "Shared A1 records retain the printed dependency of the original accepted listing.\n"
        "Observed portion membership is an instance-specific fact; the card-type union is not exhaustive.\n"
        "Connected counts require reviewed drawn-wire flags or actual text wire/border intersections; other ports remain connection unknown. Null labels remain unprinted.\n"
        "Readable function/unit/part/width alternatives remain conflicts. No majority vote is used.\n"
        "Triangles, stars and control prefixes remain literal annotations; only explicit human evidence asserts inversion.\n"
        "Derived model card/portion fields never replace a damaged printed identity for card-based question matching.\n"
        "Question candidates are proposals only. No question, workbook, canonical transcription or source scan is changed.\n"
        "AP211 direct human facts are preserved separately; a final build must follow its accepted corrected snapshot.\n")
    (out / "notes/Card types/Database notes.txt").write_text(notes, encoding="utf-8")
    build_manifest['outputs']=[{'path':p.relative_to(out).as_posix(),'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='Build manifest.json']
    write(out / "notes/Card types/Build manifest.json", build_manifest)
    print(json.dumps({"output_root": str(out), "counts": counts, "question_report_counts": report["counts"] if report else None}, ensure_ascii=False))

def question_report(path, pages, cards, bypage, repo, recorded_answer_ids=()):
    manifest = read(path); proposals, held, excluded = [], [], Counter()
    for q in manifest["questions"]:
        if q['id'] in recorded_answer_ids:
            excluded['Additional human answer already recorded; not reopened']+=1;continue
        kind = q.get("_kind"); mask = q.get("current_reading", "")
        if kind is None:
            prompt=q.get('question','').lower()
            if re.search(r'printed function\b|complete function\b|function (?:label|text)\b',prompt):kind='function'
            elif re.search(r'unit (?:designation|code|label)\b',prompt):kind='unit code'
            elif re.search(r'pin (?:label|designation)\b',prompt):kind='pin label'
        if kind not in ("function", "unit code", "pin", "pin label", "output pin label") or "�" not in mask:
            excluded["outside unreadable function/unit/pin scope"] += 1; continue
        candidates = bypage.get(q["page"], [])
        if q.get('source_scan_id'):candidates=[x for x in candidates if x['scan_id']==str(q['source_scan_id'])]
        match = re.search(r"block ([A-Z0-9_]+)(?: |\(|/)", q.get("location", ""),re.IGNORECASE)
        if not match: excluded["no unambiguous node identifier binding"] += 1; continue
        target = [x for x in candidates if x["node_identifier"] == match[1] or x["printed_node_identifier"] == match[1]]
        grid=re.search(r'(?:grid|position)\s+([0-9][A-Z])\b',q.get('location',''),re.IGNORECASE)
        if len(target)>1 and grid:target=[x for x in target if x.get('station')==grid[1]]
        if len(target) != 1: excluded["ambiguous/missing current accepted node"] += 1; continue
        target = target[0]
        if not target["identity_complete"] or len(target['literal_text_bindings']['printed_card_portion'])!=1:
            excluded["printed card type/portion not completely readable and uniquely text-bound"] += 1; continue
        page = pages[target["scan_id"]]; lines = (repo / page["text_path"]).read_text(encoding="utf-8-sig").splitlines()
        r, c = q.get("row"), q.get("column")
        if not isinstance(r, int) or not isinstance(c, int) or r >= len(lines) or lines[r][c:c+len(mask)] != mask:
            excluded["question no longer matches current accepted UTF-8 cells"] += 1; continue
        code, portion = target["card_type_literal"], target["portion_literal"]
        others = [x for x in cards[code]["diagram_observations"] if x["portion_literal"] == portion and x["scan_id"] != target["scan_id"] and len(x['literal_text_bindings']['printed_card_portion'])==1]
        field = "function_normalized" if kind == "function" else "unit_code_normalized" if kind == "unit code" else None
        values, conflicts, basis = defaultdict(list), [], ""
        target_port = None
        if field:
            if norm(target.get(field)) != norm(mask): excluded["question/model literal mismatch"] += 1; continue
            for o in others:
                value = o.get(field)
                rawfield='function' if kind=='function' else 'unit'
                if value and "�" not in value and len(o['literal_text_bindings'][rawfield])==1:
                    values[value].append({"observation_id": o["observation_id"], "source_id": o["source_id"], "JSON_pointer": o["JSON_pointer"] + ("/function" if kind == "function" else "/unit"), "page": o["page"], "physical_instance_key": o["physical_instance_key"],
                                          'literal_text_binding':o['literal_text_bindings'][rawfield], 'field_recovery_dependencies':o['field_recovery_dependencies'][rawfield]+o['field_recovery_dependencies']['printed_card_portion'],
                                          'embedded_history_dependency_pointers':o['embedded_history_dependency_pointers']})
            if len(values) > 1: conflicts = list(values)
            role='function' if kind=='function' else 'unit'
            conflicts += [x for x in cards[code]['portions'][portion]['conflicts'] if x['field']==role]
            basis = "Exact readable card type and portion; independent accepted pages; all surviving characters preserved; readable alternatives prevent a firm answer"
        else:
            possible = []
            for p in target["pins"]:
                raw = str(p.get("printed_label_literal") or "")
                if raw != mask: continue
                rawrow = p["raw_printed_and_geometry_fields"].get("row")
                if rawrow == r or target["box_bounds"].get("row", -10000) + (rawrow or 0) == r: possible.append(p)
            if len(possible) != 1 or possible[0]["direction"] not in ("input", "output"):
                excluded["unambiguous pin row/side not established"] += 1; continue
            target_port = possible[0]; side = target_port["direction"]
            prefix = re.match(r"^([0-9]*)([A-Z�][0-9�]{2})([✲*]?)$", mask)
            if not prefix: excluded["pin mask includes unresolved control/terminal structure"] += 1; continue
            occupied = {p["physical_pin"] for p in target["pins"] if p["direction"] == side and p["physical_pin"]}
            portionfacts = cards[code]["portions"][portion]
            conflicts = [x for x in portionfacts["conflicts"] if x["field"] in ("function", "unit", "pin direction")]
            for o in others:
                for p in o["pins"]:
                    name = p["physical_pin"]
                    if p["direction"] == side and name and name not in occupied and len(p['literal_text_bindings'])==1:
                        value = prefix[1] + name + norm(prefix[3])
                        values[value].append({"observation_id": o["observation_id"], "source_id": o["source_id"], "JSON_pointer": p["JSON_pointer"], "page": o["page"], "physical_instance_key": o["physical_instance_key"],
                                              'literal_text_binding':p['literal_text_bindings'],'field_recovery_dependencies':p['field_recovery_dependencies']+o['field_recovery_dependencies']['printed_card_portion'],
                                              'embedded_history_dependency_pointers':o['embedded_history_dependency_pointers']})
            basis = "Known target pin side and exact readable card/portion; independent observed pin labels only; existing readable same-side pins excluded; full physical pinout remains unknown"
        matches = sorted(x for x in values if compatible(mask, x))
        entry = {"question_id": q["id"], "page": q["page"], "scan_id": target["scan_id"], "kind": kind, "row": r, "column": c,
                 "current_reading": mask, "card_type": code, "portion": portion, "target_observation_id": target["observation_id"],
                 "target_JSON_pointer": target_port["JSON_pointer"] if target_port else target["JSON_pointer"], "compatible_candidates": matches,
                 "readable_conflicts": conflicts, "basis": basis, "supporting_observations": {x: values[x] for x in matches}, "application_authorized": False}
        entry['incompatible_observed_values']=[{'value':x,'observation_ids':sorted({o['observation_id'] for o in values[x]}),'reason':'Does not preserve the current readable characters/token pattern; no replacement is authorized'} for x in sorted(values) if x not in matches]
        if len(matches) == 1 and not conflicts:
            entry["best_guess"] = canvas_candidate(mask,matches[0])
            entry['normalized_semantic_candidate']=matches[0]
            if entry['best_guess'] is None:
                entry['confidence']='Manual; exact original canvas pattern cannot be preserved';held.append(entry);continue
            entry["confidence"] = "Tentative; incomplete pinout and recovery-dependency review required" if target_port else "Tentative; unique compatible observation, recovery-dependency review required"
            proposals.append(entry)
        else:
            entry["confidence"] = "Manual; conflicting evidence" if conflicts else "Manual; no unique compatible observation"
            held.append(entry)
    return {"status": "Read-only proposals; no automatic closures", "question_manifest_sha256": sha(path), "counts": {"questions_examined": len(manifest["questions"]), "unique_compatible_proposals": len(proposals), "held": len(held), "excluded": dict(excluded)},
            "proposals": proposals, "held": held}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--human-facts", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path, help="Original TIFF archive; read only")
    parser.add_argument('--function-authority',action='append',type=Path,default=[],help='Immutable direct human function authority, repeatable; retained in notes')
    parser.add_argument('--additional-answer-ledger',action='append',type=Path,default=[],help='Immutable post-workbook recorded answers, repeatable; retained as repair dependencies')
    parser.add_argument("--question-manifest", type=Path)
    build(parser.parse_args())
