# SK1-EXP-001 — independent PUB Writer applicability

**Stage:** automated GitHub Actions experiment submitted; no results are claimed until verified.

- **Experiment journal:** https://app.notion.com/p/3f532a84beec81ec9c63e9952fd3e0a3
- **Canonical implementation (read-only):** https://github.com/Lalalalendia/rar2
- **Pinned canonical SHA:** `703808408fd919e564a90cdc236e81db3c04af8b`
- **Existing, excluded from new evidence:** https://github.com/Lalalalendia/rar2/pull/2505 (4-fixture preflight)
- **Corpus source:** `tools/corpus/receipts/lalamu-materialized-35-input-2026-09-29.json` at the pinned upstream SHA. All entries have source SHA-256, size and provenance. Only admitted hosts and source files under 12 MiB are selected. Real eligible count is reported in `plan.json`, not preclaimed as 35.

## Experimental question

For independent validated, naturally occurring public .pub sources, can the CURRENT Reader+Editor+Writer serialize two bounded types of ordinary Story edit? Does one ASCII-unit deletion behave differently from one-unit substitution?

**No Writer implementation is copied**. The Rust program links against the upstream Editor/Writer via the upstream Cargo example workspace. Its only task is to orchestrate measurements. It is copied into an ephemeral checkout in GitHub Actions.

## Two independently constructed arms

- **A:** replace the first ASCII alphanumeric character in an editable Story with a different ASCII character. UTF-16 count unchanged.
- **B:** delete the first ASCII alphanumeric character in the exact same source Story. UTF-16 count decreases by one.

For at most three source-authorized Stories per input, the code uses `can_replace_story_text`, canonical `replace_story_text`, the actual Writer, Editor reopening, matching target Story text, exact replay of EditorProject into byte-identical candidate, source immutability, and stable unaffected Story identities/text where supported. It never edits source bytes on disk in place.

A successful **hosted** run is NOT a Microsoft Publisher acceptance; it never updates any product save/download permission. Source and candidate .pub binaries and story contents are not uploaded.

## Reproduce in GitHub Actions

Run `SK1 EXP-001 Writer applicability` on the main branch. The workflow also runs on changes to this experiment. Only the pinned upstream checkout is used; all generated source/candidate .pub files exist in a temporary directory and are deleted after processing.

Raw corpus retrieval is bounded by:
- HTTPS public unauthenticated direct `.pub` URLs from the pinned manifest;
- explicit domain allowlist and redirect restrictions;
- exact size and SHA-256 match before processing;
- per-file 12 MiB / total 120 MiB limits, 45-second request timeout;
- no customer/private files, no licenses/runtime copies, no tokens, no external source execution.

The script runs and emits a per-file evaluation record; missing/unavailable/disallowed sources remain NOT_EVALUATED, never counted as Writer failure. The original Sample3 fixture is a calibration control; its known accepted hash must agree exactly but isn't included in the new statistical sample.

## Source-safe outputs

- `plan.json`: eligible source SHA IDs, sizes, pinned upstream commit (no untrusted bytes);
- `records.json`: status per SHA and independent A/B observation;
- `report.json`: aggregate counts, per-case exceptions, machine Writer code and bounded interpretation.

`check_report.py` rejects unexpected fields, source text, non-hex hashes or unbounded error strings. Console logs must not include raw Story text or private paths.

## Conclusions / transfer contract

After verifying the completed run in Actions, log outcomes in Notion. A useful new test/hypothesis/algorithm is eligible to be separately reviewed for transfer to `rar2`. Negative results and newly verified limitations are portable Notion knowledge. **Never infer universal Writer support from raw pass rates or call hosted Reader reopening native Publisher proof.**

## Limitation

The 35-source pinned manifest includes URLs outside the initial allowlist and >12 MiB files; these are deliberately excluded in V1 rather than weakening privacy/source control. To broaden the study, prepare a separately reviewed manifest/host-allowlist revision; don't silently change the denominator.
