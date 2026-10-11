# PUB-T-1003 — independent natural 60685.pub Rust Reader alignment 0x0102

Canonical Notion Task: https://app.notion.com/p/3f632a84beec818fa9a6f7d911a42ab6

Preceding T1001 verified style census: https://app.notion.com/p/3f632a84beec8150bf08e82eb1f87228

Same technique as T998 but a **different public original and a different nonzero high byte**:
- Original Apache POI 60685.pub, `apache/poi@942d95d85b15d0dfdb3bc9ba1b4f273f277757c8`, Git blob SHA-1 `37d3dce70e1786e948edd5592527f90be1fae2ff`, SHA-256 `0d3cecf0ff000a20931d0de3ebc48040bea10e03833ade3f9902f996c20e7184`, 119296 bytes, one source, no source re-selection. The source's 36 STSH1 paragraph defaults include #21/#23 raw id0x04/type0x12/value 0x0102, plus #4/#5 with value 0x0002.
- Exactly three unique FDPP references select #21,#21,#23, with no explicit alignment override and last three UTF-16 unit ranges of one character each. Source Story lengths 1882,1,1,1 are predeclared.
- A/B arms: original; **change only 2 high bytes** 01→00 (0x0102→0x0002); **change only 2 low bytes** 02→00 (0x0102→0x0100). Input physical byte diffs must be 0/2/2, identical CFB length and all Quill streams outside changes.
- Build **real** unchanged `pub-viewer::open_pub_geometry` from pinned `rar2@b224a614af48c273b2d4bc0881793cf0217cc16d` and disposable Rust measurement helper previously used in T998, not a duplicate product implementation.
- Compare ViewerParagraphAlignmentRun **multisets of stable numeric projection attributes** to avoid source-dependent canonical Story IDs. Expected gain: three separate Right ranges 0..1, valid source references, while low-zero matches original. If different, report HYPOTHESIS_NOT_CONFIRMED_ON_SECOND_SOURCE, not false success; if missing admission, NOT_EVALUATED.
- No Microsoft Publisher-native save or visual parity claim; all input PUB, mutated PUB, Quill and Story text remain in CI temporary storage and are deleted on job exit. Artifacts contain numeric counts and source SHAs only. `rar2` remains unchanged.
