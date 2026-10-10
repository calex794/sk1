# SK1-QUILL-EXP-PUB-T-953 — two ordered deletions on one Story

**Task:** [PUB-T-953](https://app.notion.com/p/3f532a84beec81f7b53ddd902271da33); **Agent Run:** [PUB-RUN-746](https://app.notion.com/p/3f532a84beec815d839ae2c38cab83c1).

## Question
Given two deletions A and B that independently pass from the *same* original PUB, does original→A→reopen→B' pass? Does original→B→reopen→A' pass? Does edit order affect acceptance or final candidate bytes?

## Input and provenance
- Immutable upstream rar2 commit: 703808408fd919e564a90cdc236e81db3c04af8b.
- Verified [EXP-002 action #38077356809](https://github.com/calex794/sk1/actions/runs/38077356809) [artifact #11678607165](https://github.com/calex794/sk1/actions/runs/38077356809/artifacts/11678607165), ZIP sha256:651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273.
- 24 pre-registered independent PASS pairs from 23 distinct permitted public PUBs in witnesses.psv. A is second-slot deletion, B last permitted deletion (or q75). The two exact single-operation candidate SHAs are pinned and must be re-observed.
- Original 35-source manifest from EXP-001, 26 admitted public inputs. Source SHA, size, allowed HTTPS host, CFB signature and total acquisition budget are enforced; no new source fetch policy.

## Steps
1. Independently write A and B from immutable original. Exact candidate SHAs must equal EXP-002.
2. Reopen the candidate from A, identify Story using new source-hash and Quill SYID, then perform offset-adjusted B'. Repeat symmetrically B then A'.
3. For every materialized step: target semantic text, all non-target Story semantics, complete Quill SYID set, exact EditorProject replay, source immutability, new Reader/Editor open.
4. Record AB/BA statuses and machine guard codes. If both pass, separately compare final PUB hashes. Semantic equality alone does not imply byte identity.
5. Categorize missing source, SHA drift or failed baseline as NOT_EVALUATED, distinct from tested Writer refusal. Fail CI on incomplete baseline.

## Safety and transfer
Only source-safe plan.json, records.json, report.json are uploaded after schema checker approval. Never upload source or generated PUB, text, raw Quill bytes, local paths or private material. No new Writer implementation, no rar2 changes, no Local Codex/Publisher runtime. Hosted success is not native Publisher SaveAs or product PUB export acceptance. New bounded knowledge goes to Notion; rar2 changes require a separate owner decision.
