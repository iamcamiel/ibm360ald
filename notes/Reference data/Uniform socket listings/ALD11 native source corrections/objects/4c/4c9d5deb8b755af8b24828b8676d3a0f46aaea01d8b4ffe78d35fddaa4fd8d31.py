"""Execute only explicitly selected steps of the frozen, accepted ALD11 plan."""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('D:/Github/IBM360');OUT=ROOT/'tmp/ald-text/ald/socket-ald-audit/native-eleven-ald-review'
PLAN=OUT/'Publication and scoped import plan.json'
EXPECTED={'manifest':'a4e71415bf45ae47cf824332c022c943fbbe41cf4599c37eed37e2a4e0b811a3',
          'independent_acceptance':'01afcf56ce0dc11451e72ba0487d078aaeb97cf0acf320d3452e473b0e92c25b'}
PAGES=['AP639','AP781','AP813','CS011','DS131']
def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def need(value,message):
 if not value:raise ValueError(message)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--steps',type=int,nargs='+',required=True);args=parser.parse_args()
 plan=read(PLAN);need(plan['allowed_pages']==PAGES,'Page scope changed')
 for key,sha in EXPECTED.items():need(hashlib.sha256(Path(plan[key]['path']).read_bytes()).hexdigest()==sha,'Frozen accepted '+key+' changed')
 for gate in plan['required_prior_gates']:
  receipt=read(gate['path']);need(receipt.get('passed')is True and receipt.get('published')is True,'Prior A1 publication incomplete')
 for index in args.steps:
  need(index in range(len(plan['steps'])),'Unknown plan step')
  step=plan['steps'][index];log=OUT/f'Execution step {index+1:02d}.txt';receiptpath=OUT/f'Execution step {index+1:02d}.json'
  need(not receiptpath.exists(),'Do not replay an executed step')
  result=subprocess.run([sys.executable,'-X','utf8',*step['argv']],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
  log.write_text(result.stdout+result.stderr,encoding='utf-8')
  receipt={'name':step['name'],'argv':step['argv'],'exit_code':result.returncode,'passed':result.returncode==0,
           'completed_utc':datetime.now(timezone.utc).isoformat(),'log':str(log)}
  receiptpath.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt),flush=True)
  need(result.returncode==0,'ALD11 step failed; inspect '+str(log))
if __name__=='__main__':main()
