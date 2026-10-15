"""Recover five masked 4634 identifiers using visible glyphs and peers."""

from argparse import ArgumentParser
import release_463x_unit_function_batch as batch

batch.STAGE = batch.WORKSPACE / "tmp/ald-text/ald/card-463x-release/masked-unit-stage"
batch.AUDIT = batch.WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4634 masked unit current audit.json"
batch.REPO_AUDIT = batch.REPO / "notes/Card-ALD/4634 masked unit current audit.json"
batch.CHANGES = [
    ("AP361", "AA", "unit", "��1AE", "U61AE", "CONTEXT"),
    ("AP441", "AA", "unit", "U��AE", "U61AE", "CONTEXT"),
    ("AP451", "AA", "unit", "U��AE", "U61AE", "CONTEXT"),
    ("AP231", "AN", "unit", "U�3AM", "U03AM", "CONTEXT"),
    ("AP271", "AM", "unit", "U03�L", "U03AL", "CONTEXT"),
]

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    batch.stage() if parser.parse_args().action == "stage" else batch.publish()
