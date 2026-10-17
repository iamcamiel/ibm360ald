"""Side-scoped terminal parsing without source or electrical-net changes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import build_card_data as B

class NetPortResolution(unittest.TestCase):
    def node(self, pins, name="AA"):
        return {"id": name, "pins": deepcopy(pins)}

    def port(self, pin, reference, side="output", **extra):
        return {"pin": pin, "reference": reference, "side": side, "row": 12, "triangle": False, **extra}

    def test_exact_dotted_reference_distinguishes_numbered_outputs(self):
        n=self.node([self.port("D06","AA.D06.26"),self.port("B08","AA.KB08.27",printed_pin="KB08",border_control="K",triangle=True)])
        before=deepcopy(n)
        self.assertEqual(B.resolve_net_port(n,"AA.D06.26","output")["physical_contact"],"D06")
        for ref in ["AA.KB08.27","AA.B08.27"]:
            result=B.resolve_net_port(n,ref,"output")
            self.assertEqual(result["physical_contact"],"B08")
            self.assertTrue(result["raw_port"]["triangle"])
            self.assertEqual(result["raw_port"]["border_control"],"K")
        self.assertEqual(n,before)

    def test_generic_alias_selects_actual_port_among_multiple_outputs(self):
        n=self.node([self.port("B04✲","AA.out",triangle=True),self.port("D04T","AA.other")])
        result=B.resolve_net_port(n,"AA.out","output")
        self.assertEqual((result["status"],result["physical_contact"],result["effective_label"]),("numbered","B04","B04✲"))

    def test_explicit_border_qualifier_generates_only_this_ports_K_alias(self):
        n=self.node([self.port("B03","AA.KB03.27",printed_pin="KB03",border_marker=None,border_qualifier="K"),
                     self.port("D10","AA.other")])
        result=B.resolve_net_port(n,"AA.B03.27","output")
        self.assertEqual(result["physical_contact"],"B03")
        self.assertEqual(result["raw_port"]["border_qualifier"],"K")
        self.assertEqual(B.resolve_net_port(n,"AA.KD10.27","output")["status"],"unresolved")

    def test_terminal_id_and_shared_side_specific_reference(self):
        n=self.node([{"pin":"D06","terminal_id":"AA.shared","side":"input","row":3},
                     {"pin":"D06","terminal_id":"AA.shared","side":"output","row":4}])
        self.assertEqual(B.resolve_net_port(n,"AA.shared","input")["port_index"],0)
        self.assertEqual(B.resolve_net_port(n,"AA.shared","output")["port_index"],1)

    def test_control_and_decoration_fields_are_preserved(self):
        n=self.node([self.port("4D11T","AA.out",printed_pin="4D11T",numeric_control_prefix="4",border_marker="K",triangle=True)])
        result=B.resolve_net_port(n,"AA.out","output")
        self.assertEqual(result["physical_contact"],"D11")
        self.assertEqual(result["raw_port"],n["pins"][0])

    def test_repeated_contact_ports_do_not_coalesce(self):
        n=self.node([self.port("B08","AA.upper",row=10),self.port("B08","AA.lower",row=11)])
        self.assertEqual(B.resolve_net_port(n,"AA.upper","output")["port_index"],0)
        self.assertEqual(B.resolve_net_port(n,"AA.lower","output")["port_index"],1)
        self.assertEqual(B.resolve_net_port(n,"AA.B08","output")["status"],"unresolved")

    def test_unknown_alias_never_uses_unique_physical_output(self):
        n=self.node([self.port("D10","AA.known")])
        self.assertEqual(B.resolve_net_port(n,"AA.missing","output")["status"],"unresolved")

    def test_generic_multiple_local_outputs_is_ambiguous(self):
        n=self.node([self.port("D10","AA.first"),self.port("B03","AA.second")])
        self.assertEqual(B.resolve_net_port(n,"AA.output","output")["status"],"unresolved")

    def test_unknown_index_suffix_is_not_an_array_index_guess(self):
        n=self.node([self.port("D10","AA.known")])
        self.assertEqual(B.resolve_net_port(n,"AA.o0","output")["status"],"unresolved")

    def test_true_pinless_and_unreadable_labels_are_distinct(self):
        n=self.node([self.port(None,"AA.internal"),self.port("�08","AA.damaged")])
        self.assertEqual(B.resolve_net_port(n,"AA.internal","output")["status"],"pinless")
        self.assertEqual(B.resolve_net_port(n,"AA.damaged","output")["status"],"unresolved")

    def test_conflicting_physical_mirror_fails_closed(self):
        n=self.node([self.port("B08","AA.out",physical_pin="D08")])
        self.assertEqual(B.resolve_net_port(n,"AA.out","output")["status"],"unresolved")

    def test_duplicate_alias_and_foreign_node_fail_closed(self):
        n=self.node([self.port("B08","AA.duplicate"),self.port("D10","AA.duplicate")])
        self.assertEqual(B.resolve_net_port(n,"AA.duplicate","output")["status"],"unresolved")
        self.assertEqual(B.resolve_net_port(n,"AB.duplicate","output")["status"],"unresolved")

    def test_missing_physical_label_with_numbered_mirror_is_not_pinless(self):
        n=self.node([self.port(None,"AA.out",printed_pin="B08")])
        self.assertEqual(B.resolve_net_port(n,"AA.out","output")["status"],"unresolved")

    def test_numbered_output_to_genuine_middle_pinless_input(self):
        # AP793's actual terminal-ID pattern:4055H1 B10 feeds the middle
        # unlabelled4055A4 input, not its adjacent B12 or D04 input.
        a=self.node([{"pin":"B10","printed_pin":"B10","side":"output","row":3,
                      "triangle":True,"border_marker":"◺","terminal_id":"1C.output1"}],"1C")
        b=self.node([{"pin":pin,"side":"input","row":row,"triangle":False,"terminal_id":ref}
                     for pin,row,ref in [("B12",1,"2D.input1"),(None,3,"2D.input2"),("D04",5,"2D.input3")]],"2D")
        observations=[{"page":"AP793","node":n["id"],"portion":portion,"circuit_identifier":"U03AF",
                       "function_label":"N","_instance":("02B-C2","L6"),"pins":deepcopy(n["pins"])}
                      for n,portion in [(a,"H1"),(b,"A4")]]
        raw={"nodes":[a,b],"nets":[{"id":"1C.output1","driver":"1C.output1","targets":["2D.input2"]}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/"tmp")as td,patch.object(B,"ROOT",Path(td)):
            result,_=B.derive_semantics("4055",{"listing_portions":["H1","A4"]},observations,{"AP793":raw},B.SINGLE_POWER,[])
        edge=result["edges"][0]
        self.assertEqual((edge["source"],edge["target"],edge["output_ref"],edge["input_ref"]),("H1","A4","B10","PINLESS"))
        self.assertEqual(result["source_net_endpoint_resolutions"][0]["terminals"][0]["raw_port"],b["pins"][1])

    def derive(self, nets, cross_card=False):
        a=self.node([self.port("D06","AA.D06.26"),self.port("B08","AA.KB08.27",printed_pin="KB08",border_control="K",triangle=True)])
        b=self.node([self.port("D04","AB.D04.26","input")],"AB")
        observations=[{"page":"XX001","node":n["id"],"portion":portion,"circuit_identifier":"U03AF","function_label":"N",
                       "_instance":("02A-A1",site),"pins":deepcopy(n["pins"])}
                      for n,portion,site in [(a,"A1","J6"),(b,"B1","J7"if cross_card else"J6")]]
        raw={"nodes":[a,b],"nets":deepcopy(nets)};before=deepcopy(raw);uncertainties=[]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/"tmp")as td,patch.object(B,"ROOT",Path(td)):
            result,_=B.derive_semantics("1234",{"listing_portions":["A1","B1"]},observations,{"XX001":raw},B.SINGLE_POWER,uncertainties)
        self.assertEqual(raw,before)
        return result

    def test_existing_separate_net_membership_is_not_rewritten(self):
        nets=[{"id":"positive","driver":"AA.D06.26","targets":["AB.D04.26"]},
              {"id":"negative","driver":"AA.KB08.27","targets":[]}]
        model=self.derive(nets)
        self.assertEqual([x["net_id"]for x in model["source_net_endpoint_resolutions"]],["positive","negative"])
        self.assertEqual(model["edges"],[])  # Distinct contacts retain the installation-strap policy.
        self.assertFalse(any(p["pin"]is None for p in model["portions"]["A1"]["_outputs"]))

    def test_evidenced_shared_net_retains_both_numbered_output_ports(self):
        model=self.derive([{"id":"shared","driver":"AA.D06.26","route_owners":["AA.KB08.27"],
                            "declared_physical_output_drivers":["AA.D06.26","AA.KB08.27"],"targets":["AB.D04.26"]}])
        record=model["source_net_endpoint_resolutions"][0]
        outputs=[x for x in record["terminals"]if x["side"]=="output"]
        self.assertEqual({x["physical_contact"]for x in outputs},{"D06","B08"})
        self.assertEqual(len({x["port_index"]for x in outputs}),2)
        self.assertEqual(record["route_owners"],["AA.KB08.27"])
        self.assertEqual(model["edges"],[])  # Parsing does not authorize net assembly/straps.

    def test_cross_card_installation_wiring_is_not_card_internal(self):
        model=self.derive([{"driver":"AA.D06.26","targets":["AB.D04.26"]}],cross_card=True)
        self.assertFalse(model["edges"])

if __name__=="__main__":unittest.main()
