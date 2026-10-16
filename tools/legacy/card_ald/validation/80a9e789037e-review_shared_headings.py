"""Read-only independent review of common Card-ALD headings and unchanged bodies."""
import ast,csv,datetime,hashlib,json,sys
from pathlib import Path
from collections import defaultdict
HERE=Path(__file__).parent;ROOT=Path('D:/Github/IBM360/ibm360ald')
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import generate_card as G
import build_card_data as B
sys.path.insert(0,str(HERE/'compact-r-review'))
from trace_compact import trace

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def boxes(spec):return {b['portion']:{k:v for k,v in b.items() if k!='ports'}|{'ports':{p['id']:p for p in b['ports']}} for b in spec['boxes']}

def expected_header(spec,number):
    facts=spec['header'];pins=spec['exterior_pins'];power=spec['power_contacts'];banks='BD' if facts['card_width']=='SINGLE CARD' else 'BDGJ'
    unused=sorted({bank+f'{n:02}' for bank in banks for n in range(2,14)}-set(power)-{p['pin'] for p in pins})
    levels=['GROUND','+3V','-3V','+6V'];powertext='; '.join(level+' '+' '.join(sorted(pin for pin,v in power.items() if v==level)) for level in levels if level in power.values())
    provisional=defaultdict(list)
    for fact in facts['provisional_forms']:provisional[fact['circuit_identifier']].append(fact['portion'])
    text=', '.join('/'.join(sorted(parts))+' '+unit for unit,parts in sorted(provisional.items())) or 'NONE'
    variant='VARIANT '+f'{number:02}' if number else 'CANONICAL'
    inputs=sum(p['side']=='input' for p in pins);outputs=sum(p['side']=='output' for p in pins)
    return [f"CARD-ALD {facts['part_number']}  {facts['card_width']}  {variant}",
            f"PORTIONS: {len(spec['boxes'])}; SIGNAL CONTACTS: {len(pins)} ({inputs} INPUT, {outputs} OUTPUT)",
            'POWER: '+powertext,
            'UNCONNECTED SIGNAL CONTACTS: '+(', '.join(unused)+' (POSSIBLY UNUSED)' if unused else 'NONE'),
            'PROVISIONAL CIRCUIT FORMS: '+text,
            'SYMBOLS: '+('OBSERVED NOTATION VARIANT '+f'{number:02}' if number else 'SLT MANUAL STANDARD'),
            f"SOURCE: {facts['reviewed_occurrences']} REVIEWED OCCURRENCES ON {facts['reviewed_pages']} PAGES"]

def main():
    predecessor=HERE.parent/'Shared header predecessor.json';history=Path(read(predecessor)['path']);archive=read(history/'Archive bindings.json')
    archivefiles={entry['original_path']:entry for entry in archive['files']};checks=[];details={};paths=[predecessor,history/'Archive bindings.json'];output_count=0
    sources=[ROOT/'tools/card_ald'/name for name in ['generate_card.py','build_card_data.py','adopt_card_layout.py']];start=[bind(p) for p in sources]
    def ck(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    ck('Predecessor archive preserves every bound file exactly',all(sha(ROOT/entry['path'])==entry['sha256'] for entry in archive['files']))
    manualpath=ROOT/'notes/Card-ALD/Manual canonical circuit forms.json';manual=read(manualpath)
    for card in ['0141','4191','4633','4634']:
        defpath=ROOT/'json/Card-ALD/definitions'/(card+'.json');overlaypath=ROOT/'json/Card-ALD/build-overrides'/(card+'.json');catalogpath=ROOT/'json/Card types current'/(card+'.json')
        beforepath=ROOT/archivefiles[f'json/Card-ALD/definitions/{card}.json']['path'];before=read(beforepath);spec=read(defpath);overlay=read(overlaypath);catalog=read(catalogpath)
        facts=spec['header'];occ=catalog['diagram_occurrences'];expectedprovisional=sorted((b['portion'],b['circuit_identifier']) for b in spec['boxes'] if manual['circuits'].get(b['circuit_identifier'],{}).get('definition_status')=='not_found_in_supplied_manual')
        ck(card+' header facts match current independently read source catalog',catalog['full_part_numbers_observed']==[facts['part_number']] and catalog['physical_card_widths_observed']==[facts['card_width']] and facts['reviewed_occurrences']==len(occ) and facts['reviewed_pages']==len({o['page'] for o in occ}) and all(o['source_reviewed'] for o in occ) and expectedprovisional==sorted((p['portion'],p['circuit_identifier']) for p in facts['provisional_forms']),facts)
        ck(card+' shared metadata preserved in reviewed build supplement',overlay['header']==facts and facts['schema']=='card-ald-header-v1')
        ck(card+' all box/port/pin/polarity/compact coordinates and wire metadata unchanged',boxes(before)==boxes(spec) and all(before[k]==spec[k] for k in ['canvas','wiring','exterior_pins','nets','power_contacts','canonical_line_ending']))
        oldforms={v['number']:{k:v[k] for k in ['box_overrides','line_ending'] if k in v} for v in before['variants']};newforms={v['number']:{k:v[k] for k in ['box_overrides','line_ending'] if k in v} for v in spec['variants']}
        ck(card+' every numbered variant function and decoration unchanged',oldforms==newforms)
        ck(card+' no literal heading overrides remain and body annotations unchanged',all(a['row']>=7 for a in spec['annotations']) and not any(v.get('annotation_overrides') for v in spec['variants']) and [a for a in before['annotations'] if a['row']>=7]==spec['annotations'])
        outputs,val=G.build(spec);output_count+=len(outputs);bodyerrors=[];headerrors=[]
        for name,raw in outputs.items():
            number=int(name[:-4].split('-')[1]) if '-' in name else 0
            original=ROOT/archivefiles['Card-ALD/'+name]['path'];published=ROOT/'Card-ALD'/name
            if raw.splitlines(keepends=True)[7:]!=original.read_bytes().splitlines(keepends=True)[7:]:bodyerrors.append(name)
            if raw!=published.read_bytes() or raw.decode('utf8').splitlines()[:7]!=expected_header(spec,number):headerrors.append(name)
            paths.extend([original,published])
        ck(card+' all bytes below seven-line heading unchanged',not bodyerrors,bodyerrors)
        ck(card+' all seven lines use common factual template and correct filename identity',not headerrors,headerrors)
        rebuilt,report=B.build(card)
        ck(card+' default source-model builder and renderer reproduce every current byte',rebuilt is not None and rebuilt['header']==facts and G.build(rebuilt)[0]==outputs)
        ck(card+' independent electrical trace preserves all accepted tree identities',set(trace(before))==set(trace(spec))=={tuple(net) for net in spec['nets']} and all(v['cycle_rank']==0 for v in trace(spec).values()))
        receiptpath=ROOT/'notes/Card-ALD/Generation'/(card+'.json');receipt=read(receiptpath)
        ck(card+' generation receipt hashes identify new headers/current definitions',sha(ROOT/receipt['definition']['path'])==receipt['definition']['sha256'] and sha(ROOT/receipt['renderer']['path'])==receipt['renderer']['sha256'] and all(sha(ROOT/e['path'])==e['sha256'] for e in receipt['files']))
        details[card]=dict(files=len(outputs),source_occurrences=len(occ),source_pages=len({o['page'] for o in occ}),canonical_heading=expected_header(spec,0),compact_terminations=val['compact_terminations'])
        paths.extend([defpath,overlaypath,catalogpath,beforepath,receiptpath])
    ck('Exactly124 canonical and numbered drawings independently checked',output_count==124)
    tree=ast.parse(sources[0].read_text(encoding='utf-8-sig'));heading=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='header_lines');literals={n.value for n in ast.walk(heading) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
    ck('Shared formatter contains no per-card heading branches',not {'0141','4191','4633','4634','5800141','5804191','5804633','5804634'}&literals)
    sourcebaseline=HERE/'compact-r-review/ALD source baseline before card promotion.json';baseline=read(sourcebaseline);current={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in (ROOT/'ALD').rglob('*') if p.is_file()}
    ck('All2329 source ALD files remain unchanged',current=={e['path']:e['sha256'] for e in baseline['files']})
    ck('Renderer builder adopter source bytes stable throughout independent review',all(sha(Path(b['path']))==b['sha256'] for b in start))
    paths.extend(sources+[manualpath,sourcebaseline]);unique=sorted(set(paths))
    receipt=dict(schema='independent-shared-card-headings-review-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),failures=[c['name'] for c in checks if not c['passed']],checks=checks,cards=details,candidate_bindings=[bind(p) for p in unique],supporting_files=[bind(Path(__file__)),bind(HERE/'compact-r-review/trace_compact.py')],scope='Read-only header/body/source fact verification; only this private receipt is written.')
    (HERE/'Shared headings independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(passed=receipt['passed'],failures=receipt['failures'],checks=len(checks),drawings=output_count)))
if __name__=='__main__':main()
