CARD-ALD COMPOSITE PINOUTS

NNNN.txt is the canonical circuit-symbol form. Numbered variants retain
reviewed notation with identical geometry. Provisional circuit forms remain
explicit in their headers.

40 canonical card types and 259 TXT diagrams are published.
35 families (56 TXT files) are accepted and current-verified.
5 older families (203 TXT files) remain retained: 0141, 3308, 4191, 4633, 4634.

The catalogue has 190 types and 188 in scope. Only 1457 and 1724 are excluded.
The completed pre-visual run of 153 families and 459 actual CLI phase attempts
remains historical evidence. After 31 reviewed reading/classification changes
on 21 objects across 18 pages, only 13 directly corrected families have new
build/audit/render CLI runs: 39 actual phase attempts. The 35 accepted families
were separately replayed, imported and current-verified.

The other 140 raw-family results retain the preceding source epoch. The 26
page-only source/catalogue semantic checks do not constitute new CLI runs.
This update does not claim all 188 families were rechecked at the new source
epoch. Latest 13 phase outcomes: {"audit": {"blocked": 5, "passed": 8}, "build": {"passed": 13}, "render": {"blocked": 5, "passed": 8}}
Blocked downstream phases remain separate from failed executions.

RT381-02 E3 is applied. No manual answer is pending in this review wave; this
does not claim that every older workbook question is closed. 4072 remains an
older clean candidate awaiting independent review, not an accepted card.
All 259 published TXT diagrams and their geometry are unchanged. Graphviz
comparisons are private previews. No new card diagram is published here.

Current definitions: json/Card-ALD/definitions/NNNN.json.
All-card processing and holds: notes/Card-ALD/Current processing status.json.
One-row-per-card table: csv/Card-ALD/Current processing status.csv.
Current publication receipts: notes/Card-ALD/Generation/NNNN.json.
Current notation witnesses: notes/Card-ALD/Notation witnesses.
No predecessor or raw-evidence copy tree is required; Git retains older states.

REBUILD FROM THE REPOSITORY DIRECTORY

    python tools/card_ald/generate_card.py CARD

Use all four digits, including a leading zero. One shared renderer consumes
the reviewed definitions; no per-card Python builder is required.

BUILD AND AUDIT PRIVATE CANDIDATES

    python tools/card_ald/run_card_batch.py --prefix all --output-dir PATH
    python tools/card_ald/build_card_data.py CARD --render --output-dir PATH
    python tools/card_ald/audit_card_uses.py CARD --definition DEFINITION

The builder, auditor and notation collector share the unified page-JSON reader.
The batch command attempts every selected card, preserves explicit failures,
and checks that source bytes did not change. Candidate output is not published
until source, connectivity, physical contacts and notation have been reviewed.
Current source-bound accepted AR pass-through aliases are inputs only. Explicit
K contacts retain their physical role without inventing card-internal unions.

Seven-character-high boxes may start on any line. Placement, interchangeable
input ordering, wire routing and short shared-net R labels use universal rules.
Power contacts are listed separately. Numbered variants share canonical geometry.
Details and publication commands: tools/card_ald/README.txt.
