"""Reviewer-owned identity derivation; no production adapter/matcher imports."""
from copy import deepcopy
import re

def clean(value):return re.sub(r'\s+','',str(value if value is not None else '')).upper()

def derive(raw):
    """Reproduce aliases from literal source fields and explicit embedded proofs."""
    view=dict(raw);rules=[];fields={};proofs=[];issues=[];warnings=[]
    def used(rule,names):
        rules.append(rule)
        fields.update({name:deepcopy(raw.get(name)) for name in names})
    def combined(value):
        x=clean(value)
        if len(x)==7 and x.startswith('580') and x.isdigit():return None
        return x if re.fullmatch(r'[A-Z0-9�]{5,7}',x) and re.search(r'[0-9�]',x[:4]) else None
    physical=lambda value:re.fullmatch(r'((?:\d\d)?[A-Z])-([A-Z][1-9])([A-Z](?:1[0-9]|[1-9]))([BT])?',clean(value))
    for name in ['part','card']:
        value=combined(raw.get(name))
        if not value:continue
        old=clean(view.get('printed_card_portion'))
        if not old:view['printed_card_portion']=value;used('printed_card_portion_from_'+name,[name,'printed_card_portion'])
        elif old!=value:issues.append('conflicting_printed_card_portion_alias');used('conflicting_'+name+'_identity_alias',[name,'printed_card_portion'])
    if physical(raw.get('card')) and combined(raw.get('part')):
        old=clean(raw.get('location'))
        if not old or re.fullmatch(r'[1-9][A-Z]-[A-Z]{2}',old):
            view['location']=clean(raw['card']);used('physical_card_location_replaces_grid_location',['card','part','location'])
        elif old!=clean(raw['card']):issues.append('conflicting_physical_card_location_alias');used('conflicting_physical_card_location_alias',['card','part','location'])
    if str(raw.get('technology') or '').strip():
        if not str(raw.get('unit') or '').strip():view['unit']=str(raw['technology']).strip();used('unit_from_technology',['technology','unit'])
        elif clean(raw.get('technology'))!=clean(raw.get('unit')):warnings.append('conflicting_unit_technology_alias')
    loc=physical(view.get('location'))
    if loc and len(loc[1])==1:
        candidates=[];a1=raw.get('A1')
        if isinstance(a1,dict):
            if isinstance(a1.get('records'),list):candidates += [('A1.records/'+str(i),p) for i,p in enumerate(a1['records']) if isinstance(p,dict)]
            elif a1.get('board'):candidates.append(('A1',a1))
        if isinstance(raw.get('socket_listing_evidence'),dict):candidates.append(('socket_listing_evidence',raw['socket_listing_evidence']))
        printed=clean(view.get('printed_card_portion'));card=clean(view.get('card_type')) or printed[:4];portion=clean(view.get('portion')) or printed[4:]
        supported=[]
        for name,p in candidates:
            board=clean(p.get('board'));m=re.fullmatch(r'(\d\d[A-Z])-([A-Z][1-9])',board)
            sockets=p.get('sockets') or ([p['socket']] if p.get('socket') else [])
            if isinstance(sockets,str):sockets=[sockets]
            sockets={re.sub(r'(?<=\d)[BT]$','',clean(s)) for s in sockets}
            if not m or m[1][-1]!=loc[1] or m[2]!=loc[2] or loc[3] not in sockets:continue
            if clean(p.get('card_type')) and card and clean(p['card_type'])!=card:continue
            if clean(p.get('portion')) and portion and clean(p['portion'])!=portion:continue
            supported.append((name,p,board))
        boards={x[2] for x in supported}
        if len(boards)>1:issues.append('conflicting_frame_context_proofs')
        elif len(boards)==1:
            board=next(iter(boards))
            if clean(raw.get('board')) and clean(raw['board'])!=board:issues.append('conflicting_explicit_board_frame_context')
            else:view['location']=board+loc[3]+(loc[4] or '');used('physical_frame_from_exact_embedded_listing_proof',['location','board'])
        if boards:proofs=[{'source_field':name,'value':deepcopy(p)} for name,p,_ in supported]
    issues=sorted(set(issues));warnings=sorted(set(warnings))
    if issues:view['_identity_adaptation_issues']=issues
    return view,{'rules':rules,'source_fields':fields,'proof':proofs,'issues':issues,'warnings':warnings}

def identity(raw):
    """Return comparison axes and exact issue names, retaining CPU aliases."""
    def board(value):
        m=re.fullmatch(r'(\d\d[A-Z]|[A-Z])-([A-Z][1-9])',clean(value))
        if not m:return None
        unit='02'+m[1] if m[1] in 'ABCEKL' else m[1]
        return unit+'-'+m[2] if len(unit)==3 else None
    loc=clean(raw.get('location'));m=re.fullmatch(r'(\d\d[A-Z]|[A-Z])-([A-Z][1-9])([A-Z](?:1[0-9]|[1-9]))([BT])?',loc) if loc else None
    locationissues=[];parsed=board(m[1]+'-'+m[2]) if m else None;members=[m[3]] if m else []
    if loc and not parsed:locationissues.append('unreadable_or_invalid_location')
    explicit=board(raw.get('board')) if clean(raw.get('board')) else None
    if clean(raw.get('board')) and explicit is None:locationissues.append('unreadable_or_invalid_board')
    if explicit and parsed and explicit!=parsed:locationissues.append('conflicting_location_board')
    chosen=explicit or parsed
    values=next((raw.get(k) for k in ['physical_sockets','occupied_sockets','sockets'] if raw.get(k)),None)
    if values is not None:
        if isinstance(values,str):values=[values]
        listed=[]
        for value in values:
            sm=re.fullmatch(r'([A-Z](?:1[0-9]|[1-9]))[BT]?',clean(value))
            if not sm:locationissues.append('unreadable_or_invalid_socket')
            else:listed.append(sm[1])
        if members and listed and not set(members)&set(listed):locationissues.append('conflicting_location_socket')
        members=listed or members
    if not chosen:locationissues.append('missing_board')
    if not members:locationissues.append('missing_socket')
    issues=list(raw.get('_identity_adaptation_issues',[]))+locationissues
    printed=clean(raw.get('printed_card_portion'));cards=[clean(raw.get('card_type'))];parts=[clean(raw.get('portion'))]
    if len(printed)>4:cards.append(printed[:4]);parts.append(printed[4:])
    elif printed:issues.append('unreadable_or_invalid_printed_card_portion')
    def agreed(values,pattern,name):
        values=[v for v in values if v];valid=[v for v in values if re.fullmatch(pattern,v)]
        if len(set(valid))>1:issues.append('conflicting_'+name)
        if len(valid)!=len(values):issues.append('unreadable_or_invalid_'+name)
        if not values:issues.append('missing_'+name)
        return valid[0] if valid and len(set(valid))==1 and len(valid)==len(values) else None
    card=agreed(cards,r'\d{4}','card_type');portion=agreed(parts,r'[A-Z0-9]{1,3}','portion')
    return {'board':chosen,'sockets':sorted(set(members)),'location_resolved':not locationissues,'card_type':card,'portion':portion,'issues':sorted(set(issues))}

def axes(a,b):
    return {'location':a['board']==b['board'] and bool(set(a['sockets'])&set(b['sockets'])) if a['location_resolved'] and b['location_resolved'] else None,
            'card_type':a['card_type']==b['card_type'] if a['card_type'] is not None and b['card_type'] is not None else None,
            'portion':a['portion']==b['portion'] if a['portion'] is not None and b['portion'] is not None else None}

def fully_resolved(i):return not i['issues'] and i['location_resolved'] and bool(i['card_type'] and i['portion'])

