"""Independent verifier fixtures assembled without importing builder/parser."""
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

import verify_uniform_socket_listings as verifier


def rawjson(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def digest(raw): return hashlib.sha256(raw).hexdigest()


class VerificationTests(unittest.TestCase):
    def setUp(self):
        # Tests live outside the repository and honor the host TEMP/TMP area.
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMP') or os.environ.get('TEMP'))
        self.base = Path(self.temp.name); self.repo = self.base/'repo'; self.data = self.base/'candidate'
        self.lines = [['BOARD 02A-A1  ','A2T SINGLE CARD','5803308 3308','MA905 A1  '],
                      ['BOARD 02A-A1','B1','PLUG LIST','UNREADABLE']]
        self.formats = [{'encoding':'UTF-8','bom':True,'newline':'\r\n','trailing_newline':True},
                        {'encoding':'UTF-8','bom':False,'newline':'mixed','line_endings':['\n','\r\n','\r'],'trailing_newline':False}]
        raw = [b'\xef\xbb\xbf'+('\r\n'.join(self.lines[0])+'\r\n').encode(), b'BOARD 02A-A1\nB1\r\nPLUG LIST\rUNREADABLE']
        self.accepted = []
        for i,name in enumerate(['A1111-01','A1111-02']):
            rel = 'ALD/A1 Socket Listing/'+name+' SOCKET LISTING.txt'; self.put(self.repo,rel,raw[i])
            self.accepted.append({'destination':'Z:/old checkout/'+rel,'text_sha256':digest(raw[i]),'page':'A1111',
                                  'source_scan_id':str(i+1),'source_relative':'A1 Socket Listing/'+name+' SOCKET LISTING.tif'})
        self.put(self.repo,'notes/Reviewed export provenance.json',rawjson({'exported':self.accepted}))
        for name in ['build_uniform_socket_listings.py','socket_text_parser.py']:
            self.put(self.repo,'tools/references/'+name,b'# Bound fixture tool; never executed.\n')
        def span(scan,row): return {'page':'A1111-0'+str(scan),'scan_id':str(scan),'row':row,'column':0,'literal':self.lines[scan-1][row]}
        self.record = {'id':'1:0:1','board':'02A-A1','sockets':['A2T'],'physical_sockets':['A2'],'kind':'single_card',
            'kind_literal':'SINGLE CARD','part_number':'5803308','card_type':'3308','ambiguous_fields':{},
            'references':[{'page':'MA905','portions':['A1','B1'],'source_spans':[span(1,3),span(2,1)]}],
            'pin_references':[],'unused_portions':[],'unused_pins':[],'unused_sockets':[],
            'connector_listing':None,'wire_code':None,'destination':None,'header_source':span(1,1),
            'source_spans':[span(1,1),span(1,2),span(1,3),span(2,1)],'raw_lines':[span(1,1)],'issues':[]}
        self.index = {'schema':verifier.SCHEMA,'document_kind':'socket_listing_collection','policy':'Accepted TXT only.',
            'records':[self.record],'issues':[{'kind':'unparsed_significant_line','evidence':span(2,3)}],
            'supplementary_tables':[{'kind':'plug_list','evidence':span(2,2)}],'parser_coverage':{'scans':2},
            'counts':{'source_pages':2,'boards':1,'logical_records':1,'record_kinds':{'single_card':1},
                      'card_instances':1,'portion_references':2,'source_spans_verified':8,'parser_issues':1}}
        self.pages = []
        for i,name in enumerate(['A1111-01','A1111-02']):
            self.pages.append({'schema':verifier.SCHEMA,'document_kind':'socket_listing_page','page':name,'printed_page':'A1111','board':'02A-A1',
                'board_source_spans':[{'row':0,'column':6,'literal':'02A-A1','page':name,'scan_id':str(i+1)}],
                'source':{'scan_id':str(i+1),'source_relative':self.accepted[i]['source_relative'],
                          'text_path':'ALD/A1 Socket Listing/'+name+' SOCKET LISTING.txt','text_sha256':digest(raw[i]),'text_format':self.formats[i]},
                'grid':{'rows':4,'columns':max(map(len,self.lines[i])),'lines':self.lines[i]},
                'records':[deepcopy(self.record)] if i==0 else [],'continuation_record_ids':[] if i==0 else [self.record['id']],
                'supplementary_tables':[] if i==0 else deepcopy(self.index['supplementary_tables'])})
        self.csvrows = [['1:0:1','02A-A1','A2T','single_card','5803308','3308','MA905',p] for p in ['A1','B1']]
        self.write()

    def tearDown(self): self.temp.cleanup()

    def put(self,base,relative,raw):
        path=base/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)

    def write(self):
        files = {verifier.INDEX:rawjson(self.index),'notes/Socket listings uniform/README.txt':b'Fixture README\n'}
        for page in self.pages:
            files['json/Socket listings uniform/pages/'+str(Path(page['source']['source_relative']).with_suffix('.json')).replace('\\','/')] = rawjson(page)
        stream=io.StringIO(newline=''); writer=csv.writer(stream);writer.writerow(verifier.CSV_FIELDS);writer.writerows(self.csvrows)
        files[verifier.CSV]=stream.getvalue().encode('utf-8-sig')
        for rel,raw in files.items():self.put(self.data,rel,raw)
        inputs=['notes/Reviewed export provenance.json',*[p['source']['text_path'] for p in self.pages],
                'tools/references/build_uniform_socket_listings.py','tools/references/socket_text_parser.py']
        self.manifest={'schema':'uniform-socket-listing-build-v1','counts':deepcopy(self.index['counts']),
            'inputs':[{'path':p,'sha256':digest((self.repo/p).read_bytes())} for p in inputs],
            'files':[{'path':p,'sha256':digest(raw)} for p,raw in files.items()],
            'legacy_models_modified':False,'original_scans_read_or_modified':False}
        self.put(self.data,verifier.MANIFEST,rawjson(self.manifest))

    def result(self):return verifier.verify(self.repo,self.data)
    def bad(self,text):
        result=self.result();self.assertFalse(result['passed'],result);self.assertTrue(any(text in x for x in result['failures']),result)

    def test_valid_mixed_endings_bom_continuation_and_diagnostics(self):
        r=self.result();self.assertTrue(r['passed'],r);self.assertEqual(r['proof_counts']['accepted_grids_roundtripped'],2)
        self.assertEqual(r['parser_diagnostics']['status'],'unresolved');self.assertEqual(r['parser_diagnostics']['count'],1)
        self.assertEqual(r['proof_counts']['continuation_links_verified'],1)

    def test_stale_tool_hash_fails(self):
        self.put(self.repo,'tools/references/socket_text_parser.py',b'# changed\n');self.bad('Stale/missing input binding')

    def test_stale_accepted_text_fails(self):
        self.put(self.repo,self.pages[0]['source']['text_path'],b'changed');self.bad('Stale/missing input binding')

    def test_rebound_grid_edit_cannot_change_accepted_cells(self):
        self.pages[0]['grid']['lines'][3]='MA905 Z1  ';self.write();self.bad('roundtrip exact accepted TXT')

    def test_bom_or_newline_loss_fails(self):
        self.pages[0]['source']['text_format']['bom']=False;self.write();self.bad('roundtrip exact accepted TXT')

    def test_uniform_record_keys_required(self):
        self.record['unexpected']=True;self.pages[0]['records'][0]['unexpected']=True;self.write();self.bad('Nonuniform logical record keys')

    def test_collection_record_id_duplicates_fail(self):
        self.index['records'].append(deepcopy(self.record));self.write();self.bad('Duplicate/invalid logical record ID')

    def test_wrong_header_owner_fails_even_when_rebound(self):
        self.pages[1]['records']=[deepcopy(self.record)];self.write();self.bad('header ownership')

    def test_missing_continuation_id_fails(self):
        self.pages[1]['continuation_record_ids']=[];self.write();self.bad('Continuation record IDs differ')

    def test_nested_evidence_literal_checked(self):
        self.record['references'][0]['source_spans'][0]['literal']='MA905 Z1  '
        self.pages[0]['records'][0]=deepcopy(self.record);self.write();self.bad('Evidence literal differs')

    def test_nested_evidence_page_scan_agreement_checked(self):
        self.record['references'][0]['source_spans'][0]['scan_id']='2'
        self.pages[0]['records'][0]=deepcopy(self.record);self.write();self.bad('Evidence page/scan disagree')

    def test_boolean_coordinate_not_accepted_as_integer(self):
        self.record['header_source']['row']=True;self.pages[0]['records'][0]=deepcopy(self.record)
        self.write();self.bad('Invalid evidence coordinates')

    def test_duplicate_scan_ids_fail(self):
        self.accepted[1]['source_scan_id']='1';self.pages[1]['source']['scan_id']='1'
        self.put(self.repo,'notes/Reviewed export provenance.json',rawjson({'exported':self.accepted}));self.write();self.bad('Duplicate/mismatched scan ID')

    def test_printed_base_page_cannot_replace_unique_scan_page(self):
        self.pages[1]['page']='A1111';self.write();self.bad('Page/printed-page identity differs')

    def test_csv_multiset_not_just_row_count(self):
        self.csvrows[1]=deepcopy(self.csvrows[0]);self.write();self.bad('CSV reference multiset differs')

    def test_board_proof_inventory_checked(self):
        self.pages[0]['board_source_spans']=[];self.write();self.bad('Board proof inventory differs')

    def test_unlisted_output_file_fails(self):
        self.put(self.data,'json/Socket listings uniform/pages/unlisted.json',b'{}');self.bad('Unlisted files')

    def test_wrong_recomputed_counts_fail(self):
        self.index['counts']['source_spans_verified']=999;self.write();self.bad('counts differ from independent recomputation')

    def test_pin_reference_requires_uniform_keys_and_status(self):
        pin={'pin':'B02','printed_socket':None,'listing_socket':'A2T','ALD_reference':None,
             'reference_status':'no_reference_printed','evidence':deepcopy(self.record['header_source'])}
        self.record['pin_references']=[pin];self.pages[0]['records'][0]=deepcopy(self.record);self.write()
        self.assertTrue(self.result()['passed'],self.result())
        del pin['listing_socket'];self.pages[0]['records'][0]=deepcopy(self.record);self.write();self.bad('Pin-reference schema differs')

    def test_pin_reference_status_not_inferred_from_modal_neighbor(self):
        pin={'pin':'B02','printed_socket':None,'listing_socket':None,'ALD_reference':None,
             'reference_status':'listed','evidence':deepcopy(self.record['header_source'])}
        self.record['pin_references']=[pin];self.pages[0]['records'][0]=deepcopy(self.record);self.write();self.bad('Pin-reference status differs')

    def test_cli_report_outside_repository_and_exit_status(self):
        report=self.base/'independent.json'
        result=subprocess.run([sys.executable,str(Path(verifier.__file__).resolve()),'--repo',str(self.repo),
                               '--dataset',str(self.data),'--report',str(report)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(report.read_text('utf-8'))['passed'])

    def test_cli_refuses_to_write_report_inside_repository(self):
        report=self.repo/'forbidden.json'
        result=subprocess.run([sys.executable,str(Path(verifier.__file__).resolve()),'--repo',str(self.repo),
                               '--dataset',str(self.data),'--report',str(report)],capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(result.returncode,0);self.assertFalse(report.exists())


if __name__=='__main__':unittest.main()
