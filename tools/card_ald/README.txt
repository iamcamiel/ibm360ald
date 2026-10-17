CURRENT CARD DIAGRAM TOOLS

BATCH THE THREE UNIVERSAL TOOLS

    python tools/card_ald/run_card_batch.py --prefix 0 --output-dir PATH

Run this after source corrections and a verified current-catalog rebuild.
It selects every four-digit catalog card matching the prefix and attempts the
data builder, source-use auditor and renderer for each one. Candidates, tool
logs and a searchable Batch summary.csv stay in the new private output folder.
Missing definitions and other failures remain explicit; subsequent cards still
run. Changed source-epoch bindings stop the batch. This command does not publish
unreviewed pinouts or modify the ALD transcriptions. Existing reviewed layout
supplements retain their placement; new families use the current generic graph
planner with free vertical placement.

The three card tools share one in-process source reader and cache. The catalogue
verifier remains independent. --subprocess provides isolated tool execution for
comparison. A final source-byte check covers the complete accepted page set.
Explicit direct-human exclusions are recorded in notes/Card-ALD/Scope
exclusions.json; 1457 and 1724 are excluded because their only listed use is on
missing RT011. Excluded catalogue records remain present and batch reports list
the exclusions. Component-form authority and its notes are epoch-bound inputs.

From the ibm360ald repository directory:

    python tools/card_ald/generate_card.py 4191

This generates the canonical Card-ALD/4191.txt and every reviewed numbered
notation variant. It also updates generation receipts, the current card model
and the searchable variant index. Existing read-only file flags are preserved.

Reviewed definitions are listed in json/Card-ALD/definitions.
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

Initial routing protects a horizontal escape corridor for every terminal before
laying longer wires. Separate pieces of one net are joined using actual wire
connectivity. If an early net blocks a later one, a bounded deterministic search
retries the routing order. These rules use geometry and net identities only.
Temporary corridor reservations are released before later input and exterior
pin optimizations. Box placement remains on free rows, and all variants retain
the same geometry. A source terminal union that needs more output slots than
the agreed box format permits is reported for review instead of enlarging the
box solely to fit extra outputs.

Routing validation also checks reciprocal wire segments, exact wire-layer
membership, every exterior contact and physical-contact net consistency. A
crossing must remain two straight, perpendicular wires; it cannot conceal a
branch or a bend. Failed route searches do not leave partial wire changes.

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

Use publish_card_candidate.py for new cards and reviewed layout updates, as
described below. Circuit, semantic port identities, notation witnesses and power
contacts must pass current review. Older adopt/import helpers are retained for
reading historical review stages, not for current repository publication.

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

CURRENT SOURCE RECORDS

Current reviewed source state is recorded in notes/Source status.json. Current
card generation receipts are under notes/Card-ALD/Generation and current notation
witnesses are under notes/Card-ALD/Notation witnesses. Concise retained notes
record meaningful corrections, exceptions and unresolved questions. Git keeps
older states; routine publication does not create predecessor or evidence-copy
trees. Current reviewed layouts are JSON definitions rendered by generate_card.py.

PUBLISH A NEW REVIEWED CARD FAMILY

    python tools/card_ald/build_card_data.py CARD --render --output-dir CANDIDATE
    python tools/card_ald/collect_card_variants.py CARD --definition DEFINITION --publication-policy complete-witnesses --output-dir VARIANTS
    python tools/card_ald/audit_card_uses.py CARD --definition DEFINITION --overrides SUPPLEMENT --output-dir AUDIT
    python tools/card_ald/publish_card_candidate.py CARD --definition DEFINITION --overrides SUPPLEMENT --audit USE_AUDIT --review INDEPENDENT_REVIEW --check
    python tools/card_ald/publish_card_candidate.py CARD --definition DEFINITION --overrides SUPPLEMENT --audit USE_AUDIT --review INDEPENDENT_REVIEW

CARD is exactly four digits. The same commands work for a new card or an
updated family; no Python dispatch table or per-card publisher is needed.
Candidate derivation and source review remain explicit: missing evidence is
not converted into an assumed pinout. The publication check reruns the current
source-use audit, rejects unresolved source findings, validates every diagram
and requires a default-builder roundtrip of the reviewed output bytes.
Technical source-model coverage limitations remain recorded in the receipt.

The independent review JSON must contain passed:true, failures:[], and exact
candidate_bindings for the definition, reviewed supplement and use-audit file.
Supporting evidence is listed in supporting_files. Numbered variants also need
a variant_index binding, included among those bound files. The publication
index must declare publication_policy complete-witnesses. That index has a
card_type and variants list; each entry supplies number, variant_definition,
witnesses, source_pages and source_locations. Counts complete_witnesses and
partial_witnesses distinguish fully observed card patterns from profiles whose
unobserved portions retain canonical symbols. The default collector discovery
policy all-observed retains those partial profiles as candidates. The explicit
complete-witnesses policy selects only profiles with at least one complete
physical-card field witness and preserves excluded_partial_profiles in the
evidence index, without renumbering or discarding observations. Purely partial
canonical-filled profiles cannot pass the guarded publisher. Existing reviewed
partial notation records remain explicitly labeled in the CSV when generated.

Publication installs current definitions, supplements, card models, TXT files,
one current source-use audit and one generation receipt. The receipt retains
the exact independent acceptance hash without copying private drafts or crops.
Unrelated cards and index rows must remain unchanged. Per-target atomic writes
check exact predecessors; rollback restores only exact owned output bytes and
preserves concurrent changes with an explicit failure report. The established
exact allowlist refresh updates the repository inventory without history copies.

Runtime source bindings must be portable repository references. Keep only the
current facts and concise authority needed to reproduce the definition; avoid
seed snapshots and predecessor chains. Original scans remain in their reference
archive. Publication never commits, pushes or changes source ALD transcriptions.

    python tools/card_ald/publish_card_candidate.py CARD --verify-current

This verifies current source bindings, the use audit, default-builder roundtrip,
receipt and rendered bytes without opening private candidate or review files.
