# SK1-QUILL-DIAG-PUB-T-954 — bounded TOKN Story read-only discriminator

**Canonical Research Task:** [PUB-T-954](https://app.notion.com/p/3f532a84beec819fb606e8a9b61f0bf1). **Claimed agent run:** [PUB-RUN-747](https://app.notion.com/p/3f532a84beec81b4abd2e55625cf79d2).

## Discriminator, not a replacement for existing TOKN work

Read-only test of the existing Writer's TOKN guard fingerprint: in pinned `pub-quill/src/writer.rs`, an attempted ordinary Story edit is rejected if any Quill descriptor has name `TOKN` and `option_a` equal to the target Story ordinal. The current generic token parser and descriptor→SYID bridge already exist and are owned by `rar2`; **this experiment does not parse new TOKN grammar, serialize, edit, write, or bypass safeguards**.

## Evidence and sample design

- Source Writer/Reader/Editor: `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b`, temporary immutable checkout.
- Classification labels come ONLY from [EXP-002 run #38077356809](https://github.com/calex794/sk1/actions/runs/38077356809) [artifact #11678607165](https://github.com/calex794/sk1/actions/runs/38077356809/artifacts/11678607165), ZIP SHA-256 `651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273`.
- Pre-registered 13 cases from 11 distinct public SHA-pinned PUB: **one** `TOKN_BLOCKED` Story, **two** `NON_TOKN_PASS` ordinary Story in the exact same document, **ten** independent-source length-6 ordinary Story. Eleven of the controls are length-6; one same-PUB control is length-17. The lone positive is source `1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e`, eligible Story ordinal 2, length 6/5 ASCII, previously blocked at five unique edit ranges.
- Identifiers, lengths, ASCII counts, labels and sampling strata are in `witnesses.psv`. Inputs downloaded only through the pre-existing EXP-001/002 manifest allowlist: permitted HTTPS, SHA, size, CFB signature and total byte budget.
- Each sample is independently examined **twice** by a Rust read-only executable, with byte-for-byte equality of resulting JSON, exact original file SHA verified before/after, and Story SYID provenance joined to existing Editor's source-hash-derived ID.

## Observables (no payloads)

Per-Story: descriptor `TOKN` target membership, count of TOKN descriptors elsewhere, parsed TOKN chunk count, PLC effective-token and first/second-phase property-block counts, opaque block/tail presence and size, target records count, Quill/SYID, ordinary Story UTF-16/ASCII lengths, directory/FDPP/FDPC/BTEP/BTEC descriptor counts and table TCD ownership. The `writer_guard_predicts_tokn` is simply `target TOKN descriptor count > 0` — the **already existing implementation predicate**, not independently discovered TOKN wire semantics.

## Verification, negative results and boundaries

All 13/13 cases must be evaluated or CI fails without accepted artifact. Reproduce twice; compute confusion `TP,FP,FN,TN` from original EXP-002 labels. **Do not force perfect accuracy in the evidence gate:** disagreement would be a valid counterexample, not a reason to silently exclude evidence. Report how many *same-source* control Story are unblocked even when another Story has TOKN. A lone TOKN-positive cannot establish generality across Publisher versions or semantic token kinds.

Public artifacts are only `plan.json`, `records.json`, `report.json`, checked by `check_report.py` before upload. Source/candidate PUBs, Story texts, raw/unknown bytes and native Publisher material are never exported. This is not a native Open/SaveAs/Reload acceptance test, TOKN editor support, TOKN regeneration or an authorization to download product-generated PUB.

**Handoff:** bounded observation → this Notion task and research journal, with source-SHA and exact Actions receipts; `rar2` and local Codex remain untouched.
