SOURCE REVIEW TOOLS

CURRENT SOURCE STATUS

notes/Source status.json is the compact current repository checkpoint. It binds
each accepted TXT, optional current JSON/notes, scan reference and explicit page
review status. It is not a new visual acceptance or a claim that every field is
readable. Significant corrections and unresolved readings belong in concise
current notes. No preview copies, old stages, raw-byte archives or repeated
per-node acceptance contexts are required for current repository validation.

  python tools/reviews/current_checkpoint.py --repo .
  python tools/reviews/successor_registry.py verify-current --repo .
  python tools/repository/import_source_review.py --verify-current --repo .
  python tools/repository/verify_repository.py --repo .

load_checkpoint(repo, path=None, inventory=None) returns current records, a small
binding/report and recheck(). It verifies current bytes, portable paths, unique
scan identities, exact model/TXT membership and explicit review statuses. It
never reads TIFF bytes, historical receipt trees or optional external working
quartets. Passing the current inventory also checks repository ownership. The
checkpoint does not hash itself or the inventory, avoiding circular bindings.

With Source status present, refresh_inventory.py defaults to compact retention:
no inventory-predecessor copy and no appended review history. Exact allowlist,
before/after hashes, all unrelated recorded-file checks and rollback remain.
An explicit action:"remove" entry needs the exact recorded before_sha256,
after_sha256:null, authority and an already absent file. The helper does not
delete files or silently forget other missing records. Legacy inventory history
is available only via --retain-inventory-history.

To mirror a NEW published generic source-review stage:

  python tools/repository/import_source_review.py --compact-stage MANIFEST --acceptance ACCEPTANCE --repo . --source-root ORIGINAL_SCANS

This is a dry run; add --write for the guarded transaction. It verifies the one
new stage/independent acceptance/publication, exact prior TXT, and equality of
pruned prior JSON with the current repository model. It then imports the new
TXT, pruned JSON and compact notes, and refreshes current Source status, Content,
Reviewed export and inventory hashes. Existing concise correction/exception/
unresolved notes survive; explicit new notes use those same labelled lines.
No prior registry, old export plan, historical proof copy or repository preview
is used. A repeat of the same accepted state is a no-op. Before-hash guards and
in-memory rollback protect the transaction without creating an archive tree.
Mixed epochs, changed current semantics and path aliases are rejected. This
generic route currently requires an existing JSON model; TXT-only source rows
need their own reviewed model/text workflow rather than an invented model.

The result reports that uniform socket metadata and the current card catalogue
need refreshing. Their existing source-hash guards remain in force; the import
does not silently refresh or publish card diagrams. Source scan files and the
external working owner files are never written by this repository mirror.

The legacy source importer remains disabled by default on a compact repository
to avoid restoring historical models or evidence folders. --legacy-history is
an explicit old-workflow opt-in while its external evidence still exists.
Current verification needs none of that history.

The following source-edit/staging commands remain available for new explicitly
reviewed changes. Their private transaction evidence is separate from current
repository retention; old .history folders are not current runtime prerequisites.

source_review.py records literal answers and applies explicit reviewed corrections.
It does not read characters from scans, infer missing values, generate independent
acceptance, or export to another repository. Python3.10+ is required. Pillow and
an explicitly bound monospaced font are required only for new preview rendering.

Run commands from the repository root:

  python tools/reviews/source_review.py ledger-init answers.json --review-id review-name
  python tools/reviews/source_review.py add-question answers.json --question-json question.json
  python tools/reviews/source_review.py record-answer answers.json --question-id Q1 --raw "b08" --normalized B08 --response-id reply-001
  python tools/reviews/source_review.py verify-ledger answers.json

question.json contains {"question_id":"Q1","text":"What is printed?"} and may
include context and an evidence array of path/sha256 bindings. Answers retain raw
and normalized text separately. Normalization defaults to literal identity.
--raw-file preserves longer responses without shell quoting. Supply a stable
--response-id when retrying: an identical retry does not duplicate a response;
a different response with that ID is rejected. Corrections create another event
and retain all earlier answers. Optional --expected-revision rejects stale edits.

OS locks serialize writers and release on exit/reboot. Each update uses a flushed
atomic replacement. The previous exact ledger is retained in answers.json.history.
A hash chain detects later alteration of events; it is integrity evidence, not a
cryptographic identity/signature. Never edit a ledger by hand.

Build an intent with schema source-review-intent-v1, review_id, optional card_type,
target_root, unresolved_questions:[], optional evidence bindings, and pages:

  {
    "page": "PAGEKEY",
    "model_schema": "ald-page-nodes-v1",
    "source": {"path":"original.tif", "sha256":"..."},
    "prior_quartet": {
      "txt": {"path":"PAGE.txt", "sha256":"..."},
      "json": {"path":"PAGE.json", "sha256":"..."},
      "notes": {"path":"PAGE review notes.txt", "sha256":"..."},
      "preview": {"path":"PAGE preview.png", "sha256":"..."}
    },
    "grid": {"width":245, "height":103},
    "cell_edits": [{"row":3,"column":51,"before":"OR","after":"AR"}],
    "json_patches": [{"pointer":"/nodes/0/function","before":"OR","after":"AR"}],
    "notes_append": "The literal reading was independently checked.",
    "preview_config": {
      "font":{"path":"JuliaMono-Regular.ttf","sha256":"..."},
      "width":2940,"height":1854,"font_size":20,
      "cell_width":12,"row_height":18,"origin":[0,0]
    }
  }

Paths in an intent are relative to that intent, or absolute. Use the bind command
to obtain a path/sha256 object. The example pixel configuration is illustrative:
the tool must reproduce the existing preview pixels before regenerating it.
An optional preview anchor is "lt"; no other drawing modes are supported.

  python tools/reviews/source_review.py bind path/to/file
  python tools/reviews/source_review.py stage --intent intent.json --stage private-stage
  python tools/reviews/source_review.py verify-stage private-stage/manifest.json --phase staged

Only same-width text replacements within existing rows are accepted. Coordinates
are zero-based. Row widths, trailing spaces, BOM and line endings are preserved.
Models must be JSON objects with a nodes list. JSON pointers support replace with
an exact before value, add of a new object member, and remove with exact before.
Array insertion/removal, overlapping JSON scopes, missing preimages, unknown
schemas and unresolved questions are rejected. All active aliases must be listed
explicitly; the tool does not guess which other strings should change.

Printed pin labels and bare physical contacts are separate fields. A changed pin
must not leave its physical_pin mirror stale. Removing a printed asterisk requires
an explicit annotation_drop_reason on that exact JSON patch and bound page
evidence. The annotation/contact guard runs at staging and verification.

Staging writes only a new directory outside target_root. It saves immutable
intent/evidence/font/tool inputs and both before/candidate quartets. Original
TIFFs remain hash-bound in place. Preview bytes change only when TXT changes.

An independent reviewer must supply a separate JSON acceptance:

  {
    "schema":"source-review-independent-acceptance-v1",
    "passed":true,"failures":[],"independent_review":true,
    "reviewer":"reviewer identity","unresolved_questions":[],
    "manifest_sha256":"exact manifest hash","accepted_pages":["PAGEKEY"]
  }

  python tools/reviews/source_review.py publish private-stage/manifest.json --acceptance independent.json
  python tools/reviews/source_review.py verify-stage private-stage/manifest.json --phase published

Publication rechecks source, inputs, preimages, exact deltas and acceptance. It
replaces only declared quartet targets and retains backups. An identical retry
verifies the published bytes and returns the prior receipt. An interruption leaves
a publication-in-progress journal; reconcile it explicitly using the backups
instead of silently restarting a partially written batch. Multi-file publication
cannot be atomic, although individual files and the final receipt are atomic.

verify-stage also accepts native-card-review-private-stage-v1, read-only, with
--acceptance pointing to its original passed manifest-hash-bound review. It checks
the original TIFF, immutable input/artifact hashes, exact named TXT changes and
whole before/published epoch, and reports both model bindings and all JSON delta
paths. That legacy manifest does not declare JSON patches or preview parameters;
their scope remains certified by its independent acceptance, explicitly reported
as such. This tool never republishes that older schema or claims to rederive its
JSON/preview approval. --report NEW.json optionally saves a new verification report.
--phase snapshots validates immutable historical inputs and exact deltas without
asserting that the current working quartet still belongs to that historical epoch.
Use it only as one part of a successor chain whose latest quartet is checked live.

These commands publish working source-sheet quartets only. Acceptance/export
registration and repository mirroring remain a separate, reviewed workflow.

SUCCESSOR ACCEPTANCE REGISTRY

successor_registry.py records already published generic releases in order. All
stage snapshots and independent acceptances are checked. A later release for the
same exact target must start from the preceding accepted quartet hashes. Only
the latest quartet is required to match the working files. Historical reviews
remain intact. Registration is locked, atomic, idempotent and keeps prior bytes.

  python tools/reviews/successor_registry.py register registry.json --publication private-stage/publication.json --workspace WORKSPACE --exports WORKING_SHEETS --source-root ORIGINAL_SCANS
  python tools/reviews/successor_registry.py verify registry.json --workspace WORKSPACE --exports WORKING_SHEETS --source-root ORIGINAL_SCANS

The exporter adapter uses the configured Source review successor registry.json.
Once configured it is mandatory: missing registry/publication/evidence or a
changed source/current quartet raises an error, never revives an older review.
accepted_successors(...) returns exact-target records and preservation_files.
The reusable scoped repository importer consumes those validated records to
mirror an accepted successor over an otherwise verified export baseline.

A1 TABLE APPLICATIONS

register_a1_application.py registers an already independently reviewed and
published socket-table literal correction. It does not stage or apply source
changes and does not convert a table into an ALD nodes model. Preflight is the
default; --register updates only the existing current-field adapter and the
mandatory A1 table registry, retaining their exact predecessors.

Supply --stage, --publication, --acceptance, --adapter, --registry, --workspace,
--exports and --source-root. The accepted table schema has a real current TXT,
review-notes file and preview, plus immutable page-specific columns evidence.
Historical columns-reviewed arrays remain unchanged. Shared collection JSON
updates stay in the immutable publication review, rather than becoming live
dependencies of an unrelated table page.

The exporter calls validate_registered_applications before reading legacy
receipts. Missing or changed registered proof, adapter item or current table
companions blocks fallback to the old columns-file-presence rule.

Tests (all sources/destinations are disposable fixtures):

  python -m unittest discover -s tools/reviews -p "test*.py" -v

Set SOURCE_REVIEW_TEST_FONT to a TTF path if the test system has neither Consolas
nor DejaVuSansMono. No card IDs, sheet numbers or original workspace paths are
embedded in the reusable tool.
