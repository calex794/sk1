#!/usr/bin/env python3
"""Fail-closed public artifact checker for SK1 CFB preservation study."""
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"^[0-9a-f]{64}$")
CODE = re.compile(r"^[a-z_]{1,64}$")
ALLOWED_STATUS = {
    "HOSTED_PASS", "writer_blocked", "CANONICAL_EDIT_REJECTED",
    "reader_or_editor_reopen_blocked", "project_replay_blocked",
    "bounded_candidate_validation_failed", "NOT_EVALUATED",
    "SYID_OR_UNRELATED_STORY_MISMATCH", "SYID_VERIFICATION_UNAVAILABLE"
}
SLOTS = ["first", "second", "middle"]
ALLOWED_POSITION_KEYS = {
    "slot", "ascii_rank", "ascii_total", "offset_utf16", "story_utf16_len",
    "relative_per_mille", "prev_is_cr", "next_is_cr", "result",
    "writer_blocker_code", "replay_byte_equal", "quill_syid_siblings_preserved",
    "candidate_sha256", "cfb"
}
ALLOWED_RECORD_KEYS = {
    "source_sha256", "source_type", "source_bytes", "status", "result",
    "source_story_count", "eligible_story_attempts", "stories",
    "cfb_selected_count", "source_file_unchanged"
}


CFB_KEYS = {
    "preserved", "source_directory_entries", "output_directory_entries",
    "missing_paths", "new_paths", "entry_type_changes",
    "other_streams_checked", "other_streams_changed",
    "other_stream_length_changes", "non_stream_length_changes",
    "quill_found", "quill_changed",
}

def checked_cfb(c):
    assert isinstance(c, dict) and set(c) == CFB_KEYS
    for key in CFB_KEYS - {"preserved", "quill_changed"}:
        assert type(c[key]) is int and c[key] >= 0, key
    assert type(c["preserved"]) is bool and type(c["quill_changed"]) is bool
    expected = (c["missing_paths"] == 0 and c["new_paths"] == 0
        and c["entry_type_changes"] == 0 and c["other_streams_changed"] == 0
        and c["other_stream_length_changes"] == 0 and c["quill_found"] == 1
        and c["quill_changed"] is True)
    assert c["preserved"] == expected
    assert c["other_streams_changed"] <= c["other_streams_checked"]

def check(path: Path) -> None:
    r = json.loads(path.read_text(encoding="utf-8"))
    assert set(r) == {
        "schema", "upstream_commit", "source_manifest",
        "native_publisher_acceptance", "product_pub_download_authorized",
        "summary", "records"
    }
    assert r["schema"] == "sk1.cfb-val-pub-t-952.report.v1"
    assert r["upstream_commit"] == "703808408fd919e564a90cdc236e81db3c04af8b"
    assert r["native_publisher_acceptance"] == "NOT_EVALUATED"
    assert r["product_pub_download_authorized"] is False
    rows = r["records"]
    assert len(rows) == 26
    assert len({x["source_sha256"] for x in rows}) == 26
    first = {}
    n_stories = n_attempts = 0
    chosen = []
    source_immutable = 0
    noop = 0
    negative_control = 0
    by_slot = {}
    for row in rows:
        assert set(row) <= ALLOWED_RECORD_KEYS
        assert SHA.fullmatch(row["source_sha256"])
        assert row["source_type"] in {"github", "institutional-web"}
        assert isinstance(row["source_bytes"], int) and 0 < row["source_bytes"] <= 12*1024*1024
        assert row["status"] == "EVALUATED", "missing data must not count as Writer failure"
        assert row["source_file_unchanged"] is True
        source_immutable += 1
        if row["result"] == "EVALUATED":
            noop += 1
        selected_here = 0
        assert row["result"] in {"EVALUATED", "NO_PLAIN_EDITABLE_STORY", "SOURCE_EDITOR_OPEN_BLOCKED"}
        stories = row["stories"]
        assert isinstance(stories, list) and len(stories) <= 3
        assert row["eligible_story_attempts"] == len(stories)
        for idx, story in enumerate(stories):
            assert set(story) == {"story_ordinal", "story_utf16_len", "ascii_total", "attempts"}
            assert story["story_ordinal"] == idx
            assert story["story_utf16_len"] >= 1 and story["ascii_total"] >= 1
            attempts = story["attempts"]
            assert 1 <= len(attempts) <= 3
            assert attempts[0]["slot"] == "first"
            used_offsets = set()
            n_stories += 1
            n_attempts += len(attempts)
            for a in attempts:
                assert set(a) <= ALLOWED_POSITION_KEYS
                assert a["slot"] in SLOTS and a["result"] in ALLOWED_STATUS
                assert isinstance(a["offset_utf16"], int) and 0 <= a["offset_utf16"] < story["story_utf16_len"]
                assert a["offset_utf16"] not in used_offsets
                used_offsets.add(a["offset_utf16"])
                assert a["story_utf16_len"] == story["story_utf16_len"]
                assert a["ascii_total"] == story["ascii_total"]
                assert isinstance(a["ascii_rank"], int) and 0 <= a["ascii_rank"] < a["ascii_total"]
                assert 0 <= a["relative_per_mille"] <= 1000
                assert isinstance(a["prev_is_cr"], bool) and isinstance(a["next_is_cr"], bool)
                if a["result"] == "writer_blocked":
                    assert CODE.fullmatch(a.get("writer_blocker_code", ""))
                else:
                    assert "writer_blocker_code" not in a
                if a["result"] == "HOSTED_PASS":
                    assert SHA.fullmatch(a["candidate_sha256"])
                    assert a["replay_byte_equal"] is True
                    assert a["quill_syid_siblings_preserved"] is True
                else:
                    assert "candidate_sha256" not in a or SHA.fullmatch(a["candidate_sha256"])
                outcome = a.get("writer_blocker_code", "writer_blocked_unknown") if a["result"] == "writer_blocked" else a["result"]
                by_slot.setdefault(a["slot"], {})
                by_slot[a["slot"]][outcome] = by_slot[a["slot"]].get(outcome, 0) + 1
                if a["slot"] == "first":
                    first[outcome] = first.get(outcome, 0) + 1
                    if a["result"] == "writer_blocked":
                        negative_control += 1
                if "cfb" in a:
                    assert a["result"] == "HOSTED_PASS"
                    checked_cfb(a["cfb"])
                    selected_here += 1
                    chosen.append(a["cfb"])
        assert selected_here == row["cfb_selected_count"] and selected_here <= 2
    assert n_stories == 65, f"expected 65 matched Story cases, got {n_stories}"
    assert first == {
        "HOSTED_PASS": 11,
        "quill_edit_touches_fd_boundary": 53,
        "quill_token_layer": 1
    }, f"EXP-001 first-position baseline mismatch: {first}"
    assert 10 <= len(chosen) <= 52
    summary = r["summary"]
    assert summary["evaluated_sources"] == 26 and summary["not_evaluated_sources"] == 0
    assert summary["story_cases"] == n_stories
    assert summary["attempted_deletions"] == n_attempts
    assert summary["first_control"] == dict(sorted(first.items()))
    assert summary["by_slot"] == {k:dict(sorted(v.items())) for k,v in sorted(by_slot.items())}
    assert all(SHA.fullmatch(w["source_sha256"]) for w in summary["recoverable_story_witnesses"])
    stats = summary["cfb"]
    assert stats["measured_candidates"] == len(chosen)
    assert stats["preserved_candidates"] == sum(int(c["preserved"]) for c in chosen)
    assert stats["violating_candidates"] == len(chosen) - stats["preserved_candidates"]
    assert stats["source_immutability_checked"] == source_immutable == 26
    assert stats["negative_writer_controls"] == min(10, negative_control) == 10
    assert stats["no_op_source_reader_controls"] == min(10, noop) == 10
    for name, field in [
        ("other_streams_checked", "other_streams_checked"),
        ("other_streams_changed", "other_streams_changed"),
        ("added_paths", "new_paths"),
        ("missing_paths", "missing_paths"),
        ("entry_type_changes", "entry_type_changes"),
        ("non_stream_length_changes", "non_stream_length_changes"),
    ]:
        assert stats[name] == sum(c[field] for c in chosen)
    assert len(stats["counterexamples"]) == stats["violating_candidates"]
    for witness in stats["counterexamples"]:
        assert set(witness) == {
            "source_sha256", "story_ordinal", "slot", "offset_utf16", "candidate_sha256", "cfb"
        }
        assert SHA.fullmatch(witness["source_sha256"])
        assert SHA.fullmatch(witness["candidate_sha256"])
        assert witness["slot"] in SLOTS
        checked_cfb(witness["cfb"])
        assert witness["cfb"]["preserved"] is False
    assert summary["first_fd_boundary_recovered_by_nonfirst_position"] <= 53
    assert summary["first_any_failure_recovered_by_nonfirst_position"] >= summary["first_fd_boundary_recovered_by_nonfirst_position"]
    print(f"SK1-CFB-VAL-PUB-T-952: source-safe corpus + {len(chosen)} CFB comparisons PASS")

if __name__ == "__main__":
    assert len(sys.argv) == 2
    check(Path(sys.argv[1]))
