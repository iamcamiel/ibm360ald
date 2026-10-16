"""Manual-standard symbols and fixed-geometry observed notation variants."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent / 'tmp/ald-text/ald/card-universal'
PHYSICAL = re.compile(r'\d*([BDGJ](?:0[2-9]|1[0-3]))(?:✲T?|T)?$')
SUPPLY = {'D08','J08','D03','J03','B06','G06','B11','G11'}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def manual_path():
    published = ROOT / 'notes/Card-ALD/Manual canonical circuit forms.json'
    return published if published.exists() else WORK / 'Manual canonical circuit forms.json'


def normalize_canvas(canvas, card):
    forms = json.loads(manual_path().read_text(encoding='utf-8'))['circuits']
    geometry = {}
    for x, top, bottom, portion in canvas.boxes:
        unit = ''.join(canvas.rows[top+3][x+1:x+6])
        form = forms[unit]['canonical_form']
        if form is None:
            function = ''.join(canvas.rows[top+1][x+1:x+7]).strip()
            inputs = outputs = None
        else:
            function = form['primary_function']
            inputs, outputs = form['all_input_triangles'], form['all_output_triangles']
        ports = {'input': [], 'output': []}
        for row in range(top+1, bottom):
            for side, border, adjacent in [('input', x, x-1), ('output', x+7, x+8)]:
                char = canvas.rows[row][adjacent]
                if char not in '─┼◇┌┐└┘BDGJ0123456789':
                    continue
                start = x-3 if side == 'input' else x+8
                label = ''.join(canvas.rows[row][start:start+3])
                if not PHYSICAL.fullmatch(label):
                    label = None
                ports[side].append({'row': row, 'pin': label})
                flag = inputs if side == 'input' else outputs
                if flag is not None:
                    canvas.put(border, row, '◺' if flag else '│')
        assert len(function) <= 6
        canvas.text(x+1, top+1, function.ljust(6))
        geometry[portion] = {'portion': portion, 'unit': unit, 'left': x, 'top': top,
                             'height': bottom-top+1, 'ports': ports,
                             'manual_function': function, 'manual_definition_available': form is not None}
    return geometry


def save_geometry(output, geometry, header_rows):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {'schema':'card-ald-universal-geometry-v1', 'header_rows': header_rows,
            'manual_forms': {'path':str(manual_path()), 'sha256':digest(manual_path())},
            'portions': geometry}
    output.with_suffix('.geometry.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def physical(pin):
    for field in ['physical_pin_candidate', 'pin', 'printed_pin']:
        value = pin.get(field)
        if isinstance(value, str):
            match = PHYSICAL.fullmatch(value)
            if match:
                return match.group(1)
    return None


def observed_variants(card, directory):
    directory = Path(directory)
    base_path = directory / f'{card}.txt'
    base = base_path.read_text(encoding='utf-8').splitlines()
    geom = json.loads(base_path.with_suffix('.geometry.json').read_text(encoding='utf-8'))
    portions, header = geom['portions'], geom['header_rows']
    catalog_path = ROOT / f'json/Card types current/{card}.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    groups = defaultdict(list)
    for occurrence in catalog['diagram_occurrences']:
        groups[(occurrence['page'], occurrence['location'], occurrence['source_text'])].append(occurrence)
    whitelist = set()
    for g in portions.values():
        x, top = g['left'], g['top']+header
        whitelist.update((x+i, top+1) for i in range(1,7))
        for side, border in [('input', x),('output', x+7)]:
            whitelist.update((border, p['row']+header) for p in g['ports'][side])
    width = max(map(len, base))
    unique, canonical_sources = {}, []
    for (page, location, source_text), observations in sorted(groups.items()):
        rows = [list(row.ljust(width)) for row in base]
        witness = {'page':page, 'location':location, 'source_text':source_text,
                   'observed_portions':sorted({o['portion'] for o in observations}),
                   'unobserved_portions_kept_canonical':sorted(set(portions)-{o['portion'] for o in observations}),
                   'unmapped_source_fields':[]}
        by_portion = defaultdict(list)
        for o in observations:
            by_portion[o['portion']].append(o)
        for portion, os in by_portion.items():
            if portion not in portions:
                witness['unmapped_source_fields'].append({'portion':portion, 'reason':'source portion identity has no universal counterpart'})
                continue
            g = portions[portion]
            x, top = g['left'], g['top']+header
            functions = {str(o.get('function_label') or '').strip() for o in os}
            if len(functions)==1 and 0<len(next(iter(functions)))<=6:
                rows[top+1][x+1:x+7] = list(next(iter(functions)).ljust(6))
            else:
                witness['unmapped_source_fields'].append({'portion':portion,'field':'function', 'reason':'missing, conflicting, or oversized source label; canonical retained'})
            for side, border in [('input',x),('output',x+7)]:
                for port in g['ports'][side]:
                    matches=[]
                    for o in os:
                        pins = [p for p in o['pins'] if p['side']==side]
                        if port['pin']:
                            matches += [p for p in pins if physical(p)==port['pin']]
                        else:
                            pinless = sorted([p for p in pins if not physical(p)], key=lambda p:p.get('row') or 0)
                            card_pinless = [p for p in g['ports'][side] if not p['pin']]
                            if len(pinless)==len(card_pinless):
                                matches.append(pinless[card_pinless.index(port)])
                    flags={bool(p.get('triangle')) or p.get('border_marker')=='◺' for p in matches}
                    if len(flags)==1:
                        rows[port['row']+header][border] = '◺' if flags.pop() else '│'
                    elif matches:
                        witness['unmapped_source_fields'].append({'portion':portion,'field':side+'_decoration','pin':port['pin'],'reason':'conflicting source observations; canonical retained'})
        rendered = [''.join(row).rstrip() for row in rows]
        changes=[]
        for y,(old,new) in enumerate(zip(base,rendered)):
            for x,(a,b) in enumerate(zip(old.ljust(width),new.ljust(width))):
                if a!=b:
                    assert (x,y) in whitelist,(card,page,x,y,a,b)
                    changes.append({'column':x,'line':y,'before':a,'after':b})
        if not changes:
            canonical_sources.append(witness)
            continue
        key='\n'.join(rendered)+'\n'
        if key not in unique:
            unique[key]={'sources':[], 'changes':changes}
        unique[key]['sources'].append(witness)
    variants=[]
    for i,(text,data) in enumerate(sorted(unique.items()),1):
        filename=f'{card}-{i:02d}.txt'
        target=directory/filename
        target.write_text(text, encoding='utf-8', newline='\n')
        variants.append({'file':filename, 'sha256':digest(target), **data})
    result={'schema':'card-ald-observed-notation-variants-v1', 'card_type':card,
            'canonical':{'file':base_path.name,'sha256':digest(base_path)},
            'catalog':{'path':str(catalog_path),'sha256':digest(catalog_path)},
            'rules':['One page/socket witness at a time; unobserved fields retain the manual canonical symbol.',
                     'Complete physical pinout remains drawn even when a source usage omits inputs.',
                     'Only function text and connected border polarity marks differ; all geometry and wiring stays fixed.'],
            'counts':{'installation_witnesses':len(groups), 'canonical_pattern_witnesses':len(canonical_sources),
                      'distinct_observed_variants':len(variants)},
            'delta_whitelist':[{'column':x,'line':y} for x,y in sorted(whitelist,key=lambda p:(p[1],p[0]))],
            'canonical_pattern_sources':canonical_sources, 'variants':variants,
            'checks':{'fixed_geometry_and_wires':True,'all_deltas_whitelisted':True,'one_witness_pattern_per_variant':True}}
    (directory/f'{card} variants index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result
