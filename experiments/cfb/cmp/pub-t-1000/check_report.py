#!/usr/bin/env python3
"""Independent acceptance: verifies historical-vs-current image-security evidence
without conflating historical Reader with same-version controlled A/B.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import sys

def sha(x):return hashlib.sha256(x).hexdigest()
if len(sys.argv)!=5:
    raise SystemExit("usage: check_report.py REPORT BEFORE_JSON AFTER_JSON LO_JSON")
out,oldpath,newpath,lopath=map(Path,sys.argv[1:])
d=json.loads(out.read_text())
o=json.loads(oldpath.read_text())
n=json.loads(newpath.read_text())
lo=json.loads(lopath.read_text())
assert d["schema"]=="sk1.pub-t1000.web-security-history.v1"
assert d["task"]=="PUB-T-1000"
assert d["policy"]["exact_one_file_diff"] is True
assert d["policy"]["parent"]=="22a322ed10d9fe8a4ade45acf83bebd0442b691b"
assert d["policy"]["policy_commit"]=="ea5689c6a1fff065297fa3ff3e84a153ed81ecfe"
assert d["policy"]["modified_file"]=="apps/chaptera-server/src/reader_scene_v1.rs"
assert d["policy"]["policy_denies_source_exact_before_mime_size_check"]
assert d["policy"]["jpeg_five_mib_limit_unchanged"]
assert d["policy"]["security_reason"]=="source_exact_browser_denied"
assert d["policy"]["raw_browser_image_reenable_allowed"] is False
assert d["claim_boundaries"]=={
    "real_browser_before_and_after":True,
    "same_public_pub_and_publisher_reference":True,
    "source_free_no_pub_jpeg_pdf_png_uploaded":True,
    "security_guard_static_causal_for_source_exact_inline_admission":True,
    "other_intervening_main_commits_confound_all_page_pixel_causality":True,
    "historical_counterfactual_not_current_product_claim":True,
    "current_visual_85_17_9_is_real_user_facing_secure_reader":True,
    "publisher_surface_stage_known":False}
for label,file in (("old",oldpath),("new",newpath),("lo",lopath)):
    assert sha(file.read_bytes())==d["input_artifacts"][label]["sha"]
assert o["repository_commit_sha"]==d["input_artifacts"]["old"]["commit"]
assert n["repository_commit_sha"]==d["input_artifacts"]["new"]["commit"]
assert len(o["pages"])==len(n["pages"])==162
assert len(o["pairs"])==len(n["pairs"])==55
op={ (x["fixture"],x["page"]):x for x in o["pages"]}
np={ (x["fixture"],x["page"]):x for x in n["pages"]}
assert len(op)==len(np)==162 and set(op)==set(np)
cl=Counter();sumdelta=0
for key,x in op.items():
    y=np[key]
    assert x["candidate_page_identity_sha256"]==y["candidate_page_identity_sha256"]
    assert x["reference_state"]==y["reference_state"]
    assert x["reference_surface_stage"]==y["reference_surface_stage"]
    assert x["reference_media_extent_delta"]==y["reference_media_extent_delta"]
    dx=y["changed_cell_count"]-x["changed_cell_count"]
    sumdelta+=dx
    cl["worse" if dx>0 else "better" if dx<0 else "unchanged"]+=1
assert cl==Counter(worse=90,better=1,unchanged=71)
assert sumdelta==47869
summary=d["summary"]
assert summary["registered_source_pub_count"]==55
assert summary["registered_publisher_raster_pages"]==162
assert summary["both_reader_page_identity_sha256_same"]==162
assert summary["reader_page_regressed_count"]==cl["worse"]
assert summary["reader_page_improved_count"]==cl["better"]
assert summary["reader_page_unchanged_count"]==cl["unchanged"]
assert summary["added_changed_64x64_cells"]==sumdelta
assert summary["historic_and_current_same_code_commit"] is False
assert summary["exact_one_change_controlled_browser_ab_executed"] is False
assert summary["all_page_regressions_attributed_only_to_security_rule"] is False
pairs_before=Counter();pairs_after=Counter();doc_before=Counter();doc_after=Counter()
obs=[]
for c in lo["cases"]:
    before=[];after=[]
    for p in c["raster"]["pages"]:
        if p.get("status")!="COARSE_ORDINAL_MATCH":continue
        key=(c["fixture"],p["ordinal_page"])
        bf=op[key]["changed_cell_fraction"]-p["libreoffice_changed_fraction"]
        af=np[key]["changed_cell_fraction"]-p["libreoffice_changed_fraction"]
        assert np[key]["changed_cell_fraction"]==p["reader_changed_fraction"]
        def label(v):
            return "LO" if v>0.015 else "READER" if v< -0.015 else "NEAR_TIE"
        pairs_before[label(bf)]+=1;pairs_after[label(af)]+=1
        before.append(bf);after.append(af)
        obs.append((op[key]["changed_cell_fraction"],np[key]["changed_cell_fraction"],p["libreoffice_changed_fraction"]))
    if before:
        doc_before[label(sum(before)/len(before))]+=1
        doc_after[label(sum(after)/len(after))]+=1
assert len(obs)==111
assert pairs_before==Counter(LO=48,READER=36,NEAR_TIE=27)
assert pairs_after==Counter(LO=85,READER=17,NEAR_TIE=9)
assert doc_before==Counter(READER=20,LO=13,NEAR_TIE=6)
assert doc_after==Counter(LO=26,READER=8,NEAR_TIE=5)
assert summary["lo_ranked_documents"]==39
assert summary["lo_ranked_ordinal_pages"]==111
assert summary["before_pages"]==dict(pairs_before)
assert summary["after_pages"]==dict(pairs_after)
assert summary["before_documents"]==dict(doc_before)
assert summary["after_documents"]==dict(doc_after)
assert abs(summary["historical_reader_mean_shared"]-sum(x[0] for x in obs)/len(obs))<1e-12
assert abs(summary["current_reader_mean_shared"]-sum(x[1] for x in obs)/len(obs))<1e-12
assert abs(summary["lo_mean_shared"]-sum(x[2] for x in obs)/len(obs))<1e-12
assert d["sample_022"]["historical_reader_changed_cells"]==462
assert d["sample_022"]["current_reader_changed_cells"]==3817
assert d["sample_022"]["lo_changed_cells"]==540
assert len(d["largest_regressions"])==20
assert d["largest_regressions"][0]["fixture"].startswith("022_")
print("SK1 T1000 independent gate PASS: 162 pages, 90 worse/1 better, +47869 cells; "
      "same-111 LO48/R36/T27 historical vs LO85/R17/T9 secure Reader; security cause policy not sole attribution.")
