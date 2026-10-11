# PUB-T-1000 — why visual quality of 022 regressed despite JPEG fix

Task: https://app.notion.com/p/3f632a84beec8169a11cde4b9789ff6b

## Distinct experimental question

PUB-T-999 compared current secure RAR2 Reader against LibreOffice, based on the same original Publisher PDF 64x64 grids. That measurement is real and still valid as a *current browser appearance* result. It is not an isolated parser-quality comparison: the intentional WEB-SECURITY F rule in product [#2586](https://github.com/Lalalalendia/rar2/pull/2586) forbids untrusted original embedded image bytes in the browser.

Product [#2433](https://github.com/Lalalalendia/rar2/pull/2433) earlier enabled an oversized source JPEG in 022 by raising JPEG-only cap 4→5MiB. The verified real Browser source 022 Publisher difference improved 3817→462 changed grid cells on 2026-10-09. Product security merge ea5689c6 on 2026-10-11 deliberately disabled *all source_exact* original image transfer; current Reader shows 3817 again for 022.

## Exactly pinned material (no raw files)

All inputs are existing source-free published action artifact JSON, not raw PUB, PDF, JPEG, screenshots or Story text:

- RAR2 real Browser before new security rule: source 30a7bf813cb47198b2a70821564846ca49d640e1, Actions 37935975286, artifact 11618761670, zip SHA256 d286d77845f0d5b7ca2eb0ada3276a033e125747199804c42d93808dbe582f92, uncompressed summary.json SHA256 142d29a71c1936d322431200832010fffe97e5859729ab66c6c6ca909b628e45.
- RAR2 real Browser after security rule: source a654d1af59be6173cd31ba3b7be37b1155a28ba5, Actions 38143407856, artifact 11704131725, zip SHA256 a6c1d4faa1b3aee07c48de9592e770ded1072ec07a52e0247cc94e039a578fab, uncompressed summary.json SHA256 4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d.
- SK1 PUB-T-999 actual LibreOffice PUB→ODG→PDF: Actions 38145210671, artifact 11704247616, zip SHA256 228d9833e65d491a865754a132e358b317dda64c2432c21ac1d7cca2a4fc261c, report.json SHA256 2f3f1bcddaa6aa094b46893825593d9aef4789b6960620dfdaf8d01a6af5b5fd.

The security merge commit ea5689c6a1fff065297fa3ff3e84a153ed81ecfe has exact parent 22a322ed10d9fe8a4ade45acf83bebd0442b691b; the one and only changed file is apps/chaptera-server/src/reader_scene_v1.rs. The source diff sets browser_inline_safe = !image.source_exact and adds source_exact_browser_denied; the source JPEG 5MiB limit remains unchanged. This static check is performed against the pinned Git commits in CI, not merely from copied prose.

## What this proves and does not

On exact 55 public source PUB identities and exact 162 matching Publisher-grid page identities, 90 pages have more material-different 64x64 cells in later Reader, 1 less, 71 unchanged, total +47,869 changed cells. On the exact 111 LO-compatible ordinal pages, re-score *the same unchanged LO outputs* against older RAR2 Reader results: LO48 / Reader36 / near tie27; with current secure Reader it is LO85 / Reader17 / near tie9. Document majority order also changes. The older Reader is a different product SHA separated by many commits; this is NOT an isolated source-only controlled experiment for all changed pixels. Do not attribute all 90 pages to the security commit without a one-change live Browser A/B.

## Safe implementation boundary for product owners (not executed in this SK1 task)

Do not undo #2586 or bypass the post-worker host validator #2583, or copy original JPEG/PNG under a different SourceExact marker. In the isolated worker, use a bounded untrusted-image decoder with allowed codec / pixel / duration / RAM limits, then make a new sanitized and deterministic image derivative (sRGB/alpha/orientation explicit; EXIF/XMP and comments removed; new byte digest and versioned recipe). The sanitized host must independently validate newly encoded bytes and explicit SafePreview authority, and cap aggregate Scene to 16 MiB and each resource. Missing or dangerous images remain descriptor-only/Partial.

Use existing owners IMAGE-DECODE-CONTRACT-01, IMAGE-DERIVATIVE-01, IMAGE-DERIVATIVE-ENCODE-01 and WEB-SECURITY-01, not a parallel renderer. Verify actual exact 022 image and 001/023 image controls; run real 55/162 browser Publisher reference A/B and negative tests for CMYK, malformed, decompression bombs, alpha, metadata, cross-tenant and source-origin leakage. A reusable safe preview must preserve separation of source original ResourceId, derived artifact hash, and document scene references.

The only SK1 uploads are source-free report JSON and source-safe validity results. No product code changes are part of this task.
