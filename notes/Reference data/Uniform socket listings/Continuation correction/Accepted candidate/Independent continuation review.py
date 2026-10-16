"""Read-only acceptance of the bounded private parser continuation candidate."""
import collections, datetime, hashlib, importlib.util, json, os, pathlib, subprocess, sys
from PIL import Image

HERE=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path('D:/Github/IBM360/ibm360ald')
DATA=HERE/'dataset'
checks=0
bindings={}
def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def bind(p, expected=None):
    global checks
    p=pathlib.Path(p).resolve(); h=sha(p)
    if expected: assert h==expected, ('binding',str(p),h,expected)
    if str(p) in bindings: assert bindings[str(p)]==h
    bindings[str(p)]=h; checks+=1
    return {'path':str(p),'sha256':h}
def need(v,msg):
    global checks
    assert v,msg
    checks+=1
def module(p,name):
    spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def counter(v): return collections.Counter(json.dumps(x,sort_keys=True,ensure_ascii=False) for x in v)

report={'schema':'socket-continuation-independent-acceptance-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed':False,'failures':[],'source_changes_applied':False,'candidate_or_canonical_writes':False}
try:
    owner=read(HERE/'Continuation candidate review.json'); diff=read(HERE/'Semantic diff.json')
    for key in ['candidate_parser','candidate_tests','semantic_diff','native_evidence','candidate_build_manifest']:
        b=owner[key];bind(b['path'],b['sha256'])
    bind(HERE/'Continuation candidate review.json','c0a92a9c604bc16ed29b2aa6ae41ee78f83d79749c4a2df14b4c106efd72b373')
    for b in diff['source_bindings']: bind(REPO/b['path'],b['sha256'])
    bind(diff['old_parser']['path'],diff['old_parser']['sha256'])
    old=module(diff['old_parser']['path'],'review_old_parser')
    new=module(diff['candidate_parser']['path'],'review_new_parser')
    pagefiles=list((DATA/'json/Socket listings uniform/pages').rglob('*.json'))
    pages=[]
    for p in pagefiles:
        d=read(p); pages.append({'page':d['page'],'printed_page':d['printed_page'],'scan_id':d['source']['scan_id'],
                               'board':d['board'],'lines':d['grid']['lines']})
    need(len(pages)==170,'170 page inventory')
    before=old.parse_listings(pages); after=new.parse_listings(pages)
    a={r['id']:r for r in before['records']};b={r['id']:r for r in after['records']}
    need(len(a)==7222 and len(b)==7217,'record totals')
    changed={k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
    supplied={x['id']:x for x in diff['changes']}
    need(changed==set(supplied) and len(changed)==10,'only exact 10 changed/removed records')
    for k in changed: need(a.get(k)==supplied[k]['before'] and b.get(k)==supplied[k]['after'],'raw semantic diff '+k)
    need(sum(a[k]==b[k] for k in a.keys()&b.keys())==7212,'7212 remaining records unchanged')
    need(before.get('issues')==after.get('issues')==[],'zero parser issues')
    need(before.get('tables')==after.get('tables'),'supplementary tables unchanged')
    need(counter(p for r in a.values() for p in r['pins'])==counter(p for r in b.values() for p in r['pins']),'all pin values and evidence exact multiset')
    need(sum(len(r['pins']) for r in b.values())==22616,'22616 pin rows')
    for merge in owner['merges']:
        h,f=merge['header_record_id'],merge['continued_fragment_id']
        need(f not in b and h in b,'fragment collapsed into existing owner '+h)
        for key in ['id','board','sockets','kind','part_number','card_type','header_source']:
            need(a[h].get(key)==b[h].get(key),'owner header unchanged '+h+'/'+key)
        for key in ['pins','raw_lines','source_spans']:
            need(b[h][key]==a[h][key]+a[f][key],'exact concatenation '+h+'/'+key)
    oldrefs=counter((r['id'],q['page'],p) for r in a.values() for q in r['references'] for p in q['portions'])
    newrefs=counter((r['id'],q['page'],p) for r in b.values() for q in r['references'] for p in q['portions'])
    need(oldrefs-newrefs==counter([('101:1:2','ZB011','FF')]) and not(newrefs-oldrefs),'only spurious connector listing portion removed')
    # Run the independent structural verifier with one explicit private-tool binding adaptation.
    # No file is patched: only the private candidate parser absolute path is admitted in memory.
    vp=REPO/'tools/references/verify_uniform_socket_listings.py';bind(vp)
    source=vp.read_text(encoding='utf-8-sig')
    oldline="path = inside(base,link['path']); key = path.relative_to(base).as_posix()"
    newline="path = Path(link['path']).resolve() if link['path'] == PRIVATE_PARSER else inside(base,link['path']); key = PRIVATE_PARSER if str(path) == str(Path(PRIVATE_PARSER).resolve()) else path.relative_to(base).as_posix()"
    need(source.count(oldline)==1,'explicit verifier private adaptation target')
    source=source.replace(oldline,newline).replace("'tools/references/socket_text_parser.py'}","PRIVATE_PARSER}")
    ns={'__file__':str(vp),'__name__':'private_verifier','PRIVATE_PARSER':diff['candidate_parser']['path']}
    exec(compile(source,str(vp),'exec'),ns)
    structural=ns['verify'](REPO,DATA);need(structural['passed'],structural['failures'])
    report['private_structural_verification']=structural
    for x in read(HERE/'Native continuation evidence.json'):
        bind(x['source']['path'],x['source']['sha256']); im=Image.open(x['source']['path']).convert('RGB')
        for c in x['crops']:
            bind(c['crop']['path'],c['crop']['sha256']); crop=Image.open(c['crop']['path']).convert('RGB')
            need(im.crop(c['rect']).tobytes()==crop.tobytes(),'native exact crop '+x['scan_id'])
        bind(x['overview']['path'],x['overview']['sha256'])
    for scan,name in [('100','A1211-01'),('101','A1211-02')]:
        tif=pathlib.Path('D:/Reference Materials/IBM 360/IBM_360_ALD/A1 Socket Listing')/(name+' SOCKET LISTING.tif')
        bind(tif);bind(HERE/'Independent review evidence'/(scan+' overview.png'))
    temp=HERE/'Independent review evidence/test-temp';temp.mkdir(exist_ok=True)
    env=dict(os.environ,TEMP=str(temp),TMP=str(temp))
    proc=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s',str(HERE),'-p','test_socket_text_parser.py','-v'],cwd=HERE,env=env,capture_output=True,text=True)
    (HERE/'Independent review evidence/Candidate tests.txt').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    need(proc.returncode==0 and 'Ran 23 tests' in proc.stderr,'candidate 23 regression tests')
    bind(HERE/'Independent review evidence/Candidate tests.txt')
    # End-of-review epoch check over every source, native proof, tool and candidate bound above.
    for p,h in list(bindings.items()): need(sha(p)==h,'final epoch '+p)
    report.update(passed=True,merges_reviewed=5,unchanged_records=7212,pin_rows_preserved=22616,
      old_portion_references=48268,new_portion_references=48267,
      interpretation='Native sheets confirm qualified connector headers continue under bare physical socket labels across a column/page boundary. Opposite qualifiers, separators and fresh kind headers remain distinct. ZB011 FF is connector listing/wire code, not a card portion.',
      visual_review={'all_five_source_pairs_reviewed':True,'header_and_fragment_identity_visible':True,'no_new_or_opposite_header':True},
      limitations=['Private manifest intentionally binds private parser absolutely; the standard unchanged installed-tool verifier must be run after approved parser promotion and dataset rebuild.','This acceptance changes grouping only; accepted TXT literals and original scans remain unchanged.'])
except Exception as e:
    report['failures'].append(repr(e))
report['check_count']=checks
report['candidate_bindings']=[{'path':p,'sha256':h} for p,h in bindings.items()]
report['supporting_files']=[{'path':str(pathlib.Path(__file__).resolve()),'sha256':sha(__file__)}]
out=HERE/'Independent continuation acceptance.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':checks,'failures':report['failures'],'report':str(out),'sha256':sha(out)},indent=2))
sys.exit(0 if report['passed'] else 1)
