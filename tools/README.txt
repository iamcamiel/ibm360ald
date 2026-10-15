IBM 360 ALD TOOLS

tools/repository/verify_repository.py runs directly in this repository with
Python 3.10 or later and no third-party dependencies:

  python tools/repository/verify_repository.py

It checks UTF-8 encoding and the hashes recorded in notes/Repository records
manifest.json. This is an integrity check, not native-image or wiring review.
After intentional edits, update the review records and integrity snapshot.

tools/repository/import_review_records.py preserves accepted-export provenance,
review records and shared historical tools from the existing working collection:

  python tools/repository/import_review_records.py --workspace "D:/Github/IBM360"
  python tools/repository/import_review_records.py --workspace "D:/Github/IBM360" --write

The first command reports a plan. The second copies records into this repository.
Use --reference to select the original IBM_360_ALD directory on another machine.
It reads the working collection's reviewed export manifest and does not import
draft diagram text or change working files. Content JSON/CSV has a separate import.

tools/cas/cas_characters.py is the reusable helper for approved CAS glyphs.
The supplied CAS printer grid is recorded in notes/CAS printer grid specification.json.
Migration to that grid is in progress; page review records identify accepted layouts.
QQ451 F1 remains provisionally on the E row pending the requested manual check.

tools/cas/validate_grid_stage.py independently checks private candidates for
245 columns by102 rows, approved characters, box positions, printed controls,
retained QZ records and wiring regressions. It writes only its requested report:

  python tools/cas/validate_grid_stage.py --workspace "D:/Github/IBM360" --report "audit.json"

It needs the reviewed working collection and private candidate directories.
tools/cas/wire_graph.py traverses visible wires without changing any files.
Unmarked four-way crossings stay separate; printed O junctions join them.
Reachability equality is a regression check, not proof of faithful source wiring.

tools/cas/promote_reviewed_grid.py replaces working artifacts only when an explicit
root acceptance receipt binds their current hashes and records the review scope.
It preserves before-files and never changes reference scans. It does not infer
acceptance from a mechanical pass; repository export remains a separate step.

tools/legacy preserves shared conversion engines and checkers with their local
Python imports, retaining the old relative source layout. These are historical
source snapshots, not a standalone automatic TIFF-to-text converter. They refer
to original workspace paths, manually reviewed page specifications, scan caches,
reference TIFFs, glyph templates and fonts. Several use Pillow, NumPy and OpenCV.
They need those inputs and path adaptation before use in a different workspace.
The manifest records the original path and SHA-256 of each preserved source.
Page-specific repair scripts, superseded drafts and initial OCR experiments are
excluded from the curated seed list; an imported dependency may include an older
recognition helper that a retained engine still imports.

Content data can be copied with:

  python tools/repository/import_content_data.py --workspace "D:/Github/IBM360" --write

Run the content import before import_review_records.py --write so the integrity
manifest includes the content files. JSON and CSV mirror the reference folders.
The content import preserves available page models, reviewed CAS source-layout
specifications and aggregate socket/ROS tables. Pages without separate models
are recorded in notes/Content data manifest.json; aggregate tables can still
cover their printed records. It does not fabricate missing per-page models.

The original working tools remain in place for the active transcription chats.

tools/pins/audit_pin_labels.py checks the physical pin labels recorded in the
published ALD page JSON against the A1 single/double-card inventory. A single
SLT card has B02-B13 and D02-D13; a double card also has G02-G13 and
J02-J13. It writes source-bound findings and optional cross-page suggestions
to csv/Pin validation and a count summary to notes/Pin validation. It reads
all structured ALD pages but does not OCR TIFF pixels or automatically change
accepted text. Service grounds, cables, and other non-SLT terminals require
separate classification before applying the SLT card rule.

tools/card_ald/build_4191.py regenerates the Card-ALD/4191.txt example.
Its source observations and native-scan exceptions are recorded under
notes/Card-ALD. The builder verifies one label per used physical pin and
requires every bit feedback pin to match the same bit's N-stage output.
