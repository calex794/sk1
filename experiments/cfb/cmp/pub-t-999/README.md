# PUB-T-999: how current Reader and LibreOffice compare to actual Publisher

Task https://app.notion.com/p/3f632a84beec8133ad7afef24f7e04b4

Do not conflate this visual experiment with PUB-T-997 (Quill TEXT fidelity). This experiment scores approximate 64x64 RGB page-raster distance to a registered authentic Publisher PDF output using the already pinned and CRC-protected source-free raster fingerprint in the RAR2 repository. No Microsoft Publisher executable is run.

Current real Reader data is source-free report from successful product Actions 38143407856, artifact 11704131725, ZIP SHA256 a6c1d4faa1b3aee07c48de9592e770ded1072ec07a52e0247cc94e039a578fab; the uncompressed exact summary.json SHA256 is 4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d. Product source a654d1af59be6173cd31ba3b7be37b1155a28ba5 is unchanged.

49 source public PUBs from Lalalalendia/lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea were identified before LibreOffice results. Six other registered native-PDF pair PUBs do not exist in this exact donor tree and are explicitly outside this denominator. All 49 content bytes and sizes must match the original RAR2 signed manifest. RAR2 original Publisher grids remain in RAR2, not copied into SK1.

Run exact real LibreOffice Draw PUB to ODG to PDF conversion. Rasterize PDF at 144 DPI RGB with PyMuPDF and Pillow BOX to 64x64. Invoke the actual source-pinned RAR2 compare_grid against the same source-free Publisher PDF grid. Grade reader versus LO only where the Reader, LO, and Publisher reference have the same page count and matched page sizes. The near-tie deadband is 0.015 changed cell fraction. Report LO conversion errors, physical page mismatch and output-stage uncertainty instead of marking those as losses.

CRITICAL CAVEAT: every native Publisher PDF page has reference_surface_stage=unknown. Both programs might render different output-surface semantics. Scores are ordinal-page coarse visual closeness, not PageList identity, native Publisher full-resolution equivalence, text-fidelity proof, authoring parity, or product superiority. The competitor's PDF export also introduces system font substitution. Interpret per-document and per-page causes.

Controls: 49 immutable identity checks, two repeated LO conversions, malformed CFB negative, exact reader summary SHA verification, exact Git blob pins and independent JSON checker. GitHub artifact contains only numerical results, hashes, status codes; physical PUB/ODG/PDF/PNG are generated and deleted in temp runner directories. No product RAR2 code is changed.
