#!/usr/bin/env python3
"""PUB-T-1007 fail-closed independent audit for source-safe three-file JSON."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("pub_t_982_runner",HERE/"run.py")
assert SPEC and SPEC.loader
RUN=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
SHA=re.compile(r"^[a-f0-9]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}
PASS_FIELDS={"status","candidate_sha256","reader_semantic_reopen",
             "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
DIFF_FIELDS={"same_length","whole_pub_changed_raw_bytes","whole_pub_extra_bytes",
            "source_syid","result_syid","syid_delta","syid_changed_header_bytes",
            "quill_changed_bytes","outside_header_quill_changed_bytes",
            "non_quill_streams_checked","non_quill_streams_changed",
            "unchanged_story_syid_sequence","unchanged_story_lengths",
            "unchanged_text_payload","unchanged_descriptors",
            "changed_chunk_types","changed_chunk_count","publisher_native_acceptance"}
RECORD_FIELDS={"source_sha256","source_type","source_bytes","status","reason",
               "original_codepoint","source_syid_header","slot","story_ordinal",
               "utf16_offset","baseline_insert","baseline_delete",
               "baseline_inverse_insert","baseline_inverse_delete","variants"}
VAR_FIELDS={"name","codepoint","original_utf16_units",
            "replacement_utf16_units","first","first_diff",
            "first_hypothesis","inverse","final_diff","final_hypothesis",
            "delete_then_insert","insert_then_delete","two_stage_sha_equal"}
EXPECTED_CP={"CYRILLIC_ZHE":0x416,"CJK_IDEOGRAPH":0x754c,"NBSP":0xa0}

def uint(n,upper=2**32):
    assert type(n) is int and 0<=n<=upper

def step(s):
    assert isinstance(s,dict) and s.get("status") in STEPS
    if s["status"]=="HOSTED_PASS":
        assert set(s)==PASS_FIELDS and SHA.fullmatch(s["candidate_sha256"])
        for key in PASS_FIELDS-{"status","candidate_sha256"}:
            assert s[key] is True
    elif s["status"]=="WRITER_BLOCKED":
        assert set(s)=={"status","writer_code"} and CODE.fullmatch(s["writer_code"])
    else:
        assert set(s)=={"status"}

def diff(d,header):
    assert isinstance(d,dict) and set(d)==DIFF_FIELDS
    assert d["publisher_native_acceptance"]=="NOT_EVALUATED"
    for field in ("same_length","unchanged_story_syid_sequence",
                  "unchanged_story_lengths","unchanged_text_payload",
                  "unchanged_descriptors"):
        assert type(d[field]) is bool
    for field in ("whole_pub_changed_raw_bytes","whole_pub_extra_bytes",
                  "source_syid","result_syid","syid_changed_header_bytes",
                  "quill_changed_bytes","outside_header_quill_changed_bytes",
                  "non_quill_streams_checked","non_quill_streams_changed",
                  "changed_chunk_count"):
        uint(d[field],12*1024*1024 if field not in ("source_syid","result_syid") else 2**32-1)
    assert type(d["syid_delta"]) is int
    assert d["syid_delta"]==d["result_syid"]-d["source_syid"]
    assert d["source_syid"]==header
    assert isinstance(d["changed_chunk_types"],dict)
    assert all(isinstance(k,str) and re.fullmatch("[A-Z]{2,8}",k) and
               type(v) is int and 0<=v<=100 for k,v in d["changed_chunk_types"].items())
    assert sum(d["changed_chunk_types"].values())==d["changed_chunk_count"]
    assert d["quill_changed_bytes"]>=d["syid_changed_header_bytes"]
    assert d["outside_header_quill_changed_bytes"]>=0
    if d["same_length"] and not d["whole_pub_extra_bytes"]:
        assert d["whole_pub_changed_raw_bytes"]>=d["quill_changed_bytes"]
    return d

def count_bytes(a,b):
    return sum(x!=y for x,y in zip(a.to_bytes(2,"little"),b.to_bytes(2,"little")))

def header_bytes(a,n):
    if a+n>2**32-1:return None
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),(a+n).to_bytes(4,"little")))

def first_model(d,header,old,glyph):
    h=header_bytes(header,1)
    txt=count_bytes(old,glyph)
    return bool(h is not None and d["whole_pub_changed_raw_bytes"]==h+txt and
       d["same_length"] and d["whole_pub_extra_bytes"]==0 and d["syid_delta"]==1 and
       d["syid_changed_header_bytes"]==h and
       d["outside_header_quill_changed_bytes"]==txt and
       d["non_quill_streams_changed"]==0 and
       d["unchanged_story_syid_sequence"] and d["unchanged_story_lengths"] and
       d["unchanged_descriptors"] and not d["unchanged_text_payload"] and
       d["changed_chunk_types"].get("SYID")==1 and
       d["changed_chunk_types"].get("TEXT")==1 and d["changed_chunk_count"]==2)

def final_model(d,header):
    h=header_bytes(header,2)
    return bool(h is not None and d["whole_pub_changed_raw_bytes"]==h and
       d["same_length"] and d["whole_pub_extra_bytes"]==0 and
       d["syid_delta"]==2 and d["syid_changed_header_bytes"]==h and
       d["outside_header_quill_changed_bytes"]==0 and
       d["non_quill_streams_changed"]==0 and
       d["unchanged_story_syid_sequence"] and d["unchanged_story_lengths"] and
       d["unchanged_descriptors"] and d["unchanged_text_payload"] and
       d["changed_chunk_types"].get("SYID")==1 and d["changed_chunk_count"]==1)

def audit(path):
    plan=json.loads((path/"plan.json").read_text(encoding="utf-8"))
    assert set(plan)=={"schema","rar2_pin","scientific_reuse_commit",
                      "scientific_reuse_rust_blob","source_manifest","source_sha256",
                      "source_syid_header","source_count","eligible_story_ordinal",
                      "source_slot","offset_utf16","replacement_names",
                      "replacement_variants_per_source","native_publisher_acceptance",
                      "raw_pub_output_authorized"}
    assert plan["schema"]=="sk1.quill-exp-pub-t-1007.plan.v1"
    assert plan["rar2_pin"]==RUN.PIN
    assert plan["scientific_reuse_commit"]==RUN.RESEARCH_SOURCE
    assert plan["scientific_reuse_rust_blob"]==RUN.REFERENCE_BLOB
    assert plan["source_manifest"]==RUN.source.MANIFEST_URL
    assert plan["source_sha256"]==list(RUN.SOURCES)
    assert plan["source_syid_header"]==RUN.SOURCES
    assert plan["source_count"]==3 and plan["eligible_story_ordinal"]==0
    assert plan["source_slot"]=="second" and plan["offset_utf16"]==1
    assert plan["replacement_names"]==RUN.VARIANTS
    assert plan["replacement_variants_per_source"]==4
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["raw_pub_output_authorized"] is False

    rows=json.loads((path/"records.json").read_text(encoding="utf-8"))
    r=json.loads((path/"report.json").read_text(encoding="utf-8"))
    assert set(r)=={"schema","rar2_pin","native_publisher_acceptance",
                   "raw_pub_output_authorized","summary","records"}
    assert r["schema"]=="sk1.quill-exp-pub-t-1007.report.v1"
    assert r["rar2_pin"]==RUN.PIN and r["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert r["raw_pub_output_authorized"] is False
    assert r["records"]==rows
    assert len(rows)==3 and [x["source_sha256"] for x in rows]==list(RUN.SOURCES)
    for row in rows:
        assert set(row)==RECORD_FIELDS
        assert SHA.fullmatch(row["source_sha256"])
        assert row["source_type"]=="github"
        uint(row["source_bytes"],12*1024*1024)
        assert row["reason"]=="EVALUATED" and row["status"]=="EVALUATED"
        assert row["source_syid_header"]==RUN.SOURCES[row["source_sha256"]]
        uint(row["original_codepoint"],127)
        assert chr(row["original_codepoint"]).isascii() and chr(row["original_codepoint"]).isalnum()
        assert row["story_ordinal"]==0 and row["slot"]=="second" and row["utf16_offset"]==1
        for key in ("baseline_insert","baseline_delete",
                    "baseline_inverse_insert","baseline_inverse_delete"):
            step(row[key])
            assert row[key]["status"]=="HOSTED_PASS"
        assert len(row["variants"])==4
        assert [v["name"] for v in row["variants"]]==RUN.VARIANTS
        for v in row["variants"]:
            assert set(v)==VAR_FIELDS
            assert v["replacement_utf16_units"]==v["original_utf16_units"]
            uint(v["original_utf16_units"],12*1024*1024)
            uint(v["codepoint"],0xffff)
            if v["name"]=="ASCII_UPPER":
                assert chr(v["codepoint"]) in "XQZ"
            else:
                assert v["codepoint"]==EXPECTED_CP[v["name"]]
            assert v["codepoint"]!=row["original_codepoint"]
            step(v["first"])
            if v["first"]["status"]=="HOSTED_PASS":
                f=diff(v["first_diff"],row["source_syid_header"])
                assert type(v["first_hypothesis"]) is bool
                assert v["first_hypothesis"]==first_model(
                    f,row["source_syid_header"],row["original_codepoint"],v["codepoint"])
                step(v["inverse"])
                if v["inverse"]["status"]=="HOSTED_PASS":
                    fin=diff(v["final_diff"],row["source_syid_header"])
                    assert type(v["final_hypothesis"]) is bool
                    assert v["final_hypothesis"]==final_model(fin,row["source_syid_header"])
                else:
                    assert v["final_diff"] is None and v["final_hypothesis"] is None
            else:
                assert v["first_diff"] is None and v["first_hypothesis"] is None
                assert v["inverse"]=={"status":"NOT_ATTEMPTED"}
                assert v["final_diff"] is None and v["final_hypothesis"] is None
    
    completed=0
    for row in rows:
        for v in row["variants"]:
            # The old single-operation guard must NOT be changed or bypassed.
            assert v["first"]=={"status":"WRITER_BLOCKED",
                                "writer_code":"quill_length_preserving_out_of_scope"}
            finals={}
            for order in ("delete_then_insert","insert_then_delete"):
                flow=v[order]
                assert isinstance(flow,dict) and set(flow)=={
                    "first","second","final_sha256","final_diff","final_hypothesis"}
                step(flow["first"])
                if flow["first"]["status"]=="HOSTED_PASS":
                    step(flow["second"])
                else:
                    assert flow["second"]=={"status":"NOT_ATTEMPTED"}
                if flow["second"]["status"]=="HOSTED_PASS":
                    completed+=1
                    assert SHA.fullmatch(flow["final_sha256"])
                    assert flow["final_sha256"]==flow["second"]["candidate_sha256"]
                    d=diff(flow["final_diff"],row["source_syid_header"])
                    assert type(flow["final_hypothesis"]) is bool
                    h=header_bytes(row["source_syid_header"],2)
                    delta=count_bytes(row["original_codepoint"],v["codepoint"])
                    predicted=bool(h is not None and
                        d["whole_pub_changed_raw_bytes"]==h+delta and
                        d["same_length"] and d["whole_pub_extra_bytes"]==0 and
                        d["syid_delta"]==2 and d["syid_changed_header_bytes"]==h and
                        d["outside_header_quill_changed_bytes"]==delta and
                        d["non_quill_streams_changed"]==0 and
                        d["unchanged_story_syid_sequence"] and
                        d["unchanged_story_lengths"] and
                        d["unchanged_descriptors"] and
                        not d["unchanged_text_payload"] and
                        d["changed_chunk_types"].get("SYID")==1 and
                        d["changed_chunk_types"].get("TEXT")==1 and
                        d["changed_chunk_count"]==2)
                    assert flow["final_hypothesis"] is predicted
                    finals[order]=flow["final_sha256"]
                else:
                    assert flow["final_sha256"] is None
                    assert flow["final_diff"] is None
                    assert flow["final_hypothesis"] is None
                    finals[order]=None
            left=finals["delete_then_insert"]
            right=finals["insert_then_delete"]
            assert v["two_stage_sha_equal"]==((left==right) if left and right else None)
    assert r["summary"]==RUN.two_stage_summary(rows)
    assert r["summary"]["two_stage_completed"]==completed
    assert r["summary"]["variant_attempts"]==12
    assert set(r["summary"]["by_variant"])==set(RUN.VARIANTS)
    assert r["summary"]["two_stage_first_outcomes"]
    assert r["summary"]["two_stage_second_outcomes"]
    print("PUB-T-1007 VALID: three source SHA, 24 preregistered replacements, genuine Writer stage/byte receipts")
    print(json.dumps(r["summary"],sort_keys=True))
    return r

if __name__=="__main__":
    assert len(sys.argv)==2
    audit(Path(sys.argv[1]))
