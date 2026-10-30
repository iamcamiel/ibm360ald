ALDbrowser: build the static browser cache on the HOST

After updating the checkout, run from the ibm360ald directory:

    git pull --ff-only
    python3 tools/build_browser_cache.py

Use Python 3.9 or newer. The builder uses Python's standard library; no PHP
command or pip installation is needed for the build. On Windows, use python
instead of python3 if that is your Python command. Run against the same checkout
served by the web server/container. The existing PHP viewer and JavaScript
module endpoint remain presentation-only: page data, rendered text and final
links come from static files in cache/.

The build validates source hashes and review bindings, renders native pages,
and generates cross-page links once, before publishing. Serving a page does not
scan or validate the source collection. Source or editor changes become visible
after the next successful build; rebuild after saving edits as well as pulling.

Before collecting the cache, the build invokes tools/render_all_json.py to
regenerate current JSON-owned ALD/*.txt files. You can run that script manually:

    python3 tools/render_all_json.py --check
    python3 tools/render_all_json.py

Exact backups and Source status update receipts are saved under
review/maintenance when text changes. See tools/PAGE_MAINTENANCE.txt for the
standalone pin annotation migration, reports, paths and recovery details.

The host build account needs write access to ibm360ald/cache, ALD, notes and
review/maintenance. The web server
needs read access only. For Docker, its served checkout must include that same
cache directory through the host mount. The cache is ignored by Git: build it
on each deployment after pulling changes. Do not commit generated cache files.

First deployment: finish a successful build before opening index.php. There is
no expensive live-catalogue fallback. A missing cache/catalogue.json produces the
browser's catalogue-load error; build the cache, then reload the page.

cache/catalogue.json is the atomic commit point. A successful build publishes it
only after all referenced immutable assets exist. Older assets are retained so
open tabs using an earlier catalogue can finish loading. Do not delete cache
during a build or automatically prune old assets. A failed build leaves the
previous catalogue usable; inspect the reported failure before trying again.

The builder prevents simultaneous builds with cache/.build.lock. A forcibly
terminated build may leave that lock behind. Remove the lock manually only
after confirming that no cache build is still running, then build again.

The catalogue references TXT, JSON downloads and final interaction JSON by paths
relative to cache/catalogue.json, all beneath cache/. Downloads are snapshots of
that build. Serve .txt as UTF-8 text/plain and .json as application/json. Allow
cache/catalogue.json to revalidate; content-addressed assets may be cached
immutably. New files use public read permissions on POSIX systems.

The browser retains its small exact-TXT-byte hash check on HTTPS or localhost
before enabling selections/links. Review and approval metadata remain as built;
no approval or new wiring interpretation is inferred. This change does not
apply the separate inline real-reference annotation design.
