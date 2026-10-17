"""Correct one supplementary crop locator; preserve the first private stage."""
from pathlib import Path
import sys
from copy import deepcopy
from PIL import Image,ImageChops
ROOT=Path('D:/Github/IBM360');O=Path(__file__).parent;sys.path.insert(0,str(ROOT/'ibm360ald/tools/reviews'));import source_review as sr
def bind(p):return sr.binding(p)
def put(p,d):p.write_bytes(sr.encode(d))
prior=O/'3365 source correction/Intent.json';intent=sr.read_json(prior);wrong=O/'A1533 E5 continuation native.png';good=O/'A1533 E5 continuation corrected native.png';source=Path('D:/Reference Materials/IBM 360/IBM_360_ALD/A1 Socket Listing/A1533-01 SOCKET LISTING.tif');box=[4450,260,5820,980];assert ImageChops.difference(Image.open(source).crop(box).convert('RGB'),Image.open(good).convert('RGB')).getbbox()is None
correction={'schema':'private-native-crop-locator-correction-v1','prior_stage':bind(O/'3365 source correction/stage/manifest.json'),'unused_mislocated_crop':bind(wrong),'reason':'The supplementary E5-continuation locator was below its target and showed blank E6/E7 positions; it is not identity proof. Original crop/first private stage retained.','corrected_native_crop':{**bind(good),'box':box,'source':bind(source)},'visual_reading':'E5 continuation explicitly lists KM201 E1; KM841 H1; KM201 J1; KM831 K1.','actual_TXT_JSON_proposal_changes':0,'all_other_native_crops_visually_confirmed':True,'canonical_writes':0};cp=O/'Continuation locator correction.json';assert not cp.exists();put(cp,correction)
f=sr.read_json(O/'Identity findings.json');f['additional_native_evidence']=[x for x in f['additional_native_evidence']if x['crop']['path']!=bind(wrong)['path']]+[{'source':bind(source),'box':box,'crop':bind(good),'record_id':'21:82:100','visually_confirmed':'E5 KM831 K1'}];f['locator_correction']=bind(cp);fp=O/'Identity findings v2.json';assert not fp.exists();put(fp,f)
for links in [intent['evidence'],intent['pages'][0]['evidence']]:
 links[:]=[x for x in links if x['path']not in [bind(wrong)['path'],bind(O/'Identity findings.json')['path']]];links.extend([bind(good),bind(cp),bind(fp),bind(__file__)])
stage=O/'3365 source correction v2';assert not stage.exists();stage.mkdir();ip=stage/'Intent.json';put(ip,intent);result=sr.create_stage(ip,stage/'stage');put(stage/'Staging verification.json',result);print({'passed':result['passed'],'manifest':bind(stage/'stage/manifest.json'),'intent':bind(ip),'findings':bind(fp),'verification':bind(stage/'Staging verification.json')})
