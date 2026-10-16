import sys,json,hashlib,copy
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import audit_card_uses as A
checks=[];failures=[]
def check(name,result,detail=None):
    checks.append(dict(name=name,passed=bool(result),detail=detail))
    if not result:failures.append(name)
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def port(id,side,pin,row,triangle=False):return dict(id=id,side=side,pin=pin,row=row,triangle=triangle)
def flags(node,box,forms=None):return A.compare_occurrence(node,box,forms or A.expected_forms({'boxes':[box]})[box['portion']],{'D08':'GROUND','D03':'+3V','B06':'-3V','B11':'+6V'})
def bad(result):return any(x['status'] in ('discrepancy','source_uncertainty') for x in result)
def main():
    box=dict(portion='A1',function='A',circuit_identifier='U03AA',ports=[port('input:1','input','B02',1),port('input:2','input','B03',2),port('output:3','output','D02',3)])
    node=dict(id='AA',card_type='9901',portion='A1',function='A',unit='U03AA',location='A-A1A1',pins=copy.deepcopy(box['ports']))
    check('Unknown synthetic card exact occurrence matches',not bad(flags(node,box)))
    for field,value in [('unit','U99ZZ'),('function','P')]:
        altered=copy.deepcopy(node);altered[field]=value
        check('Injected '+field+' defect detected',bad(flags(altered,box)))
    altered=copy.deepcopy(node);altered['pins'][0]['pin']='B04'
    check('Injected valid-range wrong pin detected',bad(flags(altered,box)))
    altered=copy.deepcopy(node);altered['pins'][0]['pin']='U04'
    check('Injected invalid physical pin detected',bad(flags(altered,box)))
    altered=copy.deepcopy(node);altered['pins'].pop(0)
    check('Unused physical input can be omitted',not bad(flags(altered,box)))
    altered=copy.deepcopy(node);altered['function']='OR'
    for p in altered['pins']:p['triangle']=True
    check('Complete De Morgan form truth equivalent',not bad(flags(altered,box)))
    altered['pins'][0]['triangle']=False
    check('Partial De Morgan markings rejected',bad(flags(altered,box)))
    altered=copy.deepcopy(node);altered['pins'].append(dict(side='input',pin='8D03',row=7,triangle=False))
    check('Annotated power tie separated from signal graph',not bad(flags(altered,box)) and any(f['field']=='power_contact' for f in flags(altered,box)))
    altered=copy.deepcopy(node);altered['pins'].append(dict(side='output',pin='D03',row=7,triangle=False))
    check('Driven power output flagged',bad(flags(altered,box)))
    # Full public API through a new four-digit identity and portable source root.
    fixture=HERE/'card-audit-fixture';path=fixture/'json/ZZ001.json'
    box2=dict(portion='B1',function='A',circuit_identifier='U03AA',ports=[port('input:1','input',None,1),port('input:2','input',None,2),port('output:3','output','D10',3)])
    box1=dict(portion='A1',function='AR',circuit_identifier='U03AR',ports=[port('input:1','input','B02',1),port('output:3','output',None,3),port('output:5','output',None,5)])
    spec={'card_type':'9901','boxes':[box1,box2],'power_contacts':{},'nets':[['PIN:B02','PORT:A1:input:1'],['PORT:A1:output:3','PORT:B1:input:1'],['PORT:A1:output:5','PORT:B1:input:2'],['PORT:B1:output:3','PIN:D10']]}
    nodes=[]
    for id,b in [('AA',box1),('BB',box2)]:nodes.append(dict(id=id,card_type='9901',portion=b['portion'],unit=b['circuit_identifier'],function=b['function'],location='A-A1A1',pins=copy.deepcopy(b['ports'])))
    doc={'page':'ZZ001','nodes':nodes,'nets':[{'id':'N1','driver':'AA.output3','targets':['BB.input1']},{'id':'N2','driver':'AA.output5','targets':['BB.input2']}]}
    dp=fixture/'json/Card-ALD/definitions/9901.json';cp=fixture/'json/Card types current/9901.json';op=fixture/'json/Card-ALD/build-overrides/9901.json'
    catalog={'card_type':'9901','diagram_occurrences':[{'page':'ZZ001','node':n['id'],'source_text':'ALD/ZZ001.txt'} for n in nodes]}
    write(dp,spec);write(cp,catalog);write(path,doc)
    report=A.audit('9901',root=fixture)
    check('Full synthetic API audits two exact occurrences',report['summary']['occurrences']==2 and report['summary']['new_discrepancies']==0)
    check('Distinct pinless link identities accepted correctly',report['summary']['wiring_observations'].get('common_internal_link')==2)
    changed=copy.deepcopy(doc);changed['nets'].extend([{'id':'EXTERNAL','driver':'external.PADDA10','targets':['AA.B02']},{'id':'REMOTE','driver':'XY123.BB4','targets':['AA.B02']},{'id':'MISSINGLOCAL','driver':'ZZ.output','targets':['AA.B02']}]);write(path,changed)
    report=A.audit('9901',root=fixture)
    complete=report['review']+report.get('coverage_limitations',[])
    check('Reserved external and unloaded remote namespaces not false local defects',not any(r.get('net') in ('EXTERNAL','REMOTE') and r['field']=='unresolved_wire_endpoint' for r in complete))
    check('Missing local model endpoint remains transparently reported',any(r.get('net')=='MISSINGLOCAL' and r['field']=='unresolved_wire_endpoint' for r in complete))
    changed=copy.deepcopy(doc);changed['nets'][0]['route_owners']=['AA.output5'];write(path,changed)
    report=A.audit('9901',root=fixture)
    check('Additional modeled driver joining separate nets detected',any(r['field']=='multiple_internal_drivers' for r in report['review']))
    changed=copy.deepcopy(doc);changed['nodes'][0]['pins']=[changed['nodes'][0]['pins'][0],changed['nodes'][0]['pins'][1]];changed['nets'][0]['driver']='AA.D09';write(path,changed)
    report=A.audit('9901',root=fixture)
    check('Explicit stale endpoint label never silently resolves sole port',any(r.get('net')=='N1' for r in report['review']) and not any(r.get('net')=='N1' and r['classification']=='common_internal_link' for r in report['wiring_observations']))
    changed=copy.deepcopy(doc)
    for n,newid in zip(changed['nodes'],['c96r30','c119r23']):n['id']=newid
    changed['nets']=[{'id':'N1','driver':'c96r30.output3','targets':['c119r23.input2']}]
    write(path,changed);write(cp,{'card_type':'9901','diagram_occurrences':[{'page':'ZZ001','node':n['id'],'source_text':'ALD/ZZ001.txt'} for n in changed['nodes']]})
    report=A.audit('9901',root=fixture)
    check('Non-letter source node IDs wiring actually audited',any(r.get('net')=='N1' and r['field']=='internal_wiring' for r in report['review']))
    write(cp,catalog)
    changed=copy.deepcopy(doc);changed['nets'][0]['targets']=['BB.input2'];write(path,changed)
    report=A.audit('9901',root=fixture)
    check('Swapped same-pair pinless terminal not certified',any(r.get('net')=='N1' and r['field']=='internal_wiring' for r in report['review']) and not any(r.get('net')=='N1' and r['classification']=='common_internal_link' for r in report['wiring_observations']),report['summary'])
    changed=copy.deepcopy(doc);changed['nodes'][0]['portion']='ZZ';write(path,changed)
    report=A.audit('9901',root=fixture)
    check('Unknown portion detected by full API',any(r['field']=='portion' and r['observed']=='ZZ' for r in report['review']))
    changed=copy.deepcopy(doc);changed['nodes'][0]['unit']='U99ZZ';write(path,changed)
    correction={'page':'ZZ001','node':'AA','unit':{'U99ZZ':'U03AR'},'model_binding':{'path':'json/ZZ001.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    write(op,{'source_corrections':[correction]});report=A.audit('9901',root=fixture)
    check('Exact source-hash correction recorded separately',report['summary']['known_reviewed_source_corrections']==1 and not any(r.get('block')=='AA' and r['field']=='circuit_identifier' for r in report['review']))
    check('Read-only audit leaves source bytes unchanged',hashlib.sha256(path.read_bytes()).hexdigest()==correction['model_binding']['sha256'])
    changed['unused']='force source hash to differ';write(path,changed);report=A.audit('9901',root=fixture)
    check('Stale scoped correction refused and raw defect retained',report['summary']['known_reviewed_source_corrections']==0 and any(r['field']=='circuit_identifier' for r in report['review']) and any(r['field']=='reviewed_source_correction' for r in report['review']))
    write(path,doc);write(op,{});write(cp,{'card_type':'9901','diagram_occurrences':[]});report=A.audit('9901',root=fixture)
    check('Catalog-free published source occurrences inventoried',report['summary']['occurrences']==2 and any(r['field']=='catalog_coverage' for r in report['review']))
    live={}
    for card in ['0141','4191','4633','4634']:
        report=A.audit(card,root=ROOT);live[card]=report['summary']
        check(card+' normal full audit has model-bound occurrences',report['summary']['occurrences']>100 and all(o['model_sha256'] for o in report['occurrences']))
        check(card+' audit left all source model bytes unchanged',all(hashlib.sha256(Path(b['path']).read_bytes()).hexdigest()==b['sha256'] for b in report['source_bindings']))
        write(HERE/f'{card} independent use audit.json',report);print(card,report['summary'],flush=True)
    receipt={'passed':not failures,'failures':failures,'checks':checks,'live_summary':live,'candidate_bindings':[{'path':str(ROOT/'tools/card_ald/audit_card_uses.py'),'sha256':hashlib.sha256((ROOT/'tools/card_ald/audit_card_uses.py').read_bytes()).hexdigest()}]}
    write(HERE/'Card auditor independent preflight.json',receipt);print(json.dumps({'passed':not failures,'failures':failures,'checks':len(checks)}))
if __name__=='__main__':main()
