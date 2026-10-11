#!/usr/bin/env python3
"""Independent fail-closed JSON acceptance for one Rust test."""
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
r = json.loads(p.read_text(encoding="utf-8"))
assert r["schema"] == "sk1-quill-val-pub-t-989-result/v1"
assert r["task_id"] == "PUB-T-989"
assert r["source_commit"] == "22a322ed10d9fe8a4ade45acf83bebd0442b691b"
assert r["writer_git_blob_sha1"] == "b33aaf4d261a98efb7d9d487ed73852cbd0ec168"
assert r["sample3_git_blob_sha1"] == "1584a0df824a560a2e7f45e375a71fd312562aba"
assert r["publisher_native"] == "NOT_EVALUATED"
assert r["source_repo_modified_persistently"] is False
assert r["source_injection_verified"] is True
assert r["rust_test_status"] == "PASS"
assert r["cargo_exit_code"] == 0
assert r["passing_named_test_lines"] == 1
assert r["one_test_pass_summary"] is True
assert r["opaque_payload_comparisons_pass"] == 8
assert r["stsh_chunks"] == 3
assert r["font_chunks"] == 1
assert r["source_arms"] == 2
assert r["stage"] == "real_rust_completed"
print("SK1 PUB-T-989: independent report gate PASS, native Publisher NOT_EVALUATED")
