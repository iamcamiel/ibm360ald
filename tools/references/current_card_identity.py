"""Private exact identity alias candidate; no source mutation or inferred frames."""
import re
from copy import deepcopy

COMBINED = re.compile(r'([0-9]{4})([A-Z0-9]{2})\Z')

def catalogue_identity(node):
    """Return split fields only if all explicit identity representations agree."""
    evidence = []
    for key in ('card', 'part', 'printed_card_portion'):
        value = node.get(key)
        match = COMBINED.fullmatch(value) if isinstance(value, str) else None
        if match:
            evidence.append((key, match.group(1), match.group(2)))
    if not evidence:
        return deepcopy(node), {'status': 'unchanged', 'source_fields': {}}
    identities = {(card, portion) for _, card, portion in evidence}
    for key, index in (('card_type', 0), ('portion', 1)):
        value = node.get(key)
        if value not in (None, '') and any(value != identity[index] for identity in identities):
            return deepcopy(node), {'status': 'conflict', 'source_fields': {k: node.get(k) for k in ('card_type','portion','card','part','printed_card_portion')}}
    printed = node.get('printed_card_portion')
    if printed not in (None, '') and any(printed != card + portion for card, portion in identities):
        return deepcopy(node), {'status': 'conflict', 'source_fields': {k: node.get(k) for k in ('card_type','portion','card','part','printed_card_portion')}}
    if len(identities) != 1:
        return deepcopy(node), {'status': 'conflict', 'source_fields': {k: node.get(k) for k, _, _ in evidence}}
    card, portion = next(iter(identities))
    view = deepcopy(node)
    filled = []
    for key, value in (('card_type', card), ('portion', portion), ('printed_card_portion', card + portion)):
        if view.get(key) in (None, ''):
            view[key] = value; filled.append(key)
    return view, {'status': 'adapted' if filled else 'unchanged', 'filled_fields': filled,
                  'source_fields': {k: node.get(k) for k, _, _ in evidence}}
