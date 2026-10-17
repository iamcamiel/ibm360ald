"""Meaningful safety fixtures for compact current-shape metadata cleanup."""
import unittest
from copy import deepcopy
from compact_metadata import prune_history,render_compact_notes
class CleanupTests(unittest.TestCase):
 def test_existing_compact_corrections_and_exceptions_survive_reuse(self):
  original = {'source_reviewed': True, 'nodes': []}
  existing = 'Correction: {"node":"AA","before":"E08","after":"B08"}\nException: {"note":"Printed equivalent notation"}\n'
  clean, notes = prune_history(original, existing)
  self.assertEqual(clean, original)
  rendered = render_compact_notes(notes)
  self.assertIn('"after":"B08"', rendered)
  self.assertIn('Printed equivalent notation', rendered)

 def test_current_electrical_geometry_identity_and_markers_unchanged(self):
  current={'id':'AA','card':'1125A2','part':'1125A2','card_type':'1125','portion':'A2','unit':'S16CL','technology':'S16CL','location':'D-A2M6','function':'✲A-CD','source_reviewed':False,
   'pins':[{'pin':'8D0�X','physical_pin':None,'source_unknown_pin':True,'printed_prefix':'8','printed_suffix':'X','triangle':False,'border_marker':'K','row':5,'absolute_row':70,'point':[3,5],'reference':'AA.output.8D0�X','source_position':[3,70]}]}
  net={'driver':'AA.D02','declared_physical_output_drivers':['AA.D02','AA.KB13'],'candidate_edges':[[[1,2],[3,2]]],'source_driver_unresolved':True,'source_undriven':False,'source_reference':'AP271AA4','joined_diamonds':[[4,5]],'unjoined_crosses':[[7,5]],'route_owners':{'AA.D02':[0]}}
  raw={'source_reviewed':None,'review_status':'CURRENT','nodes':[current],'nets':[net],'wire_paths':[{'paths':[[[1,2],[3,2]]]}]}
  clean,notes=prune_history(raw);self.assertEqual(clean,raw);self.assertIsNone(clean['source_reviewed']);self.assertIs(clean['nodes'][0]['source_reviewed'],False);self.assertEqual(len(notes['unresolved']),2)
 def test_history_removed_literal_correction_compact(self):
  raw={'nodes':[{'unit':'U03AA'}],'human_function_corrections_v9':{'authority':{'path':'old.json','sha256':'a'*64},'changes':[{'block':'AA','field':'unit','before':'U03HA','after':'U03AA'}]},'prior_independent_review':{'checks':[True]*50}}
  clean,n=prune_history(raw);self.assertEqual(clean,{'nodes':[{'unit':'U03AA'}]});self.assertEqual(n['significant_literal_corrections'],[dict(block='AA',field='unit',before='U03HA',after='U03AA')]);self.assertNotIn('old.json',str(n));self.assertNotIn('a'*64,str(n))
 def test_minimal_socket_facts_without_changing_alternatives(self):
  proof=[{'kind':'card portion','board':'01D-A2','sockets':['M6'],'card_type':'1125','portion':'A2','part_number':'5801125','source_listing':'A1','source_listings':['A1'],'source_record_binding':{'sha256':'a'*64}}, {'board':'02D-A2','sockets':['M6'],'card_type':'1125','portion':'A2'}]
  clean,n=prune_history({'nodes':[{'socket_listing_evidence':proof}]});p=clean['nodes'][0]['socket_listing_evidence'];self.assertEqual(len(p),2);self.assertEqual(p[0]['board'],'01D-A2');self.assertEqual(p[1]['board'],'02D-A2');self.assertEqual(p[0]['part_number'],'5801125');self.assertNotIn('source_listing',p[0])
 def test_a1_record_wrapper_keeps_frame_relation(self):
  raw={'nodes':[{'A1':{'records':[{'page_key':'EF421','record':{'board':'01D-A2','socket':'M6','card_type':'1125','portion':'A2','native_evidence':'crop.png'}}]}}]}
  clean,_=prune_history(raw);self.assertEqual(clean['nodes'][0]['A1']['records'][0]['record'],dict(board='01D-A2',socket='M6',card_type='1125',portion='A2'))
 def test_unknown_semantic_evidence_not_deleted(self):
  raw={'nets':[{'physical_commoning_evidence':{'ports':['AA.D02','AA.B13'],'points':[[3,4]]},'evidence':{'paths':[[[1,2],[3,2]]]}}]}
  clean,n=prune_history(raw);self.assertEqual(clean,raw);self.assertGreater(n['cleanup_counts']['ambiguous_fields_retained'],0)
 def test_short_source_note_with_only_role_fact_conservative(self):
  raw={'nodes':[{'pins':[{'pin':'D03','source_note':'K border terminal is a passive commoned contact.'}]}]}
  clean,n=prune_history(raw);self.assertEqual(clean,raw);self.assertEqual(n['retained_ambiguous_field_names'],['source_note'])
 def test_proof_paths_hashes_removed_but_source_coordinates_remain(self):
  raw={'source':'scan.tif','source_sha256':'a'*64,'nodes':[{'source_top_border':[4,5],'source_y':42,'source_column':8,'source_reviewed':True,'source_evidence':{'path':'crop.png','sha256':'b'*64}}]}
  clean,_=prune_history(raw);self.assertEqual(clean,dict(source='scan.tif',source_sha256='a'*64,nodes=[dict(source_top_border=[4,5],source_y=42,source_column=8,source_reviewed=True)]))
 def test_source_scan_dict_minimal_not_source_endpoint(self):
  raw={'source':{'source':'scan.tif','sha256':'a'*64,'owner':'reviewer','scan_order':3,'old_proof':{'path':'old.json'}},'nets':[{'source':{'node':'AA','pin':'B08X'},'source_reference':'OTHERPAGE4'}]}
  clean,_=prune_history(raw);self.assertEqual(clean['source'],{'source':'scan.tif','sha256':'a'*64});self.assertEqual(clean['nets'],raw['nets'])
 def test_machine_checks_removed_geometry_dimensions_retained(self):
  raw={'source_reviewed':True,'review_status':'accepted','independent_review_complete':True,'branch_pairs_checked':12,'validation':{'passed':True,'hidden_junctions':0,'canvas_rows':103,'canvas_columns':245}}
  clean,_=prune_history(raw);self.assertEqual(clean,dict(source_reviewed=True,review_status='accepted',validation=dict(canvas_rows=103,canvas_columns=245)))
 def test_printed_annotation_notes_are_not_history(self):
  raw={'notes':[{'row':2,'column':6,'text':'SPECIAL SIGNAL'}],'nodes':[{'note':3}]}
  clean,_=prune_history(raw);self.assertEqual(clean,raw)
 def test_nodeless_ground_and_connector_objects_unchanged(self):
  raw={'boxes':[{'printed_id':'AA','function':'SERV✲','stub_pairs':[{'printed_pins':['E09','E10'],'rows':[2,3],'paths':[[[1,2],[1,3]]],'direction':'undetermined'}]}],'groups':[{'pins':['B08X'],'source_references':['AA1'],'routes':[{'source_reference':'BB4','pin':'B08X'}]}]}
  clean,_=prune_history(raw);self.assertEqual(clean,raw)
 def test_native_a1_disagreement_becomes_concise_exception(self):
  raw={'nodes':[{'location':'E-D2G7','native_A1_disagreement':{'printed_location':'E-D2G7','A1_location':'E-D2F7','resolution':'retain human reading','evidence':'crop.png'}}]}
  clean,n=prune_history(raw);self.assertEqual(clean,dict(nodes=[dict(location='E-D2G7')]));self.assertEqual(n['exceptions'][0]['printed_location'],'E-D2G7');self.assertNotIn('crop.png',str(n))
 def test_existing_notes_keep_only_significant_lines(self):
  clean,n=prune_history({'source':'scan.tif'},'Old receipt C:/tmp/proof.json\nCorrection: B01 → B04\nEXCEPTION: visible A1 discrepancy\nUnresolved: old unreadable already corrected')
  text=render_compact_notes(n);self.assertIn('B01 → B04',text);self.assertIn('A1 discrepancy',text);self.assertNotIn('old unreadable',text);self.assertNotIn('proof.json',text)
 def test_not_in_place_and_cleanup_idempotent(self):
  raw={'nodes':[{'pin':'B08','source_reviewed':True}],'review_notes':[{'before':'A','after':'OR'}]};old=deepcopy(raw);clean,_=prune_history(raw);again,_=prune_history(clean);self.assertEqual(raw,old);self.assertEqual(clean,again)
 def test_false_null_missing_and_empty_are_not_equivalent(self):
  raw={'nodes':[{'source_reviewed':False},{'source_reviewed':None},{},{'source_reviewed':''}]};clean,_=prune_history(raw);self.assertEqual(clean,raw)
if __name__=='__main__':unittest.main()
