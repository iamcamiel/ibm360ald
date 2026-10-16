from copy import deepcopy
import unittest

from source_review_guards import validate_pin_edits


class PinEditGuards(unittest.TestCase):
    def model(self,pin='D09✲',physical='D09',**extra):
        port={'pin':pin,'physical_pin':physical,'side':'output',**extra}
        return {'nodes':[{'id':'CC','pins':[port]}]}
    def intent(self,field='pin',reason=None,evidence=None):
        patch={'pointer':'/nodes/0/pins/0/'+field}
        if reason is not None:patch['annotation_drop_reason']=reason
        return {'json_patches':[patch],'evidence':evidence or []}
    def kinds(self,a,b,intent=None):return {x['kind'] for x in validate_pin_edits(a,b,intent or self.intent())}
    def test_detects_number_correction_that_loses_annotation_and_stales_mirror(self):
        self.assertEqual(self.kinds(self.model(),self.model('D05','D09')),
                         {'printed_pin_annotation_removed_without_explicit_evidence','new_stale_physical_contact_mirror'})
    def test_retaining_star_and_refreshing_bare_contact_passes(self):
        self.assertFalse(self.kinds(self.model(),self.model('D05✲','D05')))
    def test_explicit_annotation_drop_reason_with_evidence_passes(self):
        intent=self.intent(reason='Native crop shows no printed star.',evidence=[{'path':'crop.png','sha256':'bound-by-caller'}])
        self.assertFalse(self.kinds(self.model(),self.model('D05','D05'),intent))
    def test_reason_requires_page_evidence(self):
        self.assertIn('printed_pin_annotation_removed_without_explicit_evidence',
                      self.kinds(self.model(),self.model('D09','D09'),self.intent(reason='Native mark absent.')))
    def test_reason_on_other_field_is_not_authority(self):
        intent=self.intent(field='physical_pin',reason='Native crop.',evidence=[{'path':'crop.png'}])
        self.assertIn('printed_pin_annotation_removed_without_explicit_evidence',self.kinds(self.model(),self.model('D09','D09'),intent))
    def test_unrelated_preexisting_mismatch_is_preserved(self):
        old=self.model('D05','D09');new=deepcopy(old);new['nodes'][0]['function']='N'
        self.assertFalse(self.kinds(old,new))
    def test_same_pin_unrelated_decoration_preserves_preexisting_mismatch(self):
        old=self.model('D05','D09',triangle=False);new=deepcopy(old);new['nodes'][0]['pins'][0]['triangle']=True
        self.assertFalse(self.kinds(old,new))
    def test_added_annotation_does_not_resurrect_old_contact_mismatch(self):
        self.assertFalse(self.kinds(self.model('D05','D09'),self.model('D05✲','D09')))
    def test_ascii_star_to_open_asterisk_is_preservation(self):
        self.assertFalse(self.kinds(self.model('D09*','D09'),self.model('D09✲','D09')))
    def test_changed_printed_pin_mirror_cannot_drop_annotation(self):
        old=self.model('D09','D09',printed_pin='D09✲');new=self.model('D05','D05',printed_pin='D05')
        self.assertIn('printed_pin_annotation_removed_without_explicit_evidence',self.kinds(old,new))
    def test_invalid_unreadable_pin_not_guessed(self):
        self.assertFalse(self.kinds(self.model('D0�','D09'),self.model('D0�','D05')))
    def test_physical_contact_mirror_must_stay_bare(self):
        self.assertIn('physical_contact_mirror_has_printed_annotation',self.kinds(self.model(),self.model('D05✲','D05✲')))
    def test_numeric_and_T_annotations_do_not_change_physical_contact(self):
        self.assertFalse(self.kinds(self.model('8D09✲T','D09'),self.model('8D05✲T','D05')))
    def test_preexisting_error_on_other_pin_does_not_block_fix(self):
        old=self.model();old['nodes'][0]['pins'].append({'pin':'B05','physical_pin':'D09'})
        new=deepcopy(old);new['nodes'][0]['pins'][0].update(pin='D05✲',physical_pin='D05')
        self.assertFalse(self.kinds(old,new))


if __name__=='__main__':unittest.main()
