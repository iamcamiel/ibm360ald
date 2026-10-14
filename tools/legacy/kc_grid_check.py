"""Audit KC drafts against the user-specified, zero-based printer grid.

This checks declared anchors and literal text cells. Native route inspection
remains necessary; satisfying this audit alone is not source verification.
"""
import json
from pathlib import Path

ROOT = Path('D:/Github/IBM360')
OUT = ROOT / 'ALD_Visual_Transcriptions/ALD Diagrams'
WORK = ROOT / 'tmp/ald-text/kc'
SPEC = json.loads((ROOT / 'tmp/ald-text/ald/grid-verification/Printer grid specification.json').read_text(encoding='utf-8'))
inventory = json.loads((WORK / 'KC source inventory.json').read_text(encoding='utf-8'))
results = []
for inv in inventory:
    stem = Path(inv['filename']).stem
    text_path, model_path = OUT / (stem+'.txt'), OUT / (stem+'.json')
    if not text_path.exists() or not model_path.exists():
        results.append(dict(page=inv['page'], passed=False, faults=['missing draft']))
        continue
    lines = text_path.read_text(encoding='utf-8').splitlines()
    doc = json.loads(model_path.read_text(encoding='utf-8'))
    faults = []
    if len(lines) != 103: faults.append(f'rows {len(lines)}, expected 103')
    if any(len(line)>245 for line in lines): faults.append('text exceeds column 244')
    for node in doc.get('nodes',[]):
        grid = node.get('calibrated_grid_position',node.get('grid',''))
        if len(grid) != 2 or grid[0] not in '1234567' or grid[1].upper() not in SPEC['block_grid_letters']:
            faults.append('unrecognized source grid '+node['id']+': '+grid)
            continue
        expected_column = SPEC['block_left_columns'][int(grid[0])-1]
        expected_row = SPEC['block_top_rows'][SPEC['block_grid_letters'].index(grid[1].upper())]
        if (node['column'],node['row']) != (expected_column,expected_row):
            faults.append(f"{node['id']} anchor {(node['column'],node['row'])}, expected {(expected_column,expected_row)}")
    def cell(row,col):
        return lines[row][col] if row < len(lines) and col < len(lines[row]) else ' '
    if any(ch.islower() for line in lines for ch in line): faults.append('lowercase diagram character')
    if ''.join(cell(100,c) for c in range(227,231))!='P.N.': faults.append('literal P.N. footer')
    if ''.join(cell(96,c) for c in range(227,232))!='MACH.': faults.append('machine prefix alignment')
    if ''.join(cell(96,c) for c in range(233,240))!='7201-02': faults.append('machine value alignment')
    if cell(96,240)!=' ' or cell(100,240)!=' ': faults.append('missing one-cell footer gap')
    if ''.join(cell(100,c) for c in range(231,233))!='  ': faults.append('part number prefix gap')
    for node in doc.get('nodes',[]):
        c,r=node['column'],node['row']
        block_id=node.get('printed_id',node['id'])
        expected=node['grid']+'──'+block_id
        bottom=r+node.get('height',7)-1
        if len(expected)==6 and ''.join(cell(bottom,c+i) for i in range(1,7))!=expected:
            faults.append('grid-ID spacing '+node['id'])
        for pin in node.get('pins',[]):
            label=pin['pin']
            if not label: continue
            start=c-len(label) if pin['side']=='input' else c+8
            if ''.join(cell(pin['row'],start+i) for i in range(len(label)))!=label:
                faults.append('pin label placement '+pin['reference'])
            border=c if pin['side']=='input' else c+7
            expected_border='◺' if pin.get('triangle') else pin.get('printed_operator','│')
            if cell(pin['row'],border)!=expected_border:
                faults.append('pin border '+pin['reference'])
    pin_text_cells={}
    for node in doc.get('nodes',[]):
        for pin in node.get('pins',[]):
            label=pin.get('pin')
            if not label: continue
            start=node['column']-len(label) if pin['side']=='input' else node['column']+8
            for col in range(start,start+len(label)):
                pin_text_cells[(col,pin['row'])]=pin['reference']
    for path in doc.get('wire_paths',[]):
        pts=[]
        for point in path.get('points',[]):
            if not pts or point!=pts[-1]: pts.append(point)
        for prev,current,nxt in zip(pts,pts[1:],pts[2:]):
            turn=(prev[0]==current[0]) != (current[0]==nxt[0])
            if turn and tuple(current) in pin_text_cells:
                faults.append('wire bend hidden by pin '+pin_text_cells[tuple(current)]+' on '+path['net'])
    page = inv['page']
    if len(lines) and lines[0][235:245] != '000  '+page: faults.append('top page reference')
    for i,ch in enumerate(page):
        if cell(95+i,1)!=ch or cell(95+i,243)!=ch: faults.append('vertical page reference');break
    if len(lines)>101 and (lines[101][0:3]!='000' or lines[101][242:245]!='000'): faults.append('subpage reference')
    if cell(93,210)!='┌' or cell(93,241)!='┐': faults.append('title frame top corners')
    if any(cell(row,col)!='│' for row in range(94,103) for col in (210,241)): faults.append('title frame sides')
    results.append(dict(page=page, passed=not faults, faults=faults))
(WORK / 'KC printer grid audit.json').write_text(json.dumps(dict(specification=str(ROOT / 'tmp/ald-text/ald/grid-verification/Printer grid specification.json'),pages=results),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({r['page']:dict(passed=r['passed'],fault_count=len(r['faults']),first_faults=r['faults'][:3]) for r in results},ensure_ascii=False))
