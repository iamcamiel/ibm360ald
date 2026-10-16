"""Exercise the migration publisher in a private repository-shaped fixture."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
ROOT=Path('D:/Github/IBM360/ibm360ald');OUT=ROOT.parent/'tmp/ald-text/ald/card-universal/independent-review'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
repo=OUT/'shared-publisher-fixture/repo';work=repo.parent/'tmp/ald-text/ald/card-universal/independent-review'
work.mkdir(parents=True,exist_ok=True)
def copy(relative):
 dest=repo/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,dest)
for tool in ['generate_card.py','publish_shared_generator.py']:copy('tools/card_ald/'+tool)
for card in ['0141','4191','4633','4634']:
 copy(f'json/Card-ALD/definitions/{card}.json')
 for rel in [f'notes/Card-ALD/{card} drawing provenance.json',f'notes/Card-ALD/{card} diagram publication receipt.json',f'json/Card-ALD/{card}.json']:copy(rel)
for relative in ['notes/Card-ALD/Universal card diagrams publication.json','csv/Card-ALD/Notation variants.csv','Card-ALD/README.txt']:copy(relative)
baseline=read(OUT/'Generic renderer golden baseline.json')
for row in baseline['files']:
 dest=repo/'Card-ALD'/row['file'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(row['text'].encode('utf-8'))
approval=read(OUT/'Shared renderer independent review.json')
for support in approval['supporting_files']:
 source=Path(support['path']);dest=work/source.name;shutil.copyfile(source,dest);support['path']=str(dest)
(work/'Shared renderer independent review.json').write_text(json.dumps(approval,ensure_ascii=False),encoding='utf-8')
run=subprocess.run([sys.executable,'-X','utf8',str(repo/'tools/card_ald/publish_shared_generator.py')],cwd=repo,capture_output=True,text=True)
fail=[]
if run.returncode:fail.append({'publisher_failed':run.stderr})
if not fail:
 for row in baseline['files']:
  history=repo/'notes/Card-ALD/history/Before shared generator/Card-ALD'/row['file']
  output=repo/'Card-ALD'/row['file']
  if sha(history)!=row['sha256']:fail.append({'backup':row['file']})
  if output.read_text(encoding='utf-8').splitlines()!=row['expected_lines']:fail.append({'drawing':row['file']})
 inventory=read(repo/'notes/Card-ALD/Universal card diagrams publication.json')
 if any(sha(repo/row['path'])!=row['sha256'] for row in inventory['published_files']):fail.append('inventory mismatch')
 if not (repo/'notes/Card-ALD/Generation/Shared generator source locations.json').is_file():fail.append('supporting path map missing')
result={'schema':'independent-shared-publisher-fixture-v1','passed':not fail,'failures':fail,'private_repository':str(repo),'files_verified':len(baseline['files']),'publisher_output':run.stdout,'publisher_sha256':sha(ROOT/'tools/card_ald/publish_shared_generator.py')}
(OUT/'Shared publisher fixture review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':not fail,'failures':fail,'drawings':len(baseline['files'])},indent=2))
