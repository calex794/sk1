# PUB-T-997 — one fixed public 22-PUB corpus, two real reader engines

Canonical task: https://app.notion.com/p/3f632a84beec81d6a7c2dd4b134cf858.

This experiment does NOT assign native Microsoft Publisher truth by majority vote. It compares **actual** (1) RAR2 `pub-viewer::open_pub_geometry` source graph/Viewer structural receipt, and (2) LibreOffice Draw's PUB importer to ODG, on **the very same bytes** for 22 existing Apache POI corpus fixtures (21 semantically ordinary, 1 adversarial fuzz negative).

The manifest is reused from the exact RAR2 product repository: `tools/reader_corpus_manifest_v1.json`, Git blob `4e77d912e7a104cc192be5e6504892c295c1db01`, pinned product commit `b224a614af48c273b2d4bc0881793cf0217cc16d`. The official Viewer receipt source Git blob is `d57ea6b07e62751b65790238b1a374275dbb2199`. On GitHub-hosted Ubuntu the actual Rust Viewer binary is compiled (no source clone). A temporary probe is added to the **runner checkout only** to retrieve source-backed `document.stories.text` and page/shape metadata. Its raw text file is ephemeral and **must never be uploaded**. Python computes only casefolded Unicode text token overlap counts, then wipes temp sources/ODG/text probe.

Source files are verified by exact SHA-256 + length from RAR2's existing public manifest (Apache POI SHA-pinned source), and rehashed to check they were not changed. Chaptera's source-free official receipt must agree with the temporary Viewer text probe on open state and structural counts.

Comparable axes: per-input support/open, output page counts (with source-vs-rendered-page-role caveat), text-token bag intersection. Diagnostic descriptive but **not** comparable as evidence of fidelity: Story counts vs ODG paragraphs, image-resource counts vs draw:image, scene nodes vs ODG shape nodes, font runs vs ODF styles. Detect exact source-specific open disagreements and text gaps; these are candidates to investigate, not format laws or Publisher visual verdicts.

Two representative same-input repeat controls (one modern, one legacy), one invalid CFB signature negative, exact file count and digest/structure gates. Detailed results retain filenames and numerical counts only. No raw PUBs, text, ODG, PDFs or images leave GitHub's ephemeral runner. Run only in SK1 scientific branch; `Lalalalendia/rar2` remains unchanged.
