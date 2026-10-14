"""Independent current-cell, coverage, binding and candidate checks. Private audit only."""
import csv, hashlib, importlib.util, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
REPO = ROOT / 'ibm360ald'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def binding(p): return {'path': str(p), 'sha256': sha(p)}
def resolve(p):
    p = Path(p)
    return p if p.is_absolute() else REPO / p
def compatible(a, b):
    return len(a) == len(b) and all(x == '\ufffd' or y == '\ufffd' or x == y for x, y in zip(a, b))

def main():
    inv = read(OUT/'Endpoint inventory.json')
    page_map = inv['pages'] if isinstance(inv['pages'],dict) else {p['source_scan_id']:p for p in inv['pages']}
    inv['pages'] = list(page_map.values())
    for d in inv['endpoints']:
        if 'full_row' not in d:
            d['full_row'] = page_map[d['source_scan_id']]['literal_rows'][d['literal_row_evidence']]
    matches = read(OUT/'A1 endpoint matching results.json')
    meta = read(OUT/'Endpoint tool metadata.json')
    export = read(ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json')
    records = read(REPO/'notes/Repository records manifest.json')
    owned = {x['path'].replace('\\','/'):x['sha256'] for x in records['files']}
    issued = read(ROOT/'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v4.json')
    overlay = read(ROOT/'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/Pending inventory after V4.json')
    checks = {}; failures = []
    def check(name, passed):
        checks[name] = bool(passed)
        if not passed: failures.append(name)
    check('all_2307_accepted_scans', len(inv['pages']) == 2307 and len({x['source_scan_id'] for x in inv['pages']}) == 2307)
    check('exact_export_scan_set', {p['source_scan_id'] for p in inv['pages']} == {str(e['source_scan_id']) for e in export['exported']})
    check('export_current_accepted', export['bytewise_copy_verified'] and not export.get('export_in_progress'))
    lines = {}; binds_ok = True
    for page in inv['pages']:
        for kind in ['text','model']:
            b = page['binding'][kind]
            if b:
                p = resolve(b['path']); rel = p.relative_to(REPO).as_posix()
                binds_ok &= sha(p) == b['sha256'] == owned[rel]
                if kind == 'text': lines[page['source_scan_id']] = p.read_text(encoding='utf-8').splitlines()
    check('all_current_repository_TXT_model_hashes_owned', binds_ok)
    check('metadata_builder_current', sha(OUT/'build_endpoint_reference_index.py') == meta['builder']['sha256'])
    check('metadata_outputs_current', all(sha(resolve_output(x['path'])) == x['sha256'] for x in meta['outputs']))
    check('all_snapshot_inputs_current', all(sha(resolve_input(x['path'])) == x['sha256'] for x in inv['inputs']))
    seen = set(); exact = True; units = True; pins = True
    for d in inv['endpoints']:
        key = (d['source_scan_id'], d['row'], d['column']); seen.add(key)
        l = lines[key[0]][key[1]]
        exact &= l == d['full_row'] and l[key[2]:key[2]+len(d['raw_token'])] == d['raw_token'] and d['id'] == ':'.join(map(str,key))
        pins &= d['raw_token'].endswith(d['pin'])
        if d['unit_resolution'] == 'literal_full_unit': units &= d['board'] == d['raw_board']
        elif d['unit_resolution'] == 'direct_human_abbreviation': units &= d['prefix'] in 'ABCEKL' and d['board'] == '02'+d['raw_board'] and bool(d['unit_rule_receipt'])
        else: units &= d['board'] is None and d['unit'] is None
    check('every_endpoint_exact_current_cell_and_stable_ID', exact)
    compact_ok = True
    for sid,p in page_map.items():
        for r,line in p.get('literal_rows',{}).items(): compact_ok &= lines[sid][int(r)] == line
        for hid,h in p.get('governing_headers',{}).items():
            compact_ok &= hid == str(h['row'])+':'+str(h['column']) and lines[sid][h['row']] == h['excerpt'] and lines[sid][h['row']][h['column']:h['column']+len(h['raw_code'])] == h['raw_code']
            for proof in h.get('support',{}).get('literal_body_proof',[]): compact_ok &= lines[sid][proof['row']][proof['column']:proof['column']+len(proof['excerpt'])] == proof['excerpt']
    for d in inv['endpoints']:
        p=page_map[d['source_scan_id']];hid=d.get('governing_header_id')
        if hid: compact_ok &= p['governing_headers'][hid]['raw_code'] == d['governing_raw_code']
        elif d.get('governing_raw_code'): compact_ok=False
    check('compact_source_provenance_rows_heading_links_exact',compact_ok)
    check('matches_bound_to_exact_compact_inventory',matches.get('endpoint_inventory',{}).get('sha256') == sha(OUT/'Endpoint inventory.json'))
    check('endpoint_IDs_unique', len(seen) == len(inv['endpoints']))
    check('explicit_units_and_raw_tokens_preserved_only_six_human_expansions', units)
    check('pins_preserved_including_B05', pins)
    check('socket_only_terminal_T_B_normalization', all(d['socket_normalized'] == re.sub(r'(?<=[0-9])[TB]$','',d['socket']) for d in inv['endpoints']))
    # Independently enumerate complete physical endpoint token locations.
    token = re.compile(r'(?<![A-Z0-9\ufffd])(?:[0-9A-Z\ufffd]{2})?[A-Z\ufffd]-[A-Z\ufffd][0-9\ufffd][A-Z\ufffd][0-9\ufffd]{1,2}[TB]?[A-Z\ufffd][A-Z0-9\ufffd]{2}(?![A-Z0-9\ufffd])')
    actual = {(sid,r,m.start()) for sid, ls in lines.items() for r,l in enumerate(ls) for m in token.finditer(l)}
    check('all_complete_literal_endpoint_tokens_covered', actual == seen)
    with (OUT/'Endpoint inventory.csv').open(encoding='utf-8-sig',newline='') as f: csvrows = list(csv.DictReader(f))
    check('CSV_same_ID_order_and_literal_fields', len(csvrows) == len(inv['endpoints']) and all(c['id'] == d['id'] and c['raw_endpoint'] == d['raw_endpoint'] and c['full_row'] == d['full_row'] and c['pin'] == d['pin'] for c,d in zip(csvrows,inv['endpoints'])))
    closed = {x['id'] for x in overlay['source_derived_resolutions']}
    qmap = {x['id']:x for x in issued['questions'] if x['group']=='A1' and x['id'] not in closed}
    check('exact_11_prior_WA_MC743_closures_excluded', len(closed) == 11 and set(matches['excluded_already_resolved_ids']) == closed)
    check('all_16_remaining_A1_questions_once', len(matches['results']) == len(qmap) == 16 and {x['id'] for x in matches['results']} == set(qmap))
    check('issued_question_records_answers_preserved', all(x['original_issued_question'] == qmap[x['id']] and x['Answer']=='' and x['issued_V4_changed'] is False for x in matches['results']))
    native = read(OUT/'Independent native High proposal evidence.json')
    native_ids = {x['id']:x['candidate'] for x in native['proposals']}
    candidate_checks = []
    for q in matches['results']:
        if q['confidence'] != 'High': continue
        t=q['target']; possible=[]
        for d in inv['endpoints']:
            raw = d['raw_board']
            if len(d['prefix']) == 1 and (d['prefix'] in 'ABCEKL' or d['prefix']=='\ufffd'): raw='02'+raw
            if compatible(raw,t['board']) and compatible(d['socket_normalized'],t['socket_normalized']) and compatible(d['pin'],t['pin']): possible.append(d)
        governed = [d for d in possible if d['eligible_exact_match'] and compatible(q['current_reading'],d['governing_full_reference'])]
        competitors = [d for d in possible if not d['eligible_exact_match'] and (not d.get('governing_reference_pattern') or compatible(q['current_reading'],d['governing_reference_pattern']))]
        vals = {d['governing_full_reference'] for d in governed}
        candidate_checks.append({'id':q['id'],'candidate':q['candidate'],'possible_physical_endpoint_ids':[d['id'] for d in possible],'uncertain_competitor_ids':[d['id'] for d in competitors],'passed':vals == {q['candidate']} and not competitors and t['exact_physical_key_verified'] and native_ids.get(q['id']) == q['candidate']})
    check('all_High_unique_even_with_damaged_physical_masks_and_native_evidence', bool(candidate_checks) and all(x['passed'] for x in candidate_checks))
    native_current = all(sha(Path(b['path'])) == b['sha256'] for q in native['proposals'] for s in q['source_bindings'] for k,b in s.items() if k in ['source','current_text','current_repository_model','current_canonical_model'] and b)
    check('native_proposal_source_text_model_bindings_current', native_current)
    result={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,'failures':failures,'counts':inv['counts'],'inputs':[binding(OUT/n) for n in ['build_endpoint_reference_index.py','Endpoint inventory.json','Endpoint inventory.csv','A1 endpoint matching results.json','Endpoint tool metadata.json','Independent native High proposal evidence.json']],'High_proposals':candidate_checks,'scope':'Current accepted literal endpoint inventory; source-backed High proposals; no canonical/model/workbook mutations. Algorithm edge-case fixture review is supplied separately.'}
    path=OUT/'Independent endpoint coverage audit.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'audit':binding(path),'passed':result['passed'],'failures':failures,'counts':inv['counts']}))

def resolve_output(p):
    p=Path(p);return p if p.is_absolute() else OUT/p.name
def resolve_input(p):
    p=Path(p);return p if p.is_absolute() else ROOT/p

if __name__ == '__main__': main()
