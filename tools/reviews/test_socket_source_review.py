from copy import deepcopy
import unittest
import source_review as S
class SocketTables(unittest.TestCase):
 def test_table_records_are_explicitly_declared(self):
  d={'records':[{'part_number':'5601125'}]};S.declared_model(d,'ald-socket-listing-table-v1')
  self.assertEqual(S.patch_model(d,[{'pointer':'/records/0/part_number','before':'5601125','after':'5801125'}]),{'records':[{'part_number':'5801125'}]})
  self.assertEqual(d,{'records':[{'part_number':'5601125'}]})
 def test_table_does_not_pass_as_nodes_ald(self):
  with self.assertRaises(ValueError):S.declared_model({'records':[]},'ald-page-nodes-v1')
 def test_synthetic_nodes_do_not_turn_an_ald_into_a_socket_table(self):
  with self.assertRaises(ValueError):S.declared_model({'nodes':[],'records':[]},'ald-socket-listing-table-v1')
 def test_invalid_record_container_is_rejected(self):
  with self.assertRaises(ValueError):S.declared_model({'records':['UNKNOWN']},'ald-socket-listing-table-v1')
 def test_exact_preimage_guard_applies_to_tables(self):
  with self.assertRaisesRegex(ValueError,'preimage'):S.patch_model({'records':[{'part_number':'5801125'}]},[{'pointer':'/records/0/part_number','before':'5601125','after':'5801125'}])
if __name__=='__main__':unittest.main()
