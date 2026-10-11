# SK1-QUILL-VAL-PUB-T-989 — STSH/FONT preservation under a real Rust Writer
Task: https://app.notion.com/p/3f632a84beec819bbe85c29d402cd384

## Question
Does the **actual** \`pub-quill::plan_quill_story_text_edit\` preserve all four opaque STSH0/1/2 and FONT payloads while shrinking Sample3 Story text by six UTF-16 units, when two unknown bytes are changed only in memory (STSH1 paragraph id0x30 high 00→5A with missing id0x13, STSH1 header +8 changed independently)?

## Exact source
Only the public test fixture already contained in \`Lalalalendia/rar2\`: \`vendor/producer-a/crates/pub-quill/tests/fixtures/Sample3.pub.b64\` (Git blob \`1584a0df824a560a2e7f45e375a71fd312562aba\`). Pinned repo commit \`22a322ed10d9fe8a4ade45acf83bebd0442b691b\`; Rust Writer source blob \`b33aaf4d261a98efb7d9d487ed73852cbd0ec168\`.

The runner verifies all hashes. It injects only one temporary test into a disposable checkout of \`rar2\`; it does not edit either repository's production code. The two input variants are a public original Quill and a 2-byte in-memory mutant. They are never saved to disk as PUBs and never uploaded.

## Controls and acceptance
One Cargo test performs two source variants (original and controlled mutant), compares complete raw payloads for 3 STSH and 1 FONT in each arm (8 comparisons), and verifies a 12-byte TEXT reduction plus descriptor relocations. \`PASS\` requires cargo exit 0, exactly one named Rust test line, one-test success summary, and independent receipt validation. Rust compilation failure or zero tests is not a pass. Source-safe JSON records report exact pins and numeric outcome without raw PUB, Quill, or Story bytes.

No native Publisher validation; no proof of style-edit, construction from scratch, or format semantics. Do not merge this code as product Writer work. The experiment branch is disposable and belongs to SK1; the appropriate result is a concise Notion evidence update.
