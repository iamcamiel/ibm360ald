"""Generate a source-bound Card-ALD candidate for one installed 5800141 card.

This is deliberately not a card-family universal pinout.  It redraws only
the twelve portions actually used on XX651 at 02L-A2 H3.
"""

import hashlib
import json
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True,
                    help='New candidate TXT path; existing files are never overwritten')
parser.add_argument('--scan', type=Path,
                    default=Path('D:/Reference Materials/IBM 360/IBM_360_ALD/XX XY Register/XX651 XY PARITY REG SHEET 2 OF 2.tif'))
args = parser.parse_args()
PAGE = 'XX651 XY PARITY REG SHEET 2 OF 2'
MODEL = REPO / 'json/XX XY Register' / (PAGE + '.json')
TEXT = REPO / 'ALD/XX XY Register' / (PAGE + '.txt')
SCAN = args.scan
LOCATION = 'L-A2H3'

ORDER = [
    ('A', 'A1', 'A2', 'A3', ('D13','B13'), ('D09','B08'), 'B10'),
    ('B', 'B1', 'B2', 'B3', ('D10','B09'), ('D11','D12'), 'B12'),
    ('C', 'C1', 'C2', 'C3', ('D02','B02'), ('D07','D05'), 'B04'),
    ('D', 'D1', 'D2', 'D3', ('D04','B05'), ('B07','D06'), 'B03'),
]

class Canvas:
    def __init__(self, width=88, height=56):
        self.width = width
        self.rows = [[' '] * width for _ in range(height)]
        self.boxes = []
        self.paths = []

    def put(self, x, y, char):
        assert 0 <= x < self.width and 0 <= y < len(self.rows), (x,y,char)
        assert len(char) == 1
        self.rows[y][x] = char

    def text(self, x, y, s):
        for dx, char in enumerate(s): self.put(x+dx,y,char)

    def h(self, x1, x2, y):
        assert x1 <= x2
        for x in range(x1,x2+1):
            old=self.rows[y][x]
            assert old in (' ','─'), (x,y,old)
            self.put(x,y,'─')

    def v(self, x, y1, y2):
        assert y1 <= y2
        for y in range(y1,y2+1):
            old=self.rows[y][x]
            assert old in (' ','│'), (x,y,old)
            self.put(x,y,'│')

    def box(self,x,top,portion,function,unit):
        assert top%7==0
        assert len(function)<=6 and len(unit)==5 and len('0141'+portion)==6
        self.boxes.append({'portion':portion,'left':x,'top':top,'height':7})
        self.text(x,top,'┌──────┐')
        self.text(x,top+6,'└──────┘')
        for y in range(top+1,top+6):
            self.put(x,y,'│');self.put(x+7,y,'│')
        self.text(x+1,top+1,function)
        self.text(x+1,top+3,unit)
        self.text(x+1,top+4,'0141'+portion)

    def render(self):
        return '\n'.join(''.join(r).rstrip() for r in self.rows)+'\n'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

doc=json.loads(MODEL.read_text(encoding='utf-8'))
nodes={n['portion']:n for n in doc['nodes'] if n.get('card_type')=='0141' and n.get('location')==LOCATION}
assert sorted(nodes)==sorted([p for _,a,b,c,*_ in ORDER for p in (a,b,c)])
byid={n['id']:n['portion'] for n in nodes.values()}
edges=set()
for net in doc['nets']:
    src=str(net.get('driver') or '').split('.',1)[0]
    if src not in byid: continue
    for target in net.get('targets',[]):
        tgt=str(target).split('.',1)[0]
        if tgt in byid: edges.add((byid[src],byid[tgt]))
expected={(p,q) for _,a,b,q,*_ in ORDER for p in (a,b)}
assert edges==expected, (sorted(edges-expected), sorted(expected-edges))

# The model's printed pin strings have a terminal suffix on the output boxes;
# the contact itself is the first three characters.  Keep both in the draft.
for _,a,b,c,pins_a,pins_b,out in ORDER:
    for portion,pins in ((a,pins_a),(b,pins_b)):
        observed=[p.get('pin') for p in nodes[portion]['pins'] if p.get('side')=='input']
        assert observed==list(pins), (portion,observed,pins)
    output=[p.get('pin') for p in nodes[c]['pins'] if p.get('side')=='output']
    refs=[p.get('reference') for p in nodes[c]['pins'] if p.get('side')=='output']
    assert len(output)==1 and output[0]==out and refs==[nodes[c]['id']+'.'+out+'✲T'], (c,output,refs)

c=Canvas()
for idx,(letter,a,b,out_port,pins_a,pins_b,out_pin) in enumerate(ORDER):
    base=idx*14
    c.box(23,base,a,'A','U03AA')
    c.box(23,base+7,b,'A','U03AA')
    c.box(52,base+7,out_port,'OR','U03AE')

    # Draw the card's physical U03AA AND functions with plain inputs. Source
    # ALD input wedges describe page-level signal polarity, not extra gates.
    # Repeat each physical contact at the margin and the box border.
    for top,pins in ((base,pins_a),(base+7,pins_b)):
        portion = a if top == base else b
        for index,(y,pin) in enumerate(((top+1,pins[0]),(top+5,pins[1]))):
            c.text(0,y,pin);c.h(3,19,y);c.text(20,y,pin)

    # Two pinless gate outputs bend independently into the OR gate.  Separate
    # lanes (x36/x42) avoid a false wire crossing or a diamond junction.
    c.h(31,36,base+3);c.v(36,base+4,base+7);c.h(37,51,base+8)
    c.put(36,base+3,'┐');c.put(36,base+8,'└')
    c.h(31,42,base+10);c.v(42,base+11,base+11);c.h(43,51,base+12)
    c.put(42,base+10,'┐');c.put(42,base+12,'└')
    c.paths += [
        {'from':a+'.output','to':out_port+'.upper','via':[[36,base+3],[36,base+8]]},
        {'from':b+'.output','to':out_port+'.lower','via':[[42,base+10],[42,base+12]]},
    ]

    # Outside the block, retain the original ✲T mark and a right-end physical
    # pin label.  The external label is the contact, without that annotation.
    # U03AE is an OR with inverted output. Put that wedge in the output
    # border as a property of the card circuit, independent of page notation.
    c.put(59,base+10,'◺')
    c.text(60,base+10,out_pin+'✲T');c.h(65,79,base+10);c.text(80,base+10,out_pin)

diagram='CARD-ALD  5800141  SINGLE CARD  EXAMPLE 02L-A2 H3  (XX651)\n'
diagram+='THIS DRAWING SHOWS ALL 12 PORTIONS OF THIS INSTALLED CARD; UNUSED PINS ARE NOT INFERRED.\n'
diagram+='INPUT CONTACTS: 16   OUTPUT CONTACTS: 4   INTERNAL PINLESS LINKS: 8\n\n'
diagram+='CARD FUNCTION: U03AA = AND; U03AE = OR WITH INVERTED OUTPUT (◺).\n'
diagram+='XX651 INPUT WEDGES ARE PAGE POLARITY MARKS; SEE THE WEDGE VARIATION AUDIT.\n\n'
diagram+=c.render()
out=args.output.resolve()
assert not out.exists(), 'Refusing to overwrite an existing candidate or published diagram'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(diagram,encoding='utf-8',newline='\n')
prov={
 'schema':'private-card-ald-draft-v1', 'card_type':'0141','full_part_number':'5800141',
 'example_page':'XX651','example_socket':'02L-A2 H3','model_location':LOCATION,
 'source_files':{kind:{'path':str(path),'sha256':sha(path)} for kind,path in [('scan',SCAN),('accepted_text',TEXT),('accepted_model',MODEL)]},
 'internal_edges':[list(e) for e in sorted(expected)],
 'block_grid':{'height':7,'first_column_left':23,'second_column_left':52,
               'group_start_rows':[0,14,28,42]},
 'used_physical_pins':{'inputs':[p for _,_,_,_,pa,pb,_ in ORDER for p in (*pa,*pb)],
                       'outputs':[row[-1] for row in ORDER]},
 'draft_file':str(out),'draft_sha256':sha(out),
 'scope':'Installed example only; no full pinout or unused inputs inferred',
 'repository_published':False,
}
out.with_name(out.stem+' provenance.json').write_text(json.dumps(prov,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(out)
print('blocks',len(c.boxes),'internal paths',len(c.paths),'sha256',sha(out))
