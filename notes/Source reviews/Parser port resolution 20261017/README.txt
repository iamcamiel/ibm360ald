Parser port resolution review — 2026-10-17

The parser now resolves a source terminal to its actual raw port before reading the contact label. All41 previously reported PINLESS outputs in the five-card review are numbered outputs in the accepted source. The fix preserves exact port identities, K annotations, multiple outputs, and raw source net membership. A genuine AP793 B10-to-unlabeled-input connection remains supported.

Independent verification passed all77 card-tool regression tests and10 additional schema counterexamples. The source-scope replay checked2195 published models,2307 UTF-8 transcriptions,232 reviewed card outputs and the exact65-file card-tool namespace. The five full derivations still report54 unresolved endpoints; these remain held rather than being called pinless or guessed.

The human confirmed DR191 D06 and K-marked B08 are wired together. Its existing source graph still records separate nets: this parser change DOES NOT repair that topology. The answer and native crop are preserved here for the separate source review. Internal-net assembly and routing changes remain held.

These are immutable copies of exact accepted tool/review/evidence artifacts. Only the three tools named by the accepted preparation are current production changes; snapshots under this folder are evidence. Original JSON records retain their original absolute/private references unchanged, while Evidence manifest.json maps the copies to their sources and hashes. Earlier v1/v2 revision-required results remain historical; no new source acceptance was created by this copy operation.
