#!/usr/bin/env python3
"""PUB-T-964: strict source-safe receipt gate and unique 31×2×2 denominator."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import sys
HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
SOURCE={"source_sha256","source_type","source_bytes","status","reason",
    "eligible_story_count","single_controls","pairs"}
CONTROL={"story_ordinal","syid","offset_utf16","single_insert","single_delete"}
PAIR={"insert_story_ordinal","delete_story_ordinal","insert_story_syid",
    "delete_story_syid","insert_offset_utf16","delete_offset_utf16",
    "insert_then_delete_second","delete_then_insert_second",
    "insert_then_delete_final_stories_match",
    "delete_then_insert_final_stories_match","both_final_byte_equal"}
PASS_FIELDS={"status","candidate_sha256","reader_semantic_reopen",
    "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
STEPS={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
       "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
       "CANONICAL_EDIT_REJECTED","WRITER_HASH_OR_NO_CHANGE",
       "READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE",
       "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
       "REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
       "PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}

def step_check(x):
    assert isinstance(x,dict) and x.get("status") in STEPS
    if x["status"]=="HOSTED_PASS":
        assert set(x)==PASS_FIELDS
        assert isinstance(x["candidate_sha256"],str) and SHA.fullmatch(x["candidate_sha256"])
        for key in PASS_FIELDS-{"status","candidate_sha256"}:
            assert x[key] is True,key
    elif x["status"]=="WRITER_BLOCKED":
        assert set(x)=={"status","writer_code"}
        assert isinstance(x["writer_code"],str) and CODE.fullmatch(x["writer_code"])
    else:
        assert set(x)=={"status"}

def check(out:Path):
    spec=importlib.util.spec_from_file_location("sk1_t964_runner",HERE/"run.py")
    assert spec and spec.loader
    runner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan=json.loads((out/"plan.json").read_text(encoding="utf8"))
    records=json.loads((out/"records.json").read_text(encoding="utf8"))
    report=json.loads((out/"report.json").read_text(encoding="utf8"))
    assert set(plan)=={"schema","rar2_pin","source_manifest",
        "prior_960_scientific_sha","prior_960_evidence_zip_sha256",
        "prior_956_scientific_sha","prior_956_evidence_zip_sha256",
        "source_sha256","single_slot","source_admission",
        "expected_attempted_story_controls","expected_both_pass_story_controls",
        "expected_tokn_blocked_story_controls","expected_unordered_story_pairs",
        "expected_mixed_sign_assignments","expected_ordered_chains",
        "unit_of_independence","native_publisher_acceptance",
        "product_pub_download_authorized"}
    assert plan["schema"]=="sk1.pub-t-964.plan.v1"
    assert plan["rar2_pin"]==runner.PIN
    assert plan["source_manifest"]==runner.source.MANIFEST_URL
    assert plan["prior_960_scientific_sha"]==runner.PREV_960_SHA
    assert plan["prior_960_evidence_zip_sha256"]==runner.PREV_960_ZIP
    assert plan["prior_956_scientific_sha"]==runner.PREV_956_SHA
    assert plan["prior_956_evidence_zip_sha256"]==runner.PREV_956_ZIP
    assert plan["source_sha256"]==list(runner.SOURCE_SHA256)
    assert plan["single_slot"]=="second ASCII alphanumeric"
    assert "both standalone" in plan["source_admission"]
    assert plan["expected_attempted_story_controls"]==33
    assert plan["expected_both_pass_story_controls"]==32
    assert plan["expected_tokn_blocked_story_controls"]==1
    assert plan["expected_unordered_story_pairs"]==31
    assert plan["expected_mixed_sign_assignments"]==62
    assert plan["expected_ordered_chains"]==124
    assert plan["unit_of_independence"]=="source_sha256, not Story/pair/chain"
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["product_pub_download_authorized"] is False
    assert set(report)=={"schema","rar2_pin","source_manifest",
        "native_publisher_acceptance","product_pub_download_authorized",
        "summary","records"}
    assert report["schema"]=="sk1.pub-t-964.report.v1"
    assert report["rar2_pin"]==runner.PIN
    assert report["source_manifest"]==plan["source_manifest"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==records
    assert isinstance(records,list) and len(records)==11
    assert [r["source_sha256"] for r in records]==list(runner.SOURCE_SHA256)
    totals={"attempted_controls":0,"both_controls":0,"excluded":0,"pairs":0,
        "ID":0,"DI":0}
    for row in records:
        assert type(row) is dict and set(row)==SOURCE
        assert SHA.fullmatch(row["source_sha256"])
        assert row["source_type"] in {"github","institutional-web"}
        assert type(row["source_bytes"]) is int and 0<row["source_bytes"]<=12*1024*1024
        assert row["status"]=="EVALUATED" and row["reason"]=="EVALUATED"
        assert row["eligible_story_count"]==3
        cs=row["single_controls"]
        assert type(cs) is list and len(cs)==3
        syids=set();allowed=[]
        for ordinal,c in enumerate(cs):
            assert type(c) is dict and set(c)==CONTROL
            assert c["story_ordinal"]==ordinal
            assert type(c["syid"]) is int and 0<=c["syid"]<2**32
            assert c["syid"] not in syids;syids.add(c["syid"])
            assert type(c["offset_utf16"]) is int and c["offset_utf16"]>=0
            for op in ("single_insert","single_delete"):step_check(c[op])
            totals["attempted_controls"]+=1
            if c["single_insert"]["status"]==c["single_delete"]["status"]=="HOSTED_PASS":
                allowed.append(ordinal);totals["both_controls"]+=1
            else:
                assert row["source_sha256"]==runner.SOURCE_SHA256[-1]
                assert ordinal==2
                assert c["single_insert"]==c["single_delete"]=={
                    "status":"WRITER_BLOCKED","writer_code":"quill_token_layer"}
                totals["excluded"]+=1
        assert len(allowed)==runner.EXPECTED_ACCEPTED[row["source_sha256"]]
        pair_rows=row["pairs"]
        expected={(a,b) for a in allowed for b in allowed if a!=b}
        assert type(pair_rows) is list and len(pair_rows)==len(expected)
        seen=set()
        for pr in pair_rows:
            assert type(pr) is dict and set(pr)==PAIR
            ai,bi=pr["insert_story_ordinal"],pr["delete_story_ordinal"]
            assert type(ai) is int and type(bi) is int
            assert (ai,bi) in expected and (ai,bi) not in seen
            seen.add((ai,bi));totals["pairs"]+=1
            assert pr["insert_story_syid"]==cs[ai]["syid"]
            assert pr["delete_story_syid"]==cs[bi]["syid"]
            assert pr["insert_story_syid"]!=pr["delete_story_syid"]
            assert pr["insert_offset_utf16"]==cs[ai]["offset_utf16"]
            assert pr["delete_offset_utf16"]==cs[bi]["offset_utf16"]
            for op,outcome,denominator in [
                ("insert_then_delete_second","insert_then_delete_final_stories_match","ID"),
                ("delete_then_insert_second","delete_then_insert_final_stories_match","DI")]:
                step_check(pr[op]);totals[denominator]+=1
                if pr[op]["status"]=="HOSTED_PASS":
                    assert type(pr[outcome]) is bool
                else:
                    assert pr[outcome] is None
            if (pr["insert_then_delete_second"]["status"]==
                pr["delete_then_insert_second"]["status"]=="HOSTED_PASS"):
                assert type(pr["both_final_byte_equal"]) is bool
            else:
                assert pr["both_final_byte_equal"] is None
        assert seen==expected
    assert totals=={
        "attempted_controls":33,"both_controls":32,"excluded":1,
        "pairs":62,"ID":62,"DI":62}
    s=runner.summarize(records)
    assert report["summary"]==s
    assert s["predeclared_sources"]==11
    assert s["source_status"]=={"EVALUATED":11}
    assert s["attempted_single_story_controls"]==33
    assert s["both_single_operations_pass_controls"]==32
    assert s["excluded_single_story_results"]=={"quill_token_layer":2}
    assert s["unordered_story_pairs"]==31 and s["mixed_sign_assignments"]==62
    assert s["ordered_chains"]==124
    assert sum(s["insert_then_delete_second_outcomes"].values())==62
    assert sum(s["delete_then_insert_second_outcomes"].values())==62
    print("SK1 PUB-T-964 VERIFIED: 11 SHA / 33 attempted ordinary Story / 32 two-way single PASS / 31 pairs / 62 orientations / 124 ordered chains")
    print(json.dumps({"ID":s["insert_then_delete_second_outcomes"],
        "DI":s["delete_then_insert_second_outcomes"],
        "byte_equal":s["cross_order_final_byte_equal"],
        "negative_witnesses":len(s["negative_or_noncommuting_witnesses"])},sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
