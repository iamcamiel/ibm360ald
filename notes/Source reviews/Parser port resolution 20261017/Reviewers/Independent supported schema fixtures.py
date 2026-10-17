"""Independent legacy-schema counterexamples; no source changes."""
import unittest
import build_card_data as B
class SupportedSchema(unittest.TestCase):
 def test_exact_terminal_id_precedes_generated_printed_pin_alias(self):
  n={"id":"AY","pins":[{"pin":"D09","reference":"AY.D09","printed_pin":"D09","side":"input","row":47},{"pin":"TIE","reference":"AY.TIE","printed_pin":"D09","side":"input","row":47}]}
  x=B.resolve_net_port(n,"AY.D09","input");self.assertEqual((x["status"],x["port_index"],x["physical_contact"]),("numbered",0,"D09"))
 def test_key_alias_is_explicit_identity(self):
  n={"id":"BJ","pins":[{"pin":None,"key":"out3","side":"output","row":68}]}
  x=B.resolve_net_port(n,"BJ.out3","output");self.assertEqual((x["status"],x["port_index"]),("pinless",0))
 def test_blank_and_OUT_are_not_unreadable_contacts(self):
  for label in ["","OUT"]:
   n={"id":"AA","pins":[{"pin":label,"printed_label":"","reference":"AA.actual","side":"output","row":3}]}
   self.assertEqual(B.resolve_net_port(n,"AA.actual","output")["status"],"pinless")
 def test_explicit_K_physical_pin_preserved(self):
  n={"id":"AR","pins":[{"pin":"KB08","marker":"K","physical_pin":"B08","reference":"AR.KB08","side":"output","row":56}]}
  x=B.resolve_net_port(n,"AR.KB08","output");self.assertEqual((x["status"],x["physical_contact"]),("numbered","B08"));self.assertEqual(x["raw_port"],n["pins"][0])
 def test_semantic_pin_alias_uses_explicit_physical_printed_contact(self):
  n={"id":"AU","pins":[{"pin":"E_OUT","printed_pin":"B07✲","reference":"AU.E_OUT","side":"output","row":33}]}
  x=B.resolve_net_port(n,"AU.E_OUT","output");self.assertEqual((x["status"],x["physical_contact"]),("numbered","B07"))
 def test_physical_row_label_must_bind_the_exact_row(self):
  n={"id":"AA","pins":[{"pin":"B08","side":"output","row":69},{"pin":"B08","side":"output","row":70}]}
  x=B.resolve_net_port(n,"AA.B08@69","output");self.assertEqual((x["status"],x["port_index"]),("numbered",0));self.assertEqual(B.resolve_net_port(n,"AA.B08@68","output")["status"],"unresolved")
 def test_row_output_identifier_binds_exact_local_side(self):
  n={"id":"AB","pins":[{"pin":"D07","side":"input","row":54},{"pin":None,"side":"output","row":54}]}
  x=B.resolve_net_port(n,"AB.output@54","output");self.assertEqual((x["status"],x["port_index"]),("pinless",1))
 def test_current_contact_conflict_must_remain_unresolved(self):
  n={"id":"AA","pins":[{"pin":"B08","printed_pin":"D08","reference":"AA.out","side":"output","row":3}]}
  self.assertEqual(B.resolve_net_port(n,"AA.out","output")["status"],"unresolved")
 def test_repeated_explicit_alias_stays_ambiguous(self):
  n={"id":"AA","pins":[{"pin":"B08","reference":"AA.out","side":"output","row":3},{"pin":"D08","reference":"AA.out","side":"output","row":4}]}
  self.assertEqual(B.resolve_net_port(n,"AA.out","output")["status"],"unresolved")
 def test_generic_numeric_index_not_inferred(self):
  n={"id":"AA","pins":[{"pin":None,"side":"input","row":66},{"pin":None,"side":"input","row":67}]}
  self.assertEqual(B.resolve_net_port(n,"AA.input1","input")["status"],"unresolved")
