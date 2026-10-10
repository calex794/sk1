#!/usr/bin/env python3
"""PUB-T-965 independent source-safe JSON validator. Fail closed on unknown keys."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import json
import re
import sys

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("sk1_965_runner",HERE/"run.py")
assert SPEC and SPEC.loader
RUN=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
SHA=re.compile(r"^[a-f0-9]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
SOURCE_FIELDS={"source_sha256","source_type","source_bytes","status","reason",
    "baseline","original_syid_first_dword","story_ordinal","slot","offset_utf16","variants"}
VARIANT_FIELDS={"variant_header","patch","status","synthetic_sha256",
                "semantic_source_reopen","insert_delete","delete_insert"}
PATCH_FIELDS={"source_header","patched_header","changed_raw_bytes",
              "expected_changed_header_bytes","equal_length","extra_bytes","exact_header_only"}
ARM_FIELDS={"first","first_header","second","final"}
FINAL_FIELDS={"initial_header","final_header","delta","predicted_final_header",
              "predicted_changed_header_bytes","whole_pub_equal_length",
              "whole_pub_raw_changed_bytes","whole_pub_extra_bytes","quill_changed_bytes",
              "syid_first_dword_changed_bytes","quill_changed_bytes_outside_syid_first_dword",
              "non_quill_streams_changed","same_quill_TEXT_payload_bytes",
              "same_quill_story_syid_sequence","matched_descriptor_sequence",
              "predicted_raw_exact_match","publisher_native_acceptance"}
PASS_FIELDS={"status","candidate_sha256","reader_semantic_reopen",
             "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}
VARIANT_STATES={"MEASURED","SYNTHETIC_PATCH_NOT_EXACT",
 "ORIGINAL_EDITOR_OPEN_BLOCKED","SYNTHETIC_EDITOR_OPEN_BLOCKED",
 "SYNTHETIC_STORY_OR_SYID_MISMATCH","VARIANT_PROBE_ERROR"}
SOURCES=set(RUN.SOURCE_COUNTERS)
VALUES=RUN.VALUES

def number(n,minimum=0,maximum=2**32):
    assert type(n) is int and minimum<=n<=maximum,repr(n)

def check_step(s):
    assert isinstance(s,dict) and s.get("status") in STEPS
    if s["status"]=="HOSTED_PASS":
        assert set(s)==PASS_FIELDS
        assert SHA.fullmatch(s["candidate_sha256"])
        for name in PASS_FIELDS-{"status","candidate_sha256"}:
            assert s[name] is True
    elif s["status"]=="WRITER_BLOCKED":
        assert set(s)=={"status","writer_code"} and CODE.fullmatch(s["writer_code"])
    else:
        assert set(s)=={"status"}

def check_final(f,value):
    assert isinstance(f,dict) and set(f)==FINAL_FIELDS
    assert f["publisher_native_acceptance"]=="NOT_EVALUATED"
    expected=value+2 if value+2<=0xffffffff else None
    assert f["predicted_final_header"]==expected
    expected_bytes=(sum(a!=b for a,b in zip(value.to_bytes(4,"little"),
                       expected.to_bytes(4,"little"))) if expected is not None else None)
    assert f["predicted_changed_header_bytes"]==expected_bytes
    number(f["initial_header"],0,0xffffffff)
    number(f["final_header"],0,0xffffffff)
    assert f["initial_header"]==value
    assert type(f["delta"]) is int and f["delta"]==f["final_header"]-value
    for k in ("whole_pub_raw_changed_bytes","whole_pub_extra_bytes",
              "quill_changed_bytes","syid_first_dword_changed_bytes",
              "quill_changed_bytes_outside_syid_first_dword",
              "non_quill_streams_changed"):
        number(f[k],0,12*1024*1024)
    for k in ("whole_pub_equal_length","same_quill_TEXT_payload_bytes",
              "same_quill_story_syid_sequence","matched_descriptor_sequence",
              "predicted_raw_exact_match"):
        assert type(f[k]) is bool
    correct=(expected is not None and f["final_header"]==expected and
             f["whole_pub_equal_length"] and f["whole_pub_extra_bytes"]==0 and
             f["whole_pub_raw_changed_bytes"]==expected_bytes and
             f["delta"]==2 and
             f["syid_first_dword_changed_bytes"]==f["whole_pub_raw_changed_bytes"] and
             f["quill_changed_bytes_outside_syid_first_dword"]==0 and
             f["non_quill_streams_changed"]==0 and
             f["same_quill_TEXT_payload_bytes"] and
             f["same_quill_story_syid_sequence"] and f["matched_descriptor_sequence"])
    assert f["predicted_raw_exact_match"] is correct

def check_arm(arm,value,baseline=False):
    assert isinstance(arm,dict) and set(arm)==ARM_FIELDS
    check_step(arm["first"])
    fstatus=arm["first"]["status"]
    sstatus=arm["second"]["status"]
    if fstatus=="HOSTED_PASS":
        number(arm["first_header"],0,0xffffffff)
        assert isinstance(arm["second"],dict)
        check_step(arm["second"])
        if value<0xffffffff:
            assert arm["first_header"]==value+1
        if sstatus=="HOSTED_PASS":
            check_final(arm["final"],value)
        else:
            assert arm["final"] is None
    else:
        assert arm["first_header"] is None
        assert arm["second"]=={"status":"NOT_ATTEMPTED"}
        assert arm["final"] is None

def check(path):
    p=json.loads((path/"plan.json").read_text(encoding="utf-8"))
    assert set(p)=={"schema","rar2_pin","source_manifest","source_sha256",
       "original_source_counters","slot","story_ordinal","offset_utf16","synthetic_headers",
       "synthetic_variants_per_real_source","real_source_count","inverse_arms",
       "predecessor_963_zip_sha256","native_publisher_acceptance","raw_pub_output_authorized"}
    assert p["schema"]=="sk1.cfb-exp-pub-t-965.plan.v1"
    assert p["rar2_pin"]==RUN.PIN
    assert p["source_sha256"]==list(RUN.SOURCE_COUNTERS)
    assert p["original_source_counters"]==RUN.SOURCE_COUNTERS
    assert p["synthetic_headers"]==VALUES
    assert p["real_source_count"]==3 and p["synthetic_variants_per_real_source"]==9
    assert (p["slot"],p["story_ordinal"],p["offset_utf16"])==("second",0,1)
    assert p["inverse_arms"]==["insert_delete","delete_insert"]
    assert p["predecessor_963_zip_sha256"]=="70aed39805d587b1f4cb32bb96ec8e615c6e4f22b7909438ed1d8685c976b3dc"
    assert p["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert p["raw_pub_output_authorized"] is False

    report=json.loads((path/"report.json").read_text(encoding="utf-8"))
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
                         "raw_pub_output_authorized","summary","records"}
    assert report["schema"]=="sk1.cfb-exp-pub-t-965.report.v1"
    assert report["rar2_pin"]==RUN.PIN and report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["raw_pub_output_authorized"] is False
    records=report["records"]
    assert records==json.loads((path/"records.json").read_text(encoding="utf-8"))
    assert len(records)==3 and {r["source_sha256"] for r in records}==SOURCES
    assert [r["source_sha256"] for r in records]==list(RUN.SOURCE_COUNTERS)
    for row in records:
        assert set(row)==SOURCE_FIELDS
        assert SHA.fullmatch(row["source_sha256"])
        assert row["source_type"]=="github"
        number(row["source_bytes"],1,12*1024*1024)
        assert row["reason"]=="EVALUATED" and row["status"]=="EVALUATED"
        assert row["original_syid_first_dword"]==RUN.SOURCE_COUNTERS[row["source_sha256"]]
        assert (row["story_ordinal"],row["slot"],row["offset_utf16"])==(0,"second",1)
        baseline=row["baseline"]
        assert isinstance(baseline,dict)
        assert set(baseline)=={"insert_delete","delete_insert","both_pass"}
        check_arm(baseline["insert_delete"],row["original_syid_first_dword"],True)
        check_arm(baseline["delete_insert"],row["original_syid_first_dword"],True)
        assert baseline["both_pass"] is True
        assert baseline["insert_delete"]["second"]["status"]=="HOSTED_PASS"
        assert baseline["delete_insert"]["second"]["status"]=="HOSTED_PASS"
        assert len(row["variants"])==9
        assert [v["variant_header"] for v in row["variants"]]==VALUES
        for v in row["variants"]:
            assert isinstance(v,dict)
            assert v["status"] in VARIANT_STATES
            if v["status"]=="VARIANT_PROBE_ERROR":
                assert set(v)=={"variant_header","status"}
                continue
            assert set(v)==VARIANT_FIELDS
            assert SHA.fullmatch(v["synthetic_sha256"])
            assert set(v["patch"])==PATCH_FIELDS
            patch=v["patch"]
            assert type(patch["exact_header_only"]) is bool
            assert type(patch["equal_length"]) is bool
            for k in ("source_header","patched_header","changed_raw_bytes",
                      "expected_changed_header_bytes","extra_bytes"):
                number(patch[k],0,12*1024*1024 if k not in ("source_header","patched_header") else 0xffffffff)
            assert patch["source_header"]==row["original_syid_first_dword"]
            assert patch["patched_header"]==v["variant_header"]
            exp=sum(a!=b for a,b in zip(patch["source_header"].to_bytes(4,"little"),
                                          patch["patched_header"].to_bytes(4,"little")))
            assert patch["expected_changed_header_bytes"]==exp
            assert patch["exact_header_only"]==(
                patch["equal_length"] and patch["extra_bytes"]==0
                and patch["changed_raw_bytes"]==exp)
            if v["status"]=="MEASURED":
                assert patch["exact_header_only"] is True
                assert v["semantic_source_reopen"] is True
                for arm_name in ("insert_delete","delete_insert"):
                    check_arm(v[arm_name],v["variant_header"])
            else:
                assert v["insert_delete"] is None and v["delete_insert"] is None
    assert report["summary"]==RUN.summarize(records)
    by_value=report["summary"]["per_value"]
    assert set(by_value)=={f"0x{v:08x}" for v in VALUES
                          if any(x["status"]=="MEASURED" and x["variant_header"]==v
                                 for rec in records for x in rec["variants"])}
    print("PUB-T-965 checked: 3 SHA, 27 synthetic planned, signed outcomes & source-safe schema")
    print(json.dumps(report["summary"],sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
