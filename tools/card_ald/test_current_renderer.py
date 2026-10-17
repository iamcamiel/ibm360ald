"""Explicit display authority must not invent supplies or move variants."""
from copy import deepcopy
import unittest
import generate_card as M


def header_spec():
    return {'header':{'schema':'card-ald-header-v1','part_number':'5809999',
            'card_width':'SINGLE CARD','reviewed_occurrences':1,'reviewed_pages':1,'provisional_forms':[]},
        'canvas':{'width':160,'header_rows':7},'boxes':[{'portion':'A1','circuit_identifier':'U03AA','x':12,'top':10}],
        'exterior_pins':[],'power_contacts':{'D08':'GROUND','D03':'+3V','B06':'-3V','B11':'+6V'}}


class CurrentRendererTests(unittest.TestCase):
    def test_unknown_supplies_are_explicit_and_do_not_claim_unused_contacts(self):
        spec=header_spec();spec['power_contacts']={}
        spec['component_power_authority']={'role':'not_established'}
        spec['header']['symbol_standard']='PRINTED ALD FORMS'
        lines=M.header_lines(spec)
        self.assertEqual(lines[2],'POWER: NOT ESTABLISHED')
        self.assertEqual(lines[3],'UNCONNECTED SIGNAL CONTACTS: NOT ESTABLISHED')
        self.assertEqual(lines[5],'SYMBOLS: PRINTED ALD FORMS')
        spec['power_contacts']['D03']='+3V'
        with self.assertRaises(AssertionError):M.header_lines(spec)

    def test_partial_special_supplies_do_not_inherit_ordinary_rail_assumptions(self):
        spec=header_spec();spec['power_contacts']={'D08':'GROUND'}
        spec['component_power_authority']={'role':'reviewed_special','contact_set_complete':False}
        lines=M.header_lines(spec)
        self.assertEqual(lines[2],'POWER: GROUND D08')
        self.assertEqual(lines[3],'UNCONNECTED SIGNAL CONTACTS: NOT ESTABLISHED')
        spec.pop('component_power_authority')
        with self.assertRaises(AssertionError):M.header_lines(spec)

    def test_caption_location_is_common_and_cannot_override_geometry(self):
        spec=header_spec();spec['box_captions']=[{'portion':'A1','text':'SENSE AMP'}]
        self.assertEqual(M.caption_locations(spec),[(12,9,'SENSE AMP')])
        spec['box_captions'][0]['x']=20
        with self.assertRaises(AssertionError):M.caption_locations(spec)

    def test_reserved_contacts_are_not_claimed_as_documented_card_supplies(self):
        spec=header_spec()
        spec['component_power_authority']={'role':'reviewed_special',
            'source_contact_role':'reserved_system_contact_positions'}
        self.assertTrue(M.header_lines(spec)[2].startswith('RESERVED SYSTEM CONTACTS: '))
        spec['power_contacts']={}
        self.assertEqual(M.header_lines(spec)[2],'RESERVED SYSTEM CONTACTS: NOT ESTABLISHED')

    def test_caption_cannot_overwrite_shared_heading(self):
        spec=header_spec();spec['boxes'][0]['top']=7
        spec['box_captions']=[{'portion':'A1','text':'SENSE AMP'}]
        with self.assertRaises(AssertionError):M.caption_locations(spec)


if __name__=='__main__':unittest.main()
