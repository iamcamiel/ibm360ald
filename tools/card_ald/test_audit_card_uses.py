"""Focused defect-injection tests for the generic read-only card auditor."""
import unittest
import tempfile
import json
from pathlib import Path
from copy import deepcopy
import audit_card_uses as audit


def box():
    return {'portion':'Z1','function':'A','circuit_identifier':'U03AA','ports':[
        {'id':'i1','side':'input','pin':'B02','triangle':False,'row':1},
        {'id':'i2','side':'input','pin':'D02','triangle':False,'row':2},
        {'id':'o1','side':'output','pin':'B03','triangle':True,'row':3}]}


def node():
    b=box()
    return {'id':'AA','portion':b['portion'],'function':'A','unit':b['circuit_identifier'],
        'pins':[{'side':p['side'],'pin':p['pin'],'triangle':p['triangle'],'row':p['row']} for p in b['ports']]}


def compare(n,b=None,forms=None):
    b=b or box();return audit.compare_occurrence(n,b,forms or [{**b,'variant_number':0}],{'D08':'GROUND'})


class CardAuditTests(unittest.TestCase):
    def test_fallback_skips_auxiliary_array_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);columns=root/'json/A1 Socket Listing/table.json';columns.parent.mkdir(parents=True)
            columns.write_text(json.dumps([{'pin':'B02'}]),encoding='utf-8')
            model=root/'json/XX/XX001.json';model.parent.mkdir(parents=True)
            model.write_text(json.dumps({'page':'XX001','nodes':[{'id':'AA','card_type':'1234'}]}),encoding='utf-8')
            documents,issues=audit.load_documents(root,{'card_type':'1234','diagram_occurrences':[]})
            self.assertEqual(set(documents),{model});self.assertEqual(issues,[])

    def test_omitted_unused_input(self):
        n=node();n['pins'].pop(1)
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in compare(n)))

    def test_demorgan_requires_opposite_marks(self):
        n=node();n['function']='OR'
        for p in n['pins']:p['triangle']=not p['triangle']
        self.assertTrue(any(f['status']=='equivalent' for f in compare(n)))
        n['pins'][0]['triangle']=False
        self.assertTrue(any(f['status']=='discrepancy' for f in compare(n)))

    def test_pin_direction_and_circuit_defects(self):
        for change in ('pin','side','unit'):
            n=node()
            if change=='pin':n['pins'][0]['pin']='B04'
            elif change=='side':n['pins'][0]['side']='output'
            else:n['unit']='U03ZZ'
            self.assertTrue(any(f['status']=='discrepancy' for f in compare(n)))

    def test_recorded_variant(self):
        n=node();n['pins'][0]['triangle']=True
        form=deepcopy(box());form['ports'][0]['triangle']=True;form['variant_number']=17
        self.assertTrue(any(f['status']=='recorded_variant' for f in compare(n,forms=[{**box(),'variant_number':0},form])))

    def test_power_tie_not_extra_input(self):
        n=node();n['pins'].append({'pin':'D08','side':'input','row':4,'triangle':False})
        flags=compare(n)
        self.assertTrue(any(f['field']=='power_contact' for f in flags))
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in flags))

    def test_one_input_n_needs_same_circuit_and_polarity(self):
        n=node();n['pins'].pop(1);n['function']='N'
        self.assertTrue(any(f['status']=='equivalent' for f in compare(n)))
        n['unit']='U03ZZ'
        self.assertFalse(any(f['status']=='equivalent' for f in compare(n)))

    def test_qualifier_and_wire_annotation(self):
        n=node();n['pins'][0]['pin']='2B02';n['pins'][1]['pin']='L'
        b=box();b['ports'][1]['pin']=None
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in compare(n,b)))

    def test_pinless_terminal_cross_swap_not_certified(self):
        a={'portion':'Z1','function':'AR','ports':[
            {'id':'o1','row':11,'side':'output','pin':None,'triangle':False},
            {'id':'o2','row':12,'side':'output','pin':None,'triangle':True}]}
        b={'portion':'Z2','function':'AR','ports':[
            {'id':'i1','row':21,'side':'input','pin':None,'triangle':False},
            {'id':'i2','row':22,'side':'input','pin':None,'triangle':True}]}
        spec={'boxes':[a,b],'nets':[['PORT:Z1:o1','PORT:Z2:i1'],['PORT:Z1:o2','PORT:Z2:i2']]}
        nodes=[{'id':key,'card_type':'9999','portion':item['portion'],'location':'A-A1A1','pins':deepcopy(item['ports'])} for key,item in [('AA',a),('BB',b)]]
        doc={'page':'XX001','nodes':nodes,'nets':[{'id':'wrong','driver':'AA.output12','targets':['BB.input21']}]}
        flags,observations=audit.audit_wiring('9999',spec,{'fixture':{'document':doc}})
        self.assertTrue(any(f['status']=='discrepancy' for f in flags))
        self.assertFalse(any(o['classification']=='common_internal_link' for o in observations))

    def test_declared_extra_driver_is_checked(self):
        boxes=[];nodes=[]
        for portion,key,side,pin in [('Z1','AA','output','B02'),('Z2','BB','output','B03'),('Z3','CC','input',None)]:
            port={'id':'p1','row':3,'side':side,'pin':pin,'triangle':False}
            boxes.append({'portion':portion,'function':'A','ports':[port]})
            nodes.append({'id':key,'card_type':'9999','portion':portion,'location':'A-A1A1','pins':[deepcopy(port)]})
        spec={'boxes':boxes,'nets':[['PORT:Z1:p1','PORT:Z3:p1'],['PORT:Z2:p1','PIN:B03']]}
        doc={'page':'XX001','nodes':nodes,'nets':[{'id':'bad','driver':'AA.B02','declared_physical_output_drivers':['AA.B02','BB.B03'],'targets':['CC.input3']}]}
        flags,_=audit.audit_wiring('9999',spec,{'fixture':{'document':doc}})
        self.assertTrue(any(f['field']=='multiple_internal_drivers' for f in flags))


if __name__=='__main__':unittest.main()
