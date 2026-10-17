from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from identity import normalize_identity
from terminals import collect_terminals, normalize_net
from pages import SCHEMA, normalize_page, restore_page, renormalize_page, validate_current_page
from load_uniform_page import load_page, validate_page


def literal(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class PageTests(unittest.TestCase):
    def normalize(self,raw):
        result=normalize_page(raw,'json/Family/Test.json','001')
        self.assertEqual(literal(restore_page(result['data'])),literal(raw))
        return result

    def test_identity_semantics_match_reviewed_mapper(self):
        obj={'id':'AA','card':'419103','card_type':'4191','portion':'03','function':' A OR',
            'unit':'U03AF','location':'B-E1K6','printed_function':'A OR','source_reviewed':False}
        raw={'page':'AP001','source_reviewed':True,'nodes':[obj]}
        before=deepcopy(raw);r=self.normalize(raw);o=r['data']['objects'][0]
        for key,value in normalize_identity(obj,'/nodes/0')['data'].items():self.assertEqual(o[key],value)
        self.assertEqual(o['source_literals']['function'],' A OR')
        self.assertIs(o['source_literals']['source_reviewed'],False)
        self.assertEqual(raw,before)

    def test_terminals_decorations_symbols_are_separate(self):
        obj={'pins':[{'pin':'8B08✲','physical_pin':'B08','triangle':True,'side':'input','row':2,
            'source_top_border':False,'electrical_status':'undriven','unfamiliar':{'review_status':None}}],
            'input':'B08'}
        r=self.normalize({'nodes':[obj]});o=r['data']['objects'][0];t=o['terminals'][0]
        expected=collect_terminals(obj,'/nodes/0',{'owner_id':'nodes:0'})['data']['terminals'][0]
        for k,v in expected.items():
            if k!='terminal_id':self.assertEqual(t[k],v)
        self.assertEqual(t['pin_number'],'B08');self.assertTrue(t['border_decorations'])
        self.assertTrue(t['symbols']['prefix']);self.assertTrue(t['symbols']['suffix'])
        self.assertEqual(t['source_literals']['unfamiliar'],{'review_status':None})

    def test_reviewed_terminal_successor_semantics_are_visible_without_restoring(self):
        raw={'nodes':[{'input_pin':'1C','output_pin':'B08',
            'pins':[{'pin':'B09','printed_asterisk':False,'printed_fanout_count':3}]}],
            'nets':[{'additional_printed_output_coordinates':{'AS.✲D02':[154,42]}}]}
        data=self.normalize(raw)['data'];terminals=data['objects'][0]['terminals']
        unknown=next(t for t in terminals if t.get('current_unparsed_label_observations'))
        self.assertEqual(unknown['current_unparsed_label_observations'][0]['current_value'],'1C')
        self.assertEqual(unknown['declared_container_role'],'input')
        output=next(t for t in terminals if t['pin_number']=='B08')
        self.assertEqual(output['declared_container_role'],'output')
        primary=next(t for t in terminals if t['pin_number']=='B09')
        observations=primary['symbols']['observations']
        self.assertTrue(any(o.get('value_type')=='boolean' and o.get('current_value')is False for o in observations))
        self.assertTrue(any(o.get('value_type')=='integer' and o.get('current_value')==3 for o in observations))
        reference=data['nets'][0]['endpoint_claims'][0]['reference']['named_endpoint_members'][0]
        self.assertEqual(reference['current_value'],[154,42])
        self.assertEqual(reference['reference']['object_identifier'],'AS')
        self.assertEqual(reference['reference']['terminal']['pin_number'],'D02')

    def test_net_geometry_incidence_and_current_electrical_claims(self):
        net={'id':None,'driver':'AA.B08','targets':['AB.D02',{'node':'AC','pin':'D03','source_reviewed':False}],
            'edges':[[[0,1],[2,1]]],'native_wired_OR':True,'geometric_connectivity':{'joined':False},
            'electrical_continuity_verified':False,'source_join_evidence':{'current':'diamond'},
            'scan_gap_uncertainties':['�'],'review_status':'pending','unknowns':[]}
        r=self.normalize({'nets':[net]});n=r['data']['nets'][0]
        for k in ('endpoint_claims','endpoint_collections','connectivity_inference_applied'):
            self.assertEqual(n[k],normalize_net(net,'/nets/0',{'source_container':'nets','source_ordinal':0})['data'][k])
        self.assertIn({'kind':'electrical_continuity_verified','value':False},n['junctions'])
        self.assertEqual(n['extensions']['review_status'],'pending')
        self.assertNotIn('crossings',n)
        self.assertEqual(n['routing_status'],'partial')

    def test_crossing_literals_are_not_a_second_managed_geometry(self):
        net={'edges':[[[0,0],[1,0]]],'unjoined_crosses':[[1,0]],'printed_gap':None}
        n=self.normalize({'nets':[net]})['data']['nets'][0]
        self.assertNotIn('crossings',n)
        self.assertEqual(n['source_literals']['unjoined_crosses'],[[1,0]])
        self.assertEqual(n['routing_status'],'recorded')
        self.assertEqual(self.normalize({'nets':[{}]})['data']['nets'][0]['routing_status'],'not-recorded')
        self.assertEqual(self.normalize({'nets':[{'driver_coordinate':[2,3]}]})['data']['nets'][0]['routing_status'],'partial')

    def test_every_current_fact_survives_without_history_regex(self):
        raw={'source':{'path':'scan.tif','sha256':'current'},'review_status':'accepted',
             'status':False,'uncertainties':[None],'unknowns':[],
             'nodes':[{'card':'bad�','review_status':'pending','source_reviewed':None,
                'current_approval_needed':False,'manual_operating_mode':'RUN',
                'printed_labels':[{'text':'KEEP','review_status':'unreadable','source_wire_gaps':[]}]}]}
        r=self.normalize(raw)
        self.assertEqual(r['data']['current_extensions']['source'],raw['source'])
        self.assertEqual(r['data']['objects'][0]['source_literals']['printed_labels'],raw['nodes'][0]['printed_labels'])

    def test_all_container_and_unsupported_shapes(self):
        for key in ('nodes','boxes','groups','CAS_boxes','nets','junctions'):
            for value in (None,[],False,0,0.0,{},['bad',None,False,0,{}]):
                with self.subTest(key=key,value=value):self.normalize({key:value})
        self.assertEqual(self.normalize({})['data']['source_containers'],{})

    def test_paired_programmed_grounds_and_connector_groups(self):
        self.normalize({'boxes':[{'board_location':'A-A1','stub_pairs':[{'printed_pins':['B08','D08'],
            'rows':[3,4],'connection_kind':'source-stub','review_status':False}]}]})
        self.normalize({'groups':[{'pins':['B08','D08'],'source_references':[],
            'routes':[None],'box_location':None,'input_signals':False,'ce':0}]})

    def test_terminal_collection_null_empty_scalar_aliases_duplicates(self):
        for obj in ({'pins':[]},{'pins':None},{'input_pins':False},{'pins':['B08','B08'],'input':'B08'},
                    {'pins':[{'pin':'B08','side':'input','row':2}],'input_pins':[{'pin':'B08','side':'input','row':2}]},
                    {'pins':[{'pin':None,'physical_pin':None,'triangle':False,'role':None}]},
                    {'pins':[{'pin':'E08','physical_pin':'B08','source_unknown_pin':True}]}):
            with self.subTest(obj=obj):self.normalize({'nodes':[obj]})

    def test_anonymous_and_duplicate_object_ids_preserve_order(self):
        data=self.normalize({'nodes':[{}, {}, {'id':None}, {'id':'AA'},{'id':'AA'}]})['data']
        self.assertEqual([o['object_id']for o in data['objects']],['nodes:'+str(i)for i in range(5)])

    def test_source_status_only_no_mapping_or_archive(self):
        result=self.normalize({'nodes':[{'id':'AA','pins':['B08']}],'nets':[{'driver':'AA.B08'}]})
        data=result['data'];self.assertIn('mapping',result)
        self.assertEqual(data['source_status_ref'],{'path':'notes/Source status.json','scan_id':'001'})
        text=literal(data)
        for key in ('field_coverage','original_bytes','provenance_ref','provenance_sidecar','mapping_policy'):
            self.assertNotIn('"'+key+'"',text)

    def test_renormalize_keeps_identity_and_updates_contents(self):
        original=self.normalize({'nodes':[{'id':'AA','unit':'U03AA'}]})['data']
        updated=renormalize_page({'nodes':[{'id':'AA','unit':'U03AR'}]},original)
        self.assertEqual(updated['document_id'],original['document_id'])
        self.assertEqual(restore_page(updated),{'nodes':[{'id':'AA','unit':'U03AR'}]})
        with self.assertRaises(ValueError):self.normalize(updated)

    def test_malformed_source_forms_fail_closed(self):
        data=self.normalize({'nodes':[{'pins':['B08']},{}]})['data']
        bad=deepcopy(data);bad['objects'][1]['source_form']['ordinal']=0
        with self.assertRaises(ValueError):restore_page(bad)
        bad=deepcopy(data);bad['objects'][0]['source_form']['terminal_collections'][0]['members']*=2
        with self.assertRaises(ValueError):restore_page(bad)
        bad=deepcopy(data);bad['objects'][0]['source_form']['terminal_collections'][0]['members'][0]={'terminal_id':'missing'}
        with self.assertRaises(ValueError):restore_page(bad)

    def test_semantic_edits_cannot_be_silently_ignored_by_source_adapter(self):
        data=self.normalize({'nodes':[{'function':'A','unit':'U03AA','pins':[{'pin':'B08','triangle':False,'row':2}]}],
            'nets':[{'driver':'AA.B08','targets':['AB.D02'],'geometric_connectivity':{'joined':False}}]})['data']
        for mutate in (
            lambda d:d['objects'][0]['function'].update(label='OR'),
            lambda d:d['objects'][0]['terminals'][0].update(pin_number='D08'),
            lambda d:d['objects'][0]['terminals'][0]['border_decorations'][0].update(observed_value=True),
            lambda d:d['nets'][0]['endpoint_claims'][0].update(order=5),
            lambda d:d['nets'][0]['routes'][0].update(value={'joined':True}),
            lambda d:d['objects'][0]['source_literals'].update(function='OR'),
        ):
            bad=deepcopy(data);mutate(bad)
            with self.assertRaises(ValueError):validate_current_page(bad)
            with self.assertRaises(ValueError):restore_page(bad)

    def test_acceptance_context_does_not_change_current_data(self):
        raw={'source_reviewed':False,'nodes':[{'source_reviewed':None,'function':'A'}]}
        plain=normalize_page(raw,'json/Family/Test.json','001')['data']
        context={'accepted_page':{'source_reviewed_present':True,'source_reviewed':False}}
        bound=normalize_page(raw,'json/Family/Test.json','001',context=context)['data']
        self.assertEqual(plain,bound);validate_current_page(bound)

    def test_loader_has_no_sidecar_dependency_and_checks_paths(self):
        data=self.normalize({'nodes':[{'pins':['B08']} ]})['data']
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);(root/'page.json').write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(load_page(root,'page.json'),data)
            for path in ('../page.json','D:/page.json','folder\\page.json'):
                with self.assertRaises(ValueError):load_page(root,path)
            (root/'duplicate.json').write_text('{"schema":"x","schema":"y"}',encoding='utf-8')
            with self.assertRaises(ValueError):load_page(root,'duplicate.json')
        bad=deepcopy(data);bad['source_status_ref']['scan_id']='bad'
        with self.assertRaises(ValueError):validate_page(bad)


if __name__=='__main__':unittest.main()
