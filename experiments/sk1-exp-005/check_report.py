#!/usr/bin/env python3
"""EXP005 strict source-safe schema and independently recomputed holdout metrics."""
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
import sys

SHA=re.compile(r"^[a-f0-9]{64}$")
CODE=re.compile(r"^[a-zA-Z0-9_]{1,90}$")
HOSTS={"www.mathematicshed.com":30,"www.anyssa.org":8,
       "storage.googleapis.com":8,"law.duke.edu":6,
       "www.greville.surrey.sch.uk":5,"cdn.instructables.com":3,
       "www.bnssports.us":2}
OUTCOMES={"INSPECTED","QUILL_STREAM_MISSING_OR_BROKEN",
          "QUILL_STORY_CATALOG_UNPARSEABLE","TEXT_DESCRIPTOR_NON_UNIQUE",
          "ALIGNED_SERVICE_ANCHOR_MISSING","STRUCTURAL_RANGE_INVALID",
          "INSPECTOR_FAILED","NOT_EVALUATED"}
PRED={"NONZERO_UNKNOWN_ANCHOR_TAIL","NAMED_DESCRIPTOR_PAYLOAD_OVERLAP",
      "INSUFFICIENT_PRE_ANCHOR_SPACE","TAIL_TWO_BYTES_CLEAR_ONLY"}
REASONS={"NOT_STARTED","HTTP_UNAVAILABLE","REQUEST_TIMEOUT","FETCH_ERROR",
         "UNSAFE_REDIRECT","SHA_OR_SIZE_DRIFT","NON_CFB_INPUT","OK"}
RECORD_BASE={"source_sha256","host","expected_source_bytes","status","reason",
             "static_outcome","writer_outcome","second_pairs"}
STATIC={"tail2_nonzero_count","gap_before_anchor_bytes",
        "descriptor_payload_overlaps_tail2","predicted_plus_one_gate"}
PAIRS={"story_ordinal","offset_utf16","delete_result","insert_result"}
WRITE_STATUS={"NOT_EVALUATED","EVALUATED","NO_PLAIN_EDITABLE_STORY",
              "SOURCE_EDITOR_OPEN_BLOCKED","WRITER_PROBE_FAILED","PAIR_INVALID","UNKNOWN"}
BASIC_TYPES={"HOSTED_PASS","CANONICAL_EDIT_REJECTED","reader_or_editor_reopen_blocked",
             "project_replay_blocked","bounded_candidate_validation_failed",
             "SYID_OR_UNRELATED_STORY_MISMATCH","SYID_VERIFICATION_UNAVAILABLE",
             "NOT_EVALUATED","UNCLASSIFIED_WRITER_BLOCK","UNCLASSIFIED_HARNESS_OUTCOME"}
def label(p):
    if p["delete_result"]!="HOSTED_PASS":return "NOT_COMPARABLE_DELETION"
    if p["insert_result"]=="HOSTED_PASS":return "INSERTION_PASS"
    if p["insert_result"]=="quill_growth_would_discard_unknown":return "PROTECTED_TAIL_GUARD"
    return "OTHER_INSERTION_REJECTION"

def check(fname):
    x=json.loads(Path(fname).read_text(encoding="utf-8"))
    assert set(x)=={"schema","rar2_pin","lalamu_pin","source_manifest","prior_manifest",
                   "native_publisher_acceptance","product_pub_download_authorized",
                   "summary","records"}
    assert x["schema"]=="sk1.exp005.holdout-report.v1"
    assert x["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert x["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert x["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert x["product_pub_download_authorized"] is False
    records=x["records"]
    assert len(records)==sum(HOSTS.values())==62
    assert len(set(r["source_sha256"] for r in records))==62
    hosts=Counter()
    diag=Counter()
    pm=Counter()
    sm=Counter()
    byhost=defaultdict(Counter)
    witnesses=[]
    for r in records:
        assert RECORD_BASE<=set(r)<=RECORD_BASE|STATIC
        assert SHA.fullmatch(r["source_sha256"])
        assert r["host"] in HOSTS
        hosts[r["host"]]+=1
        assert isinstance(r["expected_source_bytes"],int) and 0<r["expected_source_bytes"]<=2_500_000
        assert r["status"] in {"NOT_EVALUATED","SHA_VERIFIED"}
        assert r["reason"] in REASONS
        assert r["static_outcome"] in OUTCOMES
        assert r["writer_outcome"] in WRITE_STATUS
        assert isinstance(r["second_pairs"],list) and len(r["second_pairs"])<=3
        byhost[r["host"]][r["status"]]+=1
        if r["status"]!="SHA_VERIFIED":
            assert r["reason"]!="OK"
            assert r["static_outcome"]==r["writer_outcome"]=="NOT_EVALUATED"
            assert not r["second_pairs"] and not(set(r)&STATIC)
            diag["not_evaluated_"+r["reason"]]+=1
            continue
        assert r["reason"]=="OK"
        diag["source_verified"]+=1
        if r["static_outcome"]=="INSPECTED":
            assert set(r)==RECORD_BASE|STATIC
            assert r["predicted_plus_one_gate"] in PRED
            assert all(isinstance(r[k],int) and r[k]>=0 for k in (
                "tail2_nonzero_count","gap_before_anchor_bytes","descriptor_payload_overlaps_tail2"))
            assert r["tail2_nonzero_count"]<=2
            assert (r["predicted_plus_one_gate"]=="NONZERO_UNKNOWN_ANCHOR_TAIL") == (
                r["gap_before_anchor_bytes"]>=2 and r["tail2_nonzero_count"]>0)
            diag["static_inspected"]+=1
        else:
            assert set(r)==RECORD_BASE and not r["second_pairs"]
            diag["static_"+r["static_outcome"]]+=1
            continue
        if r["writer_outcome"]!="EVALUATED":
            assert not r["second_pairs"]
            diag["writer_"+r["writer_outcome"]]+=1
            continue
        diag["writer_evaluated"]+=1
        seen_offsets=set()
        obs=set()
        predicts=r["predicted_plus_one_gate"]=="NONZERO_UNKNOWN_ANCHOR_TAIL"
        for p in r["second_pairs"]:
            assert set(p)==PAIRS
            assert isinstance(p["story_ordinal"],int) and 0<=p["story_ordinal"]<=2
            assert p["story_ordinal"] not in seen_offsets
            seen_offsets.add(p["story_ordinal"])
            assert isinstance(p["offset_utf16"],int) and p["offset_utf16"]>=0
            assert CODE.fullmatch(p["delete_result"]) and CODE.fullmatch(p["insert_result"])
            c=label(p)
            diag["pair_"+c]+=1
            if c not in ("INSERTION_PASS","PROTECTED_TAIL_GUARD"):continue
            blocked=c=="PROTECTED_TAIL_GUARD"
            pm["TP" if predicts and blocked else
               "FN" if blocked else
               "FP" if predicts else "TN"]+=1
            obs.add(c)
            if predicts!=blocked and len(witnesses)<80:
                witnesses.append({"source_sha256":r["source_sha256"],
                                  "story_ordinal":p["story_ordinal"],
                                  "offset_utf16":p["offset_utf16"],
                                  "predicted_tail_nonzero":predicts,"observed":c})
        if len(obs)==1:
            blocked=("PROTECTED_TAIL_GUARD" in obs)
            sm["TP" if predicts and blocked else
               "FN" if blocked else
               "FP" if predicts else "TN"]+=1
        elif len(obs)>1:
            sm["MIXED_OUTCOMES"]+=1
        else:
            sm["NO_DISCRIMINATING_STORY"]+=1
    assert hosts==HOSTS
    s=x["summary"]
    assert set(s)=={"attempted_sources","observed","primary_independent_source_matrix",
                   "correlated_story_pair_matrix","verified_by_host","contradiction_witnesses"}
    assert s["attempted_sources"]==62
    assert s["observed"]==dict(sorted(diag.items()))
    assert s["primary_independent_source_matrix"]==dict(sorted(sm.items()))
    assert s["correlated_story_pair_matrix"]==dict(sorted(pm.items()))
    assert s["verified_by_host"]=={k:dict(sorted(v.items())) for k,v in sorted(byhost.items())}
    assert s["contradiction_witnesses"]==witnesses
    comparable=sum(sm.get(k,0) for k in ("TP","TN","FP","FN"))
    assert diag.get("source_verified",0)>=15
    assert comparable>=10
    print("EXP-005: source-safe independent holdout / denominators / matrices PASS")

if __name__=="__main__":
    assert len(sys.argv)==2
    check(sys.argv[1])
