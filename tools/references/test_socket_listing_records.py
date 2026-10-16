from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

import socket_listing_records as L


class SocketSources(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'tmp');self.repo=Path(self.temp.name)
        self.manifest=[];self.export=[]
        self.names=['A1111-01 SOCKET LISTING','A1111-02 SOCKET LISTING']
        self.base={'board':'02A-A1','sockets':['J6'],'kind':'single_card','card_type':'3308','part_number':'5803���','source_listing':self.names[0],
                   'source_section_indices':[0,1],'references':[{'ALD_page':'MA905','printed_portions':['A1','�1','C1']}]}
        self.raw=[{**deepcopy(self.base),'source_section_indices':[]},{'board':'02A-A1','sockets':['J6'],'kind':'continuation','source_listing':self.names[1]}]
        self.direct={'board':'02A-A1','sockets':[{'socket':'J6','kind':'single_card','card_type':'3308','part_number':'5803308','references':[{'ALD_page':'MA905','printed_portions':['A1','B1']}]}]}
        self.add_txt(self.names[0]);self.add_txt(self.names[1])
        self.add_json('json/A1 Socket Listing/'+self.names[0]+'.json',self.direct)
    def tearDown(self):self.temp.cleanup()
    def write(self,p,raw):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def add_txt(self,name):
        relative='A1 Socket Listing/'+name+'.tif';p=self.repo/'ALD/A1 Socket Listing'/(name+'.txt');self.write(p,b'accepted text')
        self.export.append({'source_relative':relative,'destination':str(p),'text_sha256':L._hash(p)})
    def add_json(self,relative,value,role='Published page content model'):
        p=self.repo/relative;self.write(p,(json.dumps(value,ensure_ascii=False)+'\n').encode('utf-8'))
        entry={'path':relative,'sha256':L._hash(p),'role':role};self.manifest=[e for e in self.manifest if e['path']!=relative]+[entry]
    def load(self):
        self.add_json('json/A1 Socket Listing/Socket reference.json',{'delivered_pages':self.names,'records':self.raw,'logical_records':[self.base],'continuation_links':[{'section_index':1,'parent_section_index':0}]},'Reviewed collection content table')
        self.write(self.repo/'notes/Content data manifest.json',json.dumps({'files':self.manifest}).encode())
        self.write(self.repo/'notes/Reviewed export provenance.json',json.dumps({'exported':self.export}).encode())
        return L.load_listings(self.repo)
    def test_corrected_current_fields_and_continuation_portions(self):
        r=self.load();x=r['records'][0]
        self.assertEqual(x['part_number'],'5803308');self.assertEqual(x['references'][0]['portions'],['A1','B1','C1'])
        self.assertEqual(r['coverage']['accepted_listing_scans'],2);self.assertEqual(r['issues'],[])
        self.assertGreater(len(r['stale_compiled_differences']),0)
    def test_occupied_sockets_normalizes_double_card(self):
        self.base['sockets']=['J6','J7'];self.base['kind']='double_card'
        self.direct['sockets'][0].update(kind='double_card',occupied_sockets=['J6','J7'])
        self.add_json('json/A1 Socket Listing/'+self.names[0]+'.json',self.direct)
        r=self.load();self.assertEqual(r['coverage']['current_card_records_overlaid'],1);self.assertFalse(r['issues'])
    def test_current_record_board_without_document_board(self):
        self.direct['sockets'][0]['board']=self.direct.pop('board')
        self.add_json('json/A1 Socket Listing/'+self.names[0]+'.json',self.direct)
        self.assertEqual(self.load()['coverage']['current_card_records_overlaid'],1)
    def test_readable_base_only_continuation_is_retained(self):
        self.base['references'][0]['printed_portions']=['A1','B1','C1']
        self.assertEqual(self.load()['records'][0]['references'][0]['portions'],['A1','B1','C1'])
    def test_explicit_current_continuation_can_add_members(self):
        cont={'board':'02A-A1','records':[{'sockets':['J6'],'kind':'CONTINUATION','continues_socket':'J6','references':[{'ALD_page':'MA905','printed_portions':['D1']}]}]}
        self.add_json('json/A1 Socket Listing/'+self.names[1]+'.json',cont)
        self.assertIn('D1',self.load()['records'][0]['references'][0]['portions'])
    def test_shared_board_schema_is_used(self):
        self.manifest=[]
        shared={'board':'02A-A1','pages':['A1111-01','A1111-02'],'socket_records':[self.direct['sockets'][0]]}
        self.add_json('json/A1 Socket Listing/A1111 BOARD.json',shared,'Accepted existing A1 board model or source-column table')
        r=self.load();self.assertEqual(r['coverage']['current_shared_board_models'],1);self.assertEqual(r['coverage']['current_direct_covered_scans'],2)
    def test_changed_accepted_json_is_rejected(self):
        self.load();p=self.repo/'json/A1 Socket Listing'/ (self.names[0]+'.json');p.write_bytes(b'{}')
        self.assertRaises(ValueError,L.load_listings,self.repo)
    def test_changed_accepted_txt_is_rejected(self):
        self.load();p=self.repo/'ALD/A1 Socket Listing'/(self.names[0]+'.txt');p.write_bytes(b'changed')
        self.assertRaises(ValueError,L.load_listings,self.repo)
    def test_conflicting_current_identity_is_explicit(self):
        other=deepcopy(self.direct);other['sockets'][0]['card_type']='3309'
        self.add_json('json/A1 Socket Listing/'+self.names[1]+'.json',other)
        self.assertTrue(any(x['kind']=='incompatible_current_card_identity' for x in self.load()['issues']))
    def test_damaged_page_mask_requires_one_current_match(self):
        self.base['references'][0]['ALD_page']='MA9�5'
        r=self.load();self.assertEqual(r['records'][0]['references'][0]['page'],'MA905')
    def test_all_claims_keep_raw_section_and_current_model_proof(self):
        x=self.load()['records'][0]
        self.assertTrue(any(e.get('raw_section_index')==1 for e in x['evidence']))
        self.assertTrue(any(e['pointer']=='/sockets/0' for e in x['references'][0]['evidence']))


if __name__=='__main__':unittest.main()
