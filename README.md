# SK1 — temporary experiment warehouse

Independent, disposable **compute workspace** for long-running bounded Chaptera/PUB experiments. **Not** a second implementation repository.

Canonical product: [Lalalalendia/rar2](https://github.com/Lalalalendia/rar2). Evidence journal: [SK1 — склад экспериментов](https://app.notion.com/p/3f532a84beec81ad898de243b3b27c80).

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
