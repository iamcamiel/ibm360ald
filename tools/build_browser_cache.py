#!/usr/bin/env python3
"""Build the complete static browser cache after pulling source updates."""
import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

from browser_cache.publication import BuildError, Publication, Snapshot, digest, no_symlinks


def build(source_root, output=None):
    root = no_symlinks(source_root).resolve(strict=True)
    output = Path(output) if output is not None else root / 'cache'
    if Path(__file__).resolve().is_relative_to(output.resolve()):
        raise BuildError('Output cannot contain the builder code')
    with Publication(root, output) as publication:
        snapshot = Snapshot(root)
        # Installed builder code is part of the same source snapshot. No source
        # verification or rendering is required when serving the finished cache.
        tools = Path(__file__).resolve().parent
        snapshot.read_code(tools / 'build_browser_cache.py', '@builder/build_browser_cache.py')
        snapshot.track_code_directory(tools / 'browser_cache', '@builder/browser_cache')
        for path in sorted((tools / 'browser_cache').glob('*.py')):
            snapshot.read_code(path, '@builder/browser_cache/' + path.name)
        from browser_cache.catalogue import collect
        from browser_cache.interactions import enrich_interactions
        catalogue, models, texts, views = collect(root, snapshot, publication.put_asset)
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
        return {'pageCount': len(catalogue['pages']), 'catalogueChanged': changed,
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
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
