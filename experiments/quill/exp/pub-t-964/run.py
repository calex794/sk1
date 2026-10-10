#!/usr/bin/env python3
"""PUB-T-964 source-safe mixed (+1/-1) changes across two distinct Stories."""
from __future__ import annotations
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[2]
SPEC=importlib.util.spec_from_file_location("sk1_pub964_safe_public_intake",BASE/"sk1-exp-001"/"run.py")
assert SPEC and SPEC.loader
source=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
PREV_960_SHA="0bd1efc90f1e891e8a07e1bd1c0b673c45328a5c"
PREV_960_ZIP="aaa280bc3c859f149b583fe2d7b1e4eea2a1f0faaaaf584f80fa3e79a2ff3c5b"
PREV_956_SHA="08abf5c7d92fb5ca56fd3ff84009309120fcf52c"
PREV_956_ZIP="afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427"
SOURCE_SHA256=(
    "155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba",
    "942759e9d092e60f5ec4af574219590de729b2091abec94fd79c3563eccaaa70",
    "9765b8737b57c90ce7503454edc6ad7c2c1559b0d24fa9ac1309db4b37cdc3f6",
    "b1faaba988e88b4134dc8a495cb68c6f7496f3fbaedcba65fa6e02f39b29b621",
    "53388a22c9513488895785d21628b8bbc9dad4c7617ab7f639bd346c42d68f78",
    "9d6580b5a1c21543803410d44dd6e0a76aaa4b45ef6652e52afb9fbe4087bd06",
    "d2239f6c60f2a7520c02f01e37ad5899873366e4481fc6a1952d58f074d508b1",
    "b61be87eda0fbf77249a51993da5fe744446bc8ff0d25d4a922e4e29f8f29cd1",
    "6c6af8064f91ad5321f76c97c00b1a6564794d92614373334de23e2759294aaa",
    "a7679f3ae2a14760d17e1c50f13912266369aecac52f953983923766fe100ebf",
    "1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e",
)
EXPECTED_ACCEPTED={sha:(2 if sha==SOURCE_SHA256[-1] else 3) for sha in SOURCE_SHA256}
EXPECTED_UNORDERED_PAIRS=31
EXPECTED_ORIENTATIONS=62
EXPECTED_SEQUENCES=124
BINARY_NAME="sk1_pub_t_964_cross_story_mixed"

def admitted()->list[dict]:
    all_sources=source.candidates(source.load_manifest(None))
    assert len(all_sources)==26 and len({r["sha256"] for r in all_sources})==26
    indexed={r["sha256"]:r for r in all_sources}
    assert len(SOURCE_SHA256)==11 and len(set(SOURCE_SHA256))==11
    assert all(k in indexed for k in SOURCE_SHA256)
    selected=[indexed[sha] for sha in SOURCE_SHA256]
    assert sum(r["size"] for r in selected)<=source.MAX_TOTAL_BYTES
    return selected

def evaluate(row:dict,binary:Path)->dict:
    rec={"source_sha256":row["sha256"],"source_type":row["source_type"],
        "source_bytes":row["size"],"status":"NOT_EVALUATED","reason":"NOT_STARTED"}
    try:
        raw=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(raw)!=row["size"] or source.digest(raw)!=row["sha256"]:
            rec["reason"]="SOURCE_SHA_OR_SIZE_DRIFT";return rec
        if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            rec["reason"]="NON_CFB_SOURCE";return rec
        with tempfile.TemporaryDirectory(prefix="sk1-pub-t-964-") as temp:
            inp=Path(temp)/"source.pub"
            out=Path(temp)/"receipt.json"
            inp.write_bytes(raw)
            cp=subprocess.run([str(binary),str(inp),row["sha256"],str(out)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=900)
            if cp.returncode!=0 or not out.is_file():
                rec["reason"]="PROBE_UNAVAILABLE";return rec
            detail=json.loads(out.read_text(encoding="utf8"))
        if (detail.get("schema")!="sk1.quill-exp-pub-t-964.cross-story-mixed.v1"
            or detail.get("source_sha256")!=row["sha256"]
            or detail.get("source_bytes")!=row["size"]
            or detail.get("native_publisher_acceptance")!="NOT_EVALUATED"
            or detail.get("product_pub_download_authorized") is not False):
            rec["reason"]="INVALID_SOURCE_RECEIPT";return rec
        rec.update({"status":"EVALUATED","reason":detail["result"],
            "eligible_story_count":detail["eligible_story_count"],
            "single_controls":detail["single_controls"],"pairs":detail["pairs"]})
        return rec
    except Exception:
        rec["reason"]="BOUNDED_SOURCE_OR_RUNTIME_ERROR"
        return rec

def summarize(records:list[dict])->dict:
    status=Counter(); singles=Counter();excluded=Counter();counts=Counter()
    arms_id=Counter();arms_di=Counter();finals=Counter();semantics=Counter()
    negatives=[]
    for src in records:
        status[src["status"]]+=1
        if src["status"]!="EVALUATED":continue
        for control in src["single_controls"]:
            counts["attempted_story"]+=1
            x,y=control["single_insert"],control["single_delete"]
            both=x["status"]==y["status"]=="HOSTED_PASS"
            singles["both_PASS" if both else "not_both_PASS"]+=1
            if not both:
                excluded[x.get("writer_code",x["status"])] += 1
                excluded[y.get("writer_code",y["status"])] += 1
        for row in src["pairs"]:
            counts["assignments"]+=1
            a=row["insert_then_delete_second"]["status"]
            b=row["delete_then_insert_second"]["status"]
            arms_id[a]+=1;arms_di[b]+=1
            if a=="HOSTED_PASS":
                semantics["ID_" + ("PASS" if row["insert_then_delete_final_stories_match"] else "FAIL")]+=1
            if b=="HOSTED_PASS":
                semantics["DI_" + ("PASS" if row["delete_then_insert_final_stories_match"] else "FAIL")]+=1
            if a==b=="HOSTED_PASS":
                same=row["both_final_byte_equal"]
                finals["BYTE_EQUAL" if same else "BYTE_DIFFERENT"]+=1
            else:
                finals["NOT_BOTH_PASS"]+=1
            if (a!="HOSTED_PASS" or b!="HOSTED_PASS" or
                row["both_final_byte_equal"] is False or
                row["insert_then_delete_final_stories_match"] is False or
                row["delete_then_insert_final_stories_match"] is False):
                negatives.append({
                    "source_sha256":src["source_sha256"],
                    "insert_story_ordinal":row["insert_story_ordinal"],
                    "delete_story_ordinal":row["delete_story_ordinal"],
                    "insert_offset_utf16":row["insert_offset_utf16"],
                    "delete_offset_utf16":row["delete_offset_utf16"],
                    "insert_then_delete_outcome":a,
                    "delete_then_insert_outcome":b,
                    "insert_then_delete_guard":row["insert_then_delete_second"].get("writer_code"),
                    "delete_then_insert_guard":row["delete_then_insert_second"].get("writer_code"),
                    "both_final_byte_equal":row["both_final_byte_equal"]
                })
    return {
        "predeclared_sources":len(records),
        "source_status":dict(sorted(status.items())),
        "attempted_single_story_controls":counts["attempted_story"],
        "both_single_operations_pass_controls":singles["both_PASS"],
        "excluded_single_story_results":dict(sorted(excluded.items())),
        "unordered_story_pairs":counts["assignments"]//2,
        "mixed_sign_assignments":counts["assignments"],
        "ordered_chains":2*counts["assignments"],
        "insert_then_delete_second_outcomes":dict(sorted(arms_id.items())),
        "delete_then_insert_second_outcomes":dict(sorted(arms_di.items())),
        "final_story_semantic_checks":dict(sorted(semantics.items())),
        "cross_order_final_byte_equal":dict(sorted(finals.items())),
        "negative_or_noncommuting_witnesses":negatives
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--rar2",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    root=args.rar2.resolve(strict=True)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples"/BINARY_NAME
    if not binary.is_file():p.error("pinned experimental Rust executable absent")
    admitted_sources=admitted()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.pub-t-964.plan.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "prior_960_scientific_sha":PREV_960_SHA,
        "prior_960_evidence_zip_sha256":PREV_960_ZIP,
        "prior_956_scientific_sha":PREV_956_SHA,
        "prior_956_evidence_zip_sha256":PREV_956_ZIP,
        "source_sha256":list(SOURCE_SHA256),
        "single_slot":"second ASCII alphanumeric",
        "source_admission":"SHA-pinned 11 previous 960 sources; positive only if both standalone insert/delete Writer PASS",
        "expected_attempted_story_controls":33,
        "expected_both_pass_story_controls":32,
        "expected_tokn_blocked_story_controls":1,
        "expected_unordered_story_pairs":EXPECTED_UNORDERED_PAIRS,
        "expected_mixed_sign_assignments":EXPECTED_ORIENTATIONS,
        "expected_ordered_chains":EXPECTED_SEQUENCES,
        "unit_of_independence":"source_sha256, not Story/pair/chain",
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf8")
    records=[]
    for src in admitted_sources:
        records.append(evaluate(src,binary))
        (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf8")
    summary=summarize(records)
    report={
        "schema":"sk1.pub-t-964.report.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":summary,"records":records
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    pass_admission=(
        summary["source_status"]=={"EVALUATED":11}
        and all(x.get("reason")=="EVALUATED" for x in records)
        and all(x.get("eligible_story_count")==3 for x in records)
        and all(sum(c["single_insert"]["status"]==c["single_delete"]["status"]=="HOSTED_PASS"
                    for c in x["single_controls"])==EXPECTED_ACCEPTED[x["source_sha256"]]
                for x in records)
        and summary["attempted_single_story_controls"]==33
        and summary["both_single_operations_pass_controls"]==32
        and summary["excluded_single_story_results"]=={"quill_token_layer":2}
        and summary["unordered_story_pairs"]==31
        and summary["mixed_sign_assignments"]==62
        and summary["ordered_chains"]==124
        and sum(summary["insert_then_delete_second_outcomes"].values())==62
        and sum(summary["delete_then_insert_second_outcomes"].values())==62
    )
    print(json.dumps({
        "result":"COMPLETE" if pass_admission else "NOT_EVALUATED",
        "summary":summary},sort_keys=True))
    return 0 if pass_admission else 2

if __name__=="__main__":sys.exit(main())
