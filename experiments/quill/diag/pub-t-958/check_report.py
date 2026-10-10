#!/usr/bin/env python3
"""PUB-T-958 fail-closed source-safe receipt contract and 77 double-PASS baseline."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
SOURCE_FIELDS={"source_sha256","source_type","source_bytes","status","reason"}
RECORD_FIELDS=SOURCE_FIELDS|{"eligible_story_count","stories"}
STORY_FIELDS={"story_ordinal","story_utf16_length","ascii_total","pairs"}
PAIR_FIELDS={"slot","ascii_rank","ascii_total","offset_utf16",
             "story_utf16_length","ambiguous_reverse_delete_insert_offset",
             "single_insert","single_delete","both_single_pass",
             "insert_then_delete","delete_then_insert",
             "insert_delete_returns_original_bytes",
             "delete_insert_returns_original_bytes",
             "both_final_byte_equal","fd_guard_diagnostic"}
PASS_FIELDS={"status","candidate_sha256","reader_semantic_reopen",
             "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}
SLOTS={"first","second","middle"}
EXPECTED_BOTH={"first":9,"second":34,"middle":34}
EXPECTED_SLOTS={"first":65,"second":65,"middle":64}


FD_FIELDS={
    "original_fd_boundary_at_insert_start",
    "original_fd_boundary_at_deleted_end",
    "fd_after_delete_at_reverse_insert_start",
    "fdpp_after_hit","fdpc_after_hit",
    "source_fdpp_count","source_fdpc_count",
    "post_delete_fdpp_count","post_delete_fdpc_count",
    "source_nearest_fd_distance_bytes",
    "post_delete_nearest_fd_distance_bytes",
    "story_text_start_byte_preserved",
    "fdpp_delete_shift_formula_matches",
    "fdpc_delete_shift_formula_matches"
}
FD_BOOLEANS={
    "original_fd_boundary_at_insert_start",
    "original_fd_boundary_at_deleted_end",
    "fd_after_delete_at_reverse_insert_start",
    "fdpp_after_hit","fdpc_after_hit",
    "story_text_start_byte_preserved",
    "fdpp_delete_shift_formula_matches",
    "fdpc_delete_shift_formula_matches"
}
FD_INTS=FD_FIELDS-FD_BOOLEANS

def check_fd_receipt(d):
    assert isinstance(d,dict) and set(d)==FD_FIELDS
    for key in FD_BOOLEANS: assert isinstance(d[key],bool)
    for key in FD_INTS:
        assert (d[key] is None if "distance" in key else False) or (
            isinstance(d[key],int) and not isinstance(d[key],bool)
            and 0<=d[key]<2**32)
    for key in ("source_fdpp_count","source_fdpc_count",
                "post_delete_fdpp_count","post_delete_fdpc_count"):
        assert d[key]>0
    assert (d["fdpp_after_hit"] or d["fdpc_after_hit"]) == d["fd_after_delete_at_reverse_insert_start"]
    if d["fd_after_delete_at_reverse_insert_start"]:
        assert d["post_delete_nearest_fd_distance_bytes"]==0
    if d["original_fd_boundary_at_insert_start"]:
        assert d["source_nearest_fd_distance_bytes"]==0


def check_step(s):
    assert isinstance(s,dict) and s.get("status") in STEPS
    if s["status"]=="HOSTED_PASS":
        assert set(s)==PASS_FIELDS
        assert SHA.fullmatch(s["candidate_sha256"])
        for flag in PASS_FIELDS-{"status","candidate_sha256"}:
            assert s[flag] is True
    elif s["status"]=="WRITER_BLOCKED":
        assert set(s)=={"status","writer_code"}
        assert CODE.fullmatch(s["writer_code"])
    else:
        assert set(s)=={"status"}

def check(path:Path):
    r=json.loads(path.read_text(encoding="utf-8"))
    assert set(r)=={"schema","rar2_pin","source_manifest",
                   "publisher_native_acceptance",
                   "product_pub_download_authorized","summary","records"}
    assert r["schema"]=="sk1.pub-t-958.report.v1"
    assert r["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert r["publisher_native_acceptance"]=="NOT_EVALUATED"
    assert r["product_pub_download_authorized"] is False
    rows=r["records"]
    assert len(rows)==26
    assert len({x["source_sha256"] for x in rows})==26
    story_n=case_n=0
    both_by_slot={slot:0 for slot in SLOTS}
    slot_total={slot:0 for slot in SLOTS}
    for source in rows:
        assert SHA.fullmatch(source["source_sha256"])
        assert source["source_type"] in {"github","institutional-web"}
        assert isinstance(source["source_bytes"],int) and 0<source["source_bytes"]<=12*1024*1024
        assert source["status"]=="EVALUATED"
        assert source["reason"] in {"EVALUATED","NO_PLAIN_EDITABLE_STORY",
                                   "SOURCE_EDITOR_OPEN_BLOCKED"}
        assert set(source)==RECORD_FIELDS
        stories=source["stories"]
        assert len(stories)<=3
        assert source["eligible_story_count"]==len(stories)
        if source["reason"]!="EVALUATED":
            assert not stories
        for j,story in enumerate(stories):
            assert set(story)==STORY_FIELDS
            assert story["story_ordinal"]==j
            assert story["story_utf16_length"]>=1 and story["ascii_total"]>=1
            pairs=story["pairs"]
            assert 1<=len(pairs)<=3
            seen_offsets=set()
            story_n+=1
            for p in pairs:
                assert set(p)==PAIR_FIELDS
                assert p["slot"] in SLOTS
                assert isinstance(p["offset_utf16"],int)
                assert 0<=p["offset_utf16"]<story["story_utf16_length"]
                assert p["offset_utf16"] not in seen_offsets
                seen_offsets.add(p["offset_utf16"])
                assert p["story_utf16_length"]==story["story_utf16_length"]
                assert p["ascii_total"]==story["ascii_total"]
                assert 0<=p["ascii_rank"]<p["ascii_total"]
                assert isinstance(p["ambiguous_reverse_delete_insert_offset"],bool)
                slot_total[p["slot"]]+=1
                case_n+=1
                check_step(p["single_insert"])
                check_step(p["single_delete"])
                both=(p["single_insert"]["status"]=="HOSTED_PASS" and
                      p["single_delete"]["status"]=="HOSTED_PASS")
                assert p["both_single_pass"] is both
                if both:
                    check_fd_receipt(p["fd_guard_diagnostic"])
                    both_by_slot[p["slot"]]+=1
                    check_step(p["insert_then_delete"])
                    check_step(p["delete_then_insert"])
                    for field,step in [
                        ("insert_delete_returns_original_bytes",p["insert_then_delete"]),
                        ("delete_insert_returns_original_bytes",p["delete_then_insert"])
                    ]:
                        assert (isinstance(p[field],bool)
                                if step["status"]=="HOSTED_PASS"
                                else p[field] is None)
                    assert (isinstance(p["both_final_byte_equal"],bool)
                            if (p["insert_then_delete"]["status"]==
                                p["delete_then_insert"]["status"]=="HOSTED_PASS")
                            else p["both_final_byte_equal"] is None)
                else:
                    assert p["fd_guard_diagnostic"] is None
                    assert p["insert_then_delete"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
                    assert p["delete_then_insert"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
                    assert all(p[k] is None for k in (
                        "insert_delete_returns_original_bytes",
                        "delete_insert_returns_original_bytes",
                        "both_final_byte_equal"))
    assert story_n==65
    assert case_n==194
    assert slot_total==EXPECTED_SLOTS
    assert both_by_slot==EXPECTED_BOTH
    spec=importlib.util.spec_from_file_location("sk1_956_runner",HERE/"run.py")
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    computed=module.summarize(rows)
    computed["fd_guard"]=module.summarize_fd(rows)
    assert r["summary"]==computed
    assert computed["fd_guard"]["eligible_doublepass"]==77
    assert sum(computed["fd_guard"]["matrix"].values())==77
    assert computed["both_single_pass"]==77
    print("PUB-T-958: 26 source SHA / 65 Stories / 194 positions / 77 verified FD geometry paired cases PASS")

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
