"""Guarded one-time transition from per-card builders to reviewed definitions."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Contracts'))
import legacy_index_mutation_guard as index_guard
index_guard.dependency_paths(index_guard.repository_root(__file__),__file__)
import generate_card as guarded_renderer
index_guard.require_guarded_renderer(guarded_renderer)

from generate_card import ROOT, build, digest, read, write_protected

WORK = ROOT.parent/'tmp/ald-text/ald/card-universal'
REVIEW = WORK/'independent-review/Shared renderer independent review.json'
HISTORY = ROOT/'notes/Card-ALD/history/Before shared generator'


def write_json(path, data):
    write_protected(path, (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def main():
    index_guard.reject_held_index(ROOT,'publish_shared_generator.main')
    approval = read(REVIEW)
    assert approval['passed'] is True and not approval['failures']
    for binding in approval['candidate_bindings']:
        assert digest(Path(binding['path']).read_bytes()) == binding['sha256'], binding['path']
    definitions = sorted((ROOT/'json/Card-ALD/definitions').glob('*.json'))
    old_inventory = read(ROOT/'notes/Card-ALD/Universal card diagrams publication.json')
    originals, all_outputs = {}, {}
    for path in definitions:
        spec = read(path)
        outputs, _ = build(spec)
        all_outputs.update(outputs)
        for variant in [None] + spec['variants']:
            name = spec['card_type'] + (f'-{variant["number"]:02}' if variant else '') + '.txt'
            previous = variant['predecessor_sha256'] if variant else spec['provenance']['canonical_predecessor_sha256']
            raw = (ROOT/'Card-ALD'/name).read_bytes()
            assert digest(raw) == previous, ('Published drawing changed',name)
            expected = [re.sub(r'\bGROUP\s+\d+\b',lambda m:' '*len(m.group()),s).rstrip()
                        for s in raw.decode('utf-8').splitlines()]
            assert outputs[name].decode('utf-8').splitlines() == expected
            originals['Card-ALD/'+name] = raw
    assert set(all_outputs) == {Path(e['path']).name for e in old_inventory['published_files']}
    for relative in ['notes/Card-ALD/Universal card diagrams publication.json', 'csv/Card-ALD/Notation variants.csv', 'Card-ALD/README.txt']:
        originals[relative] = (ROOT/relative).read_bytes()
    for path in definitions:
        card = path.stem
        for relative in [f'notes/Card-ALD/{card} drawing provenance.json',f'notes/Card-ALD/{card} diagram publication receipt.json',f'json/Card-ALD/{card}.json']:
            originals[relative] = (ROOT/relative).read_bytes()
    backup = []
    for relative, raw in originals.items():
        destination = HISTORY/relative
        assert not destination.exists() or destination.read_bytes() == raw
        write_protected(destination,raw)
        backup.append({'path':destination.relative_to(ROOT).as_posix(),'sha256':digest(raw)})
    for definition in definitions:
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/card_ald/generate_card.py'),definition.stem],check=True)
    for name, raw in all_outputs.items():
        assert (ROOT/'Card-ALD'/name).read_bytes() == raw
    source = ROOT/'Card-ALD/README.txt'
    text = source.read_text(encoding='utf-8')
    text += ('\nREBUILD FROM THE REPOSITORY DIRECTORY:\n'
             '    python tools/card_ald/generate_card.py 4191\n'
             'USE THE SAME SCRIPT FOR 0141, 4191, 4633 OR 4634.\n'
             'DEFINITIONS: JSON/CARD-ALD/DEFINITIONS/NNNN.JSON.\n'
             'ONE SHARED RENDERER; NO PER-CARD PYTHON BUILDER IS REQUIRED.\n')
    write_protected(source,text.encode('utf-8'))
    review_dest = ROOT/'notes/Card-ALD/Generation/Shared renderer independent review.json'
    write_protected(review_dest,REVIEW.read_bytes())
    source_locations = [{'original_path':str(REVIEW),'repository_path':review_dest.relative_to(ROOT).as_posix(),
                         'sha256':digest(REVIEW.read_bytes())}]
    for support in approval.get('supporting_files',[]):
        source = Path(support['path']).resolve()
        assert source.is_relative_to((WORK/'independent-review').resolve()) and source.suffix in ['.json','.py']
        raw = source.read_bytes()
        assert digest(raw) == support['sha256']
        destination = (ROOT/'tools/legacy/card_ald'/source.name if source.suffix == '.py'
                       else ROOT/'notes/Card-ALD/Generation'/source.name)
        write_protected(destination,raw)
        source_locations.append({'original_path':str(source),'repository_path':destination.relative_to(ROOT).as_posix(),
                                 'sha256':digest(raw)})
    write_json(ROOT/'notes/Card-ALD/Generation/Shared generator source locations.json',{'files':source_locations})
    summary = {'schema':'shared-card-renderer-publication-v1','published_utc':datetime.now(timezone.utc).isoformat(),
               'cards':[{'card_type':p.stem,'canonical':f'Card-ALD/{p.stem}.txt',
                         'diagram_sha256':digest(all_outputs[p.stem+'.txt']),
                         'variant_count':len(read(p)['variants']),
                         'generation_receipt':f'notes/Card-ALD/Generation/{p.stem}.json'} for p in definitions],
               'published_files':[{'path':'Card-ALD/'+n,'sha256':digest(raw)} for n,raw in all_outputs.items()],
               'changes':'Removed four GROUP annotations from 4191 canonical and seventeen variants; other drawing cells unchanged.',
               'independent_review':{'path':review_dest.relative_to(ROOT).as_posix(),'sha256':digest(review_dest.read_bytes())},
               'previous_publication_files':backup}
    write_json(ROOT/'notes/Card-ALD/Universal card diagrams publication.json',summary)
    write_json(ROOT/'notes/Card-ALD/Generation/Shared generator migration.json',summary)
    print(json.dumps({'drawings':len(all_outputs),'prior_files_preserved':len(backup),'independent_review_passed':True}))


if __name__ == '__main__':
    main()
