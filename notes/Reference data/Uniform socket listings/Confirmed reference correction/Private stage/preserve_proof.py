from pathlib import Path
import hashlib
import json

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
DEST=REPO/'notes/Reference data/Uniform socket listings/Confirmed reference correction'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(doc):return (json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def read(path):return json.loads(path.read_text('utf-8-sig'))
def main():
    locations=[]
    def keep(source,relative):
        source=Path(source);raw=source.read_bytes();target=DEST/relative
        assert target.resolve().is_relative_to(DEST.resolve())
        if target.exists():assert target.read_bytes()==raw
        else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        locations.append({'original_path':str(source),'repository_path':target.relative_to(REPO).as_posix(),'sha256':sha(raw)})
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix.lower() not in {'.pyc','.tmp','.lock'}:
            keep(path,Path('Private stage')/path.relative_to(HERE))
    stage=read(HERE/'Stage manifest.json')
    for label,link in [('Source crop',stage['source_crop']),('Preview font',stage['render_font']),('Corroborating page',stage['corroboration']['text'])]:
        source=Path(link['path']);assert sha(source.read_bytes())==link['sha256'];keep(source,Path('Evidence')/label/source.name)
    registry=ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json'
    keep(registry,Path('A1 table application registry.json'))
    adapter=read(ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json')
    matches=[x for x in adapter['pages'] if x['page']=='A1232-01'];assert len(matches)==1
    for name,doc in [('Current A1 application.json',matches[0]),('Location map.json',{
        'schema':'preserved-a1-correction-location-map-v1','source_original_retained_in_reference_archive':stage['source'],
        'files':locations})]:
        target=DEST/name;raw=encoded(doc)
        assert not target.exists() or target.read_bytes()==raw
        target.write_bytes(raw)
    print(json.dumps({'passed':True,'preserved_files':len(locations)+2,'destination':str(DEST)}))
if __name__=='__main__':main()
