"""K is a border control; physical labels and their decorations stay separate."""
from copy import deepcopy
import unittest
import generate_card as G

def fixture():
    return {'schema':'reviewed-card-render-definition-v1','card_type':'9999',
        'canvas':{'width':40,'height':12,'header_rows':0,'grid_origin':2,'grid_step':1},
        'power_contacts':{},'canonical_line_ending':'LF','annotations':[],
        'boxes':[{'portion':'A1','x':10,'top':2,'height':7,'function':'OR','circuit_identifier':'U03AA',
            'ports':[{'id':'in','side':'input','pin':'B04','triangle':False,'row':3,'contact_role':'nonlogical_common','border_control':'K'},
                     {'id':'out','side':'output','pin':'D06','triangle':False,'row':5,'contact_role':'nonlogical_common','border_control':'K'}]}],
        'wiring':{'horizontal_segments':[{'x1':3,'x2':6,'y':3},{'x1':21,'x2':36,'y':5}],'marks':[]},
        'exterior_pins':[{'pin':'B04','side':'input','x':0,'row':3},{'pin':'D06','side':'output','x':37,'row':5}],
        'nets':[['PIN:B04','PORT:A1:in'],['PIN:D06','PORT:A1:out']], 'variants':[]}

class KBorder(unittest.TestCase):
    def test_left_and_right_k_occupy_exact_border_cells(self):
        spec=fixture();before=deepcopy(spec);files,_=G.build(spec);rows=files['9999.txt'].decode().splitlines()
        self.assertEqual(rows[3][7:11],'B04K')
        self.assertEqual(rows[5][17:22],'KD06─')
        self.assertEqual(G.port_label(spec['boxes'][0],spec['boxes'][0]['ports'][0]),(7,3,'B04'))
        self.assertEqual(G.port_label(spec['boxes'][0],spec['boxes'][0]['ports'][1]),(18,5,'D06'))
        self.assertEqual(spec,before);self.assertEqual(G.wiring_graph(spec),before['nets'])
    def test_pin_prefix_and_suffix_remain_outside_border_on_both_sides(self):
        spec=fixture()
        for port in spec['boxes'][0]['ports']:port['pin_symbols']={'prefix':['✲'],'suffix':['✲']}
        before=deepcopy(spec);files,_=G.build(spec);rows=files['9999.txt'].decode().splitlines()
        self.assertEqual(rows[3][5:11],'✲B04✲K')
        self.assertEqual(rows[5][17:23],'K✲D06✲')
        self.assertEqual(spec,before)
    def test_variants_keep_k_and_geometry_while_changing_pin_marks(self):
        spec=fixture();spec['variants']=[{'number':1,'box_overrides':{'A1':{'port_symbols':{'out':{'prefix':['✲'],'suffix':[]}}}}}]
        before=deepcopy(spec);files,_=G.build(spec)
        self.assertEqual(files['9999.txt'].decode().splitlines()[5][17:21],'KD06')
        self.assertEqual(files['9999-01.txt'].decode().splitlines()[5][17:22],'K✲D06')
        self.assertEqual(spec,before)
    def test_k_cannot_silently_erase_triangle(self):
        spec=fixture();spec['boxes'][0]['ports'][1]['triangle']=True
        with self.assertRaisesRegex(AssertionError,'K cannot share'):G.build(spec)
    def test_k_cannot_silently_erase_x(self):
        spec=fixture();spec['boxes'][0]['ports'][0]['border_symbol']='X'
        with self.assertRaisesRegex(AssertionError,'K cannot share'):G.build(spec)
    def test_variant_cannot_hide_second_border_decoration(self):
        spec=fixture();spec['variants']=[{'number':1,'box_overrides':{'A1':{'port_triangles':{'out':True}}}}]
        with self.assertRaisesRegex(AssertionError,'K cannot share'):G.build(spec)
    def test_ordinary_triangle_and_x_unchanged(self):
        spec=fixture();left,right=spec['boxes'][0]['ports']
        for p in (left,right):p.pop('contact_role');p.pop('border_control')
        left['triangle']=True;right['border_symbol']='X'
        files,_=G.build(spec);rows=files['9999.txt'].decode().splitlines()
        self.assertEqual(rows[3][7:11],'B04◺');self.assertEqual(rows[5][17:21],'XD06')

if __name__=='__main__':unittest.main()
