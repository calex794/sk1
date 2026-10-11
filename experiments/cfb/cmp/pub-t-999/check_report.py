#!/usr/bin/env python3
"""Independent, source-safe acceptance of PUB-T-999 coarse same-input visual A/B."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

r=json.loads(Path(sys.argv[1]).read_text())
base=Path(sys.argv[2])
assert r["schema"]=="sk1.pub-t999.visual-ordinal.v1"
assert r["task_id"]=="PUB-T-999"
assert r["rar2_commit"]=="a654d1af59be6173cd31ba3b7be37b1155a28ba5"
assert r["public_donor_commit"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
assert r["pair_manifest_blob"]=="2c2b03652e79390befe55f2889dbc248eb2abe01"
assert r["publisher_reference_blob"]=="1e87b52d268f87dcd4896f3d1af351a0b8cb9d96"
assert r["comparator_blob"]=="219159cf0b0ace72aa21b0d949ca2b2f8cf7fb45"
assert r["reader_main_actions_run"]==38143407856
assert r["reader_artifact"]==11704131725
assert r["reader_artifact_zip_sha256"]=="a6c1d4faa1b3aee07c48de9592e770ded1072ec07a52e0247cc94e039a578fab"
assert r["reader_summary_sha256"]=="4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d"
assert r["stage_of_reference_pdf_pages"]=="unknown"
assert r["native_publisher_ran"] is False
assert r["native_publisher_grounding"]=="preexisting_signed_64x64_rgb_pdf_reference"
assert r["comparison_limit"]=="coarse_ordinal_64x64_not_native_logical_page_or_full_resolution"
assert r["raster_policy"]=={"dpi":144,"mode":"RGB","size":[64,64],"scale":"Pillow.BOX",
                             "threshold_channel_delta":12,"tie_deadband":0.015}
with (base/"tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv").open() as file:
    listed={x["basename"]:x for x in csv.DictReader(file)}
rows=r["cases"]
assert len(rows)==49 and len({x["fixture"] for x in rows})==49
assert len(r["predeclared_excluded_no_donor_source"])==6
assert set(r["predeclared_excluded_no_donor_source"])==set(listed)-{x["fixture"] for x in rows}
assert sum(x["native_pdf_page_count"] for x in rows)==153
collected=[]
counts=Counter()
for row in rows:
    e=listed[row["fixture"]]
    assert row["pub_sha256"]==e["pub_sha256"]
    assert row["pub_byte_len"]==int(e["pub_bytes"])
    assert row["reference_pdf_sha256"]==e["pdf_sha256"]
    assert row["native_pdf_page_count"]==int(e["pdf_pages"])
    assert row["input_sha_verified"] and row["input_unchanged"]
    assert row["import"]["status"] in ("IMPORTED","ODG_NOT_CREATED","UNREADABLE_ODG",
                                       "ODG_TIMEOUT","PDF_TIMEOUT","PDF_NOT_CREATED")
    if row["import"]["status"]!="IMPORTED":
        assert row["raster"]["ranked_pages"]==0
        continue
    p=row["raster"]
    assert p["status"]=="RASTERED" and p["page_count"]==row["import"]["odg_pages"]
    assert len(p["pages"])==p["page_count"]
    assert p["counts_match_all_three"]==(
        p["page_count"]==row["native_pdf_page_count"]==row["reader_page_count"])
    assert p["ranked_pages"]==sum(q["status"]=="COARSE_ORDINAL_MATCH" for q in p["pages"])
    for x in p["pages"]:
        if x["status"]!="COARSE_ORDINAL_MATCH":continue
        assert p["counts_match_all_three"]
        assert x["physical_page_match"] and x["reader_physical_page_match"]
        a=x["libreoffice_changed_fraction"];b=x["reader_changed_fraction"]
        assert 0<=a<=1 and 0<=b<=1
        diff=x["libreoffice_advantage"]
        assert abs(diff-(b-a))<1e-6
        want="LIBREOFFICE" if diff>0.015 else "READER" if diff< -0.015 else "NEAR_TIE"
        assert x["winner"]==want
        counts[want]+=1
        collected.append((a,b,row["fixture"],x["ordinal_page"]))
    if row["fixture"].split("_")[0] in ("001","029"):
        assert row["repeat"]["odg_identical"]
        assert row["repeat"]["pdf_rasters_identical"]
s=r["summary"]
assert s["predeclared_donor_cohort"]==49
assert s["source_sha_verified_and_unchanged"]==49
assert s["lo_import_success_count"]==sum(x["import"]["status"]=="IMPORTED" for x in rows)
assert s["lo_import_blocked_count"]+s["lo_import_success_count"]==49
assert s["native_publisher_reference_pages"]==153
assert s["reader_original_pdf_page_counts_match"]==sum(
    x["reader_page_count"]==x["native_pdf_page_count"] for x in rows)
assert s["lo_original_pdf_page_counts_match"]==sum(
    x["raster"]["page_count"]==x["native_pdf_page_count"]
    for x in rows if x["import"]["status"]=="IMPORTED")
assert s["ranked_pair_count"]==len({x[2] for x in collected})
assert s["ranked_ordinal_pages"]==len(collected)
assert s["libreoffice_closer_pages"]==counts["LIBREOFFICE"]
assert s["reader_closer_pages"]==counts["READER"]
assert s["near_tie_pages"]==counts["NEAR_TIE"]
assert s["ranked_ordinal_pages"]>=12
assert s["repeated_lo_rasters_identical_count"]==2
assert s["malformed_cfb_rejected"]
assert s["reference_surface_stage_unknown"] is True
assert abs(s["reader_mean_changed_fraction"]-sum(x[1] for x in collected)/len(collected))<1e-7
assert abs(s["libreoffice_mean_changed_fraction"]-sum(x[0] for x in collected)/len(collected))<1e-7
assert r["negative"]["bytes_mutated"]==1 and r["negative"]["rejected"] and not r["negative"]["counts_towards_49"]
for x in r["largest_differences"]:
    assert x["winner"] in ("LIBREOFFICE","READER","NEAR_TIE")
    assert x["fixture"] in {z["fixture"] for z in rows}
print("PUB-T-999 source-safe independent verification PASS:",json.dumps(s,sort_keys=True))
