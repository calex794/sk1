#!/usr/bin/env python3
"""PUB-T-984 independent safe-receipt, pinned-cohort, per-arm and summary gate.
Scientific hypothesis may be false: count it as a counterexample, not failed CI.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[a-f0-9]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
REASON=re.compile(r"^[A-Z_]{2,64}$")
HOST=re.compile(r"^[a-z0-9.-]{1,200}$")
SOURCE_KEYS={"source_sha256","host","expected_source_bytes","status","reason","probe"}
PROBE_BASE={"schema","source_sha256","source_bytes","result",
            "publisher_native_acceptance","product_pub_download_authorized","stories"}
PROBE_HEADER={"source_syid_first_dword","source_syid_count","source_syid_max_live_id","eligible_story_count"}
STORY_KEYS={"story_ordinal","story_utf16_length","ascii_total","pairs"}
PAIR_KEYS={"slot","ascii_rank","ascii_total","offset_utf16","story_utf16_length",
           "ambiguous_reverse_delete_insert_offset","single_insert","single_delete",
           "both_single_pass","insert_then_delete","delete_then_insert",
           "insert_delete_returns_original_bytes","delete_insert_returns_original_bytes",
           "both_final_byte_equal","insert_delete_cfb","delete_insert_cfb",
           "insert_delete_raw","delete_insert_raw"}
RAW_KEYS={"source_file_length","final_file_length","equal_length",
          "changed_same_offset_bytes","extra_bytes","whole_file_equal"}

def load_old(ref:Path):
    p=ref/"experiments/cfb/val/pub-t-963/check_report.py"
    spec=importlib.util.spec_from_file_location("pinned_pub963_raw_checker",p)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def check_uint(v,maximum=2**32-1):
    assert type(v) is int and 0<=v<=maximum

def bytes_changed(a,b):
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),b.to_bytes(4,"little")))

def check_raw(d):
    assert isinstance(d,dict) and set(d)==RAW_KEYS
    for k in ("source_file_length","final_file_length","changed_same_offset_bytes","extra_bytes"):
        check_uint(d[k],12*1024*1024)
    assert type(d["equal_length"]) is bool
    assert type(d["whole_file_equal"]) is bool
    assert d["equal_length"]==(d["source_file_length"]==d["final_file_length"])
    assert d["extra_bytes"]==abs(d["source_file_length"]-d["final_file_length"])
    assert d["changed_same_offset_bytes"]<=min(d["source_file_length"],d["final_file_length"])
    assert d["whole_file_equal"]==(d["equal_length"] and d["changed_same_offset_bytes"]==0)

def check(path:Path,ref:Path):
    assert {x.name for x in path.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((path/"plan.json").read_text(encoding="utf-8"))
    assert set(plan)=={"schema","rar2_pin","source_selector_pin","physical_inverse_pin",
        "reference_t971_original_zip_sha256","source_sha_list_lf_digest","source_count",
        "host_count","source_size_sum","source_sha256","max_stories_per_pub","story_order",
        "offset_policy","inverse_orders","native_publisher_acceptance","raw_pub_output_authorized"}
    assert plan["schema"]=="sk1.cfb-val-pub-t-984.plan.v1"
    assert plan["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert plan["source_selector_pin"]=="69989902bfdc87fac1aeb57ccb6a1f78872831fd"
    assert plan["physical_inverse_pin"]=="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
    assert plan["reference_t971_original_zip_sha256"]=="055c1ec20ebfcbe17c2aad04bba5d11d942c159686ec49f43430463b7eee31bf"
    assert plan["source_sha_list_lf_digest"]=="b9a0559613179f31e6ee9e0d75210cce523e4dafabfba6a3d2d660f086c0d8e2"
    assert len(plan["source_sha256"])==47 and len(set(plan["source_sha256"]))==47
    assert all(isinstance(x,str) and SHA.fullmatch(x) for x in plan["source_sha256"])
    assert hashlib.sha256(("\n".join(plan["source_sha256"])+"\n").encode()).hexdigest()==plan["source_sha_list_lf_digest"]
    assert (plan["source_count"],plan["host_count"],plan["source_size_sum"])==(47,37,28191744)
    assert plan["max_stories_per_pub"]==3
    assert plan["story_order"]=="Quill source descriptor ordinal"
    assert plan["offset_policy"]=="second ASCII alphanumeric UTF16 offset"
    assert plan["inverse_orders"]==["insert_then_delete","delete_then_insert"]
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["raw_pub_output_authorized"] is False

    report=json.loads((path/"report.json").read_text(encoding="utf-8"))
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
                         "raw_pub_output_authorized","summary","records"}
    assert report["schema"]=="sk1.cfb-val-pub-t-984.report.v1"
    assert report["rar2_pin"]==plan["rar2_pin"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["raw_pub_output_authorized"] is False
    records=json.loads((path/"records.json").read_text(encoding="utf-8"))
    assert records==report["records"] and len(records)==47
    assert [x["source_sha256"] for x in records]==plan["source_sha256"]
    assert len({r["host"] for r in records})==37
    assert sum(r["expected_source_bytes"] for r in records)==28191744

    legacy=load_old(ref)
    source_status=Counter()
    probe_status=Counter()
    first_status=Counter()
    inverse_status=Counter()
    raw_classes=Counter()
    failures=[]
    heard=[]
    head_rel=Counter()
    complete_sources=set()
    stories=pairs=both=finals=matched=0
    for source in records:
        assert isinstance(source,dict) and set(source)==SOURCE_KEYS
        assert SHA.fullmatch(source["source_sha256"]) and HOST.fullmatch(source["host"])
        assert source["status"] in {"NOT_EVALUATED","SHA_VERIFIED","PROBE_UNAVAILABLE"}
        assert REASON.fullmatch(source["reason"])
        check_uint(source["expected_source_bytes"],12*1024*1024)
        source_status[source["status"]]+=1
        p=source["probe"]
        if p is None:
            continue
        assert source["status"]=="SHA_VERIFIED" and source["reason"]=="OK"
        assert set(p)==PROBE_BASE or set(p)==PROBE_BASE|PROBE_HEADER
        assert p["schema"]=="sk1.cfb-diag-pub-t-984.inverse.v1"
        assert p["source_sha256"]==source["source_sha256"]
        assert p["source_bytes"]==source["expected_source_bytes"]
        assert p["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert p["product_pub_download_authorized"] is False
        assert p["result"] in {"EVALUATED","NO_PLAIN_EDITABLE_STORY",
                               "SOURCE_EDITOR_OPEN_BLOCKED","SOURCE_QUILL_PARSE_BLOCKED"}
        probe_status[p["result"]]+=1
        assert isinstance(p["stories"],list)
        if p["result"] in {"EVALUATED","NO_PLAIN_EDITABLE_STORY"}:
            assert set(p)==PROBE_BASE|PROBE_HEADER
            hd=p["source_syid_first_dword"];mx=p["source_syid_max_live_id"]
            check_uint(hd);check_uint(p["source_syid_count"])
            assert mx is None or (type(mx) is int and 0<=mx<=2**32-1)
            check_uint(p["eligible_story_count"],3)
            assert len(p["stories"])==p["eligible_story_count"]
            if p["result"]=="EVALUATED":assert 1<=len(p["stories"])<=3
            else:assert p["eligible_story_count"]==0
            heard.append(hd)
            if mx is not None:
                head_rel["source_header_gt_max_live_syid"]+=int(hd>mx)
                head_rel["source_header_eq_max_live_syid"]+=int(hd==mx)
                head_rel["source_header_lt_max_live_syid"]+=int(hd<mx)
        else:
            assert set(p)==PROBE_BASE and len(p["stories"])==0
            continue
        for ordinal,st in enumerate(p["stories"]):
            assert isinstance(st,dict) and set(st)==STORY_KEYS
            assert st["story_ordinal"]==ordinal and st["ascii_total"]>=2
            check_uint(st["story_utf16_length"],12*1024*1024)
            assert isinstance(st["pairs"],list) and len(st["pairs"])==1
            stories+=1
            for pair in st["pairs"]:
                pairs+=1
                assert set(pair)==PAIR_KEYS
                assert pair["slot"]=="second" and pair["ascii_rank"]==1
                assert pair["ascii_total"]==st["ascii_total"]
                assert pair["story_utf16_length"]==st["story_utf16_length"]
                check_uint(pair["offset_utf16"],12*1024*1024)
                assert pair["offset_utf16"]<st["story_utf16_length"]
                assert type(pair["ambiguous_reverse_delete_insert_offset"]) is bool
                for label,name in (("single_insert","_INSERT"),("single_delete","_DELETE")):
                    legacy.check_step(pair[label])
                    first_status[pair[label]["status"]+name]+=1
                both_ok=pair["single_insert"]["status"]==pair["single_delete"]["status"]=="HOSTED_PASS"
                assert pair["both_single_pass"] is both_ok
                if not both_ok:
                    for arm in ("insert_then_delete","delete_then_insert"):
                        assert pair[arm]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
                    for nullkey in ("insert_delete_cfb","delete_insert_cfb",
                                    "insert_delete_raw","delete_insert_raw",
                                    "insert_delete_returns_original_bytes",
                                    "delete_insert_returns_original_bytes","both_final_byte_equal"):
                        assert pair[nullkey] is None
                    continue
                both+=1
                for arm,key in (("insert_then_delete","insert_delete"),
                                ("delete_then_insert","delete_insert")):
                    step=pair[arm]
                    legacy.check_step(step)
                    inverse_status[step["status"]]+=1
                    cfb=pair[key+"_cfb"]
                    raw=pair[key+"_raw"]
                    flag=pair[key+"_returns_original_bytes"]
                    if step["status"]!="HOSTED_PASS":
                        assert cfb is None and raw is None and flag is None
                        continue
                    finals+=1;complete_sources.add(source["source_sha256"])
                    check_raw(raw)
                    assert isinstance(cfb,dict)
                    d=cfb.copy()
                    assert d["schema"]=="sk1.cfb-diag-pub-t-984.diff.v1"
                    d["schema"]="sk1.cfb-diag-pub-t-963.diff.v1"
                    legacy.check_diff(d)
                    assert type(flag) is bool and flag==raw["whole_file_equal"]
                    assert raw["source_file_length"]==source["expected_source_bytes"]
                    assert raw["final_file_length"]==cfb["final_file_bytes"]
                    assert raw["source_file_length"]==cfb["source_file_bytes"]
                    check_uint(cfb["source_syid_first_dword"])
                    check_uint(cfb["final_syid_first_dword"])
                    assert hd==cfb["source_syid_first_dword"]
                    expected=hd+2 if hd<=0xfffffffd else None
                    n=bytes_changed(hd,expected) if expected is not None else None
                    match=(expected is not None and
                         cfb["final_syid_first_dword"]==expected and
                         cfb["syid_first_dword_delta"]==2 and
                         raw["equal_length"] and raw["extra_bytes"]==0 and
                         raw["changed_same_offset_bytes"]==n and
                         cfb["syid_first_dword_changed_bytes"]==n and
                         cfb["quill_differing_byte_positions_equal_len"]==n and
                         cfb["quill_changed_bytes_outside_syid_first_dword"]==0 and
                         cfb["same_quill_TEXT_payload_bytes"] is True and
                         cfb["same_quill_story_syid_sequence"] is True and
                         cfb["same_quill_story_utf16_lengths"] is True and
                         cfb["matched_descriptor_sequence"] is True and
                         cfb["non_quill_streams_changed"]==0 and
                         cfb["missing_cfb_paths"]==0 and
                         cfb["added_cfb_paths"]==0 and
                         cfb["cfb_entry_type_changes"]==0)
                    raw_classes["actual_raw_"+str(raw["changed_same_offset_bytes"])]+=1
                    if match: matched+=1
                    else:
                        failures.append({
                            "source_sha256":source["source_sha256"],
                            "story_ordinal":st["story_ordinal"],
                            "offset_utf16":pair["offset_utf16"],
                            "arm":arm,
                            "expected_raw_bytes":n,
                            "observed_raw_bytes":raw["changed_same_offset_bytes"],
                            "observed_syid_delta":cfb["syid_first_dword_delta"],
                            "outside_syid":cfb["quill_changed_bytes_outside_syid_first_dword"],
                            "non_quill_changed":cfb["non_quill_streams_changed"]})
                if (pair["insert_then_delete"]["status"]=="HOSTED_PASS" and
                    pair["delete_then_insert"]["status"]=="HOSTED_PASS"):
                    assert type(pair["both_final_byte_equal"]) is bool
                else:
                    assert pair["both_final_byte_equal"] is None
    expected_summary={
        "source_plan_total":47,
        "source_status":dict(sorted(source_status.items())),
        "probe_status":dict(sorted(probe_status.items())),
        "verified_source_SHA":source_status["SHA_VERIFIED"],
        "source_syid_header_observations":len(heard),
        "natural_syid_header_min":min(heard) if heard else None,
        "natural_syid_header_max":max(heard) if heard else None,
        "natural_syid_low_byte_ge_fe":sum((x&255)>=254 for x in heard),
        "natural_syid_header_vs_live_max":dict(sorted(head_rel.items())),
        "story_probes":stories,
        "original_fixed_second_ascii_pairs":pairs,
        "initial_writer_status":dict(sorted(first_status.items())),
        "initial_both_pass":both,
        "inverse_writer_status":dict(sorted(inverse_status.items())),
        "inverse_final_files":finals,
        "inverse_final_distinct_SHA":len(complete_sources),
        "inverse_matched_all_physical_bytes_except_syid":matched,
        "inverse_raw_byte_counts":dict(sorted(raw_classes.items())),
        "physical_counterexamples":failures,
        "native_publisher_acceptance":"NOT_EVALUATED"
    }
    assert report["summary"]==expected_summary, "independent summary mismatch"
    print("PUB-T-984 independently verified source-safe 47-input matrix:",json.dumps({
        "sha_verified":source_status["SHA_VERIFIED"],"real_header_census":len(heard),
        "original_pair_trials":pairs,"inverse_final_files":finals,
        "inverse_distinct_sha":len(complete_sources),
        "full_pub_syid_only":matched,"counterexamples":len(failures)},
        sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==3,"usage: check_report.py RESULTS_DIR REF_T963_DIR"
    check(Path(sys.argv[1]),Path(sys.argv[2]))
