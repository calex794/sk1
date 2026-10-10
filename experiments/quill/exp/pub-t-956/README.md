# SK1-QUILL-EXP-PUB-T-956 — inverse +1/−1 Writer composition

**Task:** [PUB-T-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd). **Operator GO:** "ты давай задачи делай". Only this research task, not product Writer engineering.

## New research discriminator
[EXP-003](https://app.notion.com/p/3f532a84beec81ec92f9e64a490be67c) independently tested insertion and deletion starting from the original PUB. [PUB-T-953](https://app.notion.com/p/3f532a84beec81f78424f8658052ada5) tested two deletions. Neither tested **inverse composition** of length +1/−1 in hosted Writer on the same source Story and position. The existing native-Publisher dirty-history [bridge](https://app.notion.com/p/3e032a84beec81ecb373fa4bf1709597) concerns a different, native runtime and two controls, not this independent Writer mechanism.

We ask whether
1. O → insert (+1 BMP) → **fresh Reader/Editor reopen** → delete (−1) returns the original text, and
2. O → delete (−1) → **fresh reopen** → insert (+1 BMP) returns the original text.

And crucially, whether each final PUB has **byte-identical SHA to the original PUB**, and whether the two final PUBs are identical to each other.

## Strict scope and controls
- Read-only upstream Writer/Reader/Editor/Quill fixed at `rar2@703808408fd919e564a90cdc236e81db3c04af8b`.
- Reuse only the EXP-001 pinned **35-source manifest** and HTTPS/SHA intake. Exactly 26 admitted public PUB; 65 ordinary editable Story; 194 unique selected offsets in deterministic slots `first/second/middle`.
- **Predeclared baseline** reproduces EXP-003: exactly `first=9, second=34, middle=34` cases where both independent single operations `insert` and `delete` `HOSTED_PASS`, 77 in total. Run inverse compositions only on these.
- Insert one deterministic ASCII marker (`X/Q/Z`, different from adjacent characters), and for the other arm delete the original ASCII alphanumeric. Both input arms start **independently** from identical original bytes.
- For each edit and reverse step the *existing* Writer runs, output is reopened with the existing Reader/Editor, original non-target Stories remain the same by `Quill SYID`, source is immutable, the exact expected target Story text is confirmed, and EditorProject regenerates byte-identical output.
- The reverse of deleting a character may be **offset-ambiguous** if that original character is identical to one neighbor. This is published as a boolean flag and never silently treated as proof of exact offset inversion.
- Outcomes include exact per-step Writer machine code, semantic reopen, byte fixed point versus original and equality between order arms. A second-step `FAIL` is a real answer, not infrastructure failure.

## Safety and authority
Original/candidate PUB exist only in temporary runner memory/directory. The public report contains SHA-256/offsets/ordinals, bounded enums, booleans and aggregate counts only—no raw Quill bytes, Story text, file names of private sources, Publisher binaries or secrets.

**Hosted pass does not prove native Microsoft Publisher Open/SaveAs, byte-level CFB normal form, or product Save/Download authority.** Neither a successful reverse edit nor a semantically unchanged Story guarantees byte-identical serialization. Results and evidence are recorded in the canonical Notion Research Task; code stays in this isolated SK1 branch. No edits to `rar2`.

## Reproduction
[GitHub Actions workflow](https://github.com/calex794/sk1/actions/workflows/sk1-quill-exp-pub-t-956.yml) builds the standalone orchestration example in an **ephemeral pinned** upstream checkout and runs the accepted 26-source corpus. `python3 scripts/verify_registry.py` enforces task registry integrity. `check_report.py` validates source-safe schema and all 77 paired baselines **before** publishing the three JSON receipts as a temporary Actions artifact.

Permanent results: [Notion PUB-T-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd).
