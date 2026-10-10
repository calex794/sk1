# PUB-T-965 — synthetic SYID carry / overflow in pinned Writer

Task: https://app.notion.com/p/3f532a84beec81cc8c74ce9beb18c519

New independent question: does the physically byte-local first DWORD of Quill SYID change in 2 or 3 bytes when u32 +2 crosses one or two byte boundaries? What is the actual pinned Writer outcome near u32 exhaustion?

Three exact public SHA from the verified PUB-T-963 sample, one previously successful Story/offset control per source (first editable Story, second ASCII, UTF-16 offset 1), nine pre-registered synthetic header values per source. No new real Publisher files are claimed.

Only the Quill SYID first DWORD is modified in a transient copy via the existing pinned upstream pub_cfb::replace_stream_reader; admit variant only after whole-file exact-change proof and Reader semantic reopen. The original pub and text never leave the GitHub runner. Both two-step Writer orderings are evaluated, recording hosted guards and counterexamples.

Pinned upstream rar2: 703808408fd919e564a90cdc236e81db3c04af8b. No product changes, no native Publisher acceptance, no second Writer implementation.

Verified original baseline: https://github.com/calex794/sk1/actions/runs/38086988877 ; SHA of ZIP 70aed39805d587b1f4cb32bb96ec8e615c6e4f22b7909438ed1d8685c976b3dc.

CI: .github/workflows/sk1-cfb-exp-pub-t-965.yml. Source-safe outputs: plan.json, records.json, report.json only. Notion evidence is authoritative after independent artifact audit, not after CI alone.
