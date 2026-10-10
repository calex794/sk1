#!/usr/bin/env python3
"""PUB-T-967: fail-closed source-safe, blind, no-Writer Quill prediction receipt."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re
import sys
HERE=Path(__file__).resolve().parent
SHA=re.compile(r"^[a-f0-9]{64}$")
CODE={
    "quill_growth_would_discard_descriptor",
    "quill_growth_would_discard_unknown",
    "quill_insufficient_capacity",
    "PREDICTED_PASS_UNEXPECTED",
}
R_FIELDS={"source_sha256","source_host","source_bytes","status","reason","structural",
    "matches_empirical_threshold","matches_empirical_guard",
    "predicted_minus_empirical_units"}
STRUCTURAL={
    "schema","source_sha256","source_bytes","selected_story_ordinal",
    "selected_offset_utf16","selected_story_utf16_len","quill_stream_length",
    "quill_descriptor_count","source_story_count","text_start","text_end",
    "first_aligned_fd_anchor","pre_anchor_gap_bytes","trailing_zero_bytes",
    "overlapping_nontarget_descriptor_count","furthest_nontext_descriptor_end",
    "nontext_descriptor_clearance_bytes","source_only_predicted_max_growth_utf16",
    "source_only_predicted_first_failure_utf16",
    "source_only_predicted_first_failure_guard","limiting_factors",
    "source_immutable","writer_invoked","candidate_generated",
    "native_publisher_acceptance","product_pub_download_authorized"
}
FLAGS={"source_immutable","writer_invoked","candidate_generated",
    "product_pub_download_authorized"}
TEXTS={"schema","source_sha256","source_only_predicted_first_failure_guard",
    "limiting_factors","native_publisher_acceptance"}
NUMS=STRUCTURAL-FLAGS-TEXTS

def verify(root:Path):
    assert root.is_dir()
    assert {x.name for x in root.iterdir()}=={"plan.json","records.json","report.json"}
    spec=importlib.util.spec_from_file_location("sk1_pub_t967_runner",HERE/"run.py")
    assert spec and spec.loader
    runner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    labels,digest=runner.read_labels()
    plan=json.loads((root/"plan.json").read_text(encoding="utf8"))
    rows=json.loads((root/"records.json").read_text(encoding="utf8"))
    report=json.loads((root/"report.json").read_text(encoding="utf8"))
    assert set(plan)=={"schema","upstream_rar2_sha","source_lalamu_sha",
        "upstream_source_manifest","historical_experiment",
        "historical_scientific_sha","historical_source_safe_artifact_zip_sha256",
        "historical_actions_run_id","pre_registered_witnesses_sha256",
        "witnesses","predeclared_sources","prediction_blind_to_labels",
        "writer_invoked","scope","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.quill-diag-pub-t-967.plan.v1"
    assert plan["upstream_rar2_sha"]==runner.RAR2_PIN
    assert plan["source_lalamu_sha"]==runner.LALAMU_PIN
    assert plan["upstream_source_manifest"]==runner.source.NEW_MANIFEST
    assert plan["historical_experiment"]=="SK1-QUILL-EXP-PUB-T-962"
    assert plan["historical_scientific_sha"]==runner.PREVIOUS_SCIENTIFIC_SHA
    assert plan["historical_source_safe_artifact_zip_sha256"]==runner.PREVIOUS_ZIP_SHA
    assert plan["historical_actions_run_id"]==runner.PREVIOUS_RUN
    assert plan["pre_registered_witnesses_sha256"]==digest
    assert plan["witnesses"]==list(labels.values())
    assert plan["predeclared_sources"]==runner.EXPECTED_SOURCE_COUNT==14
    assert plan["prediction_blind_to_labels"] is True
    assert plan["writer_invoked"] is False
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert set(report)=={"schema","upstream_rar2_sha",
        "pre_registered_witnesses_sha256","summary","records",
        "writer_invoked","native_publisher_acceptance",
        "product_pub_download_authorized"}
    assert report["schema"]=="sk1.quill-diag-pub-t-967.report.v1"
    assert report["upstream_rar2_sha"]==runner.RAR2_PIN
    assert report["pre_registered_witnesses_sha256"]==digest
    assert report["writer_invoked"] is False
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert report["records"]==rows
    assert isinstance(rows,list) and len(rows)==14
    assert [x["source_sha256"] for x in rows]==list(labels)
    for row in rows:
        assert isinstance(row,dict) and set(row)==R_FIELDS
        key=row["source_sha256"]
        assert SHA.fullmatch(key) and key in labels
        assert row["source_host"] in runner.source.QUOTAS
        assert type(row["source_bytes"]) is int and 0<row["source_bytes"]<=runner.source.MAX_FILE
        assert row["status"]=="EVALUATED"
        assert row["reason"]=="BLIND_PREDICTION_RECORDED"
        s=row["structural"]
        assert isinstance(s,dict) and set(s)==STRUCTURAL,(STRUCTURAL-set(s),set(s)-STRUCTURAL)
        assert s["schema"]=="sk1.quill-diag-pub-t-967.source-envelope.v1"
        assert s["source_sha256"]==key and s["source_bytes"]==row["source_bytes"]
        assert s["source_immutable"] is True
        assert s["writer_invoked"] is False and s["candidate_generated"] is False
        assert s["native_publisher_acceptance"]=="NOT_EVALUATED"
        assert s["product_pub_download_authorized"] is False
        for k in NUMS:
            assert type(s[k]) is int and 0<=s[k]<=16*1024*1024,k
        assert s["selected_story_ordinal"]==labels[key]["story_ordinal"]
        assert s["selected_offset_utf16"]==labels[key]["offset_utf16"]
        assert s["selected_story_utf16_len"]==labels[key]["before_utf16"]
        assert s["source_story_count"]>=1 and s["quill_descriptor_count"]>=1
        assert s["quill_stream_length"]>s["first_aligned_fd_anchor"]-1
        assert s["first_aligned_fd_anchor"]>=s["text_end"]>=s["text_start"]
        assert s["pre_anchor_gap_bytes"]==s["first_aligned_fd_anchor"]-s["text_end"]
        assert s["trailing_zero_bytes"]<=s["pre_anchor_gap_bytes"]
        assert s["furthest_nontext_descriptor_end"]>=s["text_end"]
        assert s["nontext_descriptor_clearance_bytes"]==max(0,
            s["first_aligned_fd_anchor"]-s["furthest_nontext_descriptor_end"])
        max_safe=min(s["pre_anchor_gap_bytes"],s["trailing_zero_bytes"],
            s["nontext_descriptor_clearance_bytes"])//2
        assert s["source_only_predicted_max_growth_utf16"]==max_safe
        assert s["source_only_predicted_first_failure_utf16"]==max_safe+1
        assert s["source_only_predicted_first_failure_guard"] in CODE
        factor=[]
        if s["pre_anchor_gap_bytes"]//2==max_safe:factor.append("GEOMETRY")
        if s["trailing_zero_bytes"]//2==max_safe:factor.append("NONZERO_SUFFIX")
        if s["nontext_descriptor_clearance_bytes"]//2==max_safe:
            factor.append("DESCRIPTOR_CLEARANCE")
        assert s["limiting_factors"]=="+".join(factor)
        for name in ("matches_empirical_threshold","matches_empirical_guard"):
            assert type(row[name]) is bool
        assert row["matches_empirical_threshold"]==(
            max_safe==labels[key]["last_pass_utf16"])
        assert row["matches_empirical_guard"]==(
            s["source_only_predicted_first_failure_guard"]==
            labels[key]["first_fail_guard"])
        assert type(row["predicted_minus_empirical_units"]) is int
        assert row["predicted_minus_empirical_units"]==(
            max_safe-labels[key]["last_pass_utf16"])
    computed=runner.summarize(rows,labels)
    assert report["summary"]==computed
    assert computed["predeclared_sources"]==14
    assert computed["evaluated_sources"]==14
    assert computed["source_status"]=={"EVALUATED":14}
    assert sum(computed["threshold_prediction_agreement"].values())==14
    assert sum(computed["first_guard_prediction_agreement"].values())==14
    assert computed["writer_invoked"] is False
    assert computed["original_962_writer_outcomes_only"] is True
    assert computed["native_publisher_acceptance"]=="NOT_EVALUATED"
    print("SK1 PUB-T-967 SOURCE-SAFE VALIDATOR PASS",
        json.dumps({"sources":14,"threshold":computed["threshold_prediction_agreement"],
            "guard":computed["first_guard_prediction_agreement"],
            "limiting_factors":computed["limiting_factors"],"writer_invoked":False},
            sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==2
    verify(Path(sys.argv[1]))
