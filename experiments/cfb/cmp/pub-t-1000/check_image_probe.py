#!/usr/bin/env python3
"""Independent static numeric receipt gate for real source_exact Viewer census."""
import json,sys
from collections import Counter
from pathlib import Path

if len(sys.argv)!=2:raise SystemExit("usage: check_image_probe.py RECEIPT")
r=json.loads(Path(sys.argv[1]).read_text())
assert r["schema"]=="sk1.pub-t1000.real-image-census.v1"
assert r["product_reader_source_sha"]=="a654d1af59be6173cd31ba3b7be37b1155a28ba5"
assert r["donor_source_sha"]=="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
assert r["native_publisher_pairs_git_blob"]=="2c2b03652e79390befe55f2889dbc248eb2abe01"
assert r["native_pdf_pixels_embedded"] is False
assert r["safety_policy_disabled"] is False
assert r["real_rust_viewer_engine_used"] is True
rows=r["fixtures"]
assert len(rows)==7
assert {x["fixture"].split("_")[0] for x in rows}=={"001","021","022","023","025","043","073"}
assert all(x["source_sha_verified"] for x in rows)
assert all(len(x["pub_sha256"])==64 and x["pub_byte_len"]>0 for x in rows)
for p in rows:
    assert p["image_count"]==p["source_exact_images"]+p["derived_images"]
    assert len(p["source_exact_byte_sizes"])==p["source_exact_images"]
    assert sum(p["source_exact_byte_sizes"])==p["source_exact_bytes"]
    assert sum(p["source_exact_mimes"].values())==p["source_exact_images"]
    assert sum(p["other_image_mimes"].values())==p["derived_images"]
    assert p["source_exact_node_uses"]>=0
    assert p["historical_real_browser_changed_cells"]>=0
    assert p["current_real_browser_changed_cells"]>=0
    assert p["regression_changed_cells"]==(
        p["current_real_browser_changed_cells"]-p["historical_real_browser_changed_cells"])
    assert all(z>0 for z in p["source_exact_byte_sizes"])
s=r["summary"]
assert s["same_source_verified"]==7
assert s["fixtures_with_source_exact_images"]==sum(p["source_exact_images"]>0 for p in rows)
assert s["fixtures_with_browser_visual_regressions"]==sum(p["regression_changed_cells"]>0 for p in rows)
assert s["max_regressed_fixture_022_jpeg_4880kb_confirmed"] is True
assert s["security_policy_all_exact_images_denied"] is True
assert s["image_census_does_not_prove_all_pixels_causally_lost"] is True
f22=next(x for x in rows if x["fixture"].startswith("022_"))
assert f22["pub_sha256"]=="7079ad60fd8109796b84286d294cb490051a1517d8e52ac61e7c416dbd04428c"
assert f22["source_exact_images"]==1 and f22["source_exact_mimes"]=={"image/jpeg":1}
assert f22["source_exact_byte_sizes"]==[4869956]
assert f22["source_exact_node_uses"]>=1
assert f22["historical_real_browser_changed_cells"]==462
assert f22["current_real_browser_changed_cells"]==3817
assert f22["regression_changed_cells"]==3355
print("SK1 T1000 real viewer source-safe image census accepted",s)
