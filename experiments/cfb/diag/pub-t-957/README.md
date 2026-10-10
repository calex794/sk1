# SK1-CFB-DIAG-PUB-T-957 — CFB/Quill after semantically inverse Writer edits

**Canonical Research Task:** [PUB-T-957](https://app.notion.com/p/3f532a84beec81adbc4fe3bed705d7a9). **Agent Run:** [PUB-RUN-749](https://app.notion.com/p/3f532a84beec81ba9947e5e049f9c2de).

## Independent question

[PUB-T-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd) proved that `insert→reopen→delete` 77/77 and `delete→reopen→insert` 75/77 succeed semantically on a fixed hosted Writer while 0 accepted inverse final candidates are byte-identical to originals. It did *not* identify whether byte drift occurs in Quill logical stream content, other CFB logical streams or only CFB physical representation. PUB-T-952 measured non-target stream preservation after single edits; its result does not resolve the inverse comparison.

This isolated task localizes source→fully semantically restored output changes at the CFB logical-stream boundary and original/final Quill descriptor payload and known chunk boundaries, without new Writer, new parser or native Publisher.

## Exact basis / admission

- Source: `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b` checkout compiled as-is. Rust code is only an example using existing Editor/Writer/CFB/Quill APIs.
- Source-SHA/allowlisted HTTPS corpus EXP-001/003: 26/26 admitted public PUB, 65 eligible ordinary Story, 194 pre-registered first/second/middle source offsets; 77 isolated matched single insertion AND deletion PASS. No new sampling or redefinition of roles.
- Baseline details: 956 [Actions #38083249275](https://github.com/calex794/sk1/actions/runs/38083249275), pinned scientific SHA `08abf5c7d92fb5ca56fd3ff84009309120fcf52c`, source-safe [artifact #11680967998](https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998) ZIP SHA256 `afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427`.
- Current positive source acceptance and `77/75` inverse outcomes must reproduce 956. Those are *calibration*, not new findings. The new observations occur *after* a verified inverse: compare original and final persisted PUB in-memory.

## New source-safe measurements

- CFB directory entry and stream-path inventory before/after, missing/added paths, entry-kind changes, count of changed *non-Quill* stream payloads, Quill stream exact equality; no user-defined stream names in outputs.
- Boolean `all_logical_streams_equal`: path/type/stream equality. If true but whole PUB differs, only then call it physical-container-only divergence; do not guess header vs FAT vs timestamp without additional physical classifier.
- Quill original/final length and SHA, exact per-offset differing-byte count only when lengths match, Story SYID sequence and STRS UTF-16 lengths, full aggregate TEXT payload bytes equality.
- Existing Quill reader descriptor order/membership. Only if sequence matches by (chunk name, source Story ordinal) count altered descriptor offsets, lengths, other options and altered *chunk payload* per fixed whitelisted Quill kind `TEXT/SYID/STRS/FDPP/FDPC/BTEP/BTEC/TOKN/TCD/OTHER`. Unknown Quill kind names remain opaque; all payloads stay private.
- Every individual source/candidate PUB remains on ephemeral hosted worker only. Output is solely `plan.json`, `records.json`, `report.json` after strict independent checker confirms all 26 input admission, 65 Stories, 194 offsets, 77 selected matched double-PASS pairs, 77 and 75 inverse receipt records and source-safe schema.

## Decisive interpretation

Expected claim must follow evidence. If the Quill stream stays equal but file SHA changes, distinguish physical CFB metadata/allocator changes from logical content differences (no overclaim about specific bytes). If Quill differs but `TEXT/SYID/STRS` are equal, report that it is an **uninterpreted remaining Quill structural difference**, not text corruption or native Publisher incompatibility. If non-target stream bytes differ, log counts as a counterexample even if Story text is restored.

Notion holds verdict and links; do not silently integrate any Writer code into rar2. Native Publisher lifecycle/SaveAs and product download permissions are outside this task.
