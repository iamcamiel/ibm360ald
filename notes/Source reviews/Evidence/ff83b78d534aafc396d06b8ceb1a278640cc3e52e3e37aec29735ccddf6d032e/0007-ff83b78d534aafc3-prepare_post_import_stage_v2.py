"""Freeze one location-only source_review stage after the combined repo import."""
from pathlib import Path
from copy import deepcopy
from PIL import Image
import argparse,json,hashlib,importlib.util,sys
R=Path('D:/Github/IBM360');H=Path(__file__).resolve().parent;BASE=H.parents[1];REPO=R/'ibm360ald'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
 if not v:raise ValueError(m)
def checked(b):need(sha(b['path'])==b['sha256'],'Stale bound input '+b['path'])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repository-import-proof',required=True,type=Path);args=ap.parse_args();gate=read(args.repository_import_proof);need(gate.get('passed')is True,'Actual completed repository import verification required')
 mp=BASE/'Combined ALD identity correction stage/stage/manifest.json';manifest=read(mp);record=next(x for x in manifest['records']if x['page']=='AP813');prior={}
 for kind,link in record['prior_quartet'].items():
  candidate=record['staged_quartet'][kind];checked(candidate);need(sha(link['path'])==candidate['sha256'],'Working quartet is not exact accepted combined postimage');prior[kind]=bind(link['path'])
 add=read(H/'Exact location addendum plan.json');proof=read(H/'Unique site proof.json');need(sha(H/'Unique site proof.json')=='bd933fc0f13c59569601d696b56a2c7313261489078aaed9cffc396ebf1949b0','Frozen unique-site proof changed');need(len(add['cases'])==2,'Two location cases required')
 model=read(prior['json']['path']);repo_model=REPO/add['cases'][0]['model_path'];repo_text=REPO/'ALD/AP Parallel Adder/AP813 ROS DR FIELD 8 POWERING.txt';need(sha(repo_model)==prior['json']['sha256']and sha(repo_text)==prior['txt']['sha256'],'Repository has not imported exact combined AP813 model/TXT postimage')
 provenance=read(REPO/'notes/Reviewed export provenance.json');matches=[e for e in provenance['exported']if Path(e['destination']).resolve()==repo_text.resolve()];need(len(matches)==1 and matches[0]['text_sha256']==prior['txt']['sha256'],'Accepted repository provenance does not bind current combined AP813 text')
 changes=[];patches=[];pins_before={}
 for c in add['cases']:
  idx=int(c['node_pointer'].split('/')[-1]);n=model['nodes'][idx];portion='B1'if idx==11 else'B2';need(n['card_type']=='4191'and n['portion']==portion and n['printed_card_portion']=='4191'+portion,'Accepted combined card identity drift');need(n['location']=='B-E2F5','Old location differs; do not overwrite a later correction');pins_before[str(idx)]=deepcopy(n['pins']);changes+=c['text_edits'];patches+=c['json_patches']
 need(len(changes)==2 and len(patches)==2,'Only two location cells/pointers allowed');evidence=[bind(H/'Unique site proof.json'),bind(H/'Exact location addendum plan.json'),bind(mp),bind(args.repository_import_proof),bind(Path(__file__))]
 for side in['native_header','native_continuation']:
  crop=proof[side]['crop'];checked(crop);checked(proof[side]['source']);evidence.append(bind(crop['path']))
  with Image.open(proof[side]['source']['path'])as original,Image.open(crop['path'])as pixels:need(original.convert('RGB').crop(crop['box']).tobytes()==pixels.convert('RGB').tobytes(),'A1 witness crop does not match original TIFF pixels')
 for c in add['cases']:checked(c['native_crop']);evidence.append(bind(c['native_crop']['path']))
 notes='AP813 portions4191B1/B2: recover both worn socket letters as B-E2B5 using the unique exact4191/card+portion+AP813 listing at02B-E2B5/B6 and readable final5. B1 source letter looks H-like; this is explicitly cross-reference recovery, not a claim of a clear literal B. B2 native resembles B5. Preserve all accepted4191 type corrections, pins, decorations, function labels, geometry and historical review evidence.'
 intent={'schema':'source-review-intent-v1','review_id':'AP813-4191-B1-B2-unique-socket-recovery','target_root':manifest['target_root'],'unresolved_questions':[],'evidence':evidence,'pages':[{'page':'AP813','model_schema':'ald-page-nodes-v1','source':record['source'],'prior_quartet':prior,'grid':record['grid'],'cell_edits':changes,'json_patches':patches,'notes_append':notes,'preview_config':record['preview_config'],'evidence':evidence}]};out=H/'Post import stage';need(not out.exists(),'Preserve a previous frozen stage attempt');out.mkdir();ip=out/'Intent.json';ip.write_text(json.dumps(intent,ensure_ascii=False,indent=2)+'\n','utf-8');sp=REPO/'tools/reviews/source_review.py';sys.path.insert(0,str(sp.parent));spec=importlib.util.spec_from_file_location('source_review',sp);sr=importlib.util.module_from_spec(spec);spec.loader.exec_module(sr);result=sr.create_stage(ip,out/'stage');need(result.get('passed')is True,'Generic source_review staging failed');m=read(out/'stage/manifest.json');new=read(m['records'][0]['staged_quartet']['json']['path']);need(all(new['nodes'][int(i)]['pins']==pins for i,pins in pins_before.items()),'Accepted pins changed');need(all(new['nodes'][i]['card_type']=='4191'for i in[11,16]),'Accepted card type regressed');(out/'Staging verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'manifest':bind(out/'stage/manifest.json'),'staging_verification':bind(out/'Staging verification.json'),'source_writes':False,'independent_acceptance_required':True},indent=2))
if __name__=='__main__':main()
