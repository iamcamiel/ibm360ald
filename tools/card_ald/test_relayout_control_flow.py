"""Generic control-flow checks for requested graph relayout, no card fixtures."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

candidate=os.environ.get('CARD_BUILDER_REVIEW_CANDIDATE')
if candidate:
    spec=importlib.util.spec_from_file_location('reviewed_candidate_builder',candidate)
    B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
else:
    import build_card_data as B
import graph_card_layout


class RelayoutControlFlow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.root=Path(self.temp.name)
        self.marker={'kind':'unresolved fixture source identity','literal':'A?'}
        self.uncertainties=[deepcopy(self.marker)]
        self.model={'card_type':'1234','portions':{},'signal_pins':[]}
        self.definition={'canvas':{'width':40},'layout_validation':{'crossings':0,'routed_grid_steps':5},'fixture':'unchanged terminals'}
    def tearDown(self):self.temp.cleanup()
    def run_case(self,relayout,power=True,overlay=False,generic=None):
        if overlay:
            path=self.root/'json/Card-ALD/build-overrides/1234.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'schema':'reviewed-card-build-overrides-v1','card_type':'1234','source_bindings':[],'layout':{},'reviewed_portions':{}}))
        self.generic_calls=[]
        def route(model,*args):
            self.generic_calls.append(deepcopy(model))
            if generic:return generic(model,*args)
            return deepcopy(self.definition)
        with ExitStack() as stack:
            stack.enter_context(patch.object(B,'load_evidence',return_value=({},[],{},B.SINGLE_POWER if power else {},[],[],self.uncertainties)))
            stack.enter_context(patch.object(B,'derive_semantics',return_value=(self.model,self.root/'no-manual')))
            stack.enter_context(patch.object(B,'generic_definition',side_effect=route))
            self.reviewed=stack.enter_context(patch.object(B,'reviewed_definition',return_value=(deepcopy(self.definition),['reviewed comparison retained'])))
            stack.enter_context(patch.object(B.generate_card,'validate',return_value={'passed':True}))
            self.planner=stack.enter_context(patch.object(graph_card_layout,'plan',return_value={'bank_interval':36}))
            result=B.build('1234',root=self.root,relayout=relayout)
        return result
    def test_relayout_reaches_graph_trials_without_eager_default_route(self):
        def route(model,*args):
            if 'layout_hints' not in model:raise ValueError('legacy placement cannot route')
            return deepcopy(self.definition)
        definition,report=self.run_case(True,generic=route)
        self.assertIsNotNone(definition);self.assertEqual(self.planner.call_count,2)
        self.assertTrue(all('layout_hints'in x for x in self.generic_calls))
        self.assertEqual(report['uncertainties'],[self.marker])
        self.assertFalse(report['reviewed_supplement_used']);self.assertFalse(report['relayout']['terminal_partition_identity_verified'])
    def test_default_nonreviewed_path_still_uses_legacy_route_once(self):
        definition,report=self.run_case(False)
        self.assertEqual(definition,self.definition);self.assertEqual(len(self.generic_calls),1)
        self.assertNotIn('layout_hints',self.generic_calls[0]);self.planner.assert_not_called()
        self.assertEqual(report['uncertainties'],[self.marker])
    def test_default_reviewed_supplement_path_is_unchanged(self):
        definition,report=self.run_case(False,overlay=True)
        self.assertEqual(definition,self.definition);self.reviewed.assert_called_once()
        self.assertEqual(self.generic_calls,[]);self.planner.assert_not_called()
        self.assertTrue(report['reviewed_supplement_used'])
        self.assertEqual(report['reviewed_fact_comparisons'],['reviewed comparison retained'])
        self.assertEqual(report['uncertainties'],[self.marker])
    def test_unsupported_module_still_never_invents_routing(self):
        definition,report=self.run_case(True,power=False)
        self.assertIsNone(definition);self.planner.assert_not_called();self.assertEqual(self.generic_calls,[])
        self.assertEqual(report['uncertainties'],[self.marker,{'kind':'definition not routed for unsupported or ambiguous module kind'}])
    def test_failed_graph_trials_remain_unresolved_with_original_evidence(self):
        def fail(model,*args):raise ValueError('No orthogonal route in fixture')
        definition,report=self.run_case(True,generic=fail)
        self.assertIsNone(definition);self.assertEqual(report['uncertainties'][0],self.marker)
        self.assertEqual(report['uncertainties'][-1]['exception'],'ValueError')
        self.assertIn('No valid graph routing',report['uncertainties'][-1]['detail'])
        self.assertTrue(all(not x['success']for x in report['relayout']['routing_attempts']))
    def test_default_route_failure_is_still_recorded_without_graph_fallback(self):
        def fail(model,*args):raise ValueError('legacy default fixture failure')
        definition,report=self.run_case(False,generic=fail)
        self.assertIsNone(definition);self.planner.assert_not_called()
        self.assertEqual(report['uncertainties'],[self.marker,{'kind':'candidate definition requires review before routing','detail':'legacy default fixture failure','exception':'ValueError'}])


if __name__=='__main__':unittest.main()
