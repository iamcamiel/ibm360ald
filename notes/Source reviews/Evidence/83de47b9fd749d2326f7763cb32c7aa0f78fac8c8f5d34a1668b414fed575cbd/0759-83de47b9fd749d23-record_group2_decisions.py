from pathlib import Path
import json,sys
p=Path(__file__).resolve().parent/'Group 2 review/Visual decisions.json'
d=json.loads(p.read_text('utf-8'))
for argument in sys.argv[1:]:
 key,value=argument.split('=',1)
 if not key.startswith('pin-'):key='pin-'+key.zfill(4)
 if key in d and d[key]!=value:raise ValueError('Do not silently replace prior reading '+key)
 d[key]=value
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
print(len(d),'visual decisions recorded')
