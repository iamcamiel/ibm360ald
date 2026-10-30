FUNCTIONAL ALD JSON CONVERTER

Python 3.10 or later; standard library only. Keep convert_ald_json.py and
ald_render.py together. This implements the approved format proposal, not a
production schema migration. Sources and the production tools are not changed.

QUICK START (PowerShell, from the ibm360ald repository root)

  python .\tools\ald_json_tools\convert_ald_json.py .\json -r --dry-run --report .\outputs\ald-conversion-audit.json

  python .\tools\ald_json_tools\convert_ald_json.py .\json -r -o .\outputs\functional-ald --render

For one page, give its quoted JSON path instead of a directory. Multiple files
or directories can be supplied in one invocation. Directory traversal is only
recursive with -r. Use --help for the complete command line.

AP001's human-confirmed upper AU4 -> AW4 correction is deliberately explicit:

  python .\tools\ald_json_tools\convert_ald_json.py ".\json\AP Parallel Adder\AP001 CLOCK POWERING.json" -o .\outputs\functional-ap001 --render --corrections .\tools\ald_json_tools\AP001-human-correction.json

OUTPUT

  AP001.json                 Indented, readable UTF-8 functional page
  review/AP/AP001.json       Content-hash-bound detailed review and evidence
  AP001.txt                  Independently rendered text, with --render
  conversion-report.json    Batch results, including blocked inputs

Printed page versions other than the default 000 add -vNNN to the output stem.
Two inputs producing the same stem are a collision, never silently merged.
No existing destination file is replaced without explicit --overwrite.
Use a fresh output directory. Destinations inside the original JSON repository
are rejected, including a report path that could overwrite a source projection.
--dry-run writes no page artifacts; --report still writes the requested audit.

EXIT STATUS AND RESULTS

  0  Every selected input produced a functional draft, possibly with findings.
  2  At least one input was blocked, or a command/output error occurred.

  converted                 Representable with no reported differences/issues
  converted with findings   Draft exists; read uncertainties and render comparison
  blocked                   No draft emitted for this input; inspect finding.code

Conversion is not source review, approval, publication readiness or publication.
Every emitted page starts with partial review status and approved:false.
Its compact review also contains "unresolved discrepancies":true/false. This
flags pending source questions, notation questions and unexplained render
differences. Resolved history remains external and does not by itself set it.
--allow-partial additionally permits drafts with unplaced-annotation questions;
without it, those pages are blocked. Other ambiguous source facts remain blocked.
Unsupported files do not stop the rest of a batch.

FORMAT RULES IMPLEMENTED

* Blocks sorted by ascending printed serial; integer pin lines and coordinates.
* Page coordinates count from 0; pin lines from 1 including the top border.
* Ordinary net IDs name their explicit driving output, e.g. AP011BJ5.
* Local input straps use e.g. KC011AGL4-strap. Naming uses the first attached
  input line on the lowest-serial attached block. The approved strap case is
  an explicitly declared input-to-input strap on one block.
* Explicit UNUSED rails use e.g. AP361ABL4-unused. Explicit ground and +3V
  nets use AP361ABL4-gnd and AP361ABL4-+3v, using the same anchor selection.
  This selects an existing terminal reference; it does not infer a physical pin.
  Numeric constant codes are not assumed to mean ground or +3V.
* Nets whose source cannot be established use AP361ABL4-no-source, anchored
  the same way and explicitly flagged as unresolved in the external review.
  Known attached inputs are required; a wire with no known terminal anchor
  still cannot receive an honest terminal-based ID.
* Orthogonal polylines contain endpoints/bends; redundant monotone points are
  removed without changing edges. Diamonds, crossings and corners are inferred.
* An undeclared RIGHT_CAPTION_TAIL_<row> in the ordinary output layout is
  treated as a continuation of the unique declared wire ending at column 204
  on that row, when the signal name and output number occupy their standard
  positions and the tail has the expected shape. Conflicts or ambiguous
  owners remain blocked. The source polylines are retained and the mapping is
  reported as a conversion warning; no unrecorded route segment is invented.
* If a full external driver reference is actually the destination page plus
  the local output number, a uniquely claimed additional local driver may be
  used when its recorded route connects to that output and destination. A
  genuine printed left-side input, competing driver, missing or ambiguous
  layout, or disconnected route prevents this interpretation. The original
  external claim remains unchanged and is reported as a review discrepancy.
* Pin annotations use terminal references; detached annotations use route-point
  references and two-dimensional offsets. Connectors belong to nets.
* Exact standalone 2, 3, 8 and L on a terminal become net annotations at
  that terminal, with no physical pin number inferred. Existing unique net
  membership is required; ambiguous or missing membership remains blocked.
  Their text uses the ordinary annotation slot beyond the three-column pin
  space, even when no pin number is printed. All block terminals have a
  fixed three-character label slot; null/omitted pin identities draw a wire
  across that slot. Net routing meets the adjacent outside cell, four columns
  from the border, independently of annotation length. A unique horizontal
  endpoint can be normalized to that contact. Bends or competing routes that
  prevent this normalization remain explicit layout-review holds.
  Characters embedded in pin numbers or longer labels are not this rule.
* Omitted pin means no printed pin. null means unresolved printed identity;
  its observed text lives in external review details.
* A leading K before an established ordinary right-side pin number is an
  auxiliary edge mark: KD11 becomes pin D11 with edge aux. A following
  annotation remains separate. Existing source net and role claims are not
  rewritten; a non-neutral legacy output/driver claim is flagged for review.
  A conflicting border mark is rejected rather than silently replaced.
* Input reference style and output hanging wire length omit their defaults.
  A source list with its first destination inline and the rest in consecutive
  hanging slots can be projected to the ordinary V4 hanging list when each
  destination has a unique matching label and the projected rows do not
  overlap another output. The review records the old and projected positions;
  other mixed or ambiguous layouts remain blocked.
  If the first destination branch is absent, assume one wire character after
  its corner and add an unresolved finding to check the length against the
  scan. Recorded lengths, including zero, are preserved; conflicting or
  disconnected branch evidence remains blocked. A singleton's assumed branch
  and continuation across the output caption are carried in its V4 route so
  the renderer can place the destination below the output. Connector tables
  normalize to row 94.
* Review details include original source hashes, inherited review, uncertainties,
  net-ID mapping, conversion evidence and the render comparison. Large legacy
  text-layout blocks are not copied into the functional page or renderer.

SOURCE SUPPORT AND LIMITS

Supports ibm360-ald-page-v3 ALD diagrams and a limited explicit legacy nodes/pins
adapter. CAS, socket listings, programmed-ground documents, nonstandard block
layouts and unsupported legacy shapes are reported, not reinterpreted as ALD.
The ordinary page template is 245 columns by 103 rows. Functional pages use
$schema: https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json
The schema belongs at schema/ALD_v4.json in the repository on branch main.
Editor retrieval requires that file to be committed and pushed there. This
converter does not publish the schema or perform a production format transition.

An adjacent UTF-8 projection is detected from the repository's parallel json/ALD
trees. Alternatively use --text for one file, --text-root for a projection tree,
or the source's explicit embedded layout. Source layout is read as data only.
No production builder, renderer or importer is imported or executed.

Existing sources are inconsistent. Some contain provisional driver names,
unresolved physical pin labels, repeated printed block serials, overlapping
terminal claims, contradictory routes, or an input drawn more than once.
Some need source decisions or an explicitly approved representation. Unknown
origins with established target pins use the approved no-source rule. The tool
does not manufacture IDs, merge same-looking nets, infer pin identities from
coordinates, or add new format fields. A batch can therefore report blocked
pages even though the converter itself completed normally.

RENDER COMPARISON AS A WIRING CHECK

The independent renderer receives only the new functional data and compact
unresolved display evidence. It never receives source text rows or wire-glyph
overrides. All wiring-glyph differences are listed separately, even if other
text differences exceed the capped first-differences list. Space-padding-only
differences do not count as changed cells; byte equality is reported separately.

A difference is a review candidate, not automatically a source error. It may
expose incorrect old connectivity, a missed wire, an extra wire, different
placement, or an unsupported layout. Check the original scan before correcting
source data. Matching old text is not a reason to invent a glyph override.

The canonical KC011/KC101 inputs still contain the six previously investigated
connectivity discrepancies. Default conversion preserves their original net
memberships and exposes one and five glyph differences respectively. It does
not silently import corrections from the separately reviewed trial files.

EXPLICIT CORRECTION MANIFEST

--corrections accepts schema:ald-functional-conversion-corrections-v1 with a
pages object keyed by printed page ID. Each entry must bind source sha256.
Optional replacements contain pointer, before, after and authority. They apply
to existing fields of the converted functional draft using JSON Pointer and
exact preimage checks. Optional resolutions contain field, value and authority
and resolve an emitted review uncertainty; they do not alter a semantic value.
Use a replacement too when a semantic value needs to change.

All changes are retained in the review sidecar. Route changes are distinguished
from unchanged source graph preservation. New unapproved fields are rejected.
This mechanism does not supply missing facts to otherwise blocked source files.
AP001-human-correction.json is a working minimal example of a human resolution.

REGRESSION CHECKS

  python -m unittest discover -s tools/ald_json_tools -p test_converter.py -v

The repository fixtures test AP001 and all four KC pages, routing preservation,
strap/board representation, the explicit AW4 correction, naming of unused and
constant nets, malformed JSON and routes, ambiguous terminal identities,
content-bound review loading, batch continuation, dry runs and overwrite guards.
They also cover the full eleven-character LOG value field and explicit blank
display evidence for an unresolved division, including its reserved spacing.
An explicit blank display does not turn the unknown semantic value into a value
or clear its unresolved review status. Missing/non-string display evidence fails.

SOURCE REVIEW COMPOSITION

External review evidence retains each source net's external_references presence,
explicit null or ordered value, and its original reference endpoint claims.
These observations do not establish directed remote terminals.

When composing a selected package, carry every known still-unresolved source
hold into the existing external uncertainties array, with its exact scope,
source kind, unresolved status and bound original review evidence. Do this before
finalize_review. A byte-exact render does not close an inherited source hold.
Resolved history stays in the external review; incomplete technical work is
recorded separately and does not by itself constitute a source discrepancy.
The converter's inherited review object alone is not a full package-hold intake.

Footer notes use the human-approved default column 4. A captured column-3 note
group moves to column 4 with its text and relative indentation preserved. The
comparison retains all raw source/render differences before normalization and
checks each original label span and non-note overlap before marking the note
placement difference as approved. This does not certify original scan columns.

Damaged two-character printed block serials may use their exact unresolved
illegible literal from the external review. The opaque serial remains the
reference identity; compact unresolved discrepancies must be exactly true.
Duplicate, missing, non-string or non-damaged serial masks fail closed;
resolved history and source-review holds do not replace a printed serial.

Wire junction degree counts distinct geometric incident directions within each
net, including a terminal stem at most once. Output continuation requires an
explicit same-net output record, matching row and explicit membership. Distinct
nets crossing at a cell never create a junction by their combined degree.

Explicit primary source terminal references take precedence over secondary
aliases. Multiple actual primaries and unresolved alias-only ambiguity still
reject. Hanging wire length candidates require an observed local vertical
connection and nonnegative bend; disconnected horizontal fragments do not
establish a hanging length.

K auxiliary modifiers require one canonical role source observation, explicit
neutral side, positive right-border K geometry and passive_terminals membership.
They render with the existing R side and edge aux, without acquiring signal
direction, driver or origin status. Known contacts stay known; printed blank
contacts require positive evidence and physical unknowns remain externally bound.

An explicit connector-table net heading with unsupported location text stops
conversion before any following continuation can inherit the previous owner.
Unsupported or opaque footer text is never silently dropped or normalized.

Exact split terminal labels are consumed only within an established printed
span; parsed sink prefixes require same-net observed route edges. Positive
explicit unprinted-terminal evidence also applies to ordinary contacts. These
coverage rules do not infer pins or routes. Wiring discrepancy reports include
changed body cells with a nonblank wire glyph on either side, including wire
versus text, with complete findings beyond the first-differences display cap.

A bare observation of an already established physical pin may omit its
separately printed star-only suffix at the exact unique same-row contact.
Unknown pins, conflicting numbers, nonstar suffixes, wrong placement and
ambiguous ownership remain unresolved; physical identities are never filled.

SOURCE INTERPRETATION GUARANTEES

Recorded block-relative pin rows are converted to page rows only when explicit
absolute-row observations or recorded points agree. Mirrored observations must
agree; missing or contradictory evidence is reported. Original terminal records
remain intact, and external evidence records the interpreted coordinate view.

An otherwise unbound inputN selector needs a complete, consistently ordered
source pin array AND exactly one input on that block at an endpoint of that
source net's recorded routes, agreeing with the input-side ordinal. An array
index alone, an interior wire crossing, or a nearby contact is insufficient.
Existing explicit aliases retain precedence and unresolved ambiguity stays held.

Repeated physical pin numbers on separate output rows do not merge logical
nets. Existing output occurrences and their source-owned routes select the net
IDs; supported disjoint legacy physical groupings retain their original source
record externally while becoming separate logical nets.

These interpretations create no physical pin identities, new functional format
fields, source approvals, or publication approvals. Remaining findings persist.


Additional source-bound conversion rules

A K-prefixed observed contact may use its separately evidenced right-border K
as a border cell, rather than part of the contact span. Contradictory literal
or mirrored side and glyph observations reject; driver and passive claims are
not changed.

A uniquely headed column-2 NOTE group can use the normal column-4 note format
when each note row has one eligible note label and single-character labels match
the page identifier. Relative indentation is preserved; grouping and placement
remain unresolved review issues. Original span and destination-overlap checks
run before rendering, including when rendering fails.

A unique ordinary input reference inside a larger recorded span is accepted only
when surrounding horizontal glyphs and the recorded corner match source text
and existing same-net route points. Conflicting or ambiguous overlaps remain
blocked; no connection is inferred. The known AP801 AN4 owner conflict remains blocked pending source review.

These conversions remain partial and unapproved. They do not certify wiring,
source geometry, electrical connectivity, or publication readiness.


Source-bound SPARE conversion
A uniquely evidenced SPARE label may be associated with its numbered route as a logical local spare, with a -spare net suffix. The printed label and numbered route remain separate polylines; no physical edge across their gap is inferred. Conversion requires explicit text, unique source and local targets attached to the numbered route component, and retains the source binding and unresolved interpretation for review. Ambiguous or unsupported cases stop. The -spare suffix requires the accompanying schema extension; schema versions before this extension do not accept it.

Column-241 output references: explicitly recorded output headings at source column 241 are accepted when their reference and caption spans match the source text and a unique routed owner reaches the heading. The V4 display uses column 242; an unresolved source-position finding records that projection. Competing headings, unsupported adjacent offsets, and ambiguous owners remain blocked. No source coordinate is changed.

REPOSITORY PACKAGE

This directory includes the converter, its matching standalone renderer and
portable regression tests. Run commands above from the repository root.
Historical source-audit tests requiring private workspace evidence are not
included. Repository-backed tests use json/ and retained review/v3 fixtures;
unavailable source fixtures are explicitly skipped. The converter and renderer
match the accepted standalone versions; repository packaging changes only
documentation and test fixture locations. Two older named-input test fixtures
also follow the current constructor contract: both alias indexes are initialized,
and object_ids remains a required initialized map.
