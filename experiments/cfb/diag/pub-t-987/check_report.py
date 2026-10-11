#!/usr/bin/env python3
"""PUB-T-987 independent admission, safe JSON, and physical inverse audit.

Do not require a positive FE/FF witness: zero in a completely verified 625-SHA
population is a valid bounded negative scientific result, not an excuse to
switch inputs.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[a-f0-9]{64}$")
STATES={"NATURAL_SYID_PARSED","QUILL_STREAM_UNAVAILABLE",
        "QUILL_SYID_PARSE_BLOCKED","NOT_CFB"}
WRITER_STATUS={"SOURCE_SHA_DRIFT","WRITER_PROCESS_UNAVAILABLE",
               "WRITER_PROCESS_FAILED","WRITER_RECEIPT_UNREADABLE",
               "WRITER_RECEIPT_INVALID","WRITER_SOURCE_SYID_DRIFT","RECEIPT_AVAILABLE"}
KEYS={"source_sha256","source_bytes","status","syid_header","syid_count",
    "syid_max_live","low_byte","is_fe_ff_boundary","original_bytes_immutable","writer"}
PROBE_BASE={"schema","source_sha256","source_bytes","result",
   "publisher_native_acceptance","product_pub_download_authorized","stories"}
PROBE_HEADER={"source_syid_first_dword","source_syid_count",
    "source_syid_max_live_id","eligible_story_count"}
STORY={"story_ordinal","story_utf16_length","ascii_total","pairs"}
PAIR={"slot","ascii_rank","ascii_total","offset_utf16","story_utf16_length",
      "ambiguous_reverse_delete_insert_offset","single_insert","single_delete",
      "both_single_pass","insert_then_delete","delete_then_insert",
      "insert_delete_returns_original_bytes","delete_insert_returns_original_bytes",
      "both_final_byte_equal","insert_delete_cfb","delete_insert_cfb",
      "insert_delete_raw","delete_insert_raw"}
RAW={"source_file_length","final_file_length","equal_length",
      "changed_same_offset_bytes","extra_bytes","whole_file_equal"}

def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def check_uint(value,max_value=0xffffffff):
    assert type(value) is int and 0<=value<=max_value

def diff_bytes(a:int,b:int)->int:
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),b.to_bytes(4,"little")))

def sha_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def check_pair(st,legacy,header):
    assert isinstance(st,dict) and set(st)==PAIR
    assert st["slot"]=="second" and st["ascii_rank"]==1
    assert type(st["ascii_total"]) is int and st["ascii_total"]>=2
    check_uint(st["offset_utf16"],2**31)
    check_uint(st["story_utf16_length"],2**31)
    assert st["offset_utf16"]<st["story_utf16_length"]
    assert type(st["ambiguous_reverse_delete_insert_offset"]) is bool
    for k in ("single_insert","single_delete"):
        legacy.check_step(st[k])
    both=st["single_insert"]["status"]==st["single_delete"]["status"]=="HOSTED_PASS"
    assert st["both_single_pass"] is both
    if not both:
        for k in ("insert_then_delete","delete_then_insert"):
            assert st[k]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
        for k in ("insert_delete_cfb","delete_insert_cfb","insert_delete_raw",
                  "delete_insert_raw","insert_delete_returns_original_bytes",
                  "delete_insert_returns_original_bytes","both_final_byte_equal"):
            assert st[k] is None
        return
    final_both=[]
    for arm,key in (("insert_then_delete","insert_delete"),
                    ("delete_then_insert","delete_insert")):
        receipt=st[arm]
        legacy.check_step(receipt)
        cfb=st[key+"_cfb"]
        raw=st[key+"_raw"]
        equal=st[key+"_returns_original_bytes"]
        if receipt["status"]!="HOSTED_PASS":
            assert cfb is None and raw is None and equal is None
            continue
        final_both.append(arm)
        assert isinstance(raw,dict) and set(raw)==RAW
        for k in ("source_file_length","final_file_length",
                  "changed_same_offset_bytes","extra_bytes"):
            check_uint(raw[k],128*1024*1024)
        assert raw["source_file_length"]>0 and raw["final_file_length"]>0
        assert type(raw["equal_length"]) is bool
        assert type(raw["whole_file_equal"]) is bool
        assert raw["equal_length"]==(raw["source_file_length"]==raw["final_file_length"])
        assert raw["extra_bytes"]==abs(raw["source_file_length"]-raw["final_file_length"])
        assert raw["changed_same_offset_bytes"]<=min(raw["source_file_length"],raw["final_file_length"])
        assert raw["whole_file_equal"]==(raw["equal_length"] and raw["changed_same_offset_bytes"]==0)
        assert type(equal) is bool and equal==raw["whole_file_equal"]
        assert isinstance(cfb,dict) and cfb["schema"]=="sk1.cfb-diag-pub-t-984.diff.v1"
        copy=cfb.copy()
        copy["schema"]="sk1.cfb-diag-pub-t-963.diff.v1"
        legacy.check_diff(copy)
        assert cfb["source_file_bytes"]==raw["source_file_length"]
        assert cfb["final_file_bytes"]==raw["final_file_length"]
        assert cfb["source_syid_first_dword"]==header
        # Do not force the physical hypothesis to be true: evidence can falsify it.
        expected=header+2 if header<=0xfffffffd else None
        if expected is not None:
            check_uint(expected)
            changed_prediction=diff_bytes(header,expected)
            assert 1<=changed_prediction<=4
    if len(final_both)==2:
        assert type(st["both_final_byte_equal"]) is bool
    else:
        assert st["both_final_byte_equal"] is None

def check(path:Path,donor:Path,ref:Path):
    assert {x.name for x in path.iterdir()}=={"plan.json","records.json","report.json"}
    p=json.loads((path/"plan.json").read_text(encoding="utf-8"))
    assert set(p)=={"schema","corpus_repo","corpus_commit","corpus_native_tree",
       "corpus_exact_sha_count","original_sha_list_lf_sha256","reader_writer_pin",
       "inverse_writer_science_pin","inverse_writer_parent_t963","inverse_writer_parent_t971",
       "natural_target_low_bytes","writer_policy",
       "previous_1050_matched_mature_cohort_note","native_publisher_acceptance",
       "raw_original_or_candidate_pub_export"}
    run=load_module(HERE/"run.py","sk1_pub987_runner")
    legacy=load_module(ref/"experiments/cfb/val/pub-t-963/check_report.py","sk1_pub963_original_check")
    assert p["schema"]=="sk1.cfb-diag-pub-t-987.plan.v1"
    assert p["corpus_repo"]=="Lalalalendia/lalamu"
    assert p["corpus_commit"]==run.DONOR_PIN and p["corpus_native_tree"]==run.DONOR_TREE
    assert p["corpus_exact_sha_count"]==run.EXPECTED==625
    assert p["reader_writer_pin"]==run.RAR2_PIN
    assert p["inverse_writer_science_pin"]==run.T984_PIN
    assert p["inverse_writer_parent_t963"]==run.T963_PIN
    assert p["inverse_writer_parent_t971"]==run.T971_PIN
    assert p["natural_target_low_bytes"]==[254,255]
    assert p["writer_policy"]=="all natural parsed FE/FF, no post-hoc selection"
    assert p["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert p["raw_original_or_candidate_pub_export"] is False
    assert SHA.fullmatch(p["original_sha_list_lf_sha256"])

    # Independently reopen EVERY pinned source file and verify its original bytes.
    donor=donor.resolve(strict=True)
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=donor,text=True).strip()==run.DONOR_PIN
    assert subprocess.check_output([
       "git","rev-parse","HEAD:pub-corpus/corpus/native/unclassified"],
       cwd=donor,text=True).strip()==run.DONOR_TREE
    native=donor/"pub-corpus/corpus/native/unclassified"
    original_files=sorted(native.iterdir())
    assert len(original_files)==625 and all(x.is_file() and x.suffix==".pub" for x in original_files)

    report=json.loads((path/"report.json").read_text(encoding="utf-8"))
    assert set(report)=={"schema","plan_sha256","source_pub_count",
                       "summary","records","native_publisher_acceptance",
                       "raw_original_or_candidate_pub_export"}
    assert report["schema"]=="sk1.cfb-diag-pub-t-987.report.v1"
    assert report["source_pub_count"]==625
    assert report["plan_sha256"]==sha_file(path/"plan.json")
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["raw_original_or_candidate_pub_export"] is False
    records=json.loads((path/"records.json").read_text(encoding="utf-8"))
    assert records==report["records"] and len(records)==625
    assert [x.name for x in original_files]==[x["source_sha256"]+".pub" for x in records]
    shas=[x["source_sha256"] for x in records]
    assert len(set(shas))==625 and all(SHA.fullmatch(x) for x in shas)
    assert hashlib.sha256(("\n".join(shas)+"\n").encode()).hexdigest()==p["original_sha_list_lf_sha256"]

    for file,row in zip(original_files,records):
        assert set(row)==KEYS
        assert row["source_sha256"]==file.stem
        assert sha_file(file)==row["source_sha256"],"materialized donor SHA mismatch"
        assert row["source_bytes"]==file.stat().st_size
        assert row["status"] in STATES
        assert row["original_bytes_immutable"] is True
        parsed=row["status"]=="NATURAL_SYID_PARSED"
        if parsed:
            h=row["syid_header"]
            check_uint(h);check_uint(row["syid_count"])
            assert row["syid_max_live"] is None or (
                type(row["syid_max_live"]) is int and 0<=row["syid_max_live"]<=0xffffffff)
            assert row["low_byte"]==h&255 and type(row["low_byte"]) is int
            assert row["is_fe_ff_boundary"] is (row["low_byte"] in (0xfe,0xff))
        else:
            assert all(row[k] is None for k in ("syid_header","syid_count",
                                               "syid_max_live","low_byte"))
            assert row["is_fe_ff_boundary"] is False
        if not row["is_fe_ff_boundary"]:
            assert row["writer"] is None
            continue
        w=row["writer"]
        assert isinstance(w,dict) and set(w)=={"status","probe"}
        assert w["status"] in {
            "SOURCE_SHA_DRIFT","WRITER_PROCESS_UNAVAILABLE","WRITER_PROCESS_FAILED",
            "WRITER_RECEIPT_UNREADABLE","WRITER_RECEIPT_INVALID",
            "WRITER_SOURCE_SYID_DRIFT","RECEIPT_AVAILABLE"}
        if w["status"]!="RECEIPT_AVAILABLE":
            assert w["probe"] is None;continue
        proof=w["probe"]
        assert isinstance(proof,dict)
        assert proof["schema"]==run.WRITER_SCHEMA
        assert proof["source_sha256"]==row["source_sha256"]
        assert proof["source_bytes"]==row["source_bytes"]
        assert proof["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert proof["product_pub_download_authorized"] is False
        assert proof["result"] in {"SOURCE_EDITOR_OPEN_BLOCKED","SOURCE_QUILL_PARSE_BLOCKED",
                                  "NO_PLAIN_EDITABLE_STORY","EVALUATED"}
        if proof["result"]=="SOURCE_EDITOR_OPEN_BLOCKED":
            assert set(proof)==PROBE_BASE or set(proof)==PROBE_BASE|{"eligible_story_count"}
            assert proof["stories"]==[]
            continue
        assert set(proof)==PROBE_BASE|PROBE_HEADER
        assert proof["source_syid_first_dword"]==row["syid_header"]
        assert proof["source_syid_count"]==row["syid_count"]
        assert proof["source_syid_max_live_id"]==row["syid_max_live"]
        check_uint(proof["eligible_story_count"],3)
        assert len(proof["stories"])==proof["eligible_story_count"]
        assert len(proof["stories"])>0 if proof["result"]=="EVALUATED" else len(proof["stories"])==0
        for ordinal,st in enumerate(proof["stories"]):
            assert isinstance(st,dict) and set(st)==STORY
            assert st["story_ordinal"]==ordinal
            assert type(st["ascii_total"]) is int and st["ascii_total"]>=2
            assert isinstance(st["pairs"],list) and len(st["pairs"])==1
            check_pair(st["pairs"][0],legacy,row["syid_header"])
    assert report["summary"]==run.summarize(records)
    summary=report["summary"]
    assert summary["natural_fe_ff_count"]==sum(r["is_fe_ff_boundary"] for r in records)
    assert summary["original_syid_headers_observed"]==sum(r["status"]=="NATURAL_SYID_PARSED" for r in records)
    assert summary["source_sha_verified"]==625
    assert summary["inverse_final_exact_syid_model"]<=summary["inverse_final_files"]
    print("PUB-T-987 validated pinned natural 625 original SHA/Census and all inherited real Writer receipts:")
    print(json.dumps({
       "natural_parsed_syid":summary["original_syid_headers_observed"],
       "natural_low_FE_FF":summary["natural_fe_ff_count"],
       "finals":summary["inverse_final_files"],
       "matched_syid_model":summary["inverse_final_exact_syid_model"],
       "counterexamples":len(summary["counterexamples"])},sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==4
    check(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
