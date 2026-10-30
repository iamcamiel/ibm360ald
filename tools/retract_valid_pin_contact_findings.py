#!/usr/bin/env python3
"""Retract obsolete annotated-contact, crossing and same-net branch holds.

Dry-run by default. --apply saves exact preimages and a maintenance receipt.
Only identifiable terminals accepted by the current converter normalizer are
changed. Other findings, original reports and source claims remain intact.
"""
import argparse
import copy
import json
from pathlib import Path

from ald_json_tools.pin_annotations import normalize_annotation_leads
from page_maintenance import apply_changes, content_digest, encode, models, review, writer_lock
from retract_contact_boundary_findings import boundary_evidence, remaining_findings, OLD_REASON

REASONS = {
    'No unique horizontal endpoint at the old terminal presentation boundary',
    'The changed lead interval is occupied by another net',
    'Another same-net route intersects the changed lead interval',
}
AUTHORITY = ('Human correction: annotated pins use the normal contact cell, '
             'with the annotation replacing its wire glyph; crossings at that '
             'cell and existing branches of the same net are valid.')


def evidence(data, details, hold):
    if hold.get('reason') == OLD_REASON:
        return boundary_evidence(data, details, hold)
    if hold.get('reason') not in REASONS:
        return None
    parts = hold.get('terminal', '').split('/')
    if len(parts) != 5 or parts[0] != 'blocks' or parts[2] != 'pins':
        return None
    _, serial, _, side, line = parts
    blocks = [b for b in data['blocks'] if b['serial'] == serial]
    if len(blocks) != 1:
        return None
    pins = [p for p in blocks[0]['pins'] if p['side'] == side and str(p['line']) == line]
    owners = [n for n in data['nets'] if hold['terminal'] in n['nodes']]
    if (len(pins) != 1 or len(owners) != 1 or
            owners[0]['nodes'].count(hold['terminal']) != 1 or
            owners[0]['net number'] != hold.get('net')):
        return None
    candidate = copy.deepcopy(data)
    changes, holds = normalize_annotation_leads(candidate, details, {hold['terminal']})
    if holds or not changes:
        return None
    return {'terminal': hold['terminal'], 'net': hold['net'],
            'basis': 'Unique existing endpoint normalized under the corrected contact rule',
            'normalization': changes}


def retract(document, details):
    data, result = copy.deepcopy(document), copy.deepcopy(details)
    questions, removed, proofs = [], [], []
    for question in result.get('format questions', []):
        if question.get('status') == 'resolved':
            questions.append(question)
            continue
        if question.get('code') == 'fixed_terminal_slot_layout':
            kept = []
            for hold in question.get('terminals', []):
                proof = evidence(data, result, hold)
                if proof is None:
                    kept.append(hold)
                else:
                    removed.append(copy.deepcopy(hold)); proofs.append(proof)
            if kept:
                questions.append({**question, 'terminals': kept})
        elif question.get('code') == 'annotation_terminal_lead' and (proof := evidence(data, result, question)):
            removed.append(copy.deepcopy(question)); proofs.append(proof)
        else:
            questions.append(question)
    if not removed:
        return data, result, [], []
    changes, holds = normalize_annotation_leads(data, result, {p['terminal'] for p in proofs})
    if holds:
        raise ValueError('Contact proof and normalizer disagree: ' + str(holds))
    result['format questions'] = questions
    history = {'rule': 'normal-contact-allows-annotations-crossings-and-own-branches',
               'authority': AUTHORITY, 'retracted findings': removed,
               'contact evidence': proofs, 'routing normalization': changes}
    result.setdefault('format question retractions', []).append(history)
    if changes and data.get('review', {}).get('approved') is True:
        history['prior approval'] = copy.deepcopy(data['review'])
        data['review'].update(approved=False, status='partial')
    data.setdefault('review', {})['unresolved discrepancies'] = remaining_findings(result)
    result['content sha256'] = content_digest(data)
    return data, result, removed, changes


def run(root, apply=False, backup_root=None):
    root = Path(root)
    with writer_lock(root):
        planned, pages, scanned = [], [], 0
        for path, raw, document, kind in models(root):
            if kind != 'v4':
                continue
            scanned += 1
            target, old_review, details = review(root, path, document)
            if details is None:
                continue
            updated, new_review, removed, changes = retract(document, details)
            if not removed:
                continue
            planned.extend([(path, raw, encode(updated, raw)),
                            (target, old_review, encode(new_review, old_review))])
            pages.append({'path': str(path), 'findingsRetracted': len(removed),
                          'routingNormalizations': changes,
                          'remainingFindings': updated['review']['unresolved discrepancies']})
        report = {'v4Scanned': scanned, 'pagesChanged': len(pages),
                  'findingsRetracted': sum(p['findingsRetracted'] for p in pages),
                  'routesNormalized': sum(len(p['routingNormalizations']) for p in pages),
                  'pagesWithoutRemainingFindings': sum(not p['remainingFindings'] for p in pages),
                  'pages': pages, 'applied': apply}
        # Same recoverable contact-finding maintenance protocol as the earlier
        # boundary correction, with this rule and exact old findings recorded.
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
