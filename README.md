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

## Experiment 001
[SK1-EXP-001](https://app.notion.com/p/3f532a84beec81ec9c63e9952fd3e0a3): external, SHA-pinned 35-source **hosted** Quill ordinary-Story Writer/Reader applicability probe, comparing one ASCII character replacement vs deletion. The previously verified Sample3/Four-fixture probe is a *calibration control only*, not new corpus evidence.

See `experiments/sk1-exp-001/README.md` for design, guardrails, commands and result format.
