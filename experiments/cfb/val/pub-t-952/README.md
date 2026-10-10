# SK1-CFB-VAL-PUB-T-952 — real-corpus logical stream preservation

- **Canonical task:** [PUB-T-952 / Notion](https://app.notion.com/p/3f532a84beec81539c49ce4d308c7011)
- **Agent Run:** [PUB-RUN-745](https://app.notion.com/p/3f532a84beec817bada8da2d5db4249c)
- **Classification:** SK1 / CFB / VAL. This uses an existing canonical Notion Task ID, not a sequential EXP number.
- **Question:** when the *existing* Writer accepts a single-character deletion on an independent SHA-pinned PUB, does it preserve every non-Quill logical CFB stream byte for byte and preserve the directory's names/kinds?

## Exact reproducible scope

- Baseline: `Lalalalendia/rar2@703808408fd919e564a90cdc236e81db3c04af8b`, never modified in the upstream repo.
- Corpus: original EXP-001/002 pinned 35-source manifest, 26 admitted public URLs through EXP-001 host and exact SHA/size/CFB gates. No customer/private files, new fetch hosts or fresh sampling.
- For **all 65 eligible Stories**, rerun the first ASCII deletion to validate the exact EXP-002 baseline: 11 Writer PASS, 53 `quill_edit_touches_fd_boundary`, 1 `quill_token_layer`. Abort evidence acceptance on any baseline drift.
- For at most two *different successful source/Story/offset ranges per input file*, measure CFB preservation. Try deterministic `first`, `second`, then `middle` within each eligible Story. Stop CFB selection at two per source; still run all first-position baseline controls.
- Run existing Editor/Writer, actual output Editor reopen, exact target text, Quill SYID count/identity and untouched Story semantics, deterministic EditorProject replay, original source SHA and candidate SHA checks. A blocked Writer does not generate a CFB candidate.
- Compare original and candidate with the **upstream** `pub_cfb::inspect_reader` inventory and `pub_cfb::read_stream_reader` for every stream. Match exact logical path and entry kind; compare each non-Quill stream payload in memory **byte by byte** and count changes/length changes. Treat Quill as the only expected changed stream. Report storage/root length changes separately from the stream-integrity verdict.
- Controls: 10 deterministic Writer-negative first-position cases, 10 immutable source Reader-open controls. Outcomes `SOURCE_EDITOR_OPEN_BLOCKED` and `NO_PLAIN_EDITABLE_STORY` are explicit non-applicable categories, not Writer corruption.

## Source-safe evidence gate

The worker creates only `plan.json`, `records.json`, and `report.json` as public artifacts, **after** schema checker passes. Only source/candidate SHA, counts, Story ordinal, operation offsets and machine blocker codes are allowed. Neither the original nor a modified PUB, stream names, stream contents, tokens, Story text, unknown bytes, or private paths may be uploaded.

Scientific outcomes are kept separate:
- Positive result: exact scoped stream and CFB-directory invariants hold for all *actually accepted* candidates.
- Counterexample: one or more non-target payloads change, a stream appears/disappears, an entry type changes or Quill is unchanged.
- Not evaluated: missing public input, invalid harness/receipt or baseline drift.

This does **not** establish physical CFB sector identity, Publisher Open/SaveAs/Reload acceptance, arbitrary Writer safety or product PUB download.

## Reproduction

The [workflow](https://github.com/calex794/sk1/actions/workflows/sk1-cfb-val-pub-t-952.yml) checks out only immutable upstream, compiles a disposable Rust example into the pinned checkout, runs the canonical positive control, then runs this SHA-gated intake and fail-closed JSON validator. Other SK1 experiments, rar2 product code and local Publisher/Codex are untouched. The Notion task is not Done until a completed Actions run **and** exact per-case artifact have been verified and a bounded verdict written.
