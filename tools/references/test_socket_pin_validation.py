"""Small source-free regressions for physical contact validation."""
import copy
import unittest

from socket_pin_validation import audit_node_pins, parse_pin_literal


def node(*pins, function="A", portion="A1", card_type="3308"):
    return dict(card_type=card_type, portion=portion, function=function, pins=list(pins))


def pin(literal, side="input", **extra):
    return dict(pin=literal, side=side, **extra)


def definition(function="A", ports=None):
    return dict(card_type="3308", power_contacts={"D08": "GROUND"}, boxes=[dict(
        portion="A1", function=function, ports=ports or [dict(side="input", pin="D04"), dict(side="output", pin="B03")])])


class PinValidationTests(unittest.TestCase):
    def check(self, source, kind="SINGLE CARD", spec=None):
        before = copy.deepcopy(source)
        result = audit_node_pins(source, kind, spec)
        self.assertEqual(source, before, "read-only contract")
        return result

    def test_known_widths_and_ranges(self):
        for kind, literal, status in [("SINGLE CARD", "B02", "valid"), ("DOUBLE CARD", "J13", "valid"),
                                      ("SINGLE CARD", "G02", "invalid_letter"), ("DOUBLE CARD", "U12", "invalid_letter"),
                                      ("SINGLE CARD", "D00", "invalid_number"), ("DOUBLE CARD", "D14", "invalid_number")]:
            with self.subTest(kind=kind, literal=literal):
                self.assertEqual(self.check(node(pin(literal)), kind)[0]["status"], status)

    def test_qualifiers_preserved(self):
        for literal, expected in [("2J09", "J09"), ("LB09", "B09"), ("TB02", "B02"),
                                  ("D04T", "D04"), ("B04✲T", "B04"), ("6B08", "B08"), ("B08*", "B08")]:
            with self.subTest(literal=literal):
                result = self.check(node(pin(literal)), "DOUBLE CARD")[0]
                self.assertEqual(result["physical_contact"], expected)
                self.assertEqual(result["literals"]["pin"], literal)
                self.assertEqual(result["severity"], "info")

    def test_explicit_numeric_suffix_only(self):
        result = self.check(node(pin("B122", physical_pin="B12", printed_numeric_suffix="2")))[0]
        self.assertEqual(result["physical_contact"], "B12")
        self.assertEqual(result["severity"], "info")
        self.assertEqual(self.check(node(pin("B122")))[0]["status"], "malformed_pin")

    def test_alias_and_control_and_pinless(self):
        result = self.check(node(pin("OUT", "output", printed_pin="D06"), pin("2"), pin("L"), pin(None), pin("")))
        self.assertEqual(result[0]["physical_contact"], "D06")
        self.assertEqual([item["status"] for item in result[1:]], ["control", "control", "pinless", "pinless"])

    def test_unknown_and_non_slt_never_assumed(self):
        for kind in [None, "CONNECTOR", "CABLE", {"3308": {"single", "double"}}]:
            self.assertEqual(self.check(node(pin("U12")), kind)[0]["status"], "unknown_kind")
        self.assertEqual(self.check(node(pin("B02")), {"3308": "single_card"})[0]["status"], "valid")

    def test_conflict_including_invalid_letter_not_first_valid(self):
        for mirrors in [dict(physical_pin="D05", printed_pin="D09"), dict(physical_pin="D05", printed_pin="U05")]:
            result = self.check(node(pin("D05", **mirrors)))[0]
            self.assertEqual(result["status"], "mirror_conflict")
            self.assertIsNone(result["physical_contact"])

    def test_unreadable_remains_review(self):
        result = self.check(node(pin("D0�", printed_pin="D0�")))[0]
        self.assertEqual(result["status"], "unreadable_pin")
        self.assertEqual(result["severity"], "review")

    def test_nested_prefix_does_not_hide_invalid_bank(self):
        result = self.check(node(pin("2LC04", physical_pin="LC04")))[0]
        self.assertEqual(result["physical_contact"], "C04")
        self.assertEqual(result["status"], "invalid_letter")

    def test_definition_contact_side_and_unused_omission(self):
        result = self.check(node(pin("D04")), spec=definition())
        self.assertEqual(result[0]["status"], "definition_match")
        self.assertEqual(self.check(node(pin("B03")), spec=definition())[0]["status"], "definition_discrepancy")
        self.assertEqual(self.check(node(pin("B05")), spec=definition())[0]["status"], "definition_discrepancy")
        self.assertEqual(self.check(node(pin("D04"), portion="J1"), spec=definition())[0]["status"], "definition_portion_unknown")

    def test_supply_contacts_not_false_signal_errors(self):
        for literal, side in [("8D03", "input"), ("D08", "input"), ("D08", "output")]:
            result = self.check(node(pin(literal, side)), spec=definition())[0]
            self.assertEqual(result["status"], "supply_contact")
            self.assertEqual(result["severity"], "info")
        self.assertEqual(self.check(node(pin("J08")), spec=definition())[0]["status"], "invalid_letter")

    def test_ar_passthrough_repeated_contacts(self):
        spec = definition("AR", [dict(side="input", pin="D04"), dict(side="output", pin="B03")])
        result = self.check(node(pin("D04"), pin("D04", "output"), pin("D04"), function="AR T"), spec=spec)
        self.assertEqual(result[1]["status"], "shared_contact_passthrough")
        self.assertTrue(any(issue["status"] == "repeated_same_contact" for issue in result[2]["issues"]))
        self.assertTrue(all(item["severity"] == "info" for item in result))
        self.assertEqual(self.check(node(pin("D04"), pin("D04", "output")), spec=definition())[1]["status"], "definition_discrepancy")

    def test_malformed_object_and_passive_direction(self):
        self.assertEqual(self.check(node("B08"))[0]["status"], "malformed_pin_object")
        self.assertEqual(self.check(node(pin("D04", "passive")), spec=definition())[0]["status"], "direction_unknown")

    def test_wrong_definition_cannot_imply_contact_coverage(self):
        spec = definition()
        spec["card_type"] = "9999"
        for literal in ["D04", "D08", None]:
            self.assertEqual(self.check(node(pin(literal)), spec=spec)[0]["status"], "definition_card_mismatch")


if __name__ == "__main__":
    unittest.main()
