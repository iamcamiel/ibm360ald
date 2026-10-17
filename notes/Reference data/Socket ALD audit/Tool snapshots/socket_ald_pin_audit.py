"""Pure read-only pin audit using accepted uniform socket-listing evidence.

audit_pins(records, wrappers, definitions=None, *, check_definitions=False)
requires source wrappers {scan_id,page,model_path,node_pointer,node}. The caller
binds the accepted files; this module neither reads nor writes source files.
Physical-site width wins. Only an unlisted/unreadable site can fall back to a
unanimous explicit card-type width. Connectors are never inferred to be SLT.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from copy import deepcopy
import re

from socket_ald_matching import normalize_identity, normalize_location
from socket_pin_validation import audit_node_pins

SCHEMA = 'socket-ald-physical-pin-audit-v1'
NON_SLT = {'cabl', 'cable', 'xovr', 'crossover', 'cross_over', 'connector', 'conn',
           'empty', 'empty_socket', 'unused', 'unused_socket'}


def _kind(value):
    value = re.sub(r'\s+', '_', str(value or '').strip().lower())
    if value in {'single', 'single_card'}: return 'single'
    if value in {'double', 'double_card'}: return 'double'
    return None


def _proof(record, index):
    return {'record_id': str(record.get('id', 'record-index:' + str(index))),
            'record_index': index, 'board': record.get('board'),
            'sockets': deepcopy(record.get('sockets', record.get('physical_sockets', []))),
            'kind': record.get('kind'), 'kind_literal': record.get('kind_literal'),
            'card_type': record.get('card_type'), 'part_number': record.get('part_number'),
            'header_source': deepcopy(record.get('header_source')),
            'kind_source_spans': [deepcopy(span) for span in record.get('source_spans', [])
                                  if re.search(r'SINGLE|DOUBLE|CABL|XOVR|CONN|EMPTY|UNUSED', str(span.get('literal', '')), re.I)],
            'evidence': deepcopy(record.get('evidence', []))}


def _context(wrapper, node):
    return {**{key: deepcopy(wrapper.get(key)) for key in
               ('scan_id', 'page', 'model_path', 'node_pointer')},
            'node_id': node.get('id'), 'card_type': node.get('card_type'),
            'portion': node.get('portion')}


def audit_pins(records, wrappers, definitions=None, *, check_definitions=False):
    """Return one source-bound result per pin plus width-resolution issues.

    Default scope is contact range, qualifiers and conflicting printed mirrors.
    Definition shape/contact comparisons are deliberately opt-in: historical
    reviewed source corrections must not silently become new discrepancies.
    All supply contacts remain informational, with no electrical-rule claims.
    """
    if isinstance(records, dict): records = records['records']
    sites = defaultdict(list); by_card = defaultdict(list); facts = {}
    for index, record in enumerate(records):
        proof = _proof(record, index); key = proof['record_id']
        if key in facts: raise ValueError('Duplicate listing record ID: ' + key)
        location = normalize_location(board=record.get('board'),
            sockets=record.get('physical_sockets', record.get('occupied_sockets', record.get('sockets'))))
        kind = _kind(record.get('kind')) or _kind(record.get('kind_literal'))
        literal_kind = re.sub(r'\s+', '_', str(record.get('kind') or '').strip().lower())
        fact = {'proof': proof, 'kind': kind, 'non_slt': literal_kind in NON_SLT,
                'location': location, 'card_type': str(record.get('card_type') or '')}
        facts[key] = fact
        if location['resolved']:
            for socket in location['sockets']: sites[(location['board'], socket)].append(key)
        if re.fullmatch(r'\d{4}', fact['card_type']): by_card[fact['card_type']].append(key)

    def resolution(identity):
        location = identity['location']; card = identity['card_type']
        exact_ids = sorted({key for socket in location['sockets']
                            for key in sites.get((location['board'], socket), [])}) if location['resolved'] else []
        card_ids = sorted(by_card.get(card, [])) if card else []
        global_widths = sorted({facts[key]['kind'] for key in card_ids if facts[key]['kind']})
        explicit_non_slt = [key for key in card_ids if facts[key]['non_slt']]
        result = {'kind': None, 'source': None, 'status': 'unclassified',
                  'site': {'board': location['board'], 'sockets': location['sockets'], 'resolved': location['resolved']},
                  'listing_record_ids': [], 'issues': []}
        if exact_ids:
            widths = sorted({facts[key]['kind'] for key in exact_ids if facts[key]['kind']})
            non_slt = [key for key in exact_ids if facts[key]['non_slt']]
            result.update(source='exact_physical_site', listing_record_ids=exact_ids)
            if len(widths) > 1 or (widths and non_slt):
                result.update(status='width_conflict')
                result['issues'].append({'status': 'site_width_conflict', 'severity': 'review',
                    'message': 'Exact socket evidence has incompatible module classifications.', 'widths': widths})
            elif non_slt:
                result.update(status='non_slt_site')
            elif len(widths) == 1:
                result.update(kind=widths[0], status='resolved')
            else:
                result.update(status='site_kind_unresolved')
        else:
            result.update(source='card_type_consensus', listing_record_ids=card_ids,
                          fallback_reason='site_unlisted' if location['resolved'] else 'site_unreadable')
            if len(global_widths) > 1 or (global_widths and explicit_non_slt):
                result.update(status='width_conflict')
                result['issues'].append({'status': 'card_type_width_conflict', 'severity': 'review',
                    'message': 'Card-type listing evidence is not a unanimous single/double SLT classification.',
                    'widths': global_widths})
            elif len(global_widths) == 1:
                result.update(kind=global_widths[0], status='resolved')
            elif explicit_non_slt:
                result.update(status='non_slt_card_type')
            elif card is None:
                result.update(status='card_identity_unresolved')
        # Width conflicts elsewhere are still visible, even when exact-site
        # evidence safely determines the local physical range.
        if exact_ids and len(global_widths) > 1:
            result['issues'].append({'status': 'card_type_width_conflict', 'severity': 'review',
                'message': 'Card-type width is inconsistent elsewhere; local range uses exact site only.',
                'widths': global_widths, 'listing_record_ids': card_ids})
        return result

    results = []; issues = []; node_widths = Counter(); used_proofs = set(); node_count = 0
    for wrapper in wrappers:
        node_count += 1
        node = wrapper.get('node')
        if not isinstance(node, dict):
            issues.append({**_context(wrapper, {}), 'status': 'malformed_node', 'severity': 'review'})
            continue
        context = _context(wrapper, node); identity = normalize_identity(wrapper.get('matching_node',node))
        width = resolution(identity); node_widths[width['status']] += 1
        used_proofs.update(width['listing_record_ids'])
        for issue in width['issues']:
            used_proofs.update(issue.get('listing_record_ids', []))
            issues.append({**context, **deepcopy(issue), 'width_resolution': deepcopy(width)})
        definition = None
        if definitions:
            definition = definitions if 'boxes' in definitions else definitions.get(identity['card_type'])
        if 'pins' in node and not isinstance(node['pins'], list):
            issues.append({**context, 'status': 'malformed_pin_container', 'severity': 'review',
                           'message': 'Source pins field is not a JSON array; no pin objects were dropped silently.',
                           'literal': deepcopy(node['pins'])})
            continue
        for result in audit_node_pins(node, width['kind'], definition if check_definitions else None):
            row = {**context, **result, 'site_literals': deepcopy(identity['location']['literal']),
                   'identity_issues': identity['issues'], 'normalized_site': deepcopy(width['site']),
                   'width_resolution': deepcopy(width), 'definition_available': definition is not None,
                   'definition_checked': bool(check_definitions and definition is not None)}
            row['range_checked'] = width['kind'] is not None and row['physical_contact'] is not None
            if width['status'] == 'width_conflict':
                row['pin_validation_status'] = row['status']
                row['status'], row['severity'] = 'width_conflict', 'review'
            results.append(row)
    counts = {'nodes': node_count, 'pins': len(results), 'range_checked': sum(row['range_checked'] for row in results),
              'range_failures': sum(any(issue['status'] in ('invalid_letter', 'invalid_number') for issue in row['issues']) for row in results),
              'statuses': dict(sorted(Counter(row['status'] for row in results).items())),
              'severities': dict(sorted(Counter(row['severity'] for row in results).items())),
              'node_width_statuses': dict(sorted(node_widths.items())),
              'width_issues': sum('width_resolution' in issue for issue in issues), 'issues': len(issues)}
    return {'schema': SCHEMA,
            'scope': 'Read-only physical pin ranges and printed-mirror agreement. No source corrections or new electrical-rule findings.',
            'definition_checks_enabled': bool(check_definitions), 'counts': counts,
            'results': results, 'issues': issues,
            'listing_width_evidence': [deepcopy(facts[key]['proof']) for key in sorted(used_proofs)]}
