# PUB-T-973 — four-byte SYID carry after two inverse Writer edits

[Canonical Notion task](https://app.notion.com/p/3f532a84beec8176aec6c23cd37e8773).

## New, nonduplicate question

PUB-T-965 demonstrated 1-, 2-, and 3-byte changes in the SYID header after a semantic inverse Writer pair, plus the 32-bit overflow guard. This experiment tests **four-byte carry**, which was explicitly excluded from its conclusions. It does not reimplement the Quill parser, Reader, Writer, or the old test harness.

The test has **three existing independently SHA-verified source PUB files** from PUB-T-965, **six** new predeclared synthetic Quill/SYID first DWORD values on each source, and two actual Writer inverse orders per variant: **36 total paths**, not 36 independent Publisher documents.

| Original SYID | +2 predicted | Raw changed bytes predicted |
|---|---|---|
| `0x00FFFFFD` | `0x00FFFFFF` | 1 (no carry control) |
| `0x00FFFFFE` | `0x01000000` | 4 |
| `0x00FFFFFF` | `0x01000001` | 4 |
| `0x01FFFFFE` | `0x02000000` | 4 |
| `0x7FFFFFFE` | `0x80000000` | 4 |
| `0xFEFFFFFE` | `0xFF000000` | 4 |

## Implementation reuse and controls

The experiment version-controls only `prepare.py` plus its workflow, README and registry entry. CI pulls the exact PUB-T-965 *scientific code commit* `72f3c823186ec0e47d5c398f7e1118a7ba4814bb`, verifies its three original git blob hashes, then modifies only the constant matrix, version labels, prior evidence SHA and admission count. The pinned `rar2@703808408fd919e564a90cdc236e81db3c04af8b` compiles the original Writer in an ephemeral GitHub worker. There is **no second Writer or copied permanent Rust harness**.

Admission controls are inherited unchanged: original public source SHA/size and baseline inverse pair, exact Quill-SYID-only synthetic source patch, full-file raw byte preservation elsewhere, Reader/Editor Story identity checks, two isolated inverse orderings, semantic reopen, sibling story retention, byte-equal EditorProject replay and full-PUB byte + Quill/CFB independent comparisons. Unexpected Writer blocks or counterexamples are logged as outcomes, not silently removed. Only three source-safe JSON files are uploaded; no raw PUB or text.

## Reproduce

[GitHub workflow](https://github.com/calex794/sk1/actions/workflows/sk1-cfb-exp-pub-t-973.yml) on branch `sk1/cfb-exp-pub-t-973`. Baseline [PUB-T-965 scientific action](https://github.com/calex794/sk1/actions/runs/38088671197) and its [Notion proof](https://app.notion.com/p/3f532a84beec815f80e1c49e211c81f2).

Pass/fail scientific verdict is recorded in Notion after downloading and independently checking the exact ZIP, not simply because CI completed. Pinned hosted Writer only; native Microsoft Publisher acceptance not evaluated. No `rar2` changes.
