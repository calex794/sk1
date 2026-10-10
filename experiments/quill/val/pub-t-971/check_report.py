#!/usr/bin/env python3
"""Fail-closed independent validator of source-safe PUB-T-971 receipts."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import re
import sys

SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
HOST=re.compile(r"^[a-z0-9.-]{2,150}$")
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
PLAN={"schema","rar2_pin","lalamu_pin","manifest_url",
      "original_35_excluded","exp005_62_excluded","t968_27_excluded",
      "t969_27_excluded","t970_27_excluded","source_count","source_bytes",
      "host_count","source_sha256","max_stories_per_source",
      "insertion_position","max_static_growth_utf16","doses_policy",
      "native_publisher_acceptance"}
PROOF={"schema","source_sha256","source_bytes","status",
       "static_predictions_built_before_writer",
       "publisher_native_acceptance","product_pub_download_authorized",
       "stories","writer_arm_count","source_immutable"}
STORY={"story_ordinal","syid","story_utf16_length","insert_at_utf16",
       "source_tokn_hit","source_fd_hit","static_class",
       "predicted_max_pass_utf16","predicted_first_growth_guard","arms"}
ARM={"dose_utf16","source_growth_class","predicted_first_class","writer"}
REPORT={"attempted_source_sha","sha_verified","source_status_counts",
        "source_reason_counts","evaluated_sources","evaluated_story_count",
        "story_class_counts","writer_arms","pass_arms","blocked_arms",
        "nonstandard_arms","machine_guard_codes","first_threshold_guard_codes",
        "first_class_matrix","first_class_mismatch_witnesses",
        "threshold_story_count","threshold_full_matches",
        "threshold_source_count","threshold_matching_distinct_sources",
        "threshold_min_pass","threshold_max_pass","threshold_details",
        "right_censored_at_8192","zero_positive_capacity"}
SOURCE_STATES={"EVALUATED","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY",
    "QUILL_READ_BLOCKED","QUILL_PARSE_BLOCKED","FD_STRUCTURE_BLOCKED",
    "STORY_ID_AMBIGUOUS","STATIC_PROBE_BLOCKED"}
WRITER_OTHER={"SOURCE_REOPEN_FAILED","TARGET_ID_UNAVAILABLE",
    "STORY_ID_MISMATCH","CANONICAL_EDIT_REJECTED","INVALID_CANDIDATE",
    "READER_REOPEN_FAILED","OUTPUT_ID_UNAVAILABLE","TARGET_SEMANTIC_MISMATCH",
    "SYID_OR_SIBLING_MISMATCH","PROJECT_SOURCE_OPEN_FAILED",
    "PROJECT_APPLY_FAILED","PROJECT_WRITER_FAILED","PROJECT_BYTE_MISMATCH"}
SOURCE_REASONS={"NOT_STARTED","HTTP_UNAVAILABLE","REQUEST_TIMEOUT",
 "FETCH_ERROR","UNSAFE_REDIRECT","SHA_OR_SIZE_DRIFT","NON_CFB_INPUT",
 "OK","PROCESS_OR_TIMEOUT","PROCESS_FAILED","INVALID_RECEIPT"}
GR={"PASS","GROWTH_DESCRIPTOR","GROWTH_UNKNOWN","CAPACITY"}
CLASSES=GR|{"TOKN","FD"}
MACHINE={"quill_token_layer":"TOKN","quill_insertion_at_fd_boundary":"FD",
         "quill_growth_would_discard_unknown":"GROWTH_UNKNOWN",
         "quill_growth_would_discard_descriptor":"GROWTH_DESCRIPTOR",
         "quill_insufficient_capacity":"CAPACITY"}

def actual(w):
    if w["status"]=="HOSTED_PASS":return "PASS"
    if w["status"]=="WRITER_BLOCKED":return MACHINE.get(w["code"],"OTHER_GUARD")
    return "OTHER_STATUS"

def validate(root:Path)->dict:
    assert {p.name for p in root.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((root/"plan.json").read_text(encoding="utf-8"))
    records=json.loads((root/"records.json").read_text(encoding="utf-8"))
    report=json.loads((root/"report.json").read_text(encoding="utf-8"))
    assert isinstance(plan,dict) and set(plan)==PLAN
    assert plan["schema"]=="sk1.pub-t-971.plan.v1"
    assert plan["rar2_pin"]==PIN
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["manifest_url"]=="https://raw.githubusercontent.com/Lalalalendia/lalamu/f78cc6f455f4dc222868f9cc035511a6ca7a91ea/pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json"
    assert all(plan[x]==value for x,value in (
        ("original_35_excluded",35),("exp005_62_excluded",62),
        ("t968_27_excluded",27),("t969_27_excluded",27),
        ("t970_27_excluded",27),("source_count",47),
        ("source_bytes",28191744),("host_count",37),
        ("max_stories_per_source",3),("max_static_growth_utf16",8192)))
    assert plan["insertion_position"]=="second_ascii_alnum"
    assert plan["doses_policy"]=="TOKN/FD +1; growth +1,N,N+1,N+2 sorted dedup, N=0 +1/+2; N=8192 +1/8192"
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(records,list) and len(records)==47
    assert len(plan["source_sha256"])==47 and len(set(plan["source_sha256"]))==47
    assert all(isinstance(s,str) and SHA.fullmatch(s) for s in plan["source_sha256"])
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
                         "product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-971.report.v1" and report["rar2_pin"]==PIN
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==records

    hosts=set();source_counts=Counter();reason_counts=Counter();story_counts=Counter()
    matrix=Counter();codes=Counter();first_codes=Counter()
    verified=total_story=total_writer=passes=blocked=nonstandard=0
    threshold_details=[];mismatch=[];successful_sources=set();seen_threshold_sources=set()
    evaluated_sources=set();censored=zero=0
    for row,sha in zip(records,plan["source_sha256"]):
        assert isinstance(row,dict) and set(row)=={
         "source_sha256","host","expected_source_bytes","status","reason","probe"}
        assert row["source_sha256"]==sha
        assert isinstance(row["host"],str) and HOST.fullmatch(row["host"])
        assert type(row["expected_source_bytes"]) is int
        assert 0<row["expected_source_bytes"]<=2500000
        assert row["reason"] in SOURCE_REASONS
        assert row["status"] in ("NOT_EVALUATED","SHA_VERIFIED","PROBE_UNAVAILABLE")
        hosts.add(row["host"])
        reason_counts[row["reason"]]+=1
        if row["status"]=="SHA_VERIFIED":verified+=1
        if row["probe"] is None:
            assert row["status"]!="SHA_VERIFIED"
            source_counts[row["status"]]+=1
            continue
        assert row["status"]=="SHA_VERIFIED" and row["reason"]=="OK"
        data=row["probe"]
        assert isinstance(data,dict) and set(data)==PROOF
        assert data["schema"]=="sk1.pub-t-971.source.v1"
        assert data["source_sha256"]==sha
        assert data["source_bytes"]==row["expected_source_bytes"]
        assert data["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert data["product_pub_download_authorized"] is False
        assert data["status"] in SOURCE_STATES
        assert type(data["static_predictions_built_before_writer"]) is bool
        assert type(data["source_immutable"]) is bool
        assert isinstance(data["stories"],list)
        assert type(data["writer_arm_count"]) is int
        source_counts[data["status"]]+=1
        if data["status"]!="EVALUATED":
            assert data["stories"]==[] and data["writer_arm_count"]==0
            continue
        evaluated_sources.add(sha)
        assert data["static_predictions_built_before_writer"] is True
        assert data["source_immutable"] is True
        assert 1<=len(data["stories"])<=3
        total=0;syids=set()
        for ordinal,story in enumerate(data["stories"]):
            assert isinstance(story,dict) and set(story)==STORY
            assert type(story["story_ordinal"]) is int and story["story_ordinal"]==ordinal
            assert type(story["syid"]) is int and 0<=story["syid"]<=0xffffffff
            assert story["syid"] not in syids;syids.add(story["syid"])
            assert type(story["story_utf16_length"]) is int
            assert 1<=story["story_utf16_length"]<=1000000
            assert type(story["insert_at_utf16"]) is int
            assert 0<=story["insert_at_utf16"]<story["story_utf16_length"]
            assert type(story["source_tokn_hit"]) is bool
            assert type(story["source_fd_hit"]) is bool
            static=story["static_class"]
            assert static in ("TOKN","FD","GROWTH")
            if static=="TOKN":assert story["source_tokn_hit"]
            elif static=="FD":assert not story["source_tokn_hit"] and story["source_fd_hit"]
            else:assert not story["source_tokn_hit"] and not story["source_fd_hit"]
            story_counts[static]+=1;total_story+=1
            n=story["predicted_max_pass_utf16"]
            guard=story["predicted_first_growth_guard"]
            if static=="GROWTH":
                assert type(n) is int and 0<=n<=8192
                assert guard in (None,"CAPACITY","GROWTH_UNKNOWN","GROWTH_DESCRIPTOR")
                assert (n==8192)==(guard is None)
                if n==8192:censored+=1
                if n==0:zero+=1
                doses=sorted(set((1,8192) if n==8192 else
                   ((1,2) if n==0 else (1,n,n+1,n+2))))
            else:
                assert n is None and guard is None
                doses=[1]
            assert isinstance(story["arms"],list) and len(story["arms"])==len(doses)
            assert [x["dose_utf16"] for x in story["arms"]]==doses
            measures={}
            for arm in story["arms"]:
                assert isinstance(arm,dict) and set(arm)==ARM
                dose=arm["dose_utf16"]
                assert type(dose) is int and 1<=dose<=8194
                predicted=arm["predicted_first_class"]
                assert predicted in CLASSES
                growth=arm["source_growth_class"]
                if static=="GROWTH":
                    assert growth in GR and predicted==growth
                    if n==0 and dose==1:assert predicted==guard
                    if n>0 and dose<=n:assert predicted=="PASS"
                    if n<8192 and dose==n+1:assert predicted==guard
                    if n<8192 and dose>n:assert predicted!="PASS"
                else:
                    assert growth=="NOT_EVALUATED_PRIORITY"
                    assert predicted==static
                w=arm["writer"]
                assert isinstance(w,dict)
                if w.get("status")=="HOSTED_PASS":
                    assert set(w)=={"status","candidate_sha256","reader_reopened",
                     "syid_siblings_preserved","project_replay_byte_equal",
                     "source_immutable","native_publisher_acceptance"}
                    assert SHA.fullmatch(w["candidate_sha256"])
                    assert all(w[k] is True for k in ("reader_reopened",
                     "syid_siblings_preserved","project_replay_byte_equal","source_immutable"))
                    assert w["native_publisher_acceptance"]=="NOT_EVALUATED"
                    passes+=1
                elif w.get("status")=="WRITER_BLOCKED":
                    assert set(w)=={"status","code"}
                    assert isinstance(w["code"],str) and CODE.fullmatch(w["code"])
                    codes[w["code"]]+=1
                    blocked+=1
                else:
                    assert set(w)=={"status"} and w["status"] in WRITER_OTHER
                    nonstandard+=1
                got=actual(w)
                matrix[predicted+"->"+got]+=1
                measures[dose]=got
                if predicted!=got:
                    mismatch.append({"source_sha256":sha,"story_ordinal":ordinal,
                     "syid":story["syid"],"offset_utf16":story["insert_at_utf16"],
                     "dose_utf16":dose,"predicted":predicted,"observed":got,
                     "writer_code":w.get("code")})
                total_writer+=1;total+=1
            if static=="GROWTH" and n is not None and 0<n<8192:
                first_codes[guard]+=1;seen_threshold_sources.add(sha)
                first=next(a["predicted_first_class"] for a in story["arms"] if a["dose_utf16"]==n+2)
                ok=(measures[n]=="PASS" and measures[n+1]==guard
                    and measures[n+2]==first and
                    all(measures[a["dose_utf16"]]==a["predicted_first_class"] for a in story["arms"]))
                if ok:successful_sources.add(sha)
                threshold_details.append({
                 "source_sha256":sha,"syid":story["syid"],
                 "story_ordinal":ordinal,"offset_utf16":story["insert_at_utf16"],
                 "predicted_last_pass":n,"predicted_first_fail":n+1,
                 "predicted_first_code":guard,"observed_at_n":measures[n],
                 "observed_at_n_plus_1":measures[n+1],
                 "observed_at_n_plus_2":measures[n+2],
                 "full_threshold_match":ok})
        assert total==data["writer_arm_count"]
    assert len(hosts)==37
    assert sum(x["expected_source_bytes"] for x in records)==28191744
    assert len(evaluated_sources)==source_counts["EVALUATED"]
    ns=[x["predicted_last_pass"] for x in threshold_details]
    expected={
     "attempted_source_sha":47,"sha_verified":verified,
     "source_status_counts":dict(sorted(source_counts.items())),
     "source_reason_counts":dict(sorted(reason_counts.items())),
     "evaluated_sources":len(evaluated_sources),
     "evaluated_story_count":total_story,
     "story_class_counts":dict(sorted(story_counts.items())),
     "writer_arms":total_writer,"pass_arms":passes,"blocked_arms":blocked,
     "nonstandard_arms":nonstandard,
     "machine_guard_codes":dict(sorted(codes.items())),
     "first_threshold_guard_codes":dict(sorted(first_codes.items())),
     "first_class_matrix":dict(sorted(matrix.items())),
     "first_class_mismatch_witnesses":mismatch,
     "threshold_story_count":len(threshold_details),
     "threshold_full_matches":sum(x["full_threshold_match"] for x in threshold_details),
     "threshold_source_count":len(seen_threshold_sources),
     "threshold_matching_distinct_sources":len(successful_sources),
     "threshold_min_pass":min(ns) if ns else None,
     "threshold_max_pass":max(ns) if ns else None,
     "threshold_details":threshold_details,
     "right_censored_at_8192":censored,"zero_positive_capacity":zero}
    z=report["summary"]
    assert isinstance(z,dict) and set(z)==REPORT
    assert z==expected,[(k,z.get(k),v) for k,v in expected.items() if z.get(k)!=v]
    print("SK1 PUB-T-971 strict source-safe gate PASS",
          len(evaluated_sources),"sources",
          len(threshold_details),"adjacent thresholds",
          expected["threshold_full_matches"],"matched")
    return expected

if __name__=="__main__":
    validate(Path(sys.argv[1]))
