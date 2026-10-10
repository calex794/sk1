#!/usr/bin/env python3
"""PUB-T-960: predeclared different-Story delete/delete order probe.

No Writer implementation. The only Writer/Reader/Editor belongs to pinned rar2.
Temporary PUB bytes and text never appear in public receipts or logs.
"""
from __future__ import annotations
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[3]
LEGACY = BASE / "sk1-exp-001" / "run.py"
SPEC = importlib.util.spec_from_file_location("sk1_exp001_safe_intake", LEGACY)
assert SPEC is not None and SPEC.loader is not None
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)

PIN = "703808408fd919e564a90cdc236e81db3c04af8b"
SOURCE_SHA256 = (
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
EXPECTED_PASS_COUNTS = {sha:(2 if sha == SOURCE_SHA256[-1] else 3) for sha in SOURCE_SHA256}
EXPECTED_PAIRS = 31
EXPECTED_CHAINS = 62
BINARY_NAME = "sk1_pub_t_960_cross_story"


def admitted_sources() -> list[dict]:
    indexed = {r["sha256"]: r for r in source.candidates(source.load_manifest(None))}
    selected = []
    if len(SOURCE_SHA256) != 11 or len(set(SOURCE_SHA256)) != 11:
        raise ValueError("predeclared independent source sample invalid")
    for sha in SOURCE_SHA256:
        if sha not in indexed:
            raise ValueError("source SHA missing from historic allowlisted manifest")
        selected.append(indexed[sha])
    if sum(r["size"] for r in selected) > source.MAX_TOTAL_BYTES:
        raise ValueError("source download budget exceeded")
    return selected


def evaluate_source(row: dict, binary: Path) -> dict:
    receipt = {
        "source_sha256":row["sha256"],
        "source_type":row["source_type"],
        "source_bytes":row["size"],
        "status":"NOT_EVALUATED",
        "reason":"NOT_STARTED",
    }
    try:
        data = source.retrieve(row["url"], min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(data) != row["size"] or source.digest(data) != row["sha256"]:
            receipt["reason"] = "SOURCE_SHA_OR_SIZE_DRIFT"
            return receipt
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            receipt["reason"] = "NON_CFB_SOURCE"
            return receipt
        with tempfile.TemporaryDirectory(prefix="sk1-pub-t-960-") as tmp:
            inp=Path(tmp)/"source.pub"
            out=Path(tmp)/"receipt.json"
            inp.write_bytes(data)
            p=subprocess.run([str(binary),str(inp),row["sha256"],str(out)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             check=False,timeout=450)
            if p.returncode or not out.exists():
                receipt["reason"]="EXPERIMENT_PROBE_FAILED"
                return receipt
            detail=json.loads(out.read_text(encoding="utf-8"))
        if (detail.get("schema")!="sk1.quill-exp-pub-t-960.inter-story.v1"
            or detail.get("source_sha256")!=row["sha256"]
            or detail.get("source_bytes")!=row["size"]
            or detail.get("native_publisher_acceptance")!="NOT_EVALUATED"
            or detail.get("product_pub_download_authorized") is not False):
            receipt["reason"]="INVALID_RUST_RECEIPT"
            return receipt
        receipt.update({
            "status":"EVALUATED",
            "reason":detail["result"],
            "eligible_story_count":detail["eligible_story_count"],
            "single_controls":detail["single_controls"],
            "pairs":detail["pairs"],
        })
    except Exception as exc:
        # Raw exception strings may disclose URLs/paths/input bytes; never log.
        receipt["reason"] = type(exc).__name__.upper()
    return receipt


def summarize(rows: list[dict]) -> dict:
    source_status=Counter()
    outcome_a_then_b=Counter()
    outcome_b_then_a=Counter()
    final_same=Counter()
    final_semantics=Counter()
    witnesses=[]
    selected_story_total=0
    attempted_story_total=0
    excluded_story_results=Counter()
    pairs_count=0
    for src in rows:
        source_status[src["status"]]+=1
        if src["status"]!="EVALUATED":
            continue
        controls=src.get("single_controls",[])
        attempted_story_total+=len(controls)
        for control in controls:
            if control["single_delete"]["status"]=="HOSTED_PASS":
                selected_story_total+=1
            else:
                result=control["single_delete"]
                excluded_story_results[result.get("writer_code",result["status"])]+=1
        for pair in src.get("pairs",[]):
            pairs_count+=1
            ab=pair["a_then_b_second"]["status"]
            ba=pair["b_then_a_second"]["status"]
            outcome_a_then_b[ab]+=1
            outcome_b_then_a[ba]+=1
            if ab=="HOSTED_PASS":
                final_semantics["A_THEN_B_"+("PASS" if pair["a_then_b_final_stories_match"] else "FAIL")]+=1
            if ba=="HOSTED_PASS":
                final_semantics["B_THEN_A_"+("PASS" if pair["b_then_a_final_stories_match"] else "FAIL")]+=1
            if ab==ba=="HOSTED_PASS":
                final_same["BYTE_EQUAL" if pair["both_final_byte_equal"] else "BYTE_DIFFERENT"]+=1
            else:
                final_same["NOT_BOTH_PASS"]+=1
            if ab!="HOSTED_PASS" or ba!="HOSTED_PASS" or (
                ab==ba=="HOSTED_PASS" and
                (pair["both_final_byte_equal"] is False
                 or not pair["a_then_b_final_stories_match"]
                 or not pair["b_then_a_final_stories_match"])
            ):
                witnesses.append({
                    "source_sha256":src["source_sha256"],
                    "a_story_ordinal":pair["a_story_ordinal"],
                    "b_story_ordinal":pair["b_story_ordinal"],
                    "a_syid":pair["a_syid"],"b_syid":pair["b_syid"],
                    "a_offset_utf16":pair["a_offset_utf16"],
                    "b_offset_utf16":pair["b_offset_utf16"],
                    "ab_outcome":ab,"ab_code":pair["a_then_b_second"].get("writer_code"),
                    "ba_outcome":ba,"ba_code":pair["b_then_a_second"].get("writer_code"),
                    "final_byte_equal":pair["both_final_byte_equal"],
                })
    return {
        "predeclared_sources":len(rows),
        "source_status":dict(sorted(source_status.items())),
        "single_story_controls":selected_story_total,
        "attempted_single_story_controls":attempted_story_total,
        "excluded_single_story_results":dict(sorted(excluded_story_results.items())),
        "cross_story_pairs":pairs_count,
        "ordered_chains":2*pairs_count,
        "A_then_B_second_outcomes":dict(sorted(outcome_a_then_b.items())),
        "B_then_A_second_outcomes":dict(sorted(outcome_b_then_a.items())),
        "two_final_story_semantic_checks":dict(sorted(final_semantics.items())),
        "cross_order_final_byte_equal":dict(sorted(final_same.items())),
        "new_negative_or_noncommuting_witnesses":witnesses,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--rar2",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    cfg=parser.parse_args()
    pinned=cfg.rar2.resolve(strict=True)
    binary=pinned/"tools/native-pub-candidate-cli/target/release/examples"/BINARY_NAME
    if not binary.is_file():
        parser.error("pinned Rust probe missing")
    sources=admitted_sources()
    output=cfg.out.resolve()
    output.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.pub-t-960.plan.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "prior_evidence":"https://github.com/calex794/sk1/actions/runs/38083249275/artifacts/11680967998",
        "sample_origin":"11 SHA with at least two independently successful second-slot delete controls in PUB-T-956",
        "source_sha256":list(SOURCE_SHA256),
        "expected_story_controls":32,
        "expected_attempted_story_controls":33,
        "expected_excluded_tokn_story_controls":1,
        "expected_cross_story_pairs":EXPECTED_PAIRS,
        "expected_ordered_chains":EXPECTED_CHAINS,
        "unit_of_independence":"source_sha256, not Story/ordered chain",
        "native_publisher_acceptance":"NOT_EVALUATED",
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row in sources:
        records.append(evaluate_source(row,binary))
        (output/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    aggregate=summarize(records)
    report={
        "schema":"sk1.pub-t-960.report.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":aggregate,
        "records":records,
    }
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    accepted=(
        aggregate["source_status"].get("EVALUATED",0)==11
        and all(row.get("reason")=="EVALUATED" for row in records)
        and all(row.get("eligible_story_count")==3 for row in records)
        and all(sum(c["single_delete"]["status"]=="HOSTED_PASS" for c in
                    row.get("single_controls",[]))==EXPECTED_PASS_COUNTS[row["source_sha256"]]
                for row in records)
        and aggregate["attempted_single_story_controls"]==33
        and aggregate["single_story_controls"]==32
        and aggregate["excluded_single_story_results"]=={"quill_token_layer":1}
        and aggregate["cross_story_pairs"]==31
        and aggregate["ordered_chains"]==62
        and len(aggregate["A_then_B_second_outcomes"])>0
        and len(aggregate["B_then_A_second_outcomes"])>0
    )
    print(json.dumps({"baseline":"PASS" if accepted else "DRIFT_OR_INCOMPLETE",
                      "summary":aggregate},indent=2))
    return 0 if accepted else 2


if __name__=="__main__":
    sys.exit(main())
