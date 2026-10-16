"""Synthetic adjacent-input crossing and semantic-identity regression tests."""
from collections import defaultdict
from copy import deepcopy
import unittest

from render_composite_card import Router,verify
from equivalent_input_order import optimize,_obstacles


def fixture(function='A'):
    model={'card_type':'9999','portions':{'X1':{'function':function}},
           'signal_pins':{'B02':{},'D02':{},'B03':{}},'layout_hints':{'row_step':1}}
    positions={'X1':{'x':30,'top':14,'height':7}}
    ports={('X1','input','iA'):{'point':(26,15),'pin':'B02','triangle':False,'net':'A','id':'iA'},
           ('X1','input','iB'):{'point':(26,16),'pin':'D02','triangle':True,'net':'B','id':'iB'},
           ('X1','output','o'):{'point':(41,17),'pin':'B03','triangle':False,'net':'C','id':'o'}}
    exterior={'B02':{'side':'input','row':16,'net':'A'},'D02':{'side':'input','row':15,'net':'B'},
              'B03':{'side':'output','row':17,'net':'C'}}
    blocked,clearance,reserved,_=_obstacles(positions,ports,exterior,80)
    router=Router(80,45,blocked,reserved,{(x+d,y) for x,y in clearance for d in range(-2,3)},clearance)
    for key,port in ports.items():router.virtual_endpoint_directions[port['point']][port['net']].add(0 if key[1]=='input' else 2)
    for data in exterior.values():
        point=(3 if data['side']=='input' else 76,data['row'])
        router.virtual_endpoint_directions[point][data['net']].add(2 if data['side']=='input' else 0)
    for key in ('A','B','C'):
        start=next(p['point'] for p in ports.values() if p['net']==key)
        e=next(e for e in exterior.values() if e['net']==key)
        router.route(key,start,{(3 if e['side']=='input' else 76,e['row'])})
    geometry=(positions,ports,exterior,router);verify(model,geometry)
    return model,geometry


class EquivalentInputOrderTests(unittest.TestCase):
    def test_swap_makes_both_inputs_straight_and_keeps_metadata(self):
        model,geometry=fixture();old=deepcopy(geometry[1]);result,report=optimize(model,geometry)
        self.assertTrue(report['accepted']);self.assertLess(report['after']['crossings'],report['before']['crossings'])
        for key,port in result[1].items():
            self.assertEqual({k:v for k,v in port.items() if k!='point'},{k:v for k,v in old[key].items() if k!='point'})
        self.assertEqual(result[1]['X1','input','iA']['point'],(26,16))
        self.assertEqual(result[1]['X1','input','iB']['point'],(26,15))
        self.assertEqual(result[1]['X1','output','o'],old['X1','output','o'])
        for net in ('A','B'):
            self.assertEqual(len({y for x,y in result[3].by_net[net]}),1)
        # Variant overrides address stable semantic IDs, not the row slot.
        variant={'iA':True,'iB':False}
        self.assertEqual({p['id']:variant[p['id']] for k,p in result[1].items() if k[1]=='input'},variant)
        self.assertEqual(geometry[1],old)

    def test_noncommutative_inputs_never_move(self):
        model,geometry=fixture('AR');result,report=optimize(model,geometry)
        self.assertFalse(report['accepted']);self.assertIs(result,geometry)

    def test_open_asterisk_or_is_eligible(self):
        model,geometry=fixture('✲OR');_,report=optimize(model,geometry)
        self.assertTrue(report['accepted'])


if __name__=='__main__':unittest.main()
