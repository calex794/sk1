#!/usr/bin/env python3
"""PUB-T-960 strict source-safe receipt, baseline and non-duplication validator."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
SOURCE_BASE={"source_sha256","source_type","source_bytes","status","reason"}
SOURCE_FULL=SOURCE_BASE|{"eligible_story_count","single_controls","pairs"}
CONTROL={"story_ordinal","syid","offset_utf16","single_delete"}
PAIR={"a_story_ordinal","b_story_ordinal","a_syid","b_syid",
      "a_offset_utf16","b_offset_utf16",
      "a_then_b_second","b_then_a_second",
      "a_then_b_final_stories_match","b_then_a_final_stories_match",
      "both_final_byte_equal"}
PASS_FIELDS={"status","candidate_sha256","reader_semantic_reopen",
             "syid_siblings_preserved","project_replay_byte_equal",
             "source_immutable"}
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}

def require_step(step:dict):
    assert isinstance(step,dict) and step.get("status") in STEPS
    if step["status"]=="HOSTED_PASS":
        assert set(step)==PASS_FIELDS
        assert SHA.fullmatch(step["candidate_sha256"])
        for attr in PASS_FIELDS-{"status","candidate_sha256"}:
            assert step[attr] is True
    elif step["status"]=="WRITER_BLOCKED":
        assert set(step)=={"status","writer_code"}
        assert CODE.fullmatch(step["writer_code"])
    else:
        assert set(step)=={"status"}

def check(path:Path):
    x=json.loads(path.read_text(encoding="utf-8"))
    assert set(x)=={"schema","rar2_pin","source_manifest",
                   "native_publisher_acceptance",
                   "product_pub_download_authorized","summary","records"}
    assert x["schema"]=="sk1.pub-t-960.report.v1"
    assert x["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert x["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert x["product_pub_download_authorized"] is False

    spec=importlib.util.spec_from_file_location("sk1_pub960_runner",HERE/"run.py")
    assert spec and spec.loader
    runner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan=json.loads((path.parent/"plan.json").read_text(encoding="utf-8"))
    assert set(plan)=={"schema","rar2_pin","source_manifest","prior_evidence",
                      "sample_origin","source_sha256","expected_story_controls",
                      "expected_cross_story_pairs","expected_ordered_chains",
                      "unit_of_independence","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-960.plan.v1"
    assert plan["rar2_pin"]==runner.PIN
    assert plan["source_manifest"]==runner.source.MANIFEST_URL
    assert plan["source_sha256"]==list(runner.SOURCE_SHA256)
    assert plan["expected_story_controls"]==32
    assert plan["expected_cross_story_pairs"]==31
    assert plan["expected_ordered_chains"]==62
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["unit_of_independence"]=="source_sha256, not Story/ordered chain"
    assert x["source_manifest"]==plan["source_manifest"]
    records=x["records"]
    assert isinstance(records,list) and len(records)==11
    assert [r["source_sha256"] for r in records]==list(runner.SOURCE_SHA256)
    n_pairs=n_controls=0
    for source in records:
        assert set(source)==SOURCE_FULL
        assert SHA.fullmatch(source["source_sha256"])
        assert source["source_type"] in {"github","institutional-web"}
        assert type(source["source_bytes"]) is int and 0<source["source_bytes"]<=12*1024*1024
        assert source["status"]=="EVALUATED"
        assert source["reason"]=="EVALUATED"
        controls=source["single_controls"]
        expected_count=runner.EXPECTED_STORY_ORDINAL_COUNTS[source["source_sha256"]]
        assert source["eligible_story_count"]==expected_count
        assert isinstance(controls,list) and len(controls)==expected_count
        n_controls+=len(controls)
        seen_syids=set()
        for ordinal,c in enumerate(controls):
            assert set(c)==CONTROL
            assert c["story_ordinal"]==ordinal
            assert type(c["syid"]) is int and 0<=c["syid"]<2**32
            assert c["syid"] not in seen_syids
            seen_syids.add(c["syid"])
            assert type(c["offset_utf16"]) is int and c["offset_utf16"]>=0
            require_step(c["single_delete"])
            assert c["single_delete"]["status"]=="HOSTED_PASS"

        pairs=source["pairs"]
        expected_pairs=expected_count*(expected_count-1)//2
        assert isinstance(pairs,list) and len(pairs)==expected_pairs
        n_pairs+=len(pairs)
        encountered=set()
        for pair in pairs:
            assert set(pair)==PAIR
            a,b=pair["a_story_ordinal"],pair["b_story_ordinal"]
            assert type(a) is int and type(b) is int and 0<=a<b<expected_count
            assert (a,b) not in encountered
            encountered.add((a,b))
            assert pair["a_syid"]==controls[a]["syid"]
            assert pair["b_syid"]==controls[b]["syid"]
            assert pair["a_syid"]!=pair["b_syid"]
            assert pair["a_offset_utf16"]==controls[a]["offset_utf16"]
            assert pair["b_offset_utf16"]==controls[b]["offset_utf16"]
            for arm,key in [("a_then_b_second","a_then_b_final_stories_match"),
                            ("b_then_a_second","b_then_a_final_stories_match")]:
                require_step(pair[arm])
                if pair[arm]["status"]=="HOSTED_PASS":
                    assert type(pair[key]) is bool
                else:
                    assert pair[key] is None
            if (pair["a_then_b_second"]["status"]==
                pair["b_then_a_second"]["status"]=="HOSTED_PASS"):
                assert type(pair["both_final_byte_equal"]) is bool
            else:
                assert pair["both_final_byte_equal"] is None
        assert len(encountered)==expected_pairs

    assert n_controls==32
    assert n_pairs==31
    computed=runner.summarize(records)
    assert x["summary"]==computed
    assert computed["predeclared_sources"]==11
    assert computed["source_status"]=={"EVALUATED":11}
    assert computed["ordered_chains"]==62
    assert sum(computed["A_then_B_second_outcomes"].values())==31
    assert sum(computed["B_then_A_second_outcomes"].values())==31
    print("PUB-T-960: 11 public SHA / 32 distinct Story controls / 31 cross-Story pairs / 62 validated chain observations PASS")

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
