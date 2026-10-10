# SK1 agent contract — Chaptera/PUB temporary experiment warehouse

**Not another Writer/Reader/product repository.** Product owner: [rar2](https://github.com/Lalalalendia/rar2). The separate local Codex agent owns native Publisher operations. All relevant agents share [Notion](https://app.notion.com/p/3f532a84beec81ad898de243b3b27c80).

## Canonical task identity / no collisions

1. **Notion Research Tasks allocates Task IDs and owns task status, assignee, and lease.** This repository's \`experiments/registry.json\` is a read-only *mirror* of identities/links, not an alternate task board or an execution authorization.
2. For **new** experiments use the full Notion-derived ID \`SK1-{AREA}-{TYPE}-{PUB-T-NNN}\`. For example \`SK1-CFB-VAL-PUB-T-952\`; never guess \`SK1-EXP-006\` from a counter. AREA = CFB / QUILL / VERSIONS (or an explicitly authorized new area); TYPE = EXP / VAL / DIAG / CMP / BENCH. Make \`area\`, \`type\`, and task number match the real Notion task.
3. New paths: \`experiments/<area-lower>/<type-lower>/<task-id-lower>/\`. Branch: \`sk1/<area-lower>-<type-lower>-<task-id-lower>\`. Keep completed legacy \`SK1-EXP-001…005\` names and receipts **unchanged**. Old IDs are reserved.
4. **Parked/Blocked/unclaimed tasks are NOT self-pickable.** An explicit GO from the Supreme Operator, current Notion task owner/lease, and a fresh dedupe check against \`rar2\`, existing SK1 branches and Local Codex are prerequisites. Two agents must not independently start the same task.
5. Before committing: fetch current Notion task and GitHub HEAD, use fresh SHA/CAS (no force), ensure a single registry row per task, and run \`python3 scripts/verify_registry.py\`. An executable under a new unregistered \`experiments/\` directory is invalid. Keep one experiment per unique Notion task; GitHub Actions run IDs are independent execution receipts.
6. **Useful verified work goes to the correct existing Notion page immediately**, including negative outcomes and uncertainty. Record hypothesis, exact pinned SHAs/inputs and exclusions, results, limits, verified run/artifact URLs, and verdict. Do not mark CI green as scientific success without evidence. A Publisher-native acceptance claim requires native Publisher evidence, not hosted Reader reopen.
7. Never publish source/candidate PUB, Story contents, unknown Quill bytes, private local paths, licensed Publisher binaries, or tokens. Keep experiments source-safe and bounded.

## What the local CI gate does — and does not

\`scripts/verify_registry.py\` + \`.github/workflows/sk1-registry-gate.yml\` check uniqueness of IDs/Task IDs/Notion task links/code paths; ID/path classification; valid Notion links/states; legacy folder completeness; and absence of unregistered experiment code. \`scripts/test_verify_registry.py\` includes collision and unauthorized-parked-code negative controls.

**It does not query private Notion leases or enforce GitHub branch protection.** No GitHub-only mechanism can authorize Notion task GO or prevent two externally coordinated agents from independently claiming work. The separate completed \`sk1/cfb-val-pub-t-952\` branch is tracked by provenance in the mirror; it is not auto-merged into \`main\`.

## Useful links

- [SK1 Notion registry and governance history](https://app.notion.com/p/3f532a84beec81ad898de243b3b27c80).
- [Global instruction — write useful findings to Notion](https://app.notion.com/p/3f532a84beec816c9026fba9af3a406c).
- [CFB task 952 (completed)](https://app.notion.com/p/3f532a84beec81539c49ce4d308c7011).
- Parked and not authorized: [QUILL-EXP 953](https://app.notion.com/p/3f532a84beec81f7b53ddd902271da33), [QUILL-DIAG 954](https://app.notion.com/p/3f532a84beec819fb606e8a9b61f0bf1), [VERSIONS-CMP 955](https://app.notion.com/p/3f532a84beec81cea03de5c517c3c8e1).
