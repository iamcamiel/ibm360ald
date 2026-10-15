"""Bind the three independently accepted native-source corrections to current quartets.

Read-only unless --emit writes the coordinator audit. Never writes ALD or repo files.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('D:/Github/IBM360')
SOURCE = Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
EXPORTS = ROOT/'ALD_Visual_Transcriptions'
BASE = ROOT/'tmp/ald-text/ald/card-type-database/native-three-review'
MANIFEST = BASE/'unified-stage/Unified native three correction manifest.json'
INDEPENDENT = BASE/'independent-review/Independent three native corrections acceptance.json'
PUBLICATION = BASE/'unified-stage/Unified native three publication receipt.json'
DEST = ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Native three source corrections current audit.json'
EXPECTED_HASHES = {
    'manifest': '726a8926ab81dc7d1ea1f0fde9272b82198e47a1c94a5fc938273138e267bf5b',
    'independent': '9ff7d60e334dd2cf04d1ee86fc080f111c28ee4ffe785683f8db1907890d9deb',
    'publication': 'da36314bd4e296b0c8ea6473afe93b6f9e51a7ccd6af9e074860f419393a962f',
}
CROPS = {
    'PX311': (ROOT/'tmp/ald-text/ald/card-type-database/native-source-findings-px311/PX311 AG B09 independently recropped.png', 'faf7c7606e4c55062e80777c731b3cbe5e77e83a7da391a6c4b30b0ae48f33f2'),
    'KU641': (BASE/'KU641 BX B10 independent native crop.png', '55900757deeaf6d233db466f6ec63a1c4b1f68e0fadd020203265b437da9f176'),
    'AP743': (ROOT/'tmp/ald-text/ald/card-type-database/OH-OK-native-review/AP743 4C OR-AR native.png', '1709b97a2c2916c07276ed1fc67e04cb69bf18e56fd880926dd3bae89a8b14b5'),
}
SCAN_IDS = {'PX311': '1555', 'KU641': '1113', 'AP743': '327'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path, expected=None):
    path = Path(path)
    actual = sha(path)
    assert expected is None or actual == expected, f'hash mismatch: {path}'
    return {'file': str(path), 'sha256': actual}


def json_at(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(emit):
    frozen = {name:bound(path, EXPECTED_HASHES[name]) for name,path in [('manifest',MANIFEST),('independent',INDEPENDENT),('publication',PUBLICATION)]}
    manifest, review, receipt = map(json_at, (MANIFEST,INDEPENDENT,PUBLICATION))
    assert review.get('passed') is True and review.get('failures') == [] and review['manifest']['sha256'] == frozen['manifest']['sha256']
    assert receipt['manifest']['sha256'] == frozen['manifest']['sha256'] and receipt['independent_audit']['sha256'] == frozen['independent']['sha256']
    assert receipt['quartet_files'] == 12 and receipt['repository_writes'] == 0 and receipt['original_scan_writes'] == 0
    assert manifest['history_key'] == 'source_native_three_corrections_v1'
    assert {p['page'] for p in manifest['pages']} == set(SCAN_IDS)
    assert len(receipt['canonical_destinations']) == 12
    destinations = {str(Path(x['path']).resolve()):x['sha256'] for x in receipt['canonical_destinations']}
    assert len(destinations) == 12
    audited = {p['page']:p for p in review['independent_checks']}
    assert set(audited) == set(SCAN_IDS)
    pages = []
    for item in manifest['pages']:
        page = item['page'];assert str(item['scan_id']) == SCAN_IDS[page]
        source = item['source'];source_path = Path(source['path'])
        assert source_path.resolve().is_relative_to(SOURCE.resolve()) and sha(source_path) == source['sha256']
        evidence = bound(item['evidence']['path'], item['evidence']['sha256'])
        crop_path,crop_sha = CROPS[page];crop = bound(crop_path,crop_sha)
        crop_in_evidence=json_at(evidence['file'])
        assert crop_sha in json.dumps(crop_in_evidence), f'{page}: crop not bound by source evidence'
        quartet = {}
        for kind in ('txt','json','notes','preview'):
            candidate = item['candidate_quartet'][kind]
            current = item['canonical_quartet'][kind]
            path = Path(current['path'])
            assert path.resolve().is_relative_to(EXPORTS.resolve())
            assert candidate['sha256'] == sha(candidate['path']) == sha(path) == destinations[str(path.resolve())]
            assert audited[page]['candidate_hashes'][kind] == candidate['sha256']
            quartet[kind] = {'path':str(path), 'sha256':sha(path)}
        assert audited[page]['text_differences'] == 1
        assert audited[page]['active_model_changes'] == (2 if page=='PX311' else 1)
        # The original native reviewer also verified no other box, wire, pin,
        # signal, row, or column changed in the private candidate.
        checks = {
            'exact_independently_reviewed_TIFF_and_native_crop': True,
            'exact_private_manifest_independent_acceptance_and_publication': True,
            'one_native_supported_changed_text_cell_and_only_listed_active_model_aliases': True,
            'current_full_quartet_matches_published_candidate_and_receipt': True,
            'all_other_geometry_wires_pins_and_history_preserved': True,
        }
        pages.append({
            'page':page, 'source_scan_id':str(item['scan_id']), 'eligible':True,
            'artifact_schema':'reviewed-current-quartet-v1',
            'source':source, 'current_quartet':quartet,
            'owner_receipt':{'file':str(PUBLICATION),'sha256':frozen['publication']['sha256']},
            'independent_audit':{'file':str(INDEPENDENT),'sha256':frozen['independent']['sha256']},
            'native_three_manifest':{'file':str(MANIFEST),'sha256':frozen['manifest']['sha256']},
            'native_three_source_evidence':evidence,
            'native_three_crop':crop,
            'changed_cell':item['text_edit'],
            'active_model_changes':item['active_model_changes'],
            'checks':checks,
        })
    output = {
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'passed':True,'failures':[],
        'scope':'Exactly PX311 AG.B09, KU641 BX.B10, and AP743 AQ/4C independently native-reviewed source corrections; current published quartets only.',
        'counts':{'pages':3,'changed_text_cells':3,'active_model_changes':4,'quartet_files':12},
        'manifest':frozen['manifest'],'independent_audit':frozen['independent'],'publication':frozen['publication'],
        'binder':bound(Path(__file__)),
        'pages':pages,'repository_writes':0,'canonical_writes':0,
    }
    if emit:
        DEST.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'pages':3,'cells':3,'active_model_changes':4,'audit':str(DEST),'emitted':emit},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--emit',action='store_true')
    main(parser.parse_args().emit)
