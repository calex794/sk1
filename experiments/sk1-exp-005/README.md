# SK1-EXP-005 — External holdout for Quill growth-guard predictor

[Notion experiment and durable knowledge log](https://app.notion.com/p/3f532a84beec81c2a98ef2d6629a54d9)

**Hypothesis:** the source-level nonzero two-byte Quill service-anchor tail predicate from EXP-004 predicts `quill_growth_would_discard_unknown` for +1-BMP edits on **independent previously untested PUB files**.

## No duplication
We reuse exactly [EXP-003](../sk1-exp-003/) and [EXP-004](../sk1-exp-004/) Rust binaries on one immutable `rar2` SHA (703808408fd919e564a90cdc236e81db3c04af8b), and do **not** implement or change a Writer. All Q001–Q004 tasks in the regular Notion Research queue remain parked and separate.

## Pre-registered independent input
- Historic public CommonCrawl rehydrated manifest with **370 SHA-identified files**, pinned to `Lalalalendia/lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea`, `pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json`.
- Deterministically select 62 sources across 7 explicitly whitelisted HTTPS hosts (30 Mathematicshed, 8 Anyssa, 8 Google public storage, 6 Duke Law, 5 Greville school, 3 Instructables CDN, 2 BNS Sports), sorted by SHA within host and bounded at 2,500,000 bytes/file (36,377,600 total expected bytes). Exactly exclude all **35 SHA** in EXP-001–004 intake manifest, not merely 26 admitted.
- At most four source requests run concurrently (each isolated in its own temporary directory); outcome order is deterministic by pre-registered SHA. All requests are anonymous HTTPS direct `.pub` with no query; no credentials, redirects off host, private addresses or arbitrary new hosts. Verify expected SHA-256, exact byte size, CFB signature before any parser probe. Source drift/unavailability are separately `NOT_EVALUATED` and excluded from accuracy denominators. No customer/private files.
- Fail closed for fewer than 15 verified sources or fewer than 10 comparable independent source-level observations. Host strata and inaccessible cases are reported; **do not silently refill missing sources**.

## Matched measurement
- Read-only static 2-byte Quill tail inspector classifies `NONZERO_UNKNOWN_ANCHOR_TAIL` vs `TAIL_TWO_BYTES_CLEAR_ONLY`.
- Canonical Writer/Reader+EditorProject probe attempts independent one-char deletion and insertion at second ASCII alphanumeric position, choosing distinct marker, via original source bytes. Only a pair with **deletion HOSTED_PASS** and either **insertion HOSTED_PASS** or the exact `quill_growth_would_discard_unknown` outcome is discriminating. Other failures remain their own category, not false negatives.
- Compare **per-source** TP/TN/FP/FN first, flag mixed Source outcomes; per-Story pair table is reported separately as correlated observations. Counterexample receipts contain SHA and Story ordinal/UTF16 offset, never Story text.

## Transfer
Results belong permanently in Notion, including negative/partial results. This tests the external validity of the predicate only. Even a perfect match is not a semantic decoding of unknown Quill bytes, Microsoft Publisher native Save/Reload evidence, or product Save/Download permission. Any later test/diagnostic in `rar2` requires its owner's decision; **SK1 does not have a second product implementation**.

[Actions](https://github.com/calex794/sk1/actions/workflows/sk1-exp-005.yml)
