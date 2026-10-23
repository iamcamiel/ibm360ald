from copy import deepcopy
import unittest
import pages,legacy_v2,review,layout
from printed_literals import repair_raw,split_records

class PrintedLiteralTests(unittest.TestCase):
 def raw(self,label='D07',prefix='3',bound=False):
  pin=dict(pin='D07',pin_status='observed',printed_label=label,reference='AA.D07',references=[],side='input',row=0,column=None,point=[4,0],label_column=None,border_point=None,triangle=False,border_marker=None,printed_prefix=prefix,printed_suffix=None,occurrence_kind='primary',source_observations=[])
  raw=dict(page='TEST',page_type='ald',nodes=[dict(id='AA',pins=[pin])],printed_labels=[dict(column=0,row=0,text=prefix+label)])
  text=(prefix+label+'\n').encode('utf8')
  binding=dict(pointer='/nodes/0/pins/0/printed_label' if bound else '/printed_labels/0/text',mirrors=[],row=0,column=len(prefix) if bound else 0,width=len(label) if bound else len(prefix+label),format='string-right-pad')
  raw['text_layout']=layout.build_layout(raw,text,[binding]);return raw,text
 def historical(self,raw):
  d=legacy_v2.normalize_page(raw,'json/Test.json','test')['data'];d['schema']=pages.SCHEMA;d['review']=review.make(d);return d
 def test_writer_rejects_split_prefix(self):
  for prefix,label in (('3','D07'),('4','D07'),('8','')):
   raw,text=self.raw(label,prefix)
   with self.assertRaisesRegex(ValueError,'full declared printed prefix'):pages.normalize_page(raw,'json/Test.json','test')
 def test_current_reader_rejects_historical_split(self):
  raw,text=self.raw();d=self.historical(raw)
  with self.assertRaisesRegex(ValueError,'full declared printed prefix'):pages.restore_page(d)
 def test_explicit_import_preserves_text_pins_and_input_bytes(self):
  raw,text=self.raw();d=self.historical(raw);before=deepcopy(d);fixed=pages.import_review_page(d)
  self.assertEqual(d,before);self.assertEqual(layout.render(fixed),text)
  pin=pages.restore_page(fixed)['nodes'][0]['pins'][0]
  self.assertEqual((pin['pin'],pin['printed_prefix'],pin['printed_label']),('D07','3','3D07'))
  self.assertFalse(fixed['review']['user_approved']);self.assertEqual(pages.import_review_page(fixed),fixed)
 def test_bound_pin_label_expands_over_exact_prefix(self):
  raw,text=self.raw(bound=True);fixed,changes=repair_raw(raw,text)
  self.assertEqual(layout.render(fixed),text);self.assertEqual(len(changes),1)
  self.assertEqual(fixed['text_layout']['bindings'][0]['column'],0)
  self.assertEqual(fixed['text_layout']['bindings'][0]['width'],4)
 def test_pinless_marker_remains_pinless(self):
  raw,text=self.raw('','8');raw['nodes'][0]['pins'][0].update(pin=None,reference='AA.input')
  old=raw.pop('text_layout');raw['text_layout']=layout.build_layout(raw,text,old['bindings'])
  d=pages.import_review_page(self.historical(raw));pin=pages.restore_page(d)['nodes'][0]['pins'][0]
  self.assertIsNone(pin['pin']);self.assertEqual(pin['printed_label'],'8');self.assertEqual(layout.render(d),text)
 def test_repair_cannot_hide_unknown_live_field(self):
  raw,text=self.raw();raw['nodes'][0]['unregistered_contract_escape']='x'
  old=raw.pop('text_layout');raw['text_layout']=layout.build_layout(raw,text,old['bindings'])
  with self.assertRaises(ValueError):pages.import_review_page(self.historical(raw))
 def test_border_K_is_not_a_pin_label_prefix(self):
  raw,text=self.raw('D07','K');raw['nodes'][0]['pins'][0].update(printed_prefix=None,border_marker='K')
  old=raw.pop('text_layout');raw['text_layout']=layout.build_layout(raw,text,old['bindings'])
  fixed,changes=repair_raw(raw,text);self.assertFalse(changes)
  d=pages.normalize_page(fixed,'json/Test.json','test')['data'];self.assertEqual(pages.restore_page(d)['nodes'][0]['pins'][0]['printed_label'],'D07')
 def test_nonnumeric_control_requires_source_classification(self):
  raw,text=self.raw('D07','K');fixed,changes=repair_raw(raw,text)
  self.assertFalse(changes);self.assertEqual(fixed,raw)
 def test_pinless_label_column_uses_existing_marker_position(self):
  raw,text=self.raw('','8');pin=raw['nodes'][0]['pins'][0];pin.update(pin=None,label_column=3)
  old=raw.pop('text_layout');raw['text_layout']=layout.build_layout(raw,text,old['bindings'])
  fixed,changes=repair_raw(raw,text);self.assertEqual(fixed['nodes'][0]['pins'][0]['label_column'],0)
  self.assertEqual(fixed['nodes'][0]['pins'][0]['point'],[4,0]);self.assertEqual(layout.render(fixed),text)
  self.assertEqual(len(changes),2)
if __name__=='__main__':unittest.main()
