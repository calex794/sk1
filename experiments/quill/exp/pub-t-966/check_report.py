#!/usr/bin/env python3
"""Fail closed: validate only source-safe PUB-T-966 numeric Writer receipts."""
from __future__ import annotations
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import sys

SHA=re.compile(r"^[a-f0-9]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
PRIOR="ab73d6206663523929843616e196287563468b0ac8988005842349afc206aeb9"
SLOTS=("first","middle","last")
HOSTS={"www.mathematicshed.com":9,"www.anyssa.org":2,"law.duke.edu":1,"www.bnssports.us":2}
ALLOWED_SOURCE={"NOT_EVALUATED","SHA_VERIFIED","ANOMALY","MEASURED_WITH_EXCLUSIONS","ALL_POSITIONS_MEASURED"}
ALLOWED_POSITION={"NOT_EVALUATED","NO_BASELINE_PASS","BRACKET_MEASURED","CENSORED_PASS",
 "ANOMALY","INCOMPLETE","DUPLICATE_SECOND_POSITION","DUPLICATE_OTHER_POSITION"}
ALLOWED_ARM={"HOSTED_PASS","WRITER_BLOCKED","PROBE_UNAVAILABLE",
    "SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY","CANONICAL_EDIT_REJECTED",
    "INVALID_CANDIDATE_HASH","REOPEN_FAILED","TARGET_SEMANTIC_MISMATCH",
    "SYID_OR_SIBLING_MISMATCH","REPLAY_OPEN_FAILED","REPLAY_APPLY_FAILED",
    "REPLAY_WRITE_FAILED","REPLAY_BYTES_MISMATCH",
    "DUPLICATE_SECOND_POSITION","DUPLICATE_OTHER_POSITION"}
ALLOWED_REASON={"NOT_STARTED","OK","HTTP_UNAVAILABLE","REQUEST_TIMEOUT","FETCH_ERROR",
 "UNSAFE_REDIRECT","SHA_OR_SIZE_DRIFT","NON_CFB_INPUT","PROCESS_OR_TIMEOUT",
 "PROCESS_FAILED","BAD_RECEIPT_OR_CFB","NO_ATTEMPTS","CONTEXT_OR_CFB_INVARIANT",
 "ALNUM_SLOT_COLLISION","WRITER_BLOCKED","CAP_8192","OBSERVED_GUARD",
 "UNRESOLVED_BOUNDARY","POSITION_INVARIANT_FAILED"}|ALLOWED_ARM
PHYSICAL_NUM={"cfb_size_before","cfb_size_after","quill_stream_size_before",
              "quill_stream_size_after","nonquill_stream_changes"}
PHYSICAL_BOOL={"quill_logical_changed","sector_count_equal","fat_table_equal",
               "minifat_table_equal","directory_sector_ids_equal","root_chain_equal"}
ARM_META={"story_ordinal","offset_utf16","before_utf16","after_utf16",
          "baseline_second_offset_utf16","ascii_count"}
SUM_KEYS={"source_attempts","source_verified","source_statuses","total_positions",
 "position_statuses","by_slot","arms","hosted_pass_arms","writer_blocked_arms",
 "guard_codes","first_guard_codes_by_slot","measured_comparisons","comparison",
 "comparison_by_slot","pass_cfb_invariant_failures","sources_with_anomaly"}

def exact_meta(x,b,growth):
    assert all(type(x[k]) is int and 0<=x[k]<1_000_000 for k in ARM_META)
    assert x["after_utf16"]==x["before_utf16"]+growth
    assert x["story_ordinal"]==b["story_ordinal"]
    assert x["before_utf16"]==b["story_utf16"]
    assert x["baseline_second_offset_utf16"]==b["second_offset_utf16"]
    assert x["ascii_count"]>=1

def check(root:Path):
    assert {x.name for x in root.iterdir()}=={"baseline.json","plan.json","records.json","report.json"} \
        or {x.name for x in root.iterdir()}=={"plan.json","records.json","report.json"}
    prior=json.loads((Path(__file__).resolve().parent/"baseline.json").read_text(encoding="utf-8"))
    plan=json.loads((root/"plan.json").read_text(encoding="utf-8"))
    rows=json.loads((root/"records.json").read_text(encoding="utf-8"))
    report=json.loads((root/"report.json").read_text(encoding="utf-8"))
    assert set(prior)=={"schema","source","source_scientific_sha","source_zip_sha256","source_successful_cases","records"}
    assert prior["schema"]=="sk1.pub-t-966.baseline.v1"
    assert prior["source_zip_sha256"]==PRIOR and prior["source_successful_cases"]==14
    assert prior["source_scientific_sha"]=="4ed320411bb5bebf23ea5a4c31c336d3fba74ce1"
    assert len(prior["records"])==14
    assert set(plan)=={"schema","rar2_pin","prior_t962_zip_sha256",
       "prior_t962_science_sha","source_manifest","lalamu_pin",
       "preselected_sha256","planned_source_bytes","slots",
       "growth_ladder","scope","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-966.plan.v1" and plan["rar2_pin"]==PIN
    assert plan["prior_t962_zip_sha256"]==PRIOR
    assert plan["prior_t962_science_sha"]==prior["source_scientific_sha"]
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["slots"]==list(SLOTS) and plan["growth_ladder"]==[1<<i for i in range(14)]
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(plan["scope"],str) and "same Story" in plan["scope"]
    assert plan["source_manifest"]=="https://raw.githubusercontent.com/Lalalalendia/lalamu/f78cc6f455f4dc222868f9cc035511a6ca7a91ea/pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json"
    assert type(plan["planned_source_bytes"]) is int and 0<plan["planned_source_bytes"]<50*1024*1024
    assert len(rows)==14 and len(plan["preselected_sha256"])==14
    assert [r["source_sha256"] for r in rows]==plan["preselected_sha256"]
    assert [b["sha256"] for b in prior["records"]]==plan["preselected_sha256"]
    assert len(set(plan["preselected_sha256"]))==14
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
      "product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-966.report.v1"
    assert report["rar2_pin"]==PIN and report["records"]==rows
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False

    host_counts=Counter();source_counts=Counter()
    pos_counts=Counter();by_slot=defaultdict(Counter)
    guard_codes=Counter();first_codes=defaultdict(Counter)
    comparison=Counter();comparison_by_slot=defaultdict(Counter)
    arms=passes=blocked=physical_failures=measured=0
    for r,b in zip(rows,prior["records"]):
        assert set(b)=={"sha256","host","source_bytes","story_ordinal",
            "second_offset_utf16","story_utf16","previous_last_pass",
            "previous_first_fail","previous_guard"}
        assert SHA.fullmatch(b["sha256"]) and CODE.fullmatch(b["previous_guard"])
        assert b["previous_first_fail"]==b["previous_last_pass"]+1
        assert set(r)=={"source_sha256","host","source_bytes","previous_second",
          "status","reason","positions"}
        assert r["source_sha256"]==b["sha256"] and r["host"]==b["host"]
        assert r["source_bytes"]==b["source_bytes"] and type(r["source_bytes"]) is int
        assert r["status"] in ALLOWED_SOURCE and r["reason"] in ALLOWED_REASON
        assert r["previous_second"]=={
            "story_ordinal":b["story_ordinal"],"offset_utf16":b["second_offset_utf16"],
            "before_utf16":b["story_utf16"],"last_pass":b["previous_last_pass"],
            "first_fail":b["previous_first_fail"],"first_guard":b["previous_guard"]}
        host_counts[r["host"]]+=1;source_counts[r["status"]]+=1
        assert len(r["positions"])==3 if r["status"]!="NOT_EVALUATED" else len(r["positions"])==0
        for p,slot in zip(r["positions"],SLOTS):
            assert set(p)=={"slot","status","reason","arms","bracket",
                "nonmonotone_detected","delta_from_second"}
            assert p["slot"]==slot and p["status"] in ALLOWED_POSITION
            assert p["reason"] in ALLOWED_REASON and type(p["nonmonotone_detected"]) is bool
            assert isinstance(p["arms"],list) and 1<=len(p["arms"])<=50
            assert isinstance(p["bracket"],dict) and set(p["bracket"])=={
                "last_tested_pass","first_tested_fail"}
            x,y=p["bracket"]["last_tested_pass"],p["bracket"]["first_tested_fail"]
            assert type(x) is int and 0<=x<=8192
            assert y is None or type(y) is int and 1<=y<=8192
            assert p["delta_from_second"] is None or type(p["delta_from_second"]) is int
            pos_counts[p["status"]]+=1;by_slot[slot][p["status"]]+=1
            if p["status"]=="BRACKET_MEASURED":
                assert y==x+1 and x>=1
                assert p["delta_from_second"]==x-b["previous_last_pass"]
                assert p["arms"][0]["status"]=="HOSTED_PASS"
                assert len([a for a in p["arms"] if a["phase"]=="after_failure_control"])==1
                measured+=1
                label="same" if p["delta_from_second"]==0 else "higher" if p["delta_from_second"]>0 else "lower"
                comparison[label]+=1;comparison_by_slot[slot][label]+=1
                first=[a for a in p["arms"] if a["growth_utf16"]==y and a["status"]=="WRITER_BLOCKED"]
                assert first,("missing first fail",slot)
                first_codes[slot][first[0]["writer_code"]]+=1
            else:assert p["delta_from_second"] is None
            if p["status"].startswith("DUPLICATE_"):
                assert len(p["arms"])==1
                assert p["arms"][0]["status"]==p["status"]
            if p["status"]=="NO_BASELINE_PASS":
                assert x==0 and y==1 and p["arms"][0]["status"]=="WRITER_BLOCKED"
            shape=None
            for a in p["arms"]:
                assert isinstance(a,dict) and {"growth_utf16","slot","status","reason","phase"}<=set(a)
                assert a["slot"]==slot and a["status"] in ALLOWED_ARM
                assert a["reason"] in ALLOWED_REASON
                n=a["growth_utf16"];assert type(n) is int and 1<=n<=8192
                assert a["phase"] in ("ladder","refine","after_failure_control")
                expected={"growth_utf16","slot","status","reason","phase"}
                if a["status"]=="WRITER_BLOCKED":
                    expected.add("writer_code")
                    assert CODE.fullmatch(a["writer_code"])
                    guard_codes[a["writer_code"]]+=1;blocked+=1
                if "story_ordinal" in a:
                    expected|=ARM_META
                    exact_meta(a,b,n)
                    cur=(a["story_ordinal"],a["offset_utf16"],a["before_utf16"],a["ascii_count"])
                    if shape is None:shape=cur
                    else:assert shape==cur or p["status"]=="ANOMALY"
                    assert a["offset_utf16"]!=b["second_offset_utf16"] \
                       or a["status"]=="DUPLICATE_SECOND_POSITION"
                if a["status"]=="HOSTED_PASS":
                    assert a["reason"]=="OK"
                    expected|={"candidate_sha256","cfb"}
                    assert SHA.fullmatch(a["candidate_sha256"])
                    z=a["cfb"]
                    assert set(z)==PHYSICAL_NUM|PHYSICAL_BOOL
                    assert all(type(z[k]) is int and 0<=z[k]<1_000_000_000 for k in PHYSICAL_NUM)
                    assert all(type(z[k]) is bool for k in PHYSICAL_BOOL)
                    assert z["cfb_size_before"]==r["source_bytes"]
                    passes+=1
                    physical_failures+=int(not(
                        z["nonquill_stream_changes"]==0 and z["quill_logical_changed"] and
                        z["cfb_size_before"]==z["cfb_size_after"] and
                        z["quill_stream_size_before"]==z["quill_stream_size_after"] and
                        all(z[k] for k in PHYSICAL_BOOL-{"quill_logical_changed"})))
                assert set(a)==expected,(a["status"],set(a)-expected)
                arms+=1
    assert host_counts==Counter(HOSTS)
    assert sum(r["source_bytes"] for r in rows)==plan["planned_source_bytes"]
    s=report["summary"];assert set(s)==SUM_KEYS
    expected_int={"source_attempts":14,"source_verified":sum(r["status"]!="NOT_EVALUATED" for r in rows),
       "total_positions":sum(pos_counts.values()),"arms":arms,
       "hosted_pass_arms":passes,"writer_blocked_arms":blocked,
       "measured_comparisons":measured,"pass_cfb_invariant_failures":physical_failures,
       "sources_with_anomaly":source_counts["ANOMALY"]}
    for k,v in expected_int.items(): assert type(s[k]) is int and s[k]==v,(k,s[k],v)
    assert s["source_statuses"]==dict(sorted(source_counts.items()))
    assert s["position_statuses"]==dict(sorted(pos_counts.items()))
    assert s["by_slot"]=={k:dict(sorted(v.items())) for k,v in sorted(by_slot.items())}
    assert s["guard_codes"]==dict(sorted(guard_codes.items()))
    assert s["first_guard_codes_by_slot"]=={k:dict(sorted(v.items())) for k,v in sorted(first_codes.items())}
    assert s["comparison"]==dict(sorted(comparison.items()))
    assert s["comparison_by_slot"]=={k:dict(sorted(v.items())) for k,v in sorted(comparison_by_slot.items())}
    print("PUB-T-966 SOURCE-SAFE PASS",measured,"independent position thresholds; new arms",arms)
    return True

if __name__=="__main__":check(Path(sys.argv[1]))
