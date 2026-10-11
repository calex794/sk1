# SK1-QUILL-EXP-PUB-T-1007 — two-stage Story replacement for Cloud Editor

[Canonical Notion task](https://app.notion.com/p/3f632a84beec81a6ac82f043e4ac9219).

**Scientific question:** The pinned Writer rejects a direct equal-length Story replacement (T982). Can two unchanged permitted Writer operations, with real intermediate Reader/Editor reopen, realize an exact Story replacement **A→B**: Original→delete A→insert B versus independent Original→insert B→delete A?

Predeclared 3 original SHA-pinned public 0x2C PUB from T982; first editable Story, second ASCII code unit at UTF-16 offset 1. Four printable replacement values: ASCII_UPPER (first distinct X/Q/Z), CYRILLIC_ZHE U+0416, CJK_IDEOGRAPH U+754C, NBSP U+00A0. No CR and no unvalidated controls. Exactly **12 direct guard attempts** and **24 independent two-step sequences**.

Only existing original Rust Writer/Reader/Editor from immutable read-only `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b` plus immutable SK1 T963 comparator at `2caeec283312b0865054ae6f5f93fc9ac1c76b9d` blob `b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92`. No alternative Writer or product modification. Every actual step checks source SHA, target Story, sibling SYID/text and byte-replayed EditorProject. Full final CFB/Quill byte-locality and both final SHA are compared; refusals also count as scientific outcomes.

**Safety:** no raw PUB, candidate files, Quill bytes, Story text, source download URLs, licensed binaries, or private resources in public reports. Only `plan.json`, `records.json`, `report.json`. A successful CI workflow is not native Microsoft Publisher acceptance and not a cloud Editor release claim. Independently audit artifact ZIP/hash/receipts and write final finding to Notion before marking DONE.

**No duplicate:** T956 tested inverse-to-original compositions; T982 tested direct 1→1 rejection; this asks about actual two-step **change to a different final character**. T1006 is separate native Publisher work owned by Local Codex.
