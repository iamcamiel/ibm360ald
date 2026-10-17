"""Reuse the guarded uniform refresh with a new, explicit evidence destination.

The original refresh helper and its historical bindings remain unchanged.
Only the derived dataset's source-epoch binding needs refreshing after ALD
publication; the socket TXT data and logical record counts stay unchanged.
"""
from pathlib import Path
import argparse, importlib.util, json

ROOT = Path('D:/Github/IBM360')
REPO = ROOT / 'ibm360ald'
HELPER = ROOT / 'tmp/ald-text/ald/socket-ald-audit/refresh_final_uniform.py'
spec = importlib.util.spec_from_file_location('guarded_uniform_refresh', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proof-directory', type=Path, required=True)
    p = sub.add_parser('publish')
    p.add_argument('manifest', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        proof = args.proof_directory.resolve()
        helper.need(proof.is_relative_to(REPO / 'notes/Reference data/Uniform socket listings')
                    and not proof.exists(), 'Use a new uniform refresh proof directory')
        helper.PROOF = proof
        result = helper.prepare(args.output)
        manifest = Path(result['manifest']['path'])
        doc = helper.read(manifest)
        doc['inputs'].append(helper.bind(Path(__file__)))
        doc['refresh_driver'] = helper.bind(Path(__file__))
        helper.atomic(manifest, helper.enc(doc))
        result['manifest'] = helper.bind(manifest)
    else:
        doc = helper.read(args.manifest)
        helper.checked(doc['refresh_driver'])
        helper.need(doc['refresh_driver'] == helper.bind(Path(__file__)), 'Refresh driver changed')
        proof = Path(doc['portable_proof_target']).resolve()
        helper.need(proof.is_relative_to(REPO / 'notes/Reference data/Uniform socket listings'),
                    'Proof destination escapes approved notes directory')
        helper.PROOF = proof
        result = helper.publish(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
