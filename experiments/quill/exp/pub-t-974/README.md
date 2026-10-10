# SK1-QUILL-EXP-PUB-T-974 — source-disjoint blind growth test
Task: https://app.notion.com/p/3f532a84beec81659a23d61867a9bfda

* Independent 28 SHA-256 source files from immutable lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea, selected across 16 HTTPS hosts **before Writer output**.
* Exclusion: original 35, old holdout 62, T968 27, T969 27 and T970 27; no source replacement upon download failure. Source cap 2.5MB, cohort < 50MiB.
* Fix original Reader/Writer/Editor rar2@703808408fd919e564a90cdc236e81db3c04af8b; +16/+64/+192 ASCII UTF-16 edits from original file; up to 3 Stories, 4 positions.
* Predict first guard source-only **before** any Writer attempt: TOKN, FD, CAPACITY, GROWTH_UNKNOWN, GROWTH_DESCRIPTOR or PASS; compare with exact codes and retain all mismatches.
* Admission ≥10 SHA-evaluated independent PUB and ≥120 comparable arms. Report **positive growth coverage** separately, including zero if none.
* Only aggregate, SHA, numerical offsets and safe status codes in Actions artifact; do not publish PUB bytes, Story text or URLs. Never claim Publisher-native support or modify product.
