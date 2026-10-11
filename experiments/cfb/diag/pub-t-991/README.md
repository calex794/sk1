# PUB-T-991 — natural Quill/SYID FE/FF outside 625

Canonical Notion: https://app.notion.com/p/3f632a84beec818bbadafb0cba02f762

New bounded experiment: original first-DWORD Quill SYID low byte FE or FF in externally saved PUB files outside the 625 already censused in PUB-T-987 (0/382). Never fabricate or patch an original SYID. Never count a source file twice.

Frozen source repositories and strict inputs (exactly 27):
- Apache POI at c85c6918858ea279de2c33df70518c105064df41, tree test-data/publisher 10300af0b12b49578dfda1b704aef0a84a663914. Exactly 21 ordinary .pub fixtures; exclude three fuzzed/corrupted files. All 21 file SHA256 and sizes are verified against the existing frozen rar2 reader_corpus_manifest_v1.json.
- Aspose.PUB for .NET at beee619f9a4b7e2c8908e0fa132f4f4650b08975, exactly five .pub files from Examples/Data. Do not count duplicate Java copies.
- mmalecot/file-format at bdc8e1d219af7d42aa1ebb30c902f0c4a12763f4, only fixtures/document/sample.pub, 12 288 bytes, not the 27-byte other sample.

Each is cryptographically authenticated to the original Git blob and frozen commit, then SHA256 fingerprinted. Exact duplicate overlap against all 625 original Lalamu PUB SHA at 87094c23e2a9eaa2aa9e95d72ec52f72ef109f11 tree 8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7, and separately against current exact 1556-SHA rar2 authority at upstream Writer pin 703808408fd919e564a90cdc236e81db3c04af8b. A match in 1556 is already known physical PUB and NOT a new acquisition. A match in 625 is NOT a new SYID experiment source. Duplicate external files count only once for independent evidence.

All 27 original source files remain untouched. A temporary SHA-named worker directory feeds the original PUB-T-987 Quill/CFB Rust scanner at fa714fe958999325649430dad53c10edac42246a. Only cardinality and safe schema string change in temporary generated code; Quill parser is not reimplemented. Every source gets normalized source admission status and, if the real Quill SYID parses, natural numeric header, count, max live, low byte.

Only previously unexamined original low-FE/FF sources trigger the previously proven PUB-T-984 actual Writer at 14ac75ae0346b3bdbeeada110e1f463dda6cbb27, through inherited frozen T963/T971. Deterministically select up to three Story/second ASCII slot, two independent first steps, two inverse Writer orders only when both first steps pass, then Reader reopen, sibling Story, byte-equal EditorProject replay, full original vs final PUB raw absolute-byte diff, all CFB streams including Quill TEXT and first DWORD SYID delta +2. Preserve failures, guards and counterexamples. No product modifications.

Only plan.json, records.json, report.json, all safe SHA, counter and status data, are exported. No raw PUB, text, URL, path, binary intermediate or unfiltered errors. Independent validator re-hashes all 27 original sources and repeats dedup, source-hash, numeric and original Writer receipt checks. The exact ZIP is independently audited before Notion Done.

Original files may be test fixtures: their Microsoft Publisher native generation is NOT independently attested. Native Microsoft Publisher Open/SaveAs NOT_EVALUATED. A zero natural FE/FF count is a valid bounded result, not a universal absence.

Science workflow: https://github.com/calex794/sk1/actions/workflows/sk1-cfb-diag-pub-t-991.yml
Predecessors: https://app.notion.com/p/3f632a84beec814fb63edc9c99460b8a and https://app.notion.com/p/3f632a84beec81cd887df660673fb7b3