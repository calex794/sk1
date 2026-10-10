# SK1-CFB-DIAG-PUB-T-959 — one-way Writer edit: physical CFB delta

Canonical [PUB-T-959](https://app.notion.com/p/3f532a84beec81aeab95c4e7c55e9ba7). Operator GO: 2026-10-11. Owner: SK1 metagent; no `rar2` writes.

## New question and dedupe

What happens to physical CFB bytes, sector topology, directory metadata and FAT/MiniFAT when a single native-candidate Writer text deletion is materialized? Separate absolute-file-offset churn from logical-stream changes.

- **Not a repeat of T956/957/958**: those measured double-edit inverses and Quill SYID/FDPC on the EXP001 corpus; they did not classify one-way physical CFB layout on independent sources.
- **Not a repeat of CORPUS-CFB-PHYSICAL-LINEAGE-01**: those 160 distribution-media duplicate pairs did not modify content; their timestamp-only class must not be assumed for Editor Writer output.
- Current `PUB-T-955` is Parked pending material Writer change; we do **not** compare versions or change the Writer.

## Pinned inputs and controls

- Sole Writer/Reader: `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b`. No forked product logic.
- Reuse the SHA-pinned 62-file holdout selection from EXP005 (`Lalalalendia/lalamu@f78cc6f455f4dc222868f9cc035511a6ca7a91ea`), which already excludes the 35 EXP001 original source SHAs.
- Fixed 27 source-SHA cases across 7 host strata, first SHA-sorted within each: math=10, anyssa=4, Google=4, Duke=3, Greville=2, Instructables=2, BNS=2. No replacement for unavailable inputs. <=2.5 MiB/file and <=50 MiB total.
- One ASCII deletion at second alphanumeric position of first editable Story per source. Source is immutable. Only Writer HOSTED_PASS with Reader semantic reopen, SYID non-target Story agreement and EditorProject byte-equal replay proceeds to physical measurement.
- CFB physical parser is the **existing upstream** `tools/corpus/cfb_physical.py`; logical stream inventory uses upstream `cfb_physical_diff.py` and olefile. Compare source/candidate path, size and SHA internally, export only aggregate counts.
- Calibrate the physical byte-label classifier on a synthetic single-directory-state-byte sample before downloading any PUB.
- All source and candidate PUB bytes (and the Story text) stay only in temporary worker paths; never send them to stdout, CI artifact, commits or Notion.

## Metrics and interpretation

- Per SHA: eligible vs blocked vs not evaluated; candidate SHA, UTF16 position for reproducibility, logical stream path add/remove/change counts (no raw names), Quill vs other-stream changes; sector size/count, directory and FAT/MiniFAT metadata, root-chain and sector-location comparison.
- Raw physical positions are counted by source and candidate **absolute same-byte offset** category (header, directory fields, FAT, MiniFAT, stream payload, slack, unallocated, etc.) and explicit `unclassified`. Extra bytes beyond the overlapping prefix are counted separately.
- **Critical limitation**: if sectors move, same-offset diff counts indicate physical churn, not which semantic byte changed or a proof of relocation; do not call it relocation-normalized accounting. Genuine stream change is computed independently from *logical payload hashes*.
- >=8 independent measured sources required to pass the resource-bound experiment. Otherwise CI reports insufficient evidence, but still stores sanitized partial receipts; no silent denominator reduction or scientific conclusion.
- Only hosted original `rar2` implementation. Nothing here proves licensed Publisher open/save, format universality or product Download/SaveAs.

## Reproduction

[Run workflow](https://github.com/calex794/sk1/actions/workflows/sk1-cfb-diag-pub-t-959.yml) from `sk1/cfb-diag-pub-t-959`. It checks out the pinned upstream SHA, compiles `one_way_delete.rs` as a temporary Rust example in the upstream CLI, runs the pinned manifest input, checks JSON privacy and summary arithmetic, and uploads only `plan.json`, `records.json`, `report.json` if validated.

The scientific verdict and exact Actions run/SHA/artifact (when available) must be written to the canonical Notion Research Task and SK1 journal. No code needs to go into `rar2` unless a product owner later requests a distinct proof.