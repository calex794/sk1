#!/usr/bin/env python3
"""Source-safe independent numeric verifier for PUB-T-976 original Quill study."""
from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
import json
import re
import sys

SHA=re.compile(r"^[0-9a-f]{64}$")
STATES={"ANALYZED","ANALYSIS_BLOCKED","NO_QUILL_STREAM_OR_CFB_ERROR",
        "QUILL_CATALOG_BLOCKED","TEXT_DESCRIPTOR_NOT_UNIQUE",
        "TEXT_SPAN_INVALID","FDPP_STRUCTURE_BLOCKED",
        "FDPC_STRUCTURE_BLOCKED","STORY_SPAN_INVALID"}
SOURCE_STATUSES={"NOT_EVALUATED","SHA_VERIFIED","PROBE_UNAVAILABLE"}
REASONS={"NOT_STARTED","OK","HTTP_UNAVAILABLE","UNSAFE_REDIRECT",
         "REQUEST_TIMEOUT","FETCH_ERROR","SHA_OR_SIZE_DRIFT",
         "NON_CFB_INPUT","PROCESS_OR_TIMEOUT","PROCESS_FAILED",
         "INVALID_RECEIPT"}
NUM_FIELDS={
 "quill_bytes","text_offset","text_bytes","story_count",
 "nonempty_stories","zero_length_stories","story_terminal_cr",
 "story_missing_terminal_cr","story_catalog_byte_mismatches",
 "story_gap_bytes","story_overlap_bytes","raw_cr_count",
 "story_terminal_cr_count","story_internal_cr_count",
 "raw_cr_not_owned_by_stories","fdpp_page_count","fdpp_entry_count",
 "fdpp_unique","fdpp_duplicate_entries","fdpc_page_count",
 "fdpc_entry_count","fdpc_unique","fdpc_duplicate_entries",
 "fdpp_missing_cr_ends","fdpp_extraneous_entries"}
BOOL_FIELDS={"story_partition_exact","fdpp_equal_raw_cr_multiset"}
SAMPLE_FIELDS={"story_terminal_missing_ordinal_sample",
               "fdpp_missing_offset_sample","fdpp_extraneous_offset_sample"}
CR_CLASSES=("both","start_only","end_only","neither")
CR_FIELDS={"fdpc_"+t+"_"+s for t in ("terminal","internal") for s in CR_CLASSES}
STATS=NUM_FIELDS|BOOL_FIELDS|SAMPLE_FIELDS|CR_FIELDS
SUM_COUNTS={
 "quill_bytes","text_bytes","story_count","nonempty_stories","zero_length_stories",
 "story_terminal_cr","story_missing_terminal_cr","story_catalog_byte_mismatches",
 "raw_cr_count","story_terminal_cr_count","story_internal_cr_count",
 "raw_cr_not_owned_by_stories","fdpp_page_count","fdpp_entry_count",
 "fdpp_unique","fdpp_duplicate_entries","fdpc_page_count","fdpc_entry_count",
 "fdpc_unique","fdpc_duplicate_entries","fdpp_missing_cr_ends",
 "fdpp_extraneous_entries","story_gap_bytes","story_overlap_bytes"
}
SUMMARY_FIELDS={"attempted_sources","sha_verified_sources","parsed_sources",
                "source_states","source_reasons","per_host_states",
                "totals","fdpc_terminal_cr_classes","fdpc_internal_cr_classes",
                "counterexamples"}
PROOF_FIELDS={"schema","source_sha256","source_bytes","status","stats",
              "quill_writer_invocations","native_publisher_acceptance",
              "product_pub_download_authorized","source_immutable"}

def validate(folder:Path):
    assert {p.name for p in folder.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((folder/"plan.json").read_text())
    rec=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    assert set(plan)=={"schema","rar2_pin","lalamu_pin","t971_selection_sha",
        "selected_sha256","selected_file_bytes","selected_file_count",
        "host_count","historical_excluded_sha","observation","reader_only",
        "quill_writer_invocations","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-976.plan.v1"
    assert plan["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["t971_selection_sha"]=="cd38c8d6a545737f9f99821076340505db5e149c"
    assert plan["selected_file_count"]==47 and plan["selected_file_bytes"]==28191744
    assert plan["host_count"]==37 and plan["historical_excluded_sha"]==178
    assert plan["reader_only"] is True and plan["quill_writer_invocations"]==0
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["observation"]==(
      "UTF16 CR end offset vs source FDPP values; FDPC CR-bracketing; Story text partition")
    assert type(plan["selected_sha256"]) is list and len(plan["selected_sha256"])==47
    assert all(isinstance(x,str) and SHA.fullmatch(x) for x in plan["selected_sha256"])
    assert len(set(plan["selected_sha256"]))==47
    assert isinstance(rec,list) and len(rec)==47
    assert [x["source_sha256"] for x in rec]==plan["selected_sha256"]
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
      "quill_writer_invocations","product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-976.report.v1"
    assert report["rar2_pin"]==plan["rar2_pin"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["quill_writer_invocations"]==0
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==rec
    seen_host=Counter();states=Counter();reasons=Counter()
    host_counts=defaultdict(Counter)
    sum_num=Counter();term=Counter();inside=Counter();issues=[]
    verified=parsed=0
    for row in rec:
        assert set(row)=={"source_sha256","host","expected_source_bytes",
                         "status","reason","probe"}
        assert row["status"] in SOURCE_STATUSES and row["reason"] in REASONS
        assert isinstance(row["host"],str) and bool(re.fullmatch(r"[a-z0-9.-]+",row["host"]))
        assert type(row["expected_source_bytes"]) is int and 0<row["expected_source_bytes"]<=2500000
        seen_host[row["host"]]+=1
        status=row["status"];probe=row["probe"]
        if status=="SHA_VERIFIED":
            verified+=1
            assert row["reason"]=="OK" and isinstance(probe,dict)
        else:
            assert probe is None
        if probe is not None:
            assert set(probe)==PROOF_FIELDS
            assert probe["schema"]=="sk1.pub-t-976.source.v1"
            assert probe["source_sha256"]==row["source_sha256"]
            assert probe["source_bytes"]==row["expected_source_bytes"]
            assert probe["quill_writer_invocations"]==0
            assert probe["native_publisher_acceptance"]=="NOT_EVALUATED"
            assert probe["product_pub_download_authorized"] is False
            assert probe["source_immutable"] is True
            assert probe["status"] in STATES
            status=probe["status"]
            if status!="ANALYZED":
                assert probe["stats"] is None
            else:
                parsed+=1
                x=probe["stats"]
                assert isinstance(x,dict) and set(x)==STATS,(set(x)-STATS,STATS-set(x))
                assert all(type(x[k]) is int and 0<=x[k]<100_000_000 for k in NUM_FIELDS|CR_FIELDS)
                assert all(type(x[k]) is bool for k in BOOL_FIELDS)
                assert all(isinstance(x[k],list) and len(x[k])<=30 for k in SAMPLE_FIELDS)
                assert all(all(type(y) is int and 0<=y<100_000_000 for y in x[k]) for k in SAMPLE_FIELDS)
                assert all(x[k]>=1 for k in ("fdpp_page_count","fdpc_page_count"))
                assert x["quill_bytes"]>=x["text_offset"]+x["text_bytes"]
                assert x["text_bytes"]%2==0
                assert x["nonempty_stories"]+x["zero_length_stories"]==x["story_count"]
                assert x["story_terminal_cr"]+x["story_missing_terminal_cr"]==x["nonempty_stories"]
                assert x["fdpp_unique"]+x["fdpp_duplicate_entries"]==x["fdpp_entry_count"]
                assert x["fdpc_unique"]+x["fdpc_duplicate_entries"]==x["fdpc_entry_count"]
                assert x["story_partition_exact"]==(
                    x["story_gap_bytes"]==0 and x["story_overlap_bytes"]==0)
                assert x["fdpp_equal_raw_cr_multiset"]==(
                    x["fdpp_missing_cr_ends"]==0 and x["fdpp_extraneous_entries"]==0)
                assert (sum(x["fdpc_terminal_"+k] for k in CR_CLASSES)
                        ==x["story_terminal_cr_count"])
                assert (sum(x["fdpc_internal_"+k] for k in CR_CLASSES)
                        ==x["story_internal_cr_count"])
                assert x["story_terminal_cr_count"]==x["story_terminal_cr"]
                assert len(x["story_terminal_missing_ordinal_sample"])<=x["story_missing_terminal_cr"]
                assert len(x["fdpp_missing_offset_sample"])<=x["fdpp_missing_cr_ends"]
                assert len(x["fdpp_extraneous_offset_sample"])<=x["fdpp_extraneous_entries"]
                assert all(x["text_offset"]<=v<=x["text_offset"]+x["text_bytes"]
                    and (v-x["text_offset"])%2==0
                    for k in ("fdpp_missing_offset_sample","fdpp_extraneous_offset_sample")
                    for v in x[k])
                if x["story_partition_exact"]:
                    assert x["raw_cr_not_owned_by_stories"]==0
                    assert x["raw_cr_count"]==(
                        x["story_terminal_cr_count"]+x["story_internal_cr_count"])
                for k in SUM_COUNTS:sum_num[k]+=x[k]
                if x["fdpp_equal_raw_cr_multiset"]:sum_num["fdpp_multiset_equal_files"]+=1
                if x["story_partition_exact"]:sum_num["story_partition_exact_files"]+=1
                if x["story_catalog_byte_mismatches"]==0:
                    sum_num["raw_story_catalog_agreement_files"]+=1
                for k in CR_CLASSES:
                    term[k]+=x["fdpc_terminal_"+k]
                    inside[k]+=x["fdpc_internal_"+k]
                if (not x["fdpp_equal_raw_cr_multiset"]
                  or not x["story_partition_exact"]
                  or x["story_missing_terminal_cr"]>0
                  or x["story_catalog_byte_mismatches"]>0):
                    issues.append({
                       "source_sha256":row["source_sha256"],"host":row["host"],
                       "missing_fdpp_cr_ends":x["fdpp_missing_cr_ends"],
                       "unexpected_fdpp_entries":x["fdpp_extraneous_entries"],
                       "missing_fdpp_offsets":x["fdpp_missing_offset_sample"],
                       "unexpected_fdpp_offsets":x["fdpp_extraneous_offset_sample"],
                       "missing_terminal_cr_count":x["story_missing_terminal_cr"],
                       "story_gap_bytes":x["story_gap_bytes"],
                       "story_overlap_bytes":x["story_overlap_bytes"],
                       "story_catalog_byte_mismatches":x["story_catalog_byte_mismatches"]})
        states[status]+=1;reasons[row["reason"]]+=1;host_counts[row["host"]][status]+=1
    assert len(seen_host)==37 and sum(seen_host.values())==47
    assert sum(x["expected_source_bytes"] for x in rec)==plan["selected_file_bytes"]
    expected={"attempted_sources":47,"sha_verified_sources":verified,
        "parsed_sources":parsed,
        "source_states":dict(sorted(states.items())),
        "source_reasons":dict(sorted(reasons.items())),
        "per_host_states":{k:dict(sorted(v.items())) for k,v in sorted(host_counts.items())},
        "totals":dict(sorted(sum_num.items())),
        "fdpc_terminal_cr_classes":dict(sorted(term.items())),
        "fdpc_internal_cr_classes":dict(sorted(inside.items())),
        "counterexamples":issues}
    assert set(report["summary"])==SUMMARY_FIELDS
    assert report["summary"]==expected, [
       k for k in expected if report["summary"].get(k)!=expected[k]]
    print("PUB-T-976 SOURCE-SAFE PASS",parsed,"Quill PUB",
          expected["totals"].get("raw_cr_count",0),"CR",
          expected["totals"].get("fdpp_multiset_equal_files",0),
          "exact-multiset files; exceptions",len(issues))
    return True

if __name__=="__main__":validate(Path(sys.argv[1]))
