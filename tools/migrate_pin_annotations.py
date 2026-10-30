#!/usr/bin/env python3
"""Migrate exact standalone 2/3/8/L pin labels in current functional V4 JSON.

Dry-run by default. Use --apply to save recoverable changes. Net ownership and source observations are retained. Uniquely determined
terminal lead endpoints are normalized to the fixed three-character pin slot.
Exit 2 reports layout holds, including when safe changes were applied.
"""
import argparse
import copy
import json
from pathlib import Path

from page_maintenance import (apply_changes, content_digest, encode, models,
                              review, writer_lock)

MARKERS = ('2', '3', '8', 'L')


def migrate(document, details):
    data, findings = copy.deepcopy(document), copy.deepcopy(details)
    changes, blocked = [], []
    masks = {}
    for item in (findings or {}).get('uncertainties', []):
        if item.get('status') == 'unresolved' and isinstance(item.get('visible text'), str):
            masks.setdefault(item.get('field'), set()).add(item['visible text'])
    for block in data['blocks']:
        for pin in block['pins']:
            node = f"blocks/{block['serial']}/pins/{pin['side']}/{pin['line']}"
            value = pin.get('pin')
            visible = masks.get(node + '/pin', set())
            label = value if isinstance(value, str) else (next(iter(visible)) if len(visible) == 1 else None)
            if label not in MARKERS or 'pin' not in pin:
                continue
            if visible and visible != {label}:
                blocked.append({'terminal': node, 'reason': 'Conflicting visible pin text'})
                continue
            owners = [net for net in data['nets'] if node in net['nodes']]
            if len(owners) != 1 or owners[0]['nodes'].count(node) != 1:
                blocked.append({'terminal': node, 'reason': 'Missing or ambiguous declared net membership'})
                continue
            annotations = owners[0].get('annotations', [])
            existing = [item for item in annotations if item.get('at') == node]
            if existing and existing != [{'at': node, 'text': label}]:
                blocked.append({'terminal': node, 'reason': 'Conflicting terminal annotation'})
                continue
            del pin['pin']
            if not existing:
                owners[0].setdefault('annotations', []).append({'at': node, 'text': label})
            changes.append({'terminal': node, 'text': label, 'net': owners[0]['net number']})
            for item in (findings or {}).get('uncertainties', []):
                if item.get('field') == node + '/pin' and item.get('status') == 'unresolved':
                    item['status'] = 'resolved'
                    item['resolution'] = 'Human rule: exact standalone marker is a net annotation at this terminal; no physical pin inferred.'
    from ald_json_tools.pin_annotations import normalize_annotation_leads
    lead_changes, lead_holds = normalize_annotation_leads(data, findings)
    blocked.extend(lead_holds)
    if findings is not None and lead_holds:
        question={'code':'fixed_terminal_slot_layout','status':'unresolved',
                  'detail':'These stored routes cannot be normalized to the fixed three-character pin slot without separate layout review. No bend or competing wire was moved.',
                  'terminals':lead_holds}
        questions=findings.setdefault('format questions',[])
        existing=next((i for i,q in enumerate(questions) if q.get('code')=='fixed_terminal_slot_layout'),None)
        if existing is None:questions.append(question)
        else:questions[existing]=question
        data.setdefault('review',{}).update(status='partial',approved=False,**{'unresolved discrepancies':True})
    if changes or lead_changes:
        if findings is not None:
            findings.setdefault('annotation migrations', []).append({
                'rule': 'standalone-2-3-8-L', 'changes': changes, 'lead changes': lead_changes, 'lead holds': lead_holds,
                'prior render comparison': 'Preserved as historical evidence; derived text is regenerated separately.'})
            findings['content sha256'] = content_digest(data)
        if data.get('review', {}).get('approved') is True:
            if findings is not None:
                findings['annotation migrations'][-1]['prior approval'] = copy.deepcopy(data['review'])
            data['review'].update(approved=False, status='partial', **{'unresolved discrepancies': True})
    if findings is not None:
        findings['content sha256']=content_digest(data)
    return data, findings, changes + lead_changes, blocked


def run(root, apply=False, backup_root=None):
    with writer_lock(root):
        planned, pages, blocked, scanned = [], [], [], 0
        for path, raw, document, kind in models(root):
            if kind != 'v4':
                continue
            scanned += 1
            target, old_review, details = review(root, path, document)
            updated, new_review, changes, holds = migrate(document, details)
            blocked.extend({'path': str(path), **item} for item in holds)
            if not changes and updated == document and new_review == details:
                continue
            planned.append((path, raw, encode(updated, raw)))
            if target:
                planned.append((target, old_review, encode(new_review, old_review)))
            pages.append({'path': str(path), 'changes': changes})
        report = {'v4Scanned': scanned, 'pagesChanged': len(pages),
                  'annotationsMigrated': sum(sum('text' in c for c in p['changes']) for p in pages),
                  'leadsCorrected': sum(sum('polyline' in c for c in p['changes']) for p in pages),
                  'pages': pages, 'blocked': blocked, 'applied': apply}
        if apply:
            return apply_changes(root, planned, 'pin-annotations', report, backup_root)
        return report


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
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['blocked'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
