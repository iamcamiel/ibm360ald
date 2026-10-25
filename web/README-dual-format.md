# Dual-format ALD browser deployment

Install the complete changed files from this candidate over the existing browser, preserving their paths. Keep existing assets, fonts, viewer.php and the catalogue.php routing wrapper.

## Runtime

- PHP 8.1 or later with JSON and `proc_open` enabled. The application remains read-only; its temporary cache must be writable.
- Python 3.9 or later for functional v4 pages. No Python package installation is required.
- The unchanged standalone renderer is included at `ibm360ald/tools/ald_render.py`. Its SHA256 is `a657f24174374a4cba8f3c47ea61be88e98e6fa9a25e5c5cd91aefd868dfb736`.

By default the browser uses this sibling `tools/ald_render.py` and starts `python3` on Unix or `python` on Windows. If Python is not on the web-server account's PATH, set `ALDBROWSER_PYTHON` to the full executable path, for example `C:/Python312/python.exe`. This setting is one executable path, not a shell command or argument string. Optionally set `ALDBROWSER_V4_RENDERER` to the exact qualified renderer file. The process is invoked with an argument array, UTF-8 mode and `-B`.

Do not configure a newer renderer without reviewing the browser layout adapter. The browser deliberately rejects any renderer whose bytes differ from the qualified hash: input positions, output hooks and footer spans currently implement a657 semantics. Future remote footer headings, derived stars and annotation-wire changes require a coordinated adapter qualification. No renderer code is patched here.

## Source and review handling

The existing Source status catalogue still supplies explicit JSON/TXT pairs. V3 pages keep their existing path. Native v4 JSON is rendered directly; no v3 source or captured TXT is used to reconstruct it. A v4 review sidecar must stay inside its model directory, match the page identity and match the canonical content hash excluding `review`. Document and sidecar duplicate keys and non-finite numbers are rejected. Changed source or review bytes invalidate cached output. Authenticated writer options preserve LF/CRLF and trailing-space behavior.

V4 conversion approval is always unverified: no source approval badge is granted from compact flags, sidecar status or old v3 approval data. A future legitimate human-approval workflow is a separate integration policy dependency. The browser displays current review status and unresolved-observation count.

The browser does not save models, change physical identities or adopt pages. Source-format preserving editor saves are implemented separately.
