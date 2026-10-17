"""Pure, source-preserving reconciliation of socket reference groups.

Every listed portion must have an exact physical identity on a common ALD page
before a unique counterpart is reported. A counterpart is a corroborated link,
never a conclusion that either printed page reference should be changed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy

from socket_ald_matching import normalize_identity

EXACT_FORWARD = {'exact', 'multiple_exact'}
IDENTITY_FIELDS = ('location', 'board', 'sockets', 'physical_sockets',
                   'occupied_sockets', 'card_type', 'portion', 'printed_card_portion')


def _key(wrapper):
    key = (wrapper.get('model_path'), wrapper.get('node_pointer'))
    if any(not isinstance(value, str) or not value for value in key):
        raise ValueError('Every source node needs model_path and node_pointer')
    return key


def _resolved(identity):
    return not identity['issues'] and identity['location']['resolved'] and bool(
        identity['card_type'] and identity['portion'])


def _proof(wrapper):
    """Keep source hashes/pointers and literal identity, without large pin arrays."""
    node = wrapper['node']
    return {'binding': deepcopy({key: value for key, value in wrapper.items()
                                if key not in {'node','matching_node'} and not key.startswith('_')}),
            'comparison_identity':normalize_identity(wrapper.get('matching_node',node)),
            'observed': deepcopy({key: node.get(key) for key in
                                 ('id', 'grid', *IDENTITY_FIELDS)})}


def reconcile_references(records, wrappers, forward_results):
    """Link every listing reference group to exact current ALD counterparts.

    Inputs are uniform records, source-bound raw node wrappers and the complete
    forward results. Duplicate or missing claim/node identities fail loudly.
    Separate scans and repeated nodes remain separate occurrences. Unknown or
    conflicting identity fields never become exact matches. Only explicit
    occupied socket members are used; adjacent socket positions are not inferred.

    Each result retains the literal page, reference spans, every listed portion,
    its forward status and all exact candidate pages/nodes. ``node_evidence``
    deduplicates source proofs. Empty candidate-page intersections never select a
    counterpart, even when different portions have witnesses on different pages.
    There is no file I/O, mutation, fuzzy correction or source-page replacement.
    """
    if isinstance(records, dict):
        records = records['records']
    records = list(records); wrappers = list(wrappers)
    record_ids = set(); expected = set()
    for record in records:
        rid = record.get('id')
        if not isinstance(rid, str) or not rid or rid in record_ids:
            raise ValueError('Missing or duplicate listing record ID: ' + str(rid))
        record_ids.add(rid)
        for i, ref in enumerate(record.get('references', [])):
            for j, _ in enumerate(ref.get('portions', [])):
                expected.add((rid, i, j))
    forward = {}
    for result in forward_results:
        claim = result['claim']
        key = (claim['record_id'], claim['reference_index'], claim['portion_index'])
        if key not in expected or key in forward:
            raise ValueError('Unexpected or duplicate forward claim: ' + repr(key))
        forward[key] = result.get('classification')
    if set(forward) != expected:
        raise ValueError('Forward results must cover every listed portion exactly once')

    by_identity = defaultdict(set); sources = {}; source_keys = set()
    indexed = 0; unresolved = 0
    for i, wrapper in enumerate(wrappers):
        key = _key(wrapper)
        if key in source_keys:
            raise ValueError('Duplicate source node binding: ' + repr(key))
        source_keys.add(key)
        node = wrapper.get('node'); page = str(wrapper.get('page') or '').strip().upper()
        if not isinstance(node, dict) or not page or wrapper.get('source_page_conflict'):
            unresolved += 1; continue
        identity = normalize_identity(wrapper.get('matching_node',node))
        if not _resolved(identity):
            unresolved += 1; continue
        node_id = 'node:' + str(i)
        sources[node_id] = wrapper
        location = identity['location']
        for socket in location['sockets']:
            by_identity[(location['board'], socket, identity['card_type'], identity['portion'])].add(node_id)
        indexed += 1

    results = []; classes = Counter(); used_nodes = set(); examined = 0
    for record_index, record in enumerate(records):
        for ref_index, ref in enumerate(record.get('references', [])):
            portions = []; candidate_sets = []; literal_page = ref.get('page')
            for portion_index, portion in enumerate(ref.get('portions', [])):
                identity = normalize_identity(dict(record, portion=portion))
                found = set()
                if _resolved(identity):
                    location = identity['location']
                    for socket in location['sockets']:
                        found.update(by_identity.get((location['board'], socket,
                            identity['card_type'], identity['portion']), ()))
                # Source order is stable; all separately scanned/node occurrences survive.
                found = sorted(found, key=lambda key: int(key.split(':')[1]))
                pages = sorted({str(sources[key]['page']).strip().upper() for key in found})
                used_nodes.update(found); candidate_sets.append(set(pages)); examined += 1
                portions.append({'portion_index': portion_index, 'portion': deepcopy(portion),
                    'forward_classification': forward[(record['id'], ref_index, portion_index)],
                    'identity_issues': deepcopy(identity['issues']),
                    'candidate_pages': pages, 'node_evidence_ids': found})
            common = set.intersection(*candidate_sets) if candidate_sets else set()
            all_supported = bool(portions) and all(candidate_sets)
            verified = all_supported and str(literal_page or '').strip().upper() in common and all(
                portion['forward_classification'] in EXACT_FORWARD for portion in portions)
            chosen = None; reason = None
            if verified:
                status = 'already_verified'; chosen = str(literal_page).strip().upper()
            elif not any(candidate_sets):
                status = 'no_counterpart'; reason = 'no_exact_witness' if portions else 'no_listed_portions'
            elif not all_supported:
                status = 'incomplete_counterpart'; reason = 'some_portions_without_exact_witness'
            elif not common:
                status = 'incomplete_counterpart'; reason = 'no_common_page_for_all_portions'
            elif len(common) == 1:
                status = 'unique_counterpart_page'; chosen = next(iter(common))
            else:
                status = 'ambiguous_counterpart_pages'
            result = {'record_id': record['id'], 'record_index': record_index,
                'reference_index': ref_index, 'literal_page': deepcopy(literal_page),
                'reference_source_spans': deepcopy(ref.get('source_spans', [])),
                'listing': deepcopy({key: record.get(key) for key in
                    ('board', 'sockets', 'physical_sockets', 'card_type', 'kind', 'header_source')}),
                'classification': status, 'reason': reason, 'portions': portions,
                'all_portions_supported': all_supported,
                'common_candidate_pages': sorted(common), 'chosen_counterpart_page': chosen,
                'source_changes_applied': False, 'source_page_correction_asserted': False}
            results.append(result); classes[status] += 1
    if examined != len(expected):
        raise ValueError('Reconciliation portion coverage failed')
    return {'schema': 'socket-ald-reference-reconciliation-v1',
        'policy': 'Exact physical identities corroborate counterpart links; printed references remain unchanged.',
        'source_changes_applied': False, 'source_page_correction_asserted': False,
        'counts': {'reference_groups': len(results), 'portion_claims': examined,
            'classifications': dict(sorted(classes.items())), 'source_nodes': len(wrappers),
            'fully_resolved_source_nodes': indexed, 'unresolved_or_non_card_source_nodes': unresolved,
            'used_node_proofs': len(used_nodes), 'all_claims_accounted': examined == len(expected)},
        'results': results, 'node_evidence': {key: _proof(sources[key]) for key in
            sorted(used_nodes, key=lambda key: int(key.split(':')[1]))}}
