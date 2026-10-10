# SK1-EXP-002 — Quill FD guard: positional counterfactual

**Question:** On the same exact ordinary Story that failed one-character deletion at the first ASCII-alphanumeric position in EXP-001, could deletion at a different position pass the same current Writer?

Evidence journal: https://app.notion.com/p/3f532a84beec81d6b406fc10231e1310

## Provenance and nonduplication

- Canonical Writer and Editor **remain read-only**, pinned from Lalalalendia/rar2 at SHA 703808408fd919e564a90cdc236e81db3c04af8b.
- Locked 35-source manifest, source allowlist and SHA+size verification are reused from EXP-001. Exactly 26 public eligible sources are selected.
- The upstream Quill Writer already intentionally guards edits starting at FD boundaries. This experiment measures position-dependence across an independent real corpus. It does not rewrite Quill grammar or bypass Writer safety rules.
- Six deterministic selection slots, deduplicated if too few distinct eligible characters: first, second, 25%, middle, 75%, last ASCII-alphanumeric.
- Every attempt starts from the SAME exact original PUB. Up to three editable source Stories per PUB.
- Actual Editor/Writer, Reader semantic reopen, byte-identical EditorProject replay, source/target-SHA-adjusted Quill SYID verification of unaffected Stories.

## Calibration and evidence gate

Exact Publisher-approved Sample3 positive control remains upstream and is rerun without being counted as new evidence. The EXP-001 first-position arm must reproduce 65 Story outcomes: 11 HOSTED_PASS, 53 quill_edit_touches_fd_boundary, and 1 quill_token_layer. Any mismatch/incomplete input yields a failed research run, not fake Writer failures.

## Reproduction

Run https://github.com/calex794/sk1/actions/workflows/sk1-exp-002.yml with GitHub Actions. The job copies one disposable experiment-only Rust example into an ephemeral pinned checkout of rar2; no rar2 PR or branch is created. A fresh Rust toolchain builds the example once and runs it against validated public files.

Security: admitted public HTTPS .pub only, SHA-256 and exact size checked; ≤12 MiB/file and ≤120 MiB total. Every original/candidate PUB stays in a temporary directory and is deleted. No Story text or proprietary documents can be uploaded. Public artifacts contain only source-safe plan, records and report; the validator checks all fields.

## Portable output

- plan.json — immutable source SHA list and experimental slots
- records.json — per-source, per-Story/position outcomes and machine-only Writer blocker codes
- report.json — matched pair stats, number of originally blocked Stories recovered by a different position, and source-SHA reproducible counterexamples

A hosted Writer/Reader pass is NOT Microsoft Publisher native SaveAs evidence and grants no product Download PUB authority. The outcome is portable knowledge in Notion; code only moves to rar2 after an independent task-owner decision.

The initial work is intentionally scoped to independent reproducible measurement, not a second Writer.
