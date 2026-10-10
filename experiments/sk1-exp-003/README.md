# SK1-EXP-003 — matched Quill insertion/deletion at the same offset

Notion journal: https://app.notion.com/p/3f532a84beec81ec92f9e64a490be67c

## What we test
Under the **same immutable source SHA, Story and UTF-16 offset**, does the current bounded Writer accept both `delete_one` (remove the selected ASCII alphanumeric character, Δ−1) and `insert_one` (insert ASCII "X" immediately before it, Δ+1)?

The same 26 public SHA-verified PUBs and first three eligible Stories from EXP-001/002 are used. Only three distinct position slots are tried: first, second, middle (deduplicated for short Stories). Two fully independent operations start from the exact unmodified source for each slot.

**No new Writer/Quill engine**, no modification to `rar2` and no Microsoft Publisher. Upstream implementation fixed to `703808408fd919e564a90cdc236e81db3c04af8b`, matching earlier experiments.

## Control
The **delete_one** arm must recreate EXP-002 deletion outcomes exactly:
- first: 11 HOSTED_PASS / 53 FD boundary / 1 TOKN
- second: 64 HOSTED_PASS / 1 TOKN
- middle: 63 HOSTED_PASS / 1 TOKN (64 distinct selected positions)

The completed test must have 26 evaluated sources / 65 Stories / **194 matched offsets** / **388 arm attempts**. Any drift fails CI, even if another analysis happens to look promising.

## Validity and safety
A pass requires actual Writer candidate bytes different from original, semantic Reader/Editor reopen, an exact byte-identical EditorProject replay, unchanged input bytes, and Quill SYID-correlated unaffected Story text/identity. Synthetic or raw mock changes do not count.

The security intake reuses EXP-001 SHA-pinned HTTPS host allowlist, size limits, and manifest. Original and candidate PUB are temporary local worker files only. Only allowlisted scalar/boolean, SHA and enumerated blocker codes go to public GitHub Actions JSON artifacts; neither Story contents nor original/generated PUB nor raw exception text are uploaded.

A hosted pass **is not** Microsoft Publisher native Open/SaveAs acceptance and does not grant product Save/Download permissions.

## Output
A per-slot contingency table: both pass / deletion-only / insertion-only / both fail, together with exact Writer blocker codes and SHA/Story-offset-only discordance witnesses. These are **paired comparisons of individual edits**, not a sequential insert-delete roundtrip.

Final knowledge and verdict are recorded in Notion whether the hypothesis survives or fails. Only a separately authorized minimal regression test may be transferred to `rar2`; temporary code stays in SK1.

## Reproduce
GitHub Actions workflow: https://github.com/calex794/sk1/actions/workflows/sk1-exp-003.yml
