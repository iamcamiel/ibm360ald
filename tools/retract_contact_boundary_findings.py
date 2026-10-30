#!/usr/bin/env python3
"""Retract obsolete inside-slot findings for bends exactly at a pin contact.

Dry-run by default; --apply saves exact backups and a maintenance receipt.
Genuine inside-slot bends and every other finding are retained. The renderer
supplies the horizontal pin stub, so a route may arrive vertically at contact.
"""
import argparse
import copy
import json
from pathlib import Path

from ald_json_tools.pin_annotations import normalize_annotation_leads
from page_maintenance import apply_changes, content_digest, encode, models, review, writer_lock

OLD_REASON = 'A bend lies inside the fixed three-character pin slot; moving it requires separate layout review'
LETTERS = 'ABCDEFGHJKLMN'
AUTHORITY = 'Human correction: bends exactly at the new contact cell are ordinary pin connections; the renderer supplies the horizontal pin stub.'


def boundary_evidence(data, details, hold):
    """Accept only the exact old reason and independently identifiable contact."""
    if hold.get('reason') != OLD_REASON:
        return None
    parts = hold.get('terminal', '').split('/')
    if len(parts) != 5 or parts[0] != 'blocks' or parts[2] != 'pins':
        return None
    _, serial, _, side, line = parts
    blocks = [b for b in data['blocks'] if b['serial'] == serial]
    if len(blocks) != 1:
        return None
    block = blocks[0]
    pins = [p for p in block['pins'] if p['side'] == side and str(p['line']) == line]
    if len(pins) != 1:
        return None
    node, pin = hold['terminal'], pins[0]
    owners = [n for n in data['nets'] if node in n['nodes']]
    if len(owners) != 1 or owners[0]['nodes'].count(node) != 1 or owners[0]['net number'] != hold.get('net'):
        return None
    net = owners[0]
    marks = [a for a in net.get('annotations', []) if a.get('at') == node]
    if len(marks) > 1:
        return None
    number = pin.get('pin', '')
    if isinstance(number, str) and number and len(number) != 3:
        return None
    if number is None:
        masks = [u.get('visible text', '') for u in details.get('uncertainties', [])
                 if u.get('status') == 'unresolved' and u.get('field') == node + '/pin']
        number = masks[-1] if masks else ''
    if not isinstance(number, str):
        return None
    column = int(block['grid position'][:-1])
    offset = next((d['deviation'] for d in data.get('column deviations', [])
                   if d['type'] == 'block' and d['num'] == column), 0)
    left = 27 + 23 * column + offset
    border = left if side == 'L' else left + 7
    direction = 1 if side == 'L' else -1
    row = 2 + 7 * LETTERS.index(block['grid position'][-1]) + pin['line'] - 1
    old = [border - (1 + len(number) + len(marks[0]['text'] if marks else '')) * direction, row]
    contact = [border - 4 * direction, row]
    endpoints = [{'polyline': i, 'point': j} for i, route in enumerate(net['routing'])
                 if len(route) >= 2 for j in (0, len(route)-1) if route[j] == contact]
    if endpoints:
        return {'terminal': node, 'net': net['net number'], 'contact': contact,
                'basis': 'Route already ends at the fixed contact', 'endpoints': endpoints}
    candidates = [{'polyline': i, 'point': j} for i, route in enumerate(net['routing'])
                  if len(route) >= 2 for j, k in ((0, 1), (len(route)-1, len(route)-2))
                  if route[j] == old and route[k] == contact
                  and (old[0] - route[k][0]) * direction > 0]
    if len(candidates) != 1:
        return None
    return {'terminal': node, 'net': net['net number'], 'contact': contact,
            'old endpoint': old, 'basis': 'Adjacent bend equals the fixed contact exactly', **candidates[0]}


def open_entries(entries):
    return bool(entries) and (not isinstance(entries, list) or any(
        not isinstance(item, dict) or item.get('status') != 'resolved' for item in entries))


def remaining_findings(details):
    if open_entries(details.get('uncertainties', [])) or open_entries(details.get('format questions', [])):
        return True
    c = details.get('render comparison') or {}
    if not isinstance(c, dict):
        return True
    different = c.get('unresolved different cells', c.get('different cells', 0))
    if c.get('rendered') is False or type(different) is not int or different > 0 or open_entries(c.get('wiring findings', [])):
        return True
    issues = details.get('publication issues')
    return bool(issues and (not isinstance(issues, dict) or issues.get('status') not in ('resolved', 'closed', 'clear', 'none')))


def retract(document, details):
    data, result = copy.deepcopy(document), copy.deepcopy(details)
    questions, retracted, evidence = [], [], []
    for q in result.get('format questions', []):
        if q.get('status') == 'resolved':
            questions.append(q)
            continue
        if q.get('code') == 'fixed_terminal_slot_layout':
            kept = []
            for hold in q.get('terminals', []):
                proof = boundary_evidence(data, result, hold)
                if proof is None:
                    kept.append(hold)
                else:
                    retracted.append(copy.deepcopy(hold)); evidence.append(proof)
            if kept:
                questions.append({**q, 'terminals': kept})
        elif q.get('code') == 'annotation_terminal_lead' and (proof := boundary_evidence(data, result, q)):
            retracted.append(copy.deepcopy(q)); evidence.append(proof)
        else:
            questions.append(q)
    if not retracted:
        return data, result, [], []
    terminals = {p['terminal'] for p in evidence}
    changes, holds = normalize_annotation_leads(data, result, only_terminals=terminals)
    if holds:
        raise ValueError('Boundary proof and normalizer disagree: ' + str(holds))
    result['format questions'] = questions
    history = {'rule': 'bend-at-fixed-contact-is-implicit', 'authority': AUTHORITY,
               'retracted findings': retracted, 'contact evidence': evidence,
               'routing normalization': changes}
    result.setdefault('format question retractions', []).append(history)
    if data.get('review', {}).get('approved') is True and changes:
        history['prior approval'] = copy.deepcopy(data['review'])
        data['review'].update(approved=False, status='partial')
    data.setdefault('review', {})['unresolved discrepancies'] = remaining_findings(result)
    result['content sha256'] = content_digest(data)
    return data, result, retracted, changes


def run(root, apply=False, backup_root=None):
    root = Path(root)
    with writer_lock(root):
        planned, pages = [], []
        scanned = 0
        for path, raw, document, kind in models(root):
            if kind != 'v4':
                continue
            scanned += 1
            target, old_review, details = review(root, path, document)
            if details is None:
                continue
            updated, updated_review, removed, changed = retract(document, details)
            if not removed:
                continue
            planned.extend([(path, raw, encode(updated, raw)),
                            (target, old_review, encode(updated_review, old_review))])
            pages.append({'path': str(path), 'findingsRetracted': len(removed),
                          'routingNormalizations': changed,
                          'remainingFindings': updated['review']['unresolved discrepancies']})
        report = {'v4Scanned': scanned, 'pagesChanged': len(pages),
                  'findingsRetracted': sum(p['findingsRetracted'] for p in pages),
                  'routesNormalized': sum(len(p['routingNormalizations']) for p in pages),
                  'pagesWithoutRemainingFindings': sum(not p['remainingFindings'] for p in pages),
                  'pages': pages, 'applied': apply}
        return apply_changes(root, planned, 'pin-contact-boundary-retraction', report, backup_root) if apply else report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = run(args.source_root, args.apply, args.backup_root)
    if args.report:
        args.report.write_bytes(encode(result))
    print(json.dumps({k: v for k, v in result.items() if k != 'pages'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
