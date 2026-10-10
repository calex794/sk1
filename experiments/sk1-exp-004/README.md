# SK1-EXP-004 — physical Quill anchor two-byte guard census

[Notion experiment log](https://app.notion.com/p/3f532a84beec81fda307fd18807f1117)

**Question:** Is the conserved +1-BMP growth guard that blocked 61 edits in EXP-003 explained by the exact **two-byte interval** that Writer would have to discard immediately before the first aligned FDPP/FDPC service anchor? Are those bytes inside a named Quill descriptor payload or outside known payload ownership?

This experiment is **read-only structural analysis**. The Rust program uses the existing `pub_cfb` and `pub_quill::parse_confirmed_story_catalog` from pinned `rar2@703808408fd919e564a90cdc236e81db3c04af8b` — there is no second Writer, no mutation, and no product or native Publisher approval.

## Why the question is new, not a duplicate

- [EXP-001](https://app.notion.com/p/3f532a84beec81ec9c63e9952fd3e0a3): observed basic Writer acceptance and failures on a public corpus.
- [EXP-002](https://app.notion.com/p/3f532a84beec81d6b406fc10231e1310): found position-specific deletion acceptance.
- [EXP-003](https://app.notion.com/p/3f532a84beec81ec92f9e64a490be67c): matched insertion/deletion, identified 61 growth-guard pairs in 30 Stories across 10 source files.
- [Historical synthetic capacity edge](https://app.notion.com/p/3e032a84beec81f1b19acee12a8f9a7d): isolated a related guard in one synthetic fixture. **EXP-004 neither repeats this synthetic test nor expands Writer scope.**

The **new discriminator** is a source-SHA matched read-only structural observation across 26 independent real PUB, split into 10 known growth-guard sources, 13 eligible observed growth-allow sources, and 3 sources with no eligible EXP-003 edit.

## Exact measurement

For each SHA-validated public PUB, decode the Quill stream with existing parser, measure:

1. TEXT byte end, FDPP/FDPC earliest aligned service anchor (0x200 alignment), gap.
2. Source-byte nonzero count in `[anchor - 2, anchor)`, i.e., discard interval for an insertion of one BMP code unit.
3. Number of consecutive trailing zero bytes before the anchor, clamped to the pre-anchor gap.
4. Whether this two-byte interval overlaps a known **descriptor payload**, and which **approved descriptor type** (STSH, etc.) is mapped there. Descriptor type is structural provenance only, **not semantic ownership or permission to rewrite**.
5. The exact existing guard's *local* prediction: nonzero protected tail, named payload overlap, insufficient gap, or tail clear.

The original files and all raw Quill bytes are destroyed with the runner's temporary directory. Reports include **counts/offsets/known tags only**, no raw two-byte values, Story text, or mutated PUB.

## Pre-registered labels and falsification

The 10 SHA labels come only from [EXP-003 verified source-safe artifact](https://github.com/calex794/sk1/actions/runs/38078248161/artifacts/11679124237) (ZIP sha256 `d8c02e32a9927077eaf6ec740375841e53b1db42a384bb4d1d0f957e39a9182c`). The 3 no-eligible labels are kept **out** of the sensitivity/specificity denominators. All 26 SHA input rows and all 10 observed growth-blocked cases must be accounted for.

Compare expected versus static NONZERO_UNKNOWN_ANCHOR_TAIL in a 23-source confusion matrix (TP/FN/FP/TN), and separately record unnamed vs named-descriptor payload overlaps. A false positive/negative is evidence, not a reason to change Writer or silence the result.

**Interpretation:** even a matching physical two-byte predicate is an explanation of *this guard path at this pinned commit*, not proof that the protected bytes can be relocated, removed or regenerated. A tail that appears all-zero does not authorize native Publisher Save/Download; independent FD/BTE/TOKN/service-metadata and lifecycle gates remain.

## Reproduce

[GitHub Actions workflow](https://github.com/calex794/sk1/actions/workflows/sk1-exp-004.yml) compiles the small read-only Quill inspector inside an ephemeral pinned `rar2` checkout. The intake reuses EXP-001's pinned manifest, HTTPS host allowlist, 12MiB/file and 120MiB total limits, byte-length + SHA-256 checks and no private files. Only `plan.json`, `records.json`, `report.json` source-safe artifacts are uploaded **after schema gate validation**.

**Transfer contract:** conclusions and negative evidence go to Notion. Code stays disposable in SK1. Any potential `rar2` regression-test adoption requires a separate task-owner decision.
