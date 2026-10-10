#!/usr/bin/env python3
"""SK1-EXP-003 source-safe validation and exact EXP-002 deletion calibration."""
from pathlib import Path
from collections import Counter
import json
import re
import sys

SHA = re.compile(r"^[0-9a-f]{64}$")
CODE = re.compile(r"^[a-z_]{1,64}$")
FIELDS = {"schema","upstream_commit","source_manifest","native_publisher_acceptance",
          "product_pub_download_authorized","summary","records"}
ROWS = {"source_sha256","source_type","source_bytes","status","result",
        "source_story_count","eligible_story_attempts","stories"}
ACTIONS = {"operation","delta_utf16","before_utf16_units","after_utf16_units",
           "slot","ascii_rank","ascii_total","offset_utf16","story_utf16_len",
           "relative_per_mille","prev_is_cr","next_is_cr","result",
           "writer_blocker_code","replay_byte_equal","quill_syid_siblings_preserved",
           "candidate_sha256"}
OUTCOMES = {"HOSTED_PASS","writer_blocked","CANONICAL_EDIT_REJECTED",
            "reader_or_editor_reopen_blocked","project_replay_blocked",
            "bounded_candidate_validation_failed","NOT_EVALUATED",
            "SYID_OR_UNRELATED_STORY_MISMATCH","SYID_VERIFICATION_UNAVAILABLE"}
EXPECTED = {
    "first": {"HOSTED_PASS": 11, "quill_edit_touches_fd_boundary": 53, "quill_token_layer": 1},
    "second": {"HOSTED_PASS": 64, "quill_token_layer": 1},
    "middle": {"HOSTED_PASS": 63, "quill_token_layer": 1},
}
DENOMINATORS = {"first":65,"second":65,"middle":64}
PAIR_STATUS = {"both_pass","delete_only","insert_only","both_fail"}

def outcome(a):
    return a.get("writer_blocker_code","writer_blocked_unknown") if a["result"] == "writer_blocked" else a["result"]

def check(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert set(data) == FIELDS
    assert data["schema"] == "sk1.exp003.report.v1"
    assert data["upstream_commit"] == "703808408fd919e564a90cdc236e81db3c04af8b"
    assert data["native_publisher_acceptance"] == "NOT_EVALUATED"
    assert data["product_pub_download_authorized"] is False
    records = data["records"]
    assert isinstance(records,list) and len(records)==26
    assert len({x["source_sha256"] for x in records}) == 26
    baseline = {slot:Counter() for slot in EXPECTED}
    byarm = {slot:{"delete_one":Counter(),"insert_one":Counter()} for slot in EXPECTED}
    matrix = {slot:Counter() for slot in EXPECTED}
    witness = []
    story_n = position_n = attempts_n = 0
    for rec in records:
        assert set(rec) <= ROWS
        assert SHA.fullmatch(rec["source_sha256"])
        assert rec["source_type"] in {"github","institutional-web"}
        assert isinstance(rec["source_bytes"],int) and 0 < rec["source_bytes"] <= 12*1024*1024
        assert rec["status"] == "EVALUATED"
        assert rec["result"] in {"EVALUATED","NO_PLAIN_EDITABLE_STORY","SOURCE_EDITOR_OPEN_BLOCKED"}
        stories=rec["stories"]
        assert isinstance(stories,list) and len(stories)<=3
        assert rec["eligible_story_attempts"] == len(stories)
        for i,story in enumerate(stories):
            assert set(story) == {"story_ordinal","story_utf16_len","ascii_total","attempts"}
            assert story["story_ordinal"] == i
            assert story["story_utf16_len"] >= 1 and story["ascii_total"] >= 1
            arms=story["attempts"]
            assert 2 <= len(arms) <= 6 and len(arms)%2==0
            seen=set()
            story_n+=1
            for j in range(0,len(arms),2):
                delete,insert=arms[j:j+2]
                for a in (delete,insert):
                    assert set(a) <= ACTIONS
                    assert a["result"] in OUTCOMES
                    assert isinstance(a["offset_utf16"],int) and 0 <= a["offset_utf16"] < story["story_utf16_len"]
                    assert a["story_utf16_len"] == story["story_utf16_len"]
                    assert a["ascii_total"] == story["ascii_total"]
                    assert 0 <= a["ascii_rank"] < story["ascii_total"]
                    assert 0 <= a["relative_per_mille"] <= 1000
                    assert isinstance(a["prev_is_cr"],bool) and isinstance(a["next_is_cr"],bool)
                    if a["result"] == "writer_blocked":
                        assert CODE.fullmatch(a.get("writer_blocker_code",""))
                    else:
                        assert "writer_blocker_code" not in a
                    if a["result"] == "HOSTED_PASS":
                        assert SHA.fullmatch(a["candidate_sha256"])
                        assert a["replay_byte_equal"] is True
                        assert a["quill_syid_siblings_preserved"] is True
                    if "candidate_sha256" in a:
                        assert SHA.fullmatch(a["candidate_sha256"])
                assert delete["operation"] == "delete_one" and insert["operation"] == "insert_one"
                assert delete["delta_utf16"] == -1 and insert["delta_utf16"] == 1
                assert delete["before_utf16_units"] == insert["before_utf16_units"] == story["story_utf16_len"]
                assert delete["after_utf16_units"] == story["story_utf16_len"] - 1
                assert insert["after_utf16_units"] == story["story_utf16_len"] + 1
                assert delete["slot"] == insert["slot"] and delete["slot"] in EXPECTED
                assert delete["offset_utf16"] == insert["offset_utf16"]
                assert delete["ascii_rank"] == insert["ascii_rank"]
                assert delete["offset_utf16"] not in seen
                seen.add(delete["offset_utf16"])
                position_n += 1
                attempts_n += 2
                slot = delete["slot"]
                d,o=outcome(delete),outcome(insert)
                baseline[slot][d]+=1
                byarm[slot]["delete_one"][d]+=1
                byarm[slot]["insert_one"][o]+=1
                kind=("both_pass" if d==o=="HOSTED_PASS" else
                      "delete_only" if d=="HOSTED_PASS" else
                      "insert_only" if o=="HOSTED_PASS" else "both_fail")
                matrix[slot][kind]+=1
                if d!=o:
                    witness.append({
                        "source_sha256":rec["source_sha256"],
                        "story_ordinal":i,"slot":slot,
                        "offset_utf16":delete["offset_utf16"],
                        "delete_outcome":d,"insert_outcome":o})
    assert story_n == 65
    assert position_n == sum(DENOMINATORS.values()) == 194
    assert attempts_n == 388
    assert {k:dict(sorted(v.items())) for k,v in baseline.items()} == EXPECTED
    summary=data["summary"]
    assert set(summary)=={"source_count","evaluated_sources","not_evaluated_sources","story_cases",
                          "matched_positions","arm_attempts","deletion_control",
                          "outcomes_by_slot_and_arm","matched_pair_outcomes","discordant_witnesses"}
    assert summary["source_count"]==summary["evaluated_sources"]==26
    assert summary["not_evaluated_sources"]==0
    assert summary["story_cases"]==story_n
    assert summary["matched_positions"]==position_n and summary["arm_attempts"]==attempts_n
    assert summary["deletion_control"] == {k:dict(sorted(v.items())) for k,v in baseline.items()}
    assert summary["outcomes_by_slot_and_arm"] == {
        k:{arm:dict(sorted(counter.items())) for arm,counter in arms.items()} for k,arms in byarm.items()}
    assert summary["matched_pair_outcomes"] == {k:dict(sorted(v.items())) for k,v in matrix.items()}
    assert summary["discordant_witnesses"] == witness
    print("SK1-EXP-003: 26 sources / 65 Stories / 194 matched pairs / 388 source-safe attempts validated")

if __name__ == "__main__":
    assert len(sys.argv)==2
    check(sys.argv[1])
