"""Logical output occurrences sharing a physical contact must not be collapsed."""
from collections import defaultdict
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import convert_ald_json as C
from ald_render import wire_graph


class RepeatedOutputTests(unittest.TestCase):
    def trial(self,merged=False):
        c=object.__new__(C.Converter);c.pid='AP161';c.auxiliary=set();c.object_ids={'AV':'AV'};c.owners={'AV':{}}
        c.primary_aliases={};c.aliases={'AV.J04':['blocks/AV/pins/R/2','blocks/AV/pins/R/4']}
        c.terminals={f'blocks/AV/pins/R/{line}':{'side':'output','pin_number':'J04',
            'geometry':{'point':[154,row],'row':row},'source_literals':{'printed_label':label}}
            for line,row,label in [(2,31,'J04✲'),(4,33,'J04')]}
        c.paths={'upper':[[[154,31],[242,31]]],'lower':[[[154,33],[154,47],[242,47]]]}
        if merged:c.paths={'physical':c.paths['upper']+c.paths['lower']}
        c.graphs={key:wire_graph(value)for key,value in c.paths.items()}
        c.nets={key:{'literal_id':key,'source_literals':{'id':key,'driver':'AV.J04','targets':[]}}for key in c.paths}
        c.logical_output_partitions=[];c.nodes=defaultdict(list);c.membership={};c.e={};c.names={};c.input_nodes={};c.no_source=set();c.allow_partial=False
        return c

    def test_distinct_net_routes_select_distinct_occurrences_without_changing_pin(self):
        c=self.trial();before=copy.deepcopy(c.terminals)
        c.memberships()
        self.assertEqual(c.names,{'upper':'AP161AV2','lower':'AP161AV4'})
        self.assertEqual(c.nodes['upper'],['blocks/AV/pins/R/2'])
        self.assertEqual(c.nodes['lower'],['blocks/AV/pins/R/4'])
        self.assertEqual(c.terminals,before)

    def test_legacy_physical_group_splits_only_disjoint_logical_route_components(self):
        c=self.trial(merged=True);old_graph=copy.deepcopy(c.graphs['physical']);old_pins=copy.deepcopy(c.terminals)
        c.partition_repeated_outputs();c.memberships()
        self.assertEqual(set(c.names.values()),{'AP161AV2','AP161AV4'})
        self.assertEqual(len(c.nets),2)
        combined=wire_graph([p for paths in c.paths.values()for p in paths])
        self.assertEqual(combined,old_graph)
        self.assertEqual(c.terminals,old_pins)
        self.assertEqual(c.logical_output_partitions[0]['source net ID'],'physical')

    def test_shared_contact_is_not_a_default_occurrence_or_net_union(self):
        c=self.trial()
        with self.assertRaises(C.ConversionError):c.resolve('AV.J04','driver')
        with self.assertRaises(C.ConversionError):c.resolve('AV.J04','driver','missing')
        c.graphs['both']=wire_graph(c.paths['upper']+c.paths['lower'])
        with self.assertRaises(C.ConversionError):c.resolve('AV.J04','driver','both')

    def test_partition_targets_stay_with_their_existing_route_component(self):
        c=self.trial(merged=True)
        for serial,pin,point in [('AX','D01',[200,31]),('AY','D02',[200,47])]:
            node=f'blocks/{serial}/pins/L/4';ref=serial+'.'+pin
            c.object_ids[serial]=serial;c.aliases[ref]=[node]
            c.terminals[node]={'side':'input','pin_number':pin,'geometry':{'point':point,'row':point[1]},'source_literals':{}}
        c.nets['physical']['source_literals']['targets']=['AX.D01','AY.D02']
        c.partition_repeated_outputs();c.memberships()
        by_name={c.names[key]:c.nodes[key]for key in c.nets}
        self.assertEqual(by_name['AP161AV2'],['blocks/AV/pins/R/2','blocks/AX/pins/L/4'])
        self.assertEqual(by_name['AP161AV4'],['blocks/AV/pins/R/4','blocks/AY/pins/L/4'])
        self.assertEqual(c.logical_output_partitions[0]['original source record']['source_literals']['targets'],['AX.D01','AY.D02'])

    def test_connected_or_orphaned_route_components_do_not_get_arbitrarily_split(self):
        for extra in ([[[154,31],[154,33]]], [[[10,10],[11,10]]]):
            c=self.trial(merged=True);c.paths['physical']+=extra;c.graphs['physical']=wire_graph(c.paths['physical'])
            c.partition_repeated_outputs()
            self.assertEqual(list(c.nets),['physical'])
            self.assertEqual(c.logical_output_partitions,[])

    def test_remote_target_claim_is_not_copied_to_both_logical_nets(self):
        c=self.trial(merged=True)
        c.nets['physical']['source_literals']['targets']=['ZZ999AB4']
        before=copy.deepcopy(c.nets)
        c.partition_repeated_outputs()
        self.assertEqual(c.nets,before)
        with self.assertRaises(C.ConversionError):c.memberships()

    def test_redundant_same_net_claims_keep_source_multiplicity_and_one_incidence(self):
        for refs in (['AX.D01','AX.D01'],['AX.D01','AX.input']):
            c=self.trial(merged=True);node='blocks/AX/pins/L/4'
            c.object_ids['AX']='AX';c.aliases['AX.D01']=[node];c.aliases['AX.input']=[node]
            c.terminals[node]={'side':'input','pin_number':'D01','geometry':{'point':[200,31],'row':31},'source_literals':{}}
            c.nets['physical']['source_literals']['targets']=refs
            before=copy.deepcopy(c.nets);c.partition_repeated_outputs();c.memberships()
            with self.subTest(refs=refs):
                self.assertEqual(c.logical_output_partitions[0]['original source record'],before['physical'])
                upper=next(k for k,v in c.names.items()if v=='AP161AV2')
                self.assertEqual(c.nets[upper]['source_literals']['targets'],refs)
                self.assertEqual(c.nodes[upper].count(node),1)
                self.assertEqual(sum(node in v for v in c.nodes.values()),1)

    def test_the_same_logical_occurrence_cannot_belong_to_two_net_records(self):
        c=self.trial();c.nets['extra']=copy.deepcopy(c.nets['upper'])
        c.graphs['extra']=copy.deepcopy(c.graphs['upper']);c.paths['extra']=copy.deepcopy(c.paths['upper'])
        with self.assertRaisesRegex(C.ConversionError,'One terminal belongs to distinct nets'):c.memberships()

    def test_row_qualified_reference_selects_recorded_occurrence(self):
        c=self.trial()
        self.assertEqual(c.resolve('AV.J04✲@31','driver'),'blocks/AV/pins/R/2')
        self.assertEqual(c.resolve('AV.J04@33','driver'),'blocks/AV/pins/R/4')
        self.assertEqual(c.resolve('AV.output@33','driver'),'blocks/AV/pins/R/4')
        for ref,role in [('AV.J04@32','driver'),('AV.J04?@31','driver'),('AV.output@31','target'),('AV.J04@31','unsupported')]:
            with self.subTest(ref=ref,role=role),self.assertRaises(C.ConversionError):c.resolve(ref,role)

    def test_route_context_does_not_relax_unknown_or_different_physical_contacts(self):
        for number in (None,'D13'):
            c=self.trial();c.terminals['blocks/AV/pins/R/4']['pin_number']=number
            with self.subTest(number=number),self.assertRaises(C.ConversionError):c.resolve('AV.J04','driver','upper')

    def test_no_nearby_cell_guess_for_missing_recorded_anchor(self):
        c=self.trial();c.terminals['blocks/AV/pins/R/2']['geometry']['point']=[153,31]
        with self.assertRaises(C.ConversionError):c.resolve('AV.J04','driver','upper')

    def test_actual_AP_sources_keep_both_output_occurrences(self):
        from test_converter import source
        for page in ('AP161','AP451','AP491','AP501'):
            path=source(page)
            raw=path.read_bytes();model=C.strict_json(raw);original=copy.deepcopy(model)
            c=C.Converter(model,path,C.digest(raw),C.choose_text(path));drivers=[]
            for key,record in c.nets.items():
                ref=record['source_literals'].get('driver')
                if isinstance(ref,str)and ref.startswith('AV.'):
                    drivers.append(c.resolve(ref,'driver',key))
            with self.subTest(page=page):
                self.assertEqual(set(drivers),{'blocks/AV/pins/R/2','blocks/AV/pins/R/4'})
                self.assertEqual(c.terminals['blocks/AV/pins/R/2']['pin_number'],c.terminals['blocks/AV/pins/R/4']['pin_number'])
                self.assertEqual(model,original)
                self.assertEqual(path.read_bytes(),raw)


if __name__=='__main__':unittest.main()
