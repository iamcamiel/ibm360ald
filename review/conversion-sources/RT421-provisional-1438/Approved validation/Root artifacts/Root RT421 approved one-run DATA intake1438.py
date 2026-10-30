from pathlib import Path
import json,hashlib,datetime,os,re,base64
R=Path('D:/Github/IBM360/tmp/ald-team-resume530');V=R/'Root RT421 isolated candidate validation PROPOSAL1365'
def load(p):return json.loads(Path(p).read_bytes())
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def auth(r):
 a=ref(r['path']);assert a=={k:r[k] for k in ['path','sha256','bytes']},(a,r);return a
receipt=load(V/'actual command receipt.json')
assert receipt['exit_code']==0 and not receipt['timed_out'] and not receipt['postcheck_errors']
allfiles=[auth(x) for x in receipt['output_files']]
auth(receipt['conversion_report']);auth(receipt['raw_stdout']);auth(receipt['raw_stderr'])
model=load(V/'Output/RT421.json');review=load(V/'Output/review/RT/RT421.json');report=load(V/'conversion report.json')
assert model['$schema']=='https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json'
digest=hashlib.sha256(json.dumps({k:v for k,v in model.items() if k!='review'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert digest==review['content sha256']
detail=(V/'Output'/model['review']['details']).resolve()
assert detail==(V/'Output/review/RT/RT421.json').resolve() and detail.is_relative_to((V/'Output').resolve())
rawsrc=(V/'Inputs/RT421.txt').read_bytes();rawnew=(V/'Output/RT421.txt').read_bytes()
src=rawsrc.decode('utf-8').splitlines();new=rawnew.decode('utf-8').splitlines()
rawdiff=[];padded=[]
for y in range(max(len(src),len(new))):
 a=src[y] if y<len(src) else '';b=new[y] if y<len(new) else ''
 for x in range(max(len(a),len(b))):
  ap=x<len(a);bp=x<len(b);av=a[x] if ap else '';bv=b[x] if bp else ''
  if av!=bv or ap!=bp:rawdiff.append({'at':[x,y],'source':av,'inferred':bv,'source present':ap,'render present':bp})
  if (av if ap else ' ')!=(bv if bp else ' '):padded.append({'at':[x,y],'source':av if ap else ' ','inferred':bv if bp else ' '})
comparison=report['pages'][0]['render comparison']
assert rawdiff==comparison['raw source render differences']
assert len(rawdiff)==19 and len(padded)==19
assert padded==[{k:x[k] for k in ['at','source','inferred']} for x in comparison['wiring findings']]
assert not any(c in rawnew.decode() for c in '├┤┬┴')
stderr=(V/'stderr.raw').read_bytes()
text=stderr.decode('utf-8',errors='replace')
import_lines=[line for line in text.splitlines() if 'ald_render' in line or 'site-packages' in line or '_distutils_hack' in line or 'code object from' in line]
assert any('code object from '+str(V/'Tool/ald_render.py') in line for line in text.splitlines())
runtime=Path(load(V/'Validation proposal.json')['runtime']['path']).parent
startup_paths=[runtime/'Lib/site-packages/distutils-precedence.pth',runtime/'Lib/site-packages/_distutils_hack/__init__.py',runtime/'Lib/site-packages/_distutils_hack/__pycache__/__init__.cpython-312.pyc']
startup_post=[ref(x) for x in startup_paths if x.is_file()]
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='ONE_ACTUALLY_APPROVED_PRIVATE_RT421_VALIDATION_COMPLETED_EXIT0_GENUINE_PARTIAL_V4_WITH_FINDINGS',command_receipt=ref(V/'actual command receipt.json'),preflight=ref(V/'actual preflight.json'),attempt_marker=ref(V/'actual attempt started.json'),output_files=allfiles,report=ref(V/'conversion report.json'),raw_stdout=ref(V/'stdout.raw'),raw_stderr=ref(V/'stderr.raw'),actual_start_utc=receipt['start_utc'],actual_end_utc=receipt['end_utc'],pid=receipt['pid'],elapsed_seconds=receipt['elapsed_seconds'],exit_code=receipt['exit_code'],protected_and_input_hash_postchecks=receipt['postcheck_errors'],V4_schema_literal=model['$schema'],V4_content_digest=digest,V4_review=model['review'],full_sidecar=review,full_report=report,independent_all_raw_presence_differences=rawdiff,independent_all_padded_differences=padded,raw_difference_count=len(rawdiff),padded_difference_count=len(padded),saved_text_T_glyphs=0,actual_import_trace_lines=import_lines,startup_package_posthashes=startup_post,dependency_origin_limit='Verbose trace actually loads staged ald_render SOURCE. Python startup also executed global site-packages distutils-precedence.pth and _distutils_hack cached code. The pth was included in pre/post runtime snapshots; hook py/pyc hashes are POST-ONLY here and were not included in preflight site-packages snapshot. Do not retroclaim independently bound hook preimages or that all actual imports were stdlib. Full raw trace retained. Main candidate exact direct argv and before/after hashes recorded; OS execution-read byte identity is not separately instrumented.',source_claim_limits='Inputs and current installed converter/renderer/package/canonical model/TXT/native are unchanged by posthash checks. Only private one-run output. Original nested text_binding failure historical, corrected private candidate now emits. No canonical SOURCE, geometry, electrical, schema or full-native acceptance. Prior BX.output.B02 double-mark reference versus single-mark observation remains source finding.',coverage_limits='97 routes,28 junctions,229 crossings/full native continuity, omissions, registration, physical ownership, external schema and electrical qualification remain open. All19 render/wire differences and8 uncertainties retained; no approved normalizations.',external_schema='NOT_RUN',approval='Exact human single-use approval consumed by PID91360. No retry or additional run authorized.',candidate_installation='UNINSTALLED; current production converter41e unchanged')
p=R/'Root RT421 approved one-run result full DATA intake1438.json'
with p.open('x',encoding='utf-8',newline='\n') as f:
 json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps(dict(intake=ref(p),digest=digest,review=model['review'],sidecar_keys=list(review),uncertainties=review.get('uncertainties'),raw_diffs=len(rawdiff),padded_diffs=len(padded),blocks=len(model['blocks']),nets=len(model['nets']),startup_origin_gap=out['dependency_origin_limit']),ensure_ascii=False))

