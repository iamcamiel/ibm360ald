"""Publish independently reviewed complete card views and notation variants."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json
import re
import shutil
import stat
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Contracts'))
import legacy_index_mutation_guard as index_guard

ROOT = index_guard.repository_root(__file__)
WORK = ROOT.parent / 'tmp/ald-text/ald/card-universal'
NOTES = ROOT / 'notes/Card-ALD'
CARDS = {'0141': WORK/'0141', '4191': WORK/'4191', '4633': WORK/'463x', '4634': WORK/'463x'}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    index_guard.guard_target(ROOT,path,'publish_universal_cards.write')
    index_guard.guard_existing_ancestor_index(path,'publish_universal_cards.write')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def replace_preserving_protection(source, destination):
    """Update an explicitly authorized diagram and restore its read-only flag."""
    index_guard.guard_target(ROOT,destination,'publish_universal_cards.replace')
    index_guard.guard_existing_ancestor_index(destination,'publish_universal_cards.replace')
    mode = destination.stat().st_mode if destination.exists() else None
    protected = mode is not None and not mode & stat.S_IWRITE
    if protected:
        destination.chmod(mode | stat.S_IWRITE)
    try:
        shutil.copyfile(source, destination)
    finally:
        if protected:
            destination.chmod(mode)


def main():
    index_guard.reject_held_index(ROOT,'publish_universal_cards.main')
    history = NOTES/'history/Before universal composite views'
    prior = {c: digest(history/(c+'.txt') if (history/(c+'.txt')).exists()
                       else ROOT/f'Card-ALD/{c}.txt') for c in CARDS}
    plan, metadata, index_rows = [], {}, []
    cards = []
    for card, stage in CARDS.items():
        approval_path = WORK/f'independent-review/{card} independent review.json'
        approval = read(approval_path)
        assert approval['passed'] is True and not approval['failures'], card
        assert approval.get('candidate_bindings'), card
        bindings = approval['candidate_bindings']
        if isinstance(bindings, dict):
            bindings = list(bindings.values())
        for b in bindings:
            p = Path(b.get('path', b.get('file', '')))
            assert p.is_file() and digest(p) == b['sha256'], (card, p)
        index_path = stage/(f'{card} variants index.json' if card in ['0141','4191'] else f'{card} render provenance.json')
        index = read(index_path)
        variants = index['variants']
        base_binding = index.get('canonical', index.get('base'))
        assert base_binding['file'] == card+'.txt'
        base = stage/base_binding['file']
        assert digest(base) == base_binding['sha256']
        observed = set()
        for entry in [base_binding] + variants:
            name = entry['file']
            assert re.fullmatch(card+r'(?:-\d{2,})?\.txt', name), name
            source = stage/name
            assert digest(source) == entry['sha256'], name
            raw = source.read_bytes()
            raw.decode('utf-8')
            assert raw not in observed, (card, 'duplicate canonical or variant', name)
            observed.add(raw)
            destination = ROOT/'Card-ALD'/name
            assert (not destination.exists() or name == card+'.txt'
                    or digest(destination) == entry['sha256']), ('Unowned existing variant', name)
            plan.append((source, destination))
            evidence = entry.get('sources', entry.get('evidence', []))
            pages = sorted({str(e.get('page')) for e in evidence if e.get('page')})
            locations = entry.get('instances', sorted({str(e.get('location')) for e in evidence if e.get('location')}))
            index_rows.append({'card_type':card, 'file':name, 'kind':'canonical' if name == card+'.txt' else 'observed notation variant',
                               'source_pages':' '.join(pages), 'source_locations':' '.join(locations), 'sha256':entry['sha256']})
        # Keep source records as exact bytes; published locations are mapped below.
        for path in stage.iterdir():
            if not path.is_file() or not path.name.startswith(card):
                continue
            if path.suffix == '.json' or path.name in [f'{card} universal review.txt', f'{card} variants review.txt', f'{card}.png']:
                metadata[path.resolve()] = NOTES/'Universal'/card/path.name
        metadata[approval_path.resolve()] = NOTES/'Universal/Independent review'/approval_path.name
        cards.append({'card_type':card, 'variant_count':len(variants), 'canonical':f'Card-ALD/{card}.txt',
                      'diagram_sha256':digest(base), 'source_index':str(index_path), 'source_index_sha256':digest(index_path),
                      'independent_review':{'path':str(approval_path),'sha256':digest(approval_path)}})
    dictionary = WORK/'Manual canonical circuit forms.json'
    metadata[dictionary.resolve()] = NOTES/dictionary.name
    # Follow only bounded local source JSON/PNG references, never duplicate TIFFs.
    queue = list(metadata)
    visited = set()
    while queue:
        p = queue.pop()
        if p in visited or p.suffix != '.json':
            continue
        visited.add(p)
        def walk(value):
            if isinstance(value, dict):
                for v in value.values(): yield from walk(v)
            elif isinstance(value, list):
                for v in value: yield from walk(v)
            elif isinstance(value, str):
                yield value
        for value in walk(read(p)):
            try:
                src = Path(value)
                if not src.is_absolute() or not src.is_file() or not src.resolve().is_relative_to(WORK.resolve()):
                    continue
            except (OSError, ValueError):
                continue
            if src.suffix.lower() not in ['.json','.png']:
                continue
            src = src.resolve()
            if src not in metadata:
                metadata[src] = NOTES/'Universal/Supporting evidence'/(digest(src)[:12]+'-'+src.name)
                queue.append(src)
    stamp = datetime.now(timezone.utc).isoformat()
    history.mkdir(parents=True, exist_ok=True)
    for card in CARDS:
        original = ROOT/f'Card-ALD/{card}.txt'
        assert digest(original) in {prior[card], digest(CARDS[card]/(card+'.txt'))}
        dest = history/original.name
        if dest.exists():
            assert digest(dest) == prior[card]
        else:
            shutil.copyfile(original, dest)
        for name in [f'{card} drawing provenance.json', f'{card} diagram publication receipt.json']:
            src = NOTES/name
            if src.exists():
                saved = history/name
                if not saved.exists():
                    shutil.copyfile(src, saved)
    published = []
    for src, dst in plan:
        dst.parent.mkdir(parents=True, exist_ok=True)
        replace_preserving_protection(src, dst)
        assert digest(dst) == digest(src)
        published.append({'path':dst.relative_to(ROOT).as_posix(),'sha256':digest(dst)})
    locations = []
    for src, dst in metadata.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            shutil.copyfile(src, dst)
        locations.append({'original_path':str(src),'repository_path':dst.relative_to(ROOT).as_posix(),'sha256':digest(dst)})
    write(NOTES/'Universal/Source locations.json', {'schema':'universal-card-source-locations-v1','files':locations})
    for item in cards:
        card = item['card_type']
        receipt = {'schema':'card-ald-universal-publication-v1','published_utc':stamp, **item,
                   'prior_drawing':{'path':str(history/(card+'.txt')),'sha256':prior[card]},
                   'published_files':[x for x in published if re.fullmatch(r'Card-ALD/'+card+r'(?:-\d+)?\.txt',x['path'])],
                   'conventions':['The base uses manual-definition-normalized functions, even when no ALD occurrence uses that form.',
                                  'Numbered variants preserve the exact base geometry, pins and wiring, changing only function text and polarity marks.',
                                  'Every unobserved source-usage field remains canonical and is documented in the variant index.',
                                  'Power contacts are listed separately; page-level ties are not additional card signal pins.'],
                   'limits':(['G13 is possibly unused; no reviewed occurrence establishes a signal connection.'] if card=='4634' else [])+
                            (['U55AC standard form was not found in the supplied SLT manual; AR is observation-derived and explicitly provisional.'] if card=='4633' else [])}
        write(NOTES/f'{card} drawing provenance.json',receipt)
        write(NOTES/f'{card} diagram publication receipt.json',receipt)
        model_path = ROOT/f'json/Card-ALD/{card}.json'
        specific = CARDS[card]/(f'{card} composite.json' if card in ['4633','4634'] else f'{card}.geometry.json')
        if specific.exists():
            composite = read(specific)
        else:
            composite = read(CARDS[card]/f'{card} universal provenance.json')
        write(model_path,{'schema':'card-ald-universal-model-v1','card_type':card,'drawing':item['canonical'],
                          'drawing_sha256':item['diagram_sha256'],'source_composite':composite,
                          'provenance':f'notes/Card-ALD/{card} drawing provenance.json'})
    csv_path = ROOT/'csv/Card-ALD/Notation variants.csv'
    csv_path.parent.mkdir(parents=True,exist_ok=True)
    with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(index_rows[0]));writer.writeheader();writer.writerows(index_rows)
    readme = ['CARD-ALD COMPOSITE PINOUTS','',
              'NNNN.TXT USES THE MANUAL-DEFINITION STANDARD SYMBOLS.',
              'NNNN-01.TXT, NNNN-02.TXT, ETC. RETAIN OBSERVED NOTATION VARIANTS.',
              'ALL VARIANTS OF A CARD HAVE IDENTICAL BOX, WIRE AND PIN POSITIONS.',
              'VERTICAL WIRES HAVE ONE CLEAR COLUMN BETWEEN PARALLEL TRACKS.',
              'VERTICAL WIRES LEAVE TWO COLUMNS CLEAR OF BOXES AND PIN LABELS.',
              'POWER CONTACTS ARE LISTED SEPARATELY IN EVERY DRAWING.','',
              *[f'{x["card_type"]}: 1 CANONICAL DRAWING AND {x["variant_count"]} OBSERVED NOTATION VARIANTS.' for x in cards], '',
              '4634 G13 AND 4633 G05: POSSIBLY UNUSED; NO CONNECTION OBSERVED.',
              '4633 U55AC: AR FORM IS OBSERVATION-DERIVED AND PROVISIONAL.', '',
              'VARIANT SOURCES AND CELL DELTAS: NOTES/CARD-ALD/UNIVERSAL.',
              'SEARCHABLE FILE INDEX: CSV/CARD-ALD/NOTATION VARIANTS.CSV.',
              'ORIGINAL DRAWINGS ARE PRESERVED UNDER NOTES/CARD-ALD/HISTORY.']
    (ROOT/'Card-ALD/README.txt').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    write(NOTES/'Universal card diagrams publication.json',{'schema':'universal-card-diagrams-publication-v1','published_utc':stamp,
          'cards':cards,'canonical_drawings':4,'numbered_variants':sum(c['variant_count'] for c in cards),
          'published_files':published,'independent_reviews_passed':True,
          'geometry_identical_across_each_variant_series':True,'source_locations':'Universal/Source locations.json'})
    print(json.dumps({'canonical_drawings':4,'numbered_variants':sum(c['variant_count'] for c in cards),
                      'variants_by_card':{c['card_type']:c['variant_count'] for c in cards},'preserved_source_records':len(metadata)}))


if __name__ == '__main__':
    main()
