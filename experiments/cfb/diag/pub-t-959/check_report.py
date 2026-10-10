#!/usr/bin/env python3
"""Fail-closed sanitizer and denominator verifier for PUB-T-959 Actions artifacts."""
from __future__ import annotations
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import sys

SHA=re.compile(r"^[0-9a-f]{64}$")
CATEGORY=re.compile(r"^(?:header|header_area|directory_[a-z_]+|(?:fat|difat|minifat)_sector|directory_sector|root_ministream_container|unallocated_sector|allocated_other_sector|stream_payload|stream_slack|unclassified)(?:->(?:header|header_area|directory_[a-z_]+|(?:fat|difat|minifat)_sector|directory_sector|root_ministream_container|unallocated_sector|allocated_other_sector|stream_payload|stream_slack|unclassified))?$")
ALL_STATUSES={"NOT_EVALUATED","SHA_VERIFIED","PROBE_UNAVAILABLE",
"WRITER_NOT_ADMITTED","PHYSICAL_NOT_EVALUATED","MEASURED"}
NEGATIVE={"HTTP_UNAVAILABLE","REQUEST_TIMEOUT","FETCH_ERROR","UNSAFE_REDIRECT",
"SHA_OR_SIZE_DRIFT","NON_CFB_INPUT","NOT_STARTED","BINARY_OR_TIMEOUT",
"EXECUTION_FAILED","PARSER_OR_RECEIPT_MISMATCH","WRITER_BLOCKED",
"SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY","CANONICAL_EDIT_REJECTED",
"HASH_OR_NO_CHANGE","REOPEN_FAILED","TARGET_SEMANTIC_MISMATCH",
"SYID_OR_SIBLING_MISMATCH","REPLAY_OPEN_FAILED","REPLAY_APPLY_FAILED",
"REPLAY_WRITE_FAILED","REPLAY_BYTES_MISMATCH","UNCLASSIFIED_PROBE_OUTCOME","OK"}
PHYSICAL_KEYS={
"source_bytes","candidate_bytes","source_sector_size","candidate_sector_size",
"source_sector_count","candidate_sector_count","source_directory_count",
"candidate_directory_count","same_sid_type_count","source_fat_sector_count",
"candidate_fat_sector_count","source_minifat_sector_count",
"candidate_minifat_sector_count","source_root_chain_sector_count",
"candidate_root_chain_sector_count","fat_table_changed_entries_same_index",
"minifat_table_changed_entries_same_index","fat_sector_ids_equal",
"difat_sector_ids_equal","directory_sector_ids_equal","root_chain_equal",
"logical_stream_count_before","logical_stream_count_after","logical_streams_added",
"logical_streams_removed","logical_streams_changed",
"logical_non_quill_streams_changed","logical_quill_changed",
"raw_overlap_changed_byte_count","raw_bytes_added_after_overlap",
"raw_bytes_removed_after_overlap","raw_absolute_offset_categories",
"raw_unclassified_absolute_byte_count","physical_interpretation"}
BOOL_KEYS={"fat_sector_ids_equal","difat_sector_ids_equal",
"directory_sector_ids_equal","root_chain_equal","logical_quill_changed"}
SUMMARY_KEYS={"attempted","source_verified","measured","status_counts",
"per_host_statuses","measured_with_non_quill_stream_changes",
"measured_with_quill_stream_change","raw_absolute_offset_category_totals",
"raw_unclassified_absolute_byte_total"}
HOST_SIZES={
 "www.mathematicshed.com":10,"www.anyssa.org":4,
 "storage.googleapis.com":4,"law.duke.edu":3,
 "www.greville.surrey.sch.uk":2,"cdn.instructables.com":2,
 "www.bnssports.us":2}

def check_physical(p,source_bytes):
    assert isinstance(p,dict) and set(p)==PHYSICAL_KEYS
    assert p["physical_interpretation"]=="ABSOLUTE_OFFSETS_ONLY_NOT_RELOCATION_NORMALIZED"
    for k in PHYSICAL_KEYS-BOOL_KEYS-{"physical_interpretation","raw_absolute_offset_categories"}:
        assert type(p[k]) is int and 0<=p[k]<=1_000_000_000,k
    for k in BOOL_KEYS:assert type(p[k]) is bool,k
    assert p["source_bytes"]==source_bytes and p["source_bytes"]>0
    assert p["candidate_bytes"]>0
    assert p["source_sector_size"] in (512,4096)
    assert p["candidate_sector_size"] in (512,4096)
    assert p["logical_stream_count_before"]>0 and p["logical_stream_count_after"]>0
    assert p["logical_non_quill_streams_changed"]<=p["logical_streams_changed"]
    assert p["logical_streams_changed"]<=min(
        p["logical_stream_count_before"],p["logical_stream_count_after"])
    assert p["raw_bytes_added_after_overlap"]==max(0,p["candidate_bytes"]-p["source_bytes"])
    assert p["raw_bytes_removed_after_overlap"]==max(0,p["source_bytes"]-p["candidate_bytes"])
    classes=p["raw_absolute_offset_categories"]
    assert isinstance(classes,dict) and len(classes)<1000
    assert all(CATEGORY.fullmatch(k) and type(v) is int and 0<v<1_000_000_000
        for k,v in classes.items())
    assert sum(classes.values())==p["raw_overlap_changed_byte_count"]
    assert sum(v for k,v in classes.items() if "unclassified" in k)==p["raw_unclassified_absolute_byte_count"]

def verify(folder:Path):
    plan=json.loads((folder/"plan.json").read_text())
    records=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    assert set(plan)=={"schema","rar2_pin","lalamu_pin","source_manifest",
      "prior_35_source_manifest","host_quotas","preselected_sha256",
      "source_budget_bytes","scope","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-959.plan.v1"
    assert plan["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["host_quotas"]==HOST_SIZES
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["source_budget_bytes"]<=50*1024*1024
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
        "product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-959.report.v1"
    assert report["rar2_pin"]==plan["rar2_pin"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==records
    assert isinstance(records,list) and len(records)==sum(HOST_SIZES.values())==27
    selected=plan["preselected_sha256"]
    assert selected==[r["source_sha256"] for r in records]
    assert len(set(selected))==27 and all(isinstance(x,str) and SHA.fullmatch(x) for x in selected)
    status=Counter();hosts=defaultdict(Counter);class_counts=Counter()
    source_verified=0;other=0;quill=0;unc=0
    for r in records:
        assert isinstance(r,dict) and {"source_sha256","source_bytes","host",
             "status","reason"}.issubset(r)
        assert r["host"] in HOST_SIZES
        assert type(r["source_bytes"]) is int and 0<r["source_bytes"]<=2_500_000
        assert r["status"] in ALL_STATUSES and r["reason"] in NEGATIVE
        status[r["status"]]+=1;hosts[r["host"]][r["status"]]+=1
        if r["status"]!="NOT_EVALUATED":source_verified+=1
        expected={"source_sha256","source_bytes","host","status","reason"}
        if r["status"]=="MEASURED":
            expected|={"physical","candidate_sha256","offset_utf16"}
            assert r["reason"]=="OK"
            assert SHA.fullmatch(r["candidate_sha256"])
            assert type(r["offset_utf16"]) is int and 0<=r["offset_utf16"]<10**8
            check_physical(r["physical"],r["source_bytes"])
            p=r["physical"];class_counts.update(p["raw_absolute_offset_categories"])
            other+=int(p["logical_non_quill_streams_changed"]>0)
            quill+=int(p["logical_quill_changed"])
            unc+=p["raw_unclassified_absolute_byte_count"]
        if r["reason"]=="WRITER_BLOCKED":
            expected.add("writer_code")
            assert re.fullmatch(r"[a-z_]{1,64}",r["writer_code"])
        assert set(r)==expected, r["status"]
    assert all(sum(hosts[h].values())==n for h,n in HOST_SIZES.items())
    s=report["summary"]
    assert isinstance(s,dict) and set(s)==SUMMARY_KEYS
    assert s["attempted"]==27 and s["measured"]==status["MEASURED"]
    assert s["source_verified"]==source_verified
    assert s["status_counts"]==dict(sorted(status.items()))
    assert s["per_host_statuses"]=={k:dict(sorted(v.items())) for k,v in sorted(hosts.items())}
    assert s["measured_with_non_quill_stream_changes"]==other
    assert s["measured_with_quill_stream_change"]==quill
    assert s["raw_absolute_offset_category_totals"]==dict(sorted(class_counts.items()))
    assert s["raw_unclassified_absolute_byte_total"]==unc
    # Recursive key whitelist and source SHA validate the sanitized public shape.
    # No PUB, text, raw stream names, source URL or transient local path is present.
    for p in folder.iterdir():
        assert p.name in {"plan.json","records.json","report.json"}
        assert p.suffix==".json"
    print("PUB-T-959 source-safe receipt PASS:",s["measured"],"/",s["attempted"])
    return True

if __name__=="__main__":
    verify(Path(sys.argv[1]))
