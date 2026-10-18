"""Source authority and portable documentary records remain separate."""
from pathlib import Path
from copy import deepcopy
import json,unittest
import card_source as S
import test_occurrence_net_role as fixtures

class DocumentaryContext(unittest.TestCase):
    setUp=fixtures.OccurrenceRole.setUp
    tearDown=fixtures.OccurrenceRole.tearDown
    cert=fixtures.OccurrenceRole.cert
    def owned(self):
        p=fixtures.raw();p['_occurrence_net_role']=self.cert(p);return p
    def test_documentary_projection_preserves_runtime_proof_and_role(self):
        p=self.owned();before=deepcopy(p);record=S.documentary_occurrence_net_role(p)
        self.assertEqual(p,before);self.assertEqual(S.intrinsic_contact_role(p),'logical')
        self.assertEqual(record['schema'],'documentary-passive-component-net-origin-v1')
        self.assertFalse(record['runtime_authority']);self.assertNotIn('context_seal',record)
        self.assertEqual(record['source_checkpoint']['path'],'notes/Source status.json')
        manual=record['component_capability']['manual_evidence'][0]
        self.assertEqual(manual['document'],'registered manual.pdf');self.assertNotIn('path',manual)
        self.assertEqual(manual['pdf_pages_1based'],[1]);self.assertNotIn(str(self.root),json.dumps(record))
    def test_serialized_documentary_record_cannot_grant_runtime_authority(self):
        p=self.owned();record=S.documentary_occurrence_net_role(p);foreign=fixtures.raw();foreign['_occurrence_net_role']=record
        self.assertIsNone(S.occurrence_net_role(foreign));self.assertEqual(S.intrinsic_contact_role(foreign),'nonlogical_common')
        with self.assertRaises(ValueError):S.register_occurrence_net_role(record,foreign,self.root)
    def test_same_manual_bytes_at_private_wrong_path_are_not_registered(self):
        copied=self.root.parent/(self.root.name+'-private.pdf');copied.write_bytes(self.manual.read_bytes());self.addCleanup(copied.unlink)
        proof=deepcopy(self.current_proof);proof['component_capability']['manual_evidence'][0]['path']=str(copied)
        p=fixtures.raw();p['_occurrence_net_role']=S.register_occurrence_net_role(proof,p,self.root)
        with self.assertRaisesRegex(ValueError,'exact registered source'):S.documentary_occurrence_net_role(p)
    def test_wrong_manual_hash_is_rejected_before_documentary_projection(self):
        p=self.owned();p['_occurrence_net_role']['component_capability']['manual_evidence'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Unowned or stale'):S.documentary_occurrence_net_role(p)
    def test_unregistered_manual_registry_identity_rejected(self):
        p=self.owned();registry=json.loads(self.manual_registry.read_text());registry['manual_sha256']='0'*64;self.manual_registry.write_text(json.dumps(registry))
        with self.assertRaisesRegex(ValueError,'Registered manual source is stale'):S.documentary_occurrence_net_role(p)
    def test_external_nonmanual_private_dependency_is_not_compacted(self):
        private=self.root.parent/(self.root.name+'-private.json');private.write_text('{}');self.addCleanup(private.unlink)
        proof=deepcopy(self.current_proof);proof['private_dependency']={'path':str(private),'sha256':S.digest(private)}
        p=fixtures.raw();p['_occurrence_net_role']=S.register_occurrence_net_role(proof,p,self.root)
        with self.assertRaisesRegex(ValueError,'Unregistered external dependency'):S.documentary_occurrence_net_role(p)
    def test_invalid_page_metadata_rejected(self):
        proof=deepcopy(self.current_proof);proof['component_capability']['manual_evidence'][0]['pdf_pages_1based']=[0]
        p=fixtures.raw();p['_occurrence_net_role']=S.register_occurrence_net_role(proof,p,self.root)
        with self.assertRaisesRegex(ValueError,'page metadata'):S.documentary_occurrence_net_role(p)
    def test_modified_owned_proof_fields_cannot_be_projected(self):
        for field,value in [('node','FOREIGN'),('page','ZZ002'),('circuit_identifier','S61XX'),('context_seal','0'*64)]:
            with self.subTest(field=field):
                p=self.owned();p['_occurrence_net_role'][field]=value
                with self.assertRaisesRegex(ValueError,'Unowned or stale'):S.documentary_occurrence_net_role(p)
    def test_old_checkpoint_cannot_become_documentary_evidence(self):
        p=self.owned();self.checkpoint.write_bytes(self.checkpoint.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'Unowned or stale'):S.documentary_occurrence_net_role(p)

if __name__=='__main__':unittest.main()
