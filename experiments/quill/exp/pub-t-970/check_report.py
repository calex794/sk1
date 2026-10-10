#!/usr/bin/env python3
"""Independent strict source-safe receipt verifier for PUB-T-970."""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import json
import re
import sys

SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
HOST_QUOTAS={
 "www.mathematicshed.com":18,"www.woodside-medical-practice.org.uk":3,
 "www.leonschools.net":3,"www.biblioteki.org":2,"www.liturgyoffice.org.uk":1}
EXCLUDED_969_QUOTAS={"www.mathematicshed.com":20,"cmapspublic2.ihmc.us":2,
 "secure1.nbed.nb.ca":2,"fradragoljevar.com":3}
EXCLUDED_968_QUOTAS={"www.mathematicshed.com":16,"storage.googleapis.com":3,
 "cmapspublic2.ihmc.us":5,"www.ci.king.nc.us":3}
SLOTS=("first","second","middle","last")
SOURCE_STATUS={"EVALUATED","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY",
 "QUILL_READ_BLOCKED","QUILL_PARSE_BLOCKED","FD_STRUCTURE_BLOCKED",
 "STORY_ID_AMBIGUOUS","STATIC_PROBE_BLOCKED"}
WRITER_STATUS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_REOPEN_FAILED",
 "TARGET_ID_UNAVAILABLE","STORY_ID_MISMATCH","CANONICAL_EDIT_REJECTED",
 "INVALID_CANDIDATE","READER_REOPEN_FAILED","OUTPUT_ID_UNAVAILABLE",
 "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
 "PROJECT_SOURCE_OPEN_FAILED","PROJECT_APPLY_FAILED","PROJECT_WRITER_FAILED",
 "PROJECT_BYTE_MISMATCH"}
SOURCE_REASON={"NOT_STARTED","OK","HTTP_UNAVAILABLE","REQUEST_TIMEOUT",
 "FETCH_ERROR","UNSAFE_REDIRECT","SHA_OR_SIZE_DRIFT","NON_CFB_INPUT",
 "PROCESS_OR_TIMEOUT","EXECUTION_FAILED","INVALID_RECEIPT"}
REPORT_SUM={"attempted_sources","sha_verified_sources","source_status",
 "per_host","evaluated_source_count","evaluated_story_count",
 "unique_position_attempts","comparable_writer_arms","hosted_pass_arms",
 "writer_nonstandard_arms","writer_nonstandard_reasons","writer_guard_counts",
 "fdpp_hit_arms","fdpc_hit_arms","both_fd_hit_arms",
 "sources_with_actual_fd_refusal","stories_with_actual_fd_refusal",
 "code_specific_confusion","actual_label_counts","mismatch_witnesses",
 "priority_confusion","priority_mismatch_witnesses","per_dose_confusion"}
PLAN={"schema","rar2_pin","lalamu_pin","source_manifest","old_manifest",
 "excluded_original_35","excluded_existing_62","host_quotas",
 "excluded_968_sources","excluded_968_quotas",
 "excluded_969_sources","excluded_969_quotas",
 "preselected_sha256","preselected_source_bytes","source_count","doses_utf16",
 "slots","max_eligible_stories_per_source","operation","prediction",
 "native_publisher_acceptance"}
SOURCE_PROOF={"schema","source_sha256","source_bytes","status",
 "static_predictions_built_before_writer","publisher_native_acceptance",
 "product_pub_download_authorized","stories","writer_arm_count","source_immutable"}
STORY={"story_ordinal","syid","story_utf16_length","arms"}
ARM={"slot","ascii_rank","at_utf16","story_utf16_length",
 "predicted_fd_hit","fdpp_hit","fdpc_hit",
 "source_tokn_hit","predicted_first_class","dose_utf16","source_growth_class",
 "nearest_fd_boundary_distance_bytes","writer"}
WRITER_PASS={"status","candidate_sha256","reader_reopened",
 "syid_siblings_preserved","project_replay_byte_equal","source_immutable",
 "native_publisher_acceptance"}

def verify(folder:Path):
    assert {p.name for p in folder.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((folder/"plan.json").read_text())
    records=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    assert set(plan)==PLAN and plan["schema"]=="sk1.pub-t-970.plan.v1"
    assert plan["rar2_pin"]==PIN
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["source_manifest"]=="https://raw.githubusercontent.com/Lalalalendia/lalamu/f78cc6f455f4dc222868f9cc035511a6ca7a91ea/pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json"
    assert plan["old_manifest"]=="https://raw.githubusercontent.com/Lalalalendia/rar2/703808408fd919e564a90cdc236e81db3c04af8b/tools/corpus/receipts/lalamu-materialized-35-input-2026-09-29.json"
    assert plan["excluded_original_35"]==35 and plan["excluded_existing_62"]==62
    assert plan["host_quotas"]==HOST_QUOTAS
    assert plan["excluded_969_sources"]==27 and plan["excluded_969_quotas"]==EXCLUDED_969_QUOTAS
    assert plan["doses_utf16"]==[1,2,8]
    assert plan["excluded_968_sources"]==27 and plan["excluded_968_quotas"]==EXCLUDED_968_QUOTAS
    assert plan["source_count"]==27
    assert plan["slots"]==list(SLOTS)
    assert plan["max_eligible_stories_per_source"]==3
    assert plan["operation"]=="insert_n_ascii"
    assert plan["prediction"]=="source-only TOKN then FD then growth source geometry or PASS"
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(records,list) and len(records)==27
    assert len(plan["preselected_sha256"])==27
    assert plan["preselected_sha256"]==[r["source_sha256"] for r in records]
    assert len(set(plan["preselected_sha256"]))==27
    assert all(SHA.fullmatch(sha) for sha in plan["preselected_sha256"])
    assert type(plan["preselected_source_bytes"]) is int
    assert 0<plan["preselected_source_bytes"]<=50*1024*1024
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
      "product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-970.report.v1" and report["rar2_pin"]==PIN
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert records==report["records"]
    hosts=Counter();host_status=defaultdict(Counter);source_status=Counter()
    matrix=Counter();guard_codes=Counter();notstandard=Counter();labels=Counter()
    fd_source=set();fd_stories=set();stories=set();mismatches=[]
    pp=pc=both=arms=passes=skips=0;verified=0;evaluated=0
    priority=Counter();priority_mismatch=[]
    per_dose=defaultdict(Counter)
    for row in records:
        assert set(row)=={"source_sha256","host","expected_source_bytes",
          "status","reason","probe"}
        assert row["host"] in HOST_QUOTAS and SHA.fullmatch(row["source_sha256"])
        assert type(row["expected_source_bytes"]) is int
        assert 0<row["expected_source_bytes"]<=2500000
        assert row["status"] in {"NOT_EVALUATED","SHA_VERIFIED","PROBE_UNAVAILABLE"}
        assert row["reason"] in SOURCE_REASON
        hosts[row["host"]]+=1;host_status[row["host"]][row["status"]]+=1
        if row["status"]=="SHA_VERIFIED":
            verified+=1
        if row["probe"] is None:
            assert row["status"]!="SHA_VERIFIED"
            source_status[row["status"]]+=1
            continue
        assert row["status"]=="SHA_VERIFIED" and row["reason"]=="OK"
        doc=row["probe"]
        assert isinstance(doc,dict) and set(doc)==SOURCE_PROOF
        assert doc["schema"]=="sk1.pub-t-970.source.v1"
        assert doc["source_sha256"]==row["source_sha256"]
        assert doc["source_bytes"]==row["expected_source_bytes"]
        assert doc["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert doc["product_pub_download_authorized"] is False
        assert doc["status"] in SOURCE_STATUS
        assert type(doc["static_predictions_built_before_writer"]) is bool
        assert type(doc["source_immutable"]) is bool
        assert type(doc["writer_arm_count"]) is int
        assert 0<=doc["writer_arm_count"]<=36
        assert isinstance(doc["stories"],list)
        source_status[doc["status"]]+=1
        if doc["status"]!="EVALUATED":
            assert doc["writer_arm_count"]==0 and doc["stories"]==[]
            continue
        evaluated+=1
        assert doc["static_predictions_built_before_writer"] is True
        assert doc["source_immutable"] is True
        assert 1<=len(doc["stories"])<=3
        arm_count=0;syids=set()
        for index,story in enumerate(doc["stories"]):
            assert set(story)==STORY and story["story_ordinal"]==index
            assert type(story["syid"]) is int and 0<=story["syid"]<=0xffffffff
            assert story["syid"] not in syids;syids.add(story["syid"])
            assert type(story["story_utf16_length"]) is int
            assert 1<=story["story_utf16_length"]<=1000000
            assert isinstance(story["arms"],list) and 1<=len(story["arms"])<=12
            unique=set();previous_rank=-1
            stories.add((row["source_sha256"],story["syid"]))
            for arm in story["arms"]:
                assert set(arm)==ARM
                assert arm["slot"] in SLOTS
                assert type(arm["ascii_rank"]) is int and arm["ascii_rank"]>=0
                assert type(arm["at_utf16"]) is int
                assert 0<=arm["at_utf16"]<story["story_utf16_length"]
                assert arm["dose_utf16"] in [1,2,8]
                assert (arm["at_utf16"],arm["dose_utf16"]) not in unique;unique.add((arm["at_utf16"],arm["dose_utf16"]))
                assert arm["story_utf16_length"]==story["story_utf16_length"]
                assert type(arm["source_tokn_hit"]) is bool
                assert arm["source_growth_class"] in {"PASS","CAPACITY","GROWTH_UNKNOWN","GROWTH_DESCRIPTOR"}
                assert arm["predicted_first_class"]==("TOKN" if arm["source_tokn_hit"] else "FD" if arm["predicted_fd_hit"] else arm["source_growth_class"])
                assert type(arm["predicted_fd_hit"]) is bool
                assert type(arm["fdpp_hit"]) is bool and type(arm["fdpc_hit"]) is bool
                assert arm["predicted_fd_hit"]==(arm["fdpp_hit"] or arm["fdpc_hit"])
                d=arm["nearest_fd_boundary_distance_bytes"]
                assert d is None or type(d) is int and 0<=d<=0xffffffff
                if arm["predicted_fd_hit"]:assert d==0
                pp+=int(arm["fdpp_hit"]);pc+=int(arm["fdpc_hit"])
                both+=int(arm["fdpp_hit"] and arm["fdpc_hit"])
                w=arm["writer"]
                assert isinstance(w,dict) and w.get("status") in WRITER_STATUS
                wstate=w["status"]
                predicted=arm["predicted_fd_hit"]
                if wstate=="HOSTED_PASS":
                    assert set(w)==WRITER_PASS
                    assert SHA.fullmatch(w["candidate_sha256"])
                    for k in ("reader_reopened","syid_siblings_preserved",
                          "project_replay_byte_equal","source_immutable"):
                        assert w[k] is True
                    assert w["native_publisher_acceptance"]=="NOT_EVALUATED"
                    passes+=1
                elif wstate=="WRITER_BLOCKED":
                    assert set(w)=={"status","code"}
                    assert CODE.fullmatch(w["code"])
                    guard_codes[w["code"]]+=1
                else:
                    assert set(w)=={"status"}
                if wstate in {"HOSTED_PASS","WRITER_BLOCKED"}:
                    pred=arm["predicted_first_class"]
                    actual=("TOKN" if wstate=="WRITER_BLOCKED" and w.get("code")=="quill_token_layer"
                        else "FD" if wstate=="WRITER_BLOCKED" and w.get("code")=="quill_insertion_at_fd_boundary"
                        else "GROWTH_UNKNOWN" if wstate=="WRITER_BLOCKED" and w.get("code")=="quill_growth_would_discard_unknown"
                        else "GROWTH_DESCRIPTOR" if wstate=="WRITER_BLOCKED" and w.get("code")=="quill_growth_would_discard_descriptor"
                        else "CAPACITY" if wstate=="WRITER_BLOCKED" and w.get("code")=="quill_insufficient_capacity"
                        else "PASS" if wstate=="HOSTED_PASS" else "OTHER_GUARD")
                    priority[pred+"->"+actual]+=1
                    per_dose[str(arm["dose_utf16"])][pred+"->"+actual]+=1
                    if pred!=actual:
                        priority_mismatch.append({"source_sha256":row["source_sha256"],
                           "syid":story["syid"],"at_utf16":arm["at_utf16"],
                           "dose_utf16":arm["dose_utf16"],
                           "predicted":pred,"actual":actual,"code":w.get("code")})
                    fd=(wstate=="WRITER_BLOCKED" and
                        w.get("code")=="quill_insertion_at_fd_boundary")
                    labels["FD" if fd else "NOT_FD"]+=1
                    key=("TP" if predicted and fd else
                       "FP" if predicted else
                       "FN" if fd else "TN")
                    matrix[key]+=1
                    if fd:
                        fd_source.add(row["source_sha256"])
                        fd_stories.add((row["source_sha256"],story["syid"]))
                    if key in ("FP","FN"):
                        mismatches.append({
                          "source_sha256":row["source_sha256"],
                          "story_ordinal":story["story_ordinal"],"syid":story["syid"],
                          "offset_utf16":arm["at_utf16"],"slot":arm["slot"],
                          "predicted_fd_hit":predicted,"fdpp_hit":arm["fdpp_hit"],
                          "fdpc_hit":arm["fdpc_hit"],"actual":wstate,
                          "actual_code":w.get("code")})
                else:skips+=1;notstandard[wstate]+=1
                arms+=1;arm_count+=1
        assert arm_count==doc["writer_arm_count"]
    assert hosts==Counter(HOST_QUOTAS)
    assert sum(x["expected_source_bytes"] for x in records)==plan["preselected_source_bytes"]
    s=report["summary"];assert isinstance(s,dict) and set(s)==REPORT_SUM
    expected={
      "attempted_sources":27,"sha_verified_sources":verified,
      "source_status":dict(sorted(source_status.items())),
      "per_host":{k:dict(sorted(v.items())) for k,v in sorted(host_status.items())},
      "evaluated_source_count":evaluated,"evaluated_story_count":len(stories),
      "unique_position_attempts":arms,"comparable_writer_arms":sum(matrix.values()),
      "hosted_pass_arms":passes,"writer_nonstandard_arms":skips,
      "writer_nonstandard_reasons":dict(sorted(notstandard.items())),
      "writer_guard_counts":dict(sorted(guard_codes.items())),
      "fdpp_hit_arms":pp,"fdpc_hit_arms":pc,"both_fd_hit_arms":both,
      "sources_with_actual_fd_refusal":len(fd_source),
      "stories_with_actual_fd_refusal":len(fd_stories),
      "code_specific_confusion":{k:matrix[k] for k in ("TP","FP","FN","TN")},
      "actual_label_counts":dict(sorted(labels.items())),
      "mismatch_witnesses":mismatches,
      "priority_confusion":dict(sorted(priority.items())),
      "priority_mismatch_witnesses":priority_mismatch,
      "per_dose_confusion":{k:dict(sorted(v.items())) for k,v in sorted(per_dose.items())}
    }
    assert s==expected,[(k,s.get(k),v) for k,v in expected.items() if s.get(k)!=v]
    print("PUB-T-970 receipts PASS",evaluated,"evaluated sources",
        len(stories),"Story",arms,"arms",expected["code_specific_confusion"])
    return True

if __name__=="__main__":
    verify(Path(sys.argv[1]))
