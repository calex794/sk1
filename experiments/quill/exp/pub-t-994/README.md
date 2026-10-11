# SK1 QUILL EXP PUB-T-994 — live LibreOffice import vs 0x30 byte changes

Task: https://app.notion.com/p/3f632a84beec81889aaef602fc832135

Runs **real LibreOffice/libmspub** on two public Apache POI samples with naturally occurring nonzero upper bytes in STSH1 id0x30. This is not Microsoft Publisher and does not open the user's private PUB archive.

Pinned inputs: apache/poi@ae62bb5116b9aee19ebd5834e3a82066132c9f7f; `60685.pub` Git blob `37d3dce70e1786e948edd5592527f90be1fae2ff`, `51318.pub` blob `728811c92dff5694520e56b6c020533b29d5295d`. Runner verifies native Git blob SHA-1 and physical size before processing.

For each source, strictly parse STSH1 indexed paragraph properties, locate the first naturally present `id0x30` with absent `id0x13` and observed upper byte `01` / `5A`, then build same-length CFB clones: first high→00, first high→FF, all matching natural high→00, STSH1 header +8 XOR5A, all STSH0/1/2/FONT header +8 XOR5A. Two independent bit-identical baseline imports detect nondeterminism. A wide, length-preserving TEXT-character rewrite is an explicit **positive sensitivity control**, a broken CFB signature is the **negative**. Only a stable baseline with nonempty imported text, visible positive text change, and rejected negative makes a SAME_PROJECTION conclusion interpretable.

Output: **only** `report.json`, numeric counts, independent hashes, PASS or support classes. CFB inputs, candidate PUBs, imported ODG and text remain transient in the GitHub host filesystem, never uploaded. A source success does not establish an unknown field is semantically inert for Microsoft Publisher. Even if an external importer is insensitive, the Writer must preserve unknown raw bytes.

Static source comparator: LibreOffice/libmspub@2b094242f97923f918972d5f1bfd26cd915f836c, `MSPUBParser::getParagraphStyle` explicitly handles `PARAGRAPH_SPACE_AFTER = 0x13`; 0x30 is not mapped in its switch and defaults to skip. Installed LO version is reported separately and may not equal this source commit.

SK1 only. Product `Lalalalendia/rar2` is not changed. No native runtime, no manual actions, no external input besides pinned public data.
