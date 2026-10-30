#!/usr/bin/env python3
"""Build the complete static browser cache after pulling source updates."""
import sys
sys.dont_write_bytecode = True

import argparse
from collections import Counter
import json
from pathlib import Path

from browser_cache.publication import BuildError, Publication, Snapshot, digest, no_symlinks


def has_findings(review, details):
    """Count current findings, including discrepancies absent from uncertainty counts."""
    def open_entries(entries):
        if not entries:
            return False
        if not isinstance(entries, list):
            return True
        return any(not isinstance(item, dict) or item.get('status') != 'resolved'
                   for item in entries)

    if review.get('unresolved discrepancies') is True:
        return True
    if open_entries(details.get('uncertainties', [])) or open_entries(details.get('format questions', [])):
        return True
    comparison = details.get('render comparison') or {}
    if not isinstance(comparison, dict):
        return True
    different = comparison.get('unresolved different cells', comparison.get('different cells', 0))
    if (comparison.get('rendered') is False
            or type(different) is not int or different > 0
            or open_entries(comparison.get('wiring findings', []))):
        return True
    issues = details.get('publication issues')
    return bool(issues and (not isinstance(issues, dict)
                           or issues.get('status') not in ('resolved', 'closed', 'clear', 'none')))


def read_review(entry, root, snapshot):
    from browser_cache.catalogue import bind_review, strict_json

    model_path = root / entry['_model']
    model = strict_json(snapshot.read(model_path))
    review = model.get('review') or {}
    reference = review.get('details')
    if reference is None:
        return review, {}
    # Reuse the collector's path validation and bind statistics to the same review.
    review_sha = bind_review(snapshot, model_path, reference)
    if review_sha != entry['_reviewSignature'][1]:
        raise BuildError('Review changed while collecting page statistics')
    return review, strict_json(snapshot.read(model_path.parent / reference))


def page_statistics(pages, review_reader):
    kinds = Counter(entry['type'] for entry in pages)
    v3 = clean = findings = 0
    for entry in pages:
        if entry['type'] != 'ald':
            continue
        if entry.get('format') != 'v4':
            v3 += 1
        elif has_findings(*review_reader(entry)):
            findings += 1
        else:
            clean += 1
    return {'pageCount': len(pages), 'pagesByKind': dict(sorted(kinds.items())),
            'aldV3PageCount': v3, 'aldV4WithoutFindingsPageCount': clean,
            'aldV4WithFindingsPageCount': findings}


def print_statistics(result, stream=None):
    stream = sys.stderr if stream is None else stream
    print('\nBrowser cache statistics:', file=stream)
    print(f"  Total pages: {result['pageCount']:,}", file=stream)
    print('  Pages per kind:', file=stream)
    for kind, count in result['pagesByKind'].items():
        print(f'    {kind}: {count:,}', file=stream)
    print('  ALD pages (kind ald):', file=stream)
    print(f"    V3: {result['aldV3PageCount']:,}", file=stream)
    print(f"    V4 without findings: {result['aldV4WithoutFindingsPageCount']:,}", file=stream)
    print(f"    V4 with findings: {result['aldV4WithFindingsPageCount']:,}", file=stream)


def build(source_root, output=None):
    root = no_symlinks(source_root).resolve(strict=True)
    output = Path(output) if output is not None else root / 'cache'
    if Path(__file__).resolve().is_relative_to(output.resolve()):
        raise BuildError('Output cannot contain the builder code')
    with Publication(root, output) as publication:
        from render_all_json import run as render_all
        rendering = render_all(root)
        if rendering['failures']:
            raise BuildError('JSON rendering failed: ' + json.dumps(rendering['failures']))
        snapshot = Snapshot(root)
        # Installed builder code is part of the same source snapshot. No source
        # verification or rendering is required when serving the finished cache.
        tools = Path(__file__).resolve().parent
        snapshot.read_code(tools / 'build_browser_cache.py', '@builder/build_browser_cache.py')
        for name in ('render_all_json.py', 'page_maintenance.py', 'ald_render.py'):
            snapshot.read_code(tools / name, '@builder/' + name)
        for folder in ('normalization', 'page_text'):
            snapshot.track_code_directory(tools / folder, '@builder/' + folder)
            for path in sorted((tools / folder).glob('*.py')):
                snapshot.read_code(path, '@builder/' + folder + '/' + path.name)
        snapshot.track_code_directory(tools / 'browser_cache', '@builder/browser_cache')
        for path in sorted((tools / 'browser_cache').glob('*.py')):
            snapshot.read_code(path, '@builder/browser_cache/' + path.name)
        from browser_cache.catalogue import collect
        from browser_cache.interactions import enrich_interactions
        catalogue, models, texts, views = collect(root, snapshot, publication.put_asset)
        statistics = page_statistics(catalogue['pages'],
                                     lambda entry: read_review(entry, root, snapshot))
        outputs = catalogue.pop('_nativeOutputsById', {})
        interaction_assets = enrich_interactions(catalogue['pages'], models, texts, views,
                                                 native_outputs_by_id=outputs)
        for entry in catalogue['pages']:
            old_url = entry.get('interactionURL')
            if old_url not in interaction_assets:
                raise BuildError('Missing static interaction payload: ' + entry['id'])
            data = interaction_assets[old_url]
            entry['interactionURL'] = publication.put_asset(data, '.json')
            entry['interactionSha256'] = digest(data)
            for key in list(entry):
                if key.startswith('_') or key == 'entryURL':
                    del entry[key]
        catalogue['signature'] = snapshot.signature()
        catalogue['revision'] = catalogue['signature']
        catalogue['delivery'] = 'static-cache-v1'
        changed, sha = publication.publish(catalogue, snapshot)
        return {**statistics, 'renderedPages': sum(rendering['rendered'].values()),
                'textFilesRegenerated': rendering['textFilesChanged'], 'catalogueChanged': changed,
                'assetsWritten': publication.written, 'catalogueSha256': sha,
                'output': str(publication.output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = build(args.source_root, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'Cache build failed: ' + str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    print_statistics(result)


if __name__ == '__main__':
    main()
