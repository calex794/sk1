# SK1-QUILL-DIAG-PUB-T-958 — Why two reverse insertions hit FD boundaries

**Canonical task:** [PUB-T-958](https://app.notion.com/p/3f532a84beec81de8979ed991021c233); approved by Supreme Operator's direct continuation `дальше`. Separate from concurrent [PUB-T-957 CFB/Quill drift analysis](https://app.notion.com/p/3f532a84beec81adbc4fe3bed705d7a9).

## Question

[EXP-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd) found 77/77 successful insert→reopen→delete inverses and **75/77** successful delete→reopen→insert inverses. The two negative outcomes were `quill_insertion_at_fd_boundary` even though insertion and deletion were individually accepted from the original PUB.

**New observation:** Inspect the *actual intermediate PUB after deletion*, BEFORE reverse insertion, and read only the numeric FDPP/FDPC boundaries. Does the reverse insert start coincide with FDPP/FDPC at exactly two blocked cases and none of the 75 successes? Is the old-to-new boundary shift the exact pinned Writer formula `boundary >= deletion_end ? boundary - 2 : boundary`?

## Reproducible protocol

- Immutable upstream Writer/Editor/Reader/Quill: `rar2@703808408fd919e564a90cdc236e81db3c04af8b`. This experiment does **not** amend Writer or bypass boundary guards.
- Same SHA-verified 26 public sources and 194 selected offset baselines from EXP-956; 77 both-successful independent insert/delete base pairs over 34 Stories from 13 PUB. Baselines are admission control, **not new findings**.
- The diagnostic copies the previously validated Writer application/reopen/SYID/replay helper and adds a **read-only numeric inspection** of existing Quill descriptor metadata and `FDPP`/`FDPC` arrays: original source vs actual *delete-only* Writer candidate.
- Each source/Story/case uses identical original SHA, Story ordinal and UTF-16 offset. The reverse insertion is actually attempted on the intermediate PUB with existing Writer. Numeric FD `hit` is computed directly from Reader catalog text_source.offset + UTF-16 offset and the stored FD array; **not** from the returned Writer error code.
- For every baseline both-PASS pair: record source FD-at-start, source FD-at-deleted-end, post-delete FD-at-reverse-start, counts, nearest FD boundary distance, and byte-shift consistency across arrays. Compare FD hit to actual Writer outcome with TP/TN/FP/FN/OTHER.
- Strict source-safe checker validates 26 sources/65 Stories/194 offsets/77 doublepass, each individual step, FD receipt schema, and recomputes the summary from source-safe `records.json`.
- No raw source/candidate PUB or text/unknown bytes/URLs are saved to GitHub; only SHA, Story index, numeric offsets, counters/booleans and bounded machine error codes. Native Publisher acceptance, semantic FD meaning and all product Save/Download guarantees remain `NOT_EVALUATED`.

## Hypotheses and scientific boundaries

Expected H1: exactly two intermediate FD hits, both correspond to `quill_insertion_at_fd_boundary`, 75 non-hits correspond to a successful reverse insertion; source had no FD boundary **at insertion start**, but the first edit's endpoint may have been exactly on one.

Expected H0: one or more mismatches or unaccounted Writer blockers. H0 also gets a verified report, not a fabricated PASS.

Since the Writer code explicitly rejects `edit.delete_utf16==0 && boundary.value==edit_start`, a perfect confusion matrix is **mechanistic validation for these Writer-produced intermediate files**, not an independent discovery of Microsoft Publisher's FD semantics.

## Proof/transfer
See GitHub Actions [SK1 QUILL DIAG PUB-T-958](https://github.com/calex794/sk1/actions/workflows/sk1-quill-diag-pub-t-958.yml); full result and permanent knowledge will be recorded in canonical [Notion PUB-T-958](https://app.notion.com/p/3f532a84beec81de8979ed991021c233). No merge to rar2.
