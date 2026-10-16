from copy import deepcopy
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

import build_uniform_socket_listings as builder


def page(name='A1111-01', scan='1'):
    lines=['BOARD 02A-A1', 'A2 SINGLE CARD', '5803308 3308', 'MA905 A1 B1']
    raw=('\n'.join(lines)+'\n').encode()
    return {'page':name,'scan_id':scan,'board':'02A-A1','lines':lines,
        'source_relative':'A1 Socket Listing/'+name+' SOCKET LISTING.tif',
        'text_path':'ALD/A1 Socket Listing/'+name+' SOCKET LISTING.txt',
        'text_sha256':hashlib.sha256(raw).hexdigest(),
        'text_format':{'encoding':'UTF-8','bom':False,'newline':'\n','trailing_newline':True}}


def record():
    return {'id':'1:0:1','board':'02A-A1','sockets':['A2T'],'kind':'SINGLE CARD',
        'part_number':'5803308','card_type':'3308',
        'references':[{'page':'MA905','portions':['A1','B1'],'evidence':[]}],
        'header_source':{'scan_id':'1','page':'A1111-01','row':1,'column':0,'literal':'A2 SINGLE CARD'},
        'source_spans':[{'scan_id':'1','page':'A1111-01','row':1,'column':0,'literal':'A2 SINGLE CARD'}]}


class UniformDatasetTests(unittest.TestCase):
    def test_uniform_fields_and_printed_socket_preserved(self):
        index,pages=builder.build([page()],{'records':[record()]})
        r=index['records'][0]
        self.assertEqual(r['sockets'],['A2T']);self.assertEqual(r['physical_sockets'],['A2'])
        self.assertEqual(r['kind'],'single_card')
        self.assertIsNone(r['destination']);self.assertEqual(r['pin_references'],[])
        self.assertEqual(pages[0]['records'],index['records'])

    def test_continuation_owned_once_but_linked_from_member_page(self):
        r=record();r['source_spans'].append({'scan_id':'2','page':'A1111-02','row':3,'column':0,'literal':'MA905 A1 B1'})
        index,pages=builder.build([page(),page('A1111-02','2')],{'records':[r]})
        self.assertEqual(len(index['records']),1)
        self.assertEqual(pages[1]['records'],[])
        self.assertEqual(pages[1]['continuation_record_ids'],['1:0:1'])

    def test_bad_source_span_rejected(self):
        r=record();r['source_spans'][0]['literal']='A3 SINGLE CARD'
        with self.assertRaisesRegex(ValueError,'does not reproduce'):builder.build([page()],{'records':[r]})

    def test_nested_reference_evidence_checked_independently(self):
        r=record();r['references'][0]['evidence']=[{'scan_id':'1','page':'A1111-01','row':3,'column':0,'literal':'MA905 A2 B1'}]
        with self.assertRaisesRegex(ValueError,'does not reproduce'):builder.build([page()],{'records':[r]})

    def test_same_printed_page_scans_keep_distinct_identity(self):
        a=page();b=page('A1111-02','2');a['printed_page']=b['printed_page']='A1111'
        _,out=builder.build([a,b],{'records':[record()]})
        self.assertEqual([p['page'] for p in out],['A1111-01','A1111-02'])
        self.assertEqual([p['printed_page'] for p in out],['A1111','A1111'])

    def test_supplementary_tables_and_ambiguous_fields_preserved(self):
        r=record();r['ambiguous_fields']={'card_type':['3308','3388']};r['unused_sockets']=['A3']
        table={'kind':'plug_list','evidence':{'scan_id':'1','page':'A1111-01','row':2,'column':0,'literal':'5803308 3308'}}
        index,out=builder.build([page()],{'records':[r],'tables':[table]})
        self.assertEqual(index['records'][0]['ambiguous_fields'],r['ambiguous_fields'])
        self.assertEqual(index['records'][0]['unused_sockets'],['A3'])
        self.assertEqual(out[0]['supplementary_tables'],[table])

    def test_missing_header_and_duplicate_ids_rejected(self):
        r=record();r['header_source']['scan_id']='unknown'
        with self.assertRaisesRegex(ValueError,'header'):builder.build([page()],{'records':[r]})
        with self.assertRaisesRegex(ValueError,'duplicate'):builder.build([page()],{'records':[record(),record()]})

    def test_exact_crlf_bom_and_trailing_spaces(self):
        p=page();p['lines']=['BOARD 02A-A1  ','A2 SINGLE CARD ']
        p['text_format'].update(bom=True,newline='\r\n')
        raw=b'\xef\xbb\xbfBOARD 02A-A1  \r\nA2 SINGLE CARD \r\n'
        self.assertEqual(builder.reconstruct_text(p),raw)

    def test_mixed_line_endings_reconstruct(self):
        p=page();p['lines']=['a','b','c'];p['text_format'].update(newline='mixed',line_endings=['\r\n','\n'],trailing_newline=False)
        self.assertEqual(builder.reconstruct_text(p),b'a\r\nb\nc')

    def test_unreadable_values_and_issues_preserved(self):
        r=record();r['card_type']='33��';r['references'][0]['portions']=['�1']
        index,_=builder.build([page()],{'records':[r],'issues':[{'kind':'unparsed'}]})
        self.assertEqual(index['records'][0]['card_type'],'33��')
        self.assertEqual(index['records'][0]['references'][0]['portions'],['�1'])
        self.assertEqual(index['issues'],[{'kind':'unparsed'}])

    def test_data_serialization_is_deterministic(self):
        args=([page()],{'records':[record()]})
        self.assertEqual(builder.encoded(builder.build(*deepcopy(args))[0]),builder.encoded(builder.build(*deepcopy(args))[0]))

    def fixture(self,root,raw):
        path=root/'ALD/A1 Socket Listing/A1111-01 SOCKET LISTING.txt';path.parent.mkdir(parents=True);path.write_bytes(raw)
        proof=root/'notes/Reviewed export provenance.json';proof.parent.mkdir()
        proof.write_text(json.dumps({'exported':[{'destination':'Z:/old checkout/ALD/A1 Socket Listing/A1111-01 SOCKET LISTING.txt',
            'source_relative':'A1 Socket Listing/A1111-01 SOCKET LISTING.tif','page':'A1111-01','source_scan_id':1,
            'text_sha256':hashlib.sha256(raw).hexdigest()}]}),'utf8')
        return path

    def test_accepted_input_portable_to_another_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root,b'BOARD 02A-A1\n')
            pages,bindings=builder.load_pages(root)
            self.assertEqual(pages[0]['board'],'02A-A1');self.assertEqual(len(bindings),2)

    def test_stale_txt_and_ambiguous_board_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=self.fixture(root,b'BOARD 02A-A1\n');p.write_bytes(b'BOARD 02B-A1\n')
            with self.assertRaisesRegex(ValueError,'changed after acceptance'):builder.load_pages(root)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root,b'BOARD 02A-A1\nBOARD 02B-A1\n')
            with self.assertRaisesRegex(ValueError,'one readable BOARD'):builder.load_pages(root)


if __name__=='__main__':unittest.main()
