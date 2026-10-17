"""Freeze the three complete independent peer files and their evidence inputs."""
from pathlib import Path
import hashlib, json

BASE = Path(__file__).resolve().parent

def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))

def main():
    target = BASE / 'Final reviewed selection v2.json'
    assert not target.exists(), 'Final selection already frozen'
    locations = [
        ('Group 1 independent review/Peer-reviewed findings.json',
         'Group 1 independent review/Independent peer acceptance.json'),
        ('Group 2 review/Peer-reviewed findings v2.json',
         'Group 2 peer review/Independent peer review v2.json'),
        ('Group 3 review/Group3 Peer-reviewed findings.json',
         'Group 3 review/Independent peer review/Independent review.json'),
    ]
    expected_original = [
        '5c841862cf5964e49688ef28e7920ea1766723977ff7979da198788f86460a2b',
        '9b0757a45c96b424673786b68443067614fe073e3d046bbb8626bd9dd0dd4124',
        '1f4cd3118b91d42175172773f076b112e6738ac7bb7a61844d7ce7f22f8dc6d4',
    ]
    groups, evidence = [], {}
    for g, ((filename, reportname), expected) in enumerate(zip(locations, expected_original), 1):
        frozen = BASE / f'Group {g} review/Findings.json'
        assert bind(frozen)['sha256'] == expected, 'Frozen initial findings changed'
        final = BASE / filename
        report = BASE / reportname
        peer = read(report)
        assert peer.get('passed') is True or (peer.get('checks_passed', 0) > 0
                                             and peer.get('failure_count', 0) == 0)
        assert not peer.get('failures') and not peer.get('blocking_issues')
        final_binding = bind(final)
        peer_final_links = [peer.get(k) for k in ('peer_reviewed_findings', 'complete_peer_findings', 'peer_findings')]
        assert final_binding in peer_final_links, 'Peer report binds a different final file'
        final_doc = read(final)
        assert len(final_doc.get('cases', final_doc.get('findings', []))) == (209 if g == 3 else 210)
        groups.append({'group': g, 'findings': bind(final), 'evidence': [bind(report), bind(frozen)]})
        # Include current/frozen case crops and source-bound witness files named
        # by the peer reports. TIFFs stay in the original read-only archive.
        for path in report.parent.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.json', '.py', '.png', '.csv'}:
                evidence[path.resolve()] = bind(path)
        for doc in [read(frozen), final_doc]:
            for case in doc.get('cases', doc.get('findings', [])):
                for key in ['native_crop', 'source_crop']:
                    link = case.get(key)
                    if isinstance(link, dict) and link.get('path'):
                        actual = bind(link['path'])
                        assert actual['sha256'] == link['sha256'], 'Changed native case crop'
                        evidence[Path(actual['path'])] = actual
    for path in BASE.glob('*'):
        if path.is_file() and path.suffix.lower() in {'.json', '.py'}:
            evidence[path.resolve()] = bind(path)
    result = {'schema': 'pin-letter-final-peer-selection-v1', 'complete': True,
              'source_changes_applied': False, 'groups': groups,
              'scope': 'All629 flagged contacts were inspected. Only independently settled corrections enter the stage; held source and context cases remain unchanged.',
              'evidence': list(evidence.values())}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'selection': bind(target), 'evidence_files': len(evidence)}))

if __name__ == '__main__':
    main()
