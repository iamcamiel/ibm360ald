SOCKET-LISTING JSON REBUILD

Run from the repository root with Python 3.12 or later:

  python tools/references/build_uniform_socket_listings.py --output ../socket-listing-build
  python tools/references/verify_uniform_socket_listings.py --dataset ../socket-listing-build

Only the Python standard library is required. --repo selects a different local
repository. The output must be a separate root, outside the canonical ALD,
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
