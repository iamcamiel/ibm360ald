"""A source-only annotation review must not masquerade as reviewed geometry."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(1,'D:/Github/IBM360/ibm360ald/tools/card_ald')
import build_card_data as B

class SourceOnlyControls(unittest.TestCase):
    def test_validated_control_proof_survives_a_fresh_generic_definition(self):
        proof={'page':'XX001','node':'AA','terminal_id':'nodes:0/t:0','literal':'L',
            'role':'anonymous-input-wire-annotation','model_binding':{'path':'json/XX.json','sha256':'a'*64}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);overlay=root/'source.json';overlay.write_text(json.dumps({
                'schema':'reviewed-card-build-overrides-v1','card_type':'1234','source_bindings':[],
                'reviewed_pinless_controls':[proof]}))
            loaded=({'_reviewed_pinless_controls':[proof]},[],{},B.SINGLE_POWER,[],[],[])
            with patch.object(B,'ROOT',root),patch.object(B,'load_evidence',return_value=loaded),\
                 patch.object(B,'derive_semantics',return_value=({},root/'absent-manual.json')),\
                 patch.object(B,'generic_definition',return_value={'card_type':'1234'}) as generic,\
                 patch.object(B,'reviewed_definition') as reviewed,patch.object(B.generate_card,'validate',return_value={}):
                definition,report=B._build('1234',overlay)
            generic.assert_called_once();reviewed.assert_not_called()
            self.assertEqual(definition['reviewed_pinless_controls'],[proof])
            self.assertTrue(report['reviewed_supplement_used'])

    def test_unvalidated_control_does_not_become_a_definition_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);overlay=root/'source.json';overlay.write_text(json.dumps({
                'schema':'reviewed-card-build-overrides-v1','card_type':'1234','source_bindings':[],
                'reviewed_pinless_controls':[{'literal':'L'}]}))
            with patch.object(B,'ROOT',root),patch.object(B,'load_evidence',return_value=({},[],{},B.SINGLE_POWER,[],[],[])),\
                 patch.object(B,'derive_semantics',return_value=({},root/'absent-manual.json')),\
                 patch.object(B,'generic_definition',return_value={'card_type':'1234'}),\
                 patch.object(B.generate_card,'validate',return_value={}):definition,report=B._build('1234',overlay)
            self.assertNotIn('reviewed_pinless_controls',definition)

    def test_stale_reviewed_supplement_never_falls_back_to_a_generic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);overlay=root/'source.json';overlay.write_text(json.dumps({
                'schema':'reviewed-card-build-overrides-v1','card_type':'1234',
                'source_bindings':[{'path':'json/current.json','sha256':'a'*64}]}))
            with patch.object(B,'ROOT',root),patch.object(B,'verify_binding',return_value={'current':False}),\
                 patch.object(B,'load_evidence')as evidence,patch.object(B,'generic_definition')as generic:
                with self.assertRaisesRegex(ValueError,'refusing generic replacement'):B._build('1234',overlay)
            evidence.assert_not_called();generic.assert_not_called()

    def test_incomplete_geometry_is_rejected_as_geometry_not_treated_as_source_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);overlay=root/'source.json';overlay.write_text(json.dumps({
                'schema':'reviewed-card-build-overrides-v1','card_type':'1234','source_bindings':[],'layout':{}}))
            with patch.object(B,'ROOT',root),self.assertRaises(ValueError):B._build('1234',overlay)

if __name__=='__main__':unittest.main()
