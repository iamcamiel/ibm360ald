"""Current format gates: aliases, drift, approval invalidation and lossless edits."""
from copy import deepcopy
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'page_text'))
import pages,review,layout
from check_format import check_file,loads

class FormatChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=Path(__file__).resolve().parents[2]
  cls.path=next((root/'json').rglob('AP001 *.json'));cls.document=loads(cls.path.read_bytes())
 def test_current_file_and_round_trip(self):
  schema=loads((Path(__file__).parent/'ALD page schema.json').read_bytes())
  check_file(self.path,schema)
  self.assertEqual(pages.renormalize_page(pages.restore_page(self.document),self.document),self.document)
 def test_legacy_aliases_are_not_writable(self):
  raw=pages.restore_page(self.document)
  for field in ('inputs','outputs','height_rows'):
   altered=deepcopy(raw);altered['nodes'][0][field]=[] if field!='height_rows' else 10
   with self.assertRaises(ValueError):pages.renormalize_page(altered,self.document)
 def test_new_fields_and_observation_names_rejected(self):
  raw=pages.restore_page(self.document)
  for altered in (deepcopy(raw),deepcopy(raw)):
   if altered==raw:altered['nodes'][0]['invented_format_field']=1
   with self.assertRaises(ValueError):pages.renormalize_page(altered,self.document)
  altered=deepcopy(raw);altered['nodes'][0].setdefault('source_observations',[]).append({'field':'uncoordinated_extension','value':1})
  with self.assertRaises(ValueError):pages.renormalize_page(altered,self.document)
 def test_changed_content_cannot_keep_approval(self):
  original=deepcopy(self.document);original['review']=review.make(original,approval={'recorded_utc':'2026-10-22T00:00:00Z','user_statement':'Explicit test approval'})
  changed=deepcopy(original);changed['current_extensions']['source_reviewed']=False
  with self.assertRaises(ValueError):review.validate(changed)
  changed['review']=review.refresh(changed,original['review']);review.validate(changed)
  self.assertFalse(changed['review']['user_approved']);self.assertEqual(changed['review']['status'],'needs-review')
 def test_duplicate_keys_and_nonfinite_rejected(self):
  for value in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   with self.assertRaises(ValueError):loads(value)
 def test_unknown_semantic_field_rejected_even_with_new_digest(self):
  d=deepcopy(self.document);d['objects'][0]['invented_field']=1;d['review']=review.refresh(d,d['review'])
  with self.assertRaises(ValueError):pages.validate_current_page(d)
 def test_physical_pin_and_conflicting_printed_label_are_independent(self):
  # This is an intentionally conflicting synthetic observation. No native
  # source or new physical identity is inferred from the displayed spelling.
  seed=next(p for n in pages.restore_page(self.document)['nodes']for p in n.get('pins',[])if p.get('pin')is not None)
  for physical,printed in (('D02','E02'),('D09','D08'),('D09','2D08'),('D07','3C07')):
   with self.subTest(physical=physical,printed=printed):
    pin=deepcopy(seed);pin.update(pin=physical,printed_label=printed,reference='AA.'+physical,references=[],source_observations=[])
    raw={'page':'TEST','page_type':'ald','nodes':[{'id':'AA','pins':[pin]}]}
    # The rendered spelling binds to printed_label, independently of pin.
    text=(printed+'\n').encode('utf8')
    raw['text_layout']=layout.build_layout(raw,text,[dict(pointer='/nodes/0/pins/0/printed_label',mirrors=[],row=0,column=0,width=len(printed),format='string-right-pad')])
    d=pages.normalize_page(raw,'json/Test.json','test')['data'];pages.validate_current_page(d)
    terminal=d['objects'][0]['terminals'][0]
    self.assertEqual(terminal['pin_number'],physical);self.assertEqual(terminal['pin_number_status'],pin['pin_status'])
    self.assertEqual(terminal['source_literals']['printed_label'],printed)
    self.assertNotIn('pin_number_alternatives',terminal)
    self.assertEqual(pages.restore_page(d),raw)
    self.assertEqual(layout.render(d),text)
    self.assertEqual(pages.renormalize_page(raw,d),d)
 def test_printed_text_does_not_fill_an_explicitly_unknown_physical_pin(self):
  seed=next(p for n in pages.restore_page(self.document)['nodes']for p in n.get('pins',[])if p.get('pin')is None)
  pin=deepcopy(seed);pin.update(printed_label='D08',reference='AA.input',references=[],source_observations=[])
  raw={'page':'TEST','page_type':'ald','nodes':[{'id':'AA','pins':[pin]}]}
  d=pages.normalize_page(raw,'json/Test.json','test')['data'];pages.validate_current_page(d)
  self.assertIsNone(d['objects'][0]['terminals'][0]['pin_number'])
  self.assertEqual(d['objects'][0]['terminals'][0]['pin_number_status'],pin['pin_status'])
  self.assertEqual(pages.restore_page(d),raw)
 def test_legacy_alternative_field_remains_forbidden(self):
  d=deepcopy(self.document);d['objects'][0]['terminals'][0]['pin_number_alternatives']=['D02','D08']
  d['review']=review.refresh(d,d['review'])
  with self.assertRaises(ValueError):pages.validate_current_page(d)
 def test_historical_noncanonical_conflict_projection_is_preserved(self):
  import legacy_v2
  raw={'nodes':[{'pins':[{'pin':'D02','printed_label':'D08','pin_status':'observed','source_observations':[]}]}]}
  d=legacy_v2.normalize_page(raw,'json/Legacy.json','legacy')['data']
  self.assertEqual(d['objects'][0]['terminals'][0]['pin_number_alternatives'],['D08','D02'])
 def test_explicit_approval_requires_exact_content(self):
  with self.assertRaises(ValueError):review.approve(self.document,'User approval','2026-10-22','0'*64)
  d=review.approve(self.document,'Explicit test approval','2026-10-22',review.content_digest(self.document));self.assertTrue(d['review']['user_approved'])
if __name__=='__main__':unittest.main()
