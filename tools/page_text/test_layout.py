"""Pure codec/edit/ownership fixtures. No card engines or repository writes."""
from pathlib import Path
from copy import deepcopy
import ast,sys,unittest
sys.path.insert(0,str(Path('D:/Github/IBM360/ibm360ald/tools/normalization')))
import layout as m
class Controls(unittest.TestCase):
 def row(self,value='B08✲'):
  raw={'page':'X','nodes':[],'nets':[{'id':'N','driver':'opaque'}],'printed_labels':[{'row':0,'column':1,'text':value}]}
  return raw,(' '+value+'  │\r\n').encode()
 def ready(self):raw,txt=self.row();return m.attach_layout(raw,txt)
 def reject(self,fn,*args):
  with self.assertRaises(ValueError):fn(*args)
 def mutate_reject(self,fn):r=self.ready();fn(r);self.reject(m.render,r)
 def test_01_exact_utf8_baseline(self):
  raw={'page':'X'};txt='┌─◺✲�◇┼\r\n'.encode();self.assertEqual(m.render(m.attach_layout(raw,txt)),txt)
 def test_02_BOM_and_interior_BOM(self):
  txt=b'\xef\xbb\xbf'+'A\ufeffB\n'.encode();self.assertEqual(m.render(m.attach_layout({},txt)),txt)
 def test_03_mixed_EOL(self):
  txt=b'A\r\nB\nC\rD';self.assertEqual(m.render(m.attach_layout({},txt)),txt)
 def test_04_absent_final_EOL(self):self.assertEqual(m.render(m.attach_layout({},b'A')),b'A')
 def test_05_blank_trailing_ragged(self):
  txt=b'\r\n  \nA   \n';self.assertEqual(m.render(m.attach_layout({},txt)),txt)
 def test_06_same_length_live_edit(self):
  r=self.ready();new,txt=m.patch_and_render(r,[{'pointer':'/printed_labels/0/text','before':'B08✲','after':'D09✲'}]);self.assertEqual(txt,' D09✲  │\r\n'.encode());self.assertEqual(r['printed_labels'][0]['text'],'B08✲')
 def test_07_repeated_same_owner(self):
  raw={'label':'A'};b=lambda row:{'pointer':'/label','mirrors':[],'row':row,'column':0,'width':1,'format':'string-right-pad'}
  r=m.attach_layout(raw,b'A\nA\n',[b(0),b(1)]);self.assertEqual(m.patch_and_render(r,[{'pointer':'/label','before':'A','after':'B'}])[1],b'B\nB\n')
 def test_08_different_owners_same_literal_held(self):
  raw={'printed_labels':[{'row':0,'column':0,'text':'A'},{'row':0,'column':0,'text':'A'}]};d=m.discover(raw,['A']);self.assertEqual(d['bindings'],[]);self.assertEqual(len(d['held']),2)
 def test_09_span_overlap(self):
  b=self.ready()['text_layout']['bindings'][0];self.reject(m.build_layout,*self.row(),[b,b])
 def test_10_literal_preimage_mismatch(self):
  raw,txt=self.row();b=self.ready()['text_layout']['bindings'];self.reject(m.build_layout,raw,b' WRONG\r\n',b)
 def test_11_wrong_page_owner(self):self.mutate_reject(lambda r:r.update(page='OTHER'))
 def test_12_unbound_semantic_edit(self):self.mutate_reject(lambda r:r['nets'][0].update(driver='OTHER'))
 def test_13_unbound_route_edit(self):self.mutate_reject(lambda r:r.update(wire_paths=[{'points':[[1,1],[2,1]]}]))
 def test_14_missing_or_changed_type(self):
  self.mutate_reject(lambda r:r['printed_labels'][0].pop('text'));self.mutate_reject(lambda r:r['printed_labels'][0].update(text=None));self.mutate_reject(lambda r:r['printed_labels'][0].update(text=1))
 def test_15_width_overflow(self):self.reject(m.patch_and_render,self.ready(),[{'pointer':'/printed_labels/0/text','before':'B08✲','after':'B08✲LONG'}])
 def test_16_prefix_suffix_star_literal(self):
  for value in('✲B08','B08✲','◺B08','B08◺'):
   raw,txt=self.row(value);self.assertEqual(m.render(m.attach_layout(raw,txt)),txt)
 def test_17_opaque_ID_preserved(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':3,'height':3,'pins':[{'pin':'OPAQUE','physical_pin':'B08','reference':'AA.OPAQUE','row':1,'side':'input'}]}],'nets':[{'targets':['AA.OPAQUE']}],'printed_labels':[{'row':1,'column':0,'text':'B08'}]}
  txt='   ┌──────┐\nB08│      │\n   │      │\n   │1A──AA│\n'.encode();r=m.attach_layout(raw,txt);new,out=m.patch_and_render(r,[{'pointer':'/nodes/0/pins/0/physical_pin','before':'B08','after':'D09'}]);self.assertEqual(new['nodes'][0]['pins'][0]['reference'],'AA.OPAQUE');self.assertEqual(new['nets'],raw['nets']);self.assertIn(b'D09',out)
 def test_18_normalized_derived_direct_edit(self):
  import pages
  raw={'page':'X','nodes':[{'id':'A','card_type':'1234','portion':'A1','function':'A','unit':'U03AA'}]};doc=pages.normalize_page(raw,'json/X/X.json','1')['data'];doc['objects'][0]['function']['label']='OR';self.reject(m.rawview,doc)
 def mirror(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':0,'height':3,'unit':'U03AI'}],'printed_labels':[{'row':1,'column':1,'text':'U03AI'}]};txt='┌──────┐\n│U03AI │\n│      │\n│1A──AA│\n'.encode();return m.attach_layout(raw,txt)
 def test_19_unregistered_mirror_conflict(self):r=self.mirror();r['printed_labels'][0]['text']='U03AB';self.reject(m.render,r)
 def test_20_crossing_not_join_inference(self):
  r={'nets':[{'id':'N1'},{'id':'N2'}],'unjoined_crossings':[{'row':0,'column':1}]};out=m.attach_layout(r,'─┼─\n'.encode());self.assertEqual(out['nets'],r['nets']);self.assertEqual(m.render(out),'─┼─\n'.encode())
 def test_21_TXT_only_owner_required(self):
  self.reject(m.build_layout,None,b'AB\n');raw={'page':'QZ001','presentation_only':True};out=m.attach_layout(raw,b'AB\n');self.assertNotIn('nodes',out);self.assertEqual(m.render(out),b'AB\n')
 def test_22_explicit_format_edit(self):
  r=self.ready();r['text_layout']['rows'][0]['eol']='\n';self.assertTrue(m.render(r).endswith(b'\n'));self.assertFalse(m.render(r).endswith(b'\r\n'))
 def test_23_no_external_scan_dependency(self):
  r=self.ready();self.assertEqual(m.render(deepcopy(r)),m.render(r));self.assertNotIn('read_bytes',Path(m.__file__).read_text())
 def test_24_shorter_value_pads(self):self.assertEqual(m.patch_and_render(self.ready(),[{'pointer':'/printed_labels/0/text','before':'B08✲','after':'B08'}])[1],' B08   │\r\n'.encode())
 def test_25_stale_patch(self):self.reject(m.patch_and_render,self.ready(),[{'pointer':'/printed_labels/0/text','before':'BAD','after':'D09'}])
 def test_26_newline_field(self):self.reject(m.patch_and_render,self.ready(),[{'pointer':'/printed_labels/0/text','before':'B08✲','after':'A\n'}])
 def test_27_invalid_escape(self):self.reject(m._get,{'a~x':'A'},'/a~2x')
 def test_28_array_leading_zero(self):self.reject(m._get,{'a':['X']},'/a/00')
 def test_29_array_negative(self):self.reject(m._get,{'a':['X']},'/a/-1')
 def test_30_array_append(self):self.reject(m._get,{'a':['X']},'/a/-')
 def test_31_array_bounds(self):self.reject(m._get,{'a':['X']},'/a/1')
 def test_32_escaped_pointer_positive(self):self.assertEqual(m._get({'a/b':{'~x':'X'}},'/a~1b/~0x'),'X')
 def test_33_numeral_dictionary_key(self):self.assertEqual(m._get({'01':'X'},'/01'),'X')
 def test_34_no_presentation_self_binding(self):self.reject(m._get,{'text_layout':{}},'/text_layout/schema')
 def test_35_field_run_claim_mismatch(self):
  def bad(r):next(x for x in r['text_layout']['rows'][0]['runs']if x['kind']=='field')['width']+=1
  self.mutate_reject(bad)
 def test_36_dangling_masked_binding(self):
  def bad(r):row=r['text_layout']['rows'][0];row['runs']=[{'kind':'glyphs','column':0,'text':' B08✲  │'}]
  self.mutate_reject(bad)
 def test_37_duplicate_field_run(self):
  def bad(r):row=r['text_layout']['rows'][0];row['runs']=[x for x in row['runs']if x['kind']!='spaces'];row['runs'].append(deepcopy(next(x for x in row['runs']if x['kind']=='field')))
  self.mutate_reject(bad)
 def test_38_run_gap(self):self.mutate_reject(lambda r:r['text_layout']['rows'][0]['runs'][0].update(column=1))
 def test_39_row_extent(self):self.mutate_reject(lambda r:r['text_layout']['rows'][0].update(width=1))
 def test_40_unknown_keys(self):self.mutate_reject(lambda r:r['text_layout'].update(extra=True))
 def test_41_declared_mirror_sync(self):
  r=self.mirror();new,txt=m.patch_and_render(r,[{'pointer':'/nodes/0/unit','before':'U03AI','after':'U03AB'}]);self.assertEqual(new['printed_labels'][0]['text'],'U03AB');self.assertIn(b'U03AB',txt)
 def test_42_mirror_edit_syncs_primary(self):
  r=self.mirror();new,txt=m.patch_and_render(r,[{'pointer':'/printed_labels/0/text','before':'U03AI','after':'U03AB'}]);self.assertEqual(new['nodes'][0]['unit'],'U03AB')
 def test_43_conflicting_group_edits(self):self.reject(m.patch_and_render,self.mirror(),[{'pointer':'/nodes/0/unit','before':'U03AI','after':'U03AB'},{'pointer':'/printed_labels/0/text','before':'U03AI','after':'U03AC'}])
 def test_44_duplicate_source_edits(self):self.reject(m.patch_and_render,self.ready(),[{'pointer':'/printed_labels/0/text','before':'B08✲','after':'D09'},{'pointer':'/printed_labels/0/text','before':'B08✲','after':'D09'}])
 def test_45_only_layout_excluded(self):self.mutate_reject(lambda r:r.update(review_status='changed'))
 def test_46_Unicode_separators_are_glyphs(self):
  txt='A\u2028B\u2029C\x85D\vE\fF\n'.encode();r=m.attach_layout({},txt);self.assertEqual(len(r['text_layout']['rows']),1);self.assertEqual(m.render(r),txt)
 def test_47_invalid_UTF8(self):self.reject(m.build_layout,{},b'\xff')
 def test_48_bool_geometry(self):self.mutate_reject(lambda r:r['text_layout']['bindings'][0].update(row=True))
 def test_49_no_assert_validation(self):self.assertFalse(any(isinstance(n,ast.Assert)for n in ast.walk(ast.parse(Path(m.__file__).read_bytes()))))
 def test_50_no_canonical_diagnostics(self):self.assertFalse({'held','object_boxes','unmapped_or_ambiguous'}&set(self.ready()['text_layout']))
 def test_51_same_priority_partial_overlap_held(self):
  raw={'printed_labels':[{'row':0,'column':0,'text':'ABC'},{'row':0,'column':1,'text':'BC'}]};self.assertEqual(m.discover(raw,['ABC'])['bindings'],[])
 def test_52_empty_and_BOM_only(self):
  for b in(b'',b'\xef\xbb\xbf'):self.assertEqual(m.render(m.attach_layout({},b)),b)

 def test_53_oversized_height_cannot_borrow_foreign_unit(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':0,'height':10,'unit':'U03AL'},{'id':'AB','grid':'1B','unit':'U03AL'}]}
  rows=['┌──────┐','│U03AI │','│      │','│1A──AA│','└──────┘','        ','┌──────┐','│U03AL │','│      │','│1B──AB│','└──────┘']
  d=m.discover(raw,rows);self.assertFalse(any(b['pointer']=='/nodes/0/unit'for b in d['bindings']));r=m.attach_layout(raw,('\n'.join(rows)+'\n').encode());self.reject(m.patch_and_render,r,[{'pointer':'/nodes/0/unit','before':'U03AL','after':'U03AR'}])
 def test_54_foreign_footer_identity_holds_all_semantic_fields(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':0,'height':4,'unit':'U03AL'}]};rows=['┌──────┐','│U03AL │','│      │','│1B──AB│','└──────┘'];self.assertEqual(m.discover(raw,rows)['bindings'],[])
 def test_55_intervening_box_even_with_matching_footer_holds(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':0,'height':9,'unit':'U03AL'}]};rows=['┌──────┐','│U03AI │','│      │','│1B──AB│','└──────┘','        ','┌──────┐','│U03AL │','│      │','│1A──AA│'];self.assertEqual(m.discover(raw,rows)['bindings'],[])
 def test_56_matching_own_footer_plus_closed_bottom_positive(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':0,'height':4,'unit':'U03AL'}]};rows=['┌──────┐','│U03AL │','│      │','│1A──AA│','└──────┘'];self.assertTrue(any(b['pointer']=='/nodes/0/unit'for b in m.discover(raw,rows)['bindings']))


 def test_57_foreign_pin_row_outside_owned_box_held(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':3,'height':3,'pins':[{'physical_pin':'B08','side':'input','row':7}]},{'id':'AB','grid':'1B','unit':'U03AL'}]}
  rows=['   ┌──────┐','   │U03AI │','   │      │','   │1A──AA│','           ','           ','   ┌──────┐','B08│U03AL │','   │      │','   │1B──AB│']
  self.assertFalse(any(b['pointer']=='/nodes/0/pins/0/physical_pin'for b in m.discover(raw,rows)['bindings']));r=m.attach_layout(raw,('\n'.join(rows)+'\n').encode());self.reject(m.patch_and_render,r,[{'pointer':'/nodes/0/pins/0/physical_pin','before':'B08','after':'D09'}])
 def test_58_pin_without_own_side_border_held(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':3,'height':3,'pins':[{'physical_pin':'B08','side':'input','row':1}]}]};rows=['   ┌──────┐','B08 U03AI │','   │      │','   │1A──AA│'];self.assertFalse(any('/pins/'in b['pointer']for b in m.discover(raw,rows)['bindings']))
 def test_59_owned_wedge_border_positive(self):
  raw={'nodes':[{'id':'AA','grid':'1A','row':0,'column':3,'height':3,'pins':[{'physical_pin':'B08','side':'input','row':1}]}]};rows=['   ┌──────┐','B08◺U03AI │','   │      │','   │1A──AA│'];self.assertTrue(any('/pins/'in b['pointer']for b in m.discover(raw,rows)['bindings']))

if __name__=='__main__':unittest.main(verbosity=2)
