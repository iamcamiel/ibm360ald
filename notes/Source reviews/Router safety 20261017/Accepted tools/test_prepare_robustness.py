"""Portable source-free routing fixtures; optional private module override."""
from copy import deepcopy
import importlib.util,os
from pathlib import Path
import unittest
from unittest.mock import patch
if os.environ.get("CARD_ROUTING_CANDIDATE"):
 spec=importlib.util.spec_from_file_location("routing_candidate",Path(os.environ["CARD_ROUTING_CANDIDATE"]))
 M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
else:
 import render_composite_card as M

def gate(inputs=2,outputs=0):
 ins=[{"id":"i"+str(i),"pin":"B"+str(i+2).zfill(2),"triangle":False}for i in range(inputs)]
 outs=[{"id":"o"+str(i),"pin":"D"+str(i+2).zfill(2),"triangle":False}for i in range(outputs)]
 nets=[{"id":p["pin"],"exterior_pin":p["pin"],"inputs":[["P",p["id"]]]if side=="input"else[],"outputs":[["P",p["id"]]]if side=="output"else[]}for side,ps in[("input",ins),("output",outs)]for p in ps]
 return{"card_type":"9999","signal_pins":{p["pin"]:{}for p in ins+outs},"portions":{"P":{"function":"A","unit":"U03AA","_inputs":ins,"_outputs":outs}},"edges":[],"networks":nets,"layout_hints":{"ranks":{"P":0},"row_step":1,"tops":{"P":15}}}
def narrow():
 return{"card_type":"9999","signal_pins":{},"portions":{"A":{"function":"A","unit":"U03AA","_inputs":[],"_outputs":[{"id":"o","pin":None,"triangle":False}]},"B":{"function":"OR","unit":"U03AE","_inputs":[{"id":"i","pin":None,"triangle":True}],"_outputs":[]}},"edges":[],"networks":[{"id":"INTERNAL:AB","exterior_pin":None,"inputs":[["B","i"]],"outputs":[["A","o"]]}],"layout_hints":{"ranks":{"A":0,"B":1},"row_step":1,"tops":{"A":14,"B":16},"bank_interval":12}}
def reservations(g):
 result={};_,ports,exterior,r=g
 for(_,side,_),p in ports.items():
  x,y=p["point"]
  for xx in(range(x-3,x+1)if side=="input"else range(x,x+4)):result.setdefault((xx,y),set()).add(p["net"])
 for d in exterior.values():
  for xx in(range(3,7)if d["side"]=="input"else range(r.width-7,r.width-3)):result.setdefault((xx,d["row"]),set()).add(d["net"])
 return result
class PrepareRobustness(unittest.TestCase):
 def test_straight_narrow_net_needs_no_vertical_turn(self):
  model=narrow();before=deepcopy(model);g=M.prepare(model);M.verify(model,g);self.assertEqual(model,before);self.assertEqual(g[3].by_net["INTERNAL:AB"],{(x,17)for x in range(68,72)})
 def test_disconnected_seed_stubs_are_joined_as_connected_components(self):
  model=gate();method=M.Router.route;calls=[]
  def route(r,net,start,goals):
   goals=set(goals);pending=[next(iter(goals))];seen=set()
   while pending:
    p=pending.pop()
    if p in seen:continue
    seen.add(p)
    for d in r.wires.get(p,{}).get(net,set()):
     dx,dy=M.DIRS[d];q=p[0]+dx,p[1]+dy
     if q in goals and M.OPPOSITE[d]in r.wires.get(q,{}).get(net,set()):pending.append(q)
   self.assertEqual(goals,seen);calls.append(net);return method(r,net,start,goals)
  with patch.object(M.Router,"route",route):g=M.prepare(model)
  M.verify(model,g);self.assertTrue(calls)
 def test_failed_order_retries_are_bounded_and_deterministic(self):
  signatures=[];method=M.Router.route
  for repeat in range(2):
   failed=[]
   def once(r,net,start,goals):
    if not failed:failed.append(net);raise ValueError(("test greedy order blocked",net,start))
    return method(r,net,start,goals)
   with patch.object(M.Router,"route",once):g=M.prepare(gate())
   metrics=M.verify(gate(),g);self.assertGreater(len(metrics["routing_order_trials"]),1);self.assertLessEqual(len(metrics["routing_order_trials"]),4);signatures.append([(p,n,tuple(sorted(ds)))for p,ns in sorted(g[3].wires.items())for n,ds in sorted(ns.items())if ds])
  self.assertEqual(signatures[0],signatures[1])
 def test_temporary_corridors_released_before_pin_optimizers(self):
  model=gate(inputs=3);g=M.prepare(model);self.assertEqual({p:set(ns)for p,ns in g[3].reserved.items()if ns},reservations(g));M.verify(model,g)
  optimized,_=M.optimize_boundary_pins(model,g);M.verify(model,optimized)
 def test_too_small_requested_right_margin_cannot_exclude_output(self):
  model=gate(inputs=0,outputs=1);model["layout_hints"]["right_margin"]=10;g=M.prepare(model);M.verify(model,g);self.assertGreaterEqual(g[3].width-g[0]["P"]["x"],20)
 def test_six_outputs_cannot_grow_a_one_input_box(self):
  with self.assertRaisesRegex(ValueError,"Portion P has 6 output terminals but only 5 output slots.*review the source terminal union"):
   M.prepare(gate(inputs=1,outputs=6))
 def test_six_inputs_allow_eight_row_box_with_six_outputs(self):
  model=gate(inputs=6,outputs=6)
  # Capture the first router construction after box/port geometry is complete;
  # the assertion tests the height rule independently of congested routing.
  saved=[];original=M.Router.__init__
  def init(r,*args,**kwargs):
   import inspect
   frame=inspect.currentframe().f_back;saved.append(deepcopy(frame.f_locals["positions"]));raise RuntimeError("geometry captured")
  with patch.object(M.Router,"__init__",init):
   with self.assertRaisesRegex(RuntimeError,"geometry captured"):M.prepare(model)
  self.assertEqual(saved[0]["P"]["height"],8)
if __name__=="__main__":unittest.main()
