#!/usr/bin/env python3
"""PUB-T-984: real public PUB inverse Writer/whole-CFB holdout.
All PUB content stays in source-verified GitHub worker memory and temporary files.
"""
from __future__ import annotations
import argparse
from collections import Counter
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
SOURCE_SEL_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
INV_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
BASELINE_SHA_LIST_DIGEST="b9a0559613179f31e6ee9e0d75210cce523e4dafabfba6a3d2d660f086c0d8e2"
ORIGINAL_T971_ZIP_SHA256="055c1ec20ebfcbe17c2aad04bba5d11d942c159686ec49f43430463b7eee31bf"
BINARY="sk1_pub_t_984_inverse_cfb"
SCHEMA="sk1.cfb-diag-pub-t-984.inverse.v1"
HERE=Path(__file__).resolve().parent

def selection(ref:Path):
    spec=importlib.util.spec_from_file_location(
        "sk1_pub984_pinned_t971_selector",
        ref/"experiments/quill/val/pub-t-971/run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("pinned source selector missing")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.PIN==RAR2_PIN and mod.EXPECTED_REMNANT==47
    source=mod.fetcher()
    rows=mod.select_all_unused(source)
    fingerprints=[x["sha256"] for x in rows]
    assert len(fingerprints)==47
    digest=hashlib.sha256(("\n".join(fingerprints)+"\n").encode()).hexdigest()
    assert digest==BASELINE_SHA_LIST_DIGEST,"pinned T971 corpus fingerprints changed"
    return source,rows

def run_case(source,row:dict,binary:Path)->dict:
    result={
        "source_sha256":row["sha256"],
        "host":row["host"],
        "expected_source_bytes":row["size"],
        "status":"NOT_EVALUATED",
        "reason":"NOT_STARTED",
        "probe":None
    }
    try:
        payload=source.download(row)
    except Exception as exc:
        result["reason"]=source.safe_error(exc)
        return result
    result["status"]="SHA_VERIFIED"
    result["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-real-syid-984-") as temp:
        root=Path(temp)
        source_file=root/"source.pub"
        report_path=root/"receipt.json"
        source_file.write_bytes(payload)
        try:
            proc=subprocess.run(
                [str(binary),str(source_file),row["sha256"],str(report_path)],
                check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=360)
        except (OSError,subprocess.TimeoutExpired):
            result["status"]="PROBE_UNAVAILABLE"
            result["reason"]="PROCESS_OR_TIMEOUT"
            return result
        if proc.returncode or not report_path.is_file():
            result["status"]="PROBE_UNAVAILABLE"
            result["reason"]="PROCESS_FAILED"
            return result
        try:
            proof=json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            result["status"]="PROBE_UNAVAILABLE"
            result["reason"]="INVALID_JSON"
            return result
        if (proof.get("schema")!=SCHEMA
            or proof.get("source_sha256")!=row["sha256"]
            or proof.get("source_bytes")!=len(payload)
            or proof.get("publisher_native_acceptance")!="NOT_EVALUATED"
            or proof.get("product_pub_download_authorized") is not False):
            result["status"]="PROBE_UNAVAILABLE"
            result["reason"]="RECEIPT_INVALID"
            return result
        result["probe"]=proof
    return result

def byte_count_le(a:int,b:int)->int:
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),b.to_bytes(4,"little")))

def summary(rows:list[dict])->dict:
    origin=Counter()
    probe_states=Counter()
    baseline=Counter()
    inverse=Counter()
    changed=Counter()
    failures=[]
    original_head=[]
    normal_success_sha=set()
    total_stories=pairs=baseline_both=finals=matched=0
    live_max_relation=Counter()
    for row in rows:
        origin[row["status"]]+=1
        p=row["probe"]
        if p is None:
            continue
        probe_states[p["result"]]+=1
        hd=p.get("source_syid_first_dword")
        if hd is not None:
            original_head.append(hd)
            mx=p.get("source_syid_max_live_id")
            if mx is not None:
                live_max_relation["source_header_gt_max_live_syid"]+=int(hd>mx)
                live_max_relation["source_header_eq_max_live_syid"]+=int(hd==mx)
                live_max_relation["source_header_lt_max_live_syid"]+=int(hd<mx)
        if p["result"]!="EVALUATED":
            continue
        for story in p["stories"]:
            total_stories+=1
            for pair in story["pairs"]:
                pairs+=1
                baseline[pair["single_insert"]["status"]+"_INSERT"]+=1
                baseline[pair["single_delete"]["status"]+"_DELETE"]+=1
                if not pair["both_single_pass"]:
                    continue
                baseline_both+=1
                for arm,key in (("insert_then_delete","insert_delete"),
                                ("delete_then_insert","delete_insert")):
                    step=pair[arm]
                    inverse[step["status"]]+=1
                    if step["status"]!="HOSTED_PASS":
                        continue
                    finals+=1
                    normal_success_sha.add(row["source_sha256"])
                    raw=pair[key+"_raw"]
                    cfb=pair[key+"_cfb"]
                    expected_header=hd+2 if hd is not None and hd<=0xfffffffd else None
                    n=byte_count_le(hd,expected_header) if expected_header is not None else None
                    valid=(
                        expected_header is not None
                        and raw["equal_length"] is True
                        and raw["extra_bytes"]==0
                        and raw["changed_same_offset_bytes"]==n
                        and cfb["source_syid_first_dword"]==hd
                        and cfb["final_syid_first_dword"]==expected_header
                        and cfb["syid_first_dword_delta"]==2
                        and cfb["syid_first_dword_changed_bytes"]==n
                        and cfb["quill_differing_byte_positions_equal_len"]==n
                        and cfb["quill_changed_bytes_outside_syid_first_dword"]==0
                        and cfb["same_quill_TEXT_payload_bytes"] is True
                        and cfb["same_quill_story_syid_sequence"] is True
                        and cfb["same_quill_story_utf16_lengths"] is True
                        and cfb["matched_descriptor_sequence"] is True
                        and cfb["non_quill_streams_changed"]==0
                        and cfb["missing_cfb_paths"]==0
                        and cfb["added_cfb_paths"]==0
                        and cfb["cfb_entry_type_changes"]==0
                    )
                    changed["actual_raw_"+str(raw["changed_same_offset_bytes"])]+=1
                    if valid:matched+=1
                    else:
                        failures.append({
                            "source_sha256":row["source_sha256"],
                            "story_ordinal":story["story_ordinal"],
                            "offset_utf16":pair["offset_utf16"],
                            "arm":arm,
                            "expected_raw_bytes":n,
                            "observed_raw_bytes":raw["changed_same_offset_bytes"],
                            "observed_syid_delta":cfb["syid_first_dword_delta"],
                            "outside_syid":cfb["quill_changed_bytes_outside_syid_first_dword"],
                            "non_quill_changed":cfb["non_quill_streams_changed"]
                        })
    return {
        "source_plan_total":len(rows),
        "source_status":dict(sorted(origin.items())),
        "probe_status":dict(sorted(probe_states.items())),
        "verified_source_SHA":origin["SHA_VERIFIED"],
        "source_syid_header_observations":len(original_head),
        "natural_syid_header_min":min(original_head) if original_head else None,
        "natural_syid_header_max":max(original_head) if original_head else None,
        "natural_syid_low_byte_ge_fe":sum((x&255)>=254 for x in original_head),
        "natural_syid_header_vs_live_max":dict(sorted(live_max_relation.items())),
        "story_probes":total_stories,
        "original_fixed_second_ascii_pairs":pairs,
        "initial_writer_status":dict(sorted(baseline.items())),
        "initial_both_pass":baseline_both,
        "inverse_writer_status":dict(sorted(inverse.items())),
        "inverse_final_files":finals,
        "inverse_final_distinct_SHA":len(normal_success_sha),
        "inverse_matched_all_physical_bytes_except_syid":matched,
        "inverse_raw_byte_counts":dict(sorted(changed.items())),
        "physical_counterexamples":failures,
        "native_publisher_acceptance":"NOT_EVALUATED"
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--ref-corpus",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    binary=(args.rar2.resolve(strict=True)/
        "tools/native-pub-candidate-cli/target/release/examples"/BINARY)
    if not binary.is_file():
        ap.error("pinned physical inverse Writer harness not compiled")
    source,rows=selection(args.ref_corpus.resolve(strict=True))
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.cfb-val-pub-t-984.plan.v1",
        "rar2_pin":RAR2_PIN,
        "source_selector_pin":SOURCE_SEL_PIN,
        "physical_inverse_pin":INV_PIN,
        "reference_t971_original_zip_sha256":ORIGINAL_T971_ZIP_SHA256,
        "source_sha_list_lf_digest":BASELINE_SHA_LIST_DIGEST,
        "source_count":47,
        "host_count":37,
        "source_size_sum":28191744,
        "source_sha256":[x["sha256"] for x in rows],
        "max_stories_per_pub":3,
        "story_order":"Quill source descriptor ordinal",
        "offset_policy":"second ASCII alphanumeric UTF16 offset",
        "inverse_orders":["insert_then_delete","delete_then_insert"],
        "native_publisher_acceptance":"NOT_EVALUATED",
        "raw_pub_output_authorized":False,
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for row in executor.map(lambda x:run_case(source,x,binary),rows):
            records.append(row)
            (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    report={
        "schema":"sk1.cfb-val-pub-t-984.report.v1",
        "rar2_pin":RAR2_PIN,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "raw_pub_output_authorized":False,
        "summary":summary(records),
        "records":records
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    s=report["summary"]
    accepted=(s["inverse_final_distinct_SHA"]>=10
              and s["source_plan_total"]==47
              and s["inverse_final_files"]>0)
    print(json.dumps({
        "research_execution":"ACCEPTED" if accepted else "INCOMPLETE",
        "attempted_SHA":s["source_plan_total"],
        "sha_verified":s["verified_source_SHA"],
        "source_SYID_headers":s["source_syid_header_observations"],
        "inverse_complete":s["inverse_final_files"],
        "inverse_final_distinct_SHA":s["inverse_final_distinct_SHA"],
        "all_raw_syid_only":s["inverse_matched_all_physical_bytes_except_syid"],
        "counterexample_count":len(s["physical_counterexamples"])
    },sort_keys=True))
    return 0 if accepted else 2

if __name__=="__main__":
    raise SystemExit(main())
