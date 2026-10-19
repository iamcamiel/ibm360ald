ALD pages: JSON-owned UTF-8 rendering

The page model owns text_layout. In a uniform v2 document this is stored at
current_extensions.text_layout; the established source reader exposes it as
text_layout in the detached source view. Existing logical objects and nets
retain their current schema.

The layout records Unicode character cells, literal drawing glyphs, spaces,
bound printed fields, row lengths, exact line endings and the UTF-8 BOM.
Coordinates are zero-based Unicode code-point positions, not byte offsets.
Rendered TXT is generated output. Do not independently edit it.

Printed fields are linked to source JSON pointers only where their ownership
and placement were verified. Declared identical printed-label mirrors are
updated together. An unbound source/geometry/net change stops rendering until
its layout is explicitly reviewed and updated; it cannot silently reuse an
obsolete drawing. Literal wire glyphs preserve the drawing, without asserting
that the existing semantic net model has been independently re-audited.

Check a page after the layout migration:
  python tools/page_text/render_page.py "json/<folder>/<page>.json" \
    --compare "ALD/<folder>/<page>.txt"

Prepare a correction using a JSON array of {pointer,before,after} edits:
  python tools/page_text/render_page.py "json/<folder>/<page>.json" \
    --patches edits.json --model-output draft.json --text-output draft.txt

The edits address the detached source view (for example /nodes/0/unit), not
the derived normalized fields. The tool updates the declared mirrors,
renormalizes the model and renders the TXT. Output files must be new drafts.
Publish both generated artifacts through the source-checkpoint workflow;
generation alone does not update the repository's acceptance records.
