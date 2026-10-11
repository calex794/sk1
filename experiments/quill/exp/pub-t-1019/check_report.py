#!/usr/bin/env python3
"""Independent source-safe, fail-closed audit of 26-PUB boundary experiment."""
from __future__ import annotations
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("sk1_1019_runner",HERE/"run.py")
assert spec and spec.loader
RUN=importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

SHA=re.compile(r"^[0-9a-f]{64}$")
MACHINE=re.compile(r"^[a-z_]{1,64}$")
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}
SUCCESS={"status","candidate_sha256","reader_semantic_reopen",
         "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
DIFF={"same_length","whole_pub_changed_raw_bytes","whole_pub_extra_bytes",
      "source_syid","result_syid","syid_delta",
      "syid_changed_header_bytes","quill_changed_bytes",
      "outside_header_quill_changed_bytes","non_quill_streams_checked",
      "non_quill_streams_changed","unchanged_story_syid_sequence",
      "unchanged_story_lengths","unchanged_text_payload",
      "unchanged_descriptors","changed_chunk_types","changed_chunk_count",
      "publisher_native_acceptance"}
RECORD={"source_sha256","source_bytes","source_type","status","reason",
        "source_syid_header","eligible_story_count","selected_story_count","stories"}
STORY={"story_ordinal","syid_id","original_story_utf16_units",
       "ascii_alnum_count","selected_slot_count","dedup_skipped","slots"}
SLOT={"slot","ascii_rank","utf16_offset","original_codepoint",
      "original_story_utf16_units","variants"}
VARIANT={"name","codepoint","direct_replace",
         "delete_then_insert","insert_then_delete","two_stage_sha_equal"}
FLOW={"first","second","final_sha256","final_diff","final_hypothesis"}

def nonneg(x,upper=12*1024*1024):
    assert type(x) is int and 0<=x<=upper,x

def step(s,may_not_attempt=False):
    assert isinstance(s,dict)
    if may_not_attempt and s=={"status":"NOT_ATTEMPTED"}:
        return False
    assert s.get("status") in STEPS,s
    if s["status"]=="HOSTED_PASS":
        assert set(s)==SUCCESS and SHA.fullmatch(s["candidate_sha256"])
        for k in SUCCESS-{"status","candidate_sha256"}:
            assert s[k] is True
        return True
    if s["status"]=="WRITER_BLOCKED":
        assert set(s)=={"status","writer_code"} and MACHINE.fullmatch(s["writer_code"])
    else:
        assert set(s)=={"status"}
    return False

def bytes_changed(x,y):
    return sum(a!=b for a,b in zip(x.to_bytes(2,"little"),y.to_bytes(2,"little")))

def header_delta(x):
    if x>=2**32-2:return None
    return sum(a!=b for a,b in zip(x.to_bytes(4,"little"),(x+2).to_bytes(4,"little")))

def diff(d,header,old,new):
    assert isinstance(d,dict) and set(d)==DIFF
    assert d["publisher_native_acceptance"]=="NOT_EVALUATED"
    for flag in ("same_length","unchanged_story_syid_sequence",
                 "unchanged_story_lengths","unchanged_text_payload",
                 "unchanged_descriptors"):
        assert type(d[flag]) is bool
    for num in ("whole_pub_changed_raw_bytes","whole_pub_extra_bytes",
                "source_syid","result_syid","syid_changed_header_bytes",
                "quill_changed_bytes","outside_header_quill_changed_bytes",
                "non_quill_streams_checked","non_quill_streams_changed",
                "changed_chunk_count"):
        nonneg(d[num],(2**32-1 if num in ("source_syid","result_syid") else 12*1024*1024))
    assert d["source_syid"]==header
    assert type(d["syid_delta"]) is int
    assert d["syid_delta"]==d["result_syid"]-d["source_syid"]
    assert d["quill_changed_bytes"]>=d["syid_changed_header_bytes"]
    assert type(d["changed_chunk_types"]) is dict
    assert all(isinstance(k,str) and re.fullmatch("[A-Z]{2,8}",k) and
               type(v) is int and 0<=v<=100 for k,v in d["changed_chunk_types"].items())
    assert sum(d["changed_chunk_types"].values())==d["changed_chunk_count"]
    if d["same_length"] and d["whole_pub_extra_bytes"]==0:
        assert d["whole_pub_changed_raw_bytes"]>=d["quill_changed_bytes"]
    h=header_delta(header)
    t=bytes_changed(old,new)
    return bool(h is not None and
        d["whole_pub_changed_raw_bytes"]==h+t and
        d["same_length"] and d["whole_pub_extra_bytes"]==0 and
        d["syid_delta"]==2 and d["syid_changed_header_bytes"]==h and
        d["outside_header_quill_changed_bytes"]==t and
        d["non_quill_streams_changed"]==0 and
        d["unchanged_story_syid_sequence"] and
        d["unchanged_story_lengths"] and
        d["unchanged_descriptors"] and
        not d["unchanged_text_payload"] and
        d["changed_chunk_types"].get("SYID")==1 and
        d["changed_chunk_types"].get("TEXT")==1 and
        d["changed_chunk_count"]==2)

def audit(folder):
    assert sorted(p.name for p in folder.iterdir())==["plan.json","records.json","report.json"]
    plan=json.loads((folder/"plan.json").read_text(encoding="utf-8"))
    records=json.loads((folder/"records.json").read_text(encoding="utf-8"))
    report=json.loads((folder/"report.json").read_text(encoding="utf-8"))
    assert set(plan)=={"schema","rar2_pin","science_reuse_commit",
        "science_reuse_blob","reference_t1007_pin","reference_t1007_zip_sha256",
        "source_manifest","source_sha256","source_bytes","source_count",
        "selected_stories_per_source","positions","codepoints","two_step_orders",
        "maximum_variant_cells","native_publisher_acceptance","raw_pub_output_authorized"}
    assert plan["schema"]=="sk1.quill-exp-pub-t-1019.plan.v1"
    assert plan["rar2_pin"]==RUN.PIN
    assert plan["science_reuse_commit"]==RUN.RESEARCH_SOURCE
    assert plan["science_reuse_blob"]==RUN.REFERENCE_BLOB
    assert plan["reference_t1007_pin"]==RUN.T1007_PIN
    assert plan["reference_t1007_zip_sha256"]==RUN.T1007_ZIP_SHA
    assert plan["source_manifest"]==RUN.source.MANIFEST_URL
    assert plan["source_count"]==26 and plan["selected_stories_per_source"]==2
    assert plan["positions"]==RUN.SLOTS and plan["codepoints"]==RUN.VARIANTS
    assert plan["two_step_orders"]==RUN.ORDERS and plan["maximum_variant_cells"]==416
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["raw_pub_output_authorized"] is False
    assert len(plan["source_sha256"])==len(plan["source_bytes"])==26
    assert all(SHA.fullmatch(x) for x in plan["source_sha256"])
    assert len(set(plan["source_sha256"]))==26
    assert set(RUN.BASELINE).issubset(set(plan["source_sha256"]))
    for n in plan["source_bytes"]:nonneg(n,12*1024*1024);assert n>0
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
                         "raw_pub_output_authorized","summary","records"}
    assert report["schema"]=="sk1.quill-exp-pub-t-1019.report.v1"
    assert report["rar2_pin"]==RUN.PIN
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["raw_pub_output_authorized"] is False
    assert report["records"]==records
    assert len(records)==26
    assert [x["source_sha256"] for x in records]==plan["source_sha256"]
    assert [x["source_bytes"] for x in records]==plan["source_bytes"]

    direct=0
    complete=0
    chosen_stories=0
    for row in records:
        assert set(row)==RECORD
        assert row["status"]==row["reason"]
        assert row["status"] in {"EVALUATED","NO_ELIGIBLE_STORY","SOURCE_EDITOR_OPEN_BLOCKED"}
        assert type(row["source_type"]) is str and len(row["source_type"])>0
        nonneg(row["source_syid_header"],2**32-1)
        nonneg(row["eligible_story_count"],100000)
        nonneg(row["selected_story_count"],2)
        assert row["selected_story_count"]==len(row["stories"])
        assert row["selected_story_count"]==min(2,row["eligible_story_count"])
        assert row["status"]=="EVALUATED" if row["stories"] else \
            row["status"] in {"NO_ELIGIBLE_STORY","SOURCE_EDITOR_OPEN_BLOCKED"}
        expected={i["source_syid_header"] for sha,i in RUN.BASELINE.items()
                  if sha==row["source_sha256"]}
        if expected:assert row["source_syid_header"]==expected.pop()
        syids=set()
        for i,story in enumerate(row["stories"]):
            chosen_stories+=1
            assert set(story)==STORY
            assert story["story_ordinal"]==i
            nonneg(story["syid_id"],2**32-1)
            assert story["syid_id"] not in syids;syids.add(story["syid_id"])
            nonneg(story["original_story_utf16_units"])
            assert story["original_story_utf16_units"]>0
            nonneg(story["ascii_alnum_count"])
            count=story["ascii_alnum_count"]
            assert count>0 and count<=story["original_story_utf16_units"]
            expected_ranks=[
                ("first",0),("second",min(1,count-1)),
                ("middle",(count-1)//2),("last",count-1)]
            unique=[]
            skipped=[]
            seen=set()
            for slot,rank in expected_ranks:
                if rank in seen:skipped.append(slot)
                else:unique.append((slot,rank));seen.add(rank)
            assert story["dedup_skipped"]==skipped
            assert story["selected_slot_count"]==len(story["slots"])==len(unique)
            for slot,(label,rank) in zip(story["slots"],unique):
                assert set(slot)==SLOT
                assert slot["slot"]==label and slot["ascii_rank"]==rank
                assert slot["original_story_utf16_units"]==story["original_story_utf16_units"]
                nonneg(slot["utf16_offset"])
                assert slot["utf16_offset"]<story["original_story_utf16_units"]
                nonneg(slot["original_codepoint"],127)
                assert chr(slot["original_codepoint"]).isascii() and \
                       chr(slot["original_codepoint"]).isalnum()
                assert len(slot["variants"])==2
                assert [v["name"] for v in slot["variants"]]==RUN.VARIANTS
                for v in slot["variants"]:
                    assert set(v)==VARIANT
                    nonneg(v["codepoint"],0xffff)
                    if v["name"]=="ASCII_UPPER":
                        assert chr(v["codepoint"]) in "XQZ"
                    else:
                        assert v["codepoint"]==0x416
                    assert v["codepoint"]!=slot["original_codepoint"]
                    assert not step(v["direct_replace"])
                    assert v["direct_replace"]=={"status":"WRITER_BLOCKED",
                        "writer_code":"quill_length_preserving_out_of_scope"}
                    direct+=1
                    got={}
                    for order in RUN.ORDERS:
                        flow=v[order]
                        assert set(flow)==FLOW
                        first=step(flow["first"])
                        second=step(flow["second"],may_not_attempt=True)
                        if not first:
                            assert flow["second"]=={"status":"NOT_ATTEMPTED"}
                        if second:
                            complete+=1
                            assert SHA.fullmatch(flow["final_sha256"])
                            assert flow["final_sha256"]==flow["second"]["candidate_sha256"]
                            model=diff(flow["final_diff"],row["source_syid_header"],
                                       slot["original_codepoint"],v["codepoint"])
                            assert type(flow["final_hypothesis"]) is bool
                            assert flow["final_hypothesis"] is model
                            got[order]=flow["final_sha256"]
                        else:
                            assert flow["final_sha256"] is None
                            assert flow["final_diff"] is None
                            assert flow["final_hypothesis"] is None
                            got[order]=None
                    a,b=got[RUN.ORDERS[0]],got[RUN.ORDERS[1]]
                    assert v["two_stage_sha_equal"]==((a==b) if a and b else None)
    summary=RUN.summarize(records)
    assert summary==report["summary"]
    assert summary["variant_cells"]==direct
    assert summary["source_count"]==26
    assert summary["selected_story_count"]==chosen_stories
    assert summary["completed_sequences"]==complete
    assert summary["two_stage_sequences"]==direct*2
    assert summary["baseline_t1007_all_pass"] is True
    # Meaningful larger-than-T1007 denominators, pre-registered before run.
    assert summary["variant_cells"]>=40
    assert summary["selected_story_count"]>=20
    assert sum(bool(r["stories"]) for r in records)>=13
    print("PUB-T-1019 AUDIT VALID: pinned 26 original PUB, 2 Story max, four rank slots, two glyphs, honest Writer outcomes.")
    print(json.dumps({k:summary[k] for k in (
        "source_count","selected_story_count","unique_slot_count","variant_cells",
        "two_stage_sequences","completed_sequences","both_orders_completed",
        "byte_equal_final_sha","baseline_t1007_all_pass","order_stats","by_slot",
        "first_writer_guard_codes","second_writer_guard_codes")},sort_keys=True))
    return summary

if __name__=="__main__":
    assert len(sys.argv)==2
    audit(Path(sys.argv[1]))
