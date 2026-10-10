#!/usr/bin/env python3
"""Public-receipt schema guard. No raw PUB bytes and no Story text."""
import json
import sys
from pathlib import Path

SAFE_STATUSES = {
    "HOSTED_PASS", "OTHER_STORIES_CHANGED_OR_IDENTITY_DRIFT",
    "CANONICAL_EDIT_REJECTED", "writer_blocked", "reader_or_editor_reopen_blocked",
    "project_replay_blocked", "bounded_candidate_validation_failed", "NOT_EVALUATED"
}
SAFE_KEYS = {
    "arm", "before_utf16_units", "after_utf16_units", "result",
    "writer_blocker_code", "output_sha256", "candidate_bytes",
    "project_replay_byte_equal", "other_story_text_and_identity_preserved"
}
HEX = set("0123456789abcdef")
def sha(v):
    return isinstance(v, str) and len(v) == 64 and set(v) <= HEX

def validate(report):
    assert report["schema"] == "sk1.exp001.result.v1"
    assert report["upstream_commit"] == "703808408fd919e564a90cdc236e81db3c04af8b"
    assert report["native_publisher_acceptance"] == "NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    records = report["records"]
    assert isinstance(records, list) and len(records) <= 35
    assert len(set(row["source_sha256"] for row in records)) == len(records)
    assert report["summary"]["source_count"] == len(records)
    counts = {"EVALUATED": 0, "NOT_EVALUATED": 0}
    for row in records:
        assert sha(row["source_sha256"])
        assert set(row) <= {
            "source_sha256", "source_type", "source_bytes", "status", "reason",
            "source_story_count", "eligible_story_attempts", "attempts"
        }
        assert row["status"] in counts
        counts[row["status"]] += 1
        for arm in row.get("attempts", []):
            assert set(arm) <= SAFE_KEYS
            assert arm["arm"] in ("ascii_replace", "ascii_delete")
            assert arm["result"] in SAFE_STATUSES
            assert 0 <= arm["after_utf16_units"] <= 10_000_000
            assert 0 <= arm["before_utf16_units"] <= 10_000_000
            if "output_sha256" in arm:
                assert sha(arm["output_sha256"])
            if "writer_blocker_code" in arm:
                code = arm["writer_blocker_code"]
                assert isinstance(code, str) and 0 < len(code) <= 64
                assert set(code) <= set("abcdefghijklmnopqrstuvwxyz_")
    assert report["summary"]["evaluated"] == counts["EVALUATED"]
    assert report["summary"]["not_evaluated"] == counts["NOT_EVALUATED"]

if __name__ == "__main__":
    assert len(sys.argv) == 2
    validate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    print("source-safe receipt schema PASS")
