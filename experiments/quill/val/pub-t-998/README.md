# PUB-T-998 — actual pinned Rust Reader STSH1 0x5A02 / 0x0002 / 0x5A00

Canonical Research Task: https://app.notion.com/p/3f632a84beec81cdb360c2124c789a25
Prior physical-source and LO experiment: https://app.notion.com/p/3f632a84beec81b9962aca87d24b12bd

This is one preselected public Apache POI source, **not three independent original PUBs**. Pin `apache/poi@ae62bb5116b9aee19ebd5834e3a82066132c9f7f`, file `test-data/publisher/51318.pub`, original blob SHA-1 `728811c92dff5694520e56b6c020533b29d5295d`, 88576 bytes. Use pinned `Lalalalendia/rar2@b224a614af48c273b2d4bc0881793cf0217cc16d`; no product commits or competing Reader. Reuse the rigorously checked T994 CFB parser at SHA `87a6733516ad6ffd1b6b97a3176f359bfeb60ca1`, script blob `cd92e00942f0a6949e72785bb1605fb70620de22`.

Physical source before testing: SYID IDs 2/3; STRS lengths 22/36; exactly two FDPP ranges, selecting STSH1 paragraph styles 1/2, neither with explicit paragraph alignment. Four STSH1 paragraph styles 1…4 store actual raw id0x04 / type0x12 / 0x5A02. Only four high or four low bytes are changed in separate in-memory/temporary variants; exact CFB physical size and all other bytes must stay fixed. No native Publisher save/acceptance; existing T996 LibreOffice evidence is not independently re-run.

Compile actual `pub-viewer::open_pub_geometry` in GitHub-hosted Rust, with an ephemeral, source-safe measurement binary. Report per-Story alignment run counts, ranges and numeric source values only. Public artifact must never include original or mutated PUB, text, ODG, raw Quill payload, or derivative image. The test's useful discriminant is **whether the original has zero aligned Viewer runs while a high-byte-only change creates two valid Right runs and a low-byte-only change still creates none**, with the same Story and page identities.

No blanket product patch or global high-byte masking is authorized. If the code outcome is different, report the bounded counterexample; if the Reader rejects a variant, report NOT_EVALUATED.
