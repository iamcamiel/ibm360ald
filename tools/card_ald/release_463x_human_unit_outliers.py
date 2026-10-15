"""Apply the four 463x circuit identifiers corrected from physical pages."""

from argparse import ArgumentParser

import release_463x_unit_function_batch as batch


batch.STAGE = batch.WORKSPACE / "tmp/ald-text/ald/card-463x-release/human-unit-outliers-stage"
batch.AUDIT = (batch.WORKSPACE / "tmp/ald-text/ald/manual-verification/"
               "contextual-cross-reference-v3/463x human unit outliers current audit.json")
batch.REPO_AUDIT = batch.REPO / "notes/Card-ALD/463x human unit outliers current audit.json"
batch.CHANGES = [
    ("AP321", "BG", "unit", "U55PC", "U55AC", "HUMAN"),
    ("AP531", "BG", "unit", "U55PC", "U55AC", "HUMAN"),
    ("AP121", "AA", "unit", "U61AF", "U61AE", "HUMAN"),
    ("AP131", "AJ", "unit", "U61AF", "U61AE", "HUMAN"),
]


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    batch.stage() if parser.parse_args().action == "stage" else batch.publish()
