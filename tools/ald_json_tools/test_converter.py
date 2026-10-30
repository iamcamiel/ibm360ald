"""Run: python -m unittest discover -s tools/ald_json_tools -p test_converter.py -v"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from collections import defaultdict

sys.path.insert(0,str(Path(__file__).resolve().parent))
import convert_ald_json as converter
from ald_render import load_page,wire_graph,render_page

ROOT=Path(__file__).resolve().parents[2]


def source(page):
    candidates=list((ROOT/'json').rglob(page+' *.json'))
    if len(candidates)!=1:raise unittest.SkipTest('Repository source fixture unavailable: '+page)
    path=candidates[0]
    if '$schema' in json.loads(path.read_bytes()):
        # Deliberately published v4 pages retain their exact v3 input as a fixture.
        path=ROOT/'review/v3'/path.relative_to(ROOT/'json')
        if not path.is_file():raise unittest.SkipTest('Archived v3 source fixture unavailable: '+page)
    return path


def convert(page):
    path=source(page);raw=path.read_bytes()
    instance=converter.Converter(converter.strict_json(raw),path,converter.digest(raw),converter.choose_text(path))
    data,review=instance.convert();converter.validate_new(data)
    return path,raw,instance,data,review


class ConversionTests(unittest.TestCase):

    def destination_driver_trial(self):
        trial=object.__new__(converter.Converter)
        node='blocks/CH/pins/R/4'
        trial.object_ids={'7K':'CH'}
        trial.terminals={node:{'geometry':{'point':[199,68]}}}
        trial.resolve=lambda ref,role,net: node
        trial.graphs={'clock':wire_graph([[[199,68],[196,68],[196,34],[204,34]],
                                         [[196,34],[196,35],[204,35]],[[229,34],[241,34]]])}
        trial.labels=[{'row':34,'column':211,'text':'- CLOCK P3 BLOCKED'},
                      {'row':34,'column':242,'text':'CH4'},
                      {'row':35,'column':215,'text':'RX051'}]
        trial.rows=[' '*245 for _ in range(103)]
        trial.rows[35]=' '*215+'RX051'+' '*25
        literal={'id':'clock','driver':'RX051CH4','additional_drivers':['7K.out_B04'],
                 'targets':['3D.in_D06']}
        return trial,literal,node

    def test_destination_mistaken_for_input_uses_recorded_routed_local_driver(self):
        trial,literal,node=self.destination_driver_trial();before=copy.deepcopy((literal,trial.graphs,trial.labels))
        found=trial.output_destination_driver('clock',literal)
        self.assertEqual(found['local driver'],'7K.out_B04')
        self.assertEqual(found['reference'],'RX051CH4')
        self.assertEqual(found['terminal'],node)
        self.assertEqual(found['destination at'],[215,35])
        self.assertEqual((literal,trial.graphs,trial.labels),before)

    def test_destination_override_rejects_genuine_inputs_and_ambiguous_evidence(self):
        for change in ('left-label','left-text','wrong-suffix','no-local-driver','two-drivers',
                       'wrong-destination','duplicate-destination','duplicate-output','other-owner','disconnected'):
            trial,literal,_=self.destination_driver_trial()
            if change=='left-label':trial.labels.append({'row':2,'column':32,'text':'RX051CH4'})
            elif change=='left-text':trial.rows[2]=' '*32+'RX051CH4'
            elif change=='wrong-suffix':literal['driver']='RX051ZZ4'
            elif change=='no-local-driver':literal.pop('additional_drivers')
            elif change=='two-drivers':literal['additional_drivers'].append('7L.out_D04')
            elif change=='wrong-destination':trial.labels[-1]['text']='RX021'
            elif change=='duplicate-destination':trial.labels.append(copy.deepcopy(trial.labels[-1]))
            elif change=='duplicate-output':trial.labels.append(copy.deepcopy(trial.labels[1]))
            elif change=='other-owner':trial.graphs['other']={(241,34):set()}
            elif change=='disconnected':trial.graphs['clock']=wire_graph([[[196,34],[204,34]],[[196,34],[196,35],[204,35]],[[229,34],[241,34]],[[199,68],[200,68]]])
            with self.subTest(change=change):self.assertIsNone(trial.output_destination_driver('clock',literal))

    def test_caption_tail_uses_unique_incoming_wire_without_changing_source(self):
        tail={'net':'RIGHT_CAPTION_TAIL_12','points':[[229,12],[241,12]]}
        incoming={'net':'incoming','points':[[200,12],[204,12]]}
        labels=[{'row':12,'column':211,'text':'+ BLOCK D SYNC TGR'},
                {'row':12,'column':242,'text':'KA4'}]
        paths=[tail,incoming];before=copy.deepcopy(paths)
        self.assertEqual(converter.caption_tail_owner(tail,paths,{'incoming':{}},labels),'incoming')
        self.assertEqual(paths,before)

    def test_caption_tail_rejects_ambiguous_or_unanchored_matches(self):
        tail={'net':'RIGHT_CAPTION_TAIL_12','points':[[229,12],[241,12]]}
        incoming={'net':'a','points':[[200,12],[204,12]]}
        labels=[{'row':12,'column':211,'text':'+ SIGNAL'},
                {'row':12,'column':242,'text':'KA4'}]
        cases=[([tail,incoming,{'net':'b','points':[[201,12],[204,12]]}],labels),
               ([tail,incoming,{'net':'b','points':[[230,12],[235,12]]}],labels),
               ([tail,incoming],labels[:1]),
               ([tail,incoming],labels+[copy.deepcopy(labels[0])]),
               ([tail,incoming],labels+[copy.deepcopy(labels[1])]),
               ([tail,incoming],[labels[0],dict(labels[1],text='?')]),
               ([tail,incoming],labels),
               ([tail,{'net':'a','points':[[200,13],[204,13]]}],labels),
               ([tail,tail,incoming],labels)]
        for index,(paths,observations) in enumerate(cases):
            with self.subTest(paths=paths,labels=observations):
                nets={} if index==6 else {'a':{},'b':{}}
                self.assertIsNone(converter.caption_tail_owner(tail,paths,nets,observations))
        malformed=copy.deepcopy(tail);malformed['points'][1]=[240,12]
        self.assertIsNone(converter.caption_tail_owner(malformed,[malformed,incoming],{'a':{}},labels))
        malformed=copy.deepcopy(tail);malformed['net']='OTHER_12'
        self.assertIsNone(converter.caption_tail_owner(malformed,[malformed,incoming],{'a':{}},labels))
        malformed=copy.deepcopy(tail);malformed['net']='RIGHT_CAPTION_TAIL_13'
        self.assertIsNone(converter.caption_tail_owner(malformed,[malformed,incoming],{'a':{}},labels))

    def test_caption_output_render_keeps_recorded_tail_and_signal_name(self):
        routes=[[[200,12],[204,12]],[[229,12],[241,12]]]
        page={'page':{'page':'ZZ001','page-type':'ald','title':['TEST'],'date':'','machine':'',
                      'log':'','frame':'','p/n':'','ibm division':'','next block':''},
              'blocks':[],'inputs':[],
              'outputs':[{'net number':'ZZ001KA4','name':'+ BLOCK D SYNC TGR','line':12,'sinks':[]}],
              'nets':[{'net number':'ZZ001KA4','nodes':['outputs/ZZ001KA4'],'routing':routes}],
              'review':{'status':'partial','approved':False,'unresolved discrepancies':True,'details':'review/ZZ/ZZ001.json'}}
        line=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[12]
        self.assertEqual(line[211:229],'+ BLOCK D SYNC TGR')
        self.assertEqual(line[229:242],'─'*13)
        self.assertEqual(line[242:245],'KA4')

    def k_prefix_block_trial(self, printed='KD11', number='D11', side='R', marker=None, triangle=False):
        trial=object.__new__(converter.Converter)
        block={'geometry':{'column':50,'row':2},'identifiers':{'id':'source','grid':'1A'},
               'function':{'label':'A'},'circuit':{'identifier':'U01AA'},
               'source_form':{'ordinal':0},'source_literals':{},'card_identity':{},'site':{}}
        node=f'blocks/AA/pins/{side}/4'
        pin={'pin_number':number,'geometry':{'row':5},'source_literals':{
             'printed_label':printed,'border_marker':marker,'triangle':triangle,'source_observations':[]}}
        trial.owners={'AA':block};trial.object_ids={'source':'AA'};trial.terminals={node:pin}
        trial.bindings={};trial.rows=[];trial.text_binding=None;trial.labels=[{'column':58 if side=='R' else 46,'row':5,'text':printed}]
        trial.auxiliary=set();trial.issues=[];trial.annotations=defaultdict(list);trial.membership={node:'source-net'}
        return trial,node

    def test_right_k_prefix_becomes_aux_edge_without_changing_pin_or_net(self):
        trial,node=self.k_prefix_block_trial();before=copy.deepcopy(trial.terminals)
        blocks,_=trial.blocks();pin=blocks[0]['pins'][0]
        self.assertEqual(pin,{'side':'R','line':4,'pin':'D11','edge':'aux'})
        self.assertEqual(trial.terminals,before)
        self.assertEqual(trial.membership,{node:'source-net'})
        self.assertEqual(trial.annotations['source-net'],[])
        self.assertIn((58,5,'KD11'),trial.covered)
        self.assertEqual(trial.issues[0]['field'],node+'/edge')
        self.assertEqual(trial.issues[0]['status'],'unresolved')
        page={'page':{'page':'ZZ001','page-type':'ald','title':['TEST'],'date':'','machine':'',
                      'log':'','frame':'','p/n':'','ibm division':'','next block':''},'blocks':blocks,'inputs':[],'outputs':[],
              'nets':[{'net number':'ZZ001AA4','nodes':[node],'routing':[]}],
              'review':{'status':'partial','approved':False,'unresolved discrepancies':True,'details':'review/ZZ/ZZ001.json'}}
        rendered=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()
        self.assertEqual(rendered[5][57:61],'KD11')

    def test_right_k_prefix_preserves_suffix_annotation_and_rejects_edge_conflict(self):
        trial,node=self.k_prefix_block_trial(printed='KD11✲');blocks,_=trial.blocks()
        self.assertEqual(blocks[0]['pins'][0]['edge'],'aux')
        self.assertEqual(trial.annotations['source-net'],[{'at':node,'text':'✲'}])
        for options in ({'marker':'E'},{'triangle':True}):
            trial,_=self.k_prefix_block_trial(**options)
            with self.subTest(options=options),self.assertRaises(converter.ConversionError):trial.blocks()

    def test_k_prefix_rule_does_not_infer_other_pin_or_input_qualifiers(self):
        for options in ({'printed':'KXD11'}, {'printed':'KD11','number':'D1'}):
            trial,_=self.k_prefix_block_trial(**options)
            with self.subTest(options=options),self.assertRaises(converter.ConversionError):trial.blocks()
        trial,_=self.k_prefix_block_trial(printed='K',number=None);blocks,_=trial.blocks()
        self.assertNotIn('edge',blocks[0]['pins'][0])
        trial,node=self.k_prefix_block_trial(side='L');blocks,_=trial.blocks()
        self.assertNotIn('edge',blocks[0]['pins'][0])
        self.assertEqual(trial.annotations['source-net'],[{'at':node,'text':'K'}])

    def bare_contact_observation_trial(self,number='B02',printed='B02✲',row=5,duplicate=False):
        trial=object.__new__(converter.Converter)
        trial.labels=[{'column':58,'row':row,'text':'B02'}]
        trial.no_source=set();trial.graphs={};trial.covered=set();trial.owners={}
        trial.issues=[];trial.gaps=[]
        pin={'pin_number':number,'side':'output','geometry':{'point':[61,5]},'source_literals':{'printed_label':printed}}
        trial.terminals={'blocks/AA/pins/R/4':pin}
        if duplicate:trial.terminals['blocks/AB/pins/R/4']=copy.deepcopy(pin)
        return trial

    def test_known_contact_bare_star_keeps_physical_identity_and_annotation(self):
        trial=self.bare_contact_observation_trial();before=copy.deepcopy(trial.terminals)
        trial.annotate([],[])
        self.assertEqual(trial.gaps,[]);self.assertEqual(trial.issues,[])
        self.assertEqual(trial.terminals,before)

    def test_bare_star_does_not_resolve_unknown_wrong_row_suffix_or_owner(self):
        for options in [{'number':None},{'number':'D05'},{'row':6},{'printed':'B02?'},{'duplicate':True}]:
            trial=self.bare_contact_observation_trial(**options);before=copy.deepcopy(trial.terminals)
            trial.annotate([],[])
            self.assertTrue(trial.gaps,options);self.assertEqual(trial.terminals,before)



    def test_exact_split_terminal_span_requires_existing_literal_and_position(self):
        yes=[({'column':71,'row':10,'text':'2D05│'},'2D05','L',75,10),
             ({'column':71,'row':10,'text':'2'},'2D05','L',75,10),
             ({'column':72,'row':10,'text':'D05'},'2D05','L',75,10),
             ({'column':75,'row':10,'text':'│D05✲'},'D05✲','R',75,10)]
        for args in yes:self.assertTrue(converter.terminal_span_label(*args))
        for label in [{'column':72,'row':10,'text':'D06'},
                      {'column':71,'row':11,'text':'2D05'},
                      {'column':70,'row':10,'text':'2D05'},
                      {'column':71,'row':10,'text':'3D05'},
                      {'column':71,'row':10,'text':'2D05│X'}]:
            self.assertFalse(converter.terminal_span_label(label,'2D05','L',75,10))
        self.assertFalse(converter.terminal_span_label({'column':75,'row':10,'text':'│'},'','L',75,10))

    def test_sink_prefix_consumes_only_exact_same_net_observed_route(self):
        label={'column':203,'row':10,'text':'──AP001'}
        graph=wire_graph([[[203,10],[205,10]]])
        self.assertTrue(converter.sink_prefix_label(label,'AP001',205,10,graph))
        for bad_graph in [{},wire_graph([[[203,10],[203,11]],[[204,10],[204,11]]])]:
            self.assertFalse(converter.sink_prefix_label(label,'AP001',205,10,bad_graph))
        for bad in [dict(label,row=11),dict(label,text='──AP011'),dict(label,text='X─AP001'),dict(label,column=204)]:
            self.assertFalse(converter.sink_prefix_label(bad,'AP001',205,10,graph))

    def test_wire_versus_text_report_is_complete_past_display_cap(self):
        from types import SimpleNamespace
        rows=[' '*245 for _ in range(103)];rows[0]='─'*200+' '*45
        rows[1]=' '*210+'│'+' '*34;rows[93]='│'+' '*244
        actual=[' '*245 for _ in range(103)];actual[0]='X'*200+' '*45
        trial=SimpleNamespace(rows=rows,labels=[],trim=False,newline='\n')
        original=converter.render_page
        try:
            converter.render_page=lambda *args:('\n'.join(actual)+'\n').encode('utf8')
            rendered,result=converter.compare_render({}, {'uncertainties':[]},trial)
        finally:converter.render_page=original
        self.assertEqual(result['different cells'],202)
        self.assertEqual(result['wire glyph differences'],200)
        self.assertEqual(len(result['wiring findings']),200)
        self.assertEqual(len(result['raw source render differences']),202)
        self.assertEqual(len(result['first differences']),120)


    def test_damaged_serial_display_keeps_opaque_identity_and_routing(self):
        _,_,_,data,review=convert('KC101')
        original=copy.deepcopy(data);block=data['blocks'][0];serial=block['serial']
        data['review']['unresolved discrepancies']=True
        record={'field':'blocks/'+serial+'/serial','kind':'illegible','status':'unresolved',
                'visible text':serial[0]+'�','detail':'Damaged printed serial; opaque identity retained.'}
        review['uncertainties'].append(record)
        baseline=render_page(data,{'uncertainties':[]})
        rendered=render_page(data,review)
        differences=[(a,b)for a,b in zip(baseline.decode('utf8'),rendered.decode('utf8'))if a!=b]
        self.assertEqual(differences,[(serial[1],'�')])
        self.assertEqual(data['blocks'],original['blocks'])
        self.assertEqual(data['nets'],original['nets'])
        record['status']='resolved'
        self.assertEqual(render_page(data,review),baseline)
        record['field']='source-review/printed-serial';record['status']='unresolved'
        self.assertEqual(render_page(data,review),baseline)

    def test_damaged_serial_rejects_invalid_masks_and_inconsistent_review(self):
        _,_,_,data,review=convert('KC101');serial=data['blocks'][0]['serial']
        data['review']['unresolved discrepancies']=True
        record={'field':'blocks/'+serial+'/serial','kind':'illegible','status':'unresolved','visible text':serial[0]+'�'}
        review['uncertainties'].append(record)
        for literal in [None,'',True,'A�B','AB']:
            bad=copy.deepcopy(review);bad['uncertainties'][-1]['visible text']=literal
            with self.subTest(literal=literal),self.assertRaises(ValueError):render_page(data,bad)
        for mode in ['duplicate','wrong kind','false flag','absent flag']:
            bad_data=copy.deepcopy(data);bad=copy.deepcopy(review)
            if mode=='duplicate':bad['uncertainties'].append(copy.deepcopy(record))
            elif mode=='wrong kind':bad['uncertainties'][-1]['kind']='conflicting'
            elif mode=='false flag':bad_data['review']['unresolved discrepancies']=False
            else:bad_data['review'].pop('unresolved discrepancies')
            with self.subTest(mode=mode),self.assertRaises(ValueError):render_page(bad_data,bad)

    def test_same_net_incidence_counts_terminal_stem_only_once(self):
        _,_,_,data,review=convert('KC101')
        block=next(b for b in data['blocks']if any(p['side']=='R'and isinstance(p.get('pin'),str)for p in b['pins']))
        pin=next(p for p in block['pins']if p['side']=='R'and isinstance(p.get('pin'),str))
        column=int(block['grid position'][:-1]);row=2+7*'ABCDEFGHJKLMN'.index(block['grid position'][-1])+pin['line']-1
        x=27+23*column+7+len(pin['pin'])+1
        node=f"blocks/{block['serial']}/pins/R/{pin['line']}"
        q=copy.deepcopy(data);q['blocks']=[copy.deepcopy(block)];q['blocks'][0]['pins']=[copy.deepcopy(pin)];q['inputs']=[];q['outputs']=[]
        q['nets']=[{'net number':'KC101ZZ1','nodes':[node],'routing':[[[x-2,row],[x,row],[x,row-2]]]}]
        def cell(value):return render_page(value,{'uncertainties':[]}).decode('utf8').splitlines()[row][x]
        self.assertEqual(cell(q),'┘')
        branch=copy.deepcopy(q);branch['nets'][0]['routing'].append([[x,row],[x+1,row]])
        self.assertEqual(cell(branch),'◇')
        separate=copy.deepcopy(q);separate['nets'].append({'net number':'KC101ZZ2','nodes':[],'routing':[[[x-1,row],[x+1,row]]]})
        self.assertNotEqual(cell(separate),'◇')

    def test_output_continuation_requires_same_net_record_row_and_membership(self):
        _,_,_,q,_=convert('KC101');q['blocks']=[];q['inputs']=[]
        q['nets']=[{'net number':'KC101AA4','nodes':['outputs/KC101AA4'],'routing':[[[204,10],[204,12]]]}]
        q['outputs']=[{'net number':'KC101AA4','line':11,'name':'TEST','sinks':['KC011']}]
        def cell(value):return render_page(value,{'uncertainties':[]}).decode('utf8').splitlines()[11][204]
        self.assertEqual(cell(q),'◇')
        for mode in ['record','row','membership']:
            bad=copy.deepcopy(q)
            if mode=='record':bad['outputs']=[]
            elif mode=='row':bad['outputs'][0]['line']=9
            else:bad['nets'][0]['nodes']=[]
            with self.subTest(mode=mode):self.assertNotEqual(cell(bad),'◇')
        q['outputs'].append(copy.deepcopy(q['outputs'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate explicit output'):render_page(q,{'uncertainties':[]})

    def reference_resolution_trial(self):
        trial=object.__new__(converter.Converter)
        trial.auxiliary=set();trial.primary_aliases={'AA.p':['one']};trial.aliases={'AA.p':['one','two']}
        trial.terminals={'one':{'side':'output'},'two':{'side':'output'}}
        return trial

    def test_primary_reference_precedes_secondary_alias_without_renaming(self):
        trial=self.reference_resolution_trial()
        self.assertEqual(trial.resolve('AA.p','driver'),'one')
        trial.primary_aliases={};trial.aliases={'AA.q':['two']}
        self.assertEqual(trial.resolve('AA.q','driver'),'two')

    def test_primary_and_alias_only_ambiguities_still_reject(self):
        for mode in ['two primary','two alias','absent']:
            trial=self.reference_resolution_trial()
            if mode=='two primary':trial.primary_aliases['AA.p']=['one','two']
            else:trial.primary_aliases={}
            if mode=='absent':trial.aliases={}
            with self.subTest(mode=mode),self.assertRaises(converter.ConversionError):trial.resolve('AA.p','driver')

    def hanging_output_trial(self,paths):
        from collections import defaultdict
        trial=object.__new__(converter.Converter);trial.pid='KC101'
        trial.labels=[{'column':242,'row':10,'text':'AA4'}]
        rows=[list(' '*245)for _ in range(103)]
        rows[10][242:245]='AA4';rows[11][205:210]='AP001';rows[11][215:220]='AP011'
        trial.rows=[''.join(row)for row in rows];trial.names={'n':'KC101AA4'}
        trial.paths={'n':paths};trial.graphs={'n':wire_graph(paths)};trial.nodes=defaultdict(list)
        trial.issues=[]
        return trial

    def test_missing_hanging_length_defaults_to_one_and_records_finding(self):
        paths=[[[200,10],[242,10]]];trial=self.hanging_output_trial(paths)
        before=copy.deepcopy(paths);outputs,_,fanouts=trial.outputs()
        self.assertNotIn('hanging wire length',outputs[0])
        self.assertEqual(fanouts['n'],[[[203,10],[203,11],[205,11]]])
        self.assertEqual(paths,before)
        self.assertEqual(trial.issues[0]['field'],'outputs/KC101AA4/hanging wire length')
        self.assertEqual(trial.issues[0]['assumed length'],1)
        self.assertEqual(trial.issues[0]['status'],'unresolved')

    def test_mixed_destination_positions_project_to_v4_hanging_list_with_finding(self):
        paths=[[[195,10],[242,10]],[[195,10],[195,11],[205,11]]]
        trial=self.hanging_output_trial(paths)
        row10=list(trial.rows[10]);row10[205:210]='DR185';trial.rows[10]=''.join(row10)
        row11=list(trial.rows[11]);row11[205:210]='KC021';row11[215:220]=' '*5;trial.rows[11]=''.join(row11)
        trial.labels.extend([{'column':205,'row':10,'text':'DR185'},{'column':205,'row':11,'text':'KC021'}])
        before=copy.deepcopy((trial.labels,trial.rows,trial.paths));outputs,_,_=trial.outputs()
        self.assertEqual(outputs[0]['sinks'],['DR185','KC021'])
        self.assertEqual(outputs[0]['hanging wire length'],9)
        issue=trial.issues[0]
        self.assertEqual(issue['field'],'outputs/KC101AA4/sinks')
        self.assertEqual(issue['source positions'],[{'page':'DR185','at':[205,10]},{'page':'KC021','at':[205,11]}])
        self.assertEqual(issue['projected positions'],[{'page':'DR185','at':[205,11]},{'page':'KC021','at':[215,11]}])
        self.assertEqual((trial.labels,trial.rows,trial.paths),before)
        page={'page':{'page':'KC101','page-type':'ald','title':['TEST'],'date':'','machine':'',
                      'log':'','frame':'','p/n':'','ibm division':'','next block':''},
              'blocks':[],'inputs':[],'outputs':outputs,
              'nets':[{'net number':'KC101AA4','nodes':['outputs/KC101AA4'],'routing':paths}],
              'review':{'status':'partial','approved':False,'unresolved discrepancies':True,'details':'review/KC/KC101.json'}}
        rows=render_page(page,{'uncertainties':trial.issues}).decode('utf8').splitlines()
        self.assertEqual(rows[11][205:210],'DR185');self.assertEqual(rows[11][215:220],'KC021')

    def test_mixed_destinations_without_label_or_with_other_layout_still_block(self):
        for missing in (True,False):
            trial=self.hanging_output_trial([[[195,10],[242,10]],[[195,10],[195,11],[205,11]]])
            row10=list(trial.rows[10]);row10[205:210]='DR185';trial.rows[10]=''.join(row10)
            row11=list(trial.rows[11]);row11[205:210]='KC021';row11[215:220]=' '*5
            if not missing:row11[224:229]='AP011'
            trial.rows[11]=''.join(row11)
            trial.labels.append({'column':205,'row':10,'text':'DR185'})
            if not missing:trial.labels.extend([{'column':205,'row':11,'text':'KC021'},{'column':224,'row':11,'text':'AP011'}])
            with self.subTest(missing_label=missing),self.assertRaises(converter.ConversionError) as error:trial.outputs()
            self.assertEqual(error.exception.finding['code'],'output_fanout_layout')

    def test_single_missing_hanger_is_renderable_with_assumed_one_wire_cell(self):
        paths=[[[200,10],[204,10]],[[229,10],[242,10]]]
        trial=self.hanging_output_trial(paths);trial.rows[11]=trial.rows[11][:215]+' '*30
        outputs,_,_=trial.outputs()
        route=paths+trial.assumed_singleton_hangers['n']
        page={'page':{'page':'KC101','page-type':'ald','title':['TEST'],'date':'','machine':'',
                      'log':'','frame':'','p/n':'','ibm division':'','next block':''},
              'blocks':[],'inputs':[],'outputs':outputs,
              'nets':[{'net number':'KC101AA4','nodes':['outputs/KC101AA4'],'routing':route}],
              'review':{'status':'partial','approved':False,'unresolved discrepancies':True,'details':'review/KC/KC101.json'}}
        rows=render_page(page,{'uncertainties':trial.issues}).decode('utf8').splitlines()
        self.assertEqual(rows[11][203:210],'└─AP001')
        self.assertEqual(trial.issues[0]['assumed length'],1)

    def test_recorded_nondefault_hanging_length_is_preserved_without_finding(self):
        paths=[[[200,10],[242,10]],[[202,10],[202,11],[205,11]]]
        trial=self.hanging_output_trial(paths);outputs,_,_=trial.outputs()
        self.assertEqual(outputs[0]['hanging wire length'],2)
        self.assertEqual(trial.issues,[])

    def test_connected_fragmented_zero_length_hang_is_direction_independent(self):
        paths=[[[200,10],[242,10]],[[204,10],[204,11]],[[204,11],[205,11]]]
        for reverse in [False,True]:
            actual=copy.deepcopy(paths)
            if reverse:
                for p in actual:p.reverse()
            result=self.hanging_output_trial(actual).outputs()[0]
            with self.subTest(reverse=reverse):self.assertEqual(result[0]['hanging wire length'],0)

    def test_disconnected_and_ambiguous_hanging_candidates_reject(self):
        cases=[[[[200,10],[242,10]],[[204,11],[205,11]]],
               [[[200,10],[242,10]],[[210,11],[205,11]]],
               [[[200,10],[242,10]],[[202,11],[205,11]]],
               [[[200,10],[242,10]],[[204,10],[204,11]],[[204,11],[205,11]],[[203,10],[203,11],[205,11]]]]
        for index,paths in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(converter.ConversionError)as e:self.hanging_output_trial(paths).outputs()
            self.assertEqual(e.exception.finding['code'],'hanging_wire_length')

    def canonical_auxiliary_trial(self):
        role='auxiliary-output-modifier';block={'geometry':{'column':50,'row':2}}
        pin={'terminal_id':'test','side':None,'role':None,'pin_number':'D05','pin_number_status':'observed',
             'geometry':{'row':5,'border_point':[57,5],'point':[61,5]},
             'source_literals':{'side':None,'printed_label':'D05','border_point':[57,5],'border_marker':'K',
                                'source_observations':[{'field':'role','value':role}]},
             'border_decorations':[{'kind':'literal-border-mark','glyph':'K','edge':None,
                                    'position_observations':[{'kind':'border_point','value':[57,5]}]}]}
        return block,pin

    def test_canonical_auxiliary_requires_positive_role_and_geometry(self):
        block,pin=self.canonical_auxiliary_trial()
        self.assertTrue(converter.auxiliary_modifier(pin,block))
        self.assertIsNone(pin['side']);self.assertEqual(pin['pin_number'],'D05')
        pin['role']='auxiliary-output-modifier'
        self.assertTrue(converter.auxiliary_modifier(pin,block))
        pin['role']=None;pin['source_literals']['source_observations']=[]
        self.assertFalse(converter.auxiliary_modifier(pin,block))

    def test_auxiliary_conflicting_side_role_marker_or_placement_rejects(self):
        for mode in ['input','output','missing side','wrong border','wrong label span','wrong marker','duplicate role','raw role','projected marker']:
            block,pin=self.canonical_auxiliary_trial()
            if mode in ('input','output'):pin['side']=mode
            elif mode=='missing side':pin['source_literals'].pop('side')
            elif mode=='wrong border':pin['geometry']['border_point']=[56,5]
            elif mode=='wrong label span':pin['geometry']['point']=[60,5]
            elif mode=='wrong marker':pin['source_literals']['border_marker']='X'
            elif mode=='duplicate role':pin['source_literals']['source_observations']*=2
            elif mode=='raw role':pin['source_literals']['role']='auxiliary-output-modifier'
            else:pin['border_decorations'][0]['glyph']='X'
            with self.subTest(mode=mode),self.assertRaises(converter.ConversionError):converter.auxiliary_modifier(pin,block)

    def test_unprinted_contact_requires_positive_noncontradictory_observation(self):
        _,pin=self.canonical_auxiliary_trial();pin['pin_number']=None;pin['pin_number_status']='unparsed-or-control'
        lit=pin['source_literals'];lit['printed_label']='';lit['source_observations'].append({'field':'printed_pin','value':''})
        self.assertTrue(converter.explicitly_unprinted_terminal(pin))
        for value in ['?',None,'D05']:
            q=copy.deepcopy(pin);q['source_literals']['source_observations'][-1]['value']=value
            with self.subTest(value=value):self.assertFalse(converter.explicitly_unprinted_terminal(q))
        lit['source_observations']=[];self.assertFalse(converter.explicitly_unprinted_terminal(pin))
        lit['source_observations']=[{'field':'border_only_label','value':True}]
        self.assertTrue(converter.explicitly_unprinted_terminal(pin))

    def test_auxiliary_cannot_be_selected_as_driver(self):
        trial=self.reference_resolution_trial();trial.auxiliary={'one'};trial.terminals['one']['side']=None
        with self.assertRaises(converter.ConversionError)as e:trial.resolve('AA.p','driver')
        self.assertEqual(e.exception.finding['code'],'auxiliary_driver')
        self.assertEqual(trial.resolve('AA.p','target'),'one')

    def connector_ownership_trial(self,heading):
        trial=object.__new__(converter.Converter);trial.pid='KC101';trial.page={'frame':'02'};trial.owners={}
        trial.names={'a':'KC101AT4','v':'KC101AV4'}
        rows=[list(' '*245)for _ in range(103)]
        for y,text in [(94,'AT4 A-C3N5D05'),(95,'  A-C3N6D05'),(96,heading),(97,'  A-C4D1E11'),(98,'  A-C4E2D04'),(99,'  K-A2B2D04')]:
            rows[y][49:49+len(text)]=text
        trial.rows=[''.join(r)for r in rows];trial.issue=lambda *a,**k:None
        return trial

    def test_unsupported_connector_heading_stops_before_owner_can_carry(self):
        for heading in ['AV4 A-C3DEF06','AV4','AV4 ???']:
            trial=self.connector_ownership_trial(heading)
            with self.subTest(heading=heading),self.assertRaises(converter.ConversionError)as e:trial.connectors({'AT4':'a','AV4':'v'})
            self.assertEqual(e.exception.finding['code'],'unsupported_connector_heading')
            self.assertEqual(e.exception.finding['reference'],'AV4')
            self.assertEqual(e.exception.finding['at'],[49,96])

    def test_supported_connector_heading_keeps_its_own_continuations(self):
        trial=self.connector_ownership_trial('AV4 A-C3D1F06')
        connectors,positions=trial.connectors({'AT4':'a','AV4':'v'})
        self.assertEqual(connectors['a'],['02A-C3N5D05','02A-C3N6D05'])
        self.assertEqual(connectors['v'],['02A-C3D1F06','02A-C4D1E11','02A-C4E2D04','02K-A2B2D04'])
        self.assertEqual(len(positions),6)

    def shifted_note_trial(self,damage=None):
        path,raw,base,baseline,_=convert('KC101')
        document=converter.strict_json(raw)
        labels=[l for l in document['current_extensions']['printed_labels']
                if l.get('row',-1)>=93 and 4<=l.get('column',-1)<30]
        rows=base.rows.copy()
        for label in labels:
            y=label['row'];x=label['column'];text=label['text'];line=list(rows[y].ljust(245))
            self.assertEqual(''.join(line[x:x+len(text)]),text)
            line[x:x+len(text)]=' '*len(text);line[x-1:x-1+len(text)]=text;rows[y]=''.join(line)
            label['column']-=1
        with tempfile.TemporaryDirectory()as folder:
            text=Path(folder)/'shifted-source.txt';text.write_bytes((base.newline.join(rows)+base.newline).encode('utf8'))
            instance=converter.Converter(document,path,converter.digest(raw),text)
            data,review=instance.convert();converter.validate_new(data)
            self.assertEqual(data['note'],baseline['note'])
            if damage:
                label=labels[0];y=label['row'];x=label['column']+(0 if damage=='span'else len(label['text']))
                line=list(instance.rows[y]);line[x]='X';instance.rows[y]=''.join(line)
            rendered,result=converter.compare_render(data,review,instance)
        return rendered,result

    def test_note_column4_normalization_keeps_content_indent_and_wire_findings(self):
        rendered,result=self.shifted_note_trial()
        self.assertIsNotNone(rendered)
        self.assertEqual(result['different cells'],5)
        self.assertEqual(result['wire glyph differences'],5)
        self.assertTrue(result['all raw differences included'])
        self.assertGreater(len(result['raw source render differences']),5)
        self.assertTrue(any('note group origin to column4'in n for n in result['approved normalizations']))

    def test_note_normalization_rejects_wrong_source_span(self):
        with self.assertRaises(converter.ConversionError)as context:self.shifted_note_trial('span')
        self.assertEqual(context.exception.finding['code'],'note_source_span')

    def test_note_normalization_rejects_overwriting_non_note_content(self):
        with self.assertRaises(converter.ConversionError)as context:self.shifted_note_trial('overlap')
        self.assertEqual(context.exception.finding['code'],'note_overlap')

    def test_external_reference_evidence_preserves_absent_null_order_and_roles(self):
        from types import SimpleNamespace
        nets={
            'absent':{'source_literals':{}},
            'null':{'source_literals':{'external_references':None}},
            'ordered':{'source_literals':{'external_references':['WA613BC4','WA613AB4']},
                'endpoint_claims':[{'relationship':'external_references','role':'observed','values':['BC4','AB4']},
                                   {'relationship':'driver','role':'input'}]}}
        outputs=[{'net number':'N2','sinks':['WA613','AP001']}]
        dummy=SimpleNamespace(nets=nets,names={'absent':'N0','null':'N1','ordered':'N2'})
        before=copy.deepcopy((nets,outputs))
        records=converter.Converter.external_reference_observations(dummy,outputs)
        self.assertEqual([r['source net ID']for r in records],list(nets))
        self.assertFalse(records[0]['present']);self.assertNotIn('value',records[0])
        self.assertTrue(records[1]['present']);self.assertIsNone(records[1]['value'])
        self.assertEqual(records[2]['value'],['WA613BC4','WA613AB4'])
        self.assertEqual(records[2]['source endpoint claims'],nets['ordered']['endpoint_claims'][:1])
        self.assertEqual(records[2]['printed sink pages'],outputs[0]['sinks'])
        self.assertTrue(all(r['directed terminal inference']is False for r in records))
        self.assertEqual((nets,outputs),before)
        records[2]['value'].append('changed');records[2]['source endpoint claims'][0]['values'].append('changed')
        records[2]['printed sink pages'].append('changed')
        self.assertEqual((nets,outputs),before)

    def test_conversion_retains_every_source_external_reference_observation(self):
        _,_,instance,data,review=convert('KC021')
        records=[r for r in review['conversion evidence']['external endpoint observations']
                 if r.get('kind')=='source external reference observation']
        self.assertEqual(len(records),len(instance.nets))
        for record in records:
            old=record['source net ID'];source_net=instance.nets[old]
            self.assertEqual(record['new net number'],instance.names[old])
            self.assertEqual(record['present'],'external_references'in source_net['source_literals'])
            self.assertEqual('value'in record,record['present'])
            if record['present']:self.assertEqual(record['value'],source_net['source_literals']['external_references'])
            self.assertEqual(record['source endpoint claims'],[c for c in source_net.get('endpoint_claims',[])if c.get('relationship')=='external_references'])
            self.assertFalse(record['directed terminal inference'])
        self.assertEqual(review['content sha256'],converter.content_digest(data))

    def test_log_capture_preserves_complete_reserved_field(self):
        from types import SimpleNamespace
        for value in ('7','583','153B','ABCDEFGHIJK'):
            with self.subTest(value=value):
                rows=[' '*245 for _ in range(103)]
                row=list(rows[98]);row[211:225]=list('LOG'+value.rjust(11));rows[98]=''.join(row)
                dummy=SimpleNamespace(pid='XX001',rows=rows,issue=lambda *args:None)
                dummy.cell=lambda x,y,width:rows[y][x:x+width].strip()
                self.assertEqual(converter.Converter.page_fields(dummy)['log'],value)

    def test_explicit_blank_division_preserves_slot_and_unknown_semantics(self):
        _,_,_,data,details=convert('KC021')
        data['page']['ibm division']='SDD'
        known=render_page(data,details).decode('utf8').splitlines()
        data['page']['ibm division']=None
        data['review']['unresolved discrepancies']=True
        details['uncertainties']=[u for u in details['uncertainties']if u['field']!='page/ibm division']
        details['uncertainties'].append({'field':'page/ibm division','status':'unresolved','visible text':''})
        before=copy.deepcopy((data,details));expected=known.copy()
        expected[102]=known[102][:223]+'   '+known[102][226:]
        self.assertEqual(render_page(data,details).decode('utf8').splitlines(),expected)
        self.assertEqual((data,details),before)
        self.assertIsNone(data['page']['ibm division'])
        self.assertFalse(data['review']['approved'])
        self.assertTrue(data['review']['unresolved discrepancies'])

    def test_missing_or_nonstring_blank_display_evidence_is_rejected(self):
        _,_,_,data,details=convert('KC021')
        data['page']['ibm division']=None
        details['uncertainties']=[u for u in details['uncertainties']if u['field']!='page/ibm division']
        with self.assertRaisesRegex(ValueError,'No literal display evidence'):
            render_page(data,details)
        for bad in (None,0,False,[],{}):
            with self.subTest(value=bad):
                altered=copy.deepcopy(details)
                altered['uncertainties'].append({'field':'page/ibm division','status':'unresolved','visible text':bad})
                with self.assertRaisesRegex(ValueError,'No literal display evidence'):
                    render_page(data,altered)

    def test_unused_and_constant_names_use_lowest_block_then_topmost_pin(self):
        nodes=['blocks/BC/pins/L/2','blocks/AB/pins/L/12','blocks/AB/pins/L/4']
        for suffix in ('unused','gnd','+3v','no-source'):
            self.assertEqual(converter.local_net_id('AP361',nodes,suffix),'AP361ABL4-'+suffix)
        with self.assertRaises(converter.ConversionError):
            converter.local_net_id('AP361',['blocks/AB/pins/R/4'],'gnd')

    def test_unknown_source_gets_named_and_flagged_without_changing_routes(self):
        path,raw,_,_,_=convert('KC101');original=converter.strict_json(raw)
        net=next(n for n in original['nets'] if not str(n['source_literals'].get('driver','')).split('.')[0] in {b['identifiers']['id']for b in original['objects']})
        old=net['literal_id'];net['source_literals']['driver']='UNREADABLE EXTERNAL SOURCE'
        for label in original['current_extensions']['printed_labels']:
            if 20<=label.get('column',999)<=45:label['text']='?'
        instance=converter.Converter(original,path,converter.digest(raw),converter.choose_text(path))
        data,review=instance.convert();converter.validate_new(data)
        number=instance.names[old];self.assertTrue(number.endswith('-no-source'))
        self.assertTrue(any(u['field']=='nets/'+number+'/source' and u['status']=='unresolved' for u in review['uncertainties']))
        self.assertEqual(wire_graph(next(n for n in data['nets']if n['net number']==number)['routing']),instance.graphs[old])

    def test_five_reviewed_pages_round_trip_and_wiring_findings(self):
        for page,cells in [('AP001',0),('KC011',1),('KC021',2),('KC031',0),('KC101',5)]:
            with self.subTest(page=page):
                path,raw,instance,data,review=convert(page)
                rendered,result=converter.compare_render(data,review,instance)
                self.assertIsNotNone(rendered)
                self.assertEqual(result['different cells'],cells)
                self.assertEqual(result['wire glyph differences'],cells)
                self.assertEqual(len(result['wiring findings']),cells)
                self.assertEqual(data['blocks'],sorted(data['blocks'],key=lambda b:b['serial']))
                self.assertEqual(data['review']['approved'],False)
                self.assertEqual(path.read_bytes(),raw)

    def test_review_flag_tracks_pending_discrepancies_not_resolved_history(self):
        _,_,instance,data,review=convert('KC101')
        _,comparison=converter.compare_render(data,review,instance)
        converter.finalize_review(data,review,comparison)
        self.assertTrue(data['review']['unresolved discrepancies'])
        _,_,instance,data,review=convert('KC021')
        for item in review['uncertainties']:item.update(status='resolved',authority='Test review resolution')
        _,comparison=converter.compare_render(data,review,instance)
        converter.finalize_review(data,review,comparison)
        self.assertFalse(data['review']['unresolved discrepancies'])
        self.assertTrue(review['uncertainties'])

    def test_exact_render_does_not_close_explicit_inherited_source_hold(self):
        _,_,instance,data,review=convert('KC021')
        # Compare the approved glyph projection while testing source-hold behavior.
        instance.rows=[row.translate(str.maketrans({c:'◇' for c in '├┤┬┴'}))
                       for row in instance.rows]
        for item in review['uncertainties']:item['status']='resolved'
        rendered,comparison=converter.compare_render(data,review,instance)
        self.assertEqual(comparison['different cells'],0)
        review['inherited review']={'status':'partial','technical validation':'pending'}
        converter.finalize_review(data,review,comparison)
        self.assertFalse(data['review']['unresolved discrepancies'])
        hold={'field':'source/example-damaged-label','kind':'illegible','status':'unresolved',
              'detail':'Explicit inherited source hold retained by review composition.',
              'sources':[{'path':'example-source-review.json','sha256':'0'*64}]}
        review['uncertainties'].append(hold)
        converter.finalize_review(data,review,comparison)
        self.assertTrue(data['review']['unresolved discrepancies'])
        self.assertFalse(data['review']['approved'])
        self.assertEqual(converter.compare_render(data,review,instance)[0],rendered)
        hold['status']='resolved'
        converter.finalize_review(data,review,comparison)
        self.assertFalse(data['review']['unresolved discrepancies'])

    def test_straps_and_board_only_blocks_keep_approved_representation(self):
        _,_,_,a,_=convert('KC011');_,_,_,b,_=convert('KC021')
        self.assertIn('KC011AGL4-strap',{n['net number']for n in a['nets']})
        self.assertIn('KC021BLL4-strap',{n['net number']for n in b['nets']})
        boards=[v for v in b['blocks'] if 'board'in v]
        self.assertEqual(len(boards),2)
        self.assertTrue(all(v['board']=='02C-D4' and 'socket'not in v for v in boards))

    def test_routing_is_preserved_per_declared_net(self):
        _,_,instance,data,_=convert('KC101')
        for old,number in instance.names.items():
            net=next(n for n in data['nets'] if n['net number']==number)
            self.assertEqual(wire_graph(net['routing']),instance.graphs[old])

    def test_ap001_human_correction_is_explicit_and_hash_bound(self):
        _,raw,instance,data,review=convert('AP001')
        field='outputs/AP001AW4/net number'
        manifest={'pages':{'AP001':{'source sha256':converter.digest(raw),'resolutions':[
            {'field':field,'value':'AP001AW4','authority':'Direct human original-scan reading: upper output is AW4.'}]}}}
        converter.apply_corrections(data,review,manifest,converter.digest(raw))
        rendered,result=converter.compare_render(data,review,instance)
        self.assertEqual(result['different cells'],1)
        self.assertEqual(result['first differences'][0]['source'],'U')
        self.assertEqual(result['first differences'][0]['inferred'],'W')
        self.assertEqual(result['unresolved different cells'],0)
        with self.assertRaises(converter.ConversionError):
            converter.apply_corrections(data,review,manifest,'0'*64)

    def test_correction_requires_exact_preimage_and_valid_routes(self):
        _,_,_,data,_=convert('KC101')
        with self.assertRaises(converter.ConversionError):
            converter.replace_pointer(data,'/page/page','KC011','KC101')
        altered=copy.deepcopy(data);altered['nets'][0]['routing']=[[[0,0],[1,1]]]
        with self.assertRaises(converter.ConversionError):converter.validate_new(altered)
        altered=copy.deepcopy(data);altered['nets'][0]['routing']=[[[0,0],[245,0]]]
        with self.assertRaises(converter.ConversionError):converter.validate_new(altered)

    def test_duplicate_keys_and_diagonals_are_rejected(self):
        with self.assertRaises(converter.ConversionError):converter.strict_json(b'{"page":1,"page":2}')
        with self.assertRaises(converter.ConversionError):converter.strict_json(b'{"n":NaN}')
        with self.assertRaises(converter.ConversionError):converter.simplify([[1,2],[3,4]])

    def test_same_pin_identity_on_two_lines_is_not_guessed(self):
        path,raw,_,_,_=convert('KC101');original=converter.strict_json(raw)
        block=original['objects'][0];pin=copy.deepcopy(block['terminals'][0])
        pin['geometry']['row']+=1;pin['source_literals']['row']+=1
        block['terminals'].append(pin)
        with self.assertRaises(converter.ConversionError):
            converter.Converter(original,path,converter.digest(raw),converter.choose_text(path)).convert()

    def test_cli_batch_continues_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bad=root/'bad.json';bad.write_text('{broken',encoding='utf-8')
            output=root/'out';args=[str(source('KC021')),str(bad),'--output',str(output),'--render','--quiet']
            with contextlib.redirect_stdout(io.StringIO()):code=converter.main(args)
            self.assertEqual(code,2)
            data,review=load_page(output/'KC021.json')
            self.assertEqual(data['page']['page'],'KC021')
            # Historical fixture contains the old, unapproved T glyphs.
            expected=converter.choose_text(source('KC021')).read_bytes().decode('utf-8')
            expected=expected.translate(str.maketrans({c:'◇' for c in '├┤┬┴'})).encode('utf-8')
            self.assertEqual((output/'KC021.txt').read_bytes(),expected)
            before=(output/'KC021.json').read_bytes()
            with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(converter.main(args),2)
            self.assertEqual((output/'KC021.json').read_bytes(),before)
            (output/'KC021.json').write_bytes(before.replace(b'KC021',b'KC022',1))
            with self.assertRaises(ValueError):load_page(output/'KC021.json')

    def test_report_cannot_overwrite_source_or_projection(self):
        path=source('KC021');raw=path.read_bytes();text=converter.choose_text(path);text_raw=text.read_bytes()
        for target in (path,text,path.parent/'test-converter-report.json'):
            with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(converter.main([str(path),'--dry-run','--report',str(target)]),2)
        self.assertEqual(path.read_bytes(),raw);self.assertEqual(text.read_bytes(),text_raw)

    def test_dry_run_writes_no_page_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'absent';report=root/'report.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(converter.main([str(source('KC021')),'--dry-run','--quiet','--output',str(output),'--report',str(report)]),0)
            self.assertTrue(report.is_file());self.assertFalse(output.exists())


class Package631RegressionTests(unittest.TestCase):
    def test_auxiliary_border_span_and_mirrored_sides(self):
        helper=ConversionTests();block,pin=helper.canonical_auxiliary_trial()
        pin['source_literals']['printed_label']='KD05'
        pin['border_decorations'][0]['edge']='right'
        pin['source_literals']['source_observations'].append({'field':'border_glyph','value':'K'})
        pin['extensions']={'source_observations':[{'field':'physical_side','value':'right'},
                                                  {'field':'border_glyph','value':'K'}]}
        before=copy.deepcopy(pin)
        self.assertTrue(converter.auxiliary_modifier(pin,block));self.assertEqual(pin,before)
        self.assertIsNone(pin['side']);self.assertEqual(pin['pin_number'],'D05')
        for field in ('physical_side','native_physical_side','layout_side','border_side'):
            for value in ('left','input',None):
                bad=copy.deepcopy(pin);bad['extensions']['source_observations'].append({'field':field,'value':value})
                with self.subTest(field=field,value=value),self.assertRaises(converter.ConversionError):
                    converter.auxiliary_modifier(bad,block)
        for mode in ('span','pin','glyph','mirror','duplicate','input'):
            bad=copy.deepcopy(pin)
            if mode=='span':bad['geometry']['point']=[62,5]
            elif mode=='pin':bad['pin_number']='D06'
            elif mode=='glyph':bad['source_literals']['source_observations'][-1]['value']='X'
            elif mode=='mirror':bad['extensions']['source_observations'][-1]['value']='X'
            elif mode=='duplicate':bad['source_literals']['source_observations'].append({'field':'border_glyph','value':'K'})
            else:bad['side']='input'
            with self.subTest(mode=mode),self.assertRaises(converter.ConversionError):converter.auxiliary_modifier(bad,block)

    def test_auxiliary_passive_membership_remains_nondirectional(self):
        def trial():
            instance=object.__new__(converter.Converter);node='blocks/AT/pins/R/4'
            instance.nets={'n':{'source_literals':{'driver':'AS.D10','targets':[],
                              'passive_terminals':['AT.B13']},'endpoint_claims':[]}}
            instance.aliases={'AT.B13':[node]};instance.auxiliary={node}
            instance.terminals={node:{'pin_number':'B13'}};instance.auxiliary_history=[]
            def stop(*args):raise RuntimeError('after passive guard')
            instance.output_destination_driver=stop
            return instance
        instance=trial();before=copy.deepcopy(instance.nets)
        with self.assertRaisesRegex(RuntimeError,'after passive guard'):instance.memberships()
        self.assertEqual(instance.nets,before);self.assertEqual(instance.auxiliary_history[0]['source field'],'passive_terminals')
        self.assertIn('Nondirectional',instance.auxiliary_history[0]['interpretation'])
        for field in ('driver','targets'):
            instance=trial();instance.nets['n']['source_literals'][field]='AT.B13' if field=='driver' else ['AT.B13']
            with self.subTest(field=field),self.assertRaises(converter.ConversionError) as caught:instance.memberships()
            self.assertEqual(caught.exception.finding['code'],'auxiliary_membership')

    def note_trial(self):
        from types import SimpleNamespace
        labels=[{'column':2,'row':93,'text':'NOTE 1'}, {'column':2,'row':94,'text':'SECOND'},
                {'column':2,'row':95,'text':'C'}, {'column':3,'row':95,'text':'THIRD'}]
        rows=[' '*245 for _ in range(103)]
        for label in labels:
            y=label['row'];x=label['column'];text=label['text'];rows[y]=rows[y][:x]+text+rows[y][x+len(text):]
        page=SimpleNamespace(rows=rows,labels=labels,pid='CA091',trim=False,newline='\n')
        return page,{'note':['NOTE 1','SECOND',' THIRD']},{'uncertainties':[]}

    def test_note_group_retains_lines_and_identifier(self):
        from unittest.mock import patch
        page,data,review=self.note_trial();selected=converter.source_note_labels(page.labels,page.pid)
        self.assertEqual([x['text'] for x in sorted(selected,key=lambda x:x['row'])],['NOTE 1','SECOND','THIRD'])
        rows=page.rows.copy()
        for label in selected:
            y=label['row'];x=label['column'];text=label['text'];rows[y]=rows[y][:x]+' '*len(text)+rows[y][x+len(text):]
        for i,text in enumerate(data['note']):rows[93+i]=rows[93+i][:4]+text+rows[93+i][4+len(text):]
        with patch.object(converter,'render_page',return_value=('\n'.join(rows)+'\n').encode()):
            rendered,comparison=converter.compare_render(data,review,page)
        self.assertEqual(comparison['different cells'],0);self.assertEqual(rendered.decode().splitlines()[95][2],'C')
        self.assertEqual(data['note'],['NOTE 1','SECOND',' THIRD'])
        for extra in ({'column':2,'row':94,'text':'OTHER'}, {'column':2,'row':96,'text':'Z'}, {'column':2,'row':93,'text':'NOTE 2'}):
            with self.subTest(extra=extra),self.assertRaises(converter.ConversionError):converter.source_note_labels(page.labels+[extra],page.pid)

    def test_note_guard_runs_when_rendering_fails(self):
        from unittest.mock import patch
        for index,code in ((2,'note_source_span'),(8,'note_overlap')):
            page,data,review=self.note_trial();row=list(page.rows[93]);row[index]='X';page.rows[93]=''.join(row)
            with self.subTest(code=code),patch.object(converter,'render_page',side_effect=ValueError('simulated renderer failure')):
                with self.assertRaises(converter.ConversionError) as caught:converter.compare_render(data,review,page)
                self.assertEqual(caught.exception.finding['code'],code)
        page,data,review=self.note_trial()
        with patch.object(converter,'render_page',side_effect=ValueError('simulated renderer failure')):
            rendered,comparison=converter.compare_render(data,review,page)
        self.assertIsNone(rendered);self.assertEqual(comparison['code'],'render_unsupported')

    def test_wrapped_reference_exact_span_and_rejections(self):
        rows=[' '*245 for _ in range(93)];literal='─DS011AR4───┘';rows[12]=rows[12][:31]+literal+rows[12][44:]
        label={'column':31,'row':12,'text':literal};graph=wire_graph([[[22,12],[43,12]]]);before=copy.deepcopy((rows,label,graph))
        self.assertEqual(converter.ordinary_input_reference_occurrences(rows,'DS011AR4',graph,[label]),[{'row':12,'column':32,'text':'DS011AR4'}])
        self.assertEqual((rows,label,graph),before)
        for mode in ('prefix','suffix','text','duplicate','extra','endpoint','route'):
            r=rows.copy();g=copy.deepcopy(graph);item=copy.deepcopy(label);labels=[item]
            if mode=='prefix':item['text']='│'+literal[1:];r[12]=r[12][:31]+'│'+r[12][32:]
            elif mode=='suffix':item['text']=literal[:-1]+'│';r[12]=r[12][:43]+'│'+r[12][44:]
            elif mode=='text':r[12]=r[12][:43]+'─'+r[12][44:]
            elif mode=='duplicate':labels.append(copy.deepcopy(item))
            elif mode=='extra':labels.append({'column':32,'row':12,'text':'DS011AR4'})
            elif mode=='endpoint':g.pop((40,12),None);g.pop((41,12),None)
            else:g.pop((31,12),None)
            with self.subTest(mode=mode),self.assertRaises(converter.ConversionError):
                converter.ordinary_input_reference_occurrences(r,'DS011AR4',g,labels)
        r=rows.copy();r[13]=r[13][:32]+'DS011AR4'+r[13][40:]
        self.assertEqual(len(converter.ordinary_input_reference_occurrences(r,'DS011AR4',graph,[label])),2)


class SpareSourceBindingTests(unittest.TestCase):
    def fixture(self,folder):
        path={'net':'SPARE-label','points':[[0,5],[31,5]]}
        paths=[path,{'net':'SPARE','points':[[36,5],[46,5]]},{'net':'SPARE','points':[[46,5],[46,10]]}]
        nets={'SPARE':{'source_literals':{'driver':'external.001','targets':['AA.B13','AB.B13']}}}
        labels=[{'column':1,'row':5,'text':'SPARE'},{'column':36,'row':5,'text':'001'}]
        text=Path(folder)/'source.txt';text.write_text('\n'*5+' SPARE'+'─'*26+' '*4+'001'+'─'*7+'◇'+'\n',encoding='utf-8')
        return path,paths,nets,labels,text

    def test_unique_binding_preserves_disconnected_polylines(self):
        with tempfile.TemporaryDirectory() as folder:
            path,paths,nets,labels,text=self.fixture(folder);before=copy.deepcopy((paths,nets,labels));result=converter.source_bound_spare_label(path,paths,nets,labels,text)
            self.assertEqual(result['net'],'SPARE');self.assertEqual(result['driver'],'external.001');self.assertEqual((paths,nets,labels),before)
            graph=wire_graph([x['points'] for x in paths]);self.assertNotIn((32,5),graph);self.assertNotIn((35,5),graph)
            self.assertEqual(converter.local_net_id('AP235',['blocks/AA/pins/L/4','blocks/AB/pins/L/2'],'spare'),'AP235AAL4-spare')
            self.assertEqual(converter.local_net_id('AP235',['blocks/AA/pins/L/4'],'unused'),'AP235AAL4-unused')
            with self.assertRaises(converter.ConversionError):converter.local_net_id('AP235',[],'spare')

    def test_conflicts_reject_source_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            for mode in ('duplicate_stub','duplicate_label','wrong_label','wrong_driver','duplicate_driver','missing_target','duplicate_target','unrelated_gap','unrelated_overlap','bad_stub','bad_gap','bad_owner','bad_label','absent_text'):
                path,paths,nets,labels,text=self.fixture(folder)
                if mode=='duplicate_stub':paths.append(copy.deepcopy(path))
                elif mode=='duplicate_label':labels.append(copy.deepcopy(labels[0]))
                elif mode=='wrong_label':labels[1]['text']='002'
                elif mode=='wrong_driver':nets['SPARE']['source_literals']['driver']='external.002'
                elif mode=='duplicate_driver':nets['OTHER']={'source_literals':{'drivers':['external.001']}}
                elif mode=='missing_target':nets['SPARE']['source_literals']['targets']=[]
                elif mode=='duplicate_target':nets['SPARE']['source_literals']['targets']=['AA.B13','AA.B13']
                elif mode=='unrelated_gap':paths.append({'net':'OTHER','points':[[32,5],[35,5]]})
                elif mode=='unrelated_overlap':paths.append({'net':'OTHER','points':[[40,5],[44,5]]})
                elif mode in ('bad_stub','bad_gap','bad_owner','bad_label'):
                    rows=text.read_text(encoding='utf-8').splitlines();r=list(rows[5]);r[{'bad_stub':10,'bad_gap':32,'bad_owner':40,'bad_label':2}[mode]]='X';rows[5]=''.join(r);text.write_text('\n'.join(rows)+'\n',encoding='utf-8')
                else:text=None
                with self.subTest(mode=mode):self.assertIsNone(converter.source_bound_spare_label(path,paths,nets,labels,text))




class Column241OutputTests(ConversionTests):
    def trial(self, column=241):
        t=self.hanging_output_trial([[[200,10],[242,10]]])
        t.labels=[{'column':column,'row':10,'text':'AA4'},{'column':211,'row':10,'text':'+ SIGNAL'}]
        rows=[list(' '*246) for _ in range(103)]
        rows[10][211:220]='+ SIGNAL ';rows[10][column:column+3]='AA4'
        t.rows=[''.join(x) for x in rows]
        return t

    def test_241_extracts_exact_name_and_reports_projection(self):
        t=self.trial();before=copy.deepcopy((t.labels,t.rows,t.paths))
        out,_,_=t.outputs()
        self.assertEqual((out[0]['name'],out[0]['net number']),('+ SIGNAL','KC101AA4'))
        self.assertEqual(t.issues[0]['source position'],[241,10])
        self.assertEqual(t.issues[0]['render position'],[242,10])
        self.assertEqual((t.labels,t.rows,t.paths),before)

    def test_242_ordinary_stays_unchanged(self):
        t=self.trial(242);out,_,_=t.outputs()
        self.assertEqual(out[0]['name'],'+ SIGNAL');self.assertEqual(t.issues,[])

    def test_241_rejects_inconsistent_span(self):
        t=self.trial();t.rows[10]=t.rows[10][:241]+'AB4'+t.rows[10][244:]
        with self.assertRaises(converter.ConversionError) as e:t.outputs()
        self.assertEqual(e.exception.finding['code'],'output_reference_span')

    def test_241_rejects_caption_mismatch_and_unowned_graph(self):
        t=self.trial();t.labels[1]['text']='+ WRONG'
        with self.assertRaises(converter.ConversionError) as e:t.outputs()
        self.assertEqual(e.exception.finding['code'],'output_caption_span')
        t=self.trial();t.graphs={'n':wire_graph([[[200,10],[204,10]]])}
        with self.assertRaises(converter.ConversionError) as e:t.outputs()
        self.assertEqual(e.exception.finding['code'],'output_owner')

    def test_dual_headings_and_competing_owners_reject(self):
        t=self.trial();t.labels.append({'column':242,'row':10,'text':'AA4'})
        with self.assertRaises(converter.ConversionError) as e:t.outputs()
        self.assertEqual(e.exception.finding['code'],'output_reference_ambiguity')
        t=self.trial();t.graphs['other']=wire_graph([[[241,10],[242,10]]])
        with self.assertRaises(converter.ConversionError) as e:t.outputs()
        self.assertEqual(e.exception.finding['code'],'output_owner')

    def test_unsupported_offsets_reject(self):
        for col in (240,243):
            with self.subTest(column=col):
                t=self.trial(col)
                with self.assertRaises(converter.ConversionError) as e:t.outputs()
                self.assertEqual(e.exception.finding['code'],'output_reference_offset')


class StandalonePinAnnotationTests(unittest.TestCase):
    def trial(self, text, side='L', number=None):
        trial,node=ConversionTests.k_prefix_block_trial(self,printed=text,number=number,side=side)
        trial.terminals[node]['pin_number_status']='unparsed-or-control'
        trial.terminals[node]['source_literals']['source_observations']=[
            {'field':'printed_pin','value':text},{'field':'control_prefix','value':text}]
        # Original annotation column, not adjacent to the block border.
        trial.labels[0]['column']=46 if side=='L' else 61
        return trial,node

    def test_exact_standalone_markers_keep_declared_membership_without_pin_guess(self):
        for text in ('2','3','8','L'):
            for side in ('L','R'):
                for number in (None,text):
                    with self.subTest(text=text,side=side,number=number):
                        trial,node=self.trial(text,side,number)
                        before=copy.deepcopy((trial.terminals,trial.membership))
                        blocks,_=trial.blocks()
                        self.assertEqual(blocks[0]['pins'],[{'side':side,'line':4}])
                        self.assertEqual(trial.annotations['source-net'],[{'at':node,'text':text}])
                        self.assertEqual(trial.issues,[])
                        self.assertEqual(trial.deferred,[])
                        self.assertEqual((trial.terminals,trial.membership),before)
                        self.assertIn((46 if side=='L' else 61,5,text),trial.covered)

    def test_other_unknown_labels_stay_unresolved_and_physical_pins_are_preserved(self):
        for text in ('23','L3','?','B02'):
            with self.subTest(text=text):
                trial,node=self.trial(text);blocks,_=trial.blocks()
                self.assertIsNone(blocks[0]['pins'][0]['pin'])
                self.assertEqual(trial.annotations['source-net'],[])
                self.assertEqual(trial.issues[0]['field'],node+'/pin')
        for side,text in (('L','3B02'),('R','B023')):
            trial,node=self.trial(text,side,'B02');blocks,_=trial.blocks()
            self.assertEqual(blocks[0]['pins'][0]['pin'],'B02')
            self.assertEqual(trial.annotations['source-net'],[{'at':node,'text':'3'}])
        trial,_=self.trial('3',number='B02')
        with self.assertRaises(converter.ConversionError):trial.blocks()

    def page(self, side, mark, known=False):
        trial,node=self.trial((mark+'B02' if side=='L' else 'B02'+mark) if known else mark,
                              side,'B02' if known else None)
        blocks,_=trial.blocks()
        routes=[[[43,5],[46,5]],[[44,5],[44,7]]] if side=='L' else [
            [[61,5],[64,5]],[[63,5],[63,7]]]
        page={'page':{'page':'ZZ001','page-type':'ald','title':['TEST'],'date':'','machine':'',
                      'log':'','frame':'','p/n':'','ibm division':'','next block':''},
              'blocks':blocks,'inputs':[],'outputs':[],
              'nets':[{'net number':'ZZ001AA4','nodes':[node],'routing':routes,
                       'annotations':trial.annotations['source-net']}],
              'review':{'status':'partial','approved':False,'unresolved discrepancies':False,
                        'details':'review/ZZ/ZZ001.json'}}
        return page

    def test_standalone_annotation_slot_preserves_wire_ink_and_graph_junction(self):
        for side in ('L','R'):
            for mark in ('2','3','8','L'):
                with self.subTest(side=side,mark=mark):
                    page=self.page(side,mark);before=copy.deepcopy(page)
                    row=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[5]
                    self.assertEqual(row[46 if side=='L' else 61],mark)
                    self.assertEqual(row[49 if side=='L' else 58],'─')
                    self.assertEqual(row[44 if side=='L' else 63],'◇')
                    self.assertEqual(page,before)

    def test_known_pin_annotation_spacing_stays_unchanged(self):
        for side in ('L','R'):
            page=self.page(side,'3',known=True)
            row=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[5]
            self.assertEqual(row[46:50] if side=='L' else row[58:62],
                             '3B02' if side=='L' else 'B023')

class StandalonePinLeadTests(unittest.TestCase):
    def page(self, side='L'):
        page=StandalonePinAnnotationTests().page(side,'3')
        page['nets'][0]['routing']=[[[43,5],[48,5]]] if side=='L' else [[[64,5],[59,5]]]
        return page

    def test_unique_old_label_slot_becomes_wire_to_ordinary_unnumbered_terminal(self):
        for side in ('L','R'):
            with self.subTest(side=side):
                page=self.page(side);node=page['nets'][0]['nodes'][0]
                changes,holds=converter.normalize_annotation_leads(page)
                self.assertEqual(holds,[]);self.assertEqual(len(changes),1)
                self.assertEqual(changes[0]['terminal'],node)
                self.assertEqual(changes[0]['after'],[46 if side=='L' else 61,5])
                row=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[5]
                self.assertEqual(row[46 if side=='L' else 61],'3')
                self.assertEqual(row[49 if side=='L' else 58],'─')
                self.assertEqual(converter.normalize_annotation_leads(page),([],[]))

    def test_foreign_wire_or_ambiguous_endpoint_is_not_bridged(self):
        for mode in ('foreign','duplicate','missing','vertical'):
            page=self.page()
            if mode=='foreign':page['nets'].append({'net number':'OTHER','nodes':[], 'routing':[[[47,4],[47,6]]]})
            elif mode=='duplicate':page['nets'][0]['routing']*=2
            elif mode=='missing':page['nets'][0]['routing']=[[[40,5],[47,5]]]
            else:page['nets'][0]['routing']=[[[48,4],[48,5]]]
            before=copy.deepcopy(page)
            changes,holds=converter.normalize_annotation_leads(page)
            self.assertEqual(changes,[]);self.assertEqual(len(holds),1)
            self.assertEqual(page,before)

    def test_route_point_annotation_absolute_position_is_preserved(self):
        page=self.page();net=page['nets'][0]
        net['annotations'].append({'at':{'polyline':0,'point':1},'offset':[2,1],'text':'NOTE'})
        changes,holds=converter.normalize_annotation_leads(page)
        self.assertEqual(holds,[])
        self.assertEqual(net['annotations'][1]['offset'],[4,1])
        self.assertEqual(net['routing'][0][1][0]+net['annotations'][1]['offset'][0],50)

    def test_numbered_pin_and_already_complete_route_remain_unchanged(self):
        for mode in ('numbered','complete'):
            page=self.page()
            if mode=='numbered':
                page['blocks'][0]['pins'][0]['pin']='B02'
                page['nets'][0]['routing'][0][-1]=[46,5]
            else:page['nets'][0]['routing'][0][-1]=[46,5]
            before=copy.deepcopy(page)
            self.assertEqual(converter.normalize_annotation_leads(page),([],[]))
            self.assertEqual(page,before)


class FixedNullPinSlotTests(unittest.TestCase):
    def test_null_and_omitted_pins_fill_the_same_three_cell_slot_on_both_sides(self):
        for side in ('L','R'):
            for explicit in (True,False):
                page=StandalonePinAnnotationTests().page(side,'3')
                pin=page['blocks'][0]['pins'][0]
                if explicit:pin['pin']=None
                before=copy.deepcopy(page)
                node=page['nets'][0]['nodes'][0]
                details={'uncertainties':[{'field':node+'/pin','status':'unresolved','visible text':'?'}]}
                row=render_page(page,details).decode('utf8').splitlines()[5]
                self.assertEqual(row[47:50] if side=='L' else row[58:61],'───')
                self.assertEqual(row[46 if side=='L' else 61],'3')
                self.assertEqual(page,before)
                without_mask=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[5]
                self.assertEqual(without_mask[47:50] if side=='L' else without_mask[58:61],'───')

class FixedSlotGraphTests(unittest.TestCase):
    def test_wire_slot_composes_branches_instead_of_overpainting_them(self):
        for side in ('L','R'):
            page=StandalonePinAnnotationTests().page(side,'3')
            page['nets'][0]['routing']=[[[43,5],[49,5]],[[48,5],[48,7]]] if side=='L' else [[[58,5],[64,5]],[[59,5],[59,7]]]
            before=copy.deepcopy(page)
            row=render_page(page,{'uncertainties':[]}).decode('utf8').splitlines()[5]
            self.assertEqual(row[48 if side=='L' else 59],'◇')
            self.assertEqual(row[49 if side=='L' else 58],'─')
            self.assertEqual(page,before)

if __name__=='__main__':unittest.main()
