import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import convert_ald_json as C

class NamedInputRouteAliasTests(unittest.TestCase):
    def trial(self):
        c=object.__new__(C.Converter)
        c.object_ids={'AL':'AL'}; c.auxiliary=set(); c.primary_aliases={}; c.aliases={}; c.semantic_input_resolutions=[]
        c.terminals={
            'blocks/AL/pins/L/1':dict(terminal_id='t1',side='input',pin_number=None,pin_number_status='unlabeled',geometry=dict(point=[72,17],row=17,column=72),source_literals={}),
            'blocks/AL/pins/L/2':dict(terminal_id='t2',side='input',pin_number=None,pin_number_status='unlabeled',geometry=dict(point=[72,18],row=18,column=72),source_literals={}),
            'blocks/AL/pins/R/3':dict(terminal_id='to',side='output',pin_number=None,pin_number_status='unlabeled',geometry=dict(point=[81,19],row=19,column=81),source_literals={})}
        tids=['t1','t2','to']
        c.owners={'AL':dict(terminals=[copy.deepcopy(c.terminals[f'blocks/AL/pins/L/1']),copy.deepcopy(c.terminals[f'blocks/AL/pins/L/2']),copy.deepcopy(c.terminals[f'blocks/AL/pins/R/3'])],source_form=dict(terminal_collections=[dict(field='pins',representation='array',members=[dict(terminal_id=x) for x in tids])]))}
        claim=dict(relationship='targets',role_category='declared-target',resolution_status='source-claim-unresolved',reference=dict(kind='unparsed-object-reference',object_identifier='AL',port_reference_text='inputAC',parse_status='unresolved-source-syntax'))
        c.nets={'AC':dict(literal_id='AC',source_literals=dict(id='AC',targets=['AL.inputAC']),endpoint_claims=[claim])}; c.paths={'AC':[[[58,12],[72,17]]]}; c.graphs={}
        return c
    def test_exact_named_claim_and_unique_route_endpoint_resolve_without_pin_identity(self):
        c=self.trial(); before=copy.deepcopy(c.terminals)
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),['blocks/AL/pins/L/1'])
        self.assertEqual(c.terminals,before)
        proof=c.semantic_input_resolutions[0]
        self.assertEqual(proof['source input order'],1)
        self.assertEqual(proof['recorded route endpoints'],[(72,17)])
        self.assertIsNone(c.terminals['blocks/AL/pins/L/1']['pin_number'])
    def test_named_alias_does_not_use_route_interior_or_other_net(self):
        c=self.trial(); c.paths={'AC':[[[1,17],[99,17]]]}
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
        c=self.trial(); c.paths={'other':[[[58,12],[72,17]]]}
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_alias_suffix_is_not_used_as_input_ordinal(self):
        c=self.trial(); c.paths={'AC':[[[58,13],[72,18]]]}
        self.assertEqual(c.resolve('AL.inputAC','target','AC'),'blocks/AL/pins/L/2')
        self.assertEqual(c.semantic_input_resolutions[0]['source input order'],2)
        self.assertIsNone(c.terminals['blocks/AL/pins/L/2']['pin_number'])
    def test_multiple_exact_input_endpoints_fail_closed(self):
        c=self.trial(); c.paths={'AC':[[[58,12],[72,17]],[[58,13],[72,18]]]}
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
        self.assertFalse(c.semantic_input_resolutions)
    def test_missing_or_nonidentical_same_net_claim_fails_closed(self):
        c=self.trial(); c.nets['AC']['endpoint_claims']=[]
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
        c=self.trial(); other=copy.deepcopy(c.nets['AC']['endpoint_claims'][0])
        other['conflicting terminal observation']='blocks/AL/pins/L/2'
        c.nets['AC']['endpoint_claims'].append(other)
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_identical_duplicate_claims_keep_full_history_and_one_selection(self):
        c=self.trial(); c.nets['AC']['endpoint_claims']*=2; original=copy.deepcopy(c.nets)
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),['blocks/AL/pins/L/1'])
        self.assertEqual(c.nets,original)
        self.assertEqual(c.semantic_input_resolutions[0]['source target claim observations'],original['AC']['endpoint_claims'])
    def test_repeated_declared_target_does_not_create_another_terminal(self):
        c=self.trial(); c.nets['AC']['source_literals']['targets']*=2; original=copy.deepcopy(c.nets)
        self.assertEqual(c.resolve('AL.inputAC','target','AC'),'blocks/AL/pins/L/1')
        self.assertEqual(c.nets,original)
    def test_missing_source_form_is_a_controlled_hold(self):
        c=self.trial(); c.owners['AL']['source_form']=None
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_one_point_path_does_not_establish_a_routed_input(self):
        c=self.trial(); c.paths['AC']=[[[72,17]]]
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_incomplete_reordered_duplicate_or_malformed_source_arrays_fail_closed(self):
        for case in ('incomplete','reordered','duplicate','malformed'):
            c=self.trial(); members=c.owners['AL']['source_form']['terminal_collections'][0]['members']
            if case=='incomplete':members.pop()
            elif case=='reordered':members.reverse()
            elif case=='duplicate':members[1]['terminal_id']='t1'
            else:members[1]['terminal_id']=None
            with self.subTest(case=case):self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_explicit_alias_precedence_and_driver_role_are_preserved(self):
        c=self.trial(); c.primary_aliases={'AL.inputAC':['blocks/AL/pins/L/2']}; c.aliases=copy.deepcopy(c.primary_aliases); c.paths={}
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),['blocks/AL/pins/L/2'])
        c=self.trial(); self.assertEqual(c.terminal_candidates('AL.inputAC','driver','AC'),[])

    def test_net_id_target_membership_and_missing_maps_fail_closed(self):
        for mutate in (
            lambda c: c.nets['AC'].__setitem__('literal_id','ZZ'),
            lambda c: c.nets['AC']['source_literals'].__setitem__('id','ZZ'),
            lambda c: c.nets['AC']['source_literals'].__setitem__('targets',[]),
        ):
            c=self.trial(); mutate(c); self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
        # Converter construction always initializes object_ids. The alias
        # ownership check reads it before the named-route helper is reached.
        # These are the optional/incomplete helper maps whose absence is a hold.
        for attr in ('nets','paths','owners','terminals','auxiliary','semantic_input_resolutions'):
            c=self.trial(); delattr(c,attr)
            with self.subTest(attr=attr): self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_conflicting_coordinate_forms_and_omitted_owner_input_fail_closed(self):
        c=self.trial(); c.terminals['blocks/AL/pins/L/1']['geometry']['row']=999
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
        c=self.trial(); c.terminals['blocks/AL/pins/L/3']=dict(terminal_id='t3',side='input',geometry=dict(point=[72,17],row=17,column=72))
        self.assertEqual(c.terminal_candidates('AL.inputAC','target','AC'),[])
    def test_numeric_selector_keeps_ordinal_route_contradiction_guard(self):
        c=self.trial(); c.paths={'AC':[[[58,13],[72,18]]]}
        self.assertEqual(c.terminal_candidates('AL.input1','target','AC'),[])

    def test_non_matching_named_syntax_is_not_guessed(self):
        c=self.trial()
        for ref in ('AL.inputac','AL.inputAAA','ZZ.inputAC'):
            with self.subTest(ref=ref):self.assertEqual(c.terminal_candidates(ref,'target','AC'),[])

if __name__=='__main__':unittest.main()
