#!/usr/bin/env python3
"""PUB-T-1007: source-safe 1->1 UTF-16 Writer substitution outcomes."""
from __future__ import annotations
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
LEGACY=ROOT/"sk1-exp-001"/"run.py"
mod=importlib.util.spec_from_file_location("sk1_1007_source_intake",LEGACY)
assert mod and mod.loader
source=importlib.util.module_from_spec(mod)
mod.loader.exec_module(source)

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
RESEARCH_SOURCE="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
REFERENCE_BLOB="b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92"
SOURCES={
  "155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba":22,
  "1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e":12,
  "712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a":2
}
VARIANTS=["ASCII_UPPER","CYRILLIC_ZHE","CJK_IDEOGRAPH","NBSP"]
BINARY="sk1_pub_t_1007_two_step"

def selected():
    manifest=source.candidates(source.load_manifest(None))
    assert len(manifest)==26 and len({x["sha256"] for x in manifest})==26
    rows={x["sha256"]:x for x in manifest if x["sha256"] in SOURCES}
    if set(rows)!=set(SOURCES):
        raise ValueError("predeclared source SHA unavailable")
    return [rows[sha] for sha in SOURCES]

def test_file(row, binary):
    out={"source_sha256":row["sha256"],"source_type":row["source_type"],
         "source_bytes":row["size"],"status":"NOT_EVALUATED","reason":"NOT_STARTED",
         "original_codepoint":None,"source_syid_header":None,
         "slot":None,"story_ordinal":None,"utf16_offset":None,
         "baseline_insert":None,"baseline_delete":None,
         "baseline_inverse_insert":None,"baseline_inverse_delete":None,
         "variants":[]}
    try:
        raw=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(raw)!=row["size"] or source.digest(raw)!=row["sha256"]:
            out["reason"]="SOURCE_SHA_OR_SIZE_DRIFT"
            return out
        if raw[:8]!=bytes.fromhex("d0cf11e0a1b11ae1"):
            out["reason"]="NOT_CFB"
            return out
        with tempfile.TemporaryDirectory(prefix="sk1-t1007-") as temporary:
            directory=Path(temporary)
            input_file=directory/"temporary.pub"
            output_file=directory/"receipt.json"
            input_file.write_bytes(raw)
            p=subprocess.run([str(binary),str(input_file),row["sha256"],str(output_file)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=360)
            if p.returncode or not output_file.is_file():
                out["reason"]="RUST_PROBE_FAILED"
                return out
            result=json.loads(output_file.read_text(encoding="utf-8"))
        if (result.get("schema")!="sk1.quill-exp-pub-t-1007.source.v1"
            or result.get("source_sha256")!=row["sha256"]
            or result.get("source_bytes")!=row["size"]
            or result.get("source_syid_header")!=SOURCES[row["sha256"]]
            or result.get("native_publisher_acceptance")!="NOT_EVALUATED"
            or result.get("story_ordinal")!=0 or result.get("slot")!="second"
            or result.get("utf16_offset")!=1):
            out["reason"]="RUST_RECEIPT_INVALID"
            return out
        out.update(status=result["result"],reason=result["result"],
                   source_syid_header=result["source_syid_header"],
                   original_codepoint=result["original_codepoint"],
                   slot=result["slot"],story_ordinal=result["story_ordinal"],
                   utf16_offset=result["utf16_offset"],
                   baseline_insert=result["baseline_insert"],
                   baseline_delete=result["baseline_delete"],
                   baseline_inverse_insert=result["baseline_inverse_insert"],
                   baseline_inverse_delete=result["baseline_inverse_delete"],
                   variants=result["variants"])
    except Exception as e:
        # Never leak exceptions/URLs/UTF16 Story content into the public receipt.
        out["reason"]=type(e).__name__.upper()
    return out

def summarize(rows):
    source_states=Counter()
    first_states=Counter()
    second_states=Counter()
    by_value={}
    abnormal=[]
    for row in rows:
        source_states[row["status"]]+=1
        if row["status"]!="EVALUATED":continue
        for var in row["variants"]:
            name=var["name"]
            v=by_value.setdefault(name,{"attempts":0,"first_pass":0,"inverse_pass":0,
                                       "first_match":0,"inverse_match":0})
            v["attempts"]+=1
            f=var["first"]["status"]
            i=var["inverse"]["status"]
            first_states[f]+=1
            second_states[i]+=1
            v["first_pass"]+=int(f=="HOSTED_PASS")
            v["inverse_pass"]+=int(i=="HOSTED_PASS")
            v["first_match"]+=int(var["first_hypothesis"] is True)
            v["inverse_match"]+=int(var["final_hypothesis"] is True)
            if (f=="HOSTED_PASS" and var["first_hypothesis"] is not True or
                i=="HOSTED_PASS" and var["final_hypothesis"] is not True):
                abnormal.append({"source_sha256":row["source_sha256"],
                  "name":name,"first_status":f,"inverse_status":i,
                  "first_exact":var["first_hypothesis"],
                  "inverse_exact":var["final_hypothesis"]})
    return {
      "source_count":len(rows),"source_status":dict(sorted(source_states.items())),
      "baseline_completed":sum(x["status"]=="EVALUATED" for x in rows),
      "variant_attempts":sum(v["attempts"] for v in by_value.values()),
      "first_outcomes":dict(sorted(first_states.items())),
      "inverse_outcomes":dict(sorted(second_states.items())),
      "by_variant":{k:by_value[k] for k in sorted(by_value)},
      "counterexamples":abnormal
    }


def two_stage_summary(rows):
    base=summarize(rows)
    first=Counter()
    second=Counter()
    locality=Counter()
    finished=0
    both=0
    same_final=0
    for row in rows:
        if row["status"]!="EVALUATED":continue
        for v in row["variants"]:
            if v["delete_then_insert"]["final_sha256"] is not None and \
               v["insert_then_delete"]["final_sha256"] is not None:
                both+=1
                same_final+=int(v["two_stage_sha_equal"] is True)
            for key in ("delete_then_insert","insert_then_delete"):
                seq=v[key]
                first[seq["first"]["status"]]+=1
                second[seq["second"]["status"]]+=1
                if seq["final_sha256"] is not None:
                    finished+=1
                    locality[str(seq["final_hypothesis"])]+=1
    base["two_stage_first_outcomes"]=dict(sorted(first.items()))
    base["two_stage_second_outcomes"]=dict(sorted(second.items()))
    base["two_stage_completed"]=finished
    base["two_stage_both_complete"]=both
    base["two_stage_equal_final_sha"]=same_final
    base["two_stage_byte_locality"]=dict(sorted(locality.items()))
    return base

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--rar2",required=True,type=Path)
    a.add_argument("--output",required=True,type=Path)
    opt=a.parse_args()
    rar2=opt.rar2.resolve(strict=True)
    exe=rar2/"tools/native-pub-candidate-cli/target/release/examples"/BINARY
    if not exe.is_file():a.error("original Writer probe missing")
    output=opt.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    plan={
       "schema":"sk1.quill-exp-pub-t-1007.plan.v1",
       "rar2_pin":PIN,"scientific_reuse_commit":RESEARCH_SOURCE,
       "scientific_reuse_rust_blob":REFERENCE_BLOB,
       "source_manifest":source.MANIFEST_URL,
       "source_sha256":list(SOURCES),
       "source_syid_header":SOURCES,
       "source_count":3,"eligible_story_ordinal":0,
       "source_slot":"second","offset_utf16":1,
       "replacement_names":VARIANTS,
       "replacement_variants_per_source":4,
       "native_publisher_acceptance":"NOT_EVALUATED",
       "raw_pub_output_authorized":False
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row in selected():
        records.append(test_file(row,exe))
        (output/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    report={
       "schema":"sk1.quill-exp-pub-t-1007.report.v1",
       "rar2_pin":PIN,
       "native_publisher_acceptance":"NOT_EVALUATED",
       "raw_pub_output_authorized":False,
       "summary":two_stage_summary(records),
       "records":records
    }
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    complete=(len(records)==3 and all(
      row["status"]=="EVALUATED" and len(row["variants"])==4
      and [v["name"] for v in row["variants"]]==VARIANTS for row in records))
    print(json.dumps({"study":"PUB-T-1007",
      "execution":"COMPLETE" if complete else "INCOMPLETE",
      "summary":report["summary"]},sort_keys=True))
    return 0 if complete else 2

if __name__=="__main__":
    sys.exit(main())
