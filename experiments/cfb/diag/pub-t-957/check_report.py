#!/usr/bin/env python3
"""PUB-T-957 fail-closed source-safe receipt contract and 77 double-PASS baseline."""
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
             "both_final_byte_equal","insert_delete_cfb","delete_insert_cfb"}
DIFF_FIELDS={
    "source_syid_first_dword","final_syid_first_dword","syid_first_dword_delta",
    "same_syid_live_ids","same_syid_count",
    "syid_first_dword_changed_bytes","quill_changed_bytes_outside_syid_first_dword",
    "schema","source_file_bytes","final_file_bytes","source_directory_entries",
    "final_directory_entries","missing_cfb_paths","added_cfb_paths",
    "cfb_entry_type_changes","non_quill_streams_checked","non_quill_streams_changed",
    "quill_streams_found","quill_bytes_equal","all_logical_streams_equal",
    "physical_only_container_difference","whole_file_equal",
    "source_quill_bytes","final_quill_bytes","source_quill_sha256","final_quill_sha256",
    "quill_differing_byte_positions_equal_len","same_quill_story_syid_sequence",
    "same_quill_story_utf16_lengths","same_quill_TEXT_payload_bytes",
    "source_quill_descriptor_count","final_quill_descriptor_count",
    "matched_descriptor_sequence","altered_chunk_payload_count",
    "equal_chunk_payload_count","altered_chunks_by_kind",
    "altered_descriptor_offsets","altered_descriptor_lengths","altered_descriptor_options",
    "publisher_native_acceptance","source_pub_output_authorized"
}
KINDS={"TEXT","SYID","STRS","FDPP","FDPC","BTEP","BTEC","TOKN","TCD","OTHER"}

def check_diff(d):
    assert isinstance(d,dict) and set(d)==DIFF_FIELDS
    assert d["schema"]=="sk1.cfb-diag-pub-t-957.diff.v1"
    bool_keys={"same_syid_live_ids","same_syid_count","quill_bytes_equal","all_logical_streams_equal",
        "physical_only_container_difference","whole_file_equal",
        "same_quill_story_syid_sequence","same_quill_story_utf16_lengths",
        "same_quill_TEXT_payload_bytes","matched_descriptor_sequence"}
    for key in bool_keys:
        assert type(d[key]) is bool,key
    assert d["publisher_native_acceptance"]=="NOT_EVALUATED"
    assert d["source_pub_output_authorized"] is False
    sha64=lambda value:isinstance(value,str) and SHA.fullmatch(value)
    assert sha64(d["source_quill_sha256"]) and sha64(d["final_quill_sha256"])
    null_int={"syid_first_dword_changed_bytes","quill_changed_bytes_outside_syid_first_dword",
        "quill_differing_byte_positions_equal_len",
        "altered_chunk_payload_count","equal_chunk_payload_count",
        "altered_descriptor_offsets","altered_descriptor_lengths","altered_descriptor_options"}
    integers=DIFF_FIELDS-bool_keys-null_int-{
        "schema","publisher_native_acceptance","source_pub_output_authorized",
        "source_quill_sha256","final_quill_sha256","altered_chunks_by_kind",
        "syid_first_dword_delta"
    }
    for key in integers:
        assert type(d[key]) is int and 0<=d[key]<=2**31,key
    assert 0<=d["source_syid_first_dword"]<=2**32-1
    assert 0<=d["final_syid_first_dword"]<=2**32-1
    assert type(d["syid_first_dword_delta"]) is int
    assert d["syid_first_dword_delta"]==(
        d["final_syid_first_dword"]-d["source_syid_first_dword"])
    assert d["same_syid_live_ids"]==d["same_quill_story_syid_sequence"]
    for k in ("syid_first_dword_changed_bytes",
              "quill_changed_bytes_outside_syid_first_dword"):
        assert d[k] is None or (type(d[k]) is int and 0<=d[k]<=12*1024*1024)
    if d["syid_first_dword_changed_bytes"] is not None:
        assert d["quill_changed_bytes_outside_syid_first_dword"] is not None
        assert d["syid_first_dword_changed_bytes"]<=4
        assert d["quill_differing_byte_positions_equal_len"]==(
            d["syid_first_dword_changed_bytes"]+
            d["quill_changed_bytes_outside_syid_first_dword"])
    else:
        assert d["quill_changed_bytes_outside_syid_first_dword"] is None
    assert d["source_file_bytes"]>0 and d["final_file_bytes"]>0
    assert d["source_quill_bytes"]>0 and d["final_quill_bytes"]>0
    assert d["quill_streams_found"]==1
    assert d["non_quill_streams_changed"]<=d["non_quill_streams_checked"]
    assert d["quill_bytes_equal"]==(d["source_quill_sha256"]==d["final_quill_sha256"])
    if d["source_quill_bytes"]==d["final_quill_bytes"]:
        n=d["quill_differing_byte_positions_equal_len"]
        assert type(n) is int and n>=0
        assert (n==0)==d["quill_bytes_equal"]
    else:
        assert d["quill_differing_byte_positions_equal_len"] is None
        assert d["quill_bytes_equal"] is False
    expected_logical=(d["missing_cfb_paths"]==d["added_cfb_paths"]==
        d["cfb_entry_type_changes"]==d["non_quill_streams_changed"]==0
        and d["quill_bytes_equal"])
    assert d["all_logical_streams_equal"]==expected_logical
    assert d["physical_only_container_difference"]==(
        d["all_logical_streams_equal"] and not d["whole_file_equal"])
    assert not d["whole_file_equal"] or d["all_logical_streams_equal"]
    assert not d["quill_bytes_equal"] or d["same_quill_TEXT_payload_bytes"]
    assert not d["quill_bytes_equal"] or d["same_quill_story_syid_sequence"]
    assert not d["quill_bytes_equal"] or d["same_quill_story_utf16_lengths"]
    changed=d["altered_chunks_by_kind"]
    assert isinstance(changed,dict) and set(changed).issubset(KINDS)
    assert all(type(v) is int and v>0 and v<10000 for v in changed.values())
    if d["matched_descriptor_sequence"]:
        for key in null_int-{"quill_differing_byte_positions_equal_len",
                             "syid_first_dword_changed_bytes",
                             "quill_changed_bytes_outside_syid_first_dword"}:
            assert type(d[key]) is int and 0<=d[key]<100000,key
        assert d["source_quill_descriptor_count"]==d["final_quill_descriptor_count"]
        assert d["altered_chunk_payload_count"]==sum(changed.values())
        assert (d["equal_chunk_payload_count"]+d["altered_chunk_payload_count"]
                ==d["source_quill_descriptor_count"])
        if d["quill_bytes_equal"]:
            assert d["altered_chunk_payload_count"]==0
            assert d["altered_descriptor_offsets"]==0
            assert d["altered_descriptor_lengths"]==0
            assert d["altered_descriptor_options"]==0
    else:
        assert changed=={}
        for key in null_int-{"quill_differing_byte_positions_equal_len"}:
            assert d[key] is None

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
    assert r["schema"]=="sk1.pub-t-957.report.v1"
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
                    for key,step in (("insert_delete_cfb",p["insert_then_delete"]),
                                     ("delete_insert_cfb",p["delete_then_insert"])):
                        if step["status"]=="HOSTED_PASS":
                            check_diff(p[key])
                        else:
                            assert p[key] is None
                    assert (isinstance(p["both_final_byte_equal"],bool)
                            if (p["insert_then_delete"]["status"]==
                                p["delete_then_insert"]["status"]=="HOSTED_PASS")
                            else p["both_final_byte_equal"] is None)
                else:
                    assert p["insert_then_delete"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
                    assert p["delete_then_insert"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
                    assert all(p[k] is None for k in (
                        "insert_delete_returns_original_bytes",
                        "delete_insert_returns_original_bytes",
                        "both_final_byte_equal","insert_delete_cfb","delete_insert_cfb"))
    assert story_n==65
    assert case_n==194
    assert slot_total==EXPECTED_SLOTS
    assert both_by_slot==EXPECTED_BOTH
    spec=importlib.util.spec_from_file_location("sk1_956_runner",HERE/"run.py")
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    computed=module.summarize(rows)
    computed["cfb_diff_by_arm"]=module.summarize_cfb(rows)
    assert r["summary"]==computed
    assert computed["both_single_pass"]==77
    assert computed["cfb_diff_by_arm"]["insert_then_delete"]["totals"]["measured_inverse_arms"]==77
    assert computed["cfb_diff_by_arm"]["delete_then_insert"]["totals"]["measured_inverse_arms"]==75
    print("PUB-T-957: 26 source SHA / 65 Stories / 194 positions / 77 matched reversible base cases PASS")

if __name__=="__main__":
    assert len(sys.argv)==2
    target=Path(sys.argv[1])
    plan=json.loads((target/"plan.json").read_text())
    assert plan["schema"]=="sk1.pub-t-957.plan.v1"
    assert plan["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert plan["predecessor_956_scientific_sha"]=="08abf5c7d92fb5ca56fd3ff84009309120fcf52c"
    assert plan["predecessor_956_artifact_zip_sha256"]=="afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427"
    r=json.loads((target/"report.json").read_text())
    assert json.loads((target/"records.json").read_text())==r["records"]
    check(target/"report.json")
