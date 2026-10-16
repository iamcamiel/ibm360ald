"""Pure, indexed reverse comparison of ALD blocks missed by the forward pass.

No inferred adjacent sockets, fuzzy values, source corrections or file access.
An identity found under another page is corroboration requiring review, never a
permission to rewrite either source. All source scan variants remain distinct.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import re

from socket_ald_matching import normalize_identity, normalize_location, _axis

AXES = ('location', 'card_type', 'portion')
IDENTITY_FIELDS = ('location', 'board', 'sockets', 'physical_sockets',
                   'occupied_sockets', 'card_type', 'portion', 'printed_card_portion')
ANNOTATION_FUNCTIONS = {'JUNCTION', 'DOT', 'NOTE', 'TEXT', 'WIRE', 'CROSSING'}


def _key(wrapper):
    key = (wrapper.get('model_path'), wrapper.get('node_pointer'))
    if any(value is None or value == '' for value in key):
        raise ValueError('Every node binding needs model_path and node_pointer')
    return key


def _annotation(node):
    """Exclude only explicitly identified annotations, never absent identities."""
    if not isinstance(node, dict):
        return False
    if any(node.get(k) for k in IDENTITY_FIELDS) or node.get('pins') or node.get('unit'):
        return False
    function = str(node.get('function') or '').strip().upper()
    kinds = {str(node.get(k) or '').strip().upper() for k in ('kind', 'node_kind', 'type')}
    return function in ANNOTATION_FUNCTIONS or bool(kinds & ANNOTATION_FUNCTIONS)


def _non_card_reason(node):
    """Use explicit model semantics, retaining unknown identity-free blocks."""
    if not isinstance(node, dict):
        return None
    # A partial board/location may also be printed on a DOT, cable or service
    # symbol. A real or damaged card/portion code, however, must never be hidden
    # by a contradictory non-card flag. Preserve that conflict for review.
    if node.get('portion') or node.get('printed_card_portion'):
        return None
    card = str(node.get('card_type') or '').strip().upper()
    if card and card not in {'CABL', 'CABLE', 'XOVR', 'CONN', 'CONNECTOR'}:
        return None
    for field in ('card', 'part'):
        value = re.sub(r'\s+', '', str(node.get(field) or '')).upper()
        if re.fullmatch(r'[A-Z0-9�]{5,7}', value) and any(c.isdigit() or c == '�' for c in value[:4]):
            return None
    if 'CAS_box' in node and 'address' in node:
        return 'CAS control-flow box rather than a physical card portion'
    kind = str(node.get('kind') or '').strip().lower()
    node_kind = str(node.get('node_kind') or '').strip().lower()
    if kind in {'reference table box', 'entry wrapper', 'indicator', 'indicator lamp',
                'printed logical connector block', 'service', 'crossover'}:
        return 'Explicit non-card kind: ' + kind
    if node_kind in {'mechanical', 'service', 'dot'}:
        return 'Explicit non-card node_kind: ' + node_kind
    for flag in ('non_card_source_block', 'cardless_dot_gate', 'service_element', 'entry_block',
                 'non_card_symbol', 'annotation_block'):
        if node.get(flag) is True:
            return 'Explicit model flag: ' + flag
    if (node.get('physical_card') is False or node.get('A1_expected') is False
            or node.get('A1_card_portion_applicable') is False):
        return 'Model explicitly declares no physical card or A1 listing expected'
    if str(node.get('unit') or '').strip().upper() in {'DOT', 'DDT'}:
        return 'Printed DOT wiring primitive without card identity'
    if str(node.get('function') or '').strip().upper() in {'OR DOT', 'DOT OR'}:
        return 'Printed DOT wiring primitive without card identity'
    function = str(node.get('function') or '').strip(' ✲*').upper()
    if function == 'SERV' or (str(node.get('technology') or '').strip().upper() == 'SYNC'
                              and not node.get('part')):
        return 'Explicit service function/technology without card portion code'
    if node.get('connector_location'):
        return 'Cable connector location field rather than a card location'
    body = node.get('body')
    if isinstance(body, dict): body = list(body.values())
    if isinstance(body, list) and any(str(line).strip(' ✲*') in {'ENTR', 'EXIT'} for line in body):
        return 'Printed cable entry/exit body rather than a card portion'
    return None


def _binding(wrapper):
    return deepcopy({k: v for k, v in wrapper.items() if not k.startswith('_')})


def _record_proof(record, index):
    fields = ('id', 'board', 'sockets', 'physical_sockets', 'kind', 'kind_literal',
              'card_type', 'part_number', 'header_source', 'source_spans',
              'unused_portions', 'unused_sockets', 'issues')
    return {'record_index': index, **{k: deepcopy(record.get(k)) for k in fields}}


def audit_reverse(records, wrappers, forward_results, *,
                  reviewed_forward_statuses=('reviewed_overlay_exact',)):
    """Return source-bound results for every node not hit by accepted forward matches.

    Inputs are uniform listing records, raw source wrappers and forward results
    whose exact matches contain binding.model_path/node_pointer. The default
    reviewed-overlay status is separately counted; callers can name additional
    explicit reviewed statuses. Candidate-only forward matches do not suppress
    reverse examination. Duplicate listing IDs or node keys fail loudly.

    Results contain full original bindings and normalized observed identities,
    exact_matches, two-of-three candidates and exact-site listing record IDs.
    Complete record proofs are deduplicated in listing_evidence keyed by ID;
    each candidate retains its own reference source spans and record ID/index.
    Coverage partitions all nodes into ordinary forward hits, reviewed overlay
    hits, reverse-examined blocks, explicit non-card nodes and annotations.
    """
    if isinstance(records, dict):
        records = records['records']
    wrappers = list(wrappers)
    nodes = {}
    for wrapper in wrappers:
        key = _key(wrapper)
        if key in nodes:
            raise ValueError('Duplicate ALD node binding: ' + repr(key))
        nodes[key] = wrapper

    ordinary_hits = set(); reviewed_hits = set()
    reviewed_statuses = set(reviewed_forward_statuses)
    if reviewed_statuses & {'exact', 'multiple_exact'}:
        raise ValueError('Reviewed statuses must be distinct from ordinary exact statuses')
    for result in forward_results:
        status = result.get('classification')
        if status not in {'exact', 'multiple_exact'} | reviewed_statuses:
            continue
        matches = result.get('matches', [])
        if not matches:
            raise ValueError('Exact forward result without matches')
        for match in matches:
            key = _key(match['binding'])
            if key not in nodes:
                raise ValueError('Forward match references an unknown node: ' + repr(key))
            (ordinary_hits if status in {'exact', 'multiple_exact'} else reviewed_hits).add(key)
    reviewed_hits -= ordinary_hits
    all_hits = ordinary_hits | reviewed_hits

    facts = []; claims = []
    by_site = defaultdict(set)
    by_location_card = defaultdict(set)
    by_location_portion = defaultdict(set)
    by_card_portion = defaultdict(set)
    record_ids = set()
    for record_index, record in enumerate(records):
        record_id = record.get('id')
        if not record_id or record_id in record_ids:
            raise ValueError('Missing or duplicate listing record ID: ' + str(record_id))
        record_ids.add(record_id)
        location = normalize_location(board=record.get('board'),
            sockets=record.get('physical_sockets') or record.get('sockets'))
        fact = {'record': record, 'proof': _record_proof(record, record_index),
                'location': location}
        facts.append(fact)
        if location['resolved']:
            for socket in location['sockets']:
                by_site[(location['board'], socket)].add(record_index)
        for ref_index, ref in enumerate(record.get('references', [])):
            for portion_index, portion in enumerate(ref.get('portions', [])):
                identity = normalize_identity({**record, 'portion': portion})
                claim_index = len(claims)
                claims.append({'record_index': record_index, 'reference_index': ref_index,
                    'portion_index': portion_index, 'page': ref.get('page'),
                    'identity': identity, 'reference': ref})
                loc = identity['location']; card = identity['card_type']; part = identity['portion']
                if loc['resolved']:
                    for socket in loc['sockets']:
                        site = (loc['board'], socket)
                        if card is not None: by_location_card[site + (card,)].add(claim_index)
                        if part is not None: by_location_portion[site + (part,)].add(claim_index)
                if card is not None and part is not None:
                    by_card_portion[(card, part)].add(claim_index)

    used_records = set()
    def record_link(index):
        used_records.add(index)
        return {'id': facts[index]['proof']['id'], 'record_index': index}

    def proof(claim, axes):
        return {'listing': record_link(claim['record_index']),
                'reference_index': claim['reference_index'], 'portion_index': claim['portion_index'],
                'page': claim['page'], 'reference_source_spans': deepcopy(claim['reference'].get('source_spans', [])),
                'identity': deepcopy(claim['identity']), 'axes': axes,
                'matching_axes': [k for k, v in axes.items() if v is True],
                'differing_axes': [k for k, v in axes.items() if v is False],
                'unresolved_axes': [k for k, v in axes.items() if v is None]}

    results = []; classes = Counter(); annotations = 0; non_cards = 0; examined = 0
    for wrapper in wrappers:
        if _key(wrapper) in all_hits:
            continue
        node = wrapper.get('node'); actual = normalize_identity(wrapper.get('matching_node',node) if isinstance(node, dict) else {})
        issues = list(actual['issues'])
        if wrapper.get('source_page_conflict'): issues.append('source_page_conflict')
        if not isinstance(node, dict): issues.append('malformed_node')
        result = {'binding': _binding(wrapper), 'observed_identity': actual,
                  'issues': sorted(set(issues)), 'exact_matches': [], 'candidates': [],
                  'site_records': [], 'source_changes_applied': False}
        if _annotation(node):
            result['classification'] = 'annotation_excluded'; annotations += 1
            classes[result['classification']] += 1; results.append(result); continue
        non_card_reason = _non_card_reason(node)
        if non_card_reason:
            result.update(classification='explicit_non_card', exclusion_reason=non_card_reason)
            non_cards += 1; classes[result['classification']] += 1; results.append(result); continue
        examined += 1
        loc = actual['location']; card = actual['card_type']; part = actual['portion']
        eligible = set(); site_ids = set()
        if loc['resolved']:
            for socket in loc['sockets']:
                site = (loc['board'], socket)
                site_ids.update(by_site.get(site, ()))
                if card is not None: eligible.update(by_location_card.get(site + (card,), ()))
                if part is not None: eligible.update(by_location_portion.get(site + (part,), ()))
        if card is not None and part is not None:
            eligible.update(by_card_portion.get((card, part), ()))
        for index in sorted(eligible):
            claim = claims[index]
            axes = {name: _axis(actual, claim['identity'], name) for name in AXES}
            if sum(value is True for value in axes.values()) < 2:
                continue
            evidence = proof(claim, axes)
            evidence['same_page'] = str(claim['page'] or '').strip().upper() == str(wrapper.get('page') or '').strip().upper()
            if all(value is True for value in axes.values()) and not issues and not claim['identity']['issues']:
                result['exact_matches'].append(evidence)
            else:
                result['candidates'].append(evidence)
        result['site_records'] = [record_link(i) for i in sorted(site_ids)]
        exact = result['exact_matches']; site_card = [facts[i] for i in sorted(site_ids)
            if card is not None and str(facts[i]['record'].get('card_type') or '').strip().upper() == card]
        if issues:
            status = 'identity_absent' if isinstance(node, dict) and not any(node.get(k) for k in IDENTITY_FIELDS) else 'unresolved_identity'
        elif exact:
            status = 'exact_same_page' if any(e['same_page'] for e in exact) else 'exact_identity_other_page'
        elif site_card:
            unused = [f for f in site_card if part in f['record'].get('unused_portions', [])]
            status = 'portion_marked_unused' if unused else 'portion_unlisted_at_site'
        elif site_ids:
            known_cards = {str(facts[i]['record'].get('card_type') or '').strip() for i in site_ids} - {''}
            status = 'site_card_type_mismatch' if known_cards else 'site_listing_identity_unresolved'
        elif result['candidates']:
            status = 'two_axis_candidates'
        else:
            status = 'no_listing_match'
        result['classification'] = status
        classes[status] += 1; results.append(result)
    coverage = {'all_nodes': len(wrappers), 'forward_exact_hit_nodes': len(ordinary_hits),
        'reviewed_overlay_hit_nodes': len(reviewed_hits), 'reverse_examined_nodes': examined,
        'annotation_excluded_nodes': annotations,
        'non_card_excluded_nodes': non_cards,
        'partition_complete': len(wrappers) == len(ordinary_hits) + len(reviewed_hits) + examined + annotations + non_cards}
    return {'schema': 'socket-ald-limited-reverse-v1', 'source_changes_applied': False,
            'coverage': coverage, 'classifications': dict(sorted(classes.items())), 'results': results,
            'listing_evidence': {facts[i]['proof']['id']: deepcopy(facts[i]['proof']) for i in sorted(used_records)}}
