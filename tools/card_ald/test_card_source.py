"""Stable-source semantics and current epoch guards, independent of layout."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import card_source as C

C.configure(Path(__file__).resolve().parents[2])
from pages import normalize_page


class SourceReaderTests(unittest.TestCase):
    def raw(self):
        return {'page':'XX001','source_reviewed':True,'printed_labels':[{'row':3,'column':4,'text':'A'}],
                'nodes':[{'id':'AA','card':'1234A1','unit':'U03AA','function':'A','location':'A-A1J6',
                    'row':2,'column':50,'pins':[{'side':'input','pin':None,'reference':'AA.IN','row':3,'triangle':False},
                    {'side':'output','pin':'D06','reference':'AA.KD06','border_marker':'K','triangle':False,'row':5}]}],
                'nets':[{'id':'wire','driver':'AA.KD06','targets':['BB.IN'],
                         'edges':[[[2,5],[3,5]],[[3,5],[3,7]]],'joined_diamonds':[[3,7]],'source_reviewed':True}]}

    def v2(self,raw=None):return normalize_page(raw or self.raw(),'json/XX/XX001.json','1')['data']

    def test_uses_uniform_identity_not_reparsed_consumer_aliases(self):
        result=C.view(self.v2());n=result['nodes'][0]
        self.assertEqual((n['card_type'],n['portion'],n['unit'],n['location']),('1234','A1','U03AA','A-A1J6'))

    def test_named_pinless_and_k_do_not_become_other_contacts(self):
        pins=C.view(self.v2())['nodes'][0]['pins']
        self.assertIsNone(pins[0]['_pin_number']);self.assertEqual(pins[0]['reference'],'AA.IN')
        self.assertEqual(pins[1]['reference'],'AA.KD06');self.assertEqual(pins[1]['border_marker'],'K')
        self.assertEqual(pins[1]['_pin_number'],'D06');self.assertFalse(pins[1]['triangle'])

    def test_contact_extra_symbols_are_not_part_of_physical_pin(self):
        for label,expected in [('B04X','B04'),('D06✲','D06'),('8B08XT','B08')]:
            self.assertEqual(C.physical_contact(label),expected)
            raw=self.raw();raw['nodes'][0]['pins'][0].update(pin=label,triangle=False)
            port=C.view(self.v2(raw))['nodes'][0]['pins'][0]
            self.assertEqual(C.terminal_contact(port),expected)

    def test_auditor_and_collector_share_contact_symbol_and_decoration_rules(self):
        import audit_card_uses as audit
        import collect_card_variants as variants
        raw=self.raw();raw['nodes'][0]['pins'][0].update(pin='B04X',triangle=False)
        raw['nodes'][0]['pins'][1].update(pin='D06✲',border_marker='K',triangle=False)
        node=C.view(self.v2(raw))['nodes'][0]
        box={'portion':'A1','function':'A','circuit_identifier':'U03AA','ports':[
            {'id':'input:1','side':'input','pin':'B04','row':1,'triangle':False},
            {'id':'output:3','side':'output','pin':'D06','row':3,'triangle':False}]}
        forms=audit.expected_forms({'boxes':[box],'variants':[]})
        findings=audit.compare_occurrence(node,box,forms['A1'],{})
        self.assertFalse([f for f in findings if f['status'] in ('discrepancy','source_uncertainty')])
        form,observed,missing,ignored=variants.observed_form(node,box,{})
        self.assertEqual(missing,[]);self.assertEqual(ignored,[])
        self.assertEqual(observed['input:1']['physical_pin'],'B04')

    def test_normalized_k_contact_keeps_pin_and_border_separate(self):
        raw=self.raw();raw['nodes'][0]['pins'][1].update(pin='KD06',border_marker='K')
        port=C.view(self.v2(raw))['nodes'][0]['pins'][1]
        self.assertEqual(C.terminal_contact(port),'D06');self.assertFalse(C.wedge(port))
        self.assertEqual(C.resolve_net_port({'id':'AA','pins':[port]},'AA.KD06','output')['physical_contact'],'D06')

    def test_accepted_active_physical_pin_is_not_damaged_printed_mirror(self):
        raw=self.raw();raw['nodes'][0]['pins'][1].update(pin='D06',printed_pin='U06')
        port=C.view(self.v2(raw))['nodes'][0]['pins'][1]
        self.assertEqual(port['_pin_number_status'],'conflicting-observations')
        self.assertEqual(C.terminal_contact(port),'D06')
        port['physical_pin']='B06';self.assertIsNone(C.terminal_contact(port))

    def test_uniform_border_decorations_are_observed_without_legacy_triangle_field(self):
        raw=self.raw();raw['nodes'][0]['pins'][0].pop('triangle');raw['nodes'][0]['pins'][0]['open_wedge']=True
        port=C.view(self.v2(raw))['nodes'][0]['pins'][0]
        self.assertTrue(C.wedge(port))
        port['_border_decorations'].append({'kind':'triangle','observed_value':False})
        self.assertIsNone(C.wedge(port))

    def test_precise_route_and_diamond_not_crossing_inference(self):
        d=self.v2();n=C.view(d)['nets'][0]
        self.assertEqual(n['edges'],self.raw()['nets'][0]['edges']);self.assertEqual(n['joined_diamonds'],[[3,7]])
        self.assertEqual(n['targets'],['BB.IN']);self.assertNotIn('crossings',n)

    def test_explicit_false_null_review_and_current_labels_preserved(self):
        for value in (False,None):
            raw=self.raw();raw['nodes'][0]['source_reviewed']=value
            result=C.view(self.v2(raw));self.assertIs(result['nodes'][0]['source_reviewed'],value)
            self.assertEqual(result['printed_labels'],raw['printed_labels'])

    def test_conflicting_identity_is_visible_but_not_selected(self):
        raw=self.raw();raw['nodes'][0]['part']='1234B1';d=C.view(self.v2(raw))
        self.assertTrue(d['nodes'][0]['_identity_conflict']);self.assertEqual(C.card_nodes(d,'1234'),[])

    def test_current_view_and_caller_are_detached(self):
        data=self.v2();before=deepcopy(data);view=C.view(data);view['nodes'][0]['pins'][0]['row']=99
        self.assertEqual(data,before);self.assertEqual(C.view(data)['nodes'][0]['pins'][0]['row'],3)

    def test_terminal_collections_have_one_common_pins_interface(self):
        raw=self.raw();n=raw['nodes'][0];n.pop('pins');n['input_pins']=[{'pin':'B04','row':3}];n['output_pin']='D06'
        result=C.view(self.v2(raw));pins=result['nodes'][0]['pins']
        self.assertEqual([(p['side'],p['pin']) for p in pins],[('input','B04'),('output','D06')])

    def test_same_named_contact_is_not_collapsed(self):
        raw=self.raw();raw['nodes'][0]['pins'].append(deepcopy(raw['nodes'][0]['pins'][0]))
        self.assertEqual(len(C.view(self.v2(raw))['nodes'][0]['pins']),3)

    def test_duplicate_non_null_source_id_cannot_identify_endpoint(self):
        raw=self.raw();raw['nodes'].append(deepcopy(raw['nodes'][0]));d=C.view(self.v2(raw))
        with self.assertRaises(ValueError):C.find_node(d,'AA')
        node,pointer,problem=C.exact_source_node(d,{'node':'AA','node_pointer':'/nodes/1'})
        self.assertIsNone(problem);self.assertEqual(pointer,'/nodes/1')

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'d.json';p.write_text('{"nodes":[],"nodes":[]}')
            with self.assertRaises(ValueError):C.json_read(p)

    def test_empty_terminal_reference_only_selects_single_anonymous_port(self):
        node={'id':'AA','pins':[{'side':'input','pin':None,'row':3},{'side':'output','pin':'D06','row':5}]}
        result=C.resolve_net_port(node,'AA.','input')
        self.assertEqual(result['status'],'pinless');self.assertEqual(result['port_index'],0)
        node['pins'].append({'side':'input','pin':'','row':4})
        self.assertEqual(C.resolve_net_port(node,'AA.','input')['status'],'unresolved')

    def test_empty_terminal_reference_does_not_hide_numbered_or_unknown_contact(self):
        for port in ({'pin':'B04'},{'pin':None,'physical_pin':'B04'},{'pin':None,'source_unknown_pin':True}):
            self.assertEqual(C.resolve_net_port({'id':'AA','pins':[{'side':'input',**port}]},'AA.','input')['status'],'unresolved')

    def test_unbound_semantic_literal_disagreement_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'d.json';data=self.v2();data['objects'][0]['card_identity']['card_type']='9999'
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):C.load(p)

    def test_checkpoint_binding_prevents_changed_normalized_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'notes').mkdir();(root/'json/XX').mkdir(parents=True)
            p=root/'json/XX/XX001.json';p.write_text(json.dumps(self.v2()))
            doc={'schema':'ald-current-source-checkpoint-v1','records':[{'repository':{'json':{'path':'json/XX/XX001.json','sha256':C.digest(p)}}}]}
            (root/'notes/Source status.json').write_text(json.dumps(doc))
            self.assertEqual(C.load(p,root)['document']['nodes'][0]['portion'],'A1')
            data=self.v2();data['objects'][0]['function']['label']='OR';p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):C.load(p,root)
            with self.assertRaises(ValueError):C.recheck_epoch(root)


if __name__=='__main__':unittest.main()
