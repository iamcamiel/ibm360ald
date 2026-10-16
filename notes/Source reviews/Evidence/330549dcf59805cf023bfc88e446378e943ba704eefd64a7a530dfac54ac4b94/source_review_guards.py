"""Reject newly lost printed pin marks and newly stale physical-contact mirrors.

The guard reads declarations and model snapshots only. It neither infers a
reading nor repairs a model. Existing unrelated uncertainties remain unchanged.
"""
from __future__ import annotations

import re

CONTACT = re.compile(r'\d*(?P<pin>[BDGJ](?:0[2-9]|1[0-3]))[✲*]?T?\Z')
BARE_CONTACT = re.compile(r'[BDGJ](?:0[2-9]|1[0-3])\Z')
PRINTED_FIELDS = ('pin', 'printed_pin', 'printed_label')


def physical_contact(value):
    match = CONTACT.fullmatch(str(value).strip()) if value is not None else None
    return match.group('pin') if match else None


def has_asterisk(value):
    return isinstance(value, str) and any(mark in value for mark in ('✲', '*'))


def _same(a, b):
    # bool and int compare equal in Python but are different source JSON values.
    return type(a) is type(b) and a == b


def validate_pin_edits(before_model, after_model, page_intent):
    """Return explicit violations for changed pin fields in a page model.

    An intentional printed-asterisk removal requires annotation_drop_reason on
    the exact matching JSON pointer patch and nonempty page-level evidence.
    No global rationale or reason on another field authorizes that removal.
    """
    issues = []
    patches = {p.get('pointer'): p for p in page_intent.get('json_patches', [])}
    old_nodes = before_model.get('nodes', [])
    new_nodes = after_model.get('nodes', [])
    for ni, new_node in enumerate(new_nodes):
        # Reordering/replacing node inventories is outside this local guard's
        # inference remit; matching indices must still identify the same block.
        old_node = old_nodes[ni] if ni < len(old_nodes) else {}
        if old_node.get('id') != new_node.get('id'):
            old_node = next((n for n in old_nodes if n.get('id') == new_node.get('id')), {})
        old_pins = old_node.get('pins', [])
        for pi, new_pin in enumerate(new_node.get('pins', [])):
            old_pin = old_pins[pi] if pi < len(old_pins) else {}
            if _same(old_pin, new_pin):
                continue
            base = f'/nodes/{ni}/pins/{pi}'
            for field in PRINTED_FIELDS:
                old, new = old_pin.get(field), new_pin.get(field)
                if has_asterisk(old) and not has_asterisk(new):
                    pointer = base + '/' + field
                    patch = patches.get(pointer, {})
                    reason = patch.get('annotation_drop_reason')
                    authorized = isinstance(reason, str) and bool(reason.strip()) and bool(page_intent.get('evidence'))
                    if not authorized:
                        issues.append({'kind': 'printed_pin_annotation_removed_without_explicit_evidence',
                                       'pointer': pointer, 'node': new_node.get('id'),
                                       'before': old, 'after': new,
                                       'requirement': 'Nonempty annotation_drop_reason on this exact patch and page evidence.'})
            # Only a changed contact pair can introduce a new mirror problem.
            # A correction elsewhere must not resurrect a preexisting mismatch.
            old_pair = (old_pin.get('pin'), old_pin.get('physical_pin'))
            new_pair = (new_pin.get('pin'), new_pin.get('physical_pin'))
            if _same(old_pair, new_pair) or new_pair[1] is None:
                continue
            pin_contact = physical_contact(new_pair[0])
            mirror_contact = physical_contact(new_pair[1])
            old_contacts = tuple(physical_contact(value) for value in old_pair)
            if pin_contact and mirror_contact and pin_contact != mirror_contact and (pin_contact, mirror_contact) != old_contacts:
                issues.append({'kind': 'new_stale_physical_contact_mirror', 'pointer': base + '/physical_pin',
                               'node': new_node.get('id'), 'pin': new_pair[0],
                               'physical_pin': new_pair[1], 'expected_physical_contact': pin_contact,
                               'before_pin': old_pair[0], 'before_physical_pin': old_pair[1]})
            if mirror_contact and not BARE_CONTACT.fullmatch(str(new_pair[1])) and old_pair[1] != new_pair[1]:
                issues.append({'kind': 'physical_contact_mirror_has_printed_annotation',
                               'pointer': base + '/physical_pin', 'node': new_node.get('id'),
                               'physical_pin': new_pair[1], 'expected_bare_contact': mirror_contact})
    return issues
