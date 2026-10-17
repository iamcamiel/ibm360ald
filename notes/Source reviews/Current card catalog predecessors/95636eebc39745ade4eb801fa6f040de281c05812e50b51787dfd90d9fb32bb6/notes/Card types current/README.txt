CURRENT CARD-TYPE CATALOG
Rebuild with tools/references/build_current_card_catalog.py from the reviewed export and content-data manifests.
Verify with tools/references/verify_current_card_catalog.py.

json/Card types current/<number>.json contains each observed portion, its exact function label,
primary function, circuit identifier, visible pins, polarity triangles, A1 listing facts,
and source text/model pointers. csv/Card types current contains searchable summaries.
The shape counts describe only visible ports; some inputs are intentionally unused or omitted.
A physical pin label is syntactically valid only when it uses B/D (single card) or B/D/G/J
(double card) and a number from 02 through 13. Apparent exceptions remain literal in
the observations for source review. Labels that cannot be parsed as physical pins are
marked unparsed rather than automatically called invalid. Non-numeric card labels,
including structural blocks
and damaged readings, are listed in Unclassified card identifiers.json.

The older json/Card types directory is the historical V15 research snapshot. Its
acceptance receipts are immutable; this current catalog is a separate derived view.
