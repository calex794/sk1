# PUB-T-963 — whole-file raw residue of hosted inverse edits

Canonical Notion task: https://app.notion.com/p/3f532a84beec8188a69de0e5ba82b601

New measurement: compare original full PUB bytes with each of 152 successful two-step Writer semantic inverse outputs, not just logical CFB/Quill streams.

Baseline/admission and exact pinned Writer are inherited from verified T957; 26 source SHA / 65 Story / 194 offsets / 77 single-operation double-PASS; 77 insert->delete + 75 delete->insert.

Track same-length byte mismatches, trailing byte count, and exact conjunction of single SYID change and whole-file mismatch. Negative outliers remain in source-safe JSON. Neither synthetic mock Writer nor product/native validation; rar2 untouched.

Run branch workflow sk1-cfb-val-pub-t-963.yml. Each final report is independently checked. Original PUB and raw Quill/text never appear in public artifacts. Scientific result is NOT_EVALUATED until successful execution and independent audit.
