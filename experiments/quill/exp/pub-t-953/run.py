#!/usr/bin/env python3
"""SK1-QUILL-EXP-PUB-T-953: SHA-pinned AB/BA two-deletion public experiment.
Uses already verified EXP-002 witnesses, never produces a second Writer.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / "sk1-exp-001" / "run.py"
SPEC = importlib.util.spec_from_file_location("sk1_exp001_source_gate", SHARED)
assert SPEC and SPEC.loader
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)
HERE = Path(__file__).resolve().parent
UPSTREAM = "703808408fd919e564a90cdc236e81db3c04af8b"
EXP002_ZIP = "651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273"
SOURCE_COUNT = 23
WITNESS_COUNT = 24
SHA = re.compile(r"^[0-9a-f]{64}$")
CFB_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")

def load_witnesses() -> tuple[list[dict], str]:
    raw = (HERE / "witnesses.psv").read_bytes()
    lines = raw.decode("utf-8").splitlines()
    assert any(EXP002_ZIP in x for x in lines if x.startswith("#"))
    rows = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        values = line.split("|")
        if len(values) != 9:
            raise ValueError("invalid witness column count")
        sha, ordinal, storylen, arank, aoff, asha, brank, boff, bsha = values
        if not all(SHA.fullmatch(x) for x in (sha, asha, bsha)):
            raise ValueError("invalid witness SHA")
        item = dict(source_sha256=sha, story_ordinal=int(ordinal),
            story_utf16_len=int(storylen), a_ascii_rank=int(arank),
            a_offset_utf16=int(aoff), expected_a_sha256=asha,
            b_ascii_rank=int(brank), b_offset_utf16=int(boff),
            expected_b_sha256=bsha)
        if item["story_ordinal"] not in range(3) or item["story_utf16_len"] <= 1:
            raise ValueError("bad Story witness")
        if item["a_offset_utf16"] == item["b_offset_utf16"]:
            raise ValueError("overlapping witness offsets")
        rows.append(item)
    pairs = [(w["source_sha256"],w["story_ordinal"]) for w in rows]
    if len(rows) != WITNESS_COUNT or len(set(pairs)) != WITNESS_COUNT:
        raise ValueError("witness count or uniqueness drift")
    if len({w["source_sha256"] for w in rows}) != SOURCE_COUNT:
        raise ValueError("witness source coverage drift")
    return rows, hashlib.sha256(raw).hexdigest()

def probe_source(row: dict, witnesses: list[dict], binary: Path) -> list[dict]:
    results = []
    base = dict(source_sha256=row["sha256"],source_type=row["source_type"],
        source_bytes=row["size"])
    try:
        content = common.retrieve(row["url"], min(row["size"]+1,common.MAX_FILE_BYTES))
        if len(content) != row["size"] or common.digest(content) != row["sha256"]:
            return [dict(base, story_ordinal=w["story_ordinal"], status="NOT_EVALUATED",
                reason="SHA_OR_SIZE_DRIFT") for w in witnesses]
        if not content.startswith(CFB_SIGNATURE):
            return [dict(base, story_ordinal=w["story_ordinal"], status="NOT_EVALUATED",
                reason="CFB_MAGIC_MISSING") for w in witnesses]
        with tempfile.TemporaryDirectory(prefix="sk1-quill-t953-") as tmp:
            folder=Path(tmp)
            source=folder/"source.pub"
            source.write_bytes(content)
            for index,w in enumerate(witnesses):
                contract=folder/f"witness-{index}.json"
                out=folder/f"receipt-{index}.json"
                contract.write_text(json.dumps(w,sort_keys=True)+"\n",encoding="utf-8")
                process=subprocess.run(
                    [str(binary), str(source), row["sha256"], str(contract),str(out)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
                if process.returncode or not out.is_file():
                    results.append(dict(base,story_ordinal=w["story_ordinal"],
                        status="NOT_EVALUATED",reason="PROBE_PROCESS_FAILED"))
                    continue
                report=json.loads(out.read_text(encoding="utf-8"))
                if (report.get("schema") != "sk1.quill-exp-pub-t-953.probe.v1"
                    or report.get("source_sha256") != row["sha256"]
                    or report.get("story_ordinal") != w["story_ordinal"]
                    or report.get("publisher_native_acceptance") != "NOT_EVALUATED"
                    or report.get("product_pub_download_authorized") is not False):
                    results.append(dict(base,story_ordinal=w["story_ordinal"],
                        status="NOT_EVALUATED",reason="INVALID_PROBE_RECEIPT"))
                    continue
                results.append(dict(base,story_ordinal=w["story_ordinal"],
                    status="EVALUATED",reason="OBSERVED",record=report))
            if common.digest(source.read_bytes()) != row["sha256"]:
                raise ValueError("Source file modified")
    except Exception as exc:
        errtype=type(exc).__name__.upper()
        results=[dict(base,story_ordinal=w["story_ordinal"],status="NOT_EVALUATED",
            reason="INPUT_OR_HARNESS_"+errtype) for w in witnesses]
    return results

def status(item: dict) -> str:
    if not isinstance(item,dict):
        return "MISSING"
    return item.get("status","MISSING")

def summarize(rows: list[dict]) -> dict:
    totals=Counter()
    ab_status=Counter()
    ba_status=Counter()
    source_pass=set()
    candidates=[]
    for row in rows:
        totals["pairs_seen"] += 1
        if row["status"] != "EVALUATED":
            totals["pairs_not_evaluated"] += 1
            continue
        source_pass.add(row["source_sha256"])
        rec=row["record"]
        if rec["singles_baseline_match"] is not True:
            totals["baseline_drift"] += 1
            continue
        totals["baseline_pairs_verified"] += 1
        a=status(rec["ab_second"])
        b=status(rec["ba_second"])
        ab_status[a]+=1
        ba_status[b]+=1
        a_pass=a=="HOSTED_PASS";b_pass=b=="HOSTED_PASS"
        if a_pass:totals["ab_pass"]+=1
        if b_pass:totals["ba_pass"]+=1
        if a_pass and b_pass:
            totals["both_pass"]+=1
            if rec["same_final_pub_bytes"] is True:
                totals["both_pass_byte_equal"]+=1
            elif rec["same_final_pub_bytes"] is False:
                totals["both_pass_byte_different"]+=1
        elif a_pass:totals["only_ab_pass"]+=1
        elif b_pass:totals["only_ba_pass"]+=1
        else:totals["neither_pass"]+=1
        if a_pass != b_pass:
            candidates.append(dict(source_sha256=row["source_sha256"],
                story_ordinal=row["story_ordinal"],
                a_offset_utf16=rec["a_offset_utf16"],b_offset_utf16=rec["b_offset_utf16"],
                ab_second=rec["ab_second"],ba_second=rec["ba_second"]))
    return {
        "sources_selected":SOURCE_COUNT, "sources_evaluated":len(source_pass),
        "pairs_selected":WITNESS_COUNT,
        "pairs_evaluated":totals["pairs_seen"]-totals["pairs_not_evaluated"],
        "pairs_not_evaluated":totals["pairs_not_evaluated"],
        "baseline_pairs_verified":totals["baseline_pairs_verified"],
        "baseline_drift":totals["baseline_drift"],
        "ab_pass":totals["ab_pass"],"ba_pass":totals["ba_pass"],
        "both_pass":totals["both_pass"],
        "only_ab_pass":totals["only_ab_pass"],"only_ba_pass":totals["only_ba_pass"],
        "neither_pass":totals["neither_pass"],
        "both_pass_byte_equal":totals["both_pass_byte_equal"],
        "both_pass_byte_different":totals["both_pass_byte_different"],
        "ab_second_status":dict(sorted(ab_status.items())),
        "ba_second_status":dict(sorted(ba_status.items())),
        "order_sensitive_witnesses":candidates,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
    }

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    rar2=args.rar2.resolve(strict=True)
    binary=rar2/"tools/native-pub-candidate-cli/target/release/examples/sk1_quill_exp_pub_t_953"
    if not binary.is_file():ap.error("binary not built")
    witness_list,witness_hash=load_witnesses()
    original=common.load_manifest(None)
    candidates=common.candidates(original)
    sources={r["sha256"]:r for r in candidates}
    if len(sources)!=26 or any(w["source_sha256"] not in sources for w in witness_list):
        raise ValueError("allowed sources differ from EXP-002 input")
    unique_sources=list(dict.fromkeys(w["source_sha256"] for w in witness_list))
    if sum(sources[s]["size"] for s in unique_sources)>common.MAX_TOTAL_BYTES:
        raise ValueError("source byte budget exceeded")
    groups=defaultdict(list)
    for witness in witness_list:
        groups[witness["source_sha256"]].append(witness)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.quill-exp-pub-t-953.plan.v1",
        "upstream_commit":UPSTREAM,"exp002_zip_sha256":EXP002_ZIP,
        "exp002_github_artifact_id":11678607165,
        "witnesses_sha256":witness_hash,
        "manifest_url":common.MANIFEST_URL,"source_count":SOURCE_COUNT,
        "pair_count":WITNESS_COUNT,"witnesses":witness_list,
        "scope":"two consecutive single ASCII deletions on one Story; hosted only"
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for sha in unique_sources:
        records.extend(probe_source(sources[sha],groups[sha],binary))
        (output/"records.json").write_text(
            json.dumps(records,indent=2)+"\n",encoding="utf-8")
    summary=summarize(records)
    report={
        "schema":"sk1.quill-exp-pub-t-953.report.v1",
        "upstream_commit":UPSTREAM,
        "exp002_zip_sha256":EXP002_ZIP,
        "witnesses_sha256":witness_hash,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":summary,"records":records
    }
    (output/"report.json").write_text(
        json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if (summary["pairs_evaluated"]!=24 or summary["baseline_pairs_verified"]!=24
        or summary["sources_evaluated"]!=23 or summary["baseline_drift"] or
        summary["pairs_not_evaluated"]):
        print(json.dumps({"result":"INCOMPLETE_OR_EXP002_DRIFT","summary":summary},
            sort_keys=True))
        return 2
    print(json.dumps({"result":"COMPLETE","summary":summary},indent=2))
    return 0

if __name__=="__main__":
    sys.exit(main())
