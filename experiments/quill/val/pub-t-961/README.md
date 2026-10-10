# SK1-QUILL-VAL-PUB-T-961 — UTF-16 BMP glyph substitution vs ASCII Writer outputs

**Canonical Research Task:** [PUB-T-961](https://app.notion.com/p/3f532a84beec81d78856e5a60a7fea6f) **Agent Run:** [PUB-RUN-753](https://app.notion.com/p/3f532a84beec81068bf4e31d4a47d9e8)

## Independent question

Prior PUB-T-956 proved a set of 77 previously successful one-code-unit ASCII source Story insertions, and its successors measured inverse operation behavior; no prior SK1 task compared **different Unicode glyph identities at the same source/Story/UTF-16 offset** with identical Writer operations and raw logical-Quill output bytes. PUB-T-959 is a different physical CFB deletion experiment on EXP005 holdout and PUB-T-960 tests two sequential cross-Story deletions. This task performs neither.

## Immutable witness manifest and comparator

- [EXP-956 Actions #38083249275](https://github.com/calex794/sk1/actions/runs/38083249275), exact research SHA `08abf5c7d92fb5ca56fd3ff84009309120fcf52c`, [source-safe artifact #11680967998](https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998), ZIP SHA256 `afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427`.
- `witnesses.json` contains precisely 77 *already proven* successful ASCII insertion slots across **13 source SHA / 34 eligible Story**. The pre-registration maps full `source SHA` to `[eligible Story ordinal, first/second/middle slot, UTF16 offset, original Story UTF16 length, original ASCII character count]`; SHA256 `c7a74f2fe7e1f72b4400628705d9f5eb7640ba95c9a1ff5b8292bddd579d904b`. **These are correlated reused specimens, not 77 independent PUB.**
- Public intake is only the previously approved SHA/size/HTTPS CFB manifest in EXP001; all 13 sources must match exactly, no partial denom. Original Writer/Reader/Editor `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b` is pinned immutable, with experimental example copied to the temporary checkout; never modify or patch upstream implementation.

## Pre-registered glyphs (fixed inputs, not corpus text)

- ASCII baseline: exactly the original EXP956 marker selection X/Q/Z and insertion offset, requires `HOSTED_PASS` and exact fresh Reader/Editor/SYID sibling + EditorProject byte replay.
- 4 BMP one-UTF-16-unit variants: `LATIN1_E_ACUTE` (U+00E9), `CYRILLIC_ZHE` (U+0416), `CJK_ZHONG` (U+4E2D), `COMBINING_ACUTE` (U+0301). Each independent insertion starts with the same original and uses the identical offset, fresh Editor session and canonical Writer.
- 1 two-UTF-16-unit negative-control variant: `ASTRAL_GRIN` (U+1F600). The pinned Writer has an explicit non-BMP replacement guard; validate real machine error without bypass. Different UTF16 length means this is **not** evaluated by the one-unit byte comparator.

## Measured observables

Each Unicode Writer receipt includes HOSTED_PASS or safe rejection code; PASS already means Reader reopened the exact expected string, non-target Story texts preserved by raw Quill SYID, source SHA invariant, and byte-identical EditorProject replay. For every BMP PASS, compare two independent complete candidate PUB outputs from the **same source**: original ASCII marker vs alternate Unicode glyph. Read-only CFB inspection records added/missing paths, entry-kind and non-Quill stream differences. Read-only Quill descriptor/parser comparison localizes changed byte positions to the **exact two-byte UTF16 inserted TEXT unit**, verifies glyph code unit at that position, unchanged descriptive offsets, Quill SYID high-water scalar, Story SYID sequence and UTF16 lengths.

Counterexamples are valid findings: if non-TEXT Quill changes, if Unicode output is rejected, or if CFB non-Quill payload changes, report it. Do not force a perfect predicted match in CI. The strict evidence gate requires 13 SHA-verified sources, exactly all 77 witnessed slots and all 385 alternative unicode arm outcomes, no dropped cases; metadata and report independently recomputed. Artifacts: ONLY `plan.json`, `records.json`, `report.json` after validator. PUB bytes, story strings, raw UTF16 payloads, raw errors, unknown names and private URLs never leave CI ephemeral storage.

## Limitations

Can describe only the tested **hosted Writer's logical-byte behavior** for four BMP characters on 77 pre-registered edit slots. Cannot claim Microsoft Publisher Open/SaveAs/Reload, native glyph/font coverage, grapheme normalization, rendering or any product Download authorization. `rar2` is unchanged; integration belongs to its separate agent under a different task/authorization.
