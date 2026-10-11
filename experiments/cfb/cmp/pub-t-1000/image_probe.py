#!/usr/bin/env python3
"""Current actual RAR2 pub-viewer source_exact image census on seven SHA-pinned
public PUBs, compared to real historical/browser raster regression receipts.
No raw PUB, image, paragraph or PNG ever published.
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen

SOURCE="a654d1af59be6173cd31ba3b7be37b1155a28ba5"
DONOR="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
PAIR_BLOB="2c2b03652e79390befe55f2889dbc248eb2abe01"
IDS={"001","021","022","023","025","043","073"}
BEFORE_SHA="142d29a71c1936d322431200832010fffe97e5859729ab66c6c6ca909b628e45"
AFTER_SHA="4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d"

def sha(b):return hashlib.sha256(b).hexdigest()
def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,capture_output=True,
                          text=True,timeout=25,check=True).stdout.strip()

def acquire(row):
    url=(f"https://raw.githubusercontent.com/Lalalalendia/lalamu/{DONOR}/"
         f"pub-corpus/corpus/native/unclassified/{row['pub_sha256']}.pub")
    for trial in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":"SK1-T1000-source-safe-image"}),timeout=65) as conn:
                b=conn.read(30_000_000)
            break
        except Exception:
            if trial==2:raise ValueError("PUBLIC_FIXTURE_NETWORK_BLOCKED")
            time.sleep(2)
    if len(b)!=int(row["pub_bytes"]) or sha(b)!=row["pub_sha256"]:
        raise ValueError("PUBLIC_SOURCE_IDENTITY_MISMATCH")
    return b

def main():
    if len(sys.argv)!=6:
        raise SystemExit("usage: image_probe.py RAR2_SOURCE READER_EXE OLD_SUMMARY NEW_SUMMARY OUT_JSON")
    root=Path(sys.argv[1]).resolve(); exe=Path(sys.argv[2]).resolve()
    old_file=Path(sys.argv[3]);new_file=Path(sys.argv[4]);output=Path(sys.argv[5])
    if git(root,"rev-parse","HEAD")!=SOURCE:raise ValueError("WRONG_RAR2_COMMIT")
    pairs_path="tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv"
    if git(root,"hash-object",pairs_path)!=PAIR_BLOB:raise ValueError("WRONG_PAIRS_BLOB")
    if not exe.is_file():raise ValueError("REAL_RUST_VIEWER_EXE_NOT_BUILT")
    oldbytes=old_file.read_bytes();newbytes=new_file.read_bytes()
    if sha(oldbytes)!=BEFORE_SHA or sha(newbytes)!=AFTER_SHA:
        raise ValueError("READER_RECEIPT_UNVERIFIED")
    old=json.loads(oldbytes);new=json.loads(newbytes)
    if old["repository_commit_sha"]!="30a7bf813cb47198b2a70821564846ca49d640e1":
        raise ValueError("BAD_OLD_READER_SOURCE")
    if new["repository_commit_sha"]!=SOURCE:raise ValueError("BAD_NEW_READER_SOURCE")
    a={(p["fixture"],p["page"]):p for p in old["pages"]}
    b={(p["fixture"],p["page"]):p for p in new["pages"]}
    if set(a)!=set(b) or len(a)!=162:raise ValueError("REFERENCE_PAGE_IDENTITY_DRIFT")
    with (root/pairs_path).open() as f:
        registered=list(csv.DictReader(f))
    selected=[row for row in registered if row["basename"].split("_")[0] in IDS]
    if len(selected)!=7:raise ValueError("WRONG_FIXED_SEVEN")
    data={"schema":"sk1.pub-t1000.real-image-census.v1",
          "product_reader_source_sha":SOURCE,
          "donor_source_sha":DONOR,
          "native_publisher_pairs_git_blob":PAIR_BLOB,
          "comparison":"actual Viewer images under product source_exact policy and actual historical Browser images",
          "native_pdf_pixels_embedded":False,
          "safety_policy_disabled":False,
          "real_rust_viewer_engine_used":True,
          "fixtures":[]}
    with tempfile.TemporaryDirectory(prefix="sk1-t1000-actual-image-") as d:
        scratch=Path(d)
        for row in selected:
            name=row["basename"]
            raw=acquire(row)
            pub=scratch/"fixture.pub";pub.write_bytes(raw)
            private=scratch/"viewer_source_safe.json"
            run=subprocess.run([str(exe),str(pub),str(private)],capture_output=True,
                               timeout=100,check=False)
            if run.returncode or not private.is_file():
                raise ValueError("RUST_VIEWER_FAILED_"+row["oracle_id"])
            actual=json.loads(private.read_text())
            if actual["schema"]!="sk1-pub-t1000-viewer-image-envelope.v1":
                raise ValueError("RUST_VIEWER_SCHEMA")
            if actual["source_byte_len"]!=len(raw):
                raise ValueError("RUST_VIEWER_SOURCE_BYTE_DRIFT")
            if actual["raw_bytes_emitted"] is not False:
                raise ValueError("UNSAFE_RESULT")
            for img in actual["images"]:
                if img["source_exact"] and img["security_browser_admission_class"]!="source_exact_browser_denied":
                    raise ValueError("EXACT_SOURCE_POLICY_MISMATCH")
            pic={
                "fixture":name,"pub_sha256":row["pub_sha256"],
                "pub_byte_len":len(raw),"source_sha_verified":True,
                "image_count":actual["viewer_image_count"],
                "source_exact_images":actual["source_exact_image_count"],
                "derived_images":actual["derived_candidate_image_count"],
                "source_exact_bytes":actual["source_exact_raw_byte_total"],
                "source_exact_node_uses":actual["source_exact_node_refs"],
                "source_exact_mimes":dict(Counter(
                    x["mime"] for x in actual["images"] if x["source_exact"])),
                "source_exact_byte_sizes":[x["raw_byte_len"] for x in actual["images"] if x["source_exact"]],
                "other_image_mimes":dict(Counter(
                    x["mime"] for x in actual["images"] if not x["source_exact"])),
                "historical_real_browser_changed_cells":sum(x["changed_cell_count"] for k,x in a.items() if k[0]==name),
                "current_real_browser_changed_cells":sum(x["changed_cell_count"] for k,x in b.items() if k[0]==name),
                "pdf_page_count":int(row["pdf_pages"])}
            pic["regression_changed_cells"]=pic["current_real_browser_changed_cells"]-pic["historical_real_browser_changed_cells"]
            data["fixtures"].append(pic)
            pub.unlink(missing_ok=True);private.unlink(missing_ok=True)
    f22=next(x for x in data["fixtures"] if x["fixture"].startswith("022_"))
    if (f22["source_exact_images"]!=1 or f22["source_exact_mimes"]!={"image/jpeg":1}
        or f22["source_exact_byte_sizes"]!=[4869956]
        or f22["source_exact_node_uses"]<1):
        raise ValueError("REAL_022_SOURCE_EXACT_JPEG_WITNESS_MISSING")
    data["summary"]={
      "same_source_verified":7,
      "fixtures_with_source_exact_images":sum(x["source_exact_images"]>0 for x in data["fixtures"]),
      "fixtures_with_browser_visual_regressions":sum(x["regression_changed_cells"]>0 for x in data["fixtures"]),
      "max_regressed_fixture_022_jpeg_4880kb_confirmed":True,
      "security_policy_all_exact_images_denied":True,
      "image_census_does_not_prove_all_pixels_causally_lost":True
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data["summary"],sort_keys=True))
    for row in data["fixtures"]:
        print(row["fixture"].split("_")[0],row["source_exact_images"],
              row["derived_images"],row["regression_changed_cells"])

if __name__=="__main__":
    main()
