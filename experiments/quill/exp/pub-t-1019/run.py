#!/usr/bin/env python3
"""PUB-T-1019: 26 original PUB × up to 2 ordinary Story × four positions × 2 glyphs.

Only immutable upstream Reader/Editor/Writer and pinned T963 byte comparator
execute edits. All source/candidate PUB content stays ephemeral on CI.
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

ROOT=Path(__file__).resolve().parents[3]
LEGACY=ROOT/"sk1-exp-001"/"run.py"
spec=importlib.util.spec_from_file_location("sk1_1019_immutable_source_intake",LEGACY)
assert spec and spec.loader
source=importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
RESEARCH_SOURCE="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
REFERENCE_BLOB="b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92"
T1007_PIN="09982df458d9882d683ec58e17c6bc1481b0b2ae"
T1007_ZIP_SHA="e2ede2209ce51c5fd9f5b6bf3710645d16314a0e6388434e093129b42d019d19"
BINARY="sk1_pub_t_1019_boundary_replace"
SLOTS=["first","second","middle","last"]
VARIANTS=["ASCII_UPPER","CYRILLIC_ZHE"]
ORDERS=["delete_then_insert","insert_then_delete"]
EXPECTED_SOURCE_COUNT=26
MAX_STORIES=2
BASELINE={
 "155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba":{
  "source_syid_header":22,"old":104,
  "ASCII_UPPER":"d383e643d515faaf374347600d7ef50bb3d00bd3d47c5c74b2ad0ff0046483a8",
  "CYRILLIC_ZHE":"863243a9149b687196783b11459746002130f0c35759d70ed61812b3a65ec42d"},
 "1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e":{
  "source_syid_header":12,"old":108,
  "ASCII_UPPER":"5b132e6a5e01cf8f6302fa053cb3f6422ffe5621067cb744fde6bdfd5cc72f25",
  "CYRILLIC_ZHE":"3327f5afd2756c564fedbcb40cbc19bd59e9a5ca60a15eb477f64754e613d90e"},
 "712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a":{
  "source_syid_header":2,"old":117,
  "ASCII_UPPER":"3032fb89646ed4a2b43f7f810e5a579ed0b6d26490792d411812e278ae154839",
  "CYRILLIC_ZHE":"0132c39888f5f857bb4ee4c9535e1af66815abbd653d5ac96b89897a00633b2b"}
}

def frozen_sources():
    rows=source.candidates(source.load_manifest(None))
    if len(rows)!=EXPECTED_SOURCE_COUNT or len({x["sha256"] for x in rows})!=EXPECTED_SOURCE_COUNT:
        raise ValueError("frozen 26 public sources changed")
    if not set(BASELINE).issubset({x["sha256"] for x in rows}):
        raise ValueError("PUB-T-1007 source fixture not present")
    return rows

def admit(row,binary):
    report={"source_sha256":row["sha256"],"source_bytes":row["size"],
            "source_type":row["source_type"],"status":"NOT_EVALUATED",
            "reason":"NOT_STARTED","source_syid_header":None,
            "eligible_story_count":0,"selected_story_count":0,"stories":[]}
    try:

        # Source transport errors may be retried once, but never use a
        # different source or select candidates based on Writer outcomes.
        try:
            contents=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        except Exception:
            try:
                contents=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
            except Exception as retry_error:
                report["reason"]="SOURCE_FETCH_"+type(retry_error).__name__.upper()
                return report
        if len(contents)!=row["size"] or source.digest(contents)!=row["sha256"]:
            report["reason"]="SOURCE_BYTES_OR_SHA_DRIFT"
            return report
        if contents[:8]!=bytes.fromhex("d0cf11e0a1b11ae1"):
            report["reason"]="NOT_CFB"
            return report
        with tempfile.TemporaryDirectory(prefix="sk1-t1019-") as scratch:
            original=Path(scratch)/"immutable.pub"
            receipt=Path(scratch)/"out.json"
            original.write_bytes(contents)
            executed=subprocess.run(
                [str(binary),str(original),row["sha256"],str(receipt)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1500)
            if executed.returncode or not receipt.is_file():
                report["reason"]="RUST_PROBE_FAILED"
                return report
            result=json.loads(receipt.read_text(encoding="utf-8"))
        if not(
          result.get("schema")=="sk1.quill-exp-pub-t-1019.source.v1"
          and result.get("source_sha256")==row["sha256"]
          and result.get("source_bytes")==row["size"]
          and result.get("native_publisher_acceptance")=="NOT_EVALUATED"
          and result.get("result") in
             {"EVALUATED","NO_ELIGIBLE_STORY","SOURCE_EDITOR_OPEN_BLOCKED"}
          and isinstance(result.get("stories"),list)
        ):
            report["reason"]="INVALID_RUST_RECEIPT"
            return report
        report.update(status=result["result"],reason=result["result"],
            source_syid_header=result["source_syid_header"],
            eligible_story_count=result["eligible_story_count"],
            selected_story_count=result["selected_story_count"],
            stories=result["stories"])
    except Exception as error:
        # No unbounded exception strings, file URLs or raw Story/Quill bytes.
        report["reason"]=type(error).__name__.upper()
    return report

def locate_controls(rows):
    controls=[]
    for row in rows:
        wanted=BASELINE.get(row["source_sha256"])
        if wanted is None:continue
        matches=[story for story in row["stories"] if story["story_ordinal"]==0]
        second=[slot for story in matches for slot in story["slots"]
                if slot["slot"]=="second" and slot["utf16_offset"]==1]
        entry={"source_sha256":row["source_sha256"],
               "found":bool(len(second)==1),
               "source_header_matches":row["source_syid_header"]==wanted["source_syid_header"],
               "old_matches":bool(len(second)==1 and
                    second[0]["original_codepoint"]==wanted["old"]),
               "glyph_receipts":[]}
        if len(second)==1:
            for v in second[0]["variants"]:
                expected=wanted.get(v["name"])
                a=v["delete_then_insert"]
                b=v["insert_then_delete"]
                entry["glyph_receipts"].append({
                   "name":v["name"],
                   "matches":bool(expected is not None
                      and a["final_sha256"]==expected and b["final_sha256"]==expected
                      and a["second"]["status"]=="HOSTED_PASS"
                      and b["second"]["status"]=="HOSTED_PASS")
                })
        entry["passed"]=bool(entry["found"] and entry["source_header_matches"]
             and entry["old_matches"]
             and len(entry["glyph_receipts"])==len(VARIANTS)
             and {v["name"] for v in entry["glyph_receipts"]}==set(VARIANTS)
             and all(v["matches"] for v in entry["glyph_receipts"]))
        controls.append(entry)
    return controls

def summarize(rows):
    source_status=Counter(row["status"] for row in rows)
    direct=Counter()
    first=Counter()
    second=Counter()
    first_codes=Counter()
    second_codes=Counter()
    orders={k:{"attempts":0,"first_pass":0,"completed":0,"locality_true":0,
               "locality_false":0} for k in ORDERS}
    by_slot={k:{"unique_offsets":0,"variants":0,"completed_orders":0,
                "both_orders":0,"equal_final_sha":0} for k in SLOTS}
    completed=0
    cells=0
    both_complete=0
    equal_sha=0
    initial_stories=0
    dedup=0
    raw_diff_exceptions=[]
    for row in rows:
        for story in row["stories"]:
            initial_stories+=1
            dedup+=len(story["dedup_skipped"])
            for slot in story["slots"]:
                label=slot["slot"]
                by_slot[label]["unique_offsets"]+=1
                for variant in slot["variants"]:
                    cells+=1
                    by_slot[label]["variants"]+=1
                    d=variant["direct_replace"]
                    direct[d["status"]]+=1
                    flow_finishes=0
                    for key in ORDERS:
                        flow=variant[key]
                        orders[key]["attempts"]+=1
                        fst,snd=flow["first"],flow["second"]
                        first[fst["status"]]+=1
                        second[snd["status"]]+=1
                        if fst["status"]=="HOSTED_PASS":
                            orders[key]["first_pass"]+=1
                        if fst["status"]=="WRITER_BLOCKED":
                            first_codes[fst["writer_code"]]+=1
                        if snd["status"]=="WRITER_BLOCKED":
                            second_codes[snd["writer_code"]]+=1
                        if flow["final_sha256"] is not None:
                            completed+=1
                            flow_finishes+=1
                            orders[key]["completed"]+=1
                            by_slot[label]["completed_orders"]+=1
                            eq=flow["final_hypothesis"]
                            orders[key]["locality_true" if eq else "locality_false"]+=1
                            if eq is False:
                                raw_diff_exceptions.append({
                                    "source_sha256":row["source_sha256"],
                                    "story_ordinal":story["story_ordinal"],
                                    "slot":label,"glyph":variant["name"],
                                    "order":key})
                    if flow_finishes==2:
                        both_complete+=1
                        by_slot[label]["both_orders"]+=1
                        if variant["two_stage_sha_equal"] is True:
                            equal_sha+=1
                            by_slot[label]["equal_final_sha"]+=1
    controls=locate_controls(rows)
    return {"source_count":len(rows),"source_status":dict(sorted(source_status.items())),
      "total_eligible_stories":sum(r["eligible_story_count"] for r in rows),
      "selected_story_count":initial_stories,
      "unique_slot_count":sum(x["unique_offsets"] for x in by_slot.values()),
      "duplicate_slot_count":dedup,
      "variant_cells":cells,"two_stage_sequences":cells*2,
      "direct_controls":dict(sorted(direct.items())),
      "first_step_outcomes":dict(sorted(first.items())),
      "second_step_outcomes":dict(sorted(second.items())),
      "first_writer_guard_codes":dict(sorted(first_codes.items())),
      "second_writer_guard_codes":dict(sorted(second_codes.items())),
      "order_stats":orders,"by_slot":by_slot,
      "completed_sequences":completed,"both_orders_completed":both_complete,
      "byte_equal_final_sha":equal_sha,
      "byte_locality_exceptions":raw_diff_exceptions,
      "baseline_t1007":controls,"baseline_t1007_all_pass":
        len(controls)==len(BASELINE) and all(x["passed"] for x in controls)
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rar2",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    writer=args.rar2.resolve(strict=True)
    binary=writer/"tools/native-pub-candidate-cli/target/release/examples"/BINARY
    if not binary.is_file():
        parser.error("original pinned Writer probe not built")
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    rows=frozen_sources()
    plan={
      "schema":"sk1.quill-exp-pub-t-1019.plan.v1",
      "rar2_pin":PIN,"science_reuse_commit":RESEARCH_SOURCE,
      "science_reuse_blob":REFERENCE_BLOB,
      "reference_t1007_pin":T1007_PIN,
      "reference_t1007_zip_sha256":T1007_ZIP_SHA,
      "source_manifest":source.MANIFEST_URL,
      "source_sha256":[r["sha256"] for r in rows],
      "source_bytes":[r["size"] for r in rows],
      "source_count":EXPECTED_SOURCE_COUNT,
      "selected_stories_per_source":MAX_STORIES,
      "positions":SLOTS,"codepoints":VARIANTS,
      "two_step_orders":ORDERS,
      "maximum_variant_cells":26*2*4*2,
      "native_publisher_acceptance":"NOT_EVALUATED",
      "raw_pub_output_authorized":False
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    admitted=[]
    for row in rows:
        admitted.append(admit(row,binary))
        # Bounded machine receipt per source, never URLs, Story text or raw bytes.
        print(json.dumps({"source_sha256":admitted[-1]["source_sha256"],
                          "status":admitted[-1]["status"],
                          "reason":admitted[-1]["reason"],
                          "selected_story_count":admitted[-1]["selected_story_count"]},
                         sort_keys=True),flush=True)
        (out/"records.json").write_text(
            json.dumps(admitted,indent=2)+"\n",encoding="utf-8")
    result={"schema":"sk1.quill-exp-pub-t-1019.report.v1",
       "rar2_pin":PIN,"native_publisher_acceptance":"NOT_EVALUATED",
       "raw_pub_output_authorized":False,
       "summary":summarize(admitted),"records":admitted}
    (out/"report.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    all_sources_ok=len(admitted)==EXPECTED_SOURCE_COUNT and all(
        row["status"] in {"EVALUATED","NO_ELIGIBLE_STORY","SOURCE_EDITOR_OPEN_BLOCKED"}
        for row in admitted)
    full=all_sources_ok and result["summary"]["variant_cells"]>0 \
         and result["summary"]["baseline_t1007_all_pass"]
    print(json.dumps({"task":"PUB-T-1019","outcome":
        "COMPLETE" if full else "INCOMPLETE","summary":result["summary"]},
        sort_keys=True))
    return 0 if full else 2

if __name__=="__main__":
    sys.exit(main())
