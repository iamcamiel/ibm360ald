"""Synthetic topology/terminal correctness fixtures; no card-specific geometry."""
from collections import defaultdict
from copy import deepcopy
import importlib.util,os
from pathlib import Path
import sys,unittest
candidate = os.environ.get('CARD_ROUTER_REVIEW_CANDIDATE')
if candidate:
    spec = importlib.util.spec_from_file_location('router_under_review', candidate)
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
else:
    import render_composite_card as M


def fixture(boundary=True, semantic=False):
 model={'card_type':'9999','portions':{'P':{'function':'A'}},'signal_pins':{'B02':{},'D02':{}},'layout_hints':{'row_step':1}}
 positions={'P':{'x':30,'top':14,'height':7}}
 ports={('P','input','i'):{'point':(26,15),'pin':'B02','triangle':False,'net':'NB','id':'i'},
        ('P','output','o'):{'point':(41,17),'pin':'D02','triangle':False,'net':'ND','id':'o'}}
 exterior={'B02':{'side':'input','row':15,'net':'NB'},'D02':{'side':'output','row':17,'net':'ND'}}
 blocked={(x,y)for x in range(30,38)for y in range(14,21)}|{(x,15)for x in range(27,30)}|{(x,17)for x in range(38,41)}
 reserved={}
 for k,p in ports.items():
  x,y=p['point']
  for xx in(range(x-3,x+1)if k[1]=='input'else range(x,x+4)):reserved.setdefault((xx,y),set()).add(p['net'])
 clearance=set(blocked)
 r=M.Router(80,40,blocked,reserved,{(x+d,y)for x,y in clearance for d in range(-2,3)},clearance)
 for k,p in ports.items():r.virtual_endpoint_directions[p['point']][p['net']].add(0 if k[1]=='input'else 2)
 r.virtual_endpoint_directions[3,15]['NB'].add(2);r.virtual_endpoint_directions[76,17]['ND'].add(0)
 r.route('NB',(26,15),{(3 if boundary else 10,15)});r.route('ND',(41,17),{(76,17)})
 if semantic:model['networks']=[{'id':'NB','inputs':[['P','i']],'outputs':[]},{'id':'ND','inputs':[],'outputs':[['P','o']]}]
 return model,(positions,ports,exterior,r)

def segment(r,net,a,b):
 dx=(b[0]>a[0])-(b[0]<a[0]);dy=(b[1]>a[1])-(b[1]<a[1]);d=M.DIRS.index((dx,dy))
 while a!=b:
  q=a[0]+dx,a[1]+dy;r.wires[a].setdefault(net,set()).add(d);r.wires[q].setdefault(net,set()).add(M.OPPOSITE[d]);r.by_net[net].update((a,q));a=q

class RouterSafetyTests(unittest.TestCase):
 def test_valid_geometry_remains_accepted_and_free_vertical_placement(self):
  model,g=fixture(semantic=True);M.verify(model,g)
  self.assertEqual(g[0]['P']['top'],14);self.assertEqual(g[0]['P']['height'],7)
  # No grid re-alignment is imposed when configured row_step is one.
  g[0]['Q']={'x':60,'top':23,'height':7};M.verify(model,g)
 def test_unrouted_exterior_is_rejected(self):
  model,g=fixture(boundary=False)
  with self.assertRaises(AssertionError):M.verify(model,g)
 def test_one_way_spurious_wire_edge_is_rejected(self):
  model,g=fixture();g[3].wires[10,15]['NB'].add(1)
  with self.assertRaises(AssertionError):M.verify(model,g)
 def test_hidden_wire_cells_outside_layer_index_are_rejected(self):
  model,g=fixture();r=g[3];r.wires[10,25]['NB']={0};r.wires[11,25]['NB']={2}
  with self.assertRaises(AssertionError):M.verify(model,g)
 def test_same_contact_cannot_be_split_between_networks(self):
  model,g=fixture();g[1]['P','input','duplicate']={'point':(26,16),'pin':'B02','triangle':False,'net':'other','id':'duplicate'}
  g[3].route('other',(26,16),{(3,16)})
  with self.assertRaises(AssertionError):M.verify(model,g)
 def test_fully_routed_geometry_cannot_reassign_semantic_network(self):
  model,g=fixture(semantic=True);model['networks'][0]['id']='wrong-semantic-id'
  with self.assertRaises(AssertionError):M.verify(model,g)
 def test_crossing_cannot_hide_virtual_terminal_branch(self):
  r=M.Router(80,40,set());segment(r,'A',(3,12),(76,12));segment(r,'B',(20,7),(20,35));r.virtual_endpoint_directions[20,12]['B'].add(0)
  with self.assertRaises(AssertionError):M.verify({'signal_pins':{},'layout_hints':{'row_step':1}},({}, {}, {}, r))
 def test_foreign_start_at_bend_is_rejected(self):
  r=M.Router(30,30,set());segment(r,'A',(10,16),(20,16));segment(r,'A',(20,16),(20,20));before=deepcopy(dict(r.wires))
  with self.assertRaises(ValueError):r.route('B',(20,16),{(24,16)})
  self.assertEqual(dict(r.wires),before)
 def test_foreign_straight_wire_cannot_be_a_goal(self):
  r=M.Router(30,30,set());segment(r,'A',(10,12),(20,12));before=deepcopy(dict(r.wires))
  with self.assertRaises(ValueError):r.route('B',(14,8),{(14,12)})
  self.assertEqual(dict(r.wires),before)
 def test_foreign_terminal_reservation_cannot_be_a_start(self):
  r=M.Router(30,30,set(),{(10,10):{'A'}})
  with self.assertRaises(ValueError):r.route('B',(10,10),{(16,10)})
  self.assertFalse(r.by_net)
 def test_failed_search_is_atomic_for_wire_geometry(self):
  r=M.Router(30,30,{(15,y)for y in range(7,29)});before=deepcopy(dict(r.wires))
  with self.assertRaises(ValueError):r.route('B',(10,10),{(20,10)})
  self.assertEqual(dict(r.wires),before);self.assertFalse(r.by_net)
 def test_ordinary_perpendicular_crossing_and_junction_remain_distinct(self):
  r=M.Router(80,40,set());segment(r,'A',(3,12),(76,12));segment(r,'B',(20,7),(20,35));segment(r,'A',(30,12),(30,20))
  result=M.verify({'signal_pins':{},'layout_hints':{'row_step':1}},({}, {}, {}, r))
  self.assertEqual(result['crossings'],1);self.assertEqual(result['junctions'],1)

if __name__=='__main__':unittest.main()
