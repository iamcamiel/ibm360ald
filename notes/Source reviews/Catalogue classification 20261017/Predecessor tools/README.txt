SOCKET-LISTING JSON REBUILD

Run from the repository root with Python 3.12 or later:

  python tools/references/build_uniform_socket_listings.py --output ../socket-listing-build
  python tools/references/verify_uniform_socket_listings.py --dataset ../socket-listing-build

Only the Python standard library is required. --repo selects the checkout root;
run that checkout's installed copy of the script. The output must be a separate root, outside the canonical ALD,
json, csv and notes trees. Running the builder does not change those trees.

The builder selects all accepted files whose names contain SOCKET LISTING,
including the EF supplements, through notes/Reviewed export provenance.json.
Each TXT hash must still match its acceptance. It does not use the older,
heterogeneous JSON tables to infer or fill values.

OUTPUT

  json/Socket listings uniform/Socket listings.json
      One collection of logical socket records, not repeated per-scan copies.
  json/Socket listings uniform/pages/<source folder>/<scan name>.json
      Uniform per-scan records, exact source text grid and continuation links.
  csv/Socket listings uniform/Portion references.csv
      One row per listed ALD page/portion claim, retaining duplicates.
  notes/Socket listings uniform/Build manifest.json
      Input, generator and output hashes for checking or reproducing a build.
  notes/Socket listings uniform/README.txt
      Data interpretation notes carried with the generated dataset.

IDENTITY AND SOURCE EVIDENCE

page is the scan filename prefix, including -01/-02 when present. printed_page
retains the page number from the accepted archive catalogue. scan_id is the
stable archive scan identity. These are different: two scans can have the
same printed page number. Records are ordered by board, scan page and source
column/row. A record continued in another column or scan remains one record,
owned by its original header scan; other scans link to its ID.

Every record uses the same keys. Missing values are null or empty lists;
unreadable print remains U+FFFD. Conflicting printed fields remain explicit in
ambiguous_fields and issues. No majority reading replaces a source literal.
Whole source chunks are retained in source_spans and raw_lines. Evidence uses
zero-based row and column coordinates in the exact accepted UTF-8 text grid.
source_relative names the original scan but the scan is not read or modified.

sockets keeps the printed socket suffixes. physical_sockets removes only a
trailing B/T position suffix after a digit for later cross-reference matching.
It does not confuse that suffix with the board/unit or a pin bank. Records
retain kind_literal alongside normalized kind; unclassified types remain
unspecified. Connector listing pages, wire codes, destinations, pin references,
unused portions/pins/sockets and supplementary plug-list rows are separate
from card ALD page/portion references.

VALIDATION AND LIMITS

The verifier checks input/output hashes, exact source-grid reconstruction,
schema consistency, record ownership/continuations, source evidence and the
flat reference CSV. It does not infer electrical correctness or prove a scan
was transcribed correctly. Parser diagnostics are kept separately from these
mechanical checks; a mechanically valid dataset can still contain uncertain
print or explicit unparsed source rows. Review those before using an affected
record as an automatic correction.

The existing socket_listing_records.py loader supports comparison with legacy
compiled data; it is not the source for this rebuild. socket_pin_validation.py
provides the downstream SLT pin-range/contact checks. Neither tool changes
accepted transcriptions. The cross-reference audit against ALD blocks is a
separate stage after the uniform socket data has been checked.

READ-ONLY SOCKET TO ALD AUDIT

  python tools/references/audit_socket_ald.py --output ../socket-ald-audit

This uses the uniform socket collection and current accepted page models. It
adapts their common node fields in memory; no ALD JSON migration is required.
TXT/model hashes are checked before matching and again before output. All
separately scanned variants remain eligible; none is chosen as the latest.

Exact identities require matching board/socket, card type and portion, including
agreement between combined printed codes and split fields. Two-of-three matches
are candidates, never corrections. Missing pages, unavailable models, unreadable
identities, ambiguous candidates and readable disagreements have separate status
codes. Empty annotation nodes cannot masquerade as unreadable matching blocks.

Pin checks use single/double socket evidence, with unanimous card-type evidence
as a fallback when appropriate. Connectors are not assumed to be SLT cards.
Power contacts, annotations, pinless wires and unused inputs are distinguished.
No electrical-rule or canonical card-diagram contact audit is implied by these
physical range checks.

The output contains complete JSON/CSV checks, a findings CSV, pin results, absent
page references, a summary and an output hash list. Output must be outside the
repository and must be new or empty. The audit changes no source files.
Audit metadata.json retains counts and all source bindings without the large
per-claim result array. Tool snapshots preserve the exact runtime used for the
comparison; Audit files.json binds every generated report and snapshot.

The same command also runs a limited reverse pass. Every block not reached by
an exact forward match is searched against all socket records, using the same
board/socket, card and portion rules. Exact identities listed under another page
are reported separately from mismatches, unused portions and unresolved print.
They establish a physical identity, not permission to rewrite a printed reference.
Explicit mechanical, CAS and other non-card objects are counted separately.

Socket entry coverage.csv accounts for every logical socket record, including
cables, connectors and records with no listed card portions. Connector pin rows
are inventoried but not electrically traced by this card-portion comparison.
All ALD node checks.csv partitions every model node into a forward hit, reverse
finding or explicit non-card object. Page model coverage.csv records model/node
availability for every accepted scan. No scan variant or candidate is discarded.
ALD to socket matches.json contains reverse evidence; Reverse findings.csv is the
compact review list. Candidate listing evidence is stored once by record ID.

Source-schema adaptation is explicit and read-only: code-shaped card/part aliases
and physical locations are distinguished from grid labels. A frame number is
expanded only when embedded listing evidence agrees with the printed unit,
board, socket and readable card/portion. Conflicts remain unresolved; CPU frame
abbreviations are not globally reassigned. Raw nodes and adaptation evidence are
retained in the audit, and original JSON is never rewritten by this command.

The command also reconciles whole reference groups. Every listed portion needs
an exact identity on a common page before a unique counterpart link is reported.
Reference reconciliation.csv and .json retain both the literal reference and
the counterpart, plus missing portions or alternative pages. These links do not
assert a transcription correction; a printed reference may be an older one.

  python tools/references/investigate_absent_ald_references.py --audit ../socket-ald-audit --output ../absent-reference-review

This second read-only pass searches other pages for the same exact physical
identity and records source listing positions. A candidate, even one differing
by a single character, does not establish a transcription error: inspect the
original print before applying a correction.
