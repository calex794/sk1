# PUB-T-982 — equal-length 1→1 Quill Writer replacement

[Canonical Notion task and preregistered protocol](https://app.notion.com/p/3f632a84beec81b796f9eeadb6a099e6)

**New question:** Can the pinned mature-0x2C Writer replace one existing ASCII-alphanumeric UTF-16 code unit with another one-unit codepoint without moving text/FD service positions? Can it then restore that codepoint without any residual whole-PUB byte differences except the SYID lifecycle header +2?

This is different from PUB-T-963 insert/delete inversion and PUB-T-978 **insertion** of controls. It does not claim native Microsoft Publisher acceptance.

Three exact public source SHA reused from the verified PUB-T-965 original manifest, original SYID headers 22, 12, 2. On each one: first eligible Story; second ASCII character at exact UTF-16 offset 1. Baseline +1/−1 in both orders must independently pass before experimental arms.

Exactly 8 named same-length replacement values per real source: ASCII_UPPER (first distinct X/Q/Z), CYRILLIC_ZHE (U+0416), CJK_IDEOGRAPH (U+754C), NUL (U+0000), TAB (U+0009), LF (U+000A), LINE_SEPARATOR (U+2028), CR (U+000D). The original character is always ASCII. All 24 one-way arms are evaluated and all first-pass arms are independently reversed.

Each Writer step validates source immutable SHA, EditorProject byte-equal replay, Reader reopen, correct target Story, sibling Story identities and contents. The actual first edit is compared against original by full-PUB raw bytes and logical CFB/Quill differences. Each successful inverse final is compared to original by full-PUB absolute byte differences and chunk histograms. A counterexample or guard is recorded as a scientific outcome, not silently dropped. Only three source-safe JSON are uploaded.

The original Writer **and** the existing T963 physical Quill comparator are pinned, not copied: [T963 scientific commit](https://github.com/calex794/sk1/commit/2caeec283312b0865054ae6f5f93fc9ac1c76b9d) and `inspect_inverse.rs` Git blob `b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92`; pinned [rar2](https://github.com/Lalalalendia/rar2/commit/703808408fd919e564a90cdc236e81db3c04af8b). Only the T982 matrix/logic is additional. Original or changed PUB text and bytes never become artifacts; no product modifications.

[GitHub Actions workflow](https://github.com/calex794/sk1/actions/workflows/sk1-quill-val-pub-t-982.yml). Do not treat an Actions success as publication until the original archive and JSON have been independently audited and the conclusion is transferred to Notion.
