# SK1-QUILL-DIAG-PUB-T-967 — source-only variable-length growth guard prediction

**Official Research Task:** [PUB-T-967](https://app.notion.com/p/3f532a84beec81659773c3d6c9d0668f). **Execution:** [PUB-RUN-755](https://app.notion.com/p/3f532a84beec81129ea1fdf57cfcb017).

## Exact research edge

[PUB-T-962](https://app.notion.com/p/3f532a84beec81a090b3f065a34c2c16) already ran hosted Writer to measure **14** adjacent `PASS at N` / `guard at N+1` (11 descriptor, 3 unknown) in 14 public source SHA. **The question here is different:** can an entirely **read-only** inspector estimate the same *whole* N boundary and the specific first guard code from original Quill stream geometry, without calling a Writer? Existing [SK1-EXP-004](https://app.notion.com/p/3f532a84beec81fda307fd18807f1117) measured only the last 2 bytes and +1 tail risk, not variable N. Concurrency dedup: [T965](https://app.notion.com/p/3f532a84beec81cc8c74ce9beb18c519) handles synthetic SYID carry, and [T966](https://app.notion.com/p/3f532a84beec81c088c0f9611cae02fa) handles **other** text insertion positions, each owned by other agents. This task only looks at the **original T962 second ASCII-offset** in each of its 14 sources.

## Pre-registration and blind predictor

- Archived scientific origin: [GitHub Actions #38086685517](https://github.com/calex794/sk1/actions/runs/38086685517) pinned SK1 scientific SHA `4ed320411bb5bebf23ea5a4c31c336d3fba74ce1`. [Artifact ZIP #11682633082](https://github.com/calex794/sk1/actions/runs/38086685517/artifacts/11682633082), independently SHA256 `ab73d6206663523929843616e196287563468b0ac8988005842349afc206aeb9`; verified ZIP/JSON before extracting labels.
- `witnesses.psv` was committed **before the predictor and CI**. Exactly 14 source SHA, old 962 original Story ordinal, UTF16 offset, pre-edit UTF16 length, last successful N, first failed N+1 and first guard code. This is a *conditional preselected* sample of 14/25 SHA-verified from a 27-file holdout, and not 14 new PUB.
- The Rust binary receives only **one unchanged original PUB + SHA + temporary read-only receipt destination**. It receives **no empirical N, guard code, hidden label or source control list**. Python joins predictions to precommitted `witnesses.psv` only after Rust returns, and independently recomputes all equality checks.
- All source bytes are obtained using existing `SK1-EXP-005` pinned public SHA, size, HTTPS/redirect allowlist at `Lalalalendia/lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea`; original Reader, CFB and Quill library `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b` exactly as PUB-T-962. Absolutely **no Writer calls or any exported PUB/candidate**.

## Mechanism under test (bounded existing guard, not format law)

Let `end` be original TEXT descriptor end, `anchor` be the earliest FDPP/FDPC descriptor offset ≥ `end`, aligned to 512 bytes; `gap = anchor-end`; `zero_suffix` the count of consecutive zero bytes from `anchor` backwards until the first occupied byte (clamped to `gap`); and `descriptor_clearance = max(0, anchor-furthest_nontext_descriptor_end)` over non-TEXT descriptor payload extents intersecting pre-anchor growth window. Source-only candidate:

`predicted max N (UTF16 units) = floor(min(gap, zero_suffix, descriptor_clearance) / 2)`.

The first candidate `N+1` is classified *without mutating data* by the original Writer's published **order of checks**: if `2(N+1)>gap`, insufficient capacity; else inspect descriptor overlap with `[anchor - 2(N+1),anchor)`: any non-zero overlap predicts `quill_growth_would_discard_unknown`, a zero-only known descriptor overlap predicts `quill_growth_would_discard_descriptor`; if no descriptor overlap, trailing nonzero predicts unknown. This is **a reflection of current hosted Writer safety policy**, not a newly established Microsoft Publisher grammar rule or permission to remove guards.

## Source-safe acceptance and falsifiers

- Structural receipt includes only SHA/source size, selected Story ordinal/UTF16 metadata, Quill length, numeric end/anchor/gap/zero_suffix/descriptor-clearance and predicted first guard. No raw Quill bytes, unknown chunk names, Story strings, user paths or source URLs.
- Evidence gate enforces **14/14** SHA-valid, 14 unambiguous Writer-selection Story/offset/length matches, 14 valid structural predictions and bounded `predicted vs empirical` comparisons. A mismatch in N or guard is **accepted as a counterexample**, not filtered or repaired into a PASS. Network/SHA failures cause incomplete CI and cannot be misreported as Writer FAIL.
- Only `plan.json`, `records.json`, `report.json` may be uploaded *after* strict independent checker. All artifacts are public-safe. `writer_invoked=false`, `candidate_generated=false`, `native_publisher_acceptance=NOT_EVALUATED`, `product_pub_download_authorized=false`.

**No upstream code changes.** If evidence shows limitations in the formula, preserve counterexamples and make a targeted handoff to the rar2 owner rather than a bypass or untested patch.
