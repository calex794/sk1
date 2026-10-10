# SK1-QUILL-EXP-PUB-T-964 — mixed-sign cross-Story Writer order

**Canonical Notion task:** [PUB-T-964](https://app.notion.com/p/3f532a84beec8151b9d7ed2beeceefde) · **claim/run:** [PUB-RUN-754](https://app.notion.com/p/3f532a84beec81ddae34e8af62c02189).

## New discriminator

`PUB-T-960` checked *two deletions*, one per distinct Story, 31/31 ordering commutation. `PUB-T-956` checked delete+insert inverse on the **same** Story. This experiment tests **one insertion in Story A and one deletion in different Story B**, as two independently ordered chains from the same immutable source. The first step moves the global Quill TEXT tail by +2 or −2 bytes, the second restores global TEXT size. A missing global-offset/FD/BTE rebase or incorrect Story ID reuse could make one order fail or produce differing persisted bytes.

## Pre-registered sample, strict comparison

- Exactly 11 public source SHA already admitted by [960 run #38086190603](https://github.com/calex794/sk1/actions/runs/38086190603). Among 33 Editor eligible Story, one TOKN-protected Story is excluded. **32 Story** have prior standalone insert *and* deletion PASS at the second ASCII-alphanumeric offset according to EXP-956/960; **31 unordered cross-SYID Story pairs** in 11 source PUB.
- Every pair has two assignments: A=insert/B=delete and B=insert/A=delete, for **62 oriented cases**. For each case, `insert→fresh-reopen→delete` and `delete→fresh-reopen→insert` are independently executed, yielding **124 ordered chains**. All outcomes are recorded; failed chains remain visible and are not forced to PASS. `11 independent sources` is the primary denominator, not 62 different documents.
- Public SHA/HTTPS CFB allowlist inherited unchanged from `sk1-exp-001`. Original Writer/Editor/Reader from immutable `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b`. No new writer or source parser; no `rar2` modifications.
- Exact provenance: [956 artifact #11680967998](https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998) ZIP SHA256 `afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427`; [960 artifact #11682312578](https://github.com/calex794/sk1/actions/runs/38086190603/artifacts/11682312578) ZIP SHA256 `aaa280bc3c859f149b583fe2d7b1e4eea2a1f0faaaaf584f80fa3e79a2ff3c5b`.

## Method

1. Fresh import original into canonical Editor; select up to first three ordinary replaceable Story. Derive current StoryId from **source SHA + Quill SYID**. At the precise second ASCII alphanumeric, create independently from original a `delete_one` and a one-code-unit ASCII marker insertion (`X`, `Q`, `Z` marker rule from original PUB-T-956). Verify both independent controls through normal Writer/Reader/Editor/EditorProject replay.
2. For each cross-Story assignment, `O→insert A→Reader/Editor reopen→delete B` and separately `O→delete B→Reader/Editor reopen→insert A`. The second step uses fresh candidate SHA when deriving StoryId for the target's *original* SYID.
3. Each individual Writer step checks exact semantic target Story, all sibling Story by Quill SYID, byte-identical EditorProject replay and immutable source; after a successful second step compare entire Quill Story catalog against expected **two** edits and unchanged other stories. If both orders succeed, compare full output PUB byte vectors, not only text.
4. No PUB bytes, Story strings, Quill raw payload, unknown paths, rejected error strings or private URLs in artifacts. Only `plan.json`, `records.json`, `report.json`; independent `check_report.py` refuses missing/partial/invalid evidence. A Writer refusal or order-sensitive final hash is a valid research observation.

## Scope limits

This tests only the pinned hosted bounded Writer on 11 previously selected PUB, not native Microsoft Publisher, physical sector layout, Unicode beyond the ASCII marker, or one atomic product multi-Story authoring transaction. Existing `rar2` implementation must remain unchanged; any product regression patch requires explicit separate authorization.
