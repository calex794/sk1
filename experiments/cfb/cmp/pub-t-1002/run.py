#!/usr/bin/env python3
"""Physically run a pinned actual Viewer/PUB SafePreview candidate on seven
public original PUBs. Only numerical and digest evidence ever uploaded.
"""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen

RAR2="5a745034afd002d968f96eda5cc17d816e621fef"
DONOR="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
PAIR_BLOB="2c2b03652e79390befe55f2889dbc248eb2abe01"
DECODE_BLOB="c6ed97b7081d3cd3915968d142d648253ddbe1e1"
IDS=("001","021","022","023","025","043","073")
MIME=("image/jpeg","image/png")

def h(b):return hashlib.sha256(b).hexdigest()
def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,check=True,text=True,
                          capture_output=True,timeout=25).stdout.strip()

def fetch_pub(row):
    url=(f"https://raw.githubusercontent.com/Lalalalendia/lalamu/{DONOR}/pub-corpus/"
         f"corpus/native/unclassified/{row['pub_sha256']}.pub")
    for trial in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":"SK1-PUB-T1002-offline-lab"}),timeout=75) as q:
                b=q.read(30000000)
            break
        except Exception:
            if trial==2:raise RuntimeError("PINNED_PUBLIC_DONOR_UNAVAILABLE")
            time.sleep(2)
    if h(b)!=row["pub_sha256"] or len(b)!=int(row["pub_bytes"]):
        raise RuntimeError("ORIGINAL_PUB_SHA_OR_SIZE_MISMATCH")
    return b

def main():
    if len(sys.argv)!=4:
        raise SystemExit("run.py RAR2_REPO TEMP_RUST_EXEC OUTPUT_JSON")
    repo=Path(sys.argv[1]).resolve()
    exe=Path(sys.argv[2]).resolve()
    result=Path(sys.argv[3]).resolve()
    if not exe.is_file():raise RuntimeError("RUST_IMAGE_LAB_MISSING")
    if git(repo,"rev-parse","HEAD")!=RAR2:
        raise RuntimeError("RAR2_EXACT_SOURCE_COMMIT_DRIFT")
    pth="tools/corpus/receipts/publisher-visual-golden-batch-01-pairs.csv"
    if git(repo,"hash-object",pth)!=PAIR_BLOB:
        raise RuntimeError("NATIVE_PUB_MANIFEST_DRIFT")
    if git(repo,"hash-object","crates/chaptera-image-decode-contract/src/lib.rs")!=DECODE_BLOB:
        raise RuntimeError("EXISTING_IMAGE_DECODE_CONTRACT_DRIFT")
    with (repo/pth).open() as f:
        allrows=list(csv.DictReader(f))
    cases={r["basename"].split("_")[0]:r for r in allrows}
    if len(allrows)!=55 or not set(IDS)<=set(cases):
        raise RuntimeError("NATIVE_REFERENCE_COHORT_DRIFT")
    output={
       "schema":"sk1.pub-t1002.pinned-seven-safe-preview-lab.v1",
       "task_id":"PUB-T-1002",
       "rar2_commit":RAR2,
       "donor_commit":DONOR,
       "pairs_git_blob":PAIR_BLOB,
       "decode_contract_source_git_blob":DECODE_BLOB,
       "image_decoder":"real chaptera-image-decode-contract",
       "viewer_source":"real pub-viewer open_pub_bundle",
       "product_or_host_modified":False,
       "host_browser_safe_preview_admitted":False,
       "public_fixture_count":7,
       "fixtures":[]
    }
    with tempfile.TemporaryDirectory(prefix="sk1-t1002-preview-") as tmp:
        root=Path(tmp)
        for id in IDS:
            row=cases[id]
            payload=fetch_pub(row)
            source_file=root/"source.pub"
            json_file=root/"local-safe-receipt.json"
            source_file.write_bytes(payload)
            process=subprocess.run([str(exe),str(source_file),row["pub_sha256"],str(json_file)],
                                   capture_output=True,timeout=240,check=False)
            # No stderr/stdout from untrusted source is ever published.
            if process.returncode or not json_file.is_file():
                # Allowlist only fixed diagnostic codes, never untrusted stderr text or file paths.
                known = ("negative_or_alpha_positive_contract_failed",
                         "original_pub_sha256_mismatch",
                         "real RAR2 Viewer source geometry",
                         "original PUB SHA mismatch")
                stderr = process.stderr.decode("utf-8",errors="replace")[-4000:]
                cause = next((s.replace(" ","_") for s in known if s in stderr), "unclassified")
                raise RuntimeError(f"RUST_LAB_FAILED_ID_{id}_{cause}")
            parsed=json.loads(json_file.read_text())
            if parsed["schema"]!="sk1-pub-t1002-image-preview-candidate.v1":
                raise RuntimeError("INVALID_EXPERIMENT_RECEIPT")
            if parsed["product_pub_sha256"]!=row["pub_sha256"] or parsed["product_pub_bytes"]!=len(payload):
                raise RuntimeError("EXPERIMENT_SOURCE_PROVENANCE_MISMATCH")
            if parsed["original_pub_or_image_bytes_exported"] is not False:
                raise RuntimeError("SOURCE_ESCAPED_EXPERIMENT")
            if not all(v is True for v in parsed["negative_controls"].values()):
                raise RuntimeError("NEGATIVE_CONTROLS_NOT_GREEN")
            for image in parsed["resources"]:
                if image["status"]=="encoded_candidate_only_not_browser_safe":
                    if not all(image.get(p) is True for p in (
                        "fresh_encoding_deterministic","source_bytes_not_forwarded",
                        "separate_derivative_identity","metadata_stripped_by_reconstruction",
                        "host_acceptance_not_executed")):
                        raise RuntimeError("DERIVED_IDENTITY_OR_SAFETY_NOT_PROVEN")
                    if image["derived_sha256"]==image["source_sha256"]:
                        raise RuntimeError("DERIVED_EQUALS_SOURCE")
                    if image["source_mime"] not in MIME:
                        raise RuntimeError("OUT_OF_SCOPE_IMAGE_CODEC_ADMITTED")
            output["fixtures"].append({"name":row["basename"],"source_sha256":row["pub_sha256"],
                "public_source_byte_len":len(payload),
                "source_verified":True,
                "reference_pdf_page_count":int(row["pdf_pages"]),
                "result":parsed})
            source_file.unlink();json_file.unlink()
    totals={
       "image_count":sum(x["result"]["viewer_image_count"] for x in output["fixtures"]),
       "source_exact_accepted_to_new_candidate":sum(x["result"]["candidate_count"] for x in output["fixtures"]),
       "source_exact_fail_closed":sum(x["result"]["failed_closed_count"] for x in output["fixtures"]),
       "non_source_derived_control_count":sum(x["result"]["already_derived_viewer_count"] for x in output["fixtures"]),
       "new_candidate_output_bytes":sum(x["result"]["aggregate_preview_bytes"] for x in output["fixtures"]),
       "source_exact_admitted_original_to_browser":0,
       "original_7_pub_sha_verified":7,
       "host_safe_preview_admission_pending":True
    }
    output["summary"]=totals
    r22=next(x for x in output["fixtures"] if x["name"].startswith("022_"))["result"]
    image22=[z for z in r22["resources"] if z["source_exact"]]
    if len(image22)!=1 or image22[0]["source_encoded_bytes"]!=4869956:
        raise RuntimeError("022_ORIGINAL_JPEG_IDENTITY_DRIFT")
    output["control_022"]={
       "source_exact_original_image":True,
       "mime":"image/jpeg",
       "source_bytes":4869956,
       "candidate_status":image22[0]["status"],
       "derived_new_encoded_bytes":image22[0].get("derived_encoded_bytes"),
       "sampled_mean_abs_channel_delta":image22[0].get("pixel_comparison",{}).get("sampled_mean_abs_channel_delta"),
       "original_never_delivered_to_browser":True
    }
    # Emit only the source-safe numerical receipt before an acceptance error so
    # the failure *class* can be diagnosed without uploading untrusted images.
    result.parent.mkdir(parents=True,exist_ok=True)
    result.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    if image22[0]["status"]!="encoded_candidate_only_not_browser_safe":
        raise RuntimeError("022_REQUIRED_DECODER_CANDIDATE_NOT_CREATED")
    if totals["source_exact_accepted_to_new_candidate"] < 1:
        raise RuntimeError("NO_SAFE_DERIVED_CANDIDATE_CREATED")
    print(json.dumps(totals,sort_keys=True))
    print(json.dumps(output["control_022"],sort_keys=True))

if __name__=="__main__":main()
