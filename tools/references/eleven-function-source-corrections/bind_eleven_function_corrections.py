"""Bind the eleven published function corrections to current canonical quartets.

Without --emit this is a read-only verification. It requires the frozen native
and direct-human candidate records, independent acceptance, and publication.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('D:/Github/IBM360')
ARCHIVE = Path('D:/Reference Materials/IBM 360/IBM_360_ALD').resolve()
CANONICAL = ROOT/'ALD_Visual_Transcriptions'
BASE = ROOT/'tmp/ald-text/ald/card-type-database/v13-next-review'
MANIFEST = BASE/'eleven-page-private-stage/Eleven native and human function correction manifest.json'
NATIVE = BASE/'V13 seven source-bound function correction candidates.json'
HUMAN = BASE/'V13 four direct-human function corrections and DT001 comparison.json'
INDEPENDENT = BASE/'Independent eleven native and human function corrections acceptance.json'
PUBLICATION = BASE/'eleven-page-private-stage/Eleven canonical publication receipt.json'
DEST = ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Eleven function corrections current audit.json'
FROZEN = {
    MANIFEST:'9bdeb975f0a457bdbd98e37d6bb162bba754f12074dc820d09b858be8f6c028f',
    NATIVE:'7f12522b6e83348a529646ff01c5f683a633b59c2f53af35e008c46c0ba42d52',
    HUMAN:'f7ac879f867147fd9553587e8ca99db293c5a3f3eb8ea00813cd1f2a4f41014f',
    INDEPENDENT:'aa8d69862b3e6a86179a2df96b7971d99faeb43b56ae3c2137607cb70628f81a',
    PUBLICATION:'dfc760aca5398e959faec09fbb74127d1ba8310bd51200b2e65e7fc278d22ec7',
}
NATIVE_PAGES={'AP737','AP181','RQ683','KU601','RQ781','MC371','AP441'}
HUMAN_PAGES={'AP531','XM181','AS201','AP313'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    path=Path(path).resolve()
    return {'file':str(path),'sha256':sha(path)}


def checked(record):
    path=Path(record.get('path',record.get('file',''))).resolve()
    assert path.is_file() and sha(path)==record['sha256'],str(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(emit):
    for path,expected in FROZEN.items():
        assert path.is_file() and sha(path)==expected,str(path)
    m,n,h,a,r=map(load,(MANIFEST,NATIVE,HUMAN,INDEPENDENT,PUBLICATION))
    assert m['schema']=='source-native-and-human-eleven-function-private-stage-v1'
    assert m['history_key']=='source_eleven_function_corrections_v1'
    assert m['native_candidate_record']['sha256']==FROZEN[NATIVE]
    assert m['human_candidate_record']['sha256']==FROZEN[HUMAN]
    assert m['direct_human_authority']==h['direct_human_authority']
    assert m['confirmed_no_change']==h['confirmed_no_change'] and h['confirmed_no_change']['page']=='DT001'
    assert a['passed'] is True and a['failures']==[] and a['visual_review_pending'] is False
    assert a['manifest']['sha256']==r['manifest']['sha256']==FROZEN[MANIFEST]
    assert r['independent_audit']['sha256']==FROZEN[INDEPENDENT]
    assert r['pages']==11 and r['canonical_quartet_files']==44
    assert r['repository_writes']==r['original_scan_writes']==0
    assert {p['page'] for p in m['pages']}==NATIVE_PAGES|HUMAN_PAGES
    assert {p['page'] for p in n['proposed_corrections']}==NATIVE_PAGES
    assert {p['page'] for p in h['proposed_corrections']}==HUMAN_PAGES
    audited={p['page']:p for p in a['reviewed_pages']}
    assert set(audited)==NATIVE_PAGES|HUMAN_PAGES
    destinations={str(Path(x['path']).resolve()):x['sha256'] for x in r['canonical_destinations']}
    assert len(destinations)==44
    pages=[]
    for item in m['pages']:
        page=item['page'];review=audited[page]
        kind='native' if page in NATIVE_PAGES else 'direct-human'
        assert item['authority_kind']==review['authority_kind']==kind
        assert item['source']==review['source'] and item['source_crop']==review['source_crop']
        assert item['text_edit']==review['text_edit'] and item['active_model_changes']==review['active_model_changes']
        assert review['broad_crop_pixel_exact'] is True
        source=checked(item['source']);assert source.is_relative_to(ARCHIVE)
        crop=checked(item['source_crop']);broad=checked(item['broad_context_crop'])
        authority=checked(item['authority_record'])
        assert authority== (NATIVE if kind=='native' else HUMAN).resolve()
        quartet={}
        for part in ('txt','json','notes','preview'):
            target=Path(item['canonical_quartet'][part]['path']).resolve()
            candidate=checked(item['candidate_quartet'][part])
            checked(item['before_quartet'][part])
            assert target.is_relative_to(CANONICAL.resolve()) and target.name==candidate.name
            assert sha(target)==sha(candidate)==destinations[str(target)]
            quartet[part]={'path':str(target),'sha256':sha(target)}
        assert review['candidate_text_sha256']==quartet['txt']['sha256']
        assert review['candidate_model_sha256']==quartet['json']['sha256']
        checks={
            'exact_TIFF_and_native_crops_bound':True,
            'exact_independent_acceptance_and_publication_bound':True,
            'native_or_direct_human_authority_distinguished':True,
            'only_listed_text_and_active_model_edits':True,
            'current_full_quartet_matches_published_candidate':True,
            'predecessor_quartet_preserved':True,
        }
        pages.append({
            'page':page,'source_scan_id':str(item['scan_id']),'eligible':True,
            'artifact_schema':'reviewed-current-quartet-v1','authority_kind':kind,
            'source':item['source'],'current_quartet':quartet,
            'owner_receipt':binding(PUBLICATION),'independent_audit':binding(INDEPENDENT),
            'eleven_manifest':binding(MANIFEST),
            'eleven_authority_record':binding(authority),
            'eleven_source_crop':binding(crop),
            'eleven_broad_context_crop':binding(broad),
            'changed_cell':item['text_edit'],'active_model_changes':item['active_model_changes'],
            'checks':checks,
        })
    output={
        'schema':'eleven-current-source-bound-function-acceptance-v1',
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'passed':True,'failures':[],
        'scope':'Exactly seven independently native-read and four direct-human-confirmed function corrections; DT001 remains unchanged.',
        'counts':{'pages':11,'native_pages':7,'direct_human_pages':4,'changed_text_spans':11,
                  'active_model_changes':12,'quartet_files':44},
        'manifest':binding(MANIFEST),'native_candidate_record':binding(NATIVE),
        'human_candidate_record':binding(HUMAN),'independent_audit':binding(INDEPENDENT),
        'publication':binding(PUBLICATION),'binder':binding(Path(__file__)),
        'confirmed_no_change':h['confirmed_no_change'],
        'matching_OR_example':h['matching_OR_example_for_DT001'],
        'pages':pages,'repository_writes':0,'canonical_writes':0,
    }
    if emit:DEST.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'pages':11,'audit':str(DEST),'emitted':emit},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--emit',action='store_true')
    main(parser.parse_args().emit)
