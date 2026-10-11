# PUB-T-1001 — natural 21-PUB STSH1 alignment 0x204 high-byte census

**Canonical task:** https://app.notion.com/p/3f632a84beec81e581deca84b652ce1c

**Prior one-source causal Rust T998:** https://app.notion.com/p/3f632a84beec81498ea8c51e8b69ad54

This experiment asks only about **prevalence**, NOT a new Reader or native Publisher:
- Use the unchanged T997 22-file manifest `Lalalalendia/rar2@b224a614af48c273b2d4bc0881793cf0217cc16d`, blob `4e77d912e7a104cc192be5e6504892c295c1db01`. Exactly 21 semantic original public Apache POI PUB; exclude exactly one adversarial fuzz from format statistics but still verify its source SHA/length. Fixed upstream `apache/poi@942d95d85b15d0dfdb3bc9ba1b4f273f277757c8`.
- Parse with **unaltered** pinned T994 typed Quill/CFB helper `calex794/sk1@87a6733516ad6ffd1b6b97a3176f359bfeb60ca1`, blob `cd92e00942f0a6949e72785bb1605fb70620de22`; no second implementation of the whole Quill reader.
- Count only STSH1 odd paragraph default records with exact raw id 0x04 / wire type 0x12, 2-byte value. Categorize u16 as high=0/low in 1..4, high!=0/low in 1..4, invalid low. Ambiguous or duplicate alignment properties remain separate, fail-closed.
- Separately count **live referenced FDPP styles** only where the exact 0x19 / 0x1A selector is unique and there is no direct FDPP 0x04 override. This is just source-linked evidence, not evidence of the Publisher visual effect.
- Source `51318.pub` belongs to the fixed 21; count it **once**, not as new independent T998 confirmation. Its expected control: 5 paragraph styles, four raw 0x5A02, two selected source style records, no explicit override.
- Original corpus always read-only; source data in hosted runner temporary paths. Public artifact is source-free numeric JSON and fixed public filenames/checksums: never upload PUB/Quill/Story text, ODG, or raw unknown property values.
- Report all missing/unsupported parse cases as NOT_EVALUATED; don't promote limited coverage to a universal rule. Product `rar2` must remain unchanged.
