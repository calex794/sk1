# SK1-QUILL-EXP-PUB-T-960 — sequential edits of TWO distinct Story identities

Canonical task: [PUB-T-960](https://app.notion.com/p/3f532a84beec812b99a1ccfca4c76c4a). **Not a multi-Story atomic Editor feature.**

## Question

If deletions on two different Quill Stories independently pass existing Writer/Reader, do they still succeed when applied serially to the same source PUB through *fresh reopen* and preserved source SYID mapping? Do they commute in **whole-PUB output bytes** when executed in opposite orders?

- A = delete one second ASCII alphanumeric in Story A.
- B = delete one second ASCII alphanumeric in a **different Story B**, not a different position of A.
- Actual materializations: original → A → reopen → B, and independently original → B → reopen → A. After every step the existing Reader opens the candidate; Story IDs are freshly derived from the **current candidate SHA and unchanged Quill SYID**.
- Each step validates exact target Story semantics, untouched siblings by SYID, original source immutability and EditorProject byte-exact replay. Final verification explicitly checks both targets and every other non-target Story after both edits.
- Compare final SHA (and full byte vector in memory) between AB and BA. Negative or order-sensitive outcomes are science, not infrastructure PASS. Artifacts record safe blocker machine codes.

## Preregistered prior-evidence sample

The independent source-safe archive from [PUB-T-956](https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998) was parsed before this task. It contains **11 source SHA** where ≥2 distinct Stories have a `HOSTED_PASS` standalone deletion in the `second` slot. All 11 files have 3 Editor-eligible Stories (33 tested). Ten have **3 individually successful** deletions; the eleventh has **2 successful** deletions plus **one explicitly excluded `quill_token_layer`** control. Thus exactly **32 accepted Story controls, 31 distinct inter-Story pairs, 62 ordered two-step chains**. Every pair is same-source but uses different Story SYID. Reuses original [EXP-001 allowlisted source intake](../../../sk1-exp-001/) and immutable `rar2@703808408fd919e564a90cdc236e81db3c04af8b`.

**These are not 11 new independent PUB**: all sources were in the original corpus and preselected via prior Writer outcomes. Primary source-level denominator = 11 SHA; 31 pairs and 62 order arms are correlated secondary units. No statistical confidence interval justified by 62 "independent" documents.

## Not duplicates

- [PUB-T-953](https://app.notion.com/p/3f532a84beec81f7b53ddd902271da33): two deletions in **one Story**. This tests **two distinct SYIDs**.
- [PUB-T-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd): inverse +/-1 within one Story. This tests cross-Story composition and order.
- [PUB-T-959](https://app.notion.com/p/3f532a84beec81aeab95c4e7c55e9ba7): ongoing physical CFB layout for *one edit* on different holdout data. We do **not** inspect physical CFB data or use its sample.
- [AUTHORING-MULTI-STORY-TEXT-TRANSACTION-01](https://app.notion.com/p/3e532a84beec81e1a5d5e5b5b321f7d1) is a product-level **atomic authoring graph transaction**; this is serial Writer Save/reopen only, not one atomic operation, Undo unit, or native Publisher capability.

## Safe and reproducible controls

- Rust example is ephemeral and reuses only canonical Writer/Reader/Editor in a pinned rar2 checkout; no second native Writer/Quill parser.
- Direct public HTTPS, size and SHA-256 source verification before touching the original PUB. Raw PUB and Story text remain strictly inside isolated temporary worker; no changed original/candidate PUB leaves the runner.
- Fail closed if any 11 predeclared source SHA missing/unverifiable, fewer than 32 original Story single-delete PASS, fewer than 31 pairs / 62 two-step arms, or invalid `source-safe` JSON.
- Source-safe receipts: original public SHA, Story ordinal/SYID, UTF-16 offset, bounded Writer status/error code, output hash, full final Story compare result, order-commutation bit and exact denominators. No text, Quill unknown byte values, private URLs, local file path, licensed binaries or opaque content.
- Native Microsoft Publisher Open/SaveAs, native format acceptance, and product Save/Download = **NOT_EVALUATED**.

## Reporting

[GitHub Actions workflow](https://github.com/calex794/sk1/actions/workflows/sk1-quill-exp-pub-t-960.yml) builds the read-only experimental oracle on exactly the pinned upstream SHA. The task's permanent result (positive or negative) belongs in [Notion PUB-T-960](https://app.notion.com/p/3f532a84beec812b99a1ccfca4c76c4a), not just the expiring CI ZIP. No Writer patch to rar2 without its owner's decision.

## Failed first admission run — repaired without changing source sample

[Actions #38086016342](https://github.com/calex794/sk1/actions/runs/38086016342) did build and execute the 11 sources; the runner **correctly failed closed** (exit 2) before the source-safe validator/artifact because its initial census assumed all **33** Editor-eligible Stories were individually writable. The single blocked Story is the already documented TOKN Story ordinal 2 in SHA `1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e`. Thirty preliminary cross-Story pairs produced 60 successful two-step chains and 30 byte-equal final pairs, **but they are not an accepted proof** because the one remaining predeclared valid pair was excluded by the faulty admission code.

The corrected census **tests and records all 33 single controls**, explicitly excludes the one known TOKN failure from *pair selection*, and requires the same fixed **11 SHA/32 PASS/31 pairs/62 orders**. This changes no source list, pair identities, Writer algorithm, or acceptance of a denied TOKN Story. New run requires full revalidation before scientific conclusion.

## Verified scientific outcome — CLOSED

[Canonical task PUB-T-960](https://app.notion.com/p/3f532a84beec812b99a1ccfca4c76c4a) · [permanent knowledge](https://app.notion.com/p/3f532a84beec81f880abf641a045b8e5) · [accepted Actions #38086190603](https://github.com/calex794/sk1/actions/runs/38086190603).

Exact science SK1 head `0bd1efc90f1e891e8a07e1bd1c0b673c45328a5c`; unchanged `rar2@703808408fd919e564a90cdc236e81db3c04af8b`. Source-safe [artifact #11682312578](https://github.com/calex794/sk1/actions/runs/38086190603/artifacts/11682312578) ZIP digest `sha256:aaa280bc3c859f149b583fe2d7b1e4eea2a1f0faaaaf584f80fa3e79a2ff3c5b`, independently verified against downloaded ZIP and all three internal JSON files.

**Accepted evidence:** 11/11 SHA-verified public PUB; 33 candidate Story with 32 standalone second-ASCII deletion `HOSTED_PASS` and one excluded `quill_token_layer` control; 31 cross-SYID Story pairs, all **31 AB** and **31 BA** Writer+Reader/SYID/replay and final semantic `HOSTED_PASS`, and **31/31** actual final byte vector equal across order arms. No new negative or noncommuting witness. This is a source-conditioned *serial hosted Writer* result, **not** a guarantee of product multi-Story atomicity, undo, arbitrary edits or native Microsoft Publisher.

**The first run was NOT scientific success.** [#38086016342](https://github.com/calex794/sk1/actions/runs/38086016342) failed its admission because it wrongly required 33/33 single PASS, including the known TOKN-protected Story. Correction kept the 11 source SHAs and 31 originally selected pairs unchanged and admits only 32 successful Story controls. That failed run must never be added to the scientific denominator.

**Verdict:** permanent Notion record, no `rar2` patch and no second Writer implementation. Task state `completed` in GitHub mirror.
