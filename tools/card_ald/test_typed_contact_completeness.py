from copy import deepcopy
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_card_data as B

class TypedCompleteness(unittest.TestCase):
    def derive(self,known):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);p=root/'notes/Card-ALD';p.mkdir(parents=True)
            (p/'Manual canonical circuit forms.json').write_text(json.dumps({'circuits':{'U03AF':{'canonical_form':{'primary_function':'A','all_input_triangles':False,'all_output_triangles':True}}}}))
            pin={'side':'input','pin':None,'row':3,'triangle':False}
            if known:pin.update(_pin_number='D04',_pin_number_status='observed')
            out={'side':'output','pin':'B03','row':3,'triangle':True}
            occurrence={'page':'ZZ001','node':'AA','node_pointer':'/nodes/0','portion':'A1','circuit_identifier':'U03AF','function_label':'N','location':'A-A1A1','pins':[pin,out]}
            node={'id':'AA','card_type':'0000','portion':'A1','unit':'U03AF','function':'N','location':'A-A1A1','pins':deepcopy(occurrence['pins'])}
            old=B.ROOT
            try:
                B.ROOT=root;holds=[];model,path=B.derive_semantics('0000',{'listing_portions':['A1']},[occurrence],{'ZZ001':{'nodes':[node],'nets':[]}},B.SINGLE_POWER,holds)
            finally:B.ROOT=old
            return model,holds
    def test_observed_uniform_contact_is_not_anonymous_when_legacy_pin_omitted(self):
        model,holds=self.derive(True)
        self.assertFalse([h for h in holds if h['kind']=='observed pinless ports have no reconstructed internal edge'])
        self.assertEqual([p['pin']for p in model['portions']['A1']['_inputs']],['D04'])
    def test_genuinely_anonymous_input_still_requires_real_internal_edge(self):
        model,holds=self.derive(False)
        h=[h for h in holds if h['kind']=='observed pinless ports have no reconstructed internal edge']
        self.assertEqual(len(h),1);self.assertEqual(h[0]['maximum_visible_pinless_ports'],1)
        self.assertFalse(model['portions']['A1']['_inputs'])

if __name__=='__main__':unittest.main()
