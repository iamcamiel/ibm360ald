"""Publish one or more independently reviewed layouts without changing their circuits."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import build_card_data
from generate_card import ROOT, build, digest, read, record_generation, write_protected


def write_json(path, value):
    write_protected(path, (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))


def semantics(spec):
    return {b['portion']: {'unit': b['circuit_identifier'], 'function': b['function'],
            'ports': sorted((p['id'], p['side'], p['pin'], p['triangle']) for p in b['ports'])}
            for b in spec['boxes']}


def checked_review(path):
    """Check the shared freeze once, before any canonical input changes."""
    approval = read(path)
    assert approval['passed'] is True and not approval['failures']
    bindings = approval['candidate_bindings']
    if isinstance(bindings, dict):
        bindings = list(bindings.values())
    supporting = approval.get('supporting_files', [])
    if isinstance(supporting, dict):
        supporting = list(supporting.values())
    for binding in bindings + supporting:
        assert digest(Path(binding['path']).read_bytes()) == binding['sha256'], binding['path']
    return {str(Path(e['path']).resolve()): e['sha256'] for e in bindings}


def adopt(candidates, review_path):
    bindings = checked_review(review_path)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    batch = stamp+'-'+digest(review_path.read_bytes())[:12]
    history = ROOT/'notes/Card-ALD/history'/('Before reviewed layout '+batch)
    accepted = ROOT/'notes/Card-ALD/Generation/Accepted layouts'/batch
    review_copy = accepted/'Independent review.json'
    jobs = []
    before = {}
    for card, source in candidates:
        assert bindings.get(str(source.resolve())) == digest(source.read_bytes()), source
        candidate = read(source)
        assert candidate['card_type'] == card
        definition_path = ROOT/f'json/Card-ALD/definitions/{card}.json'
        overlay_path = ROOT/f'json/Card-ALD/build-overrides/{card}.json'
        previous, overlay = read(definition_path), read(overlay_path)
        assert semantics(candidate) == semantics(previous), 'Layout adoption changed symbols or port identities'
        assert candidate['nets'] == previous['nets'] and candidate['power_contacts'] == previous['power_contacts']
        assert candidate['variants'] == previous['variants'], 'Layout adoption changed notation variants'
        expected, _ = build(candidate)
        stale = {p.name for p in (ROOT/'Card-ALD').glob(card+'-[0-9]*.txt')} - set(expected)
        assert not stale, ('Unlisted older variants', stale)
        relatives = [f'json/Card-ALD/definitions/{card}.json', f'json/Card-ALD/build-overrides/{card}.json',
            *['Card-ALD/'+name for name in expected], f'json/Card-ALD/{card}.json',
            f'notes/Card-ALD/{card} drawing provenance.json', f'notes/Card-ALD/{card} diagram publication receipt.json',
            f'notes/Card-ALD/Generation/{card}.json', 'notes/Card-ALD/Universal card diagrams publication.json',
            'csv/Card-ALD/Notation variants.csv']
        for relative in relatives:
            path = ROOT/relative
            before[path] = path.read_bytes() if path.exists() else None
        jobs.append(dict(card=card, source=source, candidate=candidate, expected=expected,
            definition_path=definition_path, overlay_path=overlay_path, overlay=overlay))
    accepted.mkdir(parents=True, exist_ok=False)
    history.mkdir(parents=True, exist_ok=False)
    preserved = []
    for path, raw in before.items():
        if raw is None:
            continue
        target = history/path.relative_to(ROOT)
        assert not target.exists() or target.read_bytes() == raw
        write_protected(target, raw)
        preserved.append(dict(path=target.relative_to(ROOT).as_posix(), sha256=digest(raw),
                              original_path=path.relative_to(ROOT).as_posix()))
    write_protected(review_copy, review_path.read_bytes())
    # Every candidate passes a private roundtrip before any canonical writes.
    for job in jobs:
        card, candidate = job['card'], job['candidate']
        accepted_definition = accepted/card/'Definition.json'
        write_protected(accepted_definition, job['source'].read_bytes())
        overlay = deepcopy(job['overlay'])
        boxes = []
        for box in candidate['boxes']:
            placement = {k: box[k] for k in ['portion', 'x', 'top', 'height']}
            placement['ports'] = [{'id': p['id'], 'row': p['row']} for p in box['ports']]
            if 'compact_termination' in box:
                placement['compact_termination'] = deepcopy(box['compact_termination'])
            boxes.append(placement)
        overlay['layout'] = {k: deepcopy(candidate[k]) for k in ['canvas', 'wiring', 'exterior_pins', 'annotations']}
        overlay['layout']['boxes'] = boxes
        overlay['approved_variants'] = deepcopy(candidate['variants'])
        overlay['canonical_line_ending'] = candidate['canonical_line_ending']
        overlay.setdefault('source_bindings', []).extend(
            dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p.read_bytes()))
            for p in [accepted_definition, review_copy])
        overlay['layout_authority'] = dict(review=review_copy.relative_to(ROOT).as_posix(),
            algorithm='Reviewed universal placement, routing and conditional compact R notation',
            free_start_rows=candidate['canvas'].get('grid_step') == 1)
        private = ROOT.parent/'tmp/ald-text/ald/card-layout-adoption'/batch/(card+' reviewed supplement.json')
        write_json(private, overlay)
        preflight, report = build_card_data.build(card, overrides_path=private)
        assert preflight is not None and build(preflight)[0] == job['expected'], (card, 'Private roundtrip differs')
        job.update(new_overlay=overlay, accepted_definition=accepted_definition, preflight_report=report)
    receipts = []
    try:
        for job in jobs:
            write_json(job['overlay_path'], job['new_overlay'])
        for job in jobs:
            card = job['card']
            regenerated, report = build_card_data.build(card)
            assert regenerated is not None
            actual, checks = build(regenerated)
            assert actual == job['expected'], (card, 'Default data pipeline differs from accepted drawing')
            write_json(job['definition_path'], regenerated)
            for name, raw in actual.items():
                write_protected(ROOT/'Card-ALD'/name, raw)
            record_generation(regenerated, job['definition_path'], actual, checks)
            assert all((ROOT/'Card-ALD'/name).read_bytes() == raw for name, raw in job['expected'].items())
            receipt = dict(schema='reviewed-card-layout-adoption-v2', card_type=card,
                candidate=dict(path=job['accepted_definition'].relative_to(ROOT).as_posix(),
                               sha256=digest(job['accepted_definition'].read_bytes())),
                independent_review=dict(path=review_copy.relative_to(ROOT).as_posix(), sha256=digest(review_copy.read_bytes())),
                definition=dict(path=job['definition_path'].relative_to(ROOT).as_posix(), sha256=digest(job['definition_path'].read_bytes())),
                reviewed_supplement=dict(path=job['overlay_path'].relative_to(ROOT).as_posix(), sha256=digest(job['overlay_path'].read_bytes())),
                exact_default_builder_and_renderer_roundtrip=True, unchanged_circuit_and_port_identities=True,
                compact_terminations=checks['compact_terminations'], files=len(actual), build_evidence=report)
            write_json(accepted/card/'Publication receipt.json', receipt)
            receipts.append(receipt)
        result = dict(schema='reviewed-card-layout-batch-publication-v1', published=True,
            cards=[dict(card_type=r['card_type'], files=r['files'], compact_terminations=r['compact_terminations']) for r in receipts],
            independent_review=receipts[0]['independent_review'], preserved_predecessors=preserved,
            shared_review_checked_before_any_source_mutation=True,
            publisher=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=digest(Path(__file__).read_bytes())))
        write_json(accepted/'Batch publication receipt.json', result)
    except Exception:
        for path, raw in before.items():
            if raw is not None:
                write_protected(path, raw)
            elif path.exists():
                path.unlink()
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_type', nargs='+')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--definition', type=Path, help='One independently reviewed definition')
    source.add_argument('--definitions', type=Path, help='Batch root containing CARD.json or CARD/CARD.json')
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    if len(args.card_type) != len(set(args.card_type)):
        parser.error('Each card type may occur once')
    if args.definition and len(args.card_type) != 1:
        parser.error('--definition accepts one card; use --definitions for a batch')
    candidates = []
    for card in args.card_type:
        if len(card) != 4 or not card.isascii() or not card.isdigit():
            parser.error('Use four-digit card type numbers')
        path = args.definition
        if path is None:
            direct = args.definitions/(card+'.json')
            path = direct if direct.is_file() else args.definitions/card/(card+'.json')
        candidates.append((card, path))
    result = adopt(candidates, args.review)
    print(json.dumps(dict(published=True, cards=result['cards'], files=sum(c['files'] for c in result['cards']))))


if __name__ == '__main__':
    main()
