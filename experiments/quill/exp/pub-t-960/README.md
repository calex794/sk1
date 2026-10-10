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

The independent source-safe archive from [PUB-T-956](https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998) was parsed before this task. It contains **11 source SHA** where ≥2 distinct Stories have a `HOSTED_PASS` standalone deletion in the `second` slot. Ten of these sources have 3 eligible Stories, one has 2: thus **32 Story controls, 31 distinct inter-Story pairs, 62 ordered two-step chains**. Every pair is same-source but uses different Story SYID. Reuses original [EXP-001 allowlisted source intake](../../../sk1-exp-001/) and immutable `rar2@703808408fd919e564a90cdc236e81db3c04af8b`.

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
