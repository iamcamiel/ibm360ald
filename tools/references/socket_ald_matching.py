"""Pure, conservative socket-listing to ALD block identity matching.

No source reads, writes, fuzzy corrections, circuit assumptions or card-specific
exceptions. A concrete source wrapper accompanies every match and candidate.
"""
from __future__ import annotations
from copy import deepcopy
import re

ALIASES = {c:'02'+c for c in 'ABCEKL'}
UNKNOWN = '�?'


def _literal(value):
    return str(value).strip() if value is not None else ''


def _clean(value):
    return re.sub(r'\s+', '', _literal(value)).upper()


def _socket(value):
    value = _clean(value)
    m = re.fullmatch(r'([A-Z](?:[1-9]|1[0-9]))([BT])?', value)
    return m[1] if m else None


def _board(value):
    value = _clean(value)
    m = re.fullmatch(r'(\d{2}[A-Z]|[A-Z])-([A-Z][1-9])',value)
    if not m:return None
    unit = ALIASES.get(m[1],m[1])
    if len(unit)!=3:return None
    return unit+'-'+m[2]


def normalize_location(value=None, *, board=None, sockets=None):
    """Return exact board and physical socket members, preserving literals.

    Double-card membership must be supplied; adjacent sockets are never guessed.
    A socket B/T suffix denotes a position, while full frame/unit codes remain
    significant (01A is not 02A).
    """
    issues=[];parsed_board=None;members=[]
    if _literal(value):
        m=re.fullmatch(r'(\d{2}[A-Z]|[A-Z])-([A-Z][1-9])([A-Z](?:1[0-9]|[1-9]))([BT])?',_clean(value))
        if m:
            parsed_board=_board(m[1]+'-'+m[2]);members=[m[3]]
        if not parsed_board:issues.append('unreadable_or_invalid_location')
    separate=_board(board) if _literal(board) else None
    if _literal(board) and separate is None:issues.append('unreadable_or_invalid_board')
    if separate and parsed_board and separate!=parsed_board:issues.append('conflicting_location_board')
    chosen=separate or parsed_board
    if sockets is not None:
        raw=[sockets] if isinstance(sockets,str) else list(sockets)
        listed=[_socket(s) for s in raw]
        if any(s is None for s in listed):issues.append('unreadable_or_invalid_socket')
        listed=[s for s in listed if s]
        if members and listed and not set(members).intersection(listed):issues.append('conflicting_location_socket')
        members=listed or members
    if not chosen:issues.append('missing_board')
    if not members:issues.append('missing_socket')
    return {'board':chosen,'sockets':sorted(set(members)),
            'literal':{'location':value,'board':board,'sockets':deepcopy(sockets)},
            'issues':sorted(set(issues)), 'resolved':not issues}


def _field(value,pattern):
    text=_clean(value)
    return text if text and re.fullmatch(pattern,text) else None


def normalize_identity(raw):
    """Normalize raw node/claim fields without selecting conflicting mirrors."""
    issues=list(raw.get('_identity_adaptation_issues',[]))
    members=next((raw.get(k) for k in ['physical_sockets','occupied_sockets','sockets'] if raw.get(k)),None)
    location=normalize_location(raw.get('location'),board=raw.get('board'),sockets=members)
    printed=_clean(raw.get('printed_card_portion'))
    split_card=_clean(raw.get('card_type'));split_portion=_clean(raw.get('portion'))
    pc=printed[:4] if len(printed)>4 else ''
    pp=printed[4:] if len(printed)>4 else ''
    card_values=[x for x in [split_card,pc] if x]
    portion_values=[x for x in [split_portion,pp] if x]
    def agree(values,pattern,name):
        valid=[x for x in values if re.fullmatch(pattern,x)]
        if len(set(valid))>1:issues.append('conflicting_'+name)
        if any(not re.fullmatch(pattern,x) for x in values):issues.append('unreadable_or_invalid_'+name)
        if not values:issues.append('missing_'+name)
        if len(set(valid))==1 and len(valid)==len(values):return valid[0]
        return None
    card=agree(card_values,r'\d{4}','card_type')
    portion=agree(portion_values,r'[A-Z0-9]{1,3}','portion')
    if printed and len(printed)<=4:issues.append('unreadable_or_invalid_printed_card_portion')
    return {'location':location,'card_type':card,'portion':portion,
            'literals':{k:deepcopy(raw.get(k)) for k in ['location','board','sockets','physical_sockets','occupied_sockets','card_type','portion','printed_card_portion'] if k in raw},
            'card_type_literals':card_values,'portion_literals':portion_values,
            'issues':sorted(set(issues+location['issues']))}


def _mask_compatible(a,b):
    """Unknown glyphs may match one cell, never arbitrary substring lengths."""
    return len(a)==len(b) and all(x==y or x in UNKNOWN or y in UNKNOWN for x,y in zip(a,b))


def _axis(left,right,name):
    if name=='location':
        a,b=left['location'],right['location']
        if a['resolved'] and b['resolved']:
            return a['board']==b['board'] and bool(set(a['sockets'])&set(b['sockets']))
        return None
    a,b=left[name],right[name]
    return a==b if a is not None and b is not None else None


def _compatible(left,right,name):
    status=_axis(left,right,name)
    if status is not None:return status
    if name=='location':
        a,b=left['location'],right['location']
        if a['board'] and b['board'] and a['board']!=b['board']:return False
        if a['sockets'] and b['sockets'] and not set(a['sockets'])&set(b['sockets']):return False
        return True
    # Conflicts cannot be resolved by choosing one of the mirrors.
    if 'conflicting_'+name in left['issues']+right['issues']:return False
    aa=left[name+'_literals'];bb=right[name+'_literals']
    return all(_mask_compatible(a,b) for a in aa for b in bb) if aa and bb else True


def prepare_nodes(nodes):
    """Cache identity parsing once when many claims share the same nodes.

    Returned wrappers are shallow copies. Their raw nodes are never mutated;
    match results still contain a detached copy of the complete input binding.
    """
    return [dict(w, _socket_matching_identity=normalize_identity(w.get('matching_node',w.get('node',{})))) for w in nodes]


def _partial_supported(left,right):
    for name in ['card_type','portion']:
        for a in left[name+'_literals']:
            for b in right[name+'_literals']:
                if _mask_compatible(a,b) and any(x==y and x not in UNKNOWN for x,y in zip(a,b)):
                    return True
    a,b=left['location'],right['location']
    return bool(a['board'] and a['board']==b['board'])


def _entry(wrapper,actual,axes):
    return {'binding':deepcopy({k:v for k,v in wrapper.items() if k!='_socket_matching_identity'}),
            'identity':deepcopy(actual),'axes':axes,
            'matching_axes':[k for k,v in axes.items() if v is True],
            'differing_axes':[k for k,v in axes.items() if v is False],
            'unresolved_axes':[k for k,v in axes.items() if v is None]}


def match_claim(claim,nodes):
    """Classify one listing claim against source node wrappers on its page.

    Exact and repeated exact matches are resolved identities. Candidate-only
    classifications are review findings, not permission to alter source text.
    """
    wanted=normalize_identity(claim);page=_literal(claim.get('page')).upper()
    exact=[];candidates=[];unresolved=[];same_page=0;coverage=[]
    for wrapper in nodes:
        if not page or _literal(wrapper.get('page')).upper()!=page:continue
        same_page+=1
        actual=wrapper.get('_socket_matching_identity') or normalize_identity(wrapper.get('matching_node',wrapper.get('node',{})))
        if wrapper.get('source_page_conflict'):
            actual=dict(actual,issues=actual['issues']+['source_page_conflict'])
        axes={k:_axis(wanted,actual,k) for k in ['location','card_type','portion']}
        if all(v is True for v in axes.values()) and not wanted['issues'] and not actual['issues']:
            exact.append(_entry(wrapper,actual,axes))
        elif sum(v is True for v in axes.values())>=2:
            candidates.append(_entry(wrapper,actual,axes))
        elif (any(v is None for v in axes.values())
              and (any(v is True for v in axes.values()) or _partial_supported(wanted,actual))
              and all(_compatible(wanted,actual,k) for k in axes)):
            unresolved.append(_entry(wrapper,actual,axes))
        if wrapper.get('source_page_conflict'):
            coverage.append({'code':'source_page_conflict','scan_id':wrapper.get('scan_id'),
                             'model_path':wrapper.get('model_path'),'node_pointer':wrapper.get('node_pointer'),
                             'filename_page':wrapper.get('page'),'model_page_literal':wrapper.get('model_page_literal')})
    if exact:classification='exact' if len(exact)==1 else 'multiple_exact'
    elif candidates:
        signatures={(c['identity']['location']['board'],tuple(c['identity']['location']['sockets']),c['identity']['card_type'],c['identity']['portion']) for c in candidates}
        bad={tuple(c['differing_axes']) for c in candidates}
        if all(c['unresolved_axes'] for c in candidates):classification='unresolved_print'
        elif len(signatures)>1 or len(bad)>1:classification='ambiguous_candidates'
        elif len(next(iter(bad)))==1:classification=next(iter(bad))[0]+'_mismatch'
        else:classification='unresolved_print'
    elif unresolved or wanted['issues']:classification='unresolved_print'
    else:classification='missing_block'
    return {'classification':classification,'claim':deepcopy(claim),'normalized_claim':wanted,
            'matches':exact,'candidates':candidates+unresolved,'same_page_nodes':same_page,
            'coverage_issues':coverage,
            'source_changes_applied':False}
