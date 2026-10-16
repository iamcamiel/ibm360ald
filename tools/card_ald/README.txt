CURRENT CARD DIAGRAM TOOLS

From the ibm360ald repository directory:

    python tools/card_ald/generate_card.py 4191

This generates the canonical Card-ALD/4191.txt and every reviewed numbered
notation variant. It also updates generation receipts, the current card model
and the searchable variant index. Existing read-only file flags are preserved.

Currently reviewed definitions: 0141, 4191, 4633 and 4634.
Use all four digits, including the leading zero in 0141.

BUILD DATA FROM THE TRANSCRIPTION DATABASE

    python tools/card_ald/build_card_data.py 4633

This reads the current occurrence database, hash-bound page models, socket
listings and explicit reviewed supplements. It writes candidate renderer JSON
and a separate evidence/uncertainty report under the workspace directory
tmp/ald-text/ald/card-data/4633. Add --render to make private TXT candidates too.
It never replaces published diagrams or changes the original transcriptions.
The existing reviewed layout data reproduces all current notation variants.
For other database card types, unknown circuits, missing portions and uncertain
connections remain explicit review items; a failed layout is not certified.

CHECK ALL RECORDED USES AGAINST THE COMMON CARD

    python tools/card_ald/audit_card_uses.py 4633

This audits every current recorded occurrence and its modeled internal links.
JSON, CSV and readable reports go to tmp/ald-text/ald/card-use-audit/4633.
Use --definition PATH to compare against a private candidate instead of the
current reviewed common definition. Reports distinguish disagreements,
uncertain print, equivalent symbols, recorded variants and known corrections.
Technical model-mapping gaps are listed separately as coverage limitations.
Omitted unused inputs are allowed. A flag is not a confirmed transcription
error, and the auditor never edits source pages.

TRY SMARTER GRAPH PLACEMENT AND ROUTING

    python -m pip install -r tools/card_ald/requirements.txt
    python tools/card_ald/build_card_data.py 4633 --relayout --render

NetworkX plans dependency layers, sibling groups, feedback and shared drivers.
The grid router minimizes crossings and bends while preserving the exact
reviewed terminal connections and semantic port identities. Boxes are seven
characters high, extended only for additional inputs. New placements may start
on any line; a horizontal wire can pass directly between boxes. Vertical wires
still leave two cells beside boxes/pin labels and one between parallel tracks.
All variants use the same new geometry. Reports include routing alternatives
and actual crossing, bend and wire-length metrics. Candidates stay private.
Exterior labels may move to match their routed wire. Generic leaf-wire trials
also consider passing below intervening boxes, keeping a change only when it
improves crossings or wire length. These rules contain no card, portion or pin
specific exceptions.
Shared forward fanout nets also try one horizontal trunk above or below the
receiving boxes, with short branches to their inputs. The same measured
crossing, bend and length comparison chooses between both directions and the
existing route; every terminal connection is preserved.
Convergent gate groups keep their own collector centered alongside them, with
related output buffers nearby. Separate collectors are not flattened into one
sibling group merely because they feed a common downstream gate.
Interchangeable A/OR input slots may be reordered to reduce crossings. Each
semantic input keeps its pin, net and canonical/variant decorations when it
moves. Exterior pin labels are ordered by their routed approaches; exact
routing-score ties prefer alignment with gate terminals.
Compatible fanout trees also try one vertical trunk with horizontal branches,
including internal nets, shared inputs and exposed output contacts. All other
net layers stay fixed. A change must improve crossings, bends or wire length.

PREVIEW SHORT SHARED-NET R TERMINATIONS

    python tools/card_ald/compact_terminations.py 4191 --output-dir PATH

This writes private definitions and all numbered TXT variants. It leaves the
published diagram untouched. By default it starts from an already accepted
free-row layout, or upgrades a seven-row layout using the current graph
planner, then applies short R notation. This preserves earlier approved
placement and routing improvements. Use --relayout to force a fresh plan;
--keep-layout deliberately retains published positions even on an older grid.
Relayout failures stop the command; they never trigger an older-grid fallback.
A single-input R with another block on its net
hangs directly below that net as FUNCTION CIRCUIT PORTION, without pin labels.
A standalone R keeps its full ALD box. The complete pin and portion metadata
remain in JSON. At least three extra text cells, and enough for every known
variant, are reserved beside the short label. Variant geometry stays fixed.
An input triangle is retained at the hanging endpoint in decorated variants.
The four-card preview set is under notes/Card-ALD/Previews/Compact R.
The approved four-card set is published in Card-ALD, including its compact R
metadata. Default data builds preserve that metadata; another compact-preview
pass retains already compact terminations.

PUBLISH INDEPENDENTLY REVIEWED LAYOUTS

    python tools/card_ald/adopt_card_layout.py 4191 --definition PATH --review RECEIPT
    python tools/card_ald/adopt_card_layout.py 0141 4191 4633 4634 --definitions ROOT --review RECEIPT

The batch form accepts ROOT/CARD.json or ROOT/CARD/CARD.json. All source-bound
review hashes are checked before canonical files change. Each card must retain
its circuit, semantic port identities, notation variants and power contacts.
Every candidate passes the default builder and renderer privately first.
Predecessors and the accepted review are preserved in uniquely named history
and acceptance directories. A failed publication restores previous files.

Use --output-dir PATH with either builder or auditor to choose another private
destination. NetworkX is needed for graph relayout, not for the shared text
renderer or the source-use auditor.

For a private build without changing published diagrams or their records:

    python tools/card_ald/generate_card.py 0141 --output-dir PATH

To validate a definition without writing files:

    python tools/card_ald/generate_card.py 4634 --check

DATA AND CODE

The shared renderer uses the Python standard library only. It reads
json/Card-ALD/definitions/NNNN.json. Each definition contains semantic boxes,
ports, circuit identifiers, canonical functions, notation alternatives, exterior
and power contacts, routed wire geometry and reviewed terminal connectivity.
It has no imports of the older per-card builders and requires no temporary
workspace, source TIFFs, PDF files or installed fonts to render UTF-8 text.

A new reviewed card definition can use this same renderer without Python
changes. The data builder derives candidates from database evidence; a part
number alone cannot establish a complete, proven universal card circuit.

Validation checks every wire connection, distinguishes crossings from joined
diamonds, checks pin coverage, keeps variants on the canonical geometry and
enforces the two-cell box/pin clearance and one-cell parallel-wire clearance.
Unlisted older numbered output files cause a refusal so obsolete variants
cannot silently remain mixed with the current family.

SHARED HEADINGS

Every current card and numbered variant uses generate_card.header_lines for
the same seven heading rows. JSON header metadata holds the full part number,
card width and any provisional portion/circuit forms. The builder refreshes
reviewed occurrence/page counts from current source evidence. Portion/contact
counts, power groups and possibly unused contacts come from the actual card
definition. Variant identity comes from the notation variant number.
Literal heading annotations and variant-specific heading text are rejected
when structured header metadata is present. Historical definitions without
that metadata retain their original annotations for reproducible archives.
The heading change preserves every diagram row and all routing coordinates.

SOURCE AND HISTORICAL TOOLS

import_reviewed_layout.py was the one-time importer for the accepted drawings.
It is not part of normal generation. Historical per-card build, extraction,
review and publication tools remain as evidence of earlier work; they are not
the current generation entry point. Current reviewed layout changes belong in
the JSON definitions and are rendered with generate_card.py.

Original source acceptance and variant witnesses remain under
notes/Card-ALD/Universal. Current generation receipts are under
notes/Card-ALD/Generation. Earlier publication records are preserved under
notes/Card-ALD/history/Before shared generator.
