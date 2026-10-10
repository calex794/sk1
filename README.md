# SK1 — temporary experiment warehouse

Independent, disposable **compute workspace** for long-running bounded Chaptera/PUB experiments. **Not** a second implementation repository.

Canonical product: [Lalalalendia/rar2](https://github.com/Lalalalendia/rar2). Evidence journal: [SK1 — склад экспериментов](https://app.notion.com/p/3f532a84beec81ad898de243b3b27c80).

## Multi-agent coordination — enforced repository metadata

**Read [AGENTS.md](AGENTS.md) before working.** Task IDs now derive from **Notion Research Tasks**, not the next `SK1-EXP` number: `SK1-{AREA}-{TYPE}-{PUB-T-NNN}`. The canonical [experiment identity registry](experiments/registry.json) lists 5 completed legacy studies, 4 completed classified tasks (PUB-T-952/953/954/956) on independent branches, and 1 `Parked` task (PUB-T-955).

[Registry validator](scripts/verify_registry.py) and [GitHub Actions collision check](.github/workflows/sk1-registry-gate.yml) reject duplicate task IDs, unregistered executable experiment folders, and code under Parked tasks. [Verified Actions run #38081749951](https://github.com/calex794/sk1/actions/runs/38081749951). **Notion still owns the actual GO, assignee and lease; the CI check does not grant permission to run a task.**

## Operating contract
- One experiment has a precise question, immutable baseline/source identities, admission limits, controls, exact executable receipt and conclusion.
- Reuse upstream code and confirmed fixtures; do not implement a second Reader/Writer/Editor.
- Output either **portable engineering evidence/code for rar2** or **portable knowledge for Notion** (including falsified hypotheses and negative controls).
- Never upload source/candidate PUB, user files, Story text, tokens, licensed Publisher runtime, or secret locations to a public repository or public Actions artifacts.
- Experiments do not authorize native Publisher save, product download, release maturity, or changes in upstream tasks/claims.
- After a completed run, reconcile evidence in Notion; SK1 code may be discarded.

## Experiment index — Notion is the durable result store

| ID | Independent question | Verified run | Verdict / permanent evidence |
| --- | --- | --- | --- |
| [SK1-EXP-001](experiments/sk1-exp-001/README.md) | Writer applicability on 26 SHA-pinned PUB; replacement vs deletion | [Actions #38076391741](https://github.com/calex794/sk1/actions/runs/38076391741) | [Notion: result, 65 Story cases](https://app.notion.com/p/3f532a84beec81ec9c63e9952fd3e0a3) |
| [SK1-EXP-002](experiments/sk1-exp-002/README.md) | Deletion outcome by position on same Story | [Actions #38077356809](https://github.com/calex794/sk1/actions/runs/38077356809) | [Notion: 355 attempts; 53 FD-blocked first positions recover at second](https://app.notion.com/p/3f532a84beec81d6b406fc10231e1310) |
| [SK1-EXP-003](experiments/sk1-exp-003/README.md) | Matched +1 insertion vs -1 deletion at same source/Story/UTF-16 offset | [Actions #38078248161](https://github.com/calex794/sk1/actions/runs/38078248161) | [Notion: 194 pairs; 61 delete-only due growth guard](https://app.notion.com/p/3f532a84beec81ec92f9e64a490be67c) |
| [SK1-EXP-004](experiments/sk1-exp-004/README.md) | Read-only two-byte Quill protected tail geometry and descriptor-ownership census | [Actions #38078782351](https://github.com/calex794/sk1/actions/runs/38078782351) | [Notion: physical guard predicate matches 10 blocked, 13 allowed SHA sources; 2 parser-ineligible](https://app.notion.com/p/3f532a84beec81fda307fd18807f1117) |
| [SK1-EXP-005](experiments/sk1-exp-005/README.md) | Independent 62-source holdout; 59 SHA-valid, 50 discriminating | [Actions #38079437141](https://github.com/calex794/sk1/actions/runs/38079437141) + [repeat #38079594804](https://github.com/calex794/sk1/actions/runs/38079594804) | [Notion: TP 10, TN 40, FP/FN 0; repeated identical records](https://app.notion.com/p/3f532a84beec81c2a98ef2d6629a54d9) |

**Experiments 001–005 are completed with portable knowledge in Notion. EXP-005 has two matching verified runs on the same holdout corpus; their results must not be double counted. No parallel Writer implementation exists and no code has been merged into `rar2`.** Actions artifacts expire; the corresponding Notion pages contain outcomes, source SHAs and precise run/commit identities. Future work must ask a *new* question, not rescan the same corpus for the same arms.

## Classified tasks — canonical statuses in Notion

These are **historical completed experiments**, not a new queue or a license to repeat them. Their source-safe code remains on isolated SK1 branches; no Writer/Reader implementation was merged into `rar2`.

| Task | Status | Reproducible evidence | Transfer / result |
| --- | --- | --- | --- |
| [CFB-VAL PUB-T-952](https://app.notion.com/p/3f532a84beec81539c49ce4d308c7011) | Done / Closed | [Actions #38080309891](https://github.com/calex794/sk1/actions/runs/38080309891) | [Notion: 434/434 non-Quill streams preserved](https://app.notion.com/p/3f532a84beec81f5a650d93e1d3f380d) |
| [QUILL-EXP PUB-T-953](https://app.notion.com/p/3f532a84beec81f7b53ddd902271da33) | Done / Closed | [Actions #38082180136](https://github.com/calex794/sk1/actions/runs/38082180136) | [Notion: 24/24 AB+BA pass, matching final SHA](https://app.notion.com/p/3f532a84beec81f78424f8658052ada5) |
| [QUILL-DIAG PUB-T-954](https://app.notion.com/p/3f532a84beec819fb606e8a9b61f0bf1) | Done / Closed | [Actions #38083133702](https://github.com/calex794/sk1/actions/runs/38083133702) | [Notion: 1 TOKN positive + 12 controls; not generalizable](https://app.notion.com/p/3f532a84beec81629035ce5678387e27) |
| [VERSIONS-CMP PUB-T-955](https://app.notion.com/p/3f532a84beec81cea03de5c517c3c8e1) | **Blocked / Parked** | No run, no claim, no task branch | Await a *material* Writer change in `rar2`; two different Git commit SHAs alone do not justify a replay |
| [QUILL-EXP PUB-T-956](https://app.notion.com/p/3f532a84beec81519ea3e48383defacd) | Done / Closed | [Actions #38083249275](https://github.com/calex794/sk1/actions/runs/38083249275) | [Notion: inverse operations restore text but not original whole-file SHA](https://app.notion.com/p/3f532a84beec81a38881e695939c3a38) |

**Registry authority:** [Notion Research Tasks](https://app.notion.com/p/1bd5e66edf0d4baf9e303e96265ef10c). The mirrored `experiments/registry.json` is a dated Git snapshot, not a live Notion query. A green GitHub gate does not replace checking task owner/lease and obtaining the operator's explicit GO before any new experiment.
