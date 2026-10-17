CURRENT CARD-TYPE CATALOG
Rebuild with tools/references/build_current_card_catalog.py from the reviewed export and content-data manifests.
Verify with tools/references/verify_current_card_catalog.py.

All physical card listings come once from the current accepted uniform socket dataset,
with stable record IDs and exact source spans. Legacy table shapes are not read again.
Continuations retain their source evidence but do not add physical card instances.
Unprinted or unreadable card width stays unknown. Explicit annotation nodes are
reported separately; a numeric 0000 card is retained unless explicitly annotated.

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

This is the current derived catalogue. Superseded research snapshots and
intermediate review histories are not retained in the working repository.
