#!/usr/bin/env python3
"""PUB-T-965: a preregistered synthetic SYID DWORD boundary study (no PUB in output)."""
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
S = importlib.util.spec_from_file_location("sk1_exp001_965_source_intake", LEGACY)
assert S and S.loader
source = importlib.util.module_from_spec(S)
S.loader.exec_module(source)

PIN = "703808408fd919e564a90cdc236e81db3c04af8b"
SOURCE_COUNTERS = {
    "155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba": 22,
    "1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e": 12,
    "712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a": 2,
}
VALUES = [0xFD, 0xFE, 0xFF, 0xFFFD, 0xFFFE, 0xFFFF,
          0xFFFFFFFD, 0xFFFFFFFE, 0xFFFFFFFF]
BINARY = "sk1_pub_t_965_syid_carry"

def sources():
    candidates=source.candidates(source.load_manifest(None))
    # The originally pinned public intake has exactly 26 sources.
    assert len(candidates)==26 and len({x["sha256"] for x in candidates})==26
    selected={x["sha256"]:x for x in candidates if x["sha256"] in SOURCE_COUNTERS}
    if set(selected)!=set(SOURCE_COUNTERS):
        raise ValueError("predeclared SHA missing from source manifest")
    return [selected[x] for x in SOURCE_COUNTERS]

def test_source(row:dict,binary:Path)->dict:
    out={"source_sha256":row["sha256"],"source_type":row["source_type"],
         "source_bytes":row["size"],"status":"NOT_EVALUATED","reason":"NOT_STARTED",
         "baseline":None,"original_syid_first_dword":None,
         "story_ordinal":None,"slot":None,"offset_utf16":None,"variants":[]}
    try:
        raw=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(raw)!=row["size"] or source.digest(raw)!=row["sha256"]:
            out["reason"]="SOURCE_HASH_OR_SIZE_DRIFT"
            return out
        if raw[:8]!=bytes.fromhex("d0cf11e0a1b11ae1"):
            out["reason"]="NOT_CFB"
            return out
        with tempfile.TemporaryDirectory(prefix="sk1-t965-") as temporary:
            root=Path(temporary)
            src=root/"temporary.pub"
            json_out=root/"receipt.json"
            src.write_bytes(raw)
            proc=subprocess.run([str(binary),str(src),row["sha256"],str(json_out)],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=500)
            if proc.returncode or not json_out.is_file():
                out["reason"]="RUST_PROBE_FAILED"
                return out
            result=json.loads(json_out.read_text(encoding="utf-8"))
        if (result.get("schema")!="sk1.cfb-exp-pub-t-965.source.v1"
            or result.get("source_sha256")!=row["sha256"]
            or result.get("source_bytes")!=row["size"]
            or result.get("original_syid_first_dword")!=SOURCE_COUNTERS[row["sha256"]]
            or result.get("native_publisher_acceptance")!="NOT_EVALUATED"
            or result.get("story_ordinal")!=0 or result.get("slot")!="second"
            or result.get("offset_utf16")!=1):
            out["reason"]="RUST_RECEIPT_INVALID"
            return out
        out.update(status=result["status"],reason=result["status"],
                   baseline=result["baseline"],
                   original_syid_first_dword=result["original_syid_first_dword"],
                   story_ordinal=result["story_ordinal"],slot=result["slot"],
                   offset_utf16=result["offset_utf16"],variants=result["variants"])
    except Exception as e:
        # Never publish exception messages, source paths, raw text or unexpected URLs.
        out["reason"]=type(e).__name__.upper()
    return out

def summarize(rows):
    statuses=Counter()
    variant_states=Counter()
    first=Counter()
    second=Counter()
    matched=Counter()
    by_value=defaultdict(lambda:Counter())
    exceptions=[]
    used_sources=set()
    for row in rows:
        statuses[row["status"]]+=1
        if row["status"]!="EVALUATED":
            continue
        used_sources.add(row["source_sha256"])
        for v in row["variants"]:
            value=v["variant_header"]
            name=f"0x{value:08x}"
            variant_states[v["status"]]+=1
            by_value[name]["attempted"]+=1
            if v["status"]!="MEASURED":
                exceptions.append({"source_sha256":row["source_sha256"],
                        "variant_header":value,"status":v["status"]})
                continue
            if v["patch"]["exact_header_only"] is True:
                by_value[name]["synthetic_exact_patch"]+=1
            if v["semantic_source_reopen"]:
                by_value[name]["semantic_reopen"]+=1
            for arm in ("insert_delete","delete_insert"):
                a=v[arm]
                first_status=a["first"]["status"]
                second_status=a["second"]["status"]
                first[first_status]+=1
                second[second_status]+=1
                by_value[name]["arm_attempts"]+=1
                by_value[name]["first_"+first_status]+=1
                by_value[name]["second_"+second_status]+=1
                if a["final"] is not None:
                    d=a["final"]
                    by_value[name]["complete_finals"]+=1
                    by_value[name]["raw_bytes_"+str(d["whole_pub_raw_changed_bytes"])]+=1
                    matched[str(d["predicted_raw_exact_match"])]+=1
                    by_value[name]["model_exact"]+=int(d["predicted_raw_exact_match"] is True)
                    if not d["predicted_raw_exact_match"]:
                        exceptions.append({"source_sha256":row["source_sha256"],
                          "variant_header":value,"arm":arm,"status":"RAW_MODEL_COUNTEREXAMPLE",
                          "actual_changed_raw_bytes":d["whole_pub_raw_changed_bytes"],
                          "predicted_changed_header_bytes":d["predicted_changed_header_bytes"]})
    return {
        "source_status":dict(sorted(statuses.items())),
        "distinct_predeclared_SHA":len(rows),
        "distinct_evaluated_SHA":len(used_sources),
        "variant_status":dict(sorted(variant_states.items())),
        "first_writer_outcome":dict(sorted(first.items())),
        "second_writer_outcome":dict(sorted(second.items())),
        "raw_exact_model":dict(sorted(matched.items())),
        "per_value":{k:dict(sorted(v.items())) for k,v in sorted(by_value.items())},
        "exceptions":exceptions
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rar2",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    root=args.rar2.resolve(strict=True)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples"/BINARY
    if not binary.is_file():
        parser.error("pinned Writer probe not built")
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.cfb-exp-pub-t-965.plan.v1",
        "rar2_pin":PIN,
        "source_manifest":source.MANIFEST_URL,
        "source_sha256":list(SOURCE_COUNTERS),
        "original_source_counters":SOURCE_COUNTERS,
        "slot":"second","story_ordinal":0,"offset_utf16":1,
        "synthetic_headers":VALUES,
        "synthetic_variants_per_real_source":len(VALUES),
        "real_source_count":len(SOURCE_COUNTERS),
        "inverse_arms":["insert_delete","delete_insert"],
        "predecessor_963_zip_sha256":"70aed39805d587b1f4cb32bb96ec8e615c6e4f22b7909438ed1d8685c976b3dc",
        "native_publisher_acceptance":"NOT_EVALUATED",
        "raw_pub_output_authorized":False
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    results=[]
    for row in sources():
        results.append(test_source(row,binary))
        (out/"records.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    report={
        "schema":"sk1.cfb-exp-pub-t-965.report.v1",
        "rar2_pin":PIN,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "raw_pub_output_authorized":False,
        "summary":summarize(results),
        "records":results
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    accepted=len(results)==3 and all(
        row["status"]=="EVALUATED" and len(row["variants"])==9
        and {v["variant_header"] for v in row["variants"]}==set(VALUES)
        for row in results)
    print(json.dumps({
        "research_execution":"ACCEPTED" if accepted else "INCOMPLETE",
        "source_count":len(results),
        "source_status":report["summary"]["source_status"],
        "variant_status":report["summary"]["variant_status"],
        "raw_exact_model":report["summary"]["raw_exact_model"]
    },sort_keys=True))
    return 0 if accepted else 2

if __name__=="__main__":
    sys.exit(main())
