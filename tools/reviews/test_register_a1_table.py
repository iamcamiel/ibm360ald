"""Temporary test fixtures only; these are not source review acceptances."""
from pathlib import Path
from copy import deepcopy
import json,tempfile,unittest
import register_a1_application as app

class TableQuartetTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
  self.exports=self.root/'exports';self.source_root=self.root/'sources';self.proof=self.root/'proof';self.proof.mkdir()
  self.text=self.exports/'A1 Socket Listing/A1114 SOCKET LISTING.txt';self.text.parent.mkdir(parents=True)
  self.source=self.source_root/'A1114 SOCKET LISTING.tif';self.source.parent.mkdir();self.source.write_bytes(b'test-only-native-fixture')
  self.adapter=self.root/'adapter.json';self.registry=self.root/'registry.json';self.write(self.adapter,{'passed':True,'pages':[]})
  self.stage_path=self.proof/'stage.json';self.pub_path=self.proof/'publication.json';self.peer_path=self.proof/'acceptance.json';self.batch=self.proof/'batch.json';self.write(self.batch,{'schema':'test-only-batch-fixture'})
  self.model=self.text.with_suffix('.json');self.write(self.model,{'board':'02A-A4','source':str(self.source),'sockets':[{'socket':'K4'}]})
  self.text.write_bytes(b'B\n');self.notes=self.text.with_name(self.text.stem+' review notes.txt');self.notes.write_bytes(b'fixture review notes')
  self.preview=self.text.with_name(self.text.stem+' preview.png');self.preview.write_bytes(b'fixture-preview-not-image')
  authority=self.proof/'authority.json';self.write(authority,{'test_fixture_only':True})
  old=self.proof/'old.txt';old.write_bytes(b'A\n')
  self.stage={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':app.TABLE_MODEL_SCHEMA,'page':'A1114','board':'02A-A4','source':app.bind(self.source),'human_authority':app.bind(authority),'source_crop':app.bind(authority),'predecessor_acceptance':app.bind(authority),'historical_repository_acceptance':app.bind(authority),'batch_manifest':app.bind(self.batch),'exact_meaningful_cell_changes':[{'row':0,'column':0,'before':'A','after':'B'}],'trailing_space_padding':[],'files':[]}
  for role,target in [('working accepted TXT',self.text),('current auxiliary reference mirror',self.model),('source review notes',self.notes),('source preview',self.preview)]:
   self.stage['files'].append({'role':role,'target':str(target),'before':app.bind(old) if target==self.text else app.bind(target),'candidate':app.bind(target)})
  self.seal()
 def write(self,p,v):p.write_bytes(app.encode(v))
 def seal(self):
  self.write(self.stage_path,self.stage)
  self.peer={'schema':'socket-reference-batch-independent-acceptance-v1','passed':True,'independent_review':True,'failures':[],'batch_manifest':app.bind(self.batch),'accepted_page_stages':[app.bind(self.stage_path)],'test_fixture_only':True};self.write(self.peer_path,self.peer)
  self.pub={'schema':app.PUBLICATION_SCHEMA,'passed':True,'failures':[],'manifest':app.bind(self.stage_path),'independent_acceptance':app.bind(self.peer_path),'source':self.stage['source'],'published_targets':[app.bind(r['target']) for r in self.stage['files']],'test_fixture_only':True};self.write(self.pub_path,self.pub)
 def prepare(self):return app.prepare(self.stage_path,self.pub_path,self.peer_path,self.adapter,self.registry,self.root,self.exports,self.source_root)
 def test_explicit_table_schema_and_four_live_artifacts(self):
  adapter,registry,item=self.prepare();self.assertEqual(item['artifact_schema'],app.TABLE_QUARTET_SCHEMA);self.assertEqual(set(item['current_quartet']),{'txt','json','notes','preview'})
  self.assertTrue(app.validate_registered_applications(self.registry,self.adapter,self.root,self.exports,self.source_root,adapter=adapter,registry=registry)['passed'])
 def test_no_source_or_adapter_writes_in_preflight(self):
  before=self.adapter.read_bytes();self.prepare();self.assertEqual(self.adapter.read_bytes(),before);self.assertFalse(self.registry.exists())
 def test_nodes_model_rejected_even_with_table_schema(self):
  self.write(self.model,{'board':'02A-A4','source':str(self.source),'nodes':[]});self.stage['files'][1]['candidate']=app.bind(self.model);self.stage['files'][1]['before']=app.bind(self.model);self.seal()
  with self.assertRaisesRegex(ValueError,'sockets-list'):self.prepare()
 def test_scalar_sockets_rejected(self):
  d=app.read(self.model);d['sockets']=['K4'];self.write(self.model,d);self.stage['files'][1]['candidate']=app.bind(self.model);self.stage['files'][1]['before']=app.bind(self.model);self.seal()
  with self.assertRaisesRegex(ValueError,'sockets-list'):self.prepare()
 def test_wrong_board_rejected(self):
  self.stage['board']='02B-E1';self.seal()
  with self.assertRaisesRegex(ValueError,'board differs'):self.prepare()
 def test_wrong_native_source_rejected(self):
  d=app.read(self.model);d['source']=str(self.source.with_name('other.tif'));self.write(self.model,d);self.stage['files'][1]['candidate']=app.bind(self.model);self.stage['files'][1]['before']=app.bind(self.model);self.seal()
  with self.assertRaisesRegex(ValueError,'another native scan'):self.prepare()
 def test_false_model_schema_rejected(self):
  self.stage['model_schema']='ald-page-nodes-v1';self.seal()
  with self.assertRaisesRegex(ValueError,'Unsupported table model'):self.prepare()
 def test_batch_does_not_accept_unlisted_stage(self):
  self.peer['accepted_page_stages']=[];self.write(self.peer_path,self.peer);self.pub['independent_acceptance']=app.bind(self.peer_path);self.write(self.pub_path,self.pub)
  with self.assertRaisesRegex(ValueError,'not independently accepted'):self.prepare()
 def test_changed_live_model_rejected(self):
  adapter,registry,item=self.prepare();self.model.write_bytes(b'{}')
  with self.assertRaisesRegex(ValueError,'Stale binding'):app.validate_registered_applications(self.registry,self.adapter,self.root,self.exports,self.source_root,adapter=adapter,registry=registry)
 def test_missing_json_candidate_rejected(self):
  del self.stage['files'][1];self.seal()
  with self.assertRaises((ValueError,StopIteration)):self.prepare()
 def test_no_invented_columns_proof_allowed(self):
  self.stage['files'][1]['role']='successor columns proof';self.seal()
  with self.assertRaisesRegex(ValueError,'invented columns'):self.prepare()
 def test_changed_batch_hash_rejected(self):
  self.write(self.batch,{'changed':True})
  with self.assertRaisesRegex(ValueError,'Stale binding'):self.prepare()
 def test_record_model_without_source_requires_external_binding(self):
  self.write(self.model,{'board':'02A-A4','records':[{'sockets':['K4']}]});self.stage['model_schema']='socket-page-records-v1'
  with self.assertRaisesRegex(ValueError,'external stage binding'):app.validate_table_model(self.model,self.stage)
 def test_actual_seven_table_models_use_truthful_shapes(self):
  root=Path('D:/Github/IBM360');repo=root/'ibm360ald';models=root/'ALD_Visual_Transcriptions/A1 Socket Listing'
  if not models.is_dir():self.skipTest('Native repository not available')
  expected={'A1114':'sockets','A1121-01':'sockets','A1152-01':'sockets','A1334-01':'sections','A1544-01':'sockets','A1553-01':'records','A1822-01':'records'}
  predecessor=repo/'notes/Reviewed export provenance.json'
  for page,key in expected.items():
   with self.subTest(page=page):
    model=models/(page+' SOCKET LISTING.json');data=app.read(model);native=Path('D:/Reference Materials/IBM 360/IBM_360_ALD/A1 Socket Listing')/(page+' SOCKET LISTING.tif')
    stage={'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':'socket-page-'+key+'-v1','page':page,'board':data['board'],'source':app.bind(native),'files':[{'role':'working accepted TXT','target':str(model.with_suffix('.txt'))}]}
    if 'source'not in data:stage['model_source_binding']={'mode':'external-stage-binding','native_source':stage['source'],'model_target':str(model),'model_candidate':app.bind(model),'accepted_predecessor':app.bind(predecessor)}
    self.assertTrue(app.validate_table_model(model,stage));self.assertEqual(app.TABLE_MODEL_SCHEMAS[stage['model_schema']],key)

if __name__=='__main__':unittest.main()
