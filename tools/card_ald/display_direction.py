"""Pure exterior LABEL direction; this never changes electrical gate roles.

The only K-specific display case is a single, physical, output-side terminal
with no other block incidences. Shared nets retain the ordinary driver rule.
"""
import re
from card_source import logical_gate_terminal
PIN=re.compile(r'[BDGJ](?:0[2-9]|1[0-3])\Z')

def exterior_display_side(contacts, exterior_pin=None):
    ports=list(contacts)
    if any(not isinstance(p,dict)or p.get('side')not in ('input','output')for p in ports):
        raise ValueError('Exterior display classification requires side-scoped block terminals')
    logical=[logical_gate_terminal(p)for p in ports]
    if any(p['side']=='output'and gate for p,gate in zip(ports,logical)):
        return 'output'
    if len(ports)==1:
        p=ports[0];pin=p.get('pin')
        if (p['side']=='output'and not logical[0]and p.get('border_control')=='K'
                and isinstance(pin,str)and PIN.fullmatch(pin)and pin==exterior_pin):
            return 'output'
    return 'input'
