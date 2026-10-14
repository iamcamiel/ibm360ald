"""Verify repository CAS text against current hash-bound printer-grid reviews."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,json,hashlib,re
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--write',action='store_true')
 args=parser.parse_args();repo=args.repo.resolve();pages=[]
 for text in sorted((repo/'ALD').rglob('*.txt')):
  page=text.name.split(' ',1)[0]
  if not (page=='AA001' or re.fullmatch(r'Q[B-Y]\d{3}',page)):continue
  model=repo/'json'/text.relative_to(repo/'ALD').parent/(text.stem+' source layout.json')
  spec=read(model) if model.exists() else {};acceptance=spec.get('root_grid_migration_review',{})
  lines=text.read_text(encoding='utf-8-sig').splitlines();errors=[];accepted=acceptance.get('accepted') is True
  if accepted:
   if sha(text)!=acceptance.get('text_sha256'):errors.append('Current TXT does not match accepted hash')
   if len(lines)!=102 or any(len(line)!=245 for line in lines):errors.append('Expected102 complete rows of245 cells')
   tops=dict(zip('ACEGJLNQ',range(0,78,11)));tops['S']=88;tops['F']=22
   for node in spec.get('nodes',[]):
    box=node['box'];grid=node.get('grid',[])
    if len(grid)!=2 or grid[0] not in range(25,202,22) or grid[1]!=tops.get(box[0]):errors.append('Unexpected box grid: '+box)
    if node.get('label_row',7)<7:errors.append('Box shorter than8 rows: '+box)
   if len(lines)==102 and all(len(line)==245 for line in lines):
    if any(lines[r][c]!='│' for r in range(97,102) for c in [150,173,195,237]):errors.append('Title separator differs from confirmed columns')
  pages.append(dict(page=page,text_file=text.relative_to(repo).as_posix(),text_sha256=sha(text),current_rows=len(lines),current_maximum_columns=max(map(len,lines),default=0),accepted_current_grid=accepted,recognized_boxes=len(spec.get('nodes',[])),errors=errors,physical_copy_notes_remain=True))
 report=dict(updated_utc=datetime.now(timezone.utc).isoformat(),scope='Current repository CAS grids and exact accepted TXT hashes; source interpretation remains in independent acceptance/page notes',target={'columns':245,'rows':102},page_count=len(pages),accepted_current_grid_pages=sum(p['accepted_current_grid'] for p in pages),pending_pages=[p['page'] for p in pages if not p['accepted_current_grid']],passed=not any(p['errors'] for p in pages),pages=pages)
 if args.write:
  dest=repo/'notes/CAS grid migration audit.json'
  if dest.exists() and read(dest).get('scope')=='AA001 and Q* except QZ; existing reviewed transcriptions':
   backup=repo/'notes/CAS initial grid migration plan.json';assert not backup.exists();backup.write_bytes(dest.read_bytes())
  dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k!='pages'}))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
