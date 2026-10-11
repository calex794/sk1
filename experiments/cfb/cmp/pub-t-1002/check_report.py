#!/usr/bin/env python3
"""Independent source-safe acceptance for seven real PUB decode→reencode probes.

The probe MUST remain an offline candidate, not a browser-safety claim.
"""
import json
import sys
from collections import Counter
from pathlib import Path

if len(sys.argv)!=2:raise SystemExit("check_report.py REPORT.json")
r=json.loads(Path(sys.argv[1]).read_text())
assert r["schema"]=="sk1.pub-t1002.pinned-seven-safe-preview-lab.v1"
assert r["task_id"]=="PUB-T-1002"
assert r["rar2_commit"]=="5a745034afd002d968f96eda5cc17d816e621fef"
assert r["donor_commit"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
assert r["pairs_git_blob"]=="2c2b03652e79390befe55f2889dbc248eb2abe01"
assert r["decode_contract_source_git_blob"]=="c6ed97b7081d3cd3915968d142d648253ddbe1e1"
assert r["product_or_host_modified"] is False
assert r["host_browser_safe_preview_admitted"] is False
assert r["public_fixture_count"]==7
rows=r["fixtures"]
assert len(rows)==7
assert {x["name"].split("_")[0] for x in rows}=={"001","021","022","023","025","043","073"}
accepted=rejected=already=0
for row in rows:
    assert row["source_verified"] and len(row["source_sha256"])==64
    assert row["public_source_byte_len"]>100 and row["reference_pdf_page_count"]>=1
    p=row["result"]
    assert p["product_pub_sha256"]==row["source_sha256"]
    assert p["product_pub_bytes"]==row["public_source_byte_len"]
    assert p["schema"]=="sk1-pub-t1002-image-preview-candidate.v1"
    assert p["original_pub_or_image_bytes_exported"] is False
    assert p["trust_host_sanitization_still_blocks_worker_images"] is True
    limits=p["fixed_limits"]
    assert limits["source_encoded_bytes"]==5*1024*1024
    assert limits["preview_encoded_bytes"]==5*1024*1024
    assert limits["aggregate_preview_bytes"]==12*1024*1024
    assert limits["max_dimension"]==8192 and limits["max_pixels"]==16_777_216
    assert limits["max_decoded_bytes"]==64*1024*1024
    negative=p["negative_controls"]
    assert len(negative)==7 and all(v is True for v in negative.values())
    resources=p["resources"]
    assert p["viewer_image_count"]==len(resources)
    assert p["candidate_count"]==sum(q["status"]=="encoded_candidate_only_not_browser_safe" for q in resources)
    assert p["failed_closed_count"]==sum(q["status"]=="fail_closed" for q in resources)
    assert p["already_derived_viewer_count"]==sum(q["status"]=="derived_viewer_resource_unmodified" for q in resources)
    assert p["candidate_count"]+p["failed_closed_count"]+p["already_derived_viewer_count"]==len(resources)
    assert p["aggregate_preview_bytes"]==sum(q["derived_encoded_bytes"] for q in resources if q["status"]=="encoded_candidate_only_not_browser_safe")
    assert p["aggregate_preview_bytes"]<=12*1024*1024
    accepted+=p["candidate_count"];rejected+=p["failed_closed_count"];already+=p["already_derived_viewer_count"]
    for q in resources:
        if q["status"]=="encoded_candidate_only_not_browser_safe":
            assert q["source_exact"] is True
            assert q["source_mime"]==q["derived_mime"]
            assert q["source_mime"] in ("image/jpeg","image/png")
            if q["source_mime"]=="image/jpeg":
                assert q["jpeg_quality_used"] in (93,88,82,75,68,60)
            else:
                assert q["jpeg_quality_used"] is None
            assert q["source_sha256"]!=q["derived_sha256"]
            assert len(q["source_sha256"])==len(q["derived_sha256"])==64
            assert 0<q["source_encoded_bytes"]<=5*1024*1024
            assert 0<q["derived_encoded_bytes"]<=5*1024*1024
            assert 0<q["width_px"]<=8192 and 0<q["height_px"]<=8192
            assert q["width_px"]*q["height_px"]<=16_777_216
            assert all(q[k] is True for k in (
                "fresh_encoding_deterministic","source_bytes_not_forwarded",
                "separate_derivative_identity","metadata_stripped_by_reconstruction","host_acceptance_not_executed"))
            assert q["exif_orientation"] in (None,1)
            metrics=q["pixel_comparison"]
            assert 1<=metrics["sampled_pixel_count"]<=8192
            assert 0<=metrics["sampled_changed_pixel_fraction_threshold12"]<=1
            assert 0<=metrics["sampled_mean_abs_channel_delta"]<=255
            assert 0<=metrics["sampled_max_channel_delta"]<=255
            assert metrics["sample_channels"] in (1,2,3,4)
            if q["source_mime"]=="image/png":
                assert metrics["png_pixel_lossless"]
        if q["status"]=="fail_closed":
            assert q["source_exact"] is True and q["code"] and len(q["code"])<=72
        if q["status"]=="derived_viewer_resource_unmodified":
            assert q["source_exact"] is False
summary=r["summary"]
assert summary["original_7_pub_sha_verified"]==7
assert summary["image_count"]==sum(q["result"]["viewer_image_count"] for q in rows)
assert summary["source_exact_accepted_to_new_candidate"]==accepted
assert summary["source_exact_fail_closed"]==rejected
assert summary["non_source_derived_control_count"]==already
assert summary["new_candidate_output_bytes"]==sum(q["result"]["aggregate_preview_bytes"] for q in rows)
assert summary["source_exact_admitted_original_to_browser"]==0
assert summary["host_safe_preview_admission_pending"]
f22=next(x for x in rows if x["name"].startswith("022_"))
r22=[x for x in f22["result"]["resources"] if x["source_exact"]]
assert len(r22)==1
assert r22[0]["status"]=="encoded_candidate_only_not_browser_safe"
assert r22[0]["source_mime"]=="image/jpeg"
assert r22[0]["source_encoded_bytes"]==4869956
assert r["control_022"]["source_bytes"]==4869956
assert r["control_022"]["candidate_status"]=="encoded_candidate_only_not_browser_safe"
assert r["control_022"]["derived_new_encoded_bytes"]==r22[0]["derived_encoded_bytes"]
assert r["control_022"]["original_never_delivered_to_browser"] is True
assert accepted>=1
print("PUB-T-1002 independent bounded derivative candidate accepted:",json.dumps(summary,sort_keys=True))
