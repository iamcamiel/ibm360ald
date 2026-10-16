"""Parse accepted socket-listing text, preserving literal fields and cell evidence.

Pure parser: no source files, compiled records or inferred circuit pinouts.
"""
from __future__ import annotations
from collections import Counter
import re

RULES=set('─┼┌┐└┘ │')
SOCKET=r'[A-Z�][0-9�]{1,2}[BT]?'
PAGE=r'[A-Z�][A-Z0-9�][0-9�]{3}'


def column_spans(lines):
    patterns=Counter(tuple(i for i,c in enumerate(line) if c=='│') for line in lines if line.count('│')>=3)
    if not patterns:return []
    edges=max(patterns,key=lambda x:(patterns[x],len(x)))
    width=max(map(len,lines),default=0)
    spans=[(a+1,b) for a,b in zip(edges,edges[1:]) if b-a>20]
    if edges[0]>20:spans.insert(0,(0,edges[0]))
    if width-edges[-1]-1>20:spans.append((edges[-1]+1,width))
    return spans


def _kind(text):
    for pattern,kind in [(r'DOUBLE\s*CARD','DOUBLE CARD'),(r'SINGLE\s*CARD','SINGLE CARD'),(r'EMPTY\s*SOCKET|EMPTY','EMPTY SOCKET'),
                         (r'UNUSED\s*SOCKET|UNUSED$','UNUSED'),(r'CONNECTOR|CONN\b','CONNECTOR'),(r'\bCABL','CABL'),(r'\bXOVR','XOVR')]:
        if re.search(pattern,text):return kind
    return 'UNSPECIFIED'


def _continuation_socket(printed, occupied):
    """An unqualified repeated label may abbreviate an active B/T position.

    An explicit opposite qualifier is a different header, never a continuation.
    """
    if printed in occupied:return True
    if re.search(r'\d[BT]$',printed):return False
    return printed in {re.sub(r'(?<=\d)[BT]$','',s) for s in occupied}


def parse_listings(pages):
    records=[];issues=[];active=None;reference=None;mode=None;previous_board=None;span_counts={};orphan=[];tables=[]
    def close():
        nonlocal active,reference,mode
        if active is not None:
            if active['kind']=='UNSPECIFIED' and active['card_type']:active['kind']='CARD (WIDTH NOT PRINTED HERE)'
            if active['kind'] in ('SINGLE CARD','DOUBLE CARD') and not active['card_type']:
                issues.append({'kind':'card_type_not_parsed','record_id':active['id'],'evidence':active['header_source']})
            records.append(active)
        active=None;reference=None;mode=None
    def start(board,socket,kind,evidence):
        nonlocal active,reference,mode
        close()
        active={'id':f"{evidence['scan_id']}:{evidence['column']}:{evidence['row']}",'board':board,'sockets':[socket],'kind':kind,
                'part_number':None,'card_type':None,'references':[],'pins':[],'unused_portions':[],'unused_pins':[],
                'header_source':evidence,'source_spans':[],'raw_lines':[]}
        reference=None;mode=None
    ordered=sorted(enumerate(pages),key=lambda x:(str(x[1].get('board','')),str(x[1].get('page','')),x[0]))
    for ordinal,page in ordered:
        board=page.get('board');lines=page['lines'];page_key=page.get('page',str(ordinal));scan=page.get('scan_id',str(ordinal))
        if board is None:
            candidates={m[1] for line in lines for m in re.finditer(r'BOARD\s+(0[12][A-Z]-[A-Z][0-9])',line)}
            if len(candidates)==1:board=next(iter(candidates))
            else:issues.append({'kind':'board_not_uniquely_readable','page':page_key,'scan_id':scan,'candidates':sorted(candidates)})
        if board!=previous_board:close()
        previous_board=board;spans=column_spans(lines);span_counts[str(scan)]=len(spans)
        if not spans:
            issues.append({'kind':'column_rules_not_found','page':page_key,'scan_id':scan});continue
        for left,right in spans:
            footer=False;plug_list=False;saw_content=False;boundary_separator=False
            header_margins={m.start(1) for line in lines if (m:=re.match(r'^\s{0,10}('+SOCKET+r')\s+(?:SINGLE|DOUBLE|CABL|XOVR|CONNECTOR|EMPTY|UNUSED)',line[left:right]))}
            for row,line in enumerate(lines):
                literal=line[left:right]
                lexical=literal.replace('.',' ') if literal.count('.')>=3 else literal
                if left==0 and row>80:
                    marginal=re.match(r'^(\s{0,3})[A-Z0-9](?=[A-Z]|\s|─|✲|\*)',lexical)
                    if re.match(r'^\s{0,3}000(?=\s|$)',lexical):
                        lexical=re.sub(r'^(\s{0,3})000',lambda m:m[1]+'   ',lexical)
                    if marginal:
                        at=marginal.end()-1;lexical=lexical[:at]+' '+lexical[at+1:]
                text=lexical.strip()
                if not text:continue
                if 'SOLID LOGIC' in line or 'DESIGN AUTOMATION' in line or (row<5 and 'SOCKET LISTING' in line):continue
                evidence={'page':page_key,'scan_id':scan,'row':row,'column':left,'literal':literal}
                listing_socket=None
                # Page headings and boxed footers are preserved by the caller's
                # original row inventory, never interpreted as socket contents.
                if 'SOLID LOGIC' in text or 'DESIGN AUTOMATION' in text:continue
                if 'PLUG LIST' in text or re.search(r'PART NO.*TYPE.*SOCKET',text):
                    close();plug_list=True
                if plug_list:
                    tables.append({'kind':'plug_list','evidence':evidence});continue
                if re.search(r'SOCKET LISTING',text):footer=True;continue
                if footer:continue
                if (left,right)==spans[-1] and row>len(lines)*0.65 and any(c in literal for c in '┌┐└┘'):
                    footer=True;continue
                if re.fullmatch(r'[─┼┌┐└┘│✲* .]{8,}',lexical) and any(c in literal for c in '─✲*.'):
                    if saw_content:close()
                    else:boundary_separator=True
                    continue
                if literal.count('.')>len(literal)*0.65 and len(re.sub(r'[. ]','',literal))<=2:
                    if saw_content:close()
                    continue
                if re.search(r'\b(?:BOARD\s+0[12][A-Z]-|MACH\.|FRAME\b|P\.N\.|IBM CORP|PREV\. ENGR|PRES\. ENGR|DATE\s+\d)',text):continue
                ruled_label=re.fullmatch(r'\s*('+SOCKET+r')[─]{8,}\s*',lexical)
                if ruled_label and active and ruled_label[1] in active['sockets']:
                    close();continue
                repeated=re.match(r'^\s{0,10}('+SOCKET+r')(\s+)(.+)$',lexical.rstrip())
                if not saw_content and not boundary_separator and active and repeated and _continuation_socket(repeated[1],active['sockets']) and not re.search(r'SINGLE|DOUBLE|CABL|XOVR|CONNECTOR',repeated[3]):
                    listing_socket=repeated[1];lexical=' '*repeated.start(3)+repeated[3];text=lexical.strip()
                header=re.match(r'^\s{0,10}('+SOCKET+r')(?:\s+(.*))?$',lexical.rstrip())
                if header:
                    socket,tail=header[1],header[2] or ''
                    bare_allowed=header.start(1)<=3 or header.start(1) in header_margins or (active and socket in active['sockets']) or (active and active['kind']=='DOUBLE CARD' and header.start(1)==active['header_source'].get('socket_column',left)-left)
                    good=(not tail and bare_allowed) or bool(re.search(r'CARD|SINGLE|DOUBLE|CABL|XOVR|SOCKET|CONNECTOR|EMPTY|UNUSED|[0-9�]{7}\s+[0-9�]{4}',tail))
                    if good:
                        kind=_kind(tail)
                        continuation_half=active and active['kind']=='DOUBLE CARD' and len(active['sockets'])==1 and not active['part_number'] and not active['references'] and kind=='UNSPECIFIED' and (not tail or re.search(r'[0-9�]{7}\s+[0-9�]{4}',tail))
                        immediate=active and active['header_source']['scan_id']==scan and active['header_source']['column']==left and row==active['header_source']['row']+1
                        boundary_bare_continuation=active and not saw_content and not boundary_separator and not tail and _continuation_socket(socket,active['sockets'])
                        if boundary_bare_continuation:
                            pass  # Bare physical socket repeats its qualified owner.
                        elif (immediate or continuation_half) and (active['kind']=='DOUBLE CARD' or kind=='DOUBLE CARD') and len(active['sockets'])==1 and socket not in active['sockets']:
                            active['sockets'].append(socket)
                            if kind=='DOUBLE CARD':active['kind']=kind
                        elif active and socket in active['sockets'] and (not tail or 'UNUSED' in tail or re.search(r'[0-9�]{7}\s+[0-9�]{4}',tail)):
                            pass  # Explicit repeated socket at a continuation.
                        else:start(board,socket,kind,{**evidence,'socket_column':left+header.start(1)})
                saw_content=True
                if active is None:
                    # Plug lists and continuation fragments without an earlier
                    # header remain visible; they cannot invent a parent card.
                    if not re.fullmatch(r'[A-Z0-9 .─│┌┐└┘]{1,7}',text):orphan.append(evidence)
                    continue
                active['raw_lines'].append(evidence)
                span={**evidence,'end_column':right}
                if span not in active['source_spans']:active['source_spans'].append(span)
                recognized=bool(header and good)
                if re.fullmatch(r'(?:SINGLE CARD|DOUBLE CARD|CONNECTOR|EMPTY SOCKET|EMPTY|CONN)',text):recognized=True
                if active['kind']=='UNSPECIFIED' and _kind(text)!='UNSPECIFIED':active['kind']=_kind(text);recognized=True
                part=re.search(r'(?<![A-Z0-9�])([0-9�]{7})(?:\s+([0-9�]{4})(?![A-Z0-9�]))?',lexical)
                if part:
                    for field,value in [('part_number',part[1]),('card_type',part[2])]:
                        if value:
                            if active[field] not in (None,value):
                                problem={'kind':'conflicting_printed_field','record_id':active['id'],'field':field,'before':active[field],'after':value,'evidence':evidence}
                                issues.append(problem);active.setdefault('issues',[]).append(problem)
                                active.setdefault('ambiguous_fields',{}).setdefault(field,[active[field]]).append(value)
                                active[field]=None
                            elif field not in active.get('ambiguous_fields',{}):active[field]=value
                    recognized=True
                if re.fullmatch(r'[0-9�]{4}',text) and active['kind'] in ('SINGLE CARD','DOUBLE CARD') and not active['card_type']:
                    active['card_type']=text;recognized=True
                if 'UNUSED PORTION' in text:mode='unused_portions';reference=None;recognized=True
                elif 'UNUSED PIN' in text:mode='unused_pins';reference=None;recognized=True
                elif 'UNUSED SOCKET' in text:mode='unused_sockets';reference=None;recognized=True
                dest=re.search(r'GOES TO\s+(\S+)',text)
                if dest:active['destination']=dest[1];reference=None;recognized=True
                if active['kind'] in ('CABL','XOVR','CONNECTOR'):
                    wire=re.fullmatch(r'\s*(?:'+SOCKET+r'\s+)?('+PAGE+r')\s*([A-Z�]{2})\s*',lexical)
                    if wire:active['connector_listing']=wire[1];active['wire_code']=wire[2];recognized=True
                # Physical connector labels are not restricted to SLT B/D pins.
                pin=re.fullmatch(r'\s*(?:('+SOCKET+r')[ .]+)?([A-Z�][0-9�]{2})\s+('+PAGE+r'[A-Z0-9�.]+)\s*',lexical)
                if pin:
                    active['pins'].append({'pin':pin[2],'printed_socket':pin[1],'listing_socket':listing_socket,'ALD_reference':pin[3],'evidence':evidence});recognized=True
                unreferenced_pin=re.fullmatch(r'\s*(?:('+SOCKET+r')[ .]+)?([A-Z�][0-9�]{2})\s*',lexical)
                if unreferenced_pin and mode!='unused_pins' and active['kind'] in ('CABL','XOVR','CONNECTOR'):
                    active['pins'].append({'pin':unreferenced_pin[2],'printed_socket':unreferenced_pin[1],'listing_socket':listing_socket,'ALD_reference':None,'reference_status':'no_reference_printed','evidence':evidence});recognized=True
                if not pin:
                    malformed=re.fullmatch(r'\s*(?:('+SOCKET+r')[ .]+)?([A-Z�][0-9�]{2})\s+([A-Z�][A-Z0-9�]{4}[A-Z0-9�.]+)\s*',lexical)
                    if malformed:
                        active['pins'].append({'pin':malformed[2],'printed_socket':malformed[1],'listing_socket':listing_socket,'ALD_reference':malformed[3],'evidence':evidence})
                        issues.append({'kind':'malformed_printed_ALD_reference','record_id':active['id'],'literal_reference':malformed[3],'evidence':evidence});recognized=True
                is_card=active['card_type'] is not None or active['kind'] in ('SINGLE CARD','DOUBLE CARD','UNSPECIFIED')
                pg=re.search(r'(?<![A-Z0-9�])('+PAGE+r')\s+((?:[A-Z0-9�]{1,2}\s*)+)$',lexical.rstrip()) if is_card and mode not in ('unused_portions','unused_pins') else None
                if pg:
                    reference={'page':pg[1],'portions':[],'evidence':[]};active['references'].append(reference)
                if reference and (pg or re.fullmatch(r'\s{6,}(?:[A-Z0-9�]{1,2}\s*)+',lexical)):
                    tail=pg[2] if pg else lexical
                    reference['portions'].extend(re.findall(r'(?<![A-Z0-9�])[A-Z0-9�]{1,2}(?![A-Z0-9�])',tail));reference['evidence'].append(evidence);recognized=True
                elif mode=='unused_portions' and text.split() and all(re.fullmatch(r'[A-Z0-9�]{1,2}',token) for token in text.split()):
                    active['unused_portions'].extend(text.split());recognized=True
                elif mode=='unused_pins' and re.fullmatch(r'(?:(?:'+SOCKET+r')\s+)?[A-Z�][0-9�]{2}',text):
                    active['unused_pins'].append({'literal':text,'evidence':evidence});recognized=True
                elif mode=='unused_sockets' and re.fullmatch(r'(?:'+SOCKET+r'\s*)+',text):
                    active.setdefault('unused_sockets',[]).extend(text.split());recognized=True
                if not recognized and len(text)>1:
                    issues.append({'kind':'unparsed_significant_line','record_id':active['id'],'evidence':evidence})
    close()
    issues.extend({'kind':'orphan_significant_line','evidence':e} for e in orphan)
    return {'records':records,'issues':issues,'tables':tables,'coverage':{'scans':len(pages),'column_spans_per_scan':span_counts,
            'logical_records':len(records),'card_records':sum(r['card_type'] is not None and 'CARD' in r['kind'] for r in records),
            'portion_claims':sum(len(ref['portions']) for r in records for ref in r['references']),
            'unparsed_significant_lines':sum(x['kind']=='unparsed_significant_line' for x in issues),
            'orphan_significant_lines':len(orphan)}}
