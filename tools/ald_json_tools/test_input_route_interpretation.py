"""Semantic selectors require both recorded source order and owned route proof."""
from collections import defaultdict
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import convert_ald_json as C


class InputRouteInterpretationTests(unittest.TestCase):
    def trial(self):
        c=object.__new__(C.Converter);c.object_ids={'AN':'AN'};c.auxiliary=set()
        c.primary_aliases={};c.aliases={};c.semantic_input_resolutions=[]
        c.terminals={
            'blocks/AN/pins/L/2':dict(terminal_id='p1',side='input',geometry=dict(point=[49,11],row=11),source_literals={}),
            'blocks/AN/pins/R/3':dict(terminal_id='out',side='output',geometry=dict(point=[58,12],row=12),source_literals={}),
            'blocks/AN/pins/L/4':dict(terminal_id='p2',side='input',geometry=dict(point=[49,13],row=13),source_literals={})}
        c.owners={'AN':dict(terminals=list(c.terminals.values()),source_form=dict(terminal_collections=[dict(field='pins',representation='array',members=[dict(terminal_id=x)for x in ('p1','out','p2')])]))}
        c.paths={'upper':[[[20,11],[49,11]]],'lower':[[[20,13],[49,13]]]}
        c.graphs={k:C.wire_graph(v)for k,v in c.paths.items()}
        return c

    def test_source_order_and_unique_owned_route_must_agree(self):
        c=self.trial()
        self.assertEqual(c.resolve('AN.input1','target','upper'),'blocks/AN/pins/L/2')
        self.assertEqual(c.resolve('AN.input2','target','lower'),'blocks/AN/pins/L/4')
        self.assertEqual(len(c.semantic_input_resolutions),2)

    def test_array_order_alone_does_not_establish_selector_semantics(self):
        c=self.trial()
        self.assertEqual(c.terminal_candidates('AN.input1','target'),[])
        with self.assertRaises(C.ConversionError):c.resolve('AN.input1','target')

    def test_missing_opposite_or_multiple_owned_endpoints_stay_held(self):
        c=self.trial();c.paths['both']=c.paths['upper']+c.paths['lower']
        for context in ('missing','lower','both'):
            with self.subTest(context=context):
                self.assertEqual(c.terminal_candidates('AN.input1','target',context),[])
        self.assertFalse(c.semantic_input_resolutions)

    def test_route_interior_crossing_is_not_endpoint_evidence(self):
        c=self.trial();c.paths['crossing']=[[[20,11],[90,11]]]
        self.assertEqual(c.terminal_candidates('AN.input1','target','crossing'),[])

    def test_driver_zero_leading_zero_and_wrong_owner_cannot_use_fallback(self):
        c=self.trial()
        for ref,role in [('AN.input1','driver'),('AN.input0','target'),('AN.input01','target'),('ZZ.input1','target')]:
            with self.subTest(ref=ref,role=role):self.assertEqual(c.terminal_candidates(ref,role,'upper'),[])

    def test_explicit_alias_has_precedence_and_ambiguity_is_not_hidden(self):
        c=self.trial();first='blocks/AN/pins/L/2';second='blocks/AN/pins/L/4'
        c.aliases['AN.input1']=[second]
        self.assertEqual(c.resolve('AN.input1','target'),second)
        c.aliases['AN.input1']=[first,second]
        with self.assertRaises(C.ConversionError):c.resolve('AN.input1','target','upper')

    def test_missing_incomplete_reordered_and_malformed_arrays_do_not_guess(self):
        for mutation in ('missing','incomplete','reordered','duplicate','null','list-id'):
            c=self.trial();collection=c.owners['AN']['source_form']['terminal_collections'];members=collection[0]['members']
            if mutation=='missing':collection.clear()
            elif mutation=='incomplete':members.pop()
            elif mutation=='reordered':members.reverse()
            elif mutation=='duplicate':members[1]['terminal_id']='p1'
            elif mutation=='null':members[0]['terminal_id']=None
            else:members[0]['terminal_id']=[]
            with self.subTest(mutation=mutation):self.assertEqual(c.terminal_candidates('AN.input1','target','upper'),[])

    def test_no_physical_identity_is_created_and_duplicate_proof_is_not_repeated(self):
        c=self.trial();before=copy.deepcopy(c.terminals)
        c.resolve('AN.input1','target','upper');c.resolve('AN.input1','target','upper')
        self.assertEqual(c.terminals,before)
        self.assertEqual(len(c.semantic_input_resolutions),1)

    def test_actual_coordinate_source_stays_original_but_row_lookup_uses_page_row(self):
        from test_converter import source
        p=source('AP761')
        raw=p.read_bytes();doc=json.loads(raw);before=copy.deepcopy(doc)
        c=C.Converter(doc,p,C.digest(raw),Path(__file__).resolve().parents[2]/'ALD/AP Parallel Adder'/p.with_suffix('.txt').name)
        self.assertEqual(doc,before)
        self.assertEqual(c.owners['AA']['terminals'][0]['geometry']['row'],3)
        self.assertEqual(c.terminals['blocks/AA/pins/L/4']['geometry']['row'],19)
        self.assertEqual(c.resolve('AA.D06@19','target'),'blocks/AA/pins/L/4')
        self.assertEqual(c.recorded_route_anchors('blocks/AA/pins/L/4'),set())


if __name__=='__main__':unittest.main()
