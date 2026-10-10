#!/usr/bin/env python3
"""Independent source-safe receipt gate for PUB-T-962. No byte payload is permitted."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import re
import sys

SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
HOSTS={"www.mathematicshed.com":10,"www.anyssa.org":4,
       "storage.googleapis.com":4,"law.duke.edu":3,
       "www.greville.surrey.sch.uk":2,"cdn.instructables.com":2,
       "www.bnssports.us":2}
LADDER=[1<<i for i in range(14)]
STATUS={"NOT_EVALUATED","SHA_VERIFIED","NO_BASELINE_PASS","BRACKET_MEASURED",
        "CENSORED_PASS","ANOMALY","INCOMPLETE","PROBE_UNAVAILABLE"}
ARM_STATUS={"PROBE_UNAVAILABLE","HOSTED_PASS","WRITER_BLOCKED",
        "SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY","CANONICAL_EDIT_REJECTED",
        "INVALID_CANDIDATE_HASH","REOPEN_FAILED","TARGET_SEMANTIC_MISMATCH",
        "SYID_OR_SIBLING_MISMATCH","REPLAY_OPEN_FAILED","REPLAY_APPLY_FAILED",
        "REPLAY_WRITE_FAILED","REPLAY_BYTES_MISMATCH"}
REASONS={"NOT_STARTED","HTTP_UNAVAILABLE","REQUEST_TIMEOUT","FETCH_ERROR",
         "UNSAFE_REDIRECT","SHA_OR_SIZE_DRIFT","NON_CFB_INPUT","OK",
         "PROCESS_OR_TIMEOUT","PROCESS_FAILED","BAD_RECEIPT_OR_CFB",
         "CAP_8192","OBSERVED_GUARD","INVARIANT_OR_MONOTONICITY",
         "PROBE_UNAVAILABLE"}|ARM_STATUS
CFB_BOOL={"quill_logical_changed","sector_count_equal","fat_table_equal",
          "minifat_table_equal","directory_sector_ids_equal","root_chain_equal"}
CFB_NUM={"cfb_size_before","cfb_size_after","quill_stream_size_before",
         "quill_stream_size_after","nonquill_stream_changes"}
SUM_KEYS={"attempted_sources","sha_verified_sources","with_baseline_pass",
          "status_counts","source_reason_counts","per_host_statuses",
          "arm_attempts","hosted_pass_arms","writer_guard_arms","guard_codes",
          "pass_with_nonquill_change","pass_with_pub_length_change",
          "pass_with_quill_length_change","pass_with_cfb_chain_change",
          "measured_brackets","censored_pass_sources","anomaly_sources"}
REC_KEYS={"source_sha256","host","source_bytes","status","reason","arms",
          "bracket","censored_at","nonmonotone_detected"}
ARM_KEYS={"growth_utf16","status","reason","phase"}
ARM_CONTEXT={"story_ordinal","offset_utf16","before_utf16","after_utf16"}

def check(path:Path):
    filenames={p.name for p in path.iterdir()}
    assert filenames=={"plan.json","records.json","report.json"},filenames
    p=json.loads((path/"plan.json").read_text())
    records=json.loads((path/"records.json").read_text())
    report=json.loads((path/"report.json").read_text())
    assert set(p)=={"schema","rar2_pin","lalamu_pin","source_manifest",
        "excluded_source_manifest","preselected_sha256","host_quotas",
        "planned_source_bytes","growth_ladder","max_growth_utf16",
        "scope","native_publisher_acceptance"}
    assert p["schema"]=="sk1.pub-t-962.plan.v1"
    assert p["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert p["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert p["host_quotas"]==HOSTS
    assert type(p["planned_source_bytes"]) is int and 0<p["planned_source_bytes"]<=50*1024*1024
    assert p["growth_ladder"]==LADDER and p["max_growth_utf16"]==8192
    assert p["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert p["source_manifest"]==(
        "https://raw.githubusercontent.com/Lalalalendia/lalamu/"
        "f78cc6f455f4dc222868f9cc035511a6ca7a91ea/pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json")
    assert p["excluded_source_manifest"]==(
        "https://raw.githubusercontent.com/Lalalalendia/rar2/"
        "703808408fd919e564a90cdc236e81db3c04af8b/tools/corpus/receipts/"
        "lalamu-materialized-35-input-2026-09-29.json")
    assert p["scope"]==("independent insert N ASCII into one deterministic Story; "
                         "real public PUB growth envelope, not CFB reallocator")
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
        "product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-962.report.v1"
    assert report["rar2_pin"]==p["rar2_pin"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==records
    assert len(records)==27 and len(p["preselected_sha256"])==27
    assert [r["source_sha256"] for r in records]==p["preselected_sha256"]
    assert len(set(p["preselected_sha256"]))==27
    assert all(SHA.fullmatch(x) for x in p["preselected_sha256"])
    hosts=Counter();status=Counter();reasons=Counter()
    arm_count=pass_count=guard_count=0
    guard_codes=Counter()
    nonq=file_size=quill_size=chains=0
    for r in records:
        assert set(r)==REC_KEYS and r["status"] in STATUS and r["reason"] in REASONS
        assert r["host"] in HOSTS and type(r["source_bytes"]) is int
        assert 0<r["source_bytes"]<=2_500_000
        assert type(r["nonmonotone_detected"]) is bool
        assert isinstance(r["arms"],list) and len(r["arms"])<=50
        hosts[r["host"]]+=1;status[r["status"]]+=1;reasons[r["reason"]]+=1
        assert isinstance(r["bracket"],dict) or r["bracket"] is None
        if r["bracket"] is not None:
            assert set(r["bracket"])=={"last_tested_pass","first_tested_fail"}
            a,b=r["bracket"].values()
            assert type(a) is int and 0<=a<=8192
            assert b is None or (type(b) is int and 1<=b<=8192)
        assert r["censored_at"] is None or r["censored_at"]==8192
        if r["status"]=="NOT_EVALUATED":assert not r["arms"]
        first_shape=None
        for a in r["arms"]:
            assert isinstance(a,dict) and ARM_KEYS.issubset(a)
            assert a["status"] in ARM_STATUS and a["reason"] in REASONS
            assert type(a["growth_utf16"]) is int and 1<=a["growth_utf16"]<=8192
            assert a["phase"] in ("ladder","refine","after_failure_control")
            expected=set(ARM_KEYS)
            if a["status"]=="WRITER_BLOCKED":
                expected.add("writer_code")
                assert isinstance(a["writer_code"],str) and CODE.fullmatch(a["writer_code"])
                guard_codes[a["writer_code"]]+=1;guard_count+=1
            if "story_ordinal" in a:
                expected|=ARM_CONTEXT
                assert all(type(a[k]) is int and 0<=a[k]<1_000_000 for k in ARM_CONTEXT)
                assert a["after_utf16"]==a["before_utf16"]+a["growth_utf16"]
                shape=(a["story_ordinal"],a["offset_utf16"],a["before_utf16"])
                if first_shape is None:first_shape=shape
                elif first_shape!=shape:
                    assert r["status"]=="ANOMALY"
            if a["status"]=="HOSTED_PASS":
                assert a["reason"]=="OK"
                expected|={"candidate_sha256","cfb"}
                assert SHA.fullmatch(a["candidate_sha256"])
                z=a["cfb"]
                assert set(z)==CFB_BOOL|CFB_NUM
                for k in CFB_BOOL:assert type(z[k]) is bool,k
                for k in CFB_NUM:assert type(z[k]) is int and 0<=z[k]<1_000_000_000,k
                assert z["cfb_size_before"]==r["source_bytes"]
                pass_count+=1
                nonq+=int(z["nonquill_stream_changes"]!=0)
                file_size+=int(z["cfb_size_before"]!=z["cfb_size_after"])
                quill_size+=int(z["quill_stream_size_before"]!=z["quill_stream_size_after"])
                chains+=int(not all(z[k] for k in CFB_BOOL-{"quill_logical_changed"}))
            assert set(a)==expected, a["status"]
            arm_count+=1
        if r["status"] in ("BRACKET_MEASURED","CENSORED_PASS"):
            assert r["arms"] and r["arms"][0]["status"]=="HOSTED_PASS"
    assert hosts==Counter(HOSTS)
    assert sum(r["source_bytes"] for r in records)==p["planned_source_bytes"]
    s=report["summary"];assert set(s)==SUM_KEYS
    expected_ints={"attempted_sources":len(records),
      "sha_verified_sources":sum(r["status"]!="NOT_EVALUATED" for r in records),
      "with_baseline_pass":sum(bool(r["arms"]) and r["arms"][0]["status"]=="HOSTED_PASS" for r in records),
      "arm_attempts":arm_count,"hosted_pass_arms":pass_count,"writer_guard_arms":guard_count,
      "pass_with_nonquill_change":nonq,"pass_with_pub_length_change":file_size,
      "pass_with_quill_length_change":quill_size,
      "pass_with_cfb_chain_change":chains,
      "measured_brackets":status["BRACKET_MEASURED"],
      "censored_pass_sources":status["CENSORED_PASS"],
      "anomaly_sources":status["ANOMALY"]}
    for k,v in expected_ints.items():
        assert type(s[k]) is int and s[k]==v,(k,s.get(k),v)
    assert s["status_counts"]==dict(sorted(status.items()))
    assert s["source_reason_counts"]==dict(sorted(reasons.items()))
    assert s["per_host_statuses"]=={k:dict(sorted(Counter(
        r["status"] for r in records if r["host"]==k).items())) for k in sorted(HOSTS)}
    assert s["guard_codes"]==dict(sorted(guard_codes.items()))
    # Fixed structural schema above disallows raw source/candidate bytes,
    # Story texts, local paths, URLs, and arbitrary error messages.
    print("PUB-T-962 SOURCE-SAFE RECEIPT PASS",s["with_baseline_pass"],"/",s["attempted_sources"],
        "brackets",s["measured_brackets"],"censored",s["censored_pass_sources"])
    return True

if __name__=="__main__":
    check(Path(sys.argv[1]))
