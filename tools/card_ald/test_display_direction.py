from copy import deepcopy
import unittest
from display_direction import exterior_display_side as side
from card_source import logical_gate_terminal

def k(**changes):
 d={'side':'output','pin':'B11','contact_role':'nonlogical_common','border_control':'K'};d.update(changes);return d

class DisplayDirection(unittest.TestCase):
 def test_single_right_k_is_output_without_logic_driver(self):
  p=k();before=deepcopy(p);self.assertEqual(side([p],'B11'),'output');self.assertFalse(logical_gate_terminal(p));self.assertEqual(p,before)
 def test_left_k_remains_input(self):self.assertEqual(side([k(side='input')],'B11'),'input')
 def test_shared_k_with_input_remains_input(self):self.assertEqual(side([k(),{'side':'input','pin':'B11'}],'B11'),'input')
 def test_shared_two_k_ports_remain_input(self):self.assertEqual(side([k(),k()],'B11'),'input')
 def test_pinless_peer_prevents_isolated_classification(self):self.assertEqual(side([k(),{'side':'input','pin':None}],'B11'),'input')
 def test_genuine_peer_driver_makes_output(self):self.assertEqual(side([k(),{'side':'output','pin':'B11'}],'B11'),'output')
 def test_ordinary_output_retained(self):self.assertEqual(side([{'side':'output','pin':'B11'}],'B11'),'output')
 def test_ordinary_input_retained(self):self.assertEqual(side([{'side':'input','pin':'B11'}],'B11'),'input')
 def test_wrong_physical_contact_is_not_promoted(self):self.assertEqual(side([k()],'D06'),'input')
 def test_missing_exterior_identity_is_not_promoted(self):self.assertEqual(side([k()]),'input')
 def test_invalid_pin_is_not_promoted(self):self.assertEqual(side([k(pin='E11')],'E11'),'input')
 def test_missing_explicit_k_is_rejected(self):
  p=k();del p['border_control']
  with self.assertRaises(ValueError):side([p],'B11')
 def test_contradictory_role_is_rejected(self):
  with self.assertRaises(ValueError):side([k(contact_role='logical')],'B11')
 def test_missing_side_is_rejected(self):
  with self.assertRaises(ValueError):side([{'pin':'B11'}],'B11')
 def test_empty_net_is_input(self):self.assertEqual(side([],'B11'),'input')
 def test_ar_input_only_projection_is_unchanged(self):
  from card_source import ar_input_only_aliases,logical_terminal_items
  n={'function':'AR','pins':[{'side':'input','pin':'B11'},{'side':'output','pin':'B11'}]};before=deepcopy(n)
  self.assertEqual(ar_input_only_aliases(n),{1:'B11'});self.assertEqual(side([p for _,p in logical_terminal_items(n)],'B11'),'input');self.assertEqual(n,before)
if __name__=='__main__':unittest.main()
