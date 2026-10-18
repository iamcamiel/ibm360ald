"""Source decorations are displayed without changing physical contact topology."""
from copy import deepcopy
import unittest
import generate_card as M

def fixture():
    return {'schema':'reviewed-card-render-definition-v1','card_type':'9999',
        'canvas':{'width':60,'height':16,'header_rows':7,'grid_origin':8,'grid_step':1},
        'canonical_line_ending':'LF','power_contacts':{},'annotations':[],
        'boxes':[{'portion':'A1','x':18,'top':8,'height':7,'function':'A','circuit_identifier':'U03AA','ports':[
            {'id':'i','pin':'B02','side':'input','row':9,'triangle':False},
            {'id':'o','pin':'D02','side':'output','row':11,'triangle':False}]}],
        'exterior_pins':[{'pin':'B02','side':'input','x':0,'row':9},{'pin':'D02','side':'output','x':57,'row':11}],
        'wiring':{'horizontal_segments':[{'x1':3,'x2':14,'y':9},{'x1':29,'x2':56,'y':11}],'marks':[]},
        'nets':[['PIN:B02','PORT:A1:i'],['PIN:D02','PORT:A1:o']],'variants':[]}

class PinSymbolRendererTests(unittest.TestCase):
    def test_x_overlays_exact_border_without_moving_any_wire(self):
        spec=fixture();plain=M.render(spec);graph=M.wiring_graph(spec)
        spec['boxes'][0]['ports'][0]['border_symbol']='X'
        M.validate(spec);rendered=M.render(spec)
        differences=[(x,y)for y,(a,b)in enumerate(zip(plain,rendered))for x,(c,d)in enumerate(zip(a,b))if c!=d]
        self.assertEqual(differences,[(18,9)]);self.assertEqual(rendered[9][18],'X')
        self.assertEqual(M.wiring_graph(spec),graph)
    def test_x_and_triangle_or_variant_triangle_is_rejected(self):
        for variant in (False,True):
            spec=fixture();port=spec['boxes'][0]['ports'][0];port['border_symbol']='X'
            if variant:spec['variants']=[{'number':1,'box_overrides':{'A1':{'port_triangles':{'i':True}}}}]
            else:port['triangle']=True
            with self.assertRaisesRegex(AssertionError,'triangle and X'):M.validate(spec)
    def test_placed_prefix_and_suffix_stars_consume_only_straight_wire_cells(self):
        spec=fixture();graph=M.wiring_graph(spec)
        spec['boxes'][0]['ports'][0]['pin_symbols']={'prefix':['✲'],'suffix':[]}
        spec['boxes'][0]['ports'][1]['pin_symbols']={'prefix':[],'suffix':['✲']}
        M.validate(spec);lines=M.render(spec)
        self.assertEqual(lines[9][14:18],'✲B02');self.assertEqual(lines[11][26:30],'D02✲')
        self.assertEqual(M.wiring_graph(spec),graph)
        self.assertEqual(spec['boxes'][0]['ports'][1]['pin'],'D02')
    def test_source_symbol_cannot_erase_a_corner_or_junction(self):
        for glyph in ('┐','┼','◇','│'):
            spec=fixture();spec['boxes'][0]['ports'][1]['pin_symbols']={'suffix':['✲']}
            spec['wiring']['horizontal_segments'][1]['x1']=30
            spec['wiring']['marks']=[{'x':29,'y':11,'symbol':glyph}]
            with self.assertRaisesRegex(AssertionError,'straight wire label slot'):M.render(spec)
    def test_unknown_or_unplaced_symbols_and_pinless_symbols_are_rejected(self):
        for metadata in ({'suffix':['T']},{'prefix':['8']},{'suffix':'✲'},{'unplaced':['✲']}):
            spec=fixture();spec['boxes'][0]['ports'][0]['pin_symbols']=metadata
            with self.assertRaises(AssertionError):M.validate(spec)
        spec=fixture();spec['boxes'][0]['ports'][0].update(pin=None,pin_symbols={'suffix':['✲']})
        with self.assertRaisesRegex(AssertionError,'requires a physical contact'):M.validate(spec)
    def test_oversized_label_is_rejected_instead_of_extending_canvas(self):
        spec=fixture();spec['boxes'][0]['ports'][0]['pin_symbols']={'prefix':['✲']*30}
        with self.assertRaisesRegex(AssertionError,'exceeds canvas'):M.render(spec)
    def test_plain_legacy_ports_keep_bytes(self):
        spec=fixture();before=M.build(spec)[0]
        for port in spec['boxes'][0]['ports']:port['pin_symbols']={'prefix':[],'suffix':[]};port['border_symbol']=None
        self.assertEqual(M.build(spec)[0],before)
    def test_variant_symbols_use_identical_routes_and_can_remove_base_symbols(self):
        spec=fixture();port=spec['boxes'][0]['ports'][0];port['border_symbol']='X'
        spec['boxes'][0]['ports'][1]['pin_symbols']={'suffix':['✲']}
        variant={'number':1,'box_overrides':{'A1':{'border_symbols':{'i':None},'port_symbols':{'i':{'prefix':['✲']},'o':{'prefix':[],'suffix':[]}}}}}
        spec['variants']=[variant];M.validate(spec)
        lines=M.render(spec,variant)
        self.assertEqual(lines[9][18],'│');self.assertEqual(lines[9][14:18],'✲B02')
        self.assertEqual(lines[11][26:30],'D02─');self.assertEqual(M.wiring_graph(spec),fixture()['nets'])
    def test_variant_cannot_change_a_terminal_or_decorate_unknown_port(self):
        for key,value in (('border_symbols','X'),('port_symbols',{'suffix':['✲']}),('port_triangles',True)):
            spec=fixture();spec['variants']=[{'number':1,'box_overrides':{'A1':{key:{'unknown':value}}}}]
            with self.assertRaisesRegex(AssertionError,'Unknown port decoration'):M.validate(spec)

if __name__=='__main__':unittest.main()
