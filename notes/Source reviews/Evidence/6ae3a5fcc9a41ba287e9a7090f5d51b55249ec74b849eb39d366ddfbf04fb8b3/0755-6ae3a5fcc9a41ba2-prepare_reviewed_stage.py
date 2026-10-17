"""Merge explicit peer-reviewed pin findings into a bounded private stage intent.

This prepares new files only. It does not infer contacts, publish corrections,
edit TIFFs, or modify an accepted working/repository transcription.
"""
from pathlib import Path
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json, re, sys
from PIL import Image

ROOT = Path('D:/Github/IBM360')
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ibm360ald/tools/reviews'))
import source_review as sr

def need(ok, message):
    if not ok:
        raise ValueError(message)

def read(path):
    return sr.read_json(path)

def cases(doc):
    return doc.get('cases', doc.get('findings', []))

def meaningful_cells(edits):
    result = {}
    for edit in edits:
        need(len(edit['before']) == len(edit['after']), 'Unequal TXT edit widths')
        for offset, (before, after) in enumerate(zip(edit['before'], edit['after'])):
            if before == after:
                continue
            key = (edit['row'], edit['column'] + offset)
            value = (before, after)
            need(key not in result or result[key] == value, 'Conflicting TXT edits')
            result[key] = value
    return result

def patch_identity(patch):
    return {k: patch.get(k) for k in ('op', 'pointer', 'before', 'after')}

def main():
    selection_path = BASE / 'Final reviewed selection.json'
    selection = read(selection_path)
    need(selection.get('complete') is True, 'Peer review selection is incomplete')
    intent_path = BASE / 'Intent.json'
    need(not intent_path.exists(), 'Do not overwrite a frozen intent')
    pages, requests, evidence = {}, {}, {}

    def add_evidence(link):
        path, raw = sr.checked(link, BASE)
        evidence[path] = sr.binding(path)

    add_evidence(sr.binding(selection_path))
    for group in (1, 2, 3):
        path = BASE / f'Group {group} requests.json'
        add_evidence(sr.binding(path))
        for page in read(path)['pages']:
            need(page['page'] not in pages, 'Non-disjoint group pages')
            pages[page['page']] = page
            for case in page['cases']:
                need(case['case_id'] not in requests, 'Duplicate request')
                requests[case['case_id']] = (page, case)
    need(len(requests) == 629, 'Changed request inventory')
    effective = []
    for group in selection['groups']:
        add_evidence(group['findings'])
        for proof in group.get('evidence', []):
            add_evidence(proof)
        effective.extend(cases(read(group['findings']['path'])))
    need(len(effective) == 629 and {c['case_id'] for c in effective} == set(requests),
         'Final findings must cover every request exactly once')
    need(len({c['case_id'] for c in effective}) == 629, 'Duplicate final cases')
    changes = defaultdict(lambda: {'cases': [], 'patches': {}, 'cells': {}, 'evidence': {}})
    outcome = []
    for case in effective:
        cid = case['case_id']
        page, request = requests[cid]
        need(case['page'] == page['page'], 'Wrong page in final case ' + cid)
        for binding in (page['model'], page['text']):
            sr.checked(binding, BASE)
        accepted = case.get('status', '').startswith(('confident', 'resolved'))
        edits = case.get('text_edits', [])
        patches = case.get('json_patches', [])
        need(accepted or not (edits or patches), 'Unresolved case has edits ' + cid)
        if accepted:
            need(re.fullmatch(r'[BDGJ](?:0[2-9]|1[0-3])', str(case['proposed_contact'])),
                 'Invalid proposed physical contact ' + cid)
        contexts = case.get('context_corrections', [])
        if contexts:
            need(case.get('context_corrections_independently_accepted') is True,
                 'Context identity correction lacks peer acceptance ' + cid)
        plans = [{'text_edits': edits, 'json_patches': patches}] + contexts
        outcome_case = {'case_id': cid, 'page': case['page'], 'status': case['status'],
                        'node': request['node'].get('id'), 'node_pointer': request['audit_flag']['node_pointer'],
                        'pin_index': request['audit_flag']['pin_index'],
                        'old_contact': request['audit_flag']['physical_contact'],
                        'proposed_contact': case.get('proposed_contact'),
                        'best_guess': case.get('best_guess'),
                        'native_crop': case.get('source_crop', case.get('native_crop')),
                        'note': case.get('note', ''),
                        'pin_correction_settled': accepted,
                        'context_identity_change': bool(contexts)}
        if not any(p.get('text_edits') or p.get('json_patches') for p in plans):
            outcome.append(outcome_case | {'applied': False})
            continue
        change = changes[case['page']]
        change['cases'].append(cid)
        for plan in plans:
            for patch in plan.get('json_patches', []):
                p = deepcopy(patch)
                p['pointer'] = p.pop('path', p.get('pointer'))
                p.setdefault('op', 'replace')
                need(isinstance(p['pointer'], str) and p['pointer'].startswith('/'), 'Bad JSON pointer')
                old = change['patches'].get(p['pointer'])
                need(old is None or patch_identity(old) == patch_identity(p), 'Conflicting JSON patch')
                change['patches'][p['pointer']] = p
            for key, value in meaningful_cells(plan.get('text_edits', [])).items():
                need(key not in change['cells'] or change['cells'][key] == value, 'Conflicting TXT cell')
                change['cells'][key] = value
        crop = case.get('source_crop', case.get('native_crop'))
        need(isinstance(crop, dict), 'Missing native source crop ' + cid)
        add_evidence(crop)
        change['evidence'][crop['path']] = sr.binding(crop['path'])
        source = case.get('source')
        if source:
            need(Path(source['path']).resolve() == Path(page['source_TIFF']).resolve(), 'Wrong TIFF ' + cid)
        outcome.append(outcome_case | {'applied': True})

    for extra in selection.get('evidence', []):
        add_evidence(extra)
    probe = read(BASE / 'Predecessor preview configuration probe.json')
    configs = {tuple(c['dimensions']): c['configuration'] for c in probe['configurations']}
    records = []
    for name, change in sorted(changes.items()):
        page = pages[name]
        txt = Path(page['working_text'])
        need(txt.read_bytes() == Path(page['text']['path']).read_bytes(), 'Working TXT differs ' + name)
        model = txt.with_suffix('.json')
        need(model.read_bytes() == Path(page['model']['path']).read_bytes(), 'Working JSON differs ' + name)
        notes = txt.with_name(txt.stem + ' review notes.txt')
        candidates = [txt.with_name(txt.stem + suffix) for suffix in (' JuliaMono preview.png', ' preview.png', '.png')]
        preview = next((p for p in candidates if p.exists()), None)
        need(preview is not None, 'Missing explicit preview preimage ' + name)
        dimensions = Image.open(preview).size
        need(dimensions in configs, 'Unrecognized preview dimensions ' + name)
        config = deepcopy(configs[dimensions])
        cells = [{'row': row, 'column': col, 'before': value[0], 'after': value[1]}
                 for (row, col), value in sorted(change['cells'].items())]
        patches = list(change['patches'].values())
        model_before = read(model)
        after_txt = sr.patch_text(txt.read_bytes(), cells, {'width': 245, 'height': 103})
        # No contact-coordinates, primary-function, node order or layout edits.
        for patch in patches:
            need(not re.search(r'/pins/\d+/(row|point|absolute_row|absolute_point)(/|$)', patch['pointer']),
                 'Out-of-scope pin coordinate change ' + name)
        notes_append = ('NATIVE PIN LETTER REVIEW 2026-10-16\n'
                        'Source-bound visual review with independent peer checks. Cases: '
                        + ', '.join(change['cases']) + '.\n'
                        'Only the explicitly resolved contact labels, their active data mirrors, '
                        'and separately accepted identity context are corrected. Printed control prefixes, '
                        'asterisks, wedges, wiring, grid coordinates and historical observations are retained.\n'
                        + '\n'.join(c['case_id'] + ': ' + str(c.get('old_contact', '')) + ' → '
                                    + str(c.get('proposed_contact', '')) for c in outcome
                                    if c['page'] == name and c['applied']))
        # These top-level fields describe current derivative assets. Historical
        # nested acceptance receipts are deliberately not rewritten.
        current_hashes = {
            'transcription_sha256': sr.digest(after_txt),
            'rendered_text_sha256': sr.digest(after_txt),
            'review_notes_sha256': sr.digest(sr.append_note(notes.read_bytes(), notes_append)),
        }
        if 'preview_sha256' in model_before:
            current_hashes['preview_sha256'] = sr.digest(sr.render_preview(after_txt, config, BASE)) if cells else sr.digest(preview.read_bytes())
        for key, value in current_hashes.items():
            if key in model_before and model_before[key] != value:
                patches.append({'op': 'replace', 'pointer': '/' + key,
                                'before': model_before[key], 'after': value,
                                'reason': 'Current derivative digest; nested historical receipts are retained'})
        model_after = sr.patch_model(model_before, patches)
        need(not sr.validate_pin_edits(model_before, model_after, {'json_patches': patches, 'evidence': list(change['evidence'].values())}),
             'Pin annotation mirror guard failed ' + name)
        records.append({'page': name, 'model_schema': 'ald-page-nodes-v1',
                        'source': sr.binding(page['source_TIFF']),
                        'prior_quartet': {k: sr.binding(p) for k, p in
                                          [('txt', txt), ('json', model), ('notes', notes), ('preview', preview)]},
                        'grid': {'width': 245, 'height': 103}, 'cell_edits': cells,
                        'json_patches': patches, 'notes_append': notes_append,
                        'preview_config': config, 'evidence': list(change['evidence'].values())})
    receipt = {'schema': 'pin-letter-final-review-merge-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
               'passed': True, 'source_changes_applied': False, 'request_count': len(requests),
               'status_counts': dict(Counter(c['status'] for c in outcome)),
               'changed_pages': len(records), 'cases_with_changes': sum(c['applied'] for c in outcome),
               'settled_pin_corrections': sum(c['pin_correction_settled'] for c in outcome),
               'meaningful_text_cells': sum(len(r['cell_edits']) for r in records),
               'json_patches': sum(len(r['json_patches']) for r in records), 'cases': outcome}
    sr.atomic_write(BASE / 'Final review merge.json', sr.encode(receipt))
    add_evidence(sr.binding(BASE / 'Final review merge.json'))
    add_evidence(sr.binding(Path(__file__)))
    intent = {'schema': 'source-review-intent-v1', 'review_id': 'native-pin-letter-629-20261016',
              'target_root': str(ROOT / 'ALD_Visual_Transcriptions'),
              'unresolved_questions': [],
              'scope_note': 'Only settled corrections are staged. Unresolved occurrences remain explicitly unchanged in Final review merge.json.',
              'evidence': list(evidence.values()), 'pages': records}
    sr.atomic_write(intent_path, sr.encode(intent))
    print(json.dumps({k: v for k, v in receipt.items() if k != 'cases'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
