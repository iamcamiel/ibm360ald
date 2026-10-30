from pathlib import Path
import os,sys,json,hashlib,datetime,stat,runpy,subprocess,time
R=Path('D:/Github/IBM360/tmp/ald-team-resume530')
V=R/'Root RT421 isolated candidate validation PROPOSAL1365'
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(p):return json.loads(Path(p).read_bytes())
def regular(p):
 p=Path(p)
 assert p.is_absolute(),str(p)
 for q in [p,*p.parents]:
  s=q.lstat()
  assert not stat.S_ISLNK(s.st_mode) and not (getattr(s,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT),str(q)
 assert p.is_file(),str(p)
 return p
def ref(p):
 p=regular(p);b=p.read_bytes()
 return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def auth(r):
 a=ref(r['path']);assert (a['sha256'],a['bytes'])==(r['sha256'],r['bytes']),(r,a)
 return a
def save(p,d):
 with Path(p).open('x',encoding='utf-8',newline='\n') as f:
  json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def inside(p):
 p=Path(p);assert p.is_absolute() and p.resolve().is_relative_to(V.resolve()),str(p)
 return p
proposal_ref=auth(dict(path=str(V/'Validation proposal.json'),sha256='395ad0cd0bc904806a9f8598a6b2f0752f08aa9ede35051c03a3a4949c6fecc2',bytes=12446))
review_ref=auth(dict(path=str(R/'Root actual RT421 nested pin proposal SOURCE review1365.json'),sha256='dd5e02a46c5f6f5bfea705031b70d3e055024bb55136d4ca322a6d4559c9aa2c',bytes=196249))
diagnostic_ref=auth(dict(path=str(R/'Root actual RT421 nested binding diagnostic full intake1357.json'),sha256='08cb2b9a1fe1785668a14a282468b8020f42c0b13d28f53c1a1e139ba59c68ab',bytes=339007))
plan=load(proposal_ref['path']);review=load(review_ref['path']);diagnostic=load(diagnostic_ref['path'])
guard_ref=auth(dict(path=str(R/'Root current diamond guard authentication1344.py'),sha256='05b9cbfb49ac95228216a4c133c1d498381cb13ea662d104241993a4e432c6b6',bytes=8991))
g=runpy.run_path(guard_ref['path'])
before19=g['current_guards']();assert len(before19)==19
explicit=[plan['runtime'],*plan['private_tools'],review['candidate'],review['exact_installed_original'],review['proposal'],review['only_nonstdlib_import']['current_source'],*diagnostic['scope_pins'],*diagnostic['all_actual_refs']]
for pair in plan['exact_private_inputs']:explicit.extend([pair['source'],pair['private_copy']])
explicit.extend([
 dict(path='D:/Github/IBM360/ibm360ald/tools/ald_json_tools/convert_ald_json.py',sha256='41e4573318279607278974ebaceb005fc65c68c56944ef7292c10ec32242c804',bytes=185627),
 dict(path='D:/Github/IBM360/ibm360ald/tools/ald_json_tools/ald_render.py',sha256='749144c29405fad02231f41e9ba4de9997176282c90d5ca7cff2c2f8debbec14',bytes=19622),
 dict(path='D:/Github/IBM360/ibm360ald/tools/build_browser_cache.py',sha256='b2f205440ddf77b4d07241db5609a43991c7b99ee0e94e9998d2b9ae0a8f2a44',bytes=6528)])
before_explicit=[auth(x) for x in explicit]
tool_entries=sorted(p.name for p in (V/'Tool').iterdir())
assert tool_entries==['ald_render.py','convert_ald_json.py'],tool_entries
cmd=plan['command'];argv=cmd['argv']
assert argv[0]==plan['runtime']['path'] and argv[1:6]==['-I','-B','-X','utf8','-v']
assert argv[6]==plan['private_tools'][0]['path']
assert cmd['timeout_seconds']==60 and cmd['attempt_count']==1 and cmd['cwd']=='D:/Github/IBM360'
outpath=inside(argv[argv.index('-o')+1]);reportpath=inside(argv[argv.index('--report')+1])
stdoutpath=inside(cmd['stdout_capture']);stderrpath=inside(cmd['stderr_capture']);receiptpath=inside(cmd['pid_UTC_exit_receipt'])
startpath=inside(V/'actual attempt started.json');prepath=inside(V/'actual preflight.json')
for p in [outpath,reportpath,stdoutpath,stderrpath,receiptpath,startpath,prepath]:
 assert not p.exists(),'Existing execution artifact; no retry: '+str(p)
# Fresh snapshot of standard-library and runtime origins; site-packages contents are not imported target dependencies.
runtime_root=Path(plan['runtime']['path']).parent
runtime_paths=set()
for p in runtime_root.iterdir():
 if p.is_file() and p.suffix.lower() in ('.exe','.dll','.zip','._pth'):runtime_paths.add(p)
for subtree in ['DLLs','Lib']:
 for p in (runtime_root/subtree).rglob('*'):
  if p.is_file() and 'site-packages' not in p.relative_to(runtime_root).parts and p.suffix.lower() in ('.py','.pyc','.pyd','.dll','.zip','.pth'):
   runtime_paths.add(p)
site=runtime_root/'Lib/site-packages'
if site.exists():
 for p in site.iterdir():
  if p.is_file() and (p.suffix=='.pth' or p.name.startswith(('sitecustomize','usercustomize'))):runtime_paths.add(p)
runtime_before=[ref(p) for p in sorted(runtime_paths)]
pre=dict(utc=utc(),proposal=proposal_ref,source_review=review_ref,diagnostic=diagnostic_ref,guard_source=guard_ref,current19=before19,explicit_input_and_protected_refs=before_explicit,runtime_origins=runtime_before,tool_directory_entries=tool_entries,absent_execution_paths=[str(x) for x in [outpath,reportpath,stdoutpath,stderrpath,receiptpath,startpath]],approval=dict(actual_human_reply='Approve this one validation',questionItemId='["request_user_input_async","call_8f778c89d8d9465caa80745cc6cadee3",0]',scope='Exact proposal1365 one isolated invocation max60 seconds. Received before wind-down, held without execution; human restart now resumes authorized work. Not C005 or installation.'),argv=argv,cwd=cmd['cwd'])
save(prepath,pre)
start_utc=utc();start_monotonic=time.monotonic()
save(startpath,dict(utc=start_utc,approval_consumed_for_this_single_attempt=True,argv=argv,cwd=cmd['cwd'],max_seconds=60))
proc=None;timed_out=False;launch_error=None
with stdoutpath.open('xb') as stdout,stderrpath.open('xb') as stderr:
 try:
  proc=subprocess.Popen(argv,cwd=cmd['cwd'],stdout=stdout,stderr=stderr,shell=False,creationflags=subprocess.CREATE_NO_WINDOW)
  save(V/'actual PID.json',dict(pid=proc.pid,utc_after_Popen=utc(),argv=argv,cwd=cmd['cwd'],method='Direct Popen exact argv, shell=False, CREATE_NO_WINDOW; no monkeypatch or substituted reader'))
  try:code=proc.wait(timeout=60)
  except subprocess.TimeoutExpired:
   timed_out=True;proc.kill();code=proc.wait()
 except Exception as e:
  launch_error=repr(e);code=proc.returncode if proc else None
 stdout.flush();stderr.flush();os.fsync(stdout.fileno());os.fsync(stderr.fileno())
end_utc=utc()
# Capture result before any postcheck so a failed guard cannot obscure the real single attempt.
initial=dict(start_utc=start_utc,end_utc=end_utc,elapsed_seconds=time.monotonic()-start_monotonic,pid=proc.pid if proc else None,exit_code=code,timed_out=timed_out,launch_error=launch_error,argv=argv,cwd=cmd['cwd'],raw_stdout=ref(stdoutpath),raw_stderr=ref(stderrpath),actual_preflight=ref(prepath),single_attempt_marker=ref(startpath),retry_authorized=False)
post_errors=[]
try:
 after19=g['current_guards']()
 after_explicit=[auth(x) for x in explicit]
 runtime_after=[ref(x['path']) for x in runtime_before]
 assert runtime_after==runtime_before,'Runtime origin snapshot changed'
 initial.update(current19_after=after19,explicit_input_and_protected_after=after_explicit,runtime_after=runtime_after,protected_input_and_runtime_hashes_unchanged=True)
except Exception as e:post_errors.append(repr(e))
initial['postcheck_errors']=post_errors
initial['output_files']=[ref(p) for p in sorted(outpath.rglob('*')) if p.is_file()] if outpath.exists() else []
initial['conversion_report']=ref(reportpath) if reportpath.exists() else None
initial['limits']='No automatic retry, installed tool/source/status/cache changes, corpus sweep, C005, canonical or electrical approval. Actual verbose import trace retained for separate origin assessment.'
save(receiptpath,initial)
print(json.dumps(dict(receipt=ref(receiptpath),pid=initial['pid'],exit_code=code,timed_out=timed_out,launch_error=launch_error,postcheck_errors=post_errors,output_files=initial['output_files'],conversion_report=initial['conversion_report']),ensure_ascii=False))

