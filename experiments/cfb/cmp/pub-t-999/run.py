#!/usr/bin/env python3
"""PUB-T-999: public native Publisher fingerprint vs existing real Reader vs LO.

No raw PUB, PDF, ODG, raster or extracted text is emitted to artifacts.
49 source identities and 153 native reference page entries fixed before test.
"""
from __future__ import annotations
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.request import Request,urlopen
import zipfile

import fitz
from PIL import Image

PRODUCT="a654d1af59be6173cd31ba3b7be37b1155a28ba5"
DONOR="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
BLOBS={"tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv":"2c2b03652e79390befe55f2889dbc248eb2abe01",
"tools/corpus/receipts/publisher-visual-golden-batch-01-fingerprint-v1.json":"1e87b52d268f87dcd4896f3d1af351a0b8cb9d96",
"tools/cloud_reader_visual_fingerprint_v1.py":"219159cf0b0ace72aa21b0d949ca2b2f8cf7fb45"}
ACTION=38143407856
ARTIFACT=11704131725
ARTIFACT_ZIP_SHA="a6c1d4faa1b3aee07c48de9592e770ded1072ec07a52e0247cc94e039a578fab"
SUMMARY_SHA="4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d"
IDS="""001 020 021 022 023 024 025 026 027 028 029 031 032 033 034 037 038 040 041 043 044 045
046 047 048 049 050 051 053 054 057 059 060 061 062 063 064 065 066 068 070 071 072
073 075 076 077 079 080""".split()
REPEAT=("001","029")
TIE=0.015
MAX_PIXELS=40000000


def hash_bytes(x):return hashlib.sha256(x).hexdigest()
def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,capture_output=True,text=True,timeout=20,check=True).stdout.strip()

def bounded(argv,seconds):
    try:
        r=subprocess.run(argv,capture_output=True,stdin=subprocess.DEVNULL,check=False,timeout=seconds)
        return r.returncode,False
    except subprocess.TimeoutExpired:
        return None,True

def source_pin(root):
    if git(root,"rev-parse","HEAD")!=PRODUCT:raise ValueError("WRONG_RAR2_SOURCE_PIN")
    for name,want in BLOBS.items():
        if git(root,"hash-object",name)!=want:raise ValueError("WRONG_RAR2_BLOB_PIN")

def load_comparator(root):
    sp=importlib.util.spec_from_file_location("pinned_rar_comparator",
                 root/"tools/cloud_reader_visual_fingerprint_v1.py")
    mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
    if (mod.GRID_W,mod.GRID_H,mod.CELL_DELTA)!=(64,64,12):
        raise ValueError("COMPARATOR_CHANGED")
    return mod

def setup(root,receipt):
    rows=list(csv.DictReader((root/"tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv").open()))
    fp=json.loads((root/"tools/corpus/receipts/publisher-visual-golden-batch-01-fingerprint-v1.json").read_text())
    if len(rows)!=55 or fp["pair_count"]!=55 or fp["reference_page_count"]!=162:
        raise ValueError("NATIVE_REFERENCE_COUNT_DRIFT")
    assert fp["grid"]=={"colorspace":"RGB","height":64,"reference_raster_dpi":144,
                        "resampling":"Pillow.BOX","width":64}
    by_id={x["basename"]:x for x in rows}
    native={x["basename"]:x for x in fp["pairs"]}
    cohort=[x for x in rows if x["basename"].split("_")[0] in IDS]
    if len(cohort)!=49 or len(set(x["basename"].split("_")[0] for x in cohort))!=49:
        raise ValueError("DONOR_COHORT_COUNT_DRIFT")
    if sum(int(x["pdf_pages"]) for x in cohort)!=153:
        raise ValueError("DONOR_COHORT_PAGES_DRIFT")
    if hash_bytes(receipt.read_bytes())!=SUMMARY_SHA:
        raise ValueError("READER_RECEIPT_HASH_DRIFT")
    current=json.loads(receipt.read_text())
    if (current.get("schema")!="chaptera.publisher-visual-fingerprint-compare.v1"
        or current.get("repository_commit_sha")!=PRODUCT
        or current["pair_count"]!=55 or len(current["pages"])!=162):
        raise ValueError("READER_RECEIPT_PROVENANCE_DRIFT")
    read_pairs={x["fixture"]:x for x in current["pairs"]}
    read_pages={(x["fixture"],x["page"]):x for x in current["pages"]}
    if len(read_pairs)!=55 or len(read_pages)!=162:raise ValueError("READER_DUPLICATE_ROWS")
    for row in cohort:
        key=row["basename"]
        if key not in native or native[key]["pub_sha256"]!=row["pub_sha256"] or native[key]["pdf_sha256"]!=row["pdf_sha256"]:
            raise ValueError("PDF_PAIR_HASH_DRIFT")
        if read_pairs[key]["source_sha256"]!=row["pub_sha256"]:raise ValueError("READER_SOURCE_SHA_DRIFT")
        if len(native[key]["pages"])!=int(row["pdf_pages"]):
            raise ValueError("REFERENCE_PAGE_DRIFT")
    return cohort,native,read_pairs,read_pages,set(by_id)-{x["basename"] for x in cohort}

def download(entry,root):
    name=entry["pub_sha256"]
    url=(f"https://raw.githubusercontent.com/Lalalalendia/lalamu/{DONOR}/"
        f"pub-corpus/corpus/native/unclassified/{name}.pub")
    contents=None
    for trial in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":"SK1-PUB-T-999"}),timeout=55) as res:
                contents=res.read(30000000)
            break
        except Exception:
            if trial==2:raise ValueError("DONOR_DOWNLOAD_ERROR")
            time.sleep(2)
    if len(contents)!=int(entry["pub_bytes"]) or hash_bytes(contents)!=name:
        raise ValueError("DONOR_PUB_SHA_OR_LENGTH_MISMATCH")
    output=root/(entry["basename"]+".pub")
    output.write_bytes(contents)
    return output

def convert(pub,root,lo):
    root.mkdir()
    odg_dir=root/"odg";pdf_dir=root/"pdf";odg_dir.mkdir();pdf_dir.mkdir()
    profile=root/"profile"
    base=[lo,"-env:UserInstallation="+profile.absolute().as_uri(),
          "--headless","--nodefault","--nologo","--nofirststartwizard"]
    rc,to=bounded(base+["--convert-to","odg","--outdir",str(odg_dir),str(pub)],110)
    odg=odg_dir/(pub.stem+".odg")
    if to:return {"status":"ODG_TIMEOUT"},None
    if not odg.is_file():return {"status":"ODG_NOT_CREATED","rc":rc},None
    try:
        with zipfile.ZipFile(odg) as z:
            if z.testzip():raise ValueError("BAD_ODG_CRC")
            content=z.read("content.xml")
            tree=ET.fromstring(content)
        office="{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
        draw="{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
        drawing=tree.find("./"+office+"body/"+office+"drawing")
        if drawing is None:raise ValueError("ODG_MISSING_DRAWING")
        pages=len(drawing.findall(draw+"page"))
    except Exception:
        return {"status":"UNREADABLE_ODG"},None
    rc,to=bounded(base+["--convert-to","pdf","--outdir",str(pdf_dir),str(odg)],110)
    pdf=pdf_dir/(pub.stem+".pdf")
    if to:return {"status":"PDF_TIMEOUT","odg_pages":pages},None
    if not pdf.is_file():return {"status":"PDF_NOT_CREATED","odg_pages":pages,"rc":rc},None
    return {"status":"IMPORTED","odg_pages":pages,"odg_content_xml_sha256":hash_bytes(content)},pdf

def make_grid(page):
    w,h=float(page.rect.width),float(page.rect.height)
    if w<=0 or h<=0 or (w*2)*(h*2)>MAX_PIXELS:
        raise ValueError("OVERSIZE_PAGE")
    pix=page.get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csRGB,alpha=False,annots=False)
    if pix.n!=3 or pix.width*pix.height>MAX_PIXELS:raise ValueError("BAD_PDF_PIXMAP")
    raw=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
    return raw.resize((64,64),Image.Resampling.BOX).tobytes(),(w,h)

def raster(pdf,entry,ref,reader_pair,reader_pages,cmp):
    result={"status":"RASTERED","pages":[],"page_count":0,"ranked_pages":0}
    with fitz.open(pdf) as doc:
        result["page_count"]=doc.page_count
        counts_match=(doc.page_count==int(entry["pdf_pages"])==reader_pair["candidate_pages"])
        result["counts_match_all_three"]=counts_match
        for i,page in enumerate(doc):
            p={"ordinal_page":i+1,"status":"NO_NATIVE_REFERENCE"}
            if i>=len(ref["pages"]):
                result["pages"].append(p);continue
            try:
                grid,(w,h)=make_grid(page)
                native=ref["pages"][i]
                source=comparator_reference(cmp,native)
                d=cmp.compare_grid(grid,source)
                r=reader_pages.get((entry["basename"],i+1))
                if r is None:raise ValueError("MISSING_READER_PAGE")
                delta=r["reference_media_extent_delta"]
                physical=abs(w-native["media_width_pt"])<=.05 and abs(h-native["media_height_pt"])<=.05
                reader_physical=abs(delta["width_pt"])<=.05 and abs(delta["height_pt"])<=.05
                p.update({"width_pt":round(w,5),"height_pt":round(h,5),
                          "physical_page_match":physical,
                          "reader_physical_page_match":reader_physical,
                          "libreoffice_changed_fraction":d["changed_cell_fraction"],
                          "reader_changed_fraction":r["changed_cell_fraction"],
                          "libreoffice_changed_cells":d["changed_cell_count"],
                          "libreoffice_mean_abs_rgb_delta":d["mean_abs_channel_delta"]})
                if counts_match and physical and reader_physical:
                    gap=r["changed_cell_fraction"]-d["changed_cell_fraction"]
                    winner=("LIBREOFFICE" if gap>TIE else "READER" if gap< -TIE else "NEAR_TIE")
                    p.update({"status":"COARSE_ORDINAL_MATCH","winner":winner,
                              "libreoffice_advantage":round(gap,7)})
                    result["ranked_pages"]+=1
                else:
                    p["status"]="PAGE_COUNT_OR_PHYSICAL_GEOMETRY_MISMATCH"
            except Exception as error:
                p["status"]="UNRANKED_RASTER_ERROR";p["error_class"]=type(error).__name__
            result["pages"].append(p)
    return result

def comparator_reference(cmp,ref):
    return cmp.reference_grid(ref)

def summary(data):
    valid=[r for r in data["cases"] if r.get("input_sha_verified") and r.get("input_unchanged")]
    imported=[r for r in valid if r.get("import",{}).get("status")=="IMPORTED"]
    eligible=[(r,p) for r in imported for p in r["raster"]["pages"] if p["status"]=="COARSE_ORDINAL_MATCH"]
    counts=Counter(p["winner"] for _,p in eligible)
    n=len(eligible)
    scores=lambda field:sum(p[field] for _,p in eligible)/n if n else None
    data["summary"]={
       "predeclared_donor_cohort":49,
       "source_sha_verified_and_unchanged":len(valid),
       "lo_import_success_count":len(imported),
       "lo_import_blocked_count":49-len(imported),
       "native_publisher_reference_pages":153,
       "reader_original_pdf_page_counts_match":sum(r["reader_page_count"]==r["native_pdf_page_count"] for r in data["cases"]),
       "lo_original_pdf_page_counts_match":sum(r["raster"]["page_count"]==r["native_pdf_page_count"] for r in imported),
       "ranked_pair_count":len({r["fixture"] for r,_ in eligible}),
       "ranked_ordinal_pages":n,
       "libreoffice_closer_pages":counts["LIBREOFFICE"],
       "reader_closer_pages":counts["READER"],
       "near_tie_pages":counts["NEAR_TIE"],
       "reader_mean_changed_fraction":scores("reader_changed_fraction"),
       "libreoffice_mean_changed_fraction":scores("libreoffice_changed_fraction"),
       "repeated_lo_rasters_identical_count":sum(
         r.get("repeat",{}).get("odg_identical") and r["repeat"].get("pdf_rasters_identical")
         for r in data["cases"] if r["fixture"].split("_")[0] in REPEAT),
       "malformed_cfb_rejected":data["negative"]["rejected"],
       "reference_surface_stage_unknown":True
    }
    extremes=sorted([{"fixture":r["fixture"],"page":p["ordinal_page"],
                      "gap":p["libreoffice_advantage"],"winner":p["winner"],
                      "reader_changed":p["reader_changed_fraction"],
                      "lo_changed":p["libreoffice_changed_fraction"]}
                      for r,p in eligible],key=lambda x:abs(x["gap"]),reverse=True)
    data["largest_differences"]=extremes[:18]
    return data["summary"]

def main():
    if len(sys.argv)!=4:raise SystemExit("usage: run.py RAR2_DIR CURRENT_READER_SUMMARY_JSON OUTPUT_DIR")
    root=Path(sys.argv[1]).resolve(); reader=Path(sys.argv[2]).resolve();out=Path(sys.argv[3]).resolve()
    out.mkdir(parents=True,exist_ok=True)
    source_pin(root)
    cmp=load_comparator(root)
    cases,refs,readpairs,readpages,excluded=setup(root,reader)
    lo=shutil.which("libreoffice") or shutil.which("soffice")
    if not lo:raise ValueError("LIBREOFFICE_MISSING")
    version=subprocess.run([lo,"--version"],capture_output=True,text=True,check=True).stdout.strip()
    data={"schema":"sk1.pub-t999.visual-ordinal.v1","task_id":"PUB-T-999",
          "rar2_commit":PRODUCT,"public_donor_commit":DONOR,
          "pair_manifest_blob":BLOBS["tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv"],
          "publisher_reference_blob":BLOBS["tools/corpus/receipts/publisher-visual-golden-batch-01-fingerprint-v1.json"],
          "comparator_blob":BLOBS["tools/cloud_reader_visual_fingerprint_v1.py"],
          "reader_main_actions_run":ACTION,"reader_artifact":ARTIFACT,
          "reader_artifact_zip_sha256":ARTIFACT_ZIP_SHA,
          "reader_summary_sha256":SUMMARY_SHA,
          "libreoffice_version":version,
          "pymupdf_version":getattr(fitz,"VersionBind","unknown"),
          "pillow_version":__import__("PIL").__version__,
          "native_publisher_ran":False,
          "native_publisher_grounding":"preexisting_signed_64x64_rgb_pdf_reference",
          "stage_of_reference_pdf_pages":"unknown",
          "comparison_limit":"coarse_ordinal_64x64_not_native_logical_page_or_full_resolution",
          "predeclared_excluded_no_donor_source":sorted(excluded),
          "raster_policy":{"dpi":144,"mode":"RGB","size":[64,64],"scale":"Pillow.BOX",
                           "threshold_channel_delta":12,"tie_deadband":TIE},
          "cases":[]}
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t999-") as td:
        cache=Path(td)
        for idx,entry in enumerate(cases):
            case=cache/("case-"+str(idx));case.mkdir()
            row={"fixture":entry["basename"],"pub_sha256":entry["pub_sha256"],
                 "pub_byte_len":int(entry["pub_bytes"]),
                 "reference_pdf_sha256":entry["pdf_sha256"],
                 "native_pdf_page_count":int(entry["pdf_pages"]),
                 "reader_page_count":readpairs[entry["basename"]]["candidate_pages"],
                 "input_sha_verified":False}
            data["cases"].append(row)
            try:
                source=download(entry,case);row["input_sha_verified"]=True
                conversion,pdf=convert(source,case/"first",lo)
                row["import"]=conversion
                if pdf:
                    row["raster"]=raster(pdf,entry,refs[entry["basename"]],
                                          readpairs[entry["basename"]],readpages,cmp)
                else:
                    row["raster"]={"status":"NOT_EVALUATED","pages":[],"page_count":0,"ranked_pages":0}
                row["input_unchanged"]=hash_bytes(source.read_bytes())==entry["pub_sha256"]
                if entry["basename"].split("_")[0] in REPEAT:
                    again,pdf2=convert(source,case/"repeat",lo)
                    repeat={"odg_identical":again.get("odg_content_xml_sha256")==conversion.get("odg_content_xml_sha256"),
                            "pdf_rasters_identical":False}
                    if pdf and pdf2:
                        try:
                            with fitz.open(pdf) as a,fitz.open(pdf2) as b:
                                repeat["pdf_rasters_identical"]=(
                                  len(a)==len(b) and
                                  [hash_bytes(make_grid(p)[0]) for p in a]==
                                  [hash_bytes(make_grid(p)[0]) for p in b])
                        except Exception:
                            repeat["pdf_rasters_identical"]=False
                    row["repeat"]=repeat
            except Exception as exc:
                row["error_class"]=(str(exc) if str(exc) in (
                   "DONOR_DOWNLOAD_ERROR","DONOR_PUB_SHA_OR_LENGTH_MISMATCH")
                   else type(exc).__name__)
                row.setdefault("raster",{"status":"NOT_EVALUATED","pages":[],"ranked_pages":0})
            shutil.rmtree(case,ignore_errors=True)
        case=cache/"negative";case.mkdir()
        original=download(cases[0],case)
        broken=bytearray(original.read_bytes());broken[0]^=0xff
        mutated=case/"broken_cfb.pub";mutated.write_bytes(broken)
        bad,_=convert(mutated,case/"invalid",lo)
        data["negative"]={"bytes_mutated":1,"rejected":bad["status"] in ("ODG_NOT_CREATED","UNREADABLE_ODG"),
                          "outcome":bad["status"],"counts_towards_49":False}
    totals=summary(data)
    (out/"report.json").write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("SK1 PUB-T-999",json.dumps(totals,sort_keys=True))
    return 0 if (totals["source_sha_verified_and_unchanged"]==49
                 and totals["repeated_lo_rasters_identical_count"]==2
                 and totals["malformed_cfb_rejected"]
                 and totals["ranked_ordinal_pages"]>=12) else 2

if __name__=="__main__":raise SystemExit(main())
