UNIFORM SOCKET-LISTING DATA

Socket listings.json is the single collection of logical records. Each
record has the same fields, regardless of the older JSON schema. Values
come from the current accepted UTF-8 text; no legacy value is substituted.
Literal sockets retain B/T suffixes; physical_sockets removes only those
suffixes for matching. Unknown print remains U+FFFD.

Each record is owned by its header scan. A per-scan JSON file contains
its records and IDs for continuations whose headers are on other scans.
The source grid and exact text hashes are retained. Source spans use
zero-based rows and columns. All records can be traced to these spans.

Parser issues remain explicit review items; this build does not change
transcriptions, old models, scans or acceptance receipts.
