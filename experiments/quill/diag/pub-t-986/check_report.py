#!/usr/bin/env python3
"""Source-safe independent numeric verifier for PUB-T-986 original Quill study."""
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
        "FDPC_STRUCTURE_BLOCKED","STORY_SPAN_INVALID","FDPC_RAW_STYLE_BLOCKED"}
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
RAW_KEYS={
 "records","unique_bodies","comparable_pairs","duplicate_end_pairs",
 "adjacent_alias","adjacent_equal_distinct","adjacent_different",
 "within_page","cross_page","equal_within_page","equal_cross_page",
 "at_cr_any","equal_at_cr_any","outside_cr","equal_outside_cr",
 "terminal_cr_start","equal_terminal_cr_start",
 "terminal_cr_end","equal_terminal_cr_end",
 "internal_cr_start","equal_internal_cr_start",
 "internal_cr_end","equal_internal_cr_end",
 "same_story_end","equal_same_story_end"
}

BTEC_METRIC_KEYS={
 "fdpc_pages","fdpc_records","btec_descriptors","btec_rows",
 "nonzero_flags_descriptors","zero_sentinel_rows",
 "targets_found","targets_missing","pages_one_target",
 "pages_zero_targets","pages_multiple_targets",
 "row_end_matches_page","row_end_mismatches_page",
 "cross_page_seams","cross_page_linked","cross_page_distinct_rows",
 "cross_page_boundary_join","raw_equal_seams","equal_linked",
 "equal_distinct_rows","equal_boundary_join",
 "equal_same_btec_descriptor","equal_different_btec_descriptor"
}
WITNESS_KEYS={"boundary_absolute","before_fdpc_page","after_fdpc_page",
  "before_fdpc_target","after_fdpc_target",
  "before_btec_row","after_btec_row","fully_linked",
  "distinct_target_rows","logical_boundary_join"}
JOIN_STATES={"ABSENT","STRUCTURE_BLOCKED","COMPLETE","PARTIAL"}

STATS=NUM_FIELDS|BOOL_FIELDS|SAMPLE_FIELDS|CR_FIELDS|{"fdpc_raw_style","btec_link"}
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
                "counterexamples","fdpc_raw_style_totals",
                "btec_join_statuses","btec_link_totals","equal_witnesses",
                "baseline_checked","baseline_not_reobserved","baseline_mismatch_sha256"}
PROOF_FIELDS={"schema","source_sha256","source_bytes","status","stats",
              "quill_writer_invocations","native_publisher_acceptance",
              "product_pub_download_authorized","source_immutable"}

def validate(folder:Path):
    assert {p.name for p in folder.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((folder/"plan.json").read_text())
    rec=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    assert set(plan)=={"schema","rar2_pin","lalamu_pin","t971_selection_sha","baseline_t976_zip_sha256","baseline_t985_zip_sha256",
        "selected_sha256","selected_file_bytes","selected_file_count",
        "host_count","historical_excluded_sha","observation","reader_only",
        "quill_writer_invocations","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-986.plan.v1"
    assert plan["baseline_t976_zip_sha256"]=="14e5c0c04e2ab220f692de8231e252fc34c5af9677662443b870e03f6abf0553"
    assert plan["baseline_t985_zip_sha256"]=="2b0dcbeb60ae4d5dbe05648e17231be36858b73a92c75c1eae27825e21eca113"
    assert plan["rar2_pin"]=="703808408fd919e564a90cdc236e81db3c04af8b"
    assert plan["lalamu_pin"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
    assert plan["t971_selection_sha"]=="cd38c8d6a545737f9f99821076340505db5e149c"
    assert plan["selected_file_count"]==47 and plan["selected_file_bytes"]==28191744
    assert plan["host_count"]==37 and plan["historical_excluded_sha"]==178
    assert plan["reader_only"] is True and plan["quill_writer_invocations"]==0
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert plan["observation"]==(
      "BTEC type-4 PLC FDPC physical reference join at raw-style equal page seams; T985 counts used as fixed baseline")
    assert type(plan["selected_sha256"]) is list and len(plan["selected_sha256"])==47
    assert all(isinstance(x,str) and SHA.fullmatch(x) for x in plan["selected_sha256"])
    assert len(set(plan["selected_sha256"]))==47
    assert isinstance(rec,list) and len(rec)==47
    assert [x["source_sha256"] for x in rec]==plan["selected_sha256"]
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
      "quill_writer_invocations","product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-986.report.v1"
    assert report["rar2_pin"]==plan["rar2_pin"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["quill_writer_invocations"]==0
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==rec
    seen_host=Counter();states=Counter();reasons=Counter()
    host_counts=defaultdict(Counter)
    sum_num=Counter();term=Counter();inside=Counter();issues=[]
    raw_totals=Counter()
    join_states=Counter()
    btec_totals=Counter()
    witness_total=0
    old=json.loads((Path(__file__).resolve().parent/"baseline_t985.json").read_text())
    assert set(old)=={"schema","source_scientific_sha","source_zip_sha256",
      "prior_analyzed_sources","prior_style_records","prior_fdpc_pages",
      "prior_cross_page","prior_equal_cross_page","prior_rows"}
    assert old["schema"]=="sk1.pub-t-986.old-cohort.v1"
    assert old["source_scientific_sha"]=="f07486b5362203e51d77b20b8796b1695050ee5f"
    assert old["source_zip_sha256"]==plan["baseline_t985_zip_sha256"]
    assert len(old["prior_rows"])==old["prior_analyzed_sources"]==31
    assert sum(z[1] for z in old["prior_rows"])==old["prior_fdpc_pages"]==798
    assert sum(z[2] for z in old["prior_rows"])==old["prior_style_records"]==5406
    assert sum(z[3] for z in old["prior_rows"])==old["prior_cross_page"]==767
    assert sum(z[4] for z in old["prior_rows"])==old["prior_equal_cross_page"]==16
    prior={}
    for entry in old["prior_rows"]:
        assert isinstance(entry,list) and len(entry)==5
        sha,*nums=entry
        assert isinstance(sha,str) and SHA.fullmatch(sha) and sha not in prior
        assert all(type(n) is int and 0<=n<1000000 for n in nums)
        prior[sha]=nums
    assert set(prior)<set(plan["selected_sha256"])
    old_observed=0
    old_missing=0
    old_drift=[]
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
            assert probe["schema"]=="sk1.pub-t-986.source.v1"
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
                raw=x["fdpc_raw_style"]
                assert isinstance(raw,dict) and set(raw)==RAW_KEYS
                assert all(type(raw[k]) is int and 0<=raw[k]<=100_000_000 for k in RAW_KEYS)
                assert raw["records"]==x["fdpc_entry_count"]
                assert raw["unique_bodies"]<=raw["records"]
                assert raw["comparable_pairs"]+raw["duplicate_end_pairs"]==max(0,raw["records"]-1)
                assert raw["adjacent_alias"]+raw["adjacent_equal_distinct"]+raw["adjacent_different"]==raw["comparable_pairs"]
                assert raw["within_page"]+raw["cross_page"]==raw["comparable_pairs"]
                assert raw["equal_within_page"]+raw["equal_cross_page"]==raw["adjacent_alias"]+raw["adjacent_equal_distinct"]
                assert raw["at_cr_any"]+raw["outside_cr"]==raw["comparable_pairs"]
                assert raw["equal_at_cr_any"]+raw["equal_outside_cr"]==raw["adjacent_alias"]+raw["adjacent_equal_distinct"]
                for tag in ("terminal_cr_start","terminal_cr_end","internal_cr_start","internal_cr_end","same_story_end"):
                    assert raw["equal_"+tag]<=raw[tag]<=raw["comparable_pairs"]
                raw_totals.update(raw)

                joined=x["btec_link"]
                assert isinstance(joined,dict) and set(joined)=={"status","metrics","equal_witnesses"}
                assert joined["status"] in JOIN_STATES
                assert isinstance(joined["equal_witnesses"],list)
                join_states[joined["status"]]+=1
                metrics=joined["metrics"]
                if joined["status"] in {"ABSENT","STRUCTURE_BLOCKED"}:
                    assert metrics is None and joined["equal_witnesses"]==[]
                else:
                    assert isinstance(metrics,dict) and set(metrics)==BTEC_METRIC_KEYS
                    assert all(type(metrics[k]) is int and 0<=metrics[k]<=100_000_000 for k in BTEC_METRIC_KEYS)
                    assert metrics["fdpc_pages"]==x["fdpc_page_count"]
                    assert metrics["fdpc_records"]==x["fdpc_entry_count"]
                    assert metrics["targets_found"]+metrics["targets_missing"]==metrics["btec_rows"]
                    assert metrics["row_end_matches_page"]+metrics["row_end_mismatches_page"]==metrics["targets_found"]
                    assert (metrics["pages_one_target"]+metrics["pages_zero_targets"]+
                            metrics["pages_multiple_targets"]==metrics["fdpc_pages"])
                    assert metrics["cross_page_seams"]==raw["cross_page"]
                    assert metrics["raw_equal_seams"]==raw["equal_cross_page"]
                    assert metrics["equal_linked"]<=metrics["raw_equal_seams"]
                    assert metrics["equal_distinct_rows"]<=metrics["equal_linked"]
                    assert metrics["equal_boundary_join"]<=metrics["equal_linked"]
                    assert metrics["equal_same_btec_descriptor"]+metrics["equal_different_btec_descriptor"]==metrics["equal_linked"]
                    assert metrics["cross_page_boundary_join"]<=metrics["cross_page_linked"]<=metrics["cross_page_seams"]
                    assert metrics["cross_page_distinct_rows"]<=metrics["cross_page_linked"]
                    assert metrics["nonzero_flags_descriptors"]<=metrics["btec_descriptors"]
                    assert metrics["zero_sentinel_rows"]<=metrics["btec_rows"]+metrics["btec_descriptors"]
                    assert len(joined["equal_witnesses"])==metrics["raw_equal_seams"]<=100000
                    linked=distinct=boundary=0
                    for w in joined["equal_witnesses"]:
                        assert isinstance(w,dict) and set(w)==WITNESS_KEYS
                        assert all(type(w[k]) is int and 0<=w[k]<100_000_000 for k in (
                            "boundary_absolute","before_fdpc_page","after_fdpc_page",
                            "before_fdpc_target","after_fdpc_target"))
                        assert w["before_fdpc_page"]!=w["after_fdpc_page"]
                        assert w["before_fdpc_page"]<metrics["fdpc_pages"]
                        assert w["after_fdpc_page"]<metrics["fdpc_pages"]
                        assert w["before_fdpc_target"]!=w["after_fdpc_target"]
                        assert all(type(w[k]) is bool for k in ("fully_linked","distinct_target_rows","logical_boundary_join"))
                        for k in ("before_btec_row","after_btec_row"):
                            assert w[k] is None or (type(w[k]) is int and 0<=w[k]<metrics["btec_rows"])
                        if w["fully_linked"]:
                            assert w["before_btec_row"] is not None and w["after_btec_row"] is not None
                            linked+=1
                        if w["distinct_target_rows"]:
                            assert w["fully_linked"] and w["before_btec_row"]!=w["after_btec_row"]
                            distinct+=1
                        if w["logical_boundary_join"]:
                            assert w["fully_linked"]
                            boundary+=1
                    assert linked==metrics["equal_linked"]
                    assert distinct==metrics["equal_distinct_rows"]
                    assert boundary==metrics["equal_boundary_join"]
                    if joined["status"]=="COMPLETE":
                        assert (metrics["targets_missing"]==0 and metrics["pages_zero_targets"]==0
                            and metrics["pages_multiple_targets"]==0 and metrics["row_end_mismatches_page"]==0)
                        assert metrics["btec_rows"]==metrics["fdpc_pages"]
                    btec_totals.update(metrics)
                    witness_total+=len(joined["equal_witnesses"])
                baseline=prior.get(row["source_sha256"])
                if baseline is not None:
                    old_observed+=1
                    actual=[x["fdpc_page_count"],raw["records"],
                            raw["cross_page"],raw["equal_cross_page"]]
                    if actual!=baseline:old_drift.append(row["source_sha256"])

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
        if row["source_sha256"] in prior and (probe is None or status!="ANALYZED"):
            old_missing+=1
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
        "counterexamples":issues,
        "fdpc_raw_style_totals":dict(sorted(raw_totals.items())),
        "btec_join_statuses":dict(sorted(join_states.items())),
        "btec_link_totals":dict(sorted(btec_totals.items())),
        "equal_witnesses":witness_total,
        "baseline_checked":old_observed,
        "baseline_not_reobserved":old_missing,
        "baseline_mismatch_sha256":old_drift}
    assert old_observed+old_missing==len(prior)
    assert set(report["summary"])==SUMMARY_FIELDS
    assert report["summary"]==expected, [
       k for k in expected if report["summary"].get(k)!=expected[k]]
    print("PUB-T-986 SOURCE-SAFE PASS",parsed,"Quill PUB",
          expected["totals"].get("raw_cr_count",0),"CR",
          expected["totals"].get("fdpp_multiset_equal_files",0),
          "exact-multiset files; exceptions",len(issues))
    return True

if __name__=="__main__":validate(Path(sys.argv[1]))
