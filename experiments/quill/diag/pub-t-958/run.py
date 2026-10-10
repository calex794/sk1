#!/usr/bin/env python3
"""PUB-T-958: observed post-deletion FD geometry predicts reverse insertion gate, same source/Story/offset and pinned rar2.

Predeclared exact corpus + 194 offsets + 77 baseline independently accepted pairs.
Raw PUB bytes remain in TemporaryDirectory. Only safe scalars and hashes persist.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[3]
LEGACY = BASE / "sk1-exp-001" / "run.py"
S = importlib.util.spec_from_file_location("sk1_exp001_safe_intake", LEGACY)
assert S and S.loader
source = importlib.util.module_from_spec(S)
S.loader.exec_module(source)

PIN = "703808408fd919e564a90cdc236e81db3c04af8b"
EXPECTED_PAIRS = 194
EXPECTED_STORIES = 65
EXPECTED_BOTH_PASS = {"first":9,"second":34,"middle":34}
EXPECTED_BY_SLOT = {"first":65,"second":65,"middle":64}
BINARY = "sk1_pub_t_958_fd_guard"

def test_file(row:dict,binary:Path)->dict:
    result={
        "source_sha256":row["sha256"],
        "source_type":row["source_type"],
        "source_bytes":row["size"],
        "status":"NOT_EVALUATED",
        "reason":"NOT_STARTED",
    }
    try:
        data=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(data)!=row["size"] or source.digest(data)!=row["sha256"]:
            result["reason"]="SOURCE_SHA_OR_SIZE_DRIFT"
            return result
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            result["reason"]="NON_CFB"
            return result
        with tempfile.TemporaryDirectory(prefix="sk1-pubt956-") as tmp:
            path=Path(tmp)/"input.pub"
            output=Path(tmp)/"receipt.json"
            path.write_bytes(data)
            proc=subprocess.run([str(binary),str(path),row["sha256"],str(output)],
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=360)
            if proc.returncode or not output.is_file():
                result["reason"]="RUST_PROBE_FAILED"
                return result
            receipt=json.loads(output.read_text(encoding="utf-8"))
        if (receipt.get("schema")!="sk1.quill-diag-pub-t-958.fd-geometry.v1" or
            receipt.get("source_sha256")!=row["sha256"] or
            receipt.get("source_bytes")!=row["size"] or
            receipt.get("publisher_native_acceptance")!="NOT_EVALUATED" or
            receipt.get("product_pub_download_authorized") is not False):
            result["reason"]="RUST_RECEIPT_INVALID"
            return result
        result.update(status="EVALUATED",reason=receipt["result"],
                      eligible_story_count=receipt.get("eligible_story_count",0),
                      stories=receipt.get("stories",[]))
    except Exception as e:
        # Never log raw fetch/Writer error strings: they may include PUB contents/URLs.
        result["reason"]=type(e).__name__.upper()
    return result

def summarize(rows:list[dict])->dict:
    counts=Counter()
    by_slot=Counter()
    baseline_pass=Counter()
    revert_insert=Counter()
    revert_delete=Counter()
    physical=Counter()
    witnesses=[]
    total_stories=0
    for row in rows:
        counts[row["status"]]+=1
        if row["status"]!="EVALUATED":
            continue
        for story in row["stories"]:
            total_stories+=1
            for item in story["pairs"]:
                slot=item["slot"]
                by_slot[slot]+=1
                if item["both_single_pass"]:
                    baseline_pass[slot]+=1
                    ir=item["insert_then_delete"]["status"]
                    dr=item["delete_then_insert"]["status"]
                    revert_insert[ir]+=1
                    revert_delete[dr]+=1
                    physical["both_reverted_semantically"]+=int(ir==dr=="HOSTED_PASS")
                    physical["only_insert_delete"]+=int(ir=="HOSTED_PASS" and dr!="HOSTED_PASS")
                    physical["only_delete_insert"]+=int(dr=="HOSTED_PASS" and ir!="HOSTED_PASS")
                    physical["both_failed"]+=int(ir!="HOSTED_PASS" and dr!="HOSTED_PASS")
                    if ir=="HOSTED_PASS":
                        physical["insert_delete_byte_matches_original"]+=int(
                            item["insert_delete_returns_original_bytes"] is True)
                    if dr=="HOSTED_PASS":
                        physical["delete_insert_byte_matches_original"]+=int(
                            item["delete_insert_returns_original_bytes"] is True)
                    if ir==dr=="HOSTED_PASS":
                        physical["cross_order_final_bytes_match"]+=int(
                            item["both_final_byte_equal"] is True)
                    if item["ambiguous_reverse_delete_insert_offset"]:
                        physical["reverse_position_ambiguous_cases"]+=1
                    if (ir!="HOSTED_PASS" or dr!="HOSTED_PASS" or
                        item["insert_delete_returns_original_bytes"] is False or
                        item["delete_insert_returns_original_bytes"] is False or
                        item["both_final_byte_equal"] is False):
                        witnesses.append({
                            "source_sha256":row["source_sha256"],
                            "story_ordinal":story["story_ordinal"],
                            "slot":slot,
                            "offset_utf16":item["offset_utf16"],
                            "ambiguous_reverse_offset":item["ambiguous_reverse_delete_insert_offset"],
                            "ir_status":ir,"dr_status":dr,
                            "ir_exact_original_bytes":item["insert_delete_returns_original_bytes"],
                            "dr_exact_original_bytes":item["delete_insert_returns_original_bytes"],
                            "cross_order_bytes_equal":item["both_final_byte_equal"]
                        })
    return {
        "source_count":len(rows),
        "source_status":dict(sorted(counts.items())),
        "story_count":total_stories,
        "paired_offsets":sum(by_slot.values()),
        "by_slot":dict(sorted(by_slot.items())),
        "both_single_pass_by_slot":dict(sorted(baseline_pass.items())),
        "both_single_pass":sum(baseline_pass.values()),
        "insert_then_delete_outcomes":dict(sorted(revert_insert.items())),
        "delete_then_insert_outcomes":dict(sorted(revert_delete.items())),
        "physical_and_semantic":dict(sorted(physical.items())),
        "negative_and_divergent_witnesses":witnesses
    }


def summarize_fd(rows:list[dict])->dict:
    matrix=Counter()
    diag=Counter()
    hits=[]
    samples=0
    for row in rows:
        if row["status"]!="EVALUATED":continue
        for story in row["stories"]:
            for case in story["pairs"]:
                if not case["both_single_pass"]:continue
                samples+=1
                fd=case.get("fd_guard_diagnostic")
                if not isinstance(fd,dict):
                    matrix["NOT_EVALUATED"]+=1
                    continue
                predicted=fd["fd_after_delete_at_reverse_insert_start"]
                outcome=case["delete_then_insert"]
                is_fd_error=(outcome["status"]=="WRITER_BLOCKED" and
                             outcome["writer_code"]=="quill_insertion_at_fd_boundary")
                is_pass=(outcome["status"]=="HOSTED_PASS")
                if predicted and is_fd_error: matrix["TP"]+=1
                elif not predicted and is_pass:matrix["TN"]+=1
                elif predicted and is_pass:matrix["FP"]+=1
                elif not predicted and is_fd_error:matrix["FN"]+=1
                else:matrix["OTHER"]+=1
                for key in ("original_fd_boundary_at_insert_start",
                            "original_fd_boundary_at_deleted_end",
                            "fdpp_after_hit","fdpc_after_hit",
                            "story_text_start_byte_preserved",
                            "fdpp_delete_shift_formula_matches",
                            "fdpc_delete_shift_formula_matches"):
                    diag[key+"_true"]+=int(fd[key] is True)
                diag["post_hit_count"]+=int(predicted)
                diag["source_fdpp_total"]+=fd["source_fdpp_count"]
                diag["source_fdpc_total"]+=fd["source_fdpc_count"]
                if predicted or not is_pass:
                    hits.append({
                        "source_sha256":row["source_sha256"],
                        "story_ordinal":story["story_ordinal"],
                        "slot":case["slot"],
                        "offset_utf16":case["offset_utf16"],
                        "source_fd_at_deleted_end":fd["original_fd_boundary_at_deleted_end"],
                        "post_fdpp_hit":fd["fdpp_after_hit"],
                        "post_fdpc_hit":fd["fdpc_after_hit"],
                        "nearest_fd_bytes":fd["post_delete_nearest_fd_distance_bytes"],
                        "reverse_insert_writer_status":outcome["status"],
                        "reverse_insert_writer_code":outcome.get("writer_code")
                    })
    return {
        "eligible_doublepass":samples,
        "matrix":dict(sorted(matrix.items())),
        "read_only_geometry_counters":dict(sorted(diag.items())),
        "hit_or_failure_witnesses":hits
    }

def main()->int:
    arg=argparse.ArgumentParser()
    arg.add_argument("--rar2",type=Path,required=True)
    arg.add_argument("--output",type=Path,required=True)
    options=arg.parse_args()
    root=options.rar2.resolve(strict=True)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples"/BINARY
    if not binary.is_file():arg.error("pinned Writer probe was not built")
    rows=source.candidates(source.load_manifest(None))
    if len(rows)!=26 or len(set(x["sha256"] for x in rows))!=26:
        raise ValueError("original corpus manifest drift")
    if sum(x["size"] for x in rows)>source.MAX_TOTAL_BYTES:
        raise ValueError("source byte budget exceeded")
    out=options.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.pub-t-958.plan.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "source_sha256":[x["sha256"] for x in rows],
        "predeclared_expected_194_offsets":EXPECTED_PAIRS,
        "predeclared_expected_77_doublepass_pairs":EXPECTED_BOTH_PASS,
        "two_reverse_arms":["insert_then_delete","delete_then_insert"],
        "scope":"read-only FDPP/FDPC predictor from original and actual delete-intermediate; Writer unchanged"
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row in rows:
        records.append(test_file(row,binary))
        (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    s=summarize(records)
    s["fd_guard"]=summarize_fd(records)
    report={
        "schema":"sk1.pub-t-958.report.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":s,
        "records":records
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    passed=(s["source_status"].get("EVALUATED",0)==26
       and s["story_count"]==EXPECTED_STORIES
       and s["paired_offsets"]==EXPECTED_PAIRS
       and s["by_slot"]==EXPECTED_BY_SLOT
       and s["both_single_pass_by_slot"]==EXPECTED_BOTH_PASS
       and s["fd_guard"]["eligible_doublepass"]==77
       and s["fd_guard"]["matrix"].get("NOT_EVALUATED",0)==0)
    if not passed:
        print(json.dumps({"research_result":"INCOMPLETE_OR_BASELINE_DRIFT",
                          "sources":s["source_status"],"story_count":s["story_count"],
                          "paired_offsets":s["paired_offsets"],
                          "by_slot":s["by_slot"],
                          "both_single_pass_by_slot":s["both_single_pass_by_slot"]},sort_keys=True))
        return 2
    print(json.dumps({"research_result":"COMPLETED","summary":{
        "source_count":s["source_count"],"story_count":s["story_count"],
        "paired_offsets":s["paired_offsets"],"both_single_pass":s["both_single_pass"],
        "insert_then_delete_outcomes":s["insert_then_delete_outcomes"],
        "delete_then_insert_outcomes":s["delete_then_insert_outcomes"],
        "physical_and_semantic":s["physical_and_semantic"],
        "fd_guard":s["fd_guard"]
    }},indent=2))
    return 0
if __name__=="__main__":
    sys.exit(main())
