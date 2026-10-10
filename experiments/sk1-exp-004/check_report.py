#!/usr/bin/env python3
"""Fail closed on source-leaking receipt, missing source, or bad correlation math."""
import json
from collections import Counter,defaultdict
from pathlib import Path
import re
import sys

SHA = re.compile(r"^[0-9a-f]{64}$")
ALLOWED = {
    "INSPECTED", "QUILL_STREAM_MISSING_OR_BROKEN",
    "QUILL_STORY_CATALOG_UNPARSEABLE", "TEXT_DESCRIPTOR_NON_UNIQUE",
    "ALIGNED_SERVICE_ANCHOR_MISSING", "STRUCTURAL_RANGE_INVALID"
}
TAG = {"STSH","SYID","STRS","FDPP","FDPC","BTEP","BTEC",
       "MCLD","TOKN","TEXT","OTHER_KNOWN_DESCRIPTOR"}
PRED = {"NONZERO_UNKNOWN_ANCHOR_TAIL","NAMED_DESCRIPTOR_PAYLOAD_OVERLAP",
        "INSUFFICIENT_PRE_ANCHOR_SPACE","TAIL_TWO_BYTES_CLEAR_ONLY"}
GROUP = {"GROWTH_BLOCKED","GROWTH_ALLOWED_AT_SECOND","NO_ELIGIBLE_STORY"}
BASE = {"source_sha256","source_type","expected_exp003_label","status","reason"}
METRICS = {
    "quill_length","descriptor_count","story_count","text_start","text_end",
    "first_fd_anchor","gap_before_anchor_bytes","tail2_nonzero_count",
    "trailing_zero_bytes","descriptor_payload_overlaps_tail2",
    "tail2_descriptor_tags","descriptor_metadata_inside_move_window",
    "predicted_plus_one_gate"
}

def check(path):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    assert set(r) == {"schema","rar2_pin","exp003_evidence",
                      "native_publisher_acceptance",
                      "product_pub_download_authorized","summary","records"}
    assert r["schema"] == "sk1.exp004.report.v1"
    assert r["rar2_pin"] == "703808408fd919e564a90cdc236e81db3c04af8b"
    assert r["exp003_evidence"] == (
        "https://github.com/calex794/sk1/actions/runs/38078248161/artifacts/11679124237"
    )
    assert r["native_publisher_acceptance"] == "NOT_EVALUATED"
    assert r["product_pub_download_authorized"] is False
    rows=r["records"]
    assert len(rows)==26 and len({x["source_sha256"] for x in rows})==26
    assert all(x["status"] == "EVALUATED" for x in rows)
    labels=Counter(x["expected_exp003_label"] for x in rows)
    assert labels=={"GROWTH_BLOCKED":10,"GROWTH_ALLOWED_AT_SECOND":13,"NO_ELIGIBLE_STORY":3}
    confusion=Counter()
    guard=Counter()
    owners=defaultdict(Counter)
    gap=defaultdict(list)
    inspected=0
    for x in rows:
        assert SHA.fullmatch(x["source_sha256"])
        assert x["source_type"] in {"github","institutional-web"}
        assert x["expected_exp003_label"] in GROUP
        assert x["reason"] in ALLOWED
        if x["reason"] != "INSPECTED":
            assert set(x)==BASE
            if x["expected_exp003_label"]!="NO_ELIGIBLE_STORY":
                confusion["UNRESOLVED_"+x["expected_exp003_label"]]+=1
            continue
        inspected+=1
        assert set(x)==BASE|METRICS
        a=x["text_start"]
        end=x["text_end"]
        anchor=x["first_fd_anchor"]
        total=x["quill_length"]
        distance=x["gap_before_anchor_bytes"]
        nonzero=x["tail2_nonzero_count"]
        zeros=x["trailing_zero_bytes"]
        desc=x["descriptor_payload_overlaps_tail2"]
        assert all(isinstance(x[k],int) and x[k]>=0 for k in (
            "quill_length","descriptor_count","story_count","text_start","text_end",
            "first_fd_anchor","gap_before_anchor_bytes","tail2_nonzero_count",
            "trailing_zero_bytes","descriptor_payload_overlaps_tail2"))
        assert 0<=a<=end<=anchor<=total
        assert anchor % 512 == 0 and anchor >= 2
        assert distance == anchor-end
        assert 0<=zeros<=distance and 0<=nonzero<=2
        assert isinstance(x["descriptor_metadata_inside_move_window"],bool)
        assert x["predicted_plus_one_gate"] in PRED
        names=x["tail2_descriptor_tags"]
        assert isinstance(names,list) and len(names)==len(set(names))
        assert names==sorted(names) and set(names)<=TAG
        if desc:
            assert names
        else:
            assert not names
        predicted = ("INSUFFICIENT_PRE_ANCHOR_SPACE" if distance<2 else
                     "NONZERO_UNKNOWN_ANCHOR_TAIL" if nonzero else
                     "NAMED_DESCRIPTOR_PAYLOAD_OVERLAP" if desc else
                     "TAIL_TWO_BYTES_CLEAR_ONLY")
        assert x["predicted_plus_one_gate"]==predicted
        guard[predicted]+=1
        label=x["expected_exp003_label"]
        owners[label]["named_payload" if desc else "no_named_payload"]+=1
        owners[label]["tail_nonzero" if nonzero else "tail_zero"]+=1
        gap[label].append(distance)
        if label=="NO_ELIGIBLE_STORY":
            continue
        observed=label=="GROWTH_BLOCKED"
        positive=predicted=="NONZERO_UNKNOWN_ANCHOR_TAIL"
        key=("TP" if observed and positive else
             "FN" if observed else
             "FP" if positive else "TN")
        confusion[key]+=1
    summary=r["summary"]
    assert set(summary)=={"corpus_sources","evaluated_source_count",
                           "inspected_quill_count","expected_growth_blocked_sources",
                           "expected_no_eligible_sources",
                           "confusion_known_eligible_sources","static_guard_classes",
                           "tail_ownership_by_prior_label","gap_bytes_by_prior_label"}
    assert summary["corpus_sources"]==summary["evaluated_source_count"]==26
    assert summary["inspected_quill_count"]==inspected
    assert summary["expected_growth_blocked_sources"]==10
    assert summary["expected_no_eligible_sources"]==3
    assert summary["confusion_known_eligible_sources"]==dict(sorted(confusion.items()))
    assert summary["static_guard_classes"]==dict(sorted(guard.items()))
    assert summary["tail_ownership_by_prior_label"]=={
        k:dict(sorted(v.items())) for k,v in sorted(owners.items())}
    assert summary["gap_bytes_by_prior_label"]=={
        k:{"count":len(v),"min":min(v),"max":max(v)}
        for k,v in sorted(gap.items())}
    assert "UNRESOLVED_GROWTH_BLOCKED" not in confusion
    print("EXP-004: public source-safe 26-item structural correlation report validated")

if __name__=="__main__":
    assert len(sys.argv)==2
    check(sys.argv[1])
