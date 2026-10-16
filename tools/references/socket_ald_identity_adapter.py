"""Pure source-bound identity views for existing ALD model schema variants.

Returned views are for comparison only. The original node and its source text
are never edited. Explicit conflicts remain issues rather than chosen values.
"""
from copy import deepcopy
import re


def _text(value):
    return str(value or '').strip()


def _clean(value):
    return re.sub(r'\s+', '', _text(value)).upper()


def _portion_label(value):
    value = _clean(value)
    if len(value) == 7 and value.startswith('580') and value.isdigit():
        return None  # Complete SLT part number, not card type plus portion.
    return value if (re.fullmatch(r'[A-Z0-9�]{5,7}', value)
                     and any(c.isdigit() or c == '�' for c in value[:4])) else None


def _socket_location(value):
    return re.fullmatch(r'((?:\d{2})?[A-Z])-([A-Z][1-9])([A-Z](?:1[0-9]|[1-9]))([BT])?', _clean(value))


def _grid_location(value):
    return bool(re.fullmatch(r'[1-9][A-Z]-[A-Z]{2}', _clean(value)))


def adapt_node(node):
    """Return a detached matching view and an explicit source-field audit trail.

    The ``card`` alias may hold a printed card/portion or a physical socket;
    syntax and the separate ``part`` field disambiguate them. Existing physical
    identity mirrors are retained; alias conflicts enter
    ``_identity_adaptation_issues`` for the common normalizer to preserve.
    Contextual 01C/01D (or another explicit frame) is used only when a current
    embedded socket-listing proof agrees with the printed unit, board, socket
    and readable card/portion. CPU abbreviation rules are never changed.
    """
    if not isinstance(node, dict):
        return deepcopy(node), {'rules': [], 'source_fields': {}, 'proof': [],
                                'issues': ['malformed_node'], 'warnings': []}
    view = deepcopy(node)
    audit = {'rules': [], 'source_fields': {}, 'proof': [], 'issues': [], 'warnings': []}

    def rule(name, fields):
        audit['rules'].append(name)
        for field in fields:
            audit['source_fields'][field] = deepcopy(node.get(field))

    # Preserve both literal mirrors if canonical and alias fields disagree.
    aliases = [(field, _portion_label(node.get(field))) for field in ('part', 'card')]
    aliases = [(field, value) for field, value in aliases if value]
    for field, label in aliases:
        canonical = _clean(view.get('printed_card_portion'))
        if not canonical:
            view['printed_card_portion'] = label
            rule('printed_card_portion_from_' + field, [field, 'printed_card_portion'])
        elif canonical != label:
            audit['issues'].append('conflicting_printed_card_portion_alias')
            rule('conflicting_' + field + '_identity_alias', [field, 'printed_card_portion'])

    card_location = _socket_location(node.get('card'))
    part_alias = _portion_label(node.get('part'))
    if card_location and part_alias:
        old_location = _clean(node.get('location'))
        if not old_location or _grid_location(old_location):
            view['location'] = _clean(node['card'])
            rule('physical_card_location_replaces_grid_location', ['card', 'part', 'location'])
        elif old_location != _clean(node['card']):
            audit['issues'].append('conflicting_physical_card_location_alias')
            rule('conflicting_physical_card_location_alias', ['card', 'part', 'location'])

    technology = _text(node.get('technology'))
    if technology and not _text(node.get('unit')):
        view['unit'] = technology
        rule('unit_from_technology', ['technology', 'unit'])
    elif technology and _clean(node.get('unit')) != _clean(technology):
        audit['warnings'].append('conflicting_unit_technology_alias')

    # A printed single-letter unit is ambiguous across machines. Consult only
    # exact embedded proof; never assume that C or D means frame 01 globally.
    location = _socket_location(view.get('location'))
    if location and len(location[1]) == 1:
        proofs = []
        a1 = node.get('A1')
        if isinstance(a1, dict):
            records = a1.get('records')
            if isinstance(records, list):
                proofs.extend(('A1.records/' + str(i), item) for i, item in enumerate(records) if isinstance(item, dict))
            elif a1.get('board'):
                proofs.append(('A1', a1))
        socket_proof = node.get('socket_listing_evidence')
        if isinstance(socket_proof, dict):
            proofs.append(('socket_listing_evidence', socket_proof))
        printed = _clean(view.get('printed_card_portion'))
        card = _clean(view.get('card_type')) or (printed[:4] if printed else '')
        portion = _clean(view.get('portion')) or (printed[4:] if printed else '')
        supported = []
        for path, proof in proofs:
            board = _clean(proof.get('board'))
            match = re.fullmatch(r'(\d{2}[A-Z])-([A-Z][1-9])', board)
            sockets = proof.get('sockets') or ([proof['socket']] if proof.get('socket') else [])
            if isinstance(sockets, str): sockets = [sockets]
            sockets = {re.sub(r'([0-9])[BT]$', r'\1', _clean(s)) for s in sockets}
            if not match or match[1][-1] != location[1] or match[2] != location[2] or location[3] not in sockets:
                continue
            proof_card = _clean(proof.get('card_type')); proof_portion = _clean(proof.get('portion'))
            if proof_card and card and proof_card != card:
                continue
            if proof_portion and portion and proof_portion != portion:
                continue
            supported.append((path, proof, board))
        boards = {item[2] for item in supported}
        if len(boards) > 1:
            audit['issues'].append('conflicting_frame_context_proofs')
            audit['proof'].extend({'source_field': path, 'value': deepcopy(proof)} for path, proof, _ in supported)
        elif len(boards) == 1:
            board = next(iter(boards))
            explicit_board = _clean(node.get('board'))
            if explicit_board and explicit_board != board:
                audit['issues'].append('conflicting_explicit_board_frame_context')
            else:
                view['location'] = board + location[3] + (location[4] or '')
                rule('physical_frame_from_exact_embedded_listing_proof', ['location', 'board'])
            audit['proof'].extend({'source_field': path, 'value': deepcopy(proof)} for path, proof, _ in supported)
    audit['issues'] = sorted(set(audit['issues']))
    audit['warnings'] = sorted(set(audit['warnings']))
    if audit['issues']:
        view['_identity_adaptation_issues'] = list(audit['issues'])
    return view, audit
