"""Stream compact functional-v4 graph records without importing the renderer."""
import argparse
import hashlib
import json
from pathlib import Path

from v4_view import QUALIFIED_RENDERER_SHA256, input_source_reference, load, strict_json

BATCH_SCHEMA = 'aldbrowser-v4-graph-batch-v1'
DESCRIPTOR_SCHEMA = 'aldbrowser-v4-graph-descriptor-v1'
COMPLETE_SCHEMA = 'aldbrowser-v4-graph-complete-v1'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_path(path):
    # Resolve the sidecar using the same restrictions as v4_view.load.
    data = strict_json(path.read_text('utf-8'))
    ref = data.get('review', {}).get('details')
    if ref is None:
        return None
    if not isinstance(ref, str) or not ref or '\\' in ref or ':' in ref or any(x in ('', '..', '.') for x in ref.split('/')):
        raise ValueError('Unsafe review details reference')
    target = (path.parent / ref).resolve(strict=True)
    if not target.is_relative_to(path.parent):
        raise ValueError('Review details escape page directory')
    return target


def validate_graph_fields(data):
    if not isinstance(data['page'].get('page'), str):
        raise ValueError('Invalid functional graph page identity')
    for kind in ('inputs', 'outputs', 'nets'):
        for record in data[kind]:
            if not isinstance(record, dict) or not isinstance(record.get('net number'), str):
                raise ValueError('Invalid functional graph ' + kind + ' net identity')
    output_numbers = [out['net number'] for out in data['outputs']]
    if len(set(output_numbers)) != len(output_numbers):
        raise ValueError('Duplicate explicit output net record')
    for inp in data['inputs']:
        if not isinstance(inp.get('real net number', inp['net number']), str):
            raise ValueError('Invalid functional graph input source reference')
    for net in data['nets']:
        if not isinstance(net.get('nodes'), list) or any(not isinstance(node, str) for node in net['nodes']):
            raise ValueError('Invalid functional graph net nodes')


def descriptor(item, generation):
    path = Path(item['path']).resolve(strict=True)
    model_hash = sha256(path)
    sidecar = review_path(path)
    review_hash = sha256(sidecar) if sidecar is not None else None
    if model_hash != item['modelSha256'] or review_hash != item['reviewSha256']:
        raise ValueError('Functional graph source fingerprint changed')
    data, details = load(path)
    validate_graph_fields(data)
    options = (details or {}).get('writer options', {})
    if not isinstance(options, dict):
        raise ValueError('Invalid writer options')
    if options.get('line ending', 'LF') not in ('LF', 'CRLF') or type(options.get('trim trailing spaces', False)) is not bool:
        raise ValueError('Invalid writer options')
    inputs = {i['net number']: i for i in data['inputs']}
    nets = []
    for net in data['nets']:
        number = net['net number']
        source_refs = []
        for identity, inp in inputs.items():
            if 'inputs/' + identity in net['nodes']:
                source_refs.append(input_source_reference(inp))
        nets.append({'id': number, 'label': number, 'sourceReferences': list(dict.fromkeys(source_refs))})
    result = {'schema': DESCRIPTOR_SCHEMA, 'generation': generation, 'id': item['id'],
              'modelSha256': model_hash, 'reviewSha256': review_hash, 'page': data['page']['page'],
              'outputs': [out['net number'] for out in data['outputs']], 'nets': nets}
    if sha256(path) != model_hash or review_path(path) != sidecar or (sha256(sidecar) if sidecar is not None else None) != review_hash:
        raise ValueError('Functional graph source changed during extraction')
    return result


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    parser.add_argument('renderer')
    args = parser.parse_args()
    renderer = Path(args.renderer).resolve(strict=True)
    if sha256(renderer) != QUALIFIED_RENDERER_SHA256:
        raise ValueError('Renderer semantics differ from the qualified browser geometry adapter; review required')
    batch = strict_json(Path(args.manifest).read_text('utf-8'))
    if not isinstance(batch, dict) or batch.get('schema') != BATCH_SCHEMA or not isinstance(batch.get('generation'), str) or not isinstance(batch.get('pages'), list):
        raise ValueError('Invalid functional graph batch')
    seen = set()
    for item in batch['pages']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in seen:
            raise ValueError('Invalid or repeated functional graph page identity')
        seen.add(item['id'])
        emit(descriptor(item, batch['generation']))
    if sha256(renderer) != QUALIFIED_RENDERER_SHA256:
        raise ValueError('Qualified renderer changed during graph extraction')
    emit({'schema': COMPLETE_SCHEMA, 'generation': batch['generation'], 'count': len(seen)})


if __name__ == '__main__':
    main()
